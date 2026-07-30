"""Service Desk — MOD Annual Service Visit calendar, engineer appointment
booking form, and 1-month pre-visit reminders.

MOD Type A service contracts (``mod_service_contracts``) auto-schedule an
annual maintenance visit when the quote is e-signed. This module surfaces
those visits on the Service Desk → Preventative Maintenance page as a
month-by-month calendar (colour-coded confirmed vs pending) and lets the
Pulse MOD Service team send the MOD site contact a secure, fillable
"Engineer Appointment Booking" form (mirrors the paper booking sheet used
to book engineers onto a base — visitor + vehicle details for access).

A daily idempotent sweep (run from the poller) emails the MOD Service team
AND the MOD site contact ~1 month before each confirmed visit.
"""
from __future__ import annotations

import os
import uuid
import secrets
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/pm/mod-visits", tags=["Service Ops · MOD Visits"])
public_router = APIRouter(prefix="/public/mod-booking", tags=["Public · MOD Booking Form"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _org_of(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "").rstrip("/")


def _share_url(token: str) -> str:
    base = _frontend_url()
    return f"{base}/mod-booking/{token}" if base else f"/mod-booking/{token}"


def _valid_email(e) -> str:
    e = (e or "").strip().lower()
    return e if ("@" in e and not e.endswith("@site.mod.local")) else ""


async def _resolve_site_email(site_id: str, override: str = "") -> str:
    if _valid_email(override):
        return _valid_email(override)
    site = await db.organizations.find_one(
        {"id": site_id},
        {"_id": 0, "site_manager_email": 1, "primary_contact_email": 1, "contact_email": 1},
    ) or {}
    email = (_valid_email(site.get("site_manager_email"))
             or _valid_email(site.get("primary_contact_email"))
             or _valid_email(site.get("contact_email")))
    if not email:
        owner = await db.users.find_one({"organization_id": site_id, "role": "owner"}, {"_id": 0, "email": 1})
        email = _valid_email(owner.get("email")) if owner else ""
    return email


# Fields of the Engineer Appointment Booking Sheet (editable defaults).
BOOKING_FIELDS = [
    "requested_by_name", "requested_by_email",
    "mod_contact_name", "mod_contact_email", "mod_contact_phone",
    "visit_start_date", "visit_start_time", "visit_end_date", "visit_end_time",
    "engineer_name", "engineer_dob", "engineer_phone",
    "veh_reg", "veh_make", "veh_model", "veh_colour",
]


def _visit_row(c: dict) -> dict:
    av = c.get("annual_visit") or {}
    status = av.get("status") or ("pending_confirmation" if c.get("status") == "active" else "none")
    booking = av.get("booking") or {}
    effective = av.get("scheduled_date") or av.get("proposed_date")
    return {
        "contract_id": c.get("id"),
        "quote_number": c.get("quote_number"),
        "mod_site_id": c.get("mod_site_id"),
        "mod_site_name": c.get("mod_site_name"),
        "contract_status": c.get("status"),
        "visit_status": status,
        "scheduled_date": av.get("scheduled_date"),
        "proposed_date": av.get("proposed_date"),
        "effective_date": effective,
        "engineer": av.get("engineer"),
        "annual_value": c.get("annual_value"),
        "currency": c.get("currency", "GBP"),
        "term_months": c.get("term_months", 12),
        "equipment_count": c.get("equipment_count"),
        "booking_status": booking.get("status") or "not_sent",
        "booking_token": booking.get("token"),
        "share_url": _share_url(booking["token"]) if booking.get("token") else None,
        "reminded_at": av.get("reminded_at"),
    }


@router.get("")
async def list_mod_visits(user: dict = Depends(get_current_user)) -> dict:
    """Every MOD annual service visit for the org (for the PM calendar)."""
    org = _org_of(user)
    rows = await db.mod_service_contracts.find(
        {"organization_id": org}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    visits = [_visit_row(c) for c in rows]
    with_date = [v for v in visits if v["effective_date"]]
    pending = sum(1 for v in visits if v["visit_status"] == "pending_confirmation")
    confirmed = sum(1 for v in visits if v["visit_status"] == "confirmed")
    return {"visits": with_date, "total": len(with_date),
            "pending": pending, "confirmed": confirmed}


@router.post("/{contract_id}/booking-link")
async def create_booking_link(contract_id: str, data: dict = Body(default={}),
                              user: dict = Depends(get_current_user)) -> dict:
    """Create (or reuse) a secure Engineer Appointment Booking form link for a
    contract's annual visit and optionally email it to the MOD site contact."""
    org = _org_of(user)
    contract = await db.mod_service_contracts.find_one(
        {"id": contract_id, "organization_id": org}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    av = contract.get("annual_visit") or {}
    booking = av.get("booking") or {}
    if not booking.get("token"):
        booking = {
            "token": secrets.token_urlsafe(24),
            "status": "sent",
            "requested_by_name": user.get("full_name") or "Pulse Fitness Service",
            "requested_by_email": user.get("email") or "",
            "mod_contact_name": "", "mod_contact_email": "", "mod_contact_phone": "",
            "visit_start_date": av.get("scheduled_date") or av.get("proposed_date") or "",
            "visit_start_time": "", "visit_end_date": "", "visit_end_time": "",
            "engineer_name": av.get("engineer") or "", "engineer_dob": "", "engineer_phone": "",
            "veh_reg": "", "veh_make": "", "veh_model": "", "veh_colour": "",
            "created_at": _now(), "updated_at": _now(),
        }
    booking["status"] = "sent" if booking.get("status") in (None, "not_sent") else booking["status"]
    booking["sent_at"] = _now()
    av["booking"] = booking
    await db.mod_service_contracts.update_one(
        {"id": contract_id}, {"$set": {"annual_visit": av, "updated_at": _now()}})

    share_url = _share_url(booking["token"])
    to_email = await _resolve_site_email(contract.get("mod_site_id"), data.get("email") or "")
    emailed = False
    if data.get("send_email") and to_email:
        try:
            from utils.email import send_mod_booking_form_email
            emailed = await send_mod_booking_form_email(
                to_email, contract.get("mod_site_name") or "your site", share_url,
                visit_date=booking.get("visit_start_date") or "",
                sender_name=user.get("full_name") or "Pulse Fitness",
            )
        except Exception as exc:
            logger.warning("MOD booking email failed for %s: %s", contract_id, exc)
    return {"token": booking["token"], "share_url": share_url,
            "site_email": to_email or None, "emailed": emailed,
            "needs_email": bool(data.get("send_email") and not to_email)}


# ── Public booking form (token-gated, no auth) ────────────────────

async def _contract_by_booking_token(token: str) -> dict:
    c = await db.mod_service_contracts.find_one(
        {"annual_visit.booking.token": token}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Booking form not found or expired")
    return c


def _public_booking_view(c: dict) -> dict:
    av = c.get("annual_visit") or {}
    booking = av.get("booking") or {}
    return {
        "site_name": c.get("mod_site_name"),
        "visit_scheduled_date": av.get("scheduled_date") or av.get("proposed_date"),
        "status": booking.get("status") or "sent",
        "submitted_at": booking.get("submitted_at"),
        "form": {k: booking.get(k, "") for k in BOOKING_FIELDS},
    }


@public_router.get("/{token}")
async def public_get_booking(token: str, request: Request) -> dict:
    from utils.security_plus import rate_limit_async
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"mod_booking_ip:{ip}", max_requests=60, window_seconds=300)
    return _public_booking_view(await _contract_by_booking_token(token))


@public_router.put("/{token}")
async def public_save_booking(token: str, body: dict = Body(...)) -> dict:
    c = await _contract_by_booking_token(token)
    av = c.get("annual_visit") or {}
    booking = av.get("booking") or {}
    if booking.get("status") == "submitted":
        raise HTTPException(409, "This booking form has already been submitted.")
    form = body.get("form") or {}
    for k in BOOKING_FIELDS:
        if k in form:
            booking[k] = (form.get(k) or "").strip() if isinstance(form.get(k), str) else form.get(k)
    booking["status"] = "draft" if booking.get("status") in (None, "sent") else booking["status"]
    booking["updated_at"] = _now()
    av["booking"] = booking
    await db.mod_service_contracts.update_one(
        {"id": c["id"]}, {"$set": {"annual_visit": av, "updated_at": _now()}})
    return _public_booking_view(await _contract_by_booking_token(token))


@public_router.post("/{token}/submit")
async def public_submit_booking(token: str, body: dict = Body(default={})) -> dict:
    c = await _contract_by_booking_token(token)
    av = c.get("annual_visit") or {}
    booking = av.get("booking") or {}
    if booking.get("status") == "submitted":
        raise HTTPException(409, "This booking form has already been submitted.")
    form = body.get("form") or {}
    for k in BOOKING_FIELDS:
        if k in form:
            booking[k] = (form.get(k) or "").strip() if isinstance(form.get(k), str) else form.get(k)
    if not (booking.get("mod_contact_name") and booking.get("mod_contact_email")):
        raise HTTPException(400, "Please provide the MOD contact name and email before submitting.")
    booking["status"] = "submitted"
    booking["submitted_at"] = _now()
    booking["updated_at"] = _now()
    av["booking"] = booking
    await db.mod_service_contracts.update_one(
        {"id": c["id"]}, {"$set": {"annual_visit": av, "updated_at": _now()}})
    # Notify the MOD Service team that the booking form came back.
    try:
        from utils.email import send_email
        team = os.environ.get("MOD_READINESS_HQ_EMAIL") or "modservice@pulsefitness.com"
        html = (f"<p>The Engineer Appointment Booking form for <b>{c.get('mod_site_name')}</b> "
                f"has been completed by the MOD contact.</p>"
                f"<p>Contact: {booking.get('mod_contact_name')} · {booking.get('mod_contact_email')} · "
                f"{booking.get('mod_contact_phone') or '—'}</p>"
                f"<p>Visit: {booking.get('visit_start_date') or '—'} {booking.get('visit_start_time') or ''}</p>")
        await send_email(team, f"MOD booking form completed — {c.get('mod_site_name')}", html, category="support")
    except Exception:
        pass
    return _public_booking_view(await _contract_by_booking_token(token))


__all__ = ["router", "public_router"]
