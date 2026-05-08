"""
GymAxis AI — Contracts Management System
==========================================
Central commercial + service contract operating system connecting
CRM, Service Portal, Sicon Service Contracts, and Sage 200.

Source of Truth Rules:
  - GymAxis Contracts: authoring, approvals, metadata, renewals, umbrella structure
  - Sicon Service Contracts: operational service execution, coverage, SLA, periodic invoicing
  - Sage 200: financial postings, invoices, payments, deferred income
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from utils.database import db
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit
import uuid

router = APIRouter(prefix="/crm/v2", tags=["Contracts"])

def _id(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()
def _of(user): return {"organization_id": user.get("organization_id")} if user.get("organization_id") else {"organization_id": "__none__"}

CONTRACT_TIERS = [
    {"id": "warranty", "name": "Warranty", "color": "#6B7280"},
    {"id": "bronze", "name": "Bronze", "color": "#CD7F32"},
    {"id": "silver", "name": "Silver", "color": "#C0C0C0"},
    {"id": "gold", "name": "Gold", "color": "#FFD700"},
    {"id": "platinum", "name": "Platinum", "color": "#E5E4E2"},
    {"id": "bespoke", "name": "Bespoke", "color": "#8B5CF6"},
]

CONTRACT_STATUSES = [
    {"id": "draft", "name": "Draft", "color": "#6B7280"},
    {"id": "pending_approval", "name": "Pending Approval", "color": "#F59E0B"},
    {"id": "approved", "name": "Approved", "color": "#22C55E"},
    {"id": "sent", "name": "Sent to Customer", "color": "#007AFF"},
    {"id": "negotiation", "name": "In Negotiation", "color": "#AF52DE"},
    {"id": "signed", "name": "Signed", "color": "#34C759"},
    {"id": "active", "name": "Active", "color": "#007AFF"},
    {"id": "expiring", "name": "Expiring Soon", "color": "#FF9500"},
    {"id": "expired", "name": "Expired", "color": "#FF3B30"},
    {"id": "renewed", "name": "Renewed", "color": "#34C759"},
    {"id": "cancelled", "name": "Cancelled", "color": "#EF4444"},
    {"id": "amended", "name": "Amended", "color": "#8B5CF6"},
]


# ── LOOKUPS (must be before {contract_id} routes) ────────────────

@router.get("/contracts/tiers")
async def get_contract_tiers(user=Depends(get_crm_user)):
    return {"tiers": CONTRACT_TIERS}

@router.get("/contracts/statuses")
async def get_contract_statuses(user=Depends(get_crm_user)):
    return {"statuses": CONTRACT_STATUSES}

@router.get("/contracts/expiring")
async def get_expiring_contracts(days: int = 90, user=Depends(get_crm_user)):
    """Get contracts expiring within N days."""
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    contracts = await db.crm2_contracts.find(
        {**_of(user), "status": "active", "end_date": {"$lte": cutoff, "$gte": today}},
        {"_id": 0}
    ).sort("end_date", 1).to_list(100)
    return {"contracts": contracts, "total": len(contracts), "days_threshold": days}

def _contract_is_active(c: dict, now: str) -> bool:
    """Check if a contract is within its active date window."""
    start = c.get("start_date", "")
    end = c.get("end_date", "")
    return bool(start and end and start <= now <= end)


async def _asset_is_covered(contract_id: str, asset_id: str) -> bool:
    """Return True if the contract explicitly covers the given asset."""
    if not asset_id:
        return True
    doc = await db.crm2_contract_assets.find_one(
        {"contract_id": contract_id, "asset_id": asset_id}
    )
    return bool(doc)


def _upgrade_best_tier(coverage: dict, contract: dict, tier_order: dict) -> None:
    """Mutate coverage in place if this contract is a better tier than the current best."""
    current_best = coverage["best_tier"]
    if current_best and tier_order.get(contract["tier"], 0) <= tier_order.get(current_best, 0):
        return
    sla = contract.get("sla", {})
    coverage["best_tier"] = contract["tier"]
    coverage["sla"] = sla
    coverage["parts_included"] = sla.get("parts_included", False)
    coverage["labour_included"] = sla.get("labour_included", True)
    coverage["billable"] = False


@router.get("/contracts/check-coverage")
async def check_contract_coverage(
    company_id: str = "", asset_id: str = "",
    user=Depends(get_crm_user),
):
    """Check if a company/asset has active contract coverage."""
    of = _of(user)
    now = _now()[:10]
    query = {**of, "status": "active"}
    if company_id:
        query["company_id"] = company_id

    contracts = await db.crm2_contracts.find(query, {"_id": 0}).to_list(50)
    coverage = {"has_coverage": False, "contracts": [], "best_tier": None, "sla": None,
                "parts_included": False, "labour_included": False, "billable": True}
    tier_order = {t["id"]: i for i, t in enumerate(CONTRACT_TIERS)}

    for c in contracts:
        if not _contract_is_active(c, now):
            continue
        if not await _asset_is_covered(c["id"], asset_id):
            continue
        coverage["contracts"].append({
            "contract_id": c["id"], "contract_number": c.get("contract_number"),
            "title": c.get("title"), "tier": c.get("tier"),
            "sla": c.get("sla", {}),
            "start_date": c.get("start_date", ""),
            "end_date": c.get("end_date", ""),
        })
        coverage["has_coverage"] = True
        _upgrade_best_tier(coverage, c, tier_order)
    return coverage

@router.get("/contracts/stats")
async def get_contract_stats(user=Depends(get_crm_user)):
    """Dashboard stats for contracts."""
    of = _of(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff_90 = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")

    total = await db.crm2_contracts.count_documents(of)
    active = await db.crm2_contracts.count_documents({**of, "status": "active"})
    draft = await db.crm2_contracts.count_documents({**of, "status": "draft"})
    pending = await db.crm2_contracts.count_documents({**of, "status": "pending_approval"})
    expiring = await db.crm2_contracts.count_documents({**of, "status": "active", "end_date": {"$lte": cutoff_90, "$gte": today}})
    expired = await db.crm2_contracts.count_documents({**of, "status": "expired"})

    pipeline = [{"$match": {**of, "status": "active"}}, {"$group": {"_id": None, "total": {"$sum": "$annual_value"}}}]
    agg = await db.crm2_contracts.aggregate(pipeline).to_list(1)
    active_value = agg[0]["total"] if agg else 0

    by_tier = await db.crm2_contracts.aggregate([
        {"$match": {**of, "status": "active"}},
        {"$group": {"_id": "$tier", "count": {"$sum": 1}, "value": {"$sum": "$annual_value"}}}
    ]).to_list(20)

    return {
        "total": total, "active": active, "draft": draft,
        "pending_approval": pending, "expiring_soon": expiring, "expired": expired,
        "active_annual_value": active_value,
        "by_tier": [{**t, "tier": t["_id"]} for t in by_tier],
    }


# ── CONTRACT CRUD ─────────────────────────────────────────────────

@router.get("/contracts")
async def list_contracts(
    status: str = "", company_id: str = "", type: str = "",
    skip: int = 0, limit: int = 100,
    user=Depends(get_crm_user),
):
    """List all contracts with optional filters."""
    query = _of(user)
    if status:
        query["status"] = status
    if company_id:
        query["company_id"] = company_id
    if type:
        query["type"] = type
    contracts = await db.crm2_contracts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm2_contracts.count_documents(query)
    return {"contracts": contracts, "total": total}


def _build_contract_doc(data: dict, user: dict) -> dict:
    """Build a new contract document from input data."""
    org_id = user.get("organization_id")
    return {
        "id": _id(), "organization_id": org_id,
        "contract_number": f"CTR-{_id()[:6].upper()}",
        "title": data.get("title", ""),
        "type": data.get("type", "service"),
        "tier": data.get("tier", "silver"),
        "status": "draft",
        "company_id": data.get("company_id", ""),
        "company_name": data.get("company_name", ""),
        "contact_id": data.get("contact_id", ""),
        "contact_name": data.get("contact_name", ""),
        "opportunity_id": data.get("opportunity_id", ""),
        "quote_id": data.get("quote_id", ""),
        "order_id": data.get("order_id", ""),
        "parent_contract_id": data.get("parent_contract_id"),
        "start_date": data.get("start_date", ""),
        "end_date": data.get("end_date", ""),
        "annual_value": float(data.get("annual_value", 0)),
        "total_value": float(data.get("total_value", 0)),
        "billing_frequency": data.get("billing_frequency", "annual"),
        "auto_renew": data.get("auto_renew", False),
        "renewal_notice_days": int(data.get("renewal_notice_days", 90)),
        "sla": {
            "response_hours": data.get("sla_response_hours", 8),
            "resolution_hours": data.get("sla_resolution_hours", 48),
            "parts_included": data.get("parts_included", False),
            "labour_included": data.get("labour_included", True),
            "visits_per_year": data.get("visits_per_year"),
            "preventive_maintenance": data.get("preventive_maintenance", False),
        },
        "coverage_notes": data.get("coverage_notes", ""),
        "exclusions": data.get("exclusions", ""),
        "special_terms": data.get("special_terms", ""),
        "signature": None, "signed_by": None, "signed_at": None,
        "sicon_contract_id": None, "sage_reference": None,
        "version": 1,
        "created_by": user.get("full_name", ""),
        "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }


async def _log_contract_activity(contract: dict, user: dict):
    """Log a contract creation activity."""
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": contract["organization_id"],
        "type": "system", "subject": f"Contract created: {contract['contract_number']}",
        "body": f"{contract['title']} — {contract['tier'].upper()} tier for {contract['company_name']}",
        "company_id": contract["company_id"],
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(),
    })


@router.post("/contracts")
async def create_contract(data: dict, user=Depends(get_crm_user)):
    """Create a new contract (standalone or from opportunity/quote)."""
    contract = _build_contract_doc(data, user)
    await db.crm2_contracts.insert_one(contract)
    await _log_contract_activity(contract, user)
    await record_audit(entity_type="contract", entity_id=contract["id"], action="create", user=user, after=contract)
    return {k: v for k, v in contract.items() if k != "_id"}


@router.get("/contracts/{contract_id}")
async def get_contract(contract_id: str, user=Depends(get_crm_user)):
    """Get full contract detail with sites, assets, and service data."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")

    # Enrich with linked data
    c["sites"] = await db.crm2_contract_sites.find({"contract_id": contract_id}, {"_id": 0}).to_list(100)
    c["covered_assets"] = await db.crm2_contract_assets.find({"contract_id": contract_id}, {"_id": 0}).to_list(500)
    c["child_contracts"] = await db.crm2_contracts.find(
        {"parent_contract_id": contract_id, **_of(user)}, {"_id": 0, "id": 1, "title": 1, "status": 1, "annual_value": 1, "company_name": 1}
    ).to_list(50)
    c["activities"] = await db.crm2_activities.find(
        {"$or": [{"contract_id": contract_id}, {"subject": {"$regex": c.get("contract_number", ""), "$options": "i"}}], **_of(user)}, {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    c["documents"] = await db.crm2_documents.find({"contract_id": contract_id, **_of(user)}, {"_id": 0}).to_list(50)
    c["service_cases"] = await db.crm2_service_cases.find({"contract_id": contract_id}, {"_id": 0}).to_list(50)

    return c


async def _fire_contract_activated(contract_id: str, existing: dict, updates: dict, user: dict):
    """Fire integration event when a contract becomes active."""
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="contract_activated", source_system="crm", target_system="service_portal",
            entity_type="contract", entity_id=contract_id,
            payload={
                "contract_id": contract_id,
                "company_id": existing.get("company_id", ""),
                "sla_tier": updates.get("tier") or existing.get("tier", "standard"),
                "start_date": updates.get("start_date") or existing.get("start_date", ""),
                "end_date": updates.get("end_date") or existing.get("end_date", ""),
            },
            organization_id=user.get("organization_id", ""),
            triggered_by=user.get("full_name", ""),
        )
    except Exception:
        pass


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Update contract fields."""
    existing = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Contract not found")
    exclude = {"id", "organization_id", "created_at", "contract_number"}
    updates = {k: v for k, v in data.items() if k not in exclude}
    if "annual_value" in updates:
        updates["annual_value"] = float(updates["annual_value"])
    if "total_value" in updates:
        updates["total_value"] = float(updates["total_value"])
    updates["updated_at"] = _now()
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": updates})
    after = {**existing, **updates}
    await record_audit(entity_type="contract", entity_id=contract_id, action="update", user=user, before=existing, after=after)

    if "status" in updates and updates["status"] == "active" and existing.get("status") != "active":
        await _fire_contract_activated(contract_id, existing, updates, user)
    return {"success": True}


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, user=Depends(get_crm_user)):
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    if c.get("status") in ("active", "signed"):
        raise HTTPException(400, "Cannot delete active/signed contracts — cancel instead")
    await db.crm2_contracts.delete_one({"id": contract_id})
    await db.crm2_contract_sites.delete_many({"contract_id": contract_id})
    await db.crm2_contract_assets.delete_many({"contract_id": contract_id})
    await record_audit(entity_type="contract", entity_id=contract_id, action="delete", user=user, before=c)
    return {"success": True}


# ── CONTRACT SITES ────────────────────────────────────────────────

@router.post("/contracts/{contract_id}/sites")
async def add_contract_site(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Add a site/location to a contract."""
    site = {
        "id": _id(), "contract_id": contract_id,
        "organization_id": user.get("organization_id"),
        "site_name": data.get("site_name", ""),
        "address": data.get("address", ""),
        "city": data.get("city", ""),
        "postcode": data.get("postcode", ""),
        "sla_override": data.get("sla_override"),  # site-specific SLA if different from contract
        "billing_override": data.get("billing_override"),  # site-specific billing
        "notes": data.get("notes", ""),
        "created_at": _now(),
    }
    await db.crm2_contract_sites.insert_one(site)
    return {k: v for k, v in site.items() if k != "_id"}


@router.delete("/contracts/{contract_id}/sites/{site_id}")
async def remove_contract_site(contract_id: str, site_id: str, user=Depends(get_crm_user)):
    await db.crm2_contract_sites.delete_one({"id": site_id, "contract_id": contract_id})
    await db.crm2_contract_assets.delete_many({"site_id": site_id, "contract_id": contract_id})
    return {"success": True}


# ── CONTRACT ASSETS ───────────────────────────────────────────────

@router.post("/contracts/{contract_id}/assets")
async def add_contract_asset(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Add an asset/equipment to contract coverage."""
    asset = {
        "id": _id(), "contract_id": contract_id,
        "organization_id": user.get("organization_id"),
        "site_id": data.get("site_id", ""),
        "asset_id": data.get("asset_id", ""),
        "asset_name": data.get("asset_name", ""),
        "model_code": data.get("model_code", ""),
        "serial_number": data.get("serial_number", ""),
        "warranty_end": data.get("warranty_end", ""),
        "coverage_type": data.get("coverage_type", "full"),  # full, parts_only, labour_only, inspection
        "exclusions": data.get("exclusions", ""),
        "created_at": _now(),
    }
    await db.crm2_contract_assets.insert_one(asset)
    return {k: v for k, v in asset.items() if k != "_id"}


@router.delete("/contracts/{contract_id}/assets/{asset_id}")
async def remove_contract_asset(contract_id: str, asset_id: str, user=Depends(get_crm_user)):
    await db.crm2_contract_assets.delete_one({"id": asset_id, "contract_id": contract_id})
    return {"success": True}


# ── CONTRACT RENEWAL ──────────────────────────────────────────────

@router.post("/contracts/{contract_id}/renew")
async def create_renewal(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Create a renewal from an existing contract."""
    original = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0})
    if not original:
        raise HTTPException(404, "Contract not found")

    # Create renewal opportunity in CRM
    opp_id = _id()
    opp = {
        "id": opp_id, "organization_id": user.get("organization_id"),
        "title": f"Renewal: {original['title']}",
        "stage": "lead", "value": float(data.get("proposed_value", original.get("annual_value", 0))),
        "probability": 70,
        "company_id": original.get("company_id", ""),
        "company_name": original.get("company_name", ""),
        "contact_id": original.get("contact_id", ""),
        "source": "contract_renewal",
        "source_contract_id": contract_id,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "weighted_value": 0, "close_date": original.get("end_date", ""),
        "next_step": "Review renewal terms and pricing",
        "created_at": _now(), "updated_at": _now(),
        "stage_history": [{"stage": "lead", "entered_at": _now(), "by": user.get("full_name", "")}],
    }
    await db.crm2_opportunities.insert_one(opp)

    # Create new contract draft linked to renewal opportunity
    new_contract = {
        **{k: v for k, v in original.items() if k not in ("id", "created_at", "status", "signature", "signed_by", "signed_at", "version")},
        "id": _id(),
        "contract_number": f"{original['contract_number']}/R{original.get('version', 1) + 1}",
        "status": "draft",
        "previous_contract_id": contract_id,
        "opportunity_id": opp_id,
        "start_date": data.get("start_date", original.get("end_date", "")),
        "end_date": data.get("end_date", ""),
        "annual_value": float(data.get("proposed_value", original.get("annual_value", 0))),
        "version": original.get("version", 1) + 1,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_contracts.insert_one(new_contract)

    # Mark original as expiring/renewed
    if original.get("status") == "active":
        await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"renewal_contract_id": new_contract["id"]}})

    return {
        "contract": {k: v for k, v in new_contract.items() if k != "_id"},
        "opportunity": {"id": opp_id, "title": opp["title"]},
    }


