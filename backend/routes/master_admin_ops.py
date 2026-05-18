"""
Master Admin · ops + backfills sub-router.

Iter 216h186 — Extracted from `routes/master_admin.py` as phase 10
(FINAL) of the 4,283 LoC → focused-routers decomposition.

Owns the 5 ops/admin housekeeping endpoints that don't fit any other
domain bucket:

    POST /master-admin/test-data/purge                      — seeded/demo data wipe
    GET  /master-admin/all-sites                            — cross-org site rollup
    GET  /master-admin/users/locked-sites                   — locked-staff compliance audit
    POST /master-admin/equipment/backfill-pulse-supplier    — Pulse supplier backfill
    POST /master-admin/equipment/backfill-spec-sheets       — spec-sheet auto-match backfill

Shared helpers (`is_pulse_only`, `log_activity`, `require_master_admin`)
stay on `routes.master_admin` because they're used by ~12 modules.

After this iteration `routes/master_admin.py` is a PURE helper module
with zero routes of its own — it owns the cross-module helper exports
(`require_master_admin`, `assert_org_in_pulse_scope`,
`assert_user_in_pulse_scope`, `_create_org_user`, `_mint_invite_link`,
`merge_address`, `log_activity`, etc.) that every sub-router depends on.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    is_pulse_only,
    log_activity,
    require_master_admin,
)


router = APIRouter()


# ─── Test Data Purge ────────────────────────────────────────────────
@router.post("/master-admin/test-data/purge")
async def purge_test_data(
    user: dict = Depends(get_current_user),
    payload: dict = Body(default={}),
):
    """
    Wipe seeded/demo/test data so the platform reflects real activity only.
    Master-admin only. Purges by default:
      - revenue_distributions + reserve_transactions (so Monthly Revenue resets)
      - demo faults, demo equipment, demo jobs, demo contracts
      - any record with {is_test: true} or {seed: true}
    Pass {"collections": [...]} to override the default list.
    """
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    # Default collections that accumulate platform-activity test data
    default_collections = [
        "revenue_distributions",
        "reserve_transactions",
        "llm_top_up_log",
        "financial_alerts",
    ]
    collections = payload.get("collections", default_collections)

    # Protected — never wipe these even if passed
    PROTECTED = {"users", "organizations", "stripe_webhook_events", "audit_log", "master_admin_activity_log"}
    results = {}

    for coll_name in collections:
        if coll_name in PROTECTED:
            results[coll_name] = {"skipped": True, "reason": "protected"}
            continue
        try:
            res = await db[coll_name].delete_many({})
            results[coll_name] = {"deleted": res.deleted_count}
        except Exception as e:
            results[coll_name] = {"error": str(e)}

    # Also clear any document flagged as test/seed across the whole database
    flagged_total = 0
    for coll_name in ["faults", "equipment", "jobs", "contracts", "job_cards", "ppm_sheets", "check_sheets"]:
        try:
            res = await db[coll_name].delete_many({"$or": [{"is_test": True}, {"seed": True}, {"demo": True}]})
            if res.deleted_count:
                results[f"{coll_name}_flagged"] = {"deleted": res.deleted_count}
                flagged_total += res.deleted_count
        except Exception:
            pass

    await log_activity(
        "test_data_purged",
        f"Purged: {sum(r.get('deleted',0) for r in results.values() if isinstance(r, dict))} docs, flagged: {flagged_total}",
        user.get("email", ""),
        "platform",
        "",
    )
    return {"success": True, "flagged_total": flagged_total, "results": results}


@router.get("/master-admin/all-sites")
async def all_sites_across_orgs(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    site_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 500,
):
    """Iter 216h23 — Cross-organisation physical-sites list.

    Lives at `Master Admin → Organisations → All sites` sub-tab. Solves
    the "where are all my Pulse sites?" question without breaking the
    SSoT principle (a Site still belongs to exactly one Organisation —
    this is just a flat power-view across all orgs).

    Per-row enrichments:
      • org_name / org_brand  — joined from `organizations`.
      • equipment_count       — `equipment` docs scoped to (org_id, site_id).
      • members_count         — `members` (or `crm_users`) scoped likewise.
      • is_head_office        — direct from the site doc.
      • last_activity         — most recent of any audit_logs / issues
                                / check_sheet_instances touching the site.

    Brand scope: Pulse-only admins receive only Pulse-brand sites.
    Query filters: `org_id`, `site_type`, free-text `q` (matches name).
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause

    # Org scope (Pulse-only admins are pinned to Pulse-brand orgs).
    pulse_only = is_pulse_only(user)
    org_filter: dict = {}
    if pulse_only:
        org_filter = brand_filter_clause("pulse")
    if org_id:
        org_filter = {**org_filter, "id": org_id}

    orgs = await db.organizations.find(
        org_filter, {"_id": 0, "id": 1, "name": 1, "brand": 1},
    ).to_list(2000)
    org_index = {o["id"]: o for o in orgs}
    if not org_index:
        return {"sites": [], "totals": {"sites": 0, "head_offices": 0, "branches": 0, "equipment": 0}}

    site_query: dict = {"organization_id": {"$in": list(org_index.keys())}}
    if site_type == "head_office":
        site_query["is_head_office"] = True
    elif site_type == "branch":
        site_query["is_head_office"] = {"$ne": True}
    if q:
        site_query["name"] = {"$regex": q, "$options": "i"}

    sites = await db.sites.find(site_query, {"_id": 0}).sort([("organization_id", 1), ("name", 1)]).to_list(limit)

    # Bulk equipment counts per (org, site).
    eq_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    eq_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.equipment.aggregate(eq_pipeline)}

    # Bulk member counts per site (best-effort — schema varies by tenant).
    mem_pipeline = [
        {"$match": {"organization_id": {"$in": list(org_index.keys())}, "site_id": {"$exists": True}}},
        {"$group": {"_id": {"org": "$organization_id", "site": "$site_id"}, "n": {"$sum": 1}}},
    ]
    mem_counts = {(d["_id"]["org"], d["_id"]["site"]): d["n"] async for d in db.members.aggregate(mem_pipeline)}

    enriched = []
    head_office_count = 0
    branch_count = 0
    total_equipment = 0
    for s in sites:
        org = org_index.get(s.get("organization_id"), {})
        is_hq = bool(s.get("is_head_office"))
        head_office_count += 1 if is_hq else 0
        branch_count += 0 if is_hq else 1
        eq = eq_counts.get((s.get("organization_id"), s.get("id")), 0)
        total_equipment += eq
        enriched.append({
            "id":              s.get("id"),
            "name":            s.get("name"),
            "organization_id": s.get("organization_id"),
            "org_name":        org.get("name") or "—",
            "org_brand":       org.get("brand") or "gymaxis",
            "is_head_office":  is_hq,
            "site_type":       s.get("site_type") or ("head_office" if is_hq else "branch"),
            "city":            s.get("city") or s.get("address", {}).get("city") if isinstance(s.get("address"), dict) else s.get("city"),
            "postcode":        s.get("postcode") or (s.get("address") or {}).get("postcode") if isinstance(s.get("address"), dict) else s.get("postcode"),
            "active":          s.get("active", True),
            "equipment_count": eq,
            "members_count":   mem_counts.get((s.get("organization_id"), s.get("id")), 0),
            "created_at":      s.get("created_at"),
        })

    return {
        "sites": enriched,
        "totals": {
            "sites":         len(enriched),
            "head_offices":  head_office_count,
            "branches":      branch_count,
            "equipment":     total_equipment,
        },
        "brand": "pulse" if pulse_only else "all",
    }


