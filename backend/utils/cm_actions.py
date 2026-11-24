"""Contract Management Action Centre — one coordinator work-item lifecycle.

Work items live in the existing ``crm2_activities`` collection (source
``afs_alerts``, so the existing Action Centre list shows them) with a stable
``dedupe_key``. Raising is idempotent; when the underlying problem is fixed
the sweep auto-resolves the item everywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from utils.database import db

ACTIVE_CONTRACT_STATUSES = ["draft", "active", "signed", "expiring", "renewal_pending_approval"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _assignee(org_id: str, contract: dict | None) -> dict:
    """Customer's assigned coordinator → contract coordinator → shared queue."""
    c = contract or {}
    if c.get("company_id"):
        co = await db.crm2_companies.find_one({"id": c["company_id"]}, {"_id": 0, "coordinator_id": 1, "coordinator_name": 1})
        if co and co.get("coordinator_id"):
            return {"owner_id": co["coordinator_id"], "owner_name": co.get("coordinator_name") or ""}
    if c.get("coordinator_id"):
        return {"owner_id": c["coordinator_id"], "owner_name": c.get("coordinator_name") or ""}
    return {"owner_id": "system", "owner_name": "Shared coordinator queue"}


async def ensure_indexes() -> None:
    await db.crm2_activities.create_index(
        [("organization_id", 1), ("dedupe_key", 1)], unique=True, name="uniq_org_dedupe_key",
        partialFilterExpression={"dedupe_key": {"$type": "string"}})


async def raise_action(org_id: str, dedupe_key: str, *, type_: str, subject: str, body: str,
                       contract: dict | None = None, extra: dict | None = None) -> str:
    """Create the work item once; re-raising refreshes it (and re-opens it
    if it had been auto-resolved and the problem came back)."""
    now = _now()
    existing = await db.crm2_activities.find_one({"organization_id": org_id, "dedupe_key": dedupe_key}, {"_id": 0})
    links = {"contract_id": (contract or {}).get("id"), "company_id": (contract or {}).get("company_id"),
             "contract_number": (contract or {}).get("contract_number")}
    if existing:
        upd = {"subject": subject, "body": body, "updated_at": now, **(extra or {})}
        if existing.get("status") != "open" and existing.get("auto_resolved"):
            upd.update({"status": "open", "auto_resolved": False, "reopened_at": now})
        await db.crm2_activities.update_one({"id": existing["id"]}, {"$set": upd})
        return existing["id"]
    act = {
        "id": str(uuid.uuid4()), "organization_id": org_id, "type": type_,
        "status": "open", "source": "afs_alerts", "category": "contract_admin",
        "dedupe_key": dedupe_key, "subject": subject, "body": body,
        **links, **(await _assignee(org_id, contract)),
        "created_at": now, "updated_at": now, **(extra or {}),
    }
    # Atomic: the unique (organization_id, dedupe_key) index means a
    # concurrent sweep that loses the race simply refreshes the winner's row.
    res = await db.crm2_activities.update_one(
        {"organization_id": org_id, "dedupe_key": dedupe_key}, {"$setOnInsert": act}, upsert=True)
    if res.upserted_id is None:
        return (await db.crm2_activities.find_one({"organization_id": org_id, "dedupe_key": dedupe_key}, {"_id": 0, "id": 1}))["id"]
    await db.crm2_notifications.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id, "type": "aftersales_alert",
        "read": False, "created_at": now, "activity_id": act["id"], "title": subject, "message": body,
    })
    return act["id"]


async def resolve_action(org_id: str, dedupe_key: str, reason: str) -> bool:
    r = await db.crm2_activities.update_one(
        {"organization_id": org_id, "dedupe_key": dedupe_key, "status": "open"},
        {"$set": {"status": "done", "auto_resolved": True, "resolution": reason,
                  "resolved_at": _now(), "updated_at": _now()}})
    return r.modified_count > 0


async def _customer_email(org_id: str, contract: dict) -> str:
    for cid in (contract.get("billing_contact_id"), contract.get("contact_id")):
        if cid:
            ct = await db.crm2_contacts.find_one({"id": cid}, {"_id": 0, "email": 1})
            if ct and ct.get("email"):
                return ct["email"]
    if contract.get("company_id"):
        ct = await db.crm2_contacts.find_one(
            {"organization_id": org_id, "company_id": contract["company_id"], "email": {"$nin": [None, ""]}},
            {"_id": 0, "email": 1})
        if ct:
            return ct["email"]
        co = await db.crm2_companies.find_one({"id": contract["company_id"]}, {"_id": 0, "email": 1})
        if co and co.get("email"):
            return co["email"]
    return ""


async def missing_fields(org_id: str, contract: dict) -> list[str]:
    out = []
    if not contract.get("start_date"):
        out.append("start_date")
    if not contract.get("end_date"):
        out.append("end_date")
    if not contract.get("billing_frequency"):
        out.append("billing_frequency")
    if contract.get("status") != "draft" and not float(contract.get("annual_value") or 0):
        out.append("annual_value")
    if not await _customer_email(org_id, contract):
        out.append("customer_email")
    return out


_LABELS = {"start_date": "start date", "end_date": "expiry date", "billing_frequency": "billing frequency",
           "annual_value": "contract value", "customer_email": "customer contact email"}


async def raise_missing_info_action(org_id: str, contract: dict, fields: list[str] | None = None) -> str:
    fields = fields if fields is not None else (contract.get("missing_fields") or [])
    human = ", ".join(_LABELS.get(f, f) for f in fields)
    return await raise_action(
        org_id, f"cm:missing:{contract['id']}", type_="contract_missing_info",
        subject=f"Missing information: {contract.get('contract_number') or contract.get('title')}",
        body=f"{contract.get('company_name') or 'Customer'} — add the {human} before this contract can be activated, billed or renewed.",
        contract=contract, extra={"missing_fields": fields})


async def scan_contract_admin(org_id: str) -> dict:
    """Raise one missing-info item per contract; auto-resolve fixed ones."""
    raised = resolved = 0
    async for c in db.crm2_contracts.find({"organization_id": org_id, "status": {"$in": ACTIVE_CONTRACT_STATUSES}}, {"_id": 0}):
        fields = await missing_fields(org_id, c)
        if fields:
            await raise_missing_info_action(org_id, c, fields)
            raised += 1
        elif await resolve_action(org_id, f"cm:missing:{c['id']}", "All required contract information is now recorded."):
            resolved += 1
        if sorted(fields) != sorted(c.get("missing_fields") or []):
            await db.crm2_contracts.update_one({"id": c["id"]}, {"$set": {"missing_fields": fields}})
    return {"missing_info_open": raised, "missing_info_resolved": resolved}


async def run_daily_checks(org_id: str, actor: str = "Daily checks") -> dict:
    from utils.afs_alerts import run_afs_alerts_once
    from utils.cm_renewals import prepare_renewals
    out = {"organization_id": org_id, "at": _now()}
    out["alerts"] = await run_afs_alerts_once(org_id, send_digest=True)
    out["contract_admin"] = await scan_contract_admin(org_id)
    from utils.cm_handover import scan_sales_handovers
    out["sales_handover"] = await scan_sales_handovers(org_id)
    ren = await prepare_renewals(org_id, actor=actor, dry_run=False)
    out["renewals"] = ren["totals"]
    return out
