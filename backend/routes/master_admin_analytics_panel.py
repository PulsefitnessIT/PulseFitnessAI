"""
Master Admin · Analytics sub-router.

Iter 216h177 — Extracted from `routes/master_admin.py`.

Owns observability-style endpoints that are read-only / aggregated:
    GET /master-admin/activity-log
    GET /master-admin/ai-usage
    GET /master-admin/emails-legacy

The newer outbound-email surface lives in `routes/email_health.py`; the
legacy `/emails-legacy` route is kept under its renamed path purely for
backwards compatibility with any old integration that hasn't migrated.
"""
import asyncio

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import require_master_admin


router = APIRouter()


@router.get("/master-admin/activity-log")
async def get_activity_log(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    admin_logs = await db.admin_activity_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(200)

    recent_users = await db.users.find(
        {"last_login": {"$exists": True}},
        {"_id": 0, "email": 1, "full_name": 1, "last_login": 1, "organization_id": 1},
    ).sort("last_login", -1).to_list(50)
    login_logs = [
        {
            "action": "user_login",
            "details": f"{u.get('full_name', u['email'])} logged in",
            "admin_email": u["email"],
            "timestamp": u["last_login"],
            "target_type": "user",
        }
        for u in recent_users
        if u.get("last_login")
    ]

    all_logs = admin_logs + login_logs
    all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"logs": all_logs[:200]}


@router.get("/master-admin/ai-usage")
async def get_ai_usage(user: dict = Depends(get_current_user)):
    require_master_admin(user)

    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    if not orgs:
        return {"usage": [], "total_calls": 0}

    org_ids = [o["id"] for o in orgs]

    async def _group(coll, match=None):
        pipe = [{"$match": {"organization_id": {"$in": org_ids}}}]
        if match:
            pipe.append({"$match": match})
        pipe.append({"$group": {"_id": "$organization_id", "c": {"$sum": 1}}})
        return {d["_id"]: d["c"] for d in await coll.aggregate(pipe).to_list(length=None)}

    triage_map, audit_map, ra_map = await asyncio.gather(
        _group(db.issues, {"ai_triage": {"$exists": True, "$ne": None}}),
        _group(db.audits),
        _group(db.risk_assessments),
    )

    usage = []
    for org in orgs:
        oid = org["id"]
        triage = triage_map.get(oid, 0)
        audits = audit_map.get(oid, 0)
        ra = ra_map.get(oid, 0)
        total = triage + audits + ra
        if total > 0:
            usage.append({
                "org_id": oid,
                "org_name": org["name"],
                "triage_calls": triage,
                "audit_reports": audits,
                "risk_assessments": ra,
                "total_calls": total,
                "estimated_cost": round(total * 0.03, 2),
            })
    usage.sort(key=lambda x: x["total_calls"], reverse=True)
    return {"usage": usage, "total_calls": sum(u["total_calls"] for u in usage)}


@router.get("/master-admin/emails-legacy")
async def get_email_log(user: dict = Depends(get_current_user)):
    """Iter 216h99 — deprecated. The Outbound emails panel now reads
    from ``email_send_events`` via ``email_health.list_outbound_emails``.
    Kept here under a renamed path in case an old integration still
    points at it.
    """
    require_master_admin(user)
    cases = await db.supplier_cases.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    emails = []
    for c in cases:
        emails.append({
            "id": c.get("id", ""),
            "type": "supplier_case",
            "to": c.get("supplier_email", ""),
            "subject": f"Fault Report — {c.get('serial_number', '')}",
            "status": c.get("status", "sent"),
            "org_id": c.get("organization_id", ""),
            "created_at": c.get("created_at", ""),
        })

    pos = await db.purchase_orders.find({"emailed": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for po in pos:
        emails.append({
            "id": po.get("id", ""),
            "type": "purchase_order",
            "to": po.get("supplier_email", ""),
            "subject": f"Purchase Order — {po.get('po_number', '')}",
            "status": "sent",
            "org_id": po.get("organization_id", ""),
            "created_at": po.get("created_at", ""),
        })

    emails.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"emails": emails}