# ── CONTRACT SIGN ─────────────────────────────────────────────────

@router.post("/contracts/{contract_id}/sign")
async def sign_contract(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Apply signature and activate the contract."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")

    updates = {
        "signature": data.get("signature"),
        "signed_by": data.get("signer_name", user.get("full_name", "")),
        "signed_at": _now(),
        "status": "active" if data.get("activate", True) else "signed",
        "updated_at": _now(),
    }
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": updates})
    await record_audit(
        entity_type="contract", entity_id=contract_id, action="sign",
        user=user, before=c, after={**c, **updates},
        summary=f"Contract signed by {updates['signed_by']}",
    )

    # Fire contract activated event
    if updates["status"] == "active":
        try:
            from routes.integration_hub import publish_event
            await publish_event(
                event_type="contract_activated", source_system="crm", target_system="service_portal",
                entity_type="contract", entity_id=contract_id,
                payload={
                    "contract_id": contract_id, "company_id": c.get("company_id", ""),
                    "sla_tier": c.get("tier", "standard"),
                    "start_date": c.get("start_date", ""), "end_date": c.get("end_date", ""),
                    "asset_ids": [a.get("asset_id") for a in await db.crm2_contract_assets.find({"contract_id": contract_id}, {"_id": 0, "asset_id": 1}).to_list(500)],
                },
                organization_id=user.get("organization_id", ""),
                triggered_by=user.get("full_name", ""),
            )
        except Exception:
            pass

    return {"success": True, "status": updates["status"]}


