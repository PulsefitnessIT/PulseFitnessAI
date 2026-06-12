"""GymAxis Service Operations — Engineer outbound ETA push (Iter 220dg).

Inbound: customer already has a public live-tracking page that polls
every 30 seconds. Outbound: when the engineer hits "on the way" we
auto-email the customer (via ``auto_notify_on_transition``), and the
engineer can manually fire a fresh "ETA update" email at any time
while ``en_route`` (e.g. running 10 min late, traffic, picked up the
wrong tool first).

This module owns:
  * ``POST /api/svc/engineer/jobs/{case_id}/eta-update`` — manual nudge
    with a minute-offset, optional free-text. Sends a fresh email
    using the ``engineer_en_route`` template, attaches the live
    tracking URL, and logs the comm + case event.
  * Helpers ``build_eta_minutes_estimate`` and
    ``build_tracking_url_for_case`` used by both this endpoint AND
    ``auto_notify_on_transition`` so the auto-comm + manual nudge
    render the same data.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


# ─────────────────────────────────────────────────────────────────
# Tracking URL helper
# ─────────────────────────────────────────────────────────────────
# Mints (or returns) the case's public tracking token then composes
# the FRONTEND_URL-relative path /track/{token}. Used by:
#   * auto_notify_on_transition (en_route email)
#   * the manual ETA-update endpoint below
#   * future SMS templating


async def build_tracking_url_for_case(case: dict) -> Optional[str]:
    """Return the public tracking URL for ``case``. Lazy-mints the
    token if missing. Returns ``None`` only if we have no
    organization_id, no case_id, or FRONTEND_URL is unset.
    """
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not base:
        return None
    case_id = case.get("id")
    org_id = case.get("organization_id")
    if not case_id or not org_id:
        return None
    token = case.get("track_token")
    if not token:
        token = secrets.token_urlsafe(18)
        await db.svc_cases.update_one(
            {"id": case_id, "organization_id": org_id},
            {"$set": {"track_token": token, "updated_at": _now()}},
        )
    return f"{base}/track/{token}"


# ─────────────────────────────────────────────────────────────────
# ETA estimation
# ─────────────────────────────────────────────────────────────────
# We re-use the public_tracking haversine + 35 km/h urban average.
# Helpers here are duplicated only to avoid a circular import
# (public_tracking imports comms, comms would import this).


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def build_eta_minutes_estimate(case: dict) -> Optional[int]:
    """Best-effort ETA in minutes for ``case`` based on the latest
    engineer-location ping. Returns ``None`` when:
      * the case isn't currently en_route
      * no engineer assigned
      * no recent ping (< 5 min)
      * we don't have site lat/lng
    """
    if case.get("status") != "en_route":
        return None
    eng_id = case.get("assigned_engineer_id")
    if not eng_id:
        return None
    ping = await db.svc_engineer_locations.find_one(
        {"engineer_id": eng_id},
        {"_id": 0, "lat": 1, "lng": 1, "recorded_at": 1},
    )
    if not ping or not ping.get("recorded_at"):
        return None
    try:
        recorded = datetime.fromisoformat(ping["recorded_at"].replace("Z", "+00:00"))
    except Exception:
        return None
    if (datetime.now(timezone.utc) - recorded).total_seconds() > 300:
        return None
    site_lat = case.get("site_lat") or case.get("latitude")
    site_lng = case.get("site_lng") or case.get("longitude")
    if site_lat is None or site_lng is None:
        return None
    try:
        km = _haversine_km(
            float(ping["lat"]), float(ping["lng"]),
            float(site_lat), float(site_lng),
        )
    except (TypeError, ValueError):
        return None
    return max(1, int(round(km / 35.0 * 60)))


def eta_label_from_minutes(mins: Optional[int]) -> str:
    """Customer-friendly ETA phrase. ``None`` collapses to ``"shortly"``
    so the email template still renders cleanly."""
    if mins is None or mins <= 0:
        return "shortly"
    if mins < 60:
        return f"in about {mins} minute" + ("s" if mins != 1 else "")
    h, m = divmod(mins, 60)
    if m == 0:
        return f"in about {h} hour" + ("s" if h != 1 else "")
    return f"in about {h}h {m}m"


# ─────────────────────────────────────────────────────────────────
# Manual ETA-update endpoint
# ─────────────────────────────────────────────────────────────────


class EtaUpdateIn(BaseModel):
    eta_minutes: Optional[int] = Field(
        default=None, ge=0, le=480,
        description="Engineer-supplied ETA override in minutes. "
                    "If omitted, we use the live haversine estimate.",
    )
    message: Optional[str] = Field(
        default=None, max_length=400,
        description="Optional free-text shown to the customer "
                    "(e.g. 'Stuck behind a delivery van').",
    )


async def _send_eta_email(
    *, case: dict, user: dict, eta_mins: Optional[int],
    message: str = "", trigger: str = "manual_eta_update",
) -> dict:
    """Render + send a single ETA-update email for ``case``.

    Used by:
      * ``send_eta_update`` — engineer-driven manual nudge.
      * ``maybe_renotify_eta_drift`` — automatic drift re-notify
        triggered off a location-ping (Iter 220dk).

    Caller has already verified the case is in scope (valid status,
    has customer_email, comms not disabled). Returns the same
    response shape as the manual endpoint so the location-ping
    auditor can log it.
    """
    of = {"organization_id": case["organization_id"]}
    case_id = case["id"]
    to = (case.get("customer_email") or "").strip()
    tracking_url = await build_tracking_url_for_case(case) or ""

    from routes.svc.comms import (
        _ensure_defaults,
        _render,
        _log_send,
        _PRIORITY_LABEL,
    )
    from utils.email import send_email
    from utils.svc_state import append_event

    await _ensure_defaults(of)
    template = await db.svc_email_templates.find_one(
        {**of, "key": "engineer_en_route"}, {"_id": 0},
    )
    if not template or template.get("active") is False:
        return {"ok": False, "reason": "template_inactive"}

    msg = (message or "").strip()
    ctx = {
        **case,
        "priority_label": _PRIORITY_LABEL.get(case.get("priority", "p3"), case.get("priority", "p3")),
        "engineer_name": case.get("assigned_engineer_name") or user.get("full_name") or "Our engineer",
        "scheduled_label": case.get("scheduled_at") or "shortly",
        "eta_minutes": str(eta_mins) if eta_mins is not None else "",
        "eta_label": eta_label_from_minutes(eta_mins),
        "tracking_url": tracking_url,
        "engineer_message": msg,
        "engineer_message_html": (
            f'<p style="background:#fef3c7;border-left:3px solid #f59e0b;'
            f'padding:10px 14px;border-radius:6px">'
            f'<strong>From your engineer:</strong> {msg}'
            f'</p>'
        ) if msg else "",
        "tracking_link_html": (
            f'<p style="margin-top:12px"><a href="{tracking_url}" '
            f'style="background:#2563eb;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;font-weight:700">'
            f'Track live</a></p>'
        ) if tracking_url else "",
    }
    try:
        from routes.sites import _effective_site_branding
        org_doc = await db.organizations.find_one({"id": of["organization_id"]}, {"_id": 0}) or {}
        site_doc = None
        if case.get("site_id"):
            site_doc = await db.sites.find_one(
                {"id": case["site_id"], "organization_id": of["organization_id"]},
                {"_id": 0},
            )
        eff = _effective_site_branding(org_doc, site_doc)
        ctx["org_name"] = eff.get("name") or org_doc.get("name") or "GymAxis"
        ctx["brand_primary_color"] = eff.get("primary_color") or "#19CDFF"
    except Exception as exc:  # noqa: BLE001
        logger.warning("eta-update branding resolve failed: %s", exc)
        ctx.setdefault("org_name", "GymAxis")

    subject = _render(template["subject"], ctx)
    html = _render(template["body_html"], ctx)
    if tracking_url and tracking_url not in html:
        html += ctx["tracking_link_html"]

    try:
        ok = await send_email(to=to, subject=subject, html=html, category="service")
    except Exception as exc:  # pragma: no cover
        logger.warning("eta-update send failed for %s: %s", case_id, exc)
        ok = False

    log = await _log_send(
        of=of, kind="case_eta_update", to=to, subject=subject,
        template_key="engineer_en_route", ok=ok,
        error=None if ok else "send_email returned False",
        case_id=case_id, actor=user,
    )
    if ok:
        await append_event(
            case_id=case_id, organization_id=of["organization_id"],
            event_type="comm", actor=user,
            body=f"ETA update sent → {to} ({eta_label_from_minutes(eta_mins)})",
            extra={
                "template_key": "engineer_en_route",
                "to": to,
                "eta_minutes": eta_mins,
                "message": msg,
                "tracking_url": tracking_url,
                "log_id": log["id"],
                "trigger": trigger,
                "visibility": "internal",
            },
        )
        await db.svc_cases.update_one(
            {"id": case_id, **of},
            {"$set": {"eta_last_sent_at": _now(),
                      "eta_last_minutes": eta_mins,
                      "updated_at": _now()}},
        )
    return {
        "ok": ok,
        "to": to,
        "eta_minutes": eta_mins,
        "eta_label": eta_label_from_minutes(eta_mins),
        "tracking_url": tracking_url,
        "sent_at": _now() if ok else None,
    }


@router.post("/svc/engineer/jobs/{case_id}/eta-update")
async def send_eta_update(
    case_id: str, body: EtaUpdateIn, user=Depends(get_current_user),
):
    """Fire a fresh ETA-update email to the customer.

    Pre-conditions:
      * Case exists and the engineer is assigned (or user is admin).
      * Case has a ``customer_email``.
      * Case is in ``en_route`` (or ``assigned`` — early heads-up).
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    if not user.get("is_master_admin") and case.get("assigned_engineer_id") != user["id"]:
        raise HTTPException(403, "Only the assigned engineer can send an ETA update")
    if case.get("status") not in {"assigned", "en_route", "on_site"}:
        raise HTTPException(409, "ETA updates only apply while en route / on site")
    if case.get("comms_auto_notify") is False:
        raise HTTPException(409, "Customer comms are disabled on this case")
    to = (case.get("customer_email") or "").strip()
    if not to or "@" not in to:
        raise HTTPException(400, "Case has no customer_email")

    # ETA: engineer-supplied wins over the live estimate.
    eta_mins = body.eta_minutes
    if eta_mins is None:
        eta_mins = await build_eta_minutes_estimate(case)

    result = await _send_eta_email(
        case=case, user=user, eta_mins=eta_mins,
        message=(body.message or ""),
        trigger="manual_eta_update",
    )
    if result.get("reason") == "template_inactive":
        raise HTTPException(409, "engineer_en_route template inactive")
    return result


