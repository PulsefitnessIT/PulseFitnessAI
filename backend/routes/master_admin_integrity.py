"""Iter 216h273 — Master Admin Org Integrity Audit.

Follow-on to h272 (where the GymAxis Master Admin home org doc had
been deleted out from under the user and the operator-facing
Memberships / CRM / Marketing pages all rendered "Organisation
not found").

h272 fixed the **specific** orphan case for the master admin user.
This iter generalises: a single read-only endpoint sweeps the
`users` collection and reports every user whose `organization_id`
points at a missing org doc. Lets the master admin catch zombie
staff (e.g. left behind by a half-completed tenant deletion)
before they show up as user-facing 404s.

Endpoint:
    GET  /api/master-admin/integrity/org-integrity
         → {
             "total_users": int,
             "orphan_users_count": int,
             "orphan_users": [
                 {"id", "email", "full_name", "role", "organization_id",
                  "is_master_admin", "created_at"}
             ],
             "checked_at": ISO,
           }

Read-only. Does NOT auto-heal — h272's self-heal handles the
master admin specifically, and we don't want to silently re-create
tenant orgs for paying customers (that'd mask real data corruption).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from utils.auth import get_current_user
from routes.master_admin import require_master_admin


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin", tags=["Master Admin"])


@router.get("/integrity/org-integrity")
async def org_integrity_report(user: dict = Depends(get_current_user)) -> dict:
    """List every user whose `organization_id` no longer resolves
    to a real org doc. Master admin only — surface is privileged
    because the response includes raw user records across tenants.
    """
    require_master_admin(user)

    # Collect every org id that actually exists. Single round-trip,
    # cheap on a few thousand orgs. We use a projection to keep
    # the payload small.
    org_ids: set[str] = set()
    async for o in db.organizations.find({}, {"_id": 0, "id": 1}):
        if o.get("id"):
            org_ids.add(o["id"])

    orphans: list[dict] = []
    total_users = 0
    async for u in db.users.find(
        {},
        {
            "_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1,
            "organization_id": 1, "is_master_admin": 1, "active": 1,
            "created_at": 1,
        },
    ):
        total_users += 1
        oid = u.get("organization_id")
        # Two valid kinds of "no org pointer":
        #   - users with no organization_id at all (legacy / partial fixtures)
        #   - users pointing at a deleted org (the h272 case)
        # Both are surfaced so the master admin can clean them up.
        if not oid or oid not in org_ids:
            orphans.append({
                "id": u.get("id"),
                "email": u.get("email"),
                "full_name": u.get("full_name"),
                "role": u.get("role"),
                "organization_id": oid,
                "is_master_admin": bool(u.get("is_master_admin")),
                "active": bool(u.get("active", True)),
                "missing_reason": "no_organization_id" if not oid else "org_doc_missing",
            })

    return {
        "total_users": total_users,
        "total_orgs": len(org_ids),
        "orphan_users_count": len(orphans),
        "orphan_users": orphans,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/integrity/orphan-users/{user_id}")
async def delete_orphan_user(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Manually clean up an orphan user. Master admin only. Refuses
    to delete users whose `organization_id` actually resolves (so a
    typo or stale audit can't be turned into accidental data loss)."""
    require_master_admin(user)

    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "id": 1, "email": 1, "organization_id": 1, "is_master_admin": 1},
    )
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("is_master_admin"):
        raise HTTPException(403, "Refusing to delete a master admin user via the audit endpoint")

    oid = target.get("organization_id")
    if oid:
        org_exists = await db.organizations.find_one({"id": oid}, {"_id": 0, "id": 1})
        if org_exists:
            raise HTTPException(
                409,
                f"User {target.get('email')} is NOT an orphan — their organization {oid} exists. "
                "Refusing to delete via the audit endpoint (use the regular user management tools).",
            )

    res = await db.users.delete_one({"id": user_id})
    logger.info(
        "[org-integrity] master_admin=%s deleted orphan user=%s email=%s",
        user.get("id"), user_id, target.get("email"),
    )
    return {"deleted": res.deleted_count == 1, "user_id": user_id, "email": target.get("email")}


# ── Iter 216h276 — manual tenant→CRM mirror reconcile ─────────────


@router.post("/integrity/tenant-mirror-reconcile")
async def reconcile_tenant_mirror(user: dict = Depends(get_current_user)) -> dict:
    """Force-mirror every Pulse tenant into the master admin's CRM
    Companies. Idempotent. Use after a bulk import / restore when
    the auto-mirror on boot might've missed rows.

    Returns:
      {created, updated, marked_former, skipped, pulse_tenants_found}
    """
    require_master_admin(user)
    from utils.tenant_mirror import mirror_pulse_tenants_to_crm
    summary = await mirror_pulse_tenants_to_crm()
    logger.info("[org-integrity] master_admin=%s ran manual tenant-mirror reconcile: %s",
                user.get("id"), summary)
    return summary