# ── APPROVAL WORKFLOW ─────────────────────────────────────────────

@router.post("/contracts/{contract_id}/submit-approval")
async def submit_for_approval(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Submit contract for internal approval."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")
    if c.get("status") not in ("draft", "negotiation", "amended"):
        raise HTTPException(400, f"Cannot submit from status '{c.get('status')}'")

    approval = {
        "id": _id(), "contract_id": contract_id,
        "organization_id": user.get("organization_id"),
        "submitted_by": user.get("full_name", ""),
        "submitted_by_id": user.get("id"),
        "approver_name": data.get("approver_name", ""),
        "approver_id": data.get("approver_id", ""),
        "notes": data.get("notes", ""),
        "status": "pending",
        "decision": None, "decision_notes": None, "decided_at": None,
        "created_at": _now(),
    }
    await db.crm2_contract_approvals.insert_one(approval)
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"status": "pending_approval", "updated_at": _now()}})
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Contract submitted for approval: {c.get('contract_number')}",
        "body": f"Submitted by {user.get('full_name', '')} — awaiting {data.get('approver_name', 'approval')}",
        "company_id": c.get("company_id", ""), "contract_id": contract_id,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(),
    })
    return {k: v for k, v in approval.items() if k != "_id"}


@router.get("/contracts/{contract_id}/approvals")
async def get_contract_approvals(contract_id: str, user=Depends(get_crm_user)):
    """Get approval history for a contract."""
    approvals = await db.crm2_contract_approvals.find(
        {"contract_id": contract_id, "organization_id": user.get("organization_id")}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"approvals": approvals}


