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

# A booking can name up to 4 visiting engineers, each needing Name / DOB /
# Vehicle registration for base gate access. Stored as booking["engineers"];
# the first entry is mirrored into the legacy single-engineer fields above so
# the fault card and Sicon sync keep working.
MAX_ENGINEERS = 4


def _clean_engineers(raw) -> list:
    out = []
    if isinstance(raw, list):
        for e in raw[:MAX_ENGINEERS]:
            if not isinstance(e, dict):
                continue
            name = (e.get("name") or "").strip()
            dob = (e.get("dob") or "").strip()
            veh_reg = (e.get("veh_reg") or "").strip()
            if name or dob or veh_reg:
                out.append({"name": name, "dob": dob, "veh_reg": veh_reg})
    return out


def _sync_legacy_engineer(booking: dict) -> None:
    """Mirror the first engineer into the legacy single-engineer fields."""
    engs = booking.get("engineers") or []
    if engs:
        first = engs[0]
        booking["engineer_name"] = first.get("name") or ""
        booking["engineer_dob"] = first.get("dob") or ""
        booking["veh_reg"] = first.get("veh_reg") or ""


def _engineers_list(booking: dict) -> list:
    """Normalised engineer list; falls back to the legacy single fields."""
    engs = booking.get("engineers") or []
    if engs:
        return engs
    if booking.get("engineer_name") or booking.get("veh_reg"):
        return [{"name": booking.get("engineer_name") or "",
                 "dob": booking.get("engineer_dob") or "",
                 "veh_reg": booking.get("veh_reg") or ""}]
    return []


def _visit_row(c: dict) -> dict:
    av = c.get("annual_visit") or {}
    status = av.get("status") or ("pending_confirmation" if c.get("status") == "active" else "none")
    booking = av.get("booking") or {}
    effective = av.get("scheduled_date") or av.get("proposed_date")
    booking_out = None
    if booking.get("token"):
        booking_out = {k: booking.get(k, "") for k in BOOKING_FIELDS}
        booking_out["engineers"] = _engineers_list(booking)
        booking_out["status"] = booking.get("status") or "sent"
        booking_out["submitted_at"] = booking.get("submitted_at")
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
        "booking": booking_out,
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
            "engineers": ([{"name": av.get("engineer"), "dob": "", "veh_reg": ""}]
                          if av.get("engineer") else []),
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

async def _find_booking(token: str) -> dict:
    """Locate a booking by token across both sources: contract annual visits
    (mod_service_contracts.annual_visit.booking) and MOD faults (issues.mod_booking)."""
    c = await db.mod_service_contracts.find_one(
        {"annual_visit.booking.token": token}, {"_id": 0})
    if c:
        av = c.get("annual_visit") or {}
        return {"source": "contract_visit", "doc": c, "booking": av.get("booking") or {},
                "ref_id": c.get("id"), "organization_id": c.get("organization_id"),
                "site_id": c.get("mod_site_id"), "site_name": c.get("mod_site_name"),
                "visit_date": av.get("scheduled_date") or av.get("proposed_date"),
                "reference": c.get("quote_number")}
    i = await db.issues.find_one({"mod_booking.token": token}, {"_id": 0})
    if i:
        b = i.get("mod_booking") or {}
        return {"source": "fault", "doc": i, "booking": b,
                "ref_id": i.get("id"), "organization_id": i.get("organization_id"),
                "site_id": i.get("mod_site_id") or i.get("organization_id"),
                "site_name": b.get("site_name") or "",
                "visit_date": b.get("visit_start_date") or "",
                "reference": i.get("mod_ticket_ref")}
    raise HTTPException(404, "Booking form not found or expired")


async def _persist_booking(handle: dict, booking: dict) -> None:
    if handle["source"] == "contract_visit":
        av = handle["doc"].get("annual_visit") or {}
        av["booking"] = booking
        await db.mod_service_contracts.update_one(
            {"id": handle["ref_id"]}, {"$set": {"annual_visit": av, "updated_at": _now()}})
    else:
        await db.issues.update_one(
            {"id": handle["ref_id"]}, {"$set": {"mod_booking": booking, "updated_at": _now()}})


def _public_booking_view(handle: dict) -> dict:
    b = handle["booking"]
    return {
        "site_name": handle["site_name"],
        "visit_scheduled_date": handle["visit_date"],
        "reference": handle.get("reference"),
        "source": handle["source"],
        "status": b.get("status") or "sent",
        "submitted_at": b.get("submitted_at"),
        "form": {**{k: b.get(k, "") for k in BOOKING_FIELDS},
                 "engineers": _engineers_list(b)},
    }


# ── Sicon Service / Contract / Appointment sync (queues; simulates until
#    live Sicon credentials are supplied, then posts for real) ───────

def _visit_datetimes(visit_date: str, booking: dict) -> tuple:
    start = booking.get("visit_start_date") or visit_date or ""
    end = booking.get("visit_end_date") or start
    stime = booking.get("visit_start_time") or "09:00"
    etime = booking.get("visit_end_time") or "17:00"
    return (f"{start}T{stime}" if start else None, f"{end}T{etime}" if end else None)