# ─────────────────────────────────────────────────────────────────
# Iter 220dk — Automatic ETA drift re-notify
# ─────────────────────────────────────────────────────────────────
# When an engineer pings their live location, we recompute the ETA
# for every ``en_route`` job they're currently driving to. If the
# ETA has drifted by ≥ ``DRIFT_THRESHOLD_MIN`` minutes since the
# last sent email AND the cooldown is respected, we send a fresh
# email so the customer isn't waiting in the dark wondering.
#
# Rate limits (anti-spam):
#   * 5 minutes between auto-renotifies on the same case.
#   * Skip when ``comms_auto_notify`` is False.
#   * Skip when customer_email missing.
#   * Skip when no recent location ping (helper already returns None).


DRIFT_THRESHOLD_MIN = 10
DRIFT_COOLDOWN_SECONDS = 300


def _seconds_since_iso(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds()


async def maybe_renotify_eta_drift(*, user: dict) -> list[dict]:
    """Inspect the calling engineer's open ``en_route`` cases and
    fire a fresh ETA-update email when ETA has drifted by at least
    ``DRIFT_THRESHOLD_MIN`` since the last sent value. Returns one
    result dict per case touched (empty list when nothing fired).
    """
    org_id = (user.get("organization_id") or user.get("service_org_id"))
    if not org_id:
        return []
    cases = await db.svc_cases.find(
        {
            "organization_id": org_id,
            "assigned_engineer_id": user["id"],
            "status": "en_route",
        },
        {"_id": 0},
    ).limit(5).to_list(5)
    results: list[dict] = []
    for case in cases:
        # Skip when customer comms disabled or no email.
        if case.get("comms_auto_notify") is False:
            continue
        to = (case.get("customer_email") or "").strip()
        if not to or "@" not in to:
            continue
        fresh = await build_eta_minutes_estimate(case)
        if fresh is None:
            continue
        last = case.get("eta_last_minutes")
        # First-time auto re-notify? Only fire when we already had a
        # baseline (otherwise the en_route auto-comm just went out).
        if last is None:
            continue
        if abs(int(fresh) - int(last)) < DRIFT_THRESHOLD_MIN:
            continue
        cooldown = _seconds_since_iso(case.get("eta_last_sent_at"))
        if cooldown is not None and cooldown < DRIFT_COOLDOWN_SECONDS:
            continue
        result = await _send_eta_email(
            case=case, user=user, eta_mins=fresh, message="",
            trigger="eta_drift_renotify",
        )
        results.append({"case_id": case["id"], **result})
    return results


__all__ = ["router", "build_tracking_url_for_case",
           "build_eta_minutes_estimate", "eta_label_from_minutes",
           "maybe_renotify_eta_drift",
           "DRIFT_THRESHOLD_MIN", "DRIFT_COOLDOWN_SECONDS"]
