"""
GymAxis Service Operations — Public Customer Tracking.

Iter 216h83 — "Uber-style" tracking page for customers.

A tokenised, public URL like:

    /track/<opaque-token>

shows the customer a friendly live view of their service case:
status (Assigned → En route → On site → Closed), an ETA hint, the
engineer's first name and skills, and the most recent timeline event.

Endpoints:

    GET  /svc/public/track/{token}                       (public, polled every ~30s)
    GET  /svc/cases/{case_id}/tracking-link              (operator, lazy-mints token)
    POST /svc/cases/{case_id}/tracking-link/regenerate   (operator)

Tokens are generated lazily with `secrets.token_urlsafe(18)` and stored
on the case as `track_token`. Regeneration invalidates the previous
link.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _public_status_meta(status: str) -> dict:
    """Map the internal state machine to customer-friendly copy."""
    return {
        "new":               {"label": "Logged",         "stage": 1, "tone": "info",    "blurb": "We've received the request — our team is reviewing it."},
        "triaged":           {"label": "Triaged",        "stage": 1, "tone": "info",    "blurb": "Triaged and ready to assign."},
        "assigned":          {"label": "Assigned",       "stage": 2, "tone": "info",    "blurb": "An engineer has been assigned and will set off shortly."},
        "en_route":          {"label": "On the way",     "stage": 3, "tone": "active",  "blurb": "Your engineer is on the way."},
        "on_site":           {"label": "On site",        "stage": 4, "tone": "active",  "blurb": "Your engineer is on site working on the issue."},
        "paused_parts":      {"label": "Awaiting parts", "stage": 4, "tone": "warn",    "blurb": "Paused while a part is sourced. We'll be back as soon as it lands."},
        "paused_customer":   {"label": "Awaiting you",   "stage": 4, "tone": "warn",    "blurb": "Paused — we need a quick decision or access from your side."},
        "repaired":          {"label": "Repaired",       "stage": 5, "tone": "success", "blurb": "Repair complete — wrapping up."},
        "awaiting_sign_off": {"label": "Ready to sign off", "stage": 5, "tone": "success", "blurb": "Job done — ready for your sign-off."},
        "closed":            {"label": "Complete",       "stage": 6, "tone": "success", "blurb": "All sorted. Thanks for using us."},
        "invoiced":          {"label": "Complete",       "stage": 6, "tone": "success", "blurb": "All sorted. Thanks for using us."},
    }.get(status, {"label": status.replace("_", " ").title(), "stage": 1, "tone": "info", "blurb": ""})


def _engineer_card(engineer: dict | None) -> dict | None:
    if not engineer:
        return None
    full_name = engineer.get("full_name") or engineer.get("email") or ""
    first = full_name.split()[0] if full_name else "Your engineer"
    skills = engineer.get("skills") or []
    return {
        "first_name": first,
        "skills": skills[:4],
        "vehicle_reg": engineer.get("vehicle_reg") or "",
    }


def _origin(request: Request) -> str:
    """Best-effort public origin for the share URL."""
    import os
    env = (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    if env:
        return env
    # Fall back to request host (preview).
    host = request.headers.get("x-forwarded-host") or request.url.hostname or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    return f"{proto}://{host}".rstrip("/")


async def _mint_or_get_token(case_id: str, of: dict) -> str:
    """Return the case's tracking token, generating one if missing."""
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "track_token": 1})
    if case is None:
        raise HTTPException(404, "Case not found")
    token = case.get("track_token")
    if token:
        return token
    token = secrets.token_urlsafe(18)
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {"track_token": token, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return token


# ── Public tracking endpoint ───────────────────────────────────

@router.get("/svc/public/track/{token}")
async def public_track(token: str):
    """Customer-facing live tracking view. No auth — token IS the gate."""
    if not token or len(token) < 8:
        raise HTTPException(404, "Tracking link not found")
    case = await db.svc_cases.find_one(
        {"track_token": token},
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1,
            "priority": 1, "site_name": 1, "site_postcode": 1, "site_address": 1,
            "asset_name": 1, "scheduled_at": 1, "sla_resolve_at": 1,
            "assigned_engineer_id": 1, "closed_at": 1, "updated_at": 1,
            "customer_rating": 1, "customer_name": 1, "organization_id": 1,
            "service_report_sent_at": 1,
        },
    )
    if not case:
        raise HTTPException(404, "Tracking link not found")
    # Resolve engineer (public-safe fields only).
    engineer = None
    if case.get("assigned_engineer_id"):
        engineer = await db.svc_engineers.find_one(
            {"id": case["assigned_engineer_id"]},
            {"_id": 0, "full_name": 1, "skills": 1, "vehicle_reg": 1, "email": 1},
        )
    # Most recent customer-visible event for the timeline.
    last_events = (
        await db.svc_case_events.find(
            {"case_id": case["id"]},
            {"_id": 0, "type": 1, "body": 1, "at": 1, "extra": 1},
        ).sort("at", -1).limit(5).to_list(5)
    )
    customer_safe_events = []
    for ev in last_events:
        # Strip internal-only events.
        if ev.get("type") in ("internal_note", "audit"):
            continue
        if (ev.get("extra") or {}).get("visibility") == "internal":
            continue
        customer_safe_events.append({
            "type": ev.get("type"),
            "at": ev.get("at"),
            "body": (ev.get("body") or "")[:240],
        })

    org = await db.organizations.find_one(
        {"id": case.get("organization_id")},
        {"_id": 0, "name": 1, "brand_primary_color": 1, "brand_kit": 1, "logo_url": 1},
    ) or {}
    brand_primary = (
        org.get("brand_primary_color")
        or (org.get("brand_kit") or {}).get("primary_color")
        or "#0055FF"
    )

    status = case.get("status") or "new"
    meta = _public_status_meta(status)
    customer_first = (case.get("customer_name") or "").split()[0] if case.get("customer_name") else ""

    return {
        "reference": case.get("reference") or case["id"][:8],
        "title": case.get("title") or "Service visit",
        "asset_name": case.get("asset_name"),
        "site": {
            "name": case.get("site_name"),
            "address": case.get("site_address"),
            "postcode": case.get("site_postcode"),
        },
        "status": status,
        "status_label": meta["label"],
        "status_stage": meta["stage"],
        "status_tone": meta["tone"],
        "status_blurb": meta["blurb"],
        "is_complete": status in ("closed", "invoiced"),
        "scheduled_at": case.get("scheduled_at"),
        "sla_resolve_at": case.get("sla_resolve_at"),
        "closed_at": case.get("closed_at"),
        "updated_at": case.get("updated_at"),
        "engineer": _engineer_card(engineer),
        "events": customer_safe_events,
        "rating_captured": bool(case.get("customer_rating")),
        "report_sent": bool(case.get("service_report_sent_at")),
        "customer_first_name": customer_first,
        "organization": {
            "name": org.get("name") or "Your service team",
            "logo_url": org.get("logo_url") or "",
            "brand_primary": brand_primary,
        },
        # Stages used to render the progress bar
        "stages": [
            {"key": "assigned", "label": "Assigned"},
            {"key": "en_route", "label": "On the way"},
            {"key": "on_site",  "label": "On site"},
            {"key": "complete", "label": "Complete"},
        ],
    }


# ── Operator helpers ──────────────────────────────────────────

@router.get("/svc/cases/{case_id}/tracking-link")
async def get_tracking_link(case_id: str, request: Request, user=Depends(get_current_user)):
    """Return the customer-shareable tracking URL for a case.

    Lazily mints a token the first time it's requested.
    """
    of = _of(user)
    token = await _mint_or_get_token(case_id, of)
    url = f"{_origin(request)}/track/{token}"
    return {"token": token, "url": url}


@router.post("/svc/cases/{case_id}/tracking-link/regenerate")
async def regenerate_tracking_link(case_id: str, request: Request, user=Depends(get_current_user)):
    """Force-mint a fresh token, invalidating any older link."""
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(404, "Case not found")
    token = secrets.token_urlsafe(18)
    await db.svc_cases.update_one(
        {"id": case_id, **of},
        {"$set": {"track_token": token, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"token": token, "url": f"{_origin(request)}/track/{token}"}


__all__ = ["router"]
