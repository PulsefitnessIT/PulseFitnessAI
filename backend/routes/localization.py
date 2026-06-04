"""Org localization settings (Iter 220p1 — USA readiness, slice 1).

Exposes the resolved localization (country/currency/timezone + tax vocabulary)
for the signed-in user's org and lets owners / master admins change the market.
Defaults to the United Kingdom so existing orgs are unaffected.
"""
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, HTTPException, Depends, Body

from utils.auth import get_current_user
from utils.database import db
from utils.localization import (
    org_localization, supported_countries, country_config,
    COUNTRY_CONFIG, COUNTRY_TIMEZONES, CURRENCY_SYMBOLS,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_org(user: dict):
    org_id = user.get("organization_id")
    if not org_id:
        return None
    return await db.organizations.find_one({"id": org_id}, {"_id": 0})


@router.get("/org/localization")
async def get_org_localization(user: dict = Depends(get_current_user)):
    """Resolved localization for the current org + the list of supported markets."""
    org = await _get_org(user)
    loc = org_localization(org)
    return {
        "localization": loc,
        "supported_countries": supported_countries(),
        "currency_symbols": CURRENCY_SYMBOLS,
        # Whether the signed-in user may change it (owner / master admin).
        "can_edit": bool(
            user.get("is_master_admin")
            or (user.get("role") or "").lower() == "owner"
        ),
    }


@router.put("/org/localization")
async def set_org_localization(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Owner / master admin: set the org's market.

    Picking a ``country_code`` applies that country's currency + timezone
    defaults. Explicit ``currency`` / ``timezone`` in the same request win
    over the country defaults (so a US org could still bill in USD on
    Pacific time, etc.).
    """
    if not (user.get("is_master_admin") or (user.get("role") or "").lower() == "owner"):
        raise HTTPException(status_code=403, detail="Only the owner can change localization")

    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organisation linked to this account")

    code = (body.get("country_code") or "").strip().upper()
    if code and code not in COUNTRY_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported country: {code}")

    updates: dict = {}
    if code:
        cfg = country_config(code)
        updates["country_code"] = code
        # Default currency + timezone for the chosen country; explicit
        # overrides below replace these when present.
        updates["currency"] = cfg["currency"]
        updates["timezone"] = cfg["timezone"]

    currency = (body.get("currency") or "").strip().upper()
    if currency:
        if currency not in CURRENCY_SYMBOLS:
            raise HTTPException(status_code=400, detail=f"Unsupported currency: {currency}")
        updates["currency"] = currency

    tz = (body.get("timezone") or "").strip()
    if tz:
        # Validate against the curated per-country list (avoids junk tz).
        allowed = set()
        for zones in COUNTRY_TIMEZONES.values():
            allowed.update(zones)
        if tz not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported timezone: {tz}")
        updates["timezone"] = tz

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    updates["localization_updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["localization_updated_by"] = user.get("email")
    await db.organizations.update_one({"id": org_id}, {"$set": updates})

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    return {"success": True, "localization": org_localization(org)}
