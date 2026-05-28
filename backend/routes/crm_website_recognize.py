"""Iter 216h268 — Website-first company recognition endpoint.

User feedback (P2): *"Companies — use the company's website URL as
the primary source rather than Companies House addresses, so the
right typing flows through."*

Surface: `POST /api/crm/v2/companies/recognize-from-website`

Request body:
    {"url": "https://acmegym.co.uk"}   # naked domain also accepted

Response:
    {
      "success": True,
      "source": "website",
      "url": "https://acmegym.co.uk",
      "company_info": {
        "name": ..., "website": ..., "phone": ..., "email": ...,
        "address_line1": ..., "city": ..., "postcode": ..., "country": ...,
        "description": ..., "logo_url": ..., "social_links": [...]
      },
      "pages_fetched": ["/", "/contact"],
      "cached": False
    }

Caches successful responses for 24h in `crm_website_cache` so
repeated lookups across the same org don't re-scrape the site.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from utils.website_enrichment import (
    CONTACT_PATHS,
    extract_company_info,
    merge_extractions,
    normalise_url,
)
from routes.crm_auth import get_crm_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/v2", tags=["CRM v2"])


CACHE_COLLECTION = "crm_website_cache"
CACHE_TTL_HOURS = 24
MAX_HTML_BYTES = 400_000          # ~400KB cap per page
HTTP_TIMEOUT_SECONDS = 8.0
USER_AGENT = "GymAxisAI/1.0 (+https://gymaxisai.com; CRM company recogniser)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _read_cache(url: str) -> dict | None:
    cutoff = (_now() - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    doc = await db[CACHE_COLLECTION].find_one(
        {"url": url, "fetched_at": {"$gte": cutoff}},
        {"_id": 0},
    )
    return doc


async def _write_cache(url: str, payload: dict) -> None:
    await db[CACHE_COLLECTION].update_one(
        {"url": url},
        {"$set": {**payload, "url": url, "fetched_at": _now().isoformat()}},
        upsert=True,
    )


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a page with a hard byte cap. Returns None on any error.

    Iter 220aw / F-26 — SSRF guard. Refuse any URL whose hostname
    resolves to a private / loopback / link-local / metadata address.
    """
    try:
        from utils.ssrf_guard import assert_safe_external_url, SSRFBlocked
        try:
            assert_safe_external_url(url)
        except SSRFBlocked as exc:
            logger.warning("website fetch blocked by SSRF guard url=%s reason=%s", url, exc.detail)
            return None
        resp = await client.get(url)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.debug("website fetch failed url=%s err=%s", url, exc)
        return None
    # Only treat HTML responses as parseable
    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" not in ctype and "xml" not in ctype:
        return None
    text = resp.text
    if len(text) > MAX_HTML_BYTES:
        text = text[:MAX_HTML_BYTES]
    return text


async def _scrape_url(base: str) -> tuple[dict, list[str]]:
    """Fetch the homepage + opportunistic contact pages, return the
    merged extraction + the list of paths we successfully fetched."""
    extractions: list[dict] = []
    pages_fetched: list[str] = []
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        # 1. Homepage (always)
        home_html = await _fetch(client, base + "/")
        if home_html:
            extractions.append(extract_company_info(home_html, base))
            pages_fetched.append("/")
        # 2. Contact pages — only if homepage didn't yield phone/email/postcode
        primary = extractions[0] if extractions else {}
        needs_contact = not all(primary.get(k) for k in ("phone", "email", "postcode"))
        if needs_contact:
            for path in CONTACT_PATHS:
                if not needs_contact:
                    break
                html = await _fetch(client, base + path)
                if not html:
                    continue
                extra = extract_company_info(html, base)
                if extra:
                    extractions.append(extra)
                    pages_fetched.append(path)
                # Refresh the "do we still need more pages?" check
                merged_so_far = merge_extractions(*extractions)
                needs_contact = not all(merged_so_far.get(k) for k in ("phone", "email", "postcode"))
    return merge_extractions(*extractions), pages_fetched


@router.post("/companies/recognize-from-website")
async def recognize_from_website(data: dict, user=Depends(get_crm_user)) -> dict[str, Any]:
    """Fetch a prospect's homepage + contact pages and extract the
    fields the CRM Create Company form needs. Falls back to AI /
    Companies House only when explicitly asked — sales reps wanted
    the **website** to be the source of truth for trading address
    + decision-maker contact details.
    """
    raw_url = (data or {}).get("url", "")
    base = normalise_url(raw_url)
    if not base:
        raise HTTPException(400, "Provide a valid website URL (e.g. https://acmegym.co.uk)")

    # 1. Cache hit?
    cached = await _read_cache(base)
    if cached:
        info = cached.get("company_info") or {}
        return {
            "success": bool(info),
            "source": "website",
            "url": base,
            "company_info": info,
            "pages_fetched": cached.get("pages_fetched") or [],
            "cached": True,
        }

    # 2. Live scrape
    try:
        info, pages_fetched = await _scrape_url(base)
    except Exception as exc:
        logger.warning("website scrape crashed url=%s err=%s", base, exc)
        raise HTTPException(502, f"Could not read {base}: {type(exc).__name__}") from exc

    if not info or not pages_fetched:
        # Don't cache empty/error responses — site might be flaky or
        # blocking us, the next try should re-attempt.
        raise HTTPException(
            404,
            f"Could not extract any company details from {base}. The site may block bots — please add the details manually.",
        )

    payload = {
        "company_info": info,
        "pages_fetched": pages_fetched,
    }
    # Cache successful extractions for 24h
    try:
        await _write_cache(base, payload)
    except Exception:
        logger.exception("website cache write failed (non-fatal)")

    return {
        "success": True,
        "source": "website",
        "url": base,
        "company_info": info,
        "pages_fetched": pages_fetched,
        "cached": False,
    }


async def ensure_website_cache_indexes() -> None:
    try:
        await db[CACHE_COLLECTION].create_index("url", unique=True)
        await db[CACHE_COLLECTION].create_index("fetched_at")
    except Exception:
        logger.exception("ensure_website_cache_indexes failed (non-fatal)")
