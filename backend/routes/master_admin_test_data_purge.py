"""Master Admin · Purge leaked test/demo data.

A boot-time seed (``seed_test_accounts``) historically ran on every startup
and upserted regression fixtures — most notably the test user
``lee.somers@pulsefitness.com`` and its org ``Pulse Fitness — Somers (test)``
— into whichever DB the process pointed at, INCLUDING production. That seed is
now hard-gated off in production, but this tool cleans up records that already
spilled.

Endpoints (master-admin gated):
  * GET  /master-admin/test-data/candidates  — list detected test orgs/users
  * POST /master-admin/test-data/purge       — delete them (dry_run supported)

Guards: never touches a system org (owns a master-admin user) or the pinned
operator company. Every purge writes a full snapshot to ``test_data_purge_audit``
plus an ``admin_activity_log`` entry.
"""
from datetime import datetime, timezone
import re
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import log_activity, require_master_admin

router = APIRouter()

# Known regression fixtures seeded by bootstrap/seed.py::seed_test_accounts +
# the demo-seed org names. Matched case-insensitively.
_TEST_USER_EMAILS = ["lee.somers@pulsefitness.com"]
_TEST_ORG_NAME_PATTERNS = [
    r"\(test\)",            # "Pulse Fitness — Somers (test)"
    r"—\s*somers",          # the specific Somers test org
    r"^iso\s*demo",         # iso-demo demo-seed orgs
    r"demo\s*fitness",
]

# Sites left behind by test onboarding (e.g. "TESTONB5-… Org Head Office")
# or demo seeds ("Demo Branch B"). These get wrongly attached to a real org
# and linger in the org drawer's Sites tab after the test org is deleted.
_TEST_SITE_NAME_PATTERNS = [
    r"testonb",             # "TESTONB5-67edff Org Head Office"
    r"\(test\)",
    r"—\s*somers",
    r"^iso\s*demo",
    r"demo\s*branch",       # "Demo Branch B"
    r"demo\s*head\s*office",
]

_SKIP_COLLECTIONS = {
    "organizations", "admin_activity_log", "org_cleanup_audit",
    "test_data_purge_audit", "system.indexes", "system.views",
}
_ORG_KEYS = ("organization_id", "org_id")


async def _is_system_org(org_id: str) -> bool:
    return bool(await db.users.find_one(
        {"organization_id": org_id, "is_master_admin": True}, {"_id": 1}
    ))


async def _detect_test_orgs() -> list[dict]:
    name_regex = {"$regex": "|".join(_TEST_ORG_NAME_PATTERNS), "$options": "i"}
    return await db.organizations.find({"name": name_regex}, {"_id": 0}).to_list(200)


async def _detect_test_users() -> list[dict]:
    email_regex = {"$regex": "|".join(re.escape(e) for e in _TEST_USER_EMAILS), "$options": "i"}
    return await db.users.find({"email": email_regex}, {"_id": 0, "password": 0}).to_list(200)


async def _detect_test_sites() -> list[dict]:
    """Sites that are either (a) named like test/demo fixtures or (b) orphaned
    — their organization_id no longer exists in `organizations`. Each is
    annotated with a `reason` and the owning org name (if any)."""
    org_ids = {o["id"] async for o in db.organizations.find({}, {"_id": 0, "id": 1})}
    org_names = {}
    async for o in db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}):
        org_names[o["id"]] = o.get("name")
    name_regex = re.compile("|".join(_TEST_SITE_NAME_PATTERNS), re.IGNORECASE)
    out = []
    async for s in db.sites.find({}, {"_id": 0}):
        name = s.get("name") or ""
        oid = s.get("organization_id")
        is_named = bool(name_regex.search(name))
        is_orphan = oid not in org_ids
        if not (is_named or is_orphan):
            continue
        out.append({
            "id": s.get("id"),
            "name": name,
            "organization_id": oid,
            "org_name": org_names.get(oid),
            "reason": "orphaned (org deleted)" if is_orphan else "test/demo name",
        })
    return out


