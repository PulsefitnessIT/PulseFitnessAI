"""GymAxis Service Operations — Engineer location pings (Iter 216h91).

Powers the "Live tracking" view on the customer-facing tracking page.
Engineer mobile app POSTs `navigator.geolocation` updates every ~60 s
while the on_site/en_route timer is running. We keep them brief and
TTL-expire them so the database doesn't bloat.

Endpoints:
  POST /svc/engineer/location                — engineer ping
  GET  /svc/engineer/location/me             — for debugging / self-test
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/svc/engineer/location")
async def post_location(body: dict, user=Depends(get_current_user)):
    """Record an engineer location ping.

    Body: {lat: float, lng: float, accuracy_m: float, case_id: str (optional)}
    """
    try:
        lat = float(body.get("lat"))
        lng = float(body.get("lng"))
    except (TypeError, ValueError):
        raise HTTPException(400, "lat & lng must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(400, "lat/lng out of range")
    accuracy = body.get("accuracy_m")
    try:
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy = None
    case_id = (body.get("case_id") or "").strip() or None

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "engineer_id": user["id"],
        "organization_id": (user.get("organization_id") or user.get("service_org_id")),
        "lat": lat,
        "lng": lng,
        "accuracy_m": accuracy,
        "case_id": case_id,
        "recorded_at": now,
    }
    # Upsert by engineer_id — only keep the latest. Sparse history is
    # not a product requirement at this stage.
    await db.svc_engineer_locations.update_one(
        {"engineer_id": user["id"]},
        {"$set": doc},
        upsert=True,
    )

    # Iter 220dk — Mid-journey ETA drift re-notify. After the ping is
    # persisted (so the freshly-computed haversine ETA reads the
    # latest coords), run the auto-renotify check. Wrapped in
    # try/except so a downstream comms error never breaks the
    # location ping (this is the engineer-mobile critical path).
    renotified: list[dict] = []
    try:
        from routes.svc.engineer_eta_update import maybe_renotify_eta_drift
        renotified = await maybe_renotify_eta_drift(user=user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("eta drift renotify check failed: %s", exc)

    return {
        "ok": True,
        "recorded_at": now,
        "eta_renotified_case_ids": [r["case_id"] for r in renotified if r.get("ok")],
    }


@router.get("/svc/engineer/location/me")
async def get_my_location(user=Depends(get_current_user)):
    doc = await db.svc_engineer_locations.find_one(
        {"engineer_id": user["id"]}, {"_id": 0},
    )
    return doc or {}


__all__ = ["router"]