# ──────────────────────────────────────────────────────────────────────
# Iter 216bm — Locked-staff audit view
# ──────────────────────────────────────────────────────────────────────
@router.get("/master-admin/users/locked-sites")
async def locked_staff_audit(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    limit: int = 200,
):
    """List users with non-empty `allowed_site_ids` for compliance audit.

    Returned for every locked staff member: org name, full name, email,
    role, the names of the sites they're locked to, and the timestamp
    of the last permission change. Master-admin only.

    Query params:
      • `org_id` — narrow to a single organisation (optional)
      • `limit`  — max rows (default 200, hard-capped to 1000)
    """
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(status_code=403, detail="Master admin only")

    capped_limit = max(1, min(int(limit or 200), 1000))

    user_filter: dict = {
        "allowed_site_ids": {"$exists": True, "$ne": []},
    }
    if org_id:
        user_filter["organization_id"] = org_id

    user_docs = await db.users.find(
        user_filter,
        {
            "_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1,
            "organization_id": 1, "allowed_site_ids": 1,
            "permissions_updated_at": 1, "is_master_admin": 1,
        },
    ).limit(capped_limit).to_list(capped_limit)

    if not user_docs:
        return {"locked_staff": [], "total": 0}

    # Resolve org names + site names in one round-trip each. The lock
    # field is small enough that an explicit join is fine.
    org_ids = list({u["organization_id"] for u in user_docs if u.get("organization_id")})
    org_lookup = {
        o["id"]: o["name"]
        for o in await db.organizations.find(
            {"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(org_ids))
    }

    all_site_ids: set = set()
    for u in user_docs:
        for sid in (u.get("allowed_site_ids") or []):
            all_site_ids.add(sid)
    site_lookup = {
        s["id"]: {"name": s.get("name", "(unnamed)"), "is_head_office": bool(s.get("is_head_office"))}
        for s in await db.sites.find(
            {"id": {"$in": list(all_site_ids)}}, {"_id": 0, "id": 1, "name": 1, "is_head_office": 1}
        ).to_list(len(all_site_ids) or 1)
    }

    rows = []
    for u in user_docs:
        site_ids = u.get("allowed_site_ids") or []
        sites = [
            {"id": sid, "name": site_lookup.get(sid, {}).get("name", "(deleted site)"), "is_head_office": site_lookup.get(sid, {}).get("is_head_office", False)}
            for sid in site_ids
        ]
        rows.append({
            "user_id": u.get("id"),
            "full_name": u.get("full_name") or "(no name)",
            "email": u.get("email") or "",
            "role": u.get("role") or "staff",
            "is_master_admin": bool(u.get("is_master_admin")),
            "organization_id": u.get("organization_id"),
            "organization_name": org_lookup.get(u.get("organization_id", ""), "(unknown org)"),
            "site_count": len(sites),
            "sites": sites,
            "permissions_updated_at": u.get("permissions_updated_at"),
        })

    rows.sort(key=lambda r: r.get("permissions_updated_at") or "", reverse=True)
    return {"locked_staff": rows, "total": len(rows)}


# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Pulse Fitness supplier backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-pulse-supplier")
async def backfill_pulse_supplier(
    user: dict = Depends(get_current_user),
    dry_run: bool = False,
):
    """Set every piece of equipment in every Pulse Fitness Lite / Pro
    organisation's default supplier to "Pulse Fitness" with the
    service.dept@pulsefitness.com email. Master-admin only.

    `?dry_run=true` returns counts without writing.
    """
    require_master_admin(user)
    org_cursor = db.organizations.find(
        {"account_type": {"$in": ["lite", "pulse_pro"]}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1},
    )
    pulse_orgs = [o async for o in org_cursor]
    if not pulse_orgs:
        return {"orgs": 0, "equipment_updated": 0, "dry_run": dry_run}

    org_ids = [o["id"] for o in pulse_orgs]
    if dry_run:
        cnt = await db.equipment.count_documents({"organization_id": {"$in": org_ids}})
        return {"orgs": len(pulse_orgs), "equipment_to_update": cnt, "dry_run": True}

    result = await db.equipment.update_many(
        {"organization_id": {"$in": org_ids}},
        {"$set": {
            "supplier": "Pulse Fitness",
            "supplier_email": "service.dept@pulsefitness.com",
            "supplier_backfilled_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "orgs": len(pulse_orgs),
        "equipment_updated": int(result.modified_count or 0),
        "dry_run": False,
    }


# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — Spec-sheet attach backfill
# ──────────────────────────────────────────────────────────────────────
@router.post("/master-admin/equipment/backfill-spec-sheets")
async def backfill_spec_sheets(
    user: dict = Depends(get_current_user),
    org_id: Optional[str] = None,
    dry_run: bool = False,
):
    """Re-run the spec-sheet auto-match across existing equipment so
    rows uploaded before iter 216bn pick up matching catalogue entries.
    Master-admin only. `?org_id=` narrows to one organisation.
    """
    require_master_admin(user)
    from routes.spec_sheets import auto_match_equipment_to_specs

    eq_filter: dict = {
        "$or": [
            {"spec_sheet_id": {"$exists": False}},
            {"spec_sheet_id": ""},
            {"spec_sheet_id": None},
        ],
    }
    if org_id:
        eq_filter["organization_id"] = org_id

    cursor = db.equipment.find(eq_filter, {"_id": 0})
    eq_docs = await cursor.to_list(2000)

    matched = 0
    if dry_run:
        for eq in eq_docs:
            m = await auto_match_equipment_to_specs(eq)
            if m:
                matched += 1
        return {"considered": len(eq_docs), "matched": matched, "dry_run": True}

    for eq in eq_docs:
        m = await auto_match_equipment_to_specs(eq)
        if m:
            await db.equipment.update_one(
                {"id": eq["id"]},
                {"$set": {**m, "spec_sheet_attached_at": datetime.now(timezone.utc).isoformat()}},
            )
            matched += 1
    return {"considered": len(eq_docs), "matched": matched, "dry_run": False}
