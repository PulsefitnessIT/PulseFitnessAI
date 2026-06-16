"""
Shared Companies House (UK) public-data API client — Iter 215ep (Feb 2026).

This module is the SINGLE SOURCE OF TRUTH for talking to Companies House.
Every other module that needs CH data (the master-admin onboarding proxy
in `routes/companies_house.py`, the CRM auto-recognize endpoint in
`routes/crm_v2.py`, and any future feature) imports from here so we get
exactly one rate-limit pool, one cache, and one field-normalisation
strategy.

Why a util module instead of inlining in routes/companies_house.py?
  • The master-admin proxy is gated by `require_master_admin` so a
    CRM-user-authenticated endpoint can't call it directly. Extracting
    the HTTP work into a util lets both auth contexts share the cache
    and the API budget.
  • Tests don't have to spin up FastAPI to verify behaviour.
  • Field normalisation (CH `address_line_1` → Pulse Fitness `address_line1`)
    lives in one place — no risk of the two callers drifting.
"""
from __future__ import annotations

import os
import time
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CH_API_KEY = (os.environ.get("COMPANIES_HOUSE_API_KEY") or "").strip()
CH_BASE_URL = (
    os.environ.get("COMPANIES_HOUSE_BASE_URL")
    or "https://api.company-information.service.gov.uk"
).rstrip("/")


def is_enabled() -> bool:
    """True iff the API key is configured. Callers use this to short-
    circuit before bothering to make a request."""
    return bool(CH_API_KEY)


def base_url() -> str:
    return CH_BASE_URL


# ─── In-memory caches ────────────────────────────────────────────────
# Keep TTLs aligned with how often each shape is expected to change:
# search results — 60s (autocomplete keystrokes hit the same prefix)
# profile        — 15min (registered office rarely changes)
# officers       — 15min (officers churn slowly; we don't need real-time)
SEARCH_TTL = 60
PROFILE_TTL = 15 * 60
OFFICERS_TTL = 15 * 60

_search_cache: dict[str, tuple[float, Any]] = {}
_profile_cache: dict[str, tuple[float, Any]] = {}
_officers_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()


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
    if len(cache) > 256:
        oldest_key = min(cache, key=lambda k: cache[k][0])
        cache.pop(oldest_key, None)


# ─── Field normalisation ─────────────────────────────────────────────


def normalise_address(addr: dict | None) -> dict:
    """Map CH `registered_office_address` shape onto the Pulse Fitness
    structured-address shape so callers can drop the result straight
    into our AddressFields component without any per-call mapping."""
    if not addr:
        return {
            "address_line1": "", "address_line2": "", "address_line3": "",
            "city": "", "county": "", "postcode": "", "country": "United Kingdom",
        }
    premises = (addr.get("premises") or "").strip()
    line1 = (addr.get("address_line_1") or "").strip()
    composed_line1 = ", ".join([p for p in (premises, line1) if p]) or line1 or premises
    return {
        "address_line1": composed_line1,
        "address_line2": (addr.get("address_line_2") or "").strip(),
        "address_line3": (addr.get("po_box") or "").strip(),
        "city": (addr.get("locality") or "").strip(),
        "county": (addr.get("region") or "").strip(),
        "postcode": (addr.get("postal_code") or "").strip(),
        "country": (addr.get("country") or "United Kingdom").strip() or "United Kingdom",
    }


def normalise_search_item(it: dict) -> dict:
    """Pluck the fields callers actually use out of a CH search-companies
    response item."""
    return {
        "company_number": it.get("company_number") or "",
        "company_name": _smart_case((it.get("title") or it.get("company_name") or "").strip()),
        "company_status": it.get("company_status") or "",
        "company_type": it.get("company_type") or "",
        "date_of_creation": it.get("date_of_creation") or "",
        "address_snippet": it.get("address_snippet") or "",
        **normalise_address(it.get("address")),
    }


def _smart_case(s: str) -> str:
    """Convert CH's SCREAMING all-caps names to a friendly Title Case.
    'PULSE FITNESS LIMITED' → 'Pulse Fitness Limited'. Preserves common
    acronyms (UK / GB / IT / HR) and roman-numeral suffixes."""
    if not s:
        return ""
    keep = {"UK", "GB", "EU", "USA", "US", "IT", "HR", "AI", "VAT", "PLC", "LLP", "II", "III", "IV"}
    return " ".join(w if w.upper() in keep else w.capitalize() for w in s.split())


def _parse_officer_name(raw: str) -> str:
    """CH returns names as 'LAST, First Middle' (caps); produce
    'First Middle Last' in friendly case."""
    name = (raw or "").strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2:
            return _smart_case(f"{parts[1]} {parts[0]}")
    return _smart_case(name)