def _booking_notes(booking: dict) -> str:
    lines = []
    engs = _engineers_list(booking)
    for idx, e in enumerate(engs, 1):
        label = f"Engineer {idx}" if len(engs) > 1 else "Engineer/visitor"
        lines.append(f"{label}: {e.get('name') or '—'} · DOB {e.get('dob') or '—'} · Vehicle {e.get('veh_reg') or '—'}")
    if booking.get("mod_contact_name"):
        lines.append(f"MOD contact: {booking['mod_contact_name']} · {booking.get('mod_contact_phone') or booking.get('mod_contact_email') or ''}")
    return "\n".join(lines)


async def enqueue_contract_visit_sicon(contract: dict) -> None:
    """Push a Sicon Service Call + engineer Appointment for a MOD annual visit,
    linked to the Type A Contract. Idempotent (stable OurReference)."""
    from routes.svc.integrations.sicon_sync import push_mod_service_call, push_mod_appointment
    av = contract.get("annual_visit") or {}
    booking = av.get("booking") or {}
    visit_date = av.get("scheduled_date") or av.get("proposed_date")
    start_dt, end_dt = _visit_datetimes(visit_date, booking)
    org = contract.get("organization_id")
    cid = contract.get("id")
    call_ref = contract.get("quote_number") or f"MODV-{str(cid)[:8]}"
    await push_mod_service_call(organization_id=org, payload={
        "OurReference": f"modvisit-case-{cid}",
        "CallReference": call_ref,
        "Description": f"MOD annual service visit — {contract.get('mod_site_name') or ''}"[:80],
        "Notes": _booking_notes(booking),
        "StatusID": "Logged", "CallTypeID": "contract", "JobTypeID": "service",
        "ContractID": contract.get("sicon_contract_id") or contract.get("contract_number") or cid,
        "SubLocation": {"SiconSubLocationID": contract.get("mod_site_id"),
                        "Description": contract.get("mod_site_name") or ""},
        "ContactName": booking.get("mod_contact_name") or "",
        "ContactEmail": booking.get("mod_contact_email") or "",
        "ContactPhone": booking.get("mod_contact_phone") or "",
        "ScheduledDateTime": start_dt, "LoggedDateTime": _now(),
        "LoggedByMethod": "mod_visit_calendar",
    })
    await push_mod_appointment(organization_id=org, payload={
        "OurReference": f"modvisit-appt-{cid}",
        "ServiceCallReference": call_ref,
        "ResourceID": av.get("engineer") or booking.get("engineer_name") or "",
        "StartDateTime": start_dt, "EndDateTime": end_dt,
        "AppointmentTypeID": "on_site", "Notes": _booking_notes(booking),
    })


async def enqueue_fault_visit_sicon(issue: dict) -> None:
    """Push a Sicon Service Call + Appointment for a MOD engineer-callout fault."""
    from routes.svc.integrations.sicon_sync import push_mod_service_call, push_mod_appointment
    booking = issue.get("mod_booking") or {}
    start_dt, end_dt = _visit_datetimes("", booking)
    org = issue.get("organization_id")
    iid = issue.get("id")
    call_ref = issue.get("mod_ticket_ref") or f"MODF-{str(iid)[:8]}"
    await push_mod_service_call(organization_id=org, payload={
        "OurReference": f"modfault-case-{iid}",
        "CallReference": call_ref,
        "Description": f"MOD engineer callout — {issue.get('machine_type') or 'equipment'}"[:80],
        "Notes": (issue.get("issue_description") or "") + ("\n\n" + _booking_notes(booking) if _booking_notes(booking) else ""),
        "StatusID": "Logged", "CallTypeID": "callout", "JobTypeID": "repair",
        "SubLocation": {"SiconSubLocationID": issue.get("mod_site_id"),
                        "Description": booking.get("site_name") or ""},
        "ContactName": booking.get("mod_contact_name") or issue.get("reporter_name") or "",
        "ContactEmail": booking.get("mod_contact_email") or issue.get("reporter_email") or "",
        "ContactPhone": booking.get("mod_contact_phone") or issue.get("reporter_phone") or "",
        "ScheduledDateTime": start_dt, "LoggedDateTime": _now(),
        "LoggedByMethod": "mod_fault_callout",
    })
    await push_mod_appointment(organization_id=org, payload={
        "OurReference": f"modfault-appt-{iid}",
        "ServiceCallReference": call_ref,
        "ResourceID": booking.get("engineer_name") or "",
        "StartDateTime": start_dt, "EndDateTime": end_dt,
        "AppointmentTypeID": "on_site", "Notes": _booking_notes(booking),
    })


