"""HubSpot Parity Audit — serves the feature matrix to the master admin UI."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from data.hubspot_parity import get_matrix, get_summary
from routes.master_admin import require_master_admin
from utils.auth import get_current_user

router = APIRouter()


@router.get("/master-admin/hubspot-parity")
async def hubspot_parity(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    return {
        "summary": get_summary(),
        "features": get_matrix(),
    }
