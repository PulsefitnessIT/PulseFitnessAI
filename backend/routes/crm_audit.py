"""
CRM Audit Trail read API — iter 215dd.

Exposes timeline reads for the record drawers ("Activity log" tab) and
the global Audit admin view ("Who changed what, when" dashboard).

Endpoints live under /api/crm/audit and use the CRM auth guard.
"""
from fastapi import APIRouter, Depends, Query

from routes.crm_auth import get_crm_user
from utils.crm_audit import audit_timeline

router = APIRouter(prefix="/crm/audit", tags=["CRM Audit"])


@router.get("")
async def list_audit(
    entity_type: str = Query("", description="contact | company | opportunity | contract"),
    entity_id: str = Query(""),
    actor_id: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user=Depends(get_crm_user),
):
    rows = await audit_timeline(
        organization_id=user.get("organization_id", ""),
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        actor_id=actor_id or None,
        limit=limit,
        skip=skip,
    )
    return {"entries": rows, "count": len(rows)}


@router.get("/recent")
async def recent_audit(
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_crm_user),
):
    """Global feed — the org-wide 'who changed what, when' stream."""
    rows = await audit_timeline(
        organization_id=user.get("organization_id", ""),
        limit=limit,
    )
    return {"entries": rows, "count": len(rows)}
