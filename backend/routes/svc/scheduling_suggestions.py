"""
Pulse Fitness Service Operations — Smart scheduling suggestions.

Iter 220g — When an engineer creates a new job and types the site
postcode, surface dates when they already have jobs booked near here
(within 10 miles). This stops them booking a 2-hour drive to a
postcode they could have folded into another trip.

Strategy:

  * Resolve UK postcodes to lat/lng via the free postcodes.io public
    API (no auth, no key). Cache results in `postcode_cache` keyed by
    the normalised postcode so we hit the API at most once per
    postcode per pod lifetime.
  * For each open scheduled job in the next 14 days, geocode its
    site_postcode (cached) and compute the haversine distance to the
    target. Anything ≤ 10 miles is "near".
  * Group nearby jobs by ISO date and return suggestions sorted by
    nearby_count desc, date asc.

If postcodes.io is unreachable (e.g. during tests / offline pods) we
gracefully fall back to outward-code match — "CV1 1AA" and "CV1 4BB"
both reduce to "CV1" and are treated as ~3 miles apart.

Endpoint:

    GET /api/svc/engineer/jobs/scheduling-suggestions
        ?postcode=CV1 1AA          (required)
        &days=14                   (default 14, max 60)
        &radius_miles=10           (default 10, max 50)
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Smart scheduling (iter 220g)"],
)

POSTCODES_IO = "https://api.postcodes.io/postcodes"
HTTP_TIMEOUT = 4.0


def _normalise_postcode(pc: str) -> str:
    """Uppercase + collapse whitespace + ensure single space before
    the inward code. Returns '' if the string clearly isn't a UK
    postcode (we don't want to spam postcodes.io with bin data)."""
    if not pc:
        return ""
    cleaned = re.sub(r"\s+", "", str(pc).upper())
    if not 5 <= len(cleaned) <= 7:
        return ""
    return f"{cleaned[:-3]} {cleaned[-3:]}"


def _outward_code(pc: str) -> str:
    n = _normalise_postcode(pc)
    return n.split(" ", 1)[0] if " " in n else n


def _haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) tuples, in miles."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 7917.5 * math.asin(math.sqrt(h))  # 2 * earth_radius_miles


async def _geocode_uk_postcode(postcode: str) -> Optional[tuple[float, float]]:
    """Return (lat, lng) for a UK postcode, or None on any failure.
    Caches successful lookups in `postcode_cache` so we only hit
    postcodes.io once per pod lifetime per postcode."""
    norm = _normalise_postcode(postcode)
    if not norm:
        return None
    cached = await db.postcode_cache.find_one({"postcode": norm}, {"_id": 0, "lat": 1, "lng": 1, "miss": 1})
    if cached:
        if cached.get("miss"):
            return None
        try:
            return float(cached["lat"]), float(cached["lng"])
        except (KeyError, TypeError, ValueError):
            return None
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            r = await c.get(f"{POSTCODES_IO}/{norm.replace(' ', '%20')}")
        if r.status_code != 200:
            await db.postcode_cache.update_one(
                {"postcode": norm},
                {"$set": {"postcode": norm, "miss": True, "checked_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            return None
        data = (r.json() or {}).get("result") or {}
        lat = data.get("latitude")
        lng = data.get("longitude")
        if lat is None or lng is None:
            return None
        await db.postcode_cache.update_one(
            {"postcode": norm},
            {"$set": {
                "postcode": norm, "lat": float(lat), "lng": float(lng),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        return float(lat), float(lng)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning(f"[scheduling] geocode {norm!r} failed: {exc!r}")
        return None


@router.get("/scheduling-suggestions")
async def scheduling_suggestions(
    postcode: str = Query(..., min_length=3, max_length=10),
    days: int = Query(default=14, ge=1, le=60),
    radius_miles: float = Query(default=10.0, ge=0.5, le=50.0),
    user=Depends(get_current_user),
):
    """Return up to 5 date suggestions where the engineer already has
    jobs booked within `radius_miles` of `postcode` in the next `days`.

    Empty results → no recommendations, the engineer books manually.
    """
    org = (user.get("organization_id") or user.get("service_org_id"))
    if not org:
        raise HTTPException(403, "Organization context required")

    target_norm = _normalise_postcode(postcode)
    if not target_norm:
        return {"target_postcode": postcode, "suggestions": [], "reason": "invalid_postcode"}
    target_outward = _outward_code(target_norm)
    target_latlng = await _geocode_uk_postcode(target_norm)

    # Pull the engineer's existing scheduled jobs in the window.
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days)
    rows = await db.svc_cases.find(
        {
            "organization_id": org,
            "assigned_engineer_id": user.get("id"),
            "status": {"$in": ["scheduled", "en_route", "on_site", "open", "in_progress"]},
            "scheduled_at": {"$gte": today.isoformat(), "$lt": end.isoformat() + "T23:59:59Z"},
            "site_postcode": {"$exists": True, "$ne": ""},
        },
        {
            "_id": 0, "id": 1, "reference": 1, "title": 1,
            "site_name": 1, "site_postcode": 1, "scheduled_at": 1,
            "customer_name": 1,
        },
    ).sort([("scheduled_at", 1)]).to_list(200)

    by_date: dict[str, dict] = {}
    for row in rows:
        row_pc = row.get("site_postcode") or ""
        row_norm = _normalise_postcode(row_pc)
        if not row_norm:
            continue
        distance: Optional[float] = None
        row_latlng = await _geocode_uk_postcode(row_norm)
        if target_latlng and row_latlng:
            distance = _haversine_miles(target_latlng, row_latlng)
            if distance > radius_miles:
                continue
        else:
            # Geocoder unavailable for one side → outward-code fallback.
            # Same outward code ≈ 0-5 miles in dense urban areas.
            if _outward_code(row_norm) != target_outward:
                continue
            distance = 3.0  # rough proxy so the UI can still sort

        # Parse scheduled_at date.
        sched = (row.get("scheduled_at") or "")[:10]
        if not sched:
            continue
        if sched < today.isoformat() or sched >= end.isoformat():
            continue
        bucket = by_date.setdefault(sched, {"date": sched, "jobs": [], "min_distance_miles": distance})
        bucket["jobs"].append({
            "id": row.get("id"),
            "reference": row.get("reference"),
            "title": row.get("title"),
            "site_name": row.get("site_name"),
            "site_postcode": row.get("site_postcode"),
            "customer_name": row.get("customer_name"),
            "distance_miles": round(distance, 1) if distance is not None else None,
        })
        if distance is not None and distance < bucket["min_distance_miles"]:
            bucket["min_distance_miles"] = distance

    suggestions = sorted(
        by_date.values(),
        key=lambda b: (-len(b["jobs"]), b["min_distance_miles"], b["date"]),
    )[:5]
    for s in suggestions:
        s["min_distance_miles"] = round(s["min_distance_miles"], 1)
        s["job_count"] = len(s["jobs"])
    return {
        "target_postcode": target_norm,
        "target_geocoded": bool(target_latlng),
        "window_days": days,
        "radius_miles": radius_miles,
        "suggestions": suggestions,
    }


async def ensure_indexes() -> None:
    await db.postcode_cache.create_index([("postcode", 1)], unique=True)


__all__ = ["router", "ensure_indexes"]