@router.post("/contracts/{contract_id}/approve")
async def approve_contract(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Approve or reject a contract."""
    decision = data.get("decision", "approved")  # approved or rejected
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")

    pending = await db.crm2_contract_approvals.find_one(
        {"contract_id": contract_id, "status": "pending"}, sort=[("created_at", -1)]
    )
    if pending:
        await db.crm2_contract_approvals.update_one({"id": pending["id"]}, {"$set": {
            "status": decision, "decision": decision,
            "decision_notes": data.get("notes", ""),
            "decided_by": user.get("full_name", ""),
            "decided_at": _now(),
        }})

    new_status = "approved" if decision == "approved" else "draft"
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"status": new_status, "updated_at": _now()}})
    await record_audit(
        entity_type="contract", entity_id=contract_id, action="approve",
        user=user, before=c, after={**c, "status": new_status},
        summary=f"Contract {decision} by {user.get('full_name', '')}",
        extra={"decision": decision, "notes": data.get("notes", "")},
    )
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system",
        "subject": f"Contract {decision}: {c.get('contract_number')}",
        "body": f"{decision.capitalize()} by {user.get('full_name', '')}. {data.get('notes', '')}",
        "company_id": c.get("company_id", ""), "contract_id": contract_id,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(),
    })
    return {"success": True, "status": new_status}


# ── CONTRACT SLA UPDATE ───────────────────────────────────────────

@router.put("/contracts/{contract_id}/sla")
async def update_contract_sla(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Update SLA fields on a contract."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")
    sla = {
        "response_hours": data.get("response_hours", 8),
        "resolution_hours": data.get("resolution_hours", 48),
        "parts_included": data.get("parts_included", False),
        "labour_included": data.get("labour_included", True),
        "visits_per_year": data.get("visits_per_year"),
        "preventive_maintenance": data.get("preventive_maintenance", False),
    }
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"sla": sla, "updated_at": _now()}})
    return {"success": True, "sla": sla}


# ── SERVICE INTEGRATION (Sicon mock) ─────────────────────────────

@router.post("/contracts/{contract_id}/sync-sicon")
async def sync_to_sicon(contract_id: str, user=Depends(get_crm_user)):
    """Push contract to Sicon Service Contracts (mocked)."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")
    sicon_id = f"SICON-{contract_id[:8].upper()}"
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {
        "sicon_contract_id": sicon_id,
        "sicon_sync_status": "synced",
        "sicon_synced_at": _now(),
        "updated_at": _now(),
    }})
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Sicon sync: {c.get('contract_number')}",
        "body": f"Contract pushed to Sicon as {sicon_id}",
        "company_id": c.get("company_id", ""), "contract_id": contract_id,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(),
    })
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="contract_activated", source_system="crm", target_system="sicon",
            entity_type="contract", entity_id=contract_id,
            payload={"contract_id": contract_id, "sicon_contract_id": sicon_id},
            organization_id=user.get("organization_id", ""),
            triggered_by=user.get("full_name", ""),
        )
    except Exception:
        pass
    return {"success": True, "sicon_contract_id": sicon_id}


@router.post("/contracts/{contract_id}/sync-sage")
async def sync_to_sage(contract_id: str, user=Depends(get_crm_user)):
    """Push contract to Sage 200 (mocked)."""
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)})
    if not c:
        raise HTTPException(404, "Contract not found")
    sage_ref = f"SAGE-{contract_id[:8].upper()}"
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {
        "sage_reference": sage_ref,
        "sage_sync_status": "synced",
        "sage_synced_at": _now(),
        "updated_at": _now(),
    }})
    return {"success": True, "sage_reference": sage_ref}
