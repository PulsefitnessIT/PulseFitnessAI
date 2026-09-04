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
    """Pluck the Pulse Fitness-relevant fields out of a postcodes.io lookup
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


async def _uk_lookup(postcode: str) -> dict | None:
    """Validate + look up a UK postcode. Returns the Pulse Fitness-shaped dict
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



# ─────────────────────────────────────────────────────────────────────────
# International postcodes — Zippopotam.us (Iter — Jun 2026)
#
# postcodes.io is UK-only, but Pulse trades globally. Zippopotam.us is a
# free, no-auth public API covering ~60 countries. We route by country:
#   • UK-shaped postcode (or GB country) → postcodes.io (richest data)
#   • everything else                    → Zippopotam.us /{code}/{postcode}
# Zippopotam returns { "post code", "country", "places": [{ "place name",
# "state", "latitude", "longitude" }] }.
# ─────────────────────────────────────────────────────────────────────────

ZIPPOPOTAM_BASE_URL = "https://api.zippopotam.us"

# Map free-text country names (as typed on the address form) → ISO 3166-1
# alpha-2 codes that Zippopotam understands. Anything already a 2-letter
# code is accepted as-is.
_COUNTRY_CODE_MAP: dict[str, str] = {
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "united states": "US", "united states of america": "US", "usa": "US",
    "america": "US", "u.s.a.": "US", "u.s.": "US",
    "canada": "CA",
    "ireland": "IE", "republic of ireland": "IE",
    "germany": "DE", "deutschland": "DE",
    "france": "FR",
    "spain": "ES", "españa": "ES",
    "italy": "IT", "italia": "IT",
    "netherlands": "NL", "holland": "NL",
    "belgium": "BE",
    "portugal": "PT",
    "switzerland": "CH",
    "austria": "AT",
    "denmark": "DK",
    "sweden": "SE",
    "norway": "NO",
    "finland": "FI",
    "poland": "PL",
    "australia": "AU",
    "new zealand": "NZ",
    "india": "IN",
    "japan": "JP",
    "mexico": "MX",
    "brazil": "BR", "brasil": "BR",
    "south africa": "ZA",
}


def country_to_code(country: str | None) -> str | None:
    """Resolve a free-text country name to an ISO alpha-2 code, or None."""
    if not country:
        return None
    c = country.strip().lower()
    if not c:
        return None
    if c in _COUNTRY_CODE_MAP:
        return _COUNTRY_CODE_MAP[c]
    # Already a 2-letter code?
    if len(c) == 2 and c.isalpha():
        return c.upper()
    return None


def normalise_zippo(result: dict | None) -> dict | None:
    """Pluck Pulse-relevant fields out of a Zippopotam response onto our
    address shape (city ← place name, county/region ← state)."""
    if not result:
        return None
    places = result.get("places") or []
    place = places[0] if places else {}
    return {
        "postcode": result.get("post code") or "",
        "city": place.get("place name") or "",
        "county": place.get("state") or "",
        "country": result.get("country") or "",
        "region": place.get("state") or "",
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "parliamentary_constituency": "",
        "ccg": "",
        "nhs_region": "",
    }


async def _zippo_lookup(postcode: str, code: str) -> dict | None:
    """Look up an international postcode via Zippopotam.us."""
    pc = re.sub(r"\s+", "", (postcode or "")).upper()
    if len(pc) < 3:
        return None
    code = (code or "").upper()
    cache_key = f"ZIPPO:{code}:{pc}"
    async with _cache_lock:
        cached = _cache_get(_lookup_cache, cache_key)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(base_url=ZIPPOPOTAM_BASE_URL, timeout=8.0) as client:
            r = await client.get(f"/{code.lower()}/{pc}")
        if r.status_code == 404:
            async with _cache_lock:
                _cache_set(_lookup_cache, cache_key, None, 60)
            return None
        if r.status_code != 200:
            logger.warning("[zippopotam] %s on /%s/%s", r.status_code, code, pc)
            return None
        data = r.json() or {}
    except httpx.HTTPError as e:
        logger.warning("[zippopotam] transport error on %s/%s: %s", code, pc, e)
        return None
    out = normalise_zippo(data)
    if out and not out.get("city"):
        out = None
    async with _cache_lock:
        _cache_set(_lookup_cache, cache_key, out, LOOKUP_TTL)
    return out


async def lookup(postcode: str, country: str | None = None) -> dict | None:
    """Validate + look up a postcode, worldwide.

    Routing:
      • UK-shaped postcode, or country resolves to GB → postcodes.io.
      • Otherwise → Zippopotam.us using the resolved country code.
      • UK-shaped with an unknown country still tries postcodes.io first,
        then Zippopotam GB as a fallback.
    """
    code = country_to_code(country)
    uk_shaped = normalise_postcode(postcode) is not None

    # UK context → postcodes.io (richest data).
    if uk_shaped and code in (None, "GB"):
        res = await _uk_lookup(postcode)
        if res:
            return res

    # International context → Zippopotam.
    if code and code != "GB":
        res = await _zippo_lookup(postcode, code)
        if res:
            return res

    # Explicit GB country but postcodes.io missed → try UK lookup then Zippo GB.
    if code == "GB":
        res = await _uk_lookup(postcode)
        if res:
            return res
        return await _zippo_lookup(postcode, "GB")

    # No country hint and not UK-shaped — nothing reliable to query.
    return None