# ─── HTTP helpers ────────────────────────────────────────────────────


class CompaniesHouseError(Exception):
    """Wraps a CH transport / auth / rate-limit failure with a machine-
    readable status hint so callers can map onto HTTP 502 / 429 / 404."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"CH {status}: {message}")


async def _ch_get(path: str, params: dict | None = None) -> dict:
    if not CH_API_KEY:
        raise CompaniesHouseError(503, "Companies House API key not configured")
    try:
        async with httpx.AsyncClient(
            base_url=CH_BASE_URL,
            auth=(CH_API_KEY, ""),
            timeout=10.0,
        ) as client:
            r = await client.get(path, params=params or {})
    except httpx.HTTPError as e:
        logger.warning("[ch] transport error on %s: %s", path, e)
        raise CompaniesHouseError(502, "Companies House network error") from e

    if r.status_code == 401:
        logger.warning("[ch] 401 on %s — API key rejected", path)
        raise CompaniesHouseError(502, "Companies House rejected the API key")
    if r.status_code == 404:
        raise CompaniesHouseError(404, "Not found")
    if r.status_code == 429:
        raise CompaniesHouseError(429, "Companies House rate limit hit; try again in a few seconds")
    if r.status_code >= 400:
        logger.warning("[ch] %s on %s — %s", r.status_code, path, r.text[:200])
        raise CompaniesHouseError(502, f"Companies House error ({r.status_code})")
    return r.json() or {}


# ─── Public API ──────────────────────────────────────────────────────


async def search(q: str, limit: int = 8) -> list[dict]:
    """Search Companies House by name / number / postcode prefix.
    Returns a list of Pulse Fitness-shaped dicts (see `normalise_search_item`).
    Returns [] on enabled-but-too-short queries (<2 chars)."""
    qs = (q or "").strip()
    if not is_enabled() or len(qs) < 2:
        return []
    cache_key = f"{qs.lower()}::{limit}"
    async with _cache_lock:
        cached = _cache_get(_search_cache, cache_key)
    if cached is not None:
        return cached
    data = await _ch_get("/search/companies", params={"q": qs, "items_per_page": limit})
    items = [normalise_search_item(it) for it in (data.get("items") or [])]
    async with _cache_lock:
        _cache_set(_search_cache, cache_key, items, SEARCH_TTL)
    return items


async def profile(company_number: str) -> dict:
    """Fetch the full company profile and return a Pulse Fitness-shaped dict
    with the structured registered-office address pre-normalised."""
    cn = (company_number or "").strip().upper()
    if not cn:
        raise CompaniesHouseError(400, "Company number required")
    async with _cache_lock:
        cached = _cache_get(_profile_cache, cn)
    if cached is not None:
        return cached
    data = await _ch_get(f"/company/{cn}")
    out = {
        "company_number": data.get("company_number") or cn,
        "company_name": _smart_case(data.get("company_name") or ""),
        "company_status": data.get("company_status") or "",
        "company_type": data.get("type") or data.get("company_type") or "",
        "date_of_creation": data.get("date_of_creation") or "",
        "sic_codes": list(data.get("sic_codes") or []),
        **normalise_address(data.get("registered_office_address")),
    }
    async with _cache_lock:
        _cache_set(_profile_cache, cn, out, PROFILE_TTL)
    return out


async def officers(company_number: str, include_resigned: bool = False) -> list[dict]:
    """Fetch the active officers for a company. Returns a list of
    `{name, role, appointed_on}` dicts in friendly case. Resigned
    officers are excluded by default (typical use case is "who can I
    contact?")."""
    cn = (company_number or "").strip().upper()
    if not cn:
        raise CompaniesHouseError(400, "Company number required")
    cache_key = f"{cn}::{1 if include_resigned else 0}"
    async with _cache_lock:
        cached = _cache_get(_officers_cache, cache_key)
    if cached is not None:
        return cached
    data = await _ch_get(f"/company/{cn}/officers", params={"items_per_page": 35})
    out: list[dict] = []
    for it in data.get("items") or []:
        if not include_resigned and it.get("resigned_on"):
            continue
        out.append({
            "name": _parse_officer_name(it.get("name") or ""),
            "role": _smart_case(it.get("officer_role") or "Director"),
            "appointed_on": it.get("appointed_on") or "",
            "occupation": _smart_case(it.get("occupation") or ""),
            "nationality": _smart_case(it.get("nationality") or ""),
        })
    async with _cache_lock:
        _cache_set(_officers_cache, cache_key, out, OFFICERS_TTL)
    return out