@router.get("/master-admin/test-data/candidates")
async def test_data_candidates(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    orgs, users = await _detect_test_orgs(), await _detect_test_users()
    org_items = []
    for o in orgs:
        oid = o.get("id")
        protected = await _is_system_org(oid) or bool(o.get("is_operator_company"))
        org_items.append({
            "id": oid,
            "name": o.get("name"),
            "account_type": o.get("account_type"),
            "protected": protected,
            "protected_reason": (
                "system org (owns a master admin)" if await _is_system_org(oid)
                else "pinned operator company" if o.get("is_operator_company") else None
            ),
        })
    user_items = [{
        "id": u.get("id"), "email": u.get("email"),
        "full_name": u.get("full_name"), "organization_id": u.get("organization_id"),
        "is_master_admin": bool(u.get("is_master_admin")),
    } for u in users]
    sites = await _detect_test_sites()
    return {"organizations": org_items, "users": user_items, "sites": sites}


@router.post("/master-admin/test-data/purge")
async def purge_test_data(body: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Delete detected test orgs (+ all their org-scoped data) and test users.

    Body: { dry_run: bool=True, org_ids?: [str], user_ids?: [str] }
    When org_ids/user_ids are omitted, ALL auto-detected candidates are targeted.
    Protected orgs (system / pinned operator) are always skipped.
    """
    require_master_admin(user)
    dry_run = bool(body.get("dry_run", True))
    only_org_ids = set(body.get("org_ids") or [])
    only_user_ids = set(body.get("user_ids") or [])
    only_site_ids = set(body.get("site_ids") or [])

    orgs = await _detect_test_orgs()
    users = await _detect_test_users()
    if only_org_ids:
        orgs = [o for o in orgs if o.get("id") in only_org_ids]
    if only_user_ids:
        users = [u for u in users if u.get("id") in only_user_ids]

    collection_names = [c for c in await db.list_collection_names() if c not in _SKIP_COLLECTIONS]

    org_results = []
    for org in orgs:
        oid = org.get("id")
        if await _is_system_org(oid) or org.get("is_operator_company"):
            org_results.append({"org_id": oid, "org_name": org.get("name"), "skipped": "protected"})
            continue
        removed: dict = {}
        for c in collection_names:
            for key in _ORG_KEYS:
                try:
                    match = {key: oid}
                    if dry_run:
                        n = await db[c].count_documents(match)
                    else:
                        n = (await db[c].delete_many(match)).deleted_count
                except Exception:
                    n = 0
                if n:
                    removed[f"{c}.{key}"] = removed.get(f"{c}.{key}", 0) + n
        entry = {"org_id": oid, "org_name": org.get("name"), "removed": removed}
        if not dry_run:
            await db.test_data_purge_audit.insert_one({
                "id": str(uuid.uuid4()), "action": "purge_test_org",
                "org_snapshot": org, "removed": removed,
                "admin_email": user.get("email", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await db.organizations.delete_one({"id": oid})
            await log_activity(
                "test_data_purge",
                f"Purged test org '{org.get('name')}' ({sum(removed.values())} records)",
                user.get("email", ""), "organization", oid,
            )
        org_results.append(entry)

    # Standalone test users not already removed via their org purge.
    user_results = []
    for u in users:
        uid = u.get("id")
        if u.get("is_master_admin"):
            user_results.append({"user_id": uid, "email": u.get("email"), "skipped": "master_admin"})
            continue
        still = await db.users.find_one({"id": uid}, {"_id": 1})
        if dry_run:
            user_results.append({"user_id": uid, "email": u.get("email"), "would_delete": bool(still)})
        else:
            if still:
                await db.users.delete_one({"id": uid})
                await log_activity(
                    "test_data_purge", f"Purged test user '{u.get('email')}'",
                    user.get("email", ""), "user", uid,
                )
            user_results.append({"user_id": uid, "email": u.get("email"), "deleted": bool(still)})

    # Test / orphaned sites (e.g. "TESTONB5-… Head Office", "Demo Branch B")
    # that lingered under a real org after their test org was deleted.
    sites = await _detect_test_sites()
    if only_site_ids:
        sites = [s for s in sites if s.get("id") in only_site_ids]
    site_results = []
    for s in sites:
        sid = s.get("id")
        if dry_run:
            site_results.append({
                "site_id": sid, "name": s.get("name"), "org_name": s.get("org_name"),
                "reason": s.get("reason"), "would_delete": True,
            })
            continue
        # Remove the site + its site-scoped equipment/issues so nothing dangles.
        eq = (await db.equipment.delete_many({"site_id": sid})).deleted_count
        iss = (await db.issues.delete_many({"site_id": sid})).deleted_count
        deleted = (await db.sites.delete_one({"id": sid})).deleted_count > 0
        await db.test_data_purge_audit.insert_one({
            "id": str(uuid.uuid4()), "action": "purge_test_site",
            "site_snapshot": s, "removed_equipment": eq, "removed_issues": iss,
            "admin_email": user.get("email", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await log_activity(
            "test_data_purge",
            f"Purged {s.get('reason')} site '{s.get('name')}' (eq={eq}, issues={iss})",
            user.get("email", ""), "site", sid,
        )
        site_results.append({
            "site_id": sid, "name": s.get("name"), "org_name": s.get("org_name"),
            "reason": s.get("reason"), "deleted": deleted,
            "removed_equipment": eq, "removed_issues": iss,
        })

    return {"dry_run": dry_run, "organizations": org_results,
            "users": user_results, "sites": site_results}