async def make_fault_booking(issue_id: str) -> dict | None:
    """Create an Engineer Appointment Booking form for a MOD engineer-callout
    fault (idempotent). Stored on issues.mod_booking; the site fills it via the
    same /mod-booking/:token page and its details surface on the fault card."""
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not issue:
        return None
    if (issue.get("mod_booking") or {}).get("token"):
        return issue["mod_booking"]
    org = await db.organizations.find_one(
        {"id": issue.get("mod_site_id") or issue.get("organization_id")}, {"_id": 0, "name": 1}) or {}
    booking = {k: "" for k in BOOKING_FIELDS}
    booking.update({
        "token": secrets.token_urlsafe(24), "status": "sent",
        "site_name": org.get("name") or "", "kind": "fault",
        "engineers": [],
        "requested_by_name": "Pulse Fitness Service", "requested_by_email": "",
        "mod_contact_name": issue.get("reporter_name") or "",
        "mod_contact_email": issue.get("reporter_email") or "",
        "mod_contact_phone": issue.get("reporter_phone") or "",
        "created_at": _now(), "updated_at": _now(), "sent_at": _now(),
    })
    await db.issues.update_one({"id": issue_id}, {"$set": {"mod_booking": booking}})
    return booking


@public_router.get("/{token}")
async def public_get_booking(token: str, request: Request) -> dict:
    from utils.security_plus import rate_limit_async
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"mod_booking_ip:{ip}", max_requests=60, window_seconds=300)
    return _public_booking_view(await _find_booking(token))


@public_router.put("/{token}")
async def public_save_booking(token: str, body: dict = Body(...)) -> dict:
    handle = await _find_booking(token)
    booking = handle["booking"]
    if booking.get("status") == "submitted":
        raise HTTPException(409, "This booking form has already been submitted.")
    form = body.get("form") or {}
    for k in BOOKING_FIELDS:
        if k in form:
            booking[k] = form.get(k).strip() if isinstance(form.get(k), str) else form.get(k)
    if "engineers" in form:
        booking["engineers"] = _clean_engineers(form.get("engineers"))
        _sync_legacy_engineer(booking)
    booking["status"] = "draft" if booking.get("status") in (None, "sent") else booking["status"]
    booking["updated_at"] = _now()
    await _persist_booking(handle, booking)
    return _public_booking_view(await _find_booking(token))


@public_router.post("/{token}/submit")
async def public_submit_booking(token: str, body: dict = Body(default={})) -> dict:
    handle = await _find_booking(token)
    booking = handle["booking"]
    if booking.get("status") == "submitted":
        raise HTTPException(409, "This booking form has already been submitted.")
    form = body.get("form") or {}
    for k in BOOKING_FIELDS:
        if k in form:
            booking[k] = form.get(k).strip() if isinstance(form.get(k), str) else form.get(k)
    if "engineers" in form:
        booking["engineers"] = _clean_engineers(form.get("engineers"))
        _sync_legacy_engineer(booking)
    if not (booking.get("mod_contact_name") and booking.get("mod_contact_email")):
        raise HTTPException(400, "Please provide the MOD contact name and email before submitting.")
    booking["status"] = "submitted"
    booking["submitted_at"] = _now()
    booking["updated_at"] = _now()
    await _persist_booking(handle, booking)

    # Notify the MOD Service team.
    try:
        from utils.email import send_email
        team = os.environ.get("MOD_READINESS_HQ_EMAIL") or "modservice@pulsefitness.com"
        label = "engineer callout" if handle["source"] == "fault" else "annual service visit"
        engs = _engineers_list(booking)
        if engs:
            eng_rows = "".join(
                f"<li>{(e.get('name') or '—')} · DOB {(e.get('dob') or '—')} · Vehicle reg {(e.get('veh_reg') or '—')}</li>"
                for e in engs)
            eng_html = f"<p><b>Visiting engineer(s):</b></p><ul>{eng_rows}</ul>"
        else:
            eng_html = "<p>Engineer: —</p>"
        html = (f"<p>The Engineer Appointment Booking form for the {label} at "
                f"<b>{handle['site_name']}</b> ({handle.get('reference') or ''}) has been completed.</p>"
                f"<p>Contact: {booking.get('mod_contact_name')} · {booking.get('mod_contact_email')} · "
                f"{booking.get('mod_contact_phone') or '—'}</p>"
                f"{eng_html}"
                f"<p>Visit: {booking.get('visit_start_date') or '—'} {booking.get('visit_start_time') or ''}</p>")
        await send_email(team, f"MOD booking completed — {handle['site_name']}", html, category="support")
    except Exception:
        pass

    # Sync to Sicon (Service Call + engineer Appointment; queues + simulates
    # until live credentials are provided).
    try:
        fresh = await _find_booking(token)
        if fresh["source"] == "contract_visit":
            await enqueue_contract_visit_sicon(fresh["doc"])
        else:
            await enqueue_fault_visit_sicon(fresh["doc"])
    except Exception:
        logger.exception("[mod-booking] Sicon enqueue failed on submit")

    return _public_booking_view(await _find_booking(token))


__all__ = ["router", "public_router", "enqueue_contract_visit_sicon",
           "enqueue_fault_visit_sicon", "make_fault_booking"]
