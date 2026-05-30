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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Used for an Uber-style ETA estimate."""
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def _engineer_live_location(case: dict) -> dict | None:
    """Return the engineer's location ping if (a) the case is en_route/on_site,
    (b) the ping is < 5 minutes old, and (c) the engineer is the assigned one.

    NEVER returns the lat/lng to the public payload unless those checks pass.
    """
    if case.get("status") not in ("en_route", "on_site"):
        return None
    eng_id = case.get("assigned_engineer_id")
    if not eng_id:
        return None
    doc = await db.svc_engineer_locations.find_one(
        {"engineer_id": eng_id}, {"_id": 0, "lat": 1, "lng": 1, "recorded_at": 1, "accuracy_m": 1},
    )
    if not doc or not doc.get("recorded_at"):
        return None
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    try:
        recorded = _dt.fromisoformat(doc["recorded_at"].replace("Z", "+00:00"))
    except Exception:
        return None
    if _dt.now(_tz.utc) - recorded > _td(minutes=5):
        return None
    return {
        "lat": doc["lat"],
        "lng": doc["lng"],
        "recorded_at": doc["recorded_at"],
        "accuracy_m": doc.get("accuracy_m"),
    }


def _eta_from_distance_km(km: float) -> dict:
    """Convert km distance to friendly ETA string. 35 km/h urban avg."""
    if km is None or km < 0:
        return {"minutes": None, "label": None}
    mins = max(1, int(round(km / 35.0 * 60)))
    if mins < 60:
        label = f"~{mins} min away"
    else:
        h, m = divmod(mins, 60)
        label = f"~{h}h {m}m away"
    return {"minutes": mins, "label": label, "distance_km": round(km, 1)}


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


def _engineer_card(engineer: dict | None, stats: dict | None = None) -> dict | None:
    if not engineer:
        return None
    full_name = engineer.get("full_name") or engineer.get("email") or ""
    first = full_name.split()[0] if full_name else "Your engineer"
    skills = engineer.get("skills") or []
    qualifications = engineer.get("qualifications") or []
    card = {
        "first_name": first,
        "skills": skills[:6],
        "qualifications": qualifications[:4],
        "vehicle_reg": engineer.get("vehicle_reg") or "",
        "photo_url": engineer.get("photo_url") or "",
        "verified": bool(engineer.get("verified")),
    }
    if stats:
        card.update({
            "jobs_completed_90d": int(stats.get("jobs_completed_90d") or 0),
            "avg_rating": stats.get("avg_rating"),
            "ratings_count": int(stats.get("ratings_count") or 0),
        })
    if engineer.get("years_experience"):
        card["years_experience"] = int(engineer["years_experience"])
    return card


async def _engineer_public_stats(engineer_id: str, org_id: str | None) -> dict:
    """Lightweight, brand-safe stats for the tracking card.

    Works for BOTH internal engineers AND partner engineers — pulls from
    `svc_cases` only (no commercial fields). Returns 90-day closed job
    count and average customer rating across those rows.
    """
    from datetime import timedelta
    if not engineer_id:
        return {}
    window_start = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    base = {"assigned_engineer_id": engineer_id, "status": {"$in": ["closed", "invoiced"]}}
    if org_id:
        base["organization_id"] = org_id
    jobs_90d = await db.svc_cases.count_documents(
        {**base, "closed_at": {"$gte": window_start}},
    )
    pipeline = [
        {"$match": {**base, "customer_rating": {"$gte": 1}}},
        {"$group": {"_id": None, "avg": {"$avg": "$customer_rating"},
                    "n": {"$sum": 1}}},
    ]
    agg = await db.svc_cases.aggregate(pipeline).to_list(1)
    avg = round(float(agg[0]["avg"]), 2) if agg else None
    n = int(agg[0]["n"]) if agg else 0
    return {
        "jobs_completed_90d": jobs_90d,
        "avg_rating": avg,
        "ratings_count": n,
    }


async def _public_compliance_summary(case: dict) -> dict:
    """Customer-safe compliance status for the tracking page.

    Mirrors the PDF evidence pack (Iter 220dj) but trimmed for the
    public surface — we expose **whether** evidence was captured,
    not the operator's internal step labels or notes. Three chips:

      * ``ptw``    — issued / completed permits-to-work for this case.
      * ``loto``   — lockout/tagout signoffs.
      * ``coshh``  — chemical-usage logs.

    Each kind returns ``{state: 'none'|'in_progress'|'done', count,
    label}`` so the frontend can render an empty/amber/emerald chip
    without per-row leakage.
    """
    of = {"organization_id": case.get("organization_id")}
    case_id = case.get("id")
    if not case_id or not of["organization_id"]:
        return {"ptw": None, "loto": None, "coshh": None}

    ptw_rows = await db.svc_ptw_requests.find(
        {"case_id": case_id, **of}, {"_id": 0, "status": 1},
    ).to_list(20)
    ptw_done = sum(1 for r in ptw_rows if r.get("status") == "completed")
    ptw_active = sum(1 for r in ptw_rows if r.get("status") == "issued")

    loto_count = await db.svc_loto_checklists.count_documents(
        {"case_id": case_id, **of},
    )
    coshh_count = await db.svc_coshh_usage.count_documents(
        {"case_id": case_id, **of},
    )

    def _state(count: int) -> str:
        if count <= 0:
            return "none"
        return "done"

    ptw_state = (
        "done" if ptw_done > 0 else
        "in_progress" if ptw_active > 0 else
        "none"
    )
    return {
        "ptw": {
            "state": ptw_state,
            "count": ptw_done + ptw_active,
            "label": (
                f"{ptw_done} permit{'s' if ptw_done != 1 else ''} completed"
                if ptw_done > 0 else
                f"{ptw_active} permit{'s' if ptw_active != 1 else ''} in force"
                if ptw_active > 0 else "No permits required"
            ),
        },
        "loto": {
            "state": _state(loto_count),
            "count": loto_count,
            "label": (
                f"{loto_count} isolation signoff{'s' if loto_count != 1 else ''}"
                if loto_count > 0 else "Not isolated"
            ),
        },
        "coshh": {
            "state": _state(coshh_count),
            "count": coshh_count,
            "label": (
                f"{coshh_count} chemical log{'s' if coshh_count != 1 else ''}"
                if coshh_count > 0 else "No chemicals logged"
            ),
        },
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
            "customer_feedback_at": 1,
            "site_lat": 1, "site_lng": 1, "latitude": 1, "longitude": 1,
        },
    )
    if not case:
        raise HTTPException(404, "Tracking link not found")
    # Resolve engineer (public-safe fields only).
    engineer = None
    engineer_stats: dict = {}
    if case.get("assigned_engineer_id"):
        engineer = await db.svc_engineers.find_one(
            {"id": case["assigned_engineer_id"]},
            {"_id": 0, "full_name": 1, "skills": 1, "vehicle_reg": 1, "email": 1,
             "photo_url": 1, "qualifications": 1, "verified": 1, "id": 1,
             "years_experience": 1},
        )
        engineer_stats = await _engineer_public_stats(
            case["assigned_engineer_id"], case.get("organization_id"),
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

    # Iter 216h91 — Live tracking position + ETA (en_route / on_site only).
    eng_location = await _engineer_live_location(case)
    eta = None
    site_lat = case.get("site_lat") or case.get("latitude")
    site_lng = case.get("site_lng") or case.get("longitude")
    if eng_location and site_lat is not None and site_lng is not None:
        try:
            dist = _haversine_km(eng_location["lat"], eng_location["lng"], float(site_lat), float(site_lng))
            eta = _eta_from_distance_km(dist)
        except (TypeError, ValueError):
            eta = None

    # Iter 220dl — Live compliance chips for the customer.
    # Mirrors the PDF compliance evidence pack (Iter 220dj) so the
    # customer can see safety/regulatory work landing in real time
    # rather than waiting for the post-visit report.
    compliance = await _public_compliance_summary(case)

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
        "engineer": _engineer_card(engineer, engineer_stats),
        "engineer_location": eng_location,
        "site_location": (
            {"lat": float(site_lat), "lng": float(site_lng)}
            if site_lat is not None and site_lng is not None else None
        ),
        "eta": eta,
        "compliance": compliance,
        "events": customer_safe_events,
        "rating_captured": bool(case.get("customer_rating")),
        "feedback_captured": bool(case.get("customer_feedback_at")),
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


@router.post("/svc/public/track/{token}/feedback")
async def public_feedback(token: str, body: dict | None = None):
    """Capture customer feedback from the public tracking page.

    Body: {
        rating: int (1-5, optional — re-confirm star rating),
        nps_score: int (0-10, optional),
        comment: str (free text, max 1500 chars, optional),
    }

    Idempotent: subsequent POSTs replace prior NPS/comment for the same
    case. Stored on the case so the operator can see it on the drawer
    and roll into reporting.
    """
    if not token or len(token) < 8:
        raise HTTPException(404, "Tracking link not found")
    case = await db.svc_cases.find_one(
        {"track_token": token},
        {"_id": 0, "id": 1, "organization_id": 1, "status": 1},
    )
    if not case:
        raise HTTPException(404, "Tracking link not found")
    body = body or {}

    update: dict = {"customer_feedback_at": datetime.now(timezone.utc).isoformat()}
    if (rating := body.get("rating")) is not None:
        try:
            rating = int(rating)
            assert 1 <= rating <= 5
            update["customer_rating"] = rating
        except (TypeError, ValueError, AssertionError):
            raise HTTPException(400, "rating must be an integer 1-5")
    if (nps := body.get("nps_score")) is not None:
        try:
            nps = int(nps)
            assert 0 <= nps <= 10
            update["customer_nps"] = nps
        except (TypeError, ValueError, AssertionError):
            raise HTTPException(400, "nps_score must be an integer 0-10")
    comment = (body.get("comment") or "").strip()
    if comment:
        update["customer_rating_comment"] = comment[:1500]

    if len(update) == 1:
        raise HTTPException(400, "Please leave a rating, NPS score or a comment.")

    await db.svc_cases.update_one(
        {"track_token": token},
        {"$set": {**update, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "captured_at": update["customer_feedback_at"]}


# ── Iter 220l — Customer "Request this engineer again" CTA ────
#
# Lets a happy customer flag the engineer who serviced their last
# visit as their preferred engineer for next time. Creates a row
# in `svc_engineer_preferences` so the dispatch admin can see the
# request on the org dashboard + (best-effort) emails the engineer
# so they can reach out personally.

@router.post("/svc/public/track/{token}/preferred-engineer")
async def public_request_preferred_engineer(token: str, body: dict | None = None):
    """Customer-side CTA — no auth, token is the gate. Idempotent on
    `(track_token, engineer_id)` so a customer can't spam-create rows."""
    if not token or len(token) < 8:
        raise HTTPException(404, "Tracking link not found")
    case = await db.svc_cases.find_one(
        {"track_token": token},
        {
            "_id": 0, "id": 1, "reference": 1,
            "assigned_engineer_id": 1, "assigned_engineer_name": 1,
            "customer_name": 1, "customer_email": 1, "customer_phone": 1,
            "organization_id": 1,
        },
    )
    if not case:
        raise HTTPException(404, "Tracking link not found")
    eng_id = case.get("assigned_engineer_id")
    if not eng_id:
        raise HTTPException(409, "No engineer attached to this case to request.")

    body = body or {}
    note = (body.get("note") or "").strip()[:500]

    pref_doc = {
        "track_token": token,
        "case_id": case["id"],
        "case_reference": case.get("reference"),
        "engineer_id": eng_id,
        "engineer_name": case.get("assigned_engineer_name"),
        "customer_name": case.get("customer_name"),
        "customer_email": case.get("customer_email"),
        "customer_phone": case.get("customer_phone"),
        "organization_id": case.get("organization_id"),
        "note": note,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }
    # Idempotent upsert by (track_token, engineer_id) — repeated
    # taps from the same customer just refresh the timestamp.
    await db.svc_engineer_preferences.update_one(
        {"track_token": token, "engineer_id": eng_id},
        {"$set": pref_doc},
        upsert=True,
    )

    # Best-effort notify the engineer.
    try:
        engineer = await db.users.find_one({"id": eng_id}, {"_id": 0, "email": 1, "full_name": 1})
        if engineer and engineer.get("email"):
            from utils.email import send_email
            customer = case.get("customer_name") or "A customer"
            ref = case.get("reference") or case["id"][:8]
            note_html = (
                f'<blockquote style="border-left:3px solid #6366f1;padding:6px 12px;'
                f'background:#f5f3ff;color:#475569;margin:14px 0;">{note}</blockquote>'
                if note else ""
            )
            html = (
                f"<p>Great news — <b>{customer}</b> just requested that you handle their next "
                f"job on case <b>{ref}</b>.</p>"
                f"{note_html}"
                f"<p>You'll automatically appear at the top of their dispatch shortlist next time.</p>"
            )
            await send_email(
                to=engineer["email"],
                subject="A customer asked for you again",
                html=html,
                organization_id=case.get("organization_id"),
            )
    except Exception:
        pass

    return {"ok": True, "requested_at": pref_doc["requested_at"]}


__all__ = ["router"]
