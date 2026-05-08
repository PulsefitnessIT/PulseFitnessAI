"""
Companies House (UK) public-data API proxy — Iter 215en/215ep (Feb 2026).

Master-admin gated proxy in front of `utils.companies_house_client`. The
actual HTTP / cache / normalisation work lives in the util so the CRM
auto-recognize endpoint can share the same cache and rate-limit pool —
see `routes/crm_v2.py::auto_recognize_company`.

Graceful degradation: when `COMPANIES_HOUSE_API_KEY` is not set, the
endpoints return `{"enabled": false, ...}` with HTTP 200 instead of 503
so the wizard can silently fall back to internal-org-only search.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.companies_house_client import (
    CompaniesHouseError,
    is_enabled,
    base_url,
    search as ch_search,
    profile as ch_profile,
    officers as ch_officers,
)

router = APIRouter()


def _map_ch_error(exc: CompaniesHouseError) -> HTTPException:
    """Translate a CompaniesHouseError into a FastAPI HTTPException with
    the same status hint."""
    return HTTPException(status_code=exc.status, detail=exc.message)


# ─── Endpoints ───────────────────────────────────────────────────────


@router.get("/master-admin/companies-house/status")
async def companies_house_status(user: dict = Depends(get_current_user)) -> dict:
    """Lightweight health probe the wizard hits on mount to decide
    whether to surface the "Search Companies House" affordance."""
    require_master_admin(user)
    return {
        "enabled": is_enabled(),
        "base_url": base_url() if is_enabled() else None,
    }


@router.get("/master-admin/companies-house/search")
async def companies_house_search(
    q: str = Query("", description="Company name / number / postcode prefix"),
    limit: int = Query(8, ge=1, le=20),
    user: dict = Depends(get_current_user),
) -> dict:
    """Proxy `GET /search/companies?q=...` with auth + caching + field
    normalisation."""
    require_master_admin(user)
    qs = (q or "").strip()
    if not is_enabled():
        return {"enabled": False, "items": [], "query": qs}
    try:
        items = await ch_search(qs, limit=limit)
    except CompaniesHouseError as e:
        raise _map_ch_error(e)
    return {"enabled": True, "items": items, "query": qs}


@router.get("/master-admin/companies-house/company/{company_number}")
async def companies_house_profile(
    company_number: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Proxy `GET /company/{number}` with caching + field normalisation."""
    require_master_admin(user)
    if not is_enabled():
        raise HTTPException(status_code=503, detail="Companies House lookup is not configured")
    try:
        out = await ch_profile(company_number)
    except CompaniesHouseError as e:
        raise _map_ch_error(e)
    return {"enabled": True, **out}


@router.get("/master-admin/companies-house/company/{company_number}/officers")
async def companies_house_officers(
    company_number: str,
    include_resigned: bool = False,
    user: dict = Depends(get_current_user),
) -> dict:
    """Proxy `GET /company/{number}/officers` with caching."""
    require_master_admin(user)
    if not is_enabled():
        raise HTTPException(status_code=503, detail="Companies House lookup is not configured")
    try:
        items = await ch_officers(company_number, include_resigned=include_resigned)
    except CompaniesHouseError as e:
        raise _map_ch_error(e)
    return {"enabled": True, "items": items}
