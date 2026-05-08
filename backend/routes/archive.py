"""Master Admin / Service Desk archive + GDPR right-to-erasure routes.

Access model:
  - List + restore: Service Desk (master admin passes through as superset).
  - Hard-delete:    Master Admin only (irreversible; kept behind stricter guard).
  - Lifecycle run:  Master Admin only.
"""
from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.service_desk_auth import require_service_desk
from utils.archive_lifecycle import (
    RETENTION_DAYS,
    WARNING_LEAD_DAYS,
    hard_delete_organization,
    list_archived_organizations,
    restore_organization,
    run_archive_lifecycle_once,
)

router = APIRouter()


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin access required")


@router.get("/master-admin/archive")
async def get_archive(user: dict = Depends(require_service_desk)) -> dict:
    """List all archived organisations with deletion countdown."""
    orgs = await list_archived_organizations()
    return {
        "organizations": orgs,
        "retention_days": RETENTION_DAYS,
        "warning_lead_days": WARNING_LEAD_DAYS,
        "count": len(orgs),
    }


@router.post("/master-admin/archive/{org_id}/restore")
async def restore_archived_org(org_id: str, user: dict = Depends(require_service_desk)) -> dict:
    """Restore an archived org back to active status."""
    ok = await restore_organization(org_id, user["email"])
    if not ok:
        raise HTTPException(status_code=404, detail="Archived organization not found")
    return {"success": True, "org_id": org_id, "status": "active"}


@router.delete("/master-admin/archive/{org_id}")
async def hard_delete_archived_org(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Permanently hard-delete an archived org (immediate GDPR erasure). Irreversible."""
    _require_master_admin(user)
    counts = await hard_delete_organization(org_id, user["email"])
    if counts.get("organizations", 0) == 0:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {"success": True, "org_id": org_id, "purged": counts}


@router.post("/master-admin/archive/sweep")
async def sweep_archive(user: dict = Depends(get_current_user)) -> dict:
    """Manually trigger the archive lifecycle sweep (normally runs every 5 min)."""
    _require_master_admin(user)
    counts = await run_archive_lifecycle_once()
    return {"success": True, **counts}
