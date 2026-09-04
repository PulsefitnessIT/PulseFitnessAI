"""
Postcode lookup proxy — Iter 215eq/215et (Feb 2026).

Thin wrapper over `utils.postcodes_client` exposing two endpoints:
validate-and-lookup, and autocomplete.

Iter 215et — auth REMOVED. The underlying postcodes.io data is open
public ONS / Royal Mail / Ordnance Survey data; there's nothing
sensitive to gate. Removing auth lets the public Customer Onboarding
form (token-based, no login) and any future marketing-site widget
share the same proxy and cache without bypassing infra.

Mild abuse protection comes for free from `utils.postcodes_client`'s
in-memory cache (24h on lookup, 5min on autocomplete) and from
postcodes.io's own per-IP fair-use throttling.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from utils.postcodes_client import autocomplete as pc_autocomplete
from utils.postcodes_client import lookup as pc_lookup

router = APIRouter()


@router.get("/integrations/postcode/lookup")
async def postcode_lookup(
    postcode: str = Query(..., min_length=2, max_length=12),
    country: str | None = Query(None, max_length=64),
) -> dict:
    """Validate + look up a postcode worldwide (UK via postcodes.io, the
    rest via Zippopotam.us — routed by the optional `country` hint)."""
    result = await pc_lookup(postcode, country)
    if not result:
        return {"found": False, "postcode": postcode}
    return {"found": True, **result}


@router.get("/integrations/postcode/autocomplete")
async def postcode_autocomplete(
    q: str = Query(..., min_length=2, max_length=12),
    limit: int = Query(10, ge=1, le=20),
) -> dict:
    """Return up to `limit` candidate UK postcodes for a partial input."""
    suggestions = await pc_autocomplete(q, limit=limit)
    return {"suggestions": suggestions, "query": q}
