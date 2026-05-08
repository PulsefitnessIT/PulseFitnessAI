"""
postcodes.io (UK) public-data API client — Iter 215eq (Feb 2026).

postcodes.io is a free, MIT-licensed UK postcode lookup service backed
by ONS / Royal Mail / Ordnance Survey data, maintained by Ideal
Postcodes. No auth, no formal rate limit (community fair-use).

Why a backend proxy instead of calling from the browser?
  • Postcodes.io supports CORS so we *could* call it from the SPA, but
    proxying gives us:
      - One shared cache (postcode → result rarely changes; 24h TTL is
        comfortable). The Master Admin onboarding wizard, the CRM
        company drawer, the Service Desk intake form, and the
        Memberships sign-up flow all benefit from the same cache.
      - One place to add request logging / circuit-break if the
        upstream is degraded (we'd rather quietly skip than show
        broken UI).
      - One place to swap providers later (Ideal Postcodes premium tier
        offers UPRN + property-level geocoding when we eventually need
        it for engineer dispatch heatmaps).

Used by:
  • routes.postcodes — the master-admin / authenticated-user proxy.
  • Frontend AddressFields component (autocomplete + auto-fill on
    structured-address inputs) — see /app/frontend/src/components/shared/AddressFields.js
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

POSTCODES_BASE_URL = "https://api.postcodes.io"

# Cache TTLs:
#   lookup       — 24h (postcode → admin areas rarely change between ONS releases)
#   autocomplete — 5min (autocomplete keystrokes hit the same prefix repeatedly)
LOOKUP_TTL = 24 * 60 * 60
AUTOCOMPLETE_TTL = 5 * 60

_lookup_cache: dict[str, tuple[float, Any]] = {}
_autocomplete_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()

# Postcode regex matches the canonical UK pattern (with or without space).
# Used both as a guard before hitting the upstream and to format
# user-typed values consistently (e.g. "n154qt" → "N15 4QT").
_POSTCODE_RE = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})$",
    re.IGNORECASE,
)


def normalise_postcode(p: str) -> str | None:
    """Format a user-typed postcode as canonical "AA9 9AA". Returns None
    if the value can't be parsed as a UK postcode (lets the caller skip
    the upstream call entirely rather than burning quota on garbage)."""
    if not p:
        return None
    cleaned = re.sub(r"\s+", "", p).upper()
    m = _POSTCODE_RE.match(cleaned)
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)}"


def _cache_get(cache: dict, key: str) -> Any | None:
    rec = cache.get(key)
    if not rec:
        return None
    expires_at, value = rec
    if expires_at < time.monotonic():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value: Any, ttl: int) -> None:
    cache[key] = (time.monotonic() + ttl, value)
    if len(cache) > 1024:
        oldest_key = min(cache, key=lambda k: cache[k][0])
        cache.pop(oldest_key, None)


def normalise_lookup(result: dict | None) -> dict | None:
    """Pluck the GymAxis-relevant fields out of a postcodes.io lookup
    response and rename them to match our address-shape conventions."""
    if not result:
        return None
    return {
        "postcode": result.get("postcode") or "",
        # Map onto our 8-field structured-address shape:
        "city": result.get("admin_district") or result.get("parish") or "",
        "county": result.get("admin_county") or result.get("region") or "",
        "country": result.get("country") or "United Kingdom",
        "region": result.get("region") or "",
        # Geo-coords for future engineer-dispatch heatmaps / nearest-
        # site lookups.
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        # Demographic / political — useful for marketing segmentation
        # and territory routing.
        "parliamentary_constituency": result.get("parliamentary_constituency") or "",
        "ccg": result.get("ccg") or "",
        "nhs_region": result.get("nhs_region") or "",
    }


async def lookup(postcode: str) -> dict | None:
    """Validate + look up a UK postcode. Returns the GymAxis-shaped dict
    or `None` when the postcode is invalid / not found."""
    norm = normalise_postcode(postcode)
    if not norm:
        return None
    async with _cache_lock:
        cached = _cache_get(_lookup_cache, norm)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(base_url=POSTCODES_BASE_URL, timeout=8.0) as client:
            r = await client.get(f"/postcodes/{norm.replace(' ', '')}")
        if r.status_code == 404:
            async with _cache_lock:
                # Cache the negative result for a shorter window — invalid
                # postcodes are mostly typos that the user fixes in seconds.
                _cache_set(_lookup_cache, norm, None, 60)
            return None
        if r.status_code != 200:
            logger.warning("[postcodes.io] %s on /postcodes/%s — %s", r.status_code, norm, r.text[:200])
            return None
        data = (r.json() or {}).get("result")
    except httpx.HTTPError as e:
        logger.warning("[postcodes.io] transport error on lookup %s: %s", norm, e)
        return None
    out = normalise_lookup(data)
    async with _cache_lock:
        _cache_set(_lookup_cache, norm, out, LOOKUP_TTL)
    return out


async def autocomplete(prefix: str, limit: int = 10) -> list[str]:
    """Return up to `limit` candidate postcodes for a partial input.
    Empty / too-short prefixes return [] without hitting the upstream."""
    qs = re.sub(r"\s+", "", (prefix or "")).upper()
    if len(qs) < 2:
        return []
    cache_key = f"{qs}::{limit}"
    async with _cache_lock:
        cached = _cache_get(_autocomplete_cache, cache_key)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(base_url=POSTCODES_BASE_URL, timeout=6.0) as client:
            r = await client.get(f"/postcodes/{qs}/autocomplete", params={"limit": limit})
        if r.status_code != 200:
            return []
        data = (r.json() or {}).get("result") or []
    except httpx.HTTPError as e:
        logger.warning("[postcodes.io] transport error on autocomplete %s: %s", qs, e)
        return []
    suggestions = [str(p) for p in data if p]
    async with _cache_lock:
        _cache_set(_autocomplete_cache, cache_key, suggestions, AUTOCOMPLETE_TTL)
    return suggestions
