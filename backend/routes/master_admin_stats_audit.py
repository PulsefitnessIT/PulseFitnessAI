"""
Master Admin · platform stats + audit-log sub-router.

Iter 216h182 — Extracted from `routes/master_admin.py` as phase 6 of
the 4,283 LoC → focused-routers decomposition.

Owns two compliance-adjacent surfaces:

    GET /master-admin/stats              — global counts / MRR / 6-month growth
    GET /master-admin/audit-logs         — paginated audit search
    GET /master-admin/audit-logs/facets  — distinct values for filter dropdowns
    GET /master-admin/audit-logs/export.csv — streamed CSV export

Helpers `_get_platform_counts`, `_get_subscription_stats`, and
`_get_growth_data` travel with the stats endpoint (they're not used
anywhere else).

`_resolve_pulse_scope_org_ids` stays on `routes.master_admin` because
`routes/sites.py` and `routes/assistant.py` import it directly; we
re-import it here as a regular dependency rather than redefining.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from utils.security_plus import safe_regex

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    _resolve_pulse_scope_org_ids,
    require_master_admin,
)


router = APIRouter()


# ───────────── stats helpers ─────────────

async def _get_platform_counts(org_ids: Optional[list[str]] = None) -> dict:
    """Fetch core platform entity counts.

    When ``org_ids`` is provided (Pulse-scoped admins), every count is filtered
    by ``organization_id ∈ org_ids``. ``None`` means platform-wide (GymAxis
    master view).
    """
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    return {
        "total_users": await db.users.count_documents(scoped_q),
        "total_organizations": await db.organizations.count_documents(org_q),
        "active_orgs": await db.organizations.count_documents({**org_q, "status": {"$in": ["active", None]}}),
        "trial_orgs": await db.organizations.count_documents({**org_q, "status": "trial"}),
        "suspended_orgs": await db.organizations.count_documents({**org_q, "status": "suspended"}),
        "cancelled_orgs": await db.organizations.count_documents({**org_q, "status": "cancelled"}),
        "total_equipment": await db.equipment.count_documents(scoped_q),
        "total_issues": await db.issues.count_documents(scoped_q),
        "open_issues": await db.issues.count_documents({**scoped_q, "status": "open"}),
        "resolved_issues": await db.issues.count_documents({**scoped_q, "status": {"$in": ["resolved", "closed"]}}),
        "total_files": await db.files.count_documents(scoped_q),
        "total_purchase_orders": await db.purchase_orders.count_documents(scoped_q),
        "total_supplier_cases": await db.supplier_cases.count_documents(scoped_q),
    }


async def _get_subscription_stats(org_ids: Optional[list[str]] = None) -> tuple[dict, int]:
    """Fetch subscription breakdown and MRR (excluding test accounts).

    Same scoping semantics as ``_get_platform_counts``.
    """
    non_test = {"is_test": {"$ne": True}}
    if org_ids is not None:
        non_test["id"] = {"$in": org_ids}
    subs = {
        "free": await db.organizations.count_documents({**non_test, "subscription_tier": {"$in": ["free", None, ""]}}),
        "pro": await db.organizations.count_documents({**non_test, "subscription_tier": "pro"}),
        "premium": await db.organizations.count_documents({**non_test, "subscription_tier": "premium"}),
        "enterprise": await db.organizations.count_documents({**non_test, "subscription_tier": "enterprise"}),
    }
    mrr = (subs["pro"] * 49) + (subs["premium"] * 99) + (subs["enterprise"] * 199)
    return subs, mrr


async def _get_growth_data(mrr: int, org_ids: Optional[list[str]] = None) -> list:
    """Build 6-month growth timeline (org_id-scoped when ``org_ids`` is set)."""
    org_q: dict = {}
    scoped_q: dict = {}
    if org_ids is not None:
        org_q = {"id": {"$in": org_ids}}
        scoped_q = {"organization_id": {"$in": org_ids}}
    data = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=30 * i)
        month_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = (month_start + timedelta(days=32)).replace(day=1) if i > 0 else datetime.now(timezone.utc)
        data.append({
            "month": month_start.strftime("%b %Y"),
            "users": await db.users.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "organizations": await db.organizations.count_documents({**org_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "issues": await db.issues.count_documents({**scoped_q, "created_at": {"$lte": cutoff.isoformat()}}),
            "mrr": mrr,
        })
    return data


async def _resolve_module_org_ids(module: str, base_org_ids: Optional[list[str]]) -> list[str]:
    """Return the org ids that have the given product module enabled.

    Iter 220o — powers the per-module Master-Admin overview tabs (e.g.
    Operations Portal must show ONLY operations-enabled orgs, not the
    whole platform). Mirrors ``utils.module_access`` defaults at the
    query level:

      • operations — enabled for every non-MOD org unless explicitly
        switched off (``modules.operations.enabled == False``). MOD
        orgs (mod_site/mod_branch/mod_org) never carry the gym modules.
      • memberships / marketing / crm — bolt-ons, so only count orgs
        with an explicit ``modules.<key>.enabled == True``.

    When ``base_org_ids`` is set (a Pulse-scoped admin) the result is
    intersected with that scope.
    """
    if module == "operations":
        q: dict = {
            "account_type": {"$nin": ["mod_site", "mod_branch", "mod_org"]},
            "modules.operations.enabled": {"$ne": False},
        }
    else:
        q = {f"modules.{module}.enabled": True}
    if base_org_ids is not None:
        q["id"] = {"$in": base_org_ids}
    docs = await db.organizations.find(q, {"id": 1}).to_list(length=None)
    return [d["id"] for d in docs if d.get("id")]


@router.get("/master-admin/stats")
async def get_master_stats(user: dict = Depends(get_current_user), module: Optional[str] = None):
    require_master_admin(user)
    org_ids = await _resolve_pulse_scope_org_ids(user)
    # Iter 220o — optional per-module scoping for the Operations-only
    # overview. A module filter narrows org_ids to that module's orgs
    # (intersected with any Pulse scope), so every downstream count is
    # module-scoped via the existing helpers.
    if module in ("operations", "memberships", "marketing", "crm"):
        org_ids = await _resolve_module_org_ids(module, org_ids)
    counts = await _get_platform_counts(org_ids)
    subs, mrr = await _get_subscription_stats(org_ids)
    issue_q: dict = {"ai_triage": {"$exists": True, "$ne": None}}
    audit_q: dict = {}
    payment_succ_q: dict = {"status": "succeeded"}
    payment_fail_q: dict = {"status": "failed"}
    if org_ids is not None:
        issue_q["organization_id"] = {"$in": org_ids}
        audit_q["organization_id"] = {"$in": org_ids}
        payment_succ_q["organization_id"] = {"$in": org_ids}
        payment_fail_q["organization_id"] = {"$in": org_ids}
    ai_calls = await db.issues.count_documents(issue_q)
    ai_audits = await db.audits.count_documents(audit_q)

    return {
        **counts,
        "mrr": mrr,
        "subscriptions": subs,
        "ai_usage": {"triage_calls": ai_calls, "audit_reports": ai_audits, "total": ai_calls + ai_audits},
        "payments": {
            "total": await db.payment_transactions.count_documents(payment_succ_q),
            "failed": await db.payment_transactions.count_documents(payment_fail_q),
        },
        "growth_data": await _get_growth_data(mrr, org_ids),
        "scoped": org_ids is not None,
    }


# ── Audit-log viewer · Iter 216h161 ─────────────────────────────
#
# Compliance surface over the `audit_logs` collection populated by
# `utils.audit.audit_log()`. Filterable + paginated + CSV export so
# enterprise procurement / SOC2 auditors can pull "every action by
# this user in 2026" in one click.

@router.get("/master-admin/audit-logs")
async def list_audit_logs(
    user: dict = Depends(get_current_user),
    q: str = "",
    action: str = "",
    user_id: str = "",
    user_email: str = "",
    resource_type: str = "",
    resource_id: str = "",
    since: str = "",   # ISO date or datetime
    until: str = "",
    skip: int = 0,
    limit: int = 50,
):
    """Paginated audit-log search. Master-admin only."""
    require_master_admin(user)
    limit = max(1, min(limit, 500))
    skip = max(skip, 0)
    query: dict = {}
    if action:
        query["action"] = safe_regex(action)
    if user_id:
        query["user_id"] = user_id
    if user_email:
        query["user_email"] = safe_regex(user_email)
    if resource_type:
        query["resource_type"] = resource_type
    if resource_id:
        query["resource_id"] = resource_id
    if since or until:
        ts: dict = {}
        if since:
            ts["$gte"] = since
        if until:
            ts["$lte"] = until
        query["timestamp"] = ts
    if q:
        # Free-text — search across action, email, details, resource id.
        query.setdefault("$or", []).extend([
            {"action": safe_regex(q)},
            {"user_email": safe_regex(q)},
            {"details": safe_regex(q)},
            {"resource_id": safe_regex(q)},
        ])
    cursor = db.audit_logs.find(
        query, {"_id": 0},
    ).sort([("timestamp", -1)]).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    total = await db.audit_logs.count_documents(query)
    return {"rows": rows, "total": total, "skip": skip, "limit": limit}


@router.get("/master-admin/audit-logs/facets")
async def list_audit_facets(user: dict = Depends(get_current_user)):
    """Distinct actions + resource_types so the UI can render filter
    dropdowns without scanning the full collection."""
    require_master_admin(user)
    actions = await db.audit_logs.distinct("action")
    resource_types = await db.audit_logs.distinct("resource_type")
    return {
        "actions": sorted([a for a in actions if a])[:500],
        "resource_types": sorted([r for r in resource_types if r])[:200],
    }


@router.get("/master-admin/audit-logs/export.csv")
async def export_audit_logs_csv(
    user: dict = Depends(get_current_user),
    q: str = "",
    action: str = "",
    user_email: str = "",
    resource_type: str = "",
    since: str = "",
    until: str = "",
    limit: int = 10000,
):
    """Stream a filtered audit-log slice as CSV. Same query semantics
    as the JSON list endpoint, but capped at 10k rows by default to
    keep response time bounded."""
    require_master_admin(user)
    import csv
    import io
    from fastapi.responses import StreamingResponse

    limit = max(1, min(limit, 50000))
    query: dict = {}
    if action:
        query["action"] = safe_regex(action)
    if user_email:
        query["user_email"] = safe_regex(user_email)
    if resource_type:
        query["resource_type"] = resource_type
    if since or until:
        ts: dict = {}
        if since:
            ts["$gte"] = since
        if until:
            ts["$lte"] = until
        query["timestamp"] = ts
    if q:
        query.setdefault("$or", []).extend([
            {"action": safe_regex(q)},
            {"user_email": safe_regex(q)},
            {"details": safe_regex(q)},
            {"resource_id": safe_regex(q)},
        ])
    rows = await db.audit_logs.find(
        query, {"_id": 0},
    ).sort([("timestamp", -1)]).limit(limit).to_list(limit)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action", "user_email", "user_id",
                     "resource_type", "resource_id", "details", "ip_address"])
    for r in rows:
        writer.writerow([
            r.get("timestamp", ""), r.get("action", ""), r.get("user_email", ""),
            r.get("user_id", ""), r.get("resource_type", ""), r.get("resource_id", ""),
            (r.get("details", "") or "").replace("\n", " ").replace("\r", " "),
            r.get("ip_address", ""),
        ])
    buf.seek(0)
    fname = f"audit-logs-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
