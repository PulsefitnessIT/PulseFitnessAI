"""Marketing entitlement endpoint.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations


from fastapi import APIRouter, Depends

from utils.auth import get_current_user

from routes.marketing.helpers import (
    _get_entitlement,
)

router = APIRouter()


# ───────────────────────── Entitlement endpoint ─────────────────────────

@router.get("/marketing/me/entitlement")
async def my_entitlement(user: dict = Depends(get_current_user)):
    return await _get_entitlement(user)
