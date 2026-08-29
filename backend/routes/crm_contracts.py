"""
Pulse Fitness AI — Contracts Management System
==========================================
Central commercial + service contract operating system connecting
CRM, Service Portal, Sicon Service Contracts, and Sage 200.

Source of Truth Rules:
  - Pulse Fitness Contracts: authoring, approvals, metadata, renewals, umbrella structure
  - Sicon Service Contracts: operational service execution, coverage, SLA, periodic invoicing
  - Sage 200: financial postings, invoices, payments, deferred income
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from utils.security_plus import safe_regex
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
        "billing_contact_id": data.get("billing_contact_id", ""),
        "assigned_engineer_id": data.get("assigned_engineer_id", ""),
        "site_id": data.get("site_id", ""),
        "opportunity_id": data.get("opportunity_id", ""),
        "quote_id": data.get("quote_id", ""),
        "order_id": data.get("order_id", ""),
        "parent_contract_id": data.get("parent_contract_id"),
        "start_date": data.get("start_date", ""),
        "end_date": data.get("end_date", ""),
        "renewal_date": data.get("renewal_date", ""),
        "contract_length_months": data.get("contract_length_months"),
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
        # Iter 220e3 — structured cover schema mirrored from templates.
        # These fields are optional and additive; legacy contracts
        # without them keep working through the existing free-text
        # `coverage_notes` / `exclusions` fields.
        "template_id": data.get("template_id"),
        "inclusions": data.get("inclusions") or {},
        "exclusions_structured": data.get("exclusions_structured") or [],
        "consumables": data.get("consumables") or [],
        "response_times": data.get("response_times") or {},
        "pricing": data.get("pricing") or {},
        "terms_md": data.get("terms_md", ""),
        "coverage_notes": data.get("coverage_notes", ""),
        "exclusions": data.get("exclusions", ""),
        "special_terms": data.get("special_terms", ""),
        "signature": None, "signed_by": None, "signed_at": None,
        "sicon_contract_id": None, "sage_reference": None,
        # Iter 216h240 — Orbit 4 round-trip ref. Populated when the
        # contract is mirrored to Orbit 4 via the outbound mappers
        # documented in INTEGRATION_FIELD_MAPPING.md §32.2. Stays null
        # for non-Orbit 4 tenants.
        "orbit4_contract_id": data.get("orbit4_contract_id"),
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


@router.post("/contracts/{contract_id}/convert-to-quote")
async def convert_contract_to_quote(contract_id: str, data: dict = None, user=Depends(get_crm_user)):
    """One-click: turn a (draft) aftersales contract into a SENT quote.

    Builds a CPQ quote (crm2_quotes) with a single service-contract line for
    the cover, marks it 'sent', links it both ways, and moves the contract to
    'sent'. Idempotent — returns the existing quote if already converted."""
    from routes.crm_v2 import compute_quote_totals
    from utils.localization import org_localization

    data = data or {}
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")

    # Idempotency — reuse an already-linked quote.
    if c.get("quote_id"):
        existing = await db.crm2_quotes.find_one({"id": c["quote_id"], **_of(user)}, {"_id": 0})
        if existing:
            return {"status": "already_converted", "quote": existing, "contract_id": contract_id}

    tier = (c.get("tier") or "bronze").title()
    annual = float(c.get("annual_value", 0) or 0)

    # Itemise: one service-contract line per unit from the warranty enquiry
    # (with serials), so the aftersales quote is fully itemised on creation.
    eq_ids = c.get("enquiry_equipment_ids") or []
    equipment = []
    if eq_ids:
        equipment = await db.equipment.find(
            {"id": {"$in": eq_ids}},
            {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1, "serial_number": 1},
        ).to_list(200)
    if equipment:
        n = len(equipment)
        per = round(annual / n, 2) if annual else 0
        lines, running = [], 0.0
        for i, e in enumerate(equipment):
            price = round(annual - running, 2) if (i == n - 1 and annual) else per
            running += per
            serial = e.get("serial_number")
            mm = " ".join([p for p in [e.get("manufacturer"), e.get("model")] if p])
            desc = f"Aftersales cover ({tier}) — {e.get('name') or 'Equipment'}"
            if mm:
                desc += f" · {mm}"
            if serial:
                desc += f" (S/N {serial})"
            lines.append({
                "id": _id(), "line_type": "service_contract", "description": desc,
                "quantity": 1, "unit_price": price, "discount": 0,
                "equipment_id": e.get("id"), "serial_number": serial or "",
            })
    else:
        lines = [{
            "id": _id(), "line_type": "service_contract",
            "description": f"Aftersales cover ({tier}) — {c.get('title') or 'Service contract'}",
            "quantity": 1, "unit_price": annual, "discount": 0,
        }]
    _org = await db.organizations.find_one(
        {"id": user.get("organization_id")}, {"_id": 0, "country_code": 1, "currency": 1, "timezone": 1})
    loc = org_localization(_org)
    totals = compute_quote_totals(lines, float(loc["default_tax_rate"]))
    now = _now()
    quote = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "quote_number": f"QT-{str(uuid.uuid4())[:6].upper()}",
        "company_id": c.get("company_id"), "company_name": c.get("company_name", ""),
        "contact_id": c.get("contact_id", ""), "contact_name": c.get("contact_name", ""),
        "opportunity_id": "",
        "status": "sent", "sent_at": now,
        "lines": lines, **totals,
        "currency": loc["currency"], "tax_label": loc["tax_label"], "country_code": loc["country_code"],
        "valid_until": "", "notes": f"Generated from aftersales contract {c.get('contract_number', '')}.",
        "source": "aftersales_contract", "contract_id": contract_id,
        "version": 1, "created_by": user.get("full_name", ""),
        "created_at": now, "updated_at": now,
    }
    await db.crm2_quotes.insert_one({**quote})
    await db.crm2_contracts.update_one(
        {"id": contract_id, **_of(user)},
        {"$set": {"quote_id": quote["id"], "status": "sent", "updated_at": now}})
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Contract converted to quote: {quote['quote_number']}",
        "body": f"{c.get('title')} → quote {quote['quote_number']} ({tier} cover) sent to {c.get('company_name')}.",
        "company_id": c.get("company_id"), "contract_id": contract_id, "quote_id": quote["id"],
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""), "created_at": now,
    })
    await record_audit(entity_type="contract", entity_id=contract_id, action="convert_to_quote",
                       user=user, after={"quote_id": quote["id"], "status": "sent"})

    # Optionally email the freshly-created quote to the customer contact.
    result = {"status": "converted", "quote": quote, "contract_id": contract_id, "emailed": False}
    if data.get("send_email"):
        from routes.crm_v2 import send_quote_email
        to_addr = (data.get("email_to") or "").strip().lower()
        if not to_addr and c.get("contact_id"):
            ct = await db.crm2_contacts.find_one({"id": c["contact_id"], **_of(user)}, {"_id": 0, "email": 1})
            to_addr = ((ct or {}).get("email") or "").strip().lower()
        if not to_addr and c.get("company_id"):
            ct = await db.crm2_contacts.find_one(
                {"company_id": c["company_id"], "email": {"$nin": [None, ""]}, **_of(user)},
                {"_id": 0, "email": 1})
            to_addr = ((ct or {}).get("email") or "").strip().lower()
        if not to_addr:
            result["email_error"] = "No contact email on the contract or company — the quote was created but not emailed."
        else:
            try:
                await send_quote_email(quote["id"], {"to": to_addr}, user)
                result["emailed"] = True
                result["email_to"] = to_addr
            except HTTPException as he:
                result["email_error"] = he.detail
            except Exception as exc:  # pragma: no cover
                result["email_error"] = f"Quote created but email failed: {exc}"
    return result


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
        {"$or": [{"contract_id": contract_id}, {"subject": safe_regex(c.get("contract_number", ""))}], **_of(user)}, {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    c["documents"] = await db.crm2_documents.find({"contract_id": contract_id, **_of(user)}, {"_id": 0}).to_list(50)
    c["service_cases"] = await db.crm2_service_cases.find({"contract_id": contract_id}, {"_id": 0}).to_list(50)

    return c


async def _fire_contract_activated(contract_id: str, existing: dict, updates: dict, user: dict):
    """Fire integration event when a contract becomes active, and bridge
    it into Service Ops (G2 — auto sales→service onboarding)."""
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
    # Iter 220ea·26 (G2) — auto-onboard the maintenance contract into the
    # service world (customer + PPM schedule + first visit). Idempotent,
    # best-effort: never blocks the contract flow.
    try:
        from utils.sales_to_service import onboard_contract_to_service
        contract = {**existing, **updates, "id": contract_id}
        contract.pop("_id", None)
        await onboard_contract_to_service(contract, user=user)
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

    target_status = "active" if data.get("activate", True) else "signed"
    # Workflow lock: a contract can only be signed/activated once it has been
    # APPROVED (or already sent/signed) — blocks signing an unapproved draft.
    from utils.authz import assert_transition
    await assert_transition("contract", c.get("status"), target_status, user, resource_id=contract_id)

    updates = {
        "signature": data.get("signature"),
        "signed_by": data.get("signer_name", user.get("full_name", "")),
        "signed_at": _now(),
        "status": target_status,
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
        # Iter 220ea·26 (G2) — auto-onboard the signed maintenance contract
        # into Service Ops (customer + PPM schedule + first visit).
        try:
            from utils.sales_to_service import onboard_contract_to_service
            await onboard_contract_to_service({**c, **updates, "id": contract_id}, user=user)
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
    from utils.authz import assert_transition
    await assert_transition("contract", c.get("status"), "pending_approval", user, resource_id=contract_id)
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

    new_status = "approved" if decision == "approved" else "draft"
    # Workflow lock: a contract can only be approved from 'pending_approval'
    # — blocks approving a contract that never went through submission.
    from utils.authz import assert_transition
    await assert_transition("contract", c.get("status"), new_status, user, resource_id=contract_id)

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



# ── PHASE 1: SITES & EQUIPMENT TAB ─────────────────────────────────
#
# Iter 216h196 — Lee's ask: CRM Company → Sites & Equipment tab. For
# the Company in CRM, surface the org's sites + their equipment with
# real-time contract-coverage badges so the Pulse Fitness team can
# attach aftersales contracts to specific machines and (via Phase 2)
# the Operations app sees that coverage too.
#
# Linking strategy (least-friction):
#   1. If `crm_companies.linked_organization_id` is set explicitly,
#      use that org's sites/equipment.
#   2. Else if the company name case-insensitively matches the user's
#      own org name, treat this CRM company as the self-record and
#      return the user's own org's data. (This is how Pulse Fitness
#      naturally ends up with "Pulse Fitness Limited" in CRM that
#      maps to their own HQ org.)
#   3. Else return empty — future phases will let the operator pick
#      an organisation to link.


def _coverage_for_equipment(equipment_id: str, contract_assets: list[dict],
                            contracts_by_id: dict, today: str) -> dict:
    """Resolve the best active coverage for one piece of equipment.

    Walks every ``crm2_contract_assets`` row whose ``asset_id`` matches
    and picks the highest-tier active contract. ``best_tier`` ordering
    mirrors ``CONTRACT_TIERS`` (warranty < bronze < silver < gold <
    platinum < bespoke).
    """
    tier_order = {t["id"]: i for i, t in enumerate(CONTRACT_TIERS)}
    matches = [a for a in contract_assets if a.get("asset_id") == equipment_id]
    best = None
    for a in matches:
        contract = contracts_by_id.get(a.get("contract_id"))
        if not contract or contract.get("status") not in {"active", "signed", "expiring"}:
            continue
        end = contract.get("end_date", "")
        if end and end < today:
            continue
        rank = tier_order.get(contract.get("tier", ""), -1)
        if not best or rank > best["_rank"]:
            best = {
                "_rank": rank,
                "has_coverage": True,
                "contract_id": contract.get("id"),
                "contract_number": contract.get("contract_number"),
                "contract_title": contract.get("title"),
                "tier": contract.get("tier"),
                "coverage_type": a.get("coverage_type", "full"),
                "start_date": contract.get("start_date"),
                "end_date": end,
                "exclusions": a.get("exclusions", ""),
            }
    if not best:
        return {"has_coverage": False, "contract_id": None}
    # Drop the internal rank field from the response.
    best.pop("_rank", None)
    return best


@router.get("/companies/{company_id}/sites-and-equipment")
async def company_sites_and_equipment(company_id: str, user=Depends(get_crm_user)):
    """Returns the linked-organisation's sites + equipment with
    contract-coverage badges. Phase 1 of the Operations ↔ CRM ↔ Service
    Desk linkage.

    Response shape:
        {
          "linked_organization_id": "<org_id or null>",
          "linked_via": "explicit_link" | "name_match" | "unlinked",
          "sites": [
            {
              "id": "...", "name": "...",
              "equipment": [
                {
                  "id": "...", "name": "...", "model": "...",
                  "serial_number": "...", "manufacturer": "...",
                  "warranty_expiry": "YYYY-MM-DD",
                  "coverage": { "has_coverage": bool, ...best tier },
                },
              ],
            },
          ],
          "totals": {"sites": N, "equipment": N, "covered": N, "expiring_soon": N},
        }
    """
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")

    # Step 1 — resolve linked organization id.
    linked_org_id = company.get("linked_organization_id") or ""
    linked_via = "explicit_link" if linked_org_id else None
    if not linked_org_id:
        user_org_id = user.get("organization_id") or ""
        if user_org_id:
            user_org = await db.organizations.find_one(
                {"id": user_org_id}, {"_id": 0, "name": 1}
            ) or {}
            user_org_name = (user_org.get("name") or "").strip().lower()
            company_name = (company.get("name") or "").strip().lower()
            if user_org_name and user_org_name == company_name:
                linked_org_id = user_org_id
                linked_via = "name_match"
    if not linked_org_id:
        return {
            "linked_organization_id": None, "linked_via": "unlinked",
            "sites": [], "totals": {"sites": 0, "equipment": 0, "covered": 0, "expiring_soon": 0},
        }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    expiring_cutoff = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")

    # Step 2 — sites for the linked org.
    sites = await db.sites.find(
        {"organization_id": linked_org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "city": 1, "postcode": 1},
    ).sort("name", 1).to_list(500)

    # Step 3 — equipment for the linked org (filtered to known sites).
    equipment = await db.equipment.find(
        {"organization_id": linked_org_id},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "manufacturer": 1,
         "supplier": 1, "serial_number": 1, "site_id": 1, "location": 1,
         "warranty_expiry": 1, "sla_expiry": 1, "sla_contract_ref": 1,
         "sla_response_time": 1, "status": 1, "photo_url": 1},
    ).sort("name", 1).to_list(5000)

    # Step 4 — preload contract assets + contracts to resolve coverage.
    eq_ids = [e["id"] for e in equipment if e.get("id")]
    contract_assets = await db.crm2_contract_assets.find(
        {"asset_id": {"$in": eq_ids}, **of}, {"_id": 0},
    ).to_list(5000) if eq_ids else []
    contract_ids = list({a.get("contract_id") for a in contract_assets if a.get("contract_id")})
    contracts = await db.crm2_contracts.find(
        {"id": {"$in": contract_ids}, **of}, {"_id": 0},
    ).to_list(2000) if contract_ids else []
    contracts_by_id = {c.get("id"): c for c in contracts}

    # Step 5 — bucket equipment by site, resolve coverage, count totals.
    by_site: dict[str, list[dict]] = {}
    for eq in equipment:
        sid = eq.get("site_id") or "__unassigned__"
        coverage = _coverage_for_equipment(eq["id"], contract_assets, contracts_by_id, today)
        eq_out = {
            "id": eq.get("id"),
            "name": eq.get("name"),
            "model": eq.get("model") or eq.get("model_code") or "",
            "manufacturer": eq.get("manufacturer") or eq.get("supplier") or "",
            "serial_number": eq.get("serial_number", ""),
            "location": eq.get("location", ""),
            "warranty_expiry": eq.get("warranty_expiry", ""),
            "sla_expiry": eq.get("sla_expiry", ""),
            "sla_response_time": eq.get("sla_response_time", ""),
            "sla_contract_ref": eq.get("sla_contract_ref", ""),
            "status": eq.get("status", "operational"),
            "photo_url": eq.get("photo_url"),
            "coverage": coverage,
        }
        by_site.setdefault(sid, []).append(eq_out)

    site_rows = []
    for s in sites:
        eqs = by_site.get(s["id"], [])
        site_rows.append({**s, "equipment": eqs, "equipment_count": len(eqs)})

    # If there's equipment on no recognised site, surface it under
    # "Unassigned" so the operator notices the orphan and tags a site.
    unassigned = by_site.get("__unassigned__", [])
    if unassigned:
        site_rows.append({
            "id": "__unassigned__", "name": "Unassigned (no site tagged)",
            "equipment": unassigned, "equipment_count": len(unassigned),
        })

    # Totals.
    flat = [e for s in site_rows for e in s["equipment"]]
    covered_count = sum(1 for e in flat if e["coverage"]["has_coverage"])
    expiring_count = sum(
        1 for e in flat
        if e["coverage"]["has_coverage"] and (e["coverage"].get("end_date") or "") <= expiring_cutoff
    )

    return {
        "linked_organization_id": linked_org_id,
        "linked_via": linked_via,
        "sites": site_rows,
        "totals": {
            "sites": len(site_rows),
            "equipment": len(flat),
            "covered": covered_count,
            "uncovered": len(flat) - covered_count,
            "expiring_soon": expiring_count,
        },
    }


@router.post("/companies/{company_id}/link-organization")
async def link_company_to_organization(company_id: str, data: dict,
                                       user=Depends(get_crm_user)):
    """Explicitly link a CRM Company to an Operations Organisation.
    Sets ``linked_organization_id`` on ``crm_companies`` so the Sites &
    Equipment tab returns that org's estate even when names don't match.
    """
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0, "id": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    org_id = (data.get("organization_id") or "").strip()
    if not org_id:
        raise HTTPException(400, "organization_id is required")
    # Only let users link to their own organisation for now (multi-tenant
    # safety: don't let CRM-Pro orgs reach into someone else's data).
    if org_id != user.get("organization_id"):
        raise HTTPException(403, "Can only link a company to your own organisation")
    await db.crm2_companies.update_one(
        {"id": company_id, **of},
        {"$set": {"linked_organization_id": org_id, "linked_at": _now()}},
    )
    return {"success": True, "linked_organization_id": org_id}


def _norm_serial(s: str) -> str:
    return "".join((s or "").strip().lower().split())


async def _resolve_linked_org(company: dict, user: dict) -> str:
    """Explicit link, else exact name-match to the caller's own org."""
    linked = company.get("linked_organization_id") or ""
    if linked:
        return linked
    uoid = user.get("organization_id") or ""
    if uoid:
        uo = await db.organizations.find_one({"id": uoid}, {"_id": 0, "name": 1}) or {}
        if (uo.get("name") or "").strip().lower() == (company.get("name") or "").strip().lower():
            return uoid
    return ""


@router.get("/companies/{company_id}/asset-reconciliation")
async def company_asset_reconciliation(company_id: str, user=Depends(get_crm_user)):
    """Single-source-of-truth check for a company's equipment.

    The Operations equipment register (``db.equipment``) — also used by the
    Service Desk — is the canonical source. This compares any CRM-side
    ``crm2_assets`` against that register and flags duplicates (same serial /
    Sicon id) that should be linked, manual CRM-only assets, and register
    items not yet reflected in CRM. Read-only.
    """
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")

    linked_org_id = await _resolve_linked_org(company, user)
    register = []
    if linked_org_id:
        register = await db.equipment.find(
            {"organization_id": linked_org_id},
            {"_id": 0, "id": 1, "name": 1, "model": 1, "manufacturer": 1,
             "serial_number": 1, "sicon_equipment_id": 1, "site_id": 1},
        ).to_list(5000)
    crm_assets = await db.crm2_assets.find(
        {"company_id": company_id, **of}, {"_id": 0}).to_list(2000)

    by_id, by_serial, by_sicon = {}, {}, {}
    for e in register:
        by_id[e.get("id")] = e
        ns = _norm_serial(e.get("serial_number"))
        if ns:
            by_serial[ns] = e
        sic = (e.get("sicon_equipment_id") or "").strip()
        if sic:
            by_sicon[sic] = e

    duplicates, crm_only, matched_reg_ids, already_linked = [], [], set(), 0
    for a in crm_assets:
        match, via = None, None
        if a.get("equipment_id") and a["equipment_id"] in by_id:
            match, via = by_id[a["equipment_id"]], "equipment_id"
        if not match:
            sic = (a.get("sicon_equipment_id") or "").strip()
            if sic and sic in by_sicon:
                match, via = by_sicon[sic], "sicon"
        if not match:
            ns = _norm_serial(a.get("serial_number"))
            if ns and ns in by_serial:
                match, via = by_serial[ns], "serial"
        if match:
            matched_reg_ids.add(match.get("id"))
            if a.get("equipment_id"):
                already_linked += 1
                continue
            duplicates.append({
                "crm_asset": {"id": a.get("id"), "name": a.get("name"),
                              "serial_number": a.get("serial_number"), "status": a.get("status")},
                "register": {"id": match.get("id"), "name": match.get("name"),
                             "serial_number": match.get("serial_number"), "model": match.get("model")},
                "matched_via": via,
            })
        else:
            crm_only.append({"id": a.get("id"), "name": a.get("name"),
                             "serial_number": a.get("serial_number"), "status": a.get("status")})

    unlinked_register = sum(1 for e in register if e.get("id") not in matched_reg_ids)
    return {
        "linked_organization_id": linked_org_id or None,
        "source_of_truth": "operations_equipment_register",
        "register_count": len(register),
        "crm_asset_count": len(crm_assets),
        "already_linked": already_linked,
        "duplicates": duplicates,
        "crm_only": crm_only,
        "unlinked_register_count": unlinked_register,
    }


@router.post("/assets/{asset_id}/link-equipment")
async def link_asset_to_equipment(asset_id: str, data: dict, user=Depends(get_crm_user)):
    """Resolve a duplicate by pointing a CRM asset at its canonical register
    record — the register stays the single source of truth."""
    of = _of(user)
    equipment_id = (data.get("equipment_id") or "").strip()
    if not equipment_id:
        raise HTTPException(400, "equipment_id is required")
    asset = await db.crm2_assets.find_one({"id": asset_id, **of}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Asset not found")
    eq = await db.equipment.find_one(
        {"id": equipment_id},
        {"_id": 0, "id": 1, "serial_number": 1, "model": 1, "name": 1, "sicon_equipment_id": 1})
    if not eq:
        raise HTTPException(404, "Register equipment not found")
    upd = {"equipment_id": equipment_id, "source": "register", "updated_at": _now()}
    if eq.get("serial_number") and not asset.get("serial_number"):
        upd["serial_number"] = eq["serial_number"]
    if eq.get("sicon_equipment_id"):
        upd["sicon_equipment_id"] = eq["sicon_equipment_id"]
    await db.crm2_assets.update_one({"id": asset_id, **of}, {"$set": upd})
    return {"ok": True, "asset_id": asset_id, "equipment_id": equipment_id}



@router.post("/assets/{asset_id}/promote-to-register")
async def promote_asset_to_register(asset_id: str, data: dict | None = None,
                                    user=Depends(get_crm_user)):
    """Promote a CRM-only asset into the Operations equipment register.

    Creates a canonical ``db.equipment`` row from the CRM asset's fields
    (enriched from the linked product when available) and links the CRM
    asset back to it, so the register stays the single source of truth.
    Only valid for CRM-only assets (no existing ``equipment_id``).
    """
    of = _of(user)
    asset = await db.crm2_assets.find_one({"id": asset_id, **of}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.get("equipment_id"):
        return {"ok": True, "asset_id": asset_id,
                "equipment_id": asset["equipment_id"], "already_linked": True}

    company = await db.crm2_companies.find_one(
        {"id": asset.get("company_id"), **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found for this asset")
    linked_org_id = await _resolve_linked_org(company, user)
    if not linked_org_id:
        raise HTTPException(
            400,
            "This company isn't linked to an Operations organisation, so its "
            "equipment register can't be located. Link the company to an org first.",
        )

    # Best-effort product enrichment (manufacturer / model / type / cost).
    product = None
    if asset.get("product_id"):
        product = await db.crm_products.find_one(
            {"id": asset["product_id"]}, {"_id": 0}) or None
    p = product or {}

    name = (asset.get("name") or p.get("name") or "Unnamed asset").strip()
    category = (p.get("category") or "").strip()
    equipment_type = category if category and category.lower() not in ("equipment", "other") else "Other"

    now = _now()
    equipment_doc = {
        "id": _id(),
        "user_id": user.get("id"),
        "organization_id": linked_org_id,
        "name": name,
        "equipment_type": equipment_type,
        "manufacturer": p.get("supplier_name") or "",
        "model": p.get("sku") or "",
        "serial_number": asset.get("serial_number") or "",
        "warranty_expiry": asset.get("warranty_expiry") or None,
        "purchase_date": asset.get("install_date") or None,
        "site_id": asset.get("site_id") or None,
        "sicon_equipment_id": asset.get("sicon_equipment_id") or None,
        "purchase_cost": p.get("cost_price"),
        "source": "crm_promoted",
        "manuals": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.equipment.insert_one(equipment_doc)
    await db.crm2_assets.update_one(
        {"id": asset_id, **of},
        {"$set": {"equipment_id": equipment_doc["id"], "source": "register", "updated_at": now}},
    )
    await record_audit(
        entity_type="crm2_asset", entity_id=asset_id, action="update", user=user,
        summary=f"Promoted CRM asset '{name}' to the equipment register",
        extra={"equipment_id": equipment_doc["id"], "linked_organization_id": linked_org_id},
    )
    return {"ok": True, "asset_id": asset_id,
            "equipment_id": equipment_doc["id"], "name": name}



@router.post("/companies/{company_id}/equipment-coverage")
async def attach_equipment_to_contract(company_id: str, data: dict,
                                       user=Depends(get_crm_user)):
    """Convenience wrapper for the "Add coverage" modal on the Sites &
    Equipment tab. Either attaches an equipment to an existing contract
    OR creates a brand-new contract + attaches in one call.
    """
    equipment_id = (data.get("equipment_id") or "").strip()
    if not equipment_id:
        raise HTTPException(400, "equipment_id is required")
    contract_id = (data.get("contract_id") or "").strip()
    coverage_type = data.get("coverage_type", "full")
    site_id = data.get("site_id", "")
    warranty_end = data.get("warranty_end", "")

    if not contract_id:
        # Create a fresh contract on the fly using the data the modal
        # collected. The CRM contract list view exposes the rest of
        # the contract editing surface (renewal, signatures, etc.).
        new_contract = {
            "id": _id(), "organization_id": user.get("organization_id"),
            "contract_number": f"GAX-{datetime.now(timezone.utc).strftime('%Y%m')}-{_id()[:6].upper()}",
            "company_id": company_id,
            "title": data.get("contract_title") or "Aftersales coverage",
            "tier": data.get("tier", "bronze"),
            "type": data.get("type", "aftersales"),
            "status": "active",
            "start_date": data.get("start_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "end_date": warranty_end or data.get("end_date") or "",
            "annual_value": data.get("annual_value", 0),
            "currency": data.get("currency", "GBP"),
            "auto_renew": bool(data.get("auto_renew", False)),
            "created_by": user.get("id"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.crm2_contracts.insert_one(new_contract)
        contract_id = new_contract["id"]
        await record_audit(entity_type="contract", entity_id=contract_id, action="create",
                           user=user, after={k: v for k, v in new_contract.items() if k != "_id"})

    # Resolve / look up equipment metadata to copy onto the asset row.
    eq = await db.equipment.find_one(
        {"id": equipment_id}, {"_id": 0, "name": 1, "model": 1, "serial_number": 1, "site_id": 1},
    ) or {}

    asset = {
        "id": _id(), "contract_id": contract_id,
        "organization_id": user.get("organization_id"),
        "site_id": site_id or eq.get("site_id", ""),
        "asset_id": equipment_id,
        "asset_name": eq.get("name", ""),
        "model_code": eq.get("model", ""),
        "serial_number": eq.get("serial_number", ""),
        "warranty_end": warranty_end,
        "coverage_type": coverage_type,
        "exclusions": data.get("exclusions", ""),
        "created_at": _now(),
    }
    await db.crm2_contract_assets.insert_one(asset)
    asset.pop("_id", None)
    return {"success": True, "contract_id": contract_id, "asset": asset}



# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT / MULTI-SITE PTE SERVICE  (Phase 1 — foundation & visibility)
# ════════════════════════════════════════════════════════════════════

BLUE_LIGHT_CUSTOMER_TYPES = [
    {"id": "fire_rescue", "name": "Fire & Rescue Service"},
    {"id": "police", "name": "Police"},
    {"id": "ambulance", "name": "Ambulance Service"},
    {"id": "combined_emergency", "name": "Combined Emergency Services"},
    {"id": "public_sector", "name": "Other public-sector multi-site organisation"},
]

# Default calibration + service profile for a Blue Light contract. Every value
# is overridable per contract by an authorised admin (§53). Speed/incline points
# match the approved Pulse Fire & Rescue certificate. Failure = variance strictly
# outside the tolerance band (default 5% of target).
DEFAULT_BLUE_LIGHT_CONFIG = {
    "customer_type": "fire_rescue",
    "service_frequency_months": 6,
    "calibration_required": True,
    "speed_points_mph": [3, 6, 9, 12],
    "incline_points_pct": [0, 5, 10, 15],
    "tolerance_pct": 5.0,               # speed + non-zero incline: |measured-target|/target*100
    "incline_zero_abs_tolerance": 0.5,  # absolute tolerance when target incline is 0%
    "review_pct": None,                 # optional amber band (< tolerance_pct); null = no amber
    "asset_audit_required": True,
    "certificate_approval_mode": "office_review",  # auto_send | office_review | manager_approval
    "certificate_template_id": None,
    "customer_logo_url": None,
    "certificate_recipients": [],        # contract-level recipient emails
    "office_notification_emails": [],    # internal office ops emails for transfer/ops alerts
    "mandatory_check_sheets": [],
    "engineer_skills_required": [],
}

CERT_APPROVAL_MODES = ["auto_send", "office_review", "manager_approval"]

_TREADMILL_HINTS = ("treadmill", "run ", "runner", "tread ")


def _is_treadmill(asset: dict) -> bool:
    blob = " ".join(str(asset.get(k, "")) for k in
                     ("asset_name", "model_code", "equipment_type", "type", "category")).lower()
    return any(h in blob for h in _TREADMILL_HINTS)


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _get_bl_contract(contract_id: str, user: dict) -> dict:
    c = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    return c


@router.get("/blue-light/customer-types")
async def blue_light_customer_types(user=Depends(get_crm_user)):
    return {"customer_types": BLUE_LIGHT_CUSTOMER_TYPES,
            "approval_modes": CERT_APPROVAL_MODES,
            "defaults": DEFAULT_BLUE_LIGHT_CONFIG}


@router.put("/contracts/{contract_id}/blue-light-config")
async def set_blue_light_config(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Mark a contract as a Blue Light / Multi-Site PTE Service contract and
    save its configurable service + calibration + certificate profile (§1, §53).
    Non-destructive: merges over the existing config so partial updates work."""
    existing = await _get_bl_contract(contract_id, user)
    cfg = {**DEFAULT_BLUE_LIGHT_CONFIG, **(existing.get("blue_light") or {})}
    incoming = data.get("blue_light") if isinstance(data.get("blue_light"), dict) else data
    for k, v in (incoming or {}).items():
        if k in DEFAULT_BLUE_LIGHT_CONFIG:
            cfg[k] = v
    # Validation / coercion
    if cfg.get("certificate_approval_mode") not in CERT_APPROVAL_MODES:
        cfg["certificate_approval_mode"] = "office_review"
    valid_ct = {t["id"] for t in BLUE_LIGHT_CUSTOMER_TYPES}
    if cfg.get("customer_type") not in valid_ct:
        cfg["customer_type"] = "fire_rescue"
    try:
        cfg["tolerance_pct"] = float(cfg.get("tolerance_pct") or 5.0)
        cfg["service_frequency_months"] = int(cfg.get("service_frequency_months") or 6)
        cfg["speed_points_mph"] = [float(x) for x in (cfg.get("speed_points_mph") or [])]
        cfg["incline_points_pct"] = [float(x) for x in (cfg.get("incline_points_pct") or [])]
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid numeric value in calibration config")
    onc = cfg.get("office_notification_emails")
    if isinstance(onc, str):
        cfg["office_notification_emails"] = [e.strip() for e in onc.replace(";", ",").split(",") if e.strip()]
    updates = {
        "contract_type": "blue_light_multisite",
        "is_blue_light": True,
        "customer_type": cfg.get("customer_type"),
        "blue_light": cfg,
        "updated_at": _now(),
    }
    await db.crm2_contracts.update_one({"id": contract_id, **_of(user)}, {"$set": updates})
    await record_audit(entity_type="contract", entity_id=contract_id,
                       action="blue_light_config", user=user, after=updates)
    return {"success": True, "blue_light": cfg, "contract_type": "blue_light_multisite"}


async def _station_rows(contract_id: str, user: dict):
    """Build the per-station matrix: joins contract_sites → contract_assets and
    any recorded station visits / certificates (future collections; safe-empty)."""
    sites = await db.crm2_contract_sites.find(
        {"contract_id": contract_id}, {"_id": 0}).to_list(2000)
    assets = await db.crm2_contract_assets.find(
        {"contract_id": contract_id}, {"_id": 0}).to_list(20000)
    # index assets by site
    by_site: dict[str, list] = {}
    for a in assets:
        by_site.setdefault(a.get("site_id") or "", []).append(a)
    # future: recorded visits + certificates (empty until Phase 3/4)
    visits = {}
    try:
        async for v in db.crm2_station_visits.find({"contract_id": contract_id}, {"_id": 0}):
            visits[v.get("site_id")] = v
    except Exception:
        pass
    certs = {}
    try:
        async for cert in db.crm2_certificates.find({"contract_id": contract_id}, {"_id": 0}):
            certs.setdefault(cert.get("site_id"), cert)
    except Exception:
        pass
    today = _today_str()
    rows = []
    for s in sites:
        sid = s.get("id")
        sassets = by_site.get(sid, [])
        treadmills = [a for a in sassets if _is_treadmill(a)]
        visit = visits.get(sid) or {}
        cert = certs.get(sid) or {}
        next_due = s.get("next_service_due") or ""
        scheduled = s.get("scheduled_date") or visit.get("scheduled_date") or ""
        vstatus = (visit.get("status") or s.get("visit_status") or "").strip()
        if not vstatus:
            if scheduled:
                vstatus = "scheduled"
            elif next_due and next_due < today:
                vstatus = "overdue"
            else:
                vstatus = "not_planned"
        rows.append({
            "site_id": sid,
            "visit_id": visit.get("id", ""),
            "station_name": s.get("site_name", ""),
            "address": ", ".join([x for x in [s.get("address"), s.get("city"), s.get("postcode")] if x]),
            "postcode": s.get("postcode", ""),
            "contact_name": s.get("contact_name", ""),
            "telephone": s.get("telephone", s.get("phone", "")),
            "email": s.get("email", ""),
            "asset_count": len(sassets),
            "treadmill_count": len(treadmills),
            "last_service": s.get("last_service", visit.get("completed_at", "")),
            "next_service_due": next_due,
            "scheduled_date": scheduled,
            "assigned_engineer_id": s.get("assigned_engineer_id", visit.get("assigned_engineer_id", "")),
            "assigned_engineer_name": s.get("assigned_engineer_name", visit.get("assigned_engineer_name", "")),
            "visit_status": vstatus,
            "asset_audit_status": visit.get("asset_audit_status", "pending" if sassets else "n/a"),
            "calibration_status": visit.get("calibration_status",
                                            ("pending" if treadmills else "n/a")),
            "faults_raised": int(visit.get("faults_raised", 0) or 0),
            "certificate_status": cert.get("status", "outstanding"),
            "certificate_sent_date": cert.get("sent_at", ""),
            "follow_up_required": bool(s.get("follow_up_required", visit.get("follow_up_required", False))),
        })
    return rows


@router.get("/contracts/{contract_id}/overview")
async def blue_light_overview(contract_id: str, user=Depends(get_crm_user)):
    """Operational contract overview stats (§2) — reads linked stations + assets
    + any recorded visits/certificates. Works before any visit exists (defaults)."""
    c = await _get_bl_contract(contract_id, user)
    rows = await _station_rows(contract_id, user)
    today = _today_str()
    n = len(rows)
    completed = sum(1 for r in rows if r["visit_status"] in ("completed", "certificate_generated", "certificate_sent"))
    scheduled = sum(1 for r in rows if r["visit_status"] == "scheduled")
    overdue = sum(1 for r in rows if r["visit_status"] == "overdue"
                  or (r["next_service_due"] and r["next_service_due"] < today
                      and r["visit_status"] not in ("completed", "certificate_generated", "certificate_sent")))
    awaiting = sum(1 for r in rows if r["visit_status"] == "not_planned")
    certs_done = sum(1 for r in rows if r["certificate_status"] in ("generated", "sent"))
    certs_sent = sum(1 for r in rows if r["certificate_status"] == "sent")
    cert_breakdown = {
        "total_stations": n,
        "generated": sum(1 for r in rows if r["certificate_status"] in ("generated", "sent", "awaiting_review")),
        "sent": certs_sent,
        "awaiting_review": sum(1 for r in rows if r["certificate_status"] == "awaiting_review"),
        "send_failed": sum(1 for r in rows if r["certificate_status"] == "send_failed"),
        "outstanding": sum(1 for r in rows if r["certificate_status"] in ("outstanding", "")),
    }
    faults_open = sum(r["faults_raised"] for r in rows)
    follow_ups = sum(1 for r in rows if r["follow_up_required"])
    total_assets = sum(r["asset_count"] for r in rows)
    total_treadmills = sum(r["treadmill_count"] for r in rows)
    future_due = sorted([r["next_service_due"] for r in rows
                         if r["next_service_due"] and r["next_service_due"] >= today])
    discrepancies = (
        await db.crm2_contract_assets.count_documents({"contract_id": contract_id, "office_review": True})
        + await db.crm2_asset_verifications.count_documents({"contract_id": contract_id, "action": "not_found"})
        + await db.crm2_asset_transfers.count_documents({"contract_id": contract_id, "status": "pending"})
    )
    return {
        "contract": {
            "id": c["id"], "contract_number": c.get("contract_number"),
            "title": c.get("title"), "company_name": c.get("company_name"),
            "customer_type": c.get("customer_type"),
            "start_date": c.get("start_date"), "end_date": c.get("end_date"),
            "is_blue_light": bool(c.get("is_blue_light")),
            "blue_light": c.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG,
        },
        "stats": {
            "sites": n,
            "assets": total_assets,
            "treadmills": total_treadmills,
            "service_frequency_months": (c.get("blue_light") or {}).get("service_frequency_months", 6),
            "visits_completed": completed,
            "visits_scheduled": scheduled,
            "visits_awaiting_booking": awaiting,
            "visits_overdue": overdue,
            "visits_outstanding": n - completed,
            "certificates_completed": certs_done,
            "certificates_sent": certs_sent,
            "certificates_outstanding": n - certs_done,
            "certificates_breakdown": cert_breakdown,
            "open_faults": faults_open,
            "follow_ups_required": follow_ups,
            "asset_discrepancies": discrepancies,
            "next_planned_service_date": future_due[0] if future_due else "",
            "completion_pct": round(completed / n * 100) if n else 0,
        },
    }


@router.get("/contracts/{contract_id}/stations")
async def blue_light_station_matrix(
    contract_id: str,
    search: str = "", status: str = "", engineer_id: str = "", cert_status: str = "",
    sort: str = "station_name", direction: str = "asc",
    user=Depends(get_crm_user),
):
    """Station service matrix (§3) with search / filter / sort."""
    await _get_bl_contract(contract_id, user)
    rows = await _station_rows(contract_id, user)
    if search:
        q = search.lower()
        rows = [r for r in rows if q in (r["station_name"] or "").lower()
                or q in (r["address"] or "").lower()
                or q in (r["contact_name"] or "").lower()
                or q in (r["postcode"] or "").lower()]
    if status:
        rows = [r for r in rows if r["visit_status"] == status]
    if cert_status:
        if cert_status == "outstanding":
            rows = [r for r in rows if r["certificate_status"] in ("outstanding", "")]
        else:
            rows = [r for r in rows if r["certificate_status"] == cert_status]
    if engineer_id:
        rows = [r for r in rows if r["assigned_engineer_id"] == engineer_id]
    reverse = direction == "desc"
    try:
        rows.sort(key=lambda r: (r.get(sort) is None, r.get(sort)), reverse=reverse)
    except TypeError:
        rows.sort(key=lambda r: str(r.get(sort) or ""), reverse=reverse)
    return {"stations": rows, "count": len(rows)}


@router.put("/contracts/{contract_id}/stations/{site_id}")
async def update_contract_station(contract_id: str, site_id: str, data: dict, user=Depends(get_crm_user)):
    """Edit a station's operational fields (contact, next due, engineer, follow-up).
    Reuses the existing crm2_contract_sites collection (no duplicate site record)."""
    await _get_bl_contract(contract_id, user)
    allowed = {"contact_name", "telephone", "phone", "email", "access_instructions",
               "parking_info", "opening_times", "site_notes", "next_service_due",
               "scheduled_date", "last_service", "assigned_engineer_id",
               "assigned_engineer_name", "visit_status", "follow_up_required"}
    updates = {k: v for k, v in (data or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No editable station fields supplied")
    updates["updated_at"] = _now()
    res = await db.crm2_contract_sites.update_one(
        {"id": site_id, "contract_id": contract_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Station not found on this contract")
    return {"success": True, "updates": updates}


@router.get("/contracts/{contract_id}/stations.csv")
async def blue_light_station_matrix_csv(contract_id: str, user=Depends(get_crm_user)):
    """CSV export of the station matrix (§3 Export)."""
    import csv
    import io
    from fastapi.responses import StreamingResponse
    await _get_bl_contract(contract_id, user)
    rows = await _station_rows(contract_id, user)
    cols = ["station_name", "address", "postcode", "contact_name", "telephone", "email",
            "asset_count", "treadmill_count", "last_service", "next_service_due",
            "scheduled_date", "assigned_engineer_name", "visit_status",
            "asset_audit_status", "calibration_status", "faults_raised",
            "certificate_status", "certificate_sent_date", "follow_up_required"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.replace("_", " ").title() for c in cols])
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=stations-{contract_id[:8]}.csv"})


# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — PHASE 2: BULK SERVICE PLANNING → ENGINEER JOB PACKS
# ════════════════════════════════════════════════════════════════════

_OPEN_VISIT_STATES = ("scheduled", "planned", "travelling", "on_site",
                      "in_progress", "awaiting_information", "follow_up_required")


def _cycle_tag(scheduled_date: str, freq_months: int) -> tuple[str, str]:
    """Return (cycle_tag, human label) for duplicate-protection + display.
    Buckets by the contract service frequency so two visits in the same
    service window collide (§61)."""
    try:
        dt = datetime.fromisoformat(scheduled_date[:10])
    except (ValueError, TypeError):
        dt = datetime.now(timezone.utc)
    y = dt.year
    if freq_months >= 12:
        return f"{y}", f"{y} Annual"
    if freq_months >= 6:
        half = 1 if dt.month <= 6 else 2
        return f"{y}-H{half}", f"H{half} {y}"
    if freq_months >= 3:
        q = (dt.month - 1) // 3 + 1
        return f"{y}-Q{q}", f"Q{q} {y}"
    return f"{y}-M{dt.month:02d}", dt.strftime("%b %Y")


async def _engineer_name(org_id: str, engineer_id: str) -> str:
    if not engineer_id:
        return ""
    e = await db.svc_engineers.find_one(
        {"id": engineer_id, "organization_id": org_id}, {"_id": 0, "full_name": 1})
    return (e or {}).get("full_name", "")


@router.get("/contracts/{contract_id}/engineers")
async def blue_light_engineers(contract_id: str, user=Depends(get_crm_user)):
    """Available engineers for allocation (reuses svc_engineers — no new roster)."""
    c = await _get_bl_contract(contract_id, user)
    org_id = c.get("organization_id")
    rows = await db.svc_engineers.find(
        {"organization_id": org_id, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "skills": 1, "home_postcode": 1},
    ).sort("full_name", 1).to_list(500)
    # live open Blue Light job counts per engineer for capacity awareness
    load = {}
    async for v in db.crm2_station_visits.find(
            {"contract_id": contract_id, "status": {"$in": list(_OPEN_VISIT_STATES)}},
            {"_id": 0, "assigned_engineer_id": 1}):
        eid = v.get("assigned_engineer_id")
        if eid:
            load[eid] = load.get(eid, 0) + 1
    for r in rows:
        r["planned_visits"] = load.get(r["id"], 0)
    return {"engineers": rows, "count": len(rows)}


def _build_job_pack(contract: dict, site: dict, assets: list) -> dict:
    """Pre-visit engineer job pack (§5): station + contract + expected asset
    register with treadmill-calibration flags."""
    bl = contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG
    expected = []
    for a in assets:
        name = a.get("asset_name", "")
        manu = name.split(" ")[0] if name else ""
        expected.append({
            "asset_id": a.get("asset_id") or a.get("id"),
            "contract_asset_id": a.get("id"),
            "asset_name": name,
            "manufacturer": manu,
            "model_code": a.get("model_code", ""),
            "serial_number": a.get("serial_number", ""),
            "equipment_type": a.get("equipment_type", ""),
            "is_treadmill": _is_treadmill(a),
            "location": site.get("site_name", ""),
            "warranty_end": a.get("warranty_end", ""),
        })
    treadmills = [e for e in expected if e["is_treadmill"]]
    return {
        "contract_id": contract["id"],
        "contract_number": contract.get("contract_number", ""),
        "customer_type": contract.get("customer_type", ""),
        "company_name": contract.get("company_name", ""),
        "station_name": site.get("site_name", ""),
        "station": {
            "address": site.get("address", ""), "city": site.get("city", ""),
            "postcode": site.get("postcode", ""),
            "contact_name": site.get("contact_name", ""),
            "telephone": site.get("telephone", site.get("phone", "")),
            "email": site.get("email", ""),
            "access_instructions": site.get("access_instructions", ""),
            "parking_info": site.get("parking_info", ""),
            "opening_times": site.get("opening_times", ""),
            "site_notes": site.get("site_notes", ""),
        },
        "expected_assets": expected,
        "expected_asset_count": len(expected),
        "treadmill_count": len(treadmills),
        "calibration": {
            "required": bool(bl.get("calibration_required", True)) and bool(treadmills),
            "speed_points_mph": bl.get("speed_points_mph", [3, 6, 9, 12]),
            "incline_points_pct": bl.get("incline_points_pct", [0, 5, 10, 15]),
            "tolerance_pct": bl.get("tolerance_pct", 5.0),
            "incline_zero_abs_tolerance": bl.get("incline_zero_abs_tolerance", 0.5),
        },
        "asset_audit_required": bool(bl.get("asset_audit_required", True)),
    }


async def _create_engineer_job(contract: dict, site: dict, visit: dict, pack: dict,
                                engineer_id: str, engineer_name: str, user: dict) -> str:
    """Create the engineer job in the existing svc_cases collection (case_type=ppm,
    service_kind=blue_light) carrying the pre-visit pack. No duplicate job system."""
    from routes.svc.cases import next_reference, compute_sla_targets
    from utils.svc_state import NEW, ASSIGNED
    org_id = contract.get("organization_id")
    reference = await next_reference(org_id)
    sla = await compute_sla_targets(organization_id=org_id, priority="p3", cover_type="contract")
    job_id = _id()
    doc = {
        "id": job_id, "organization_id": org_id, "reference": reference,
        "status": ASSIGNED if engineer_id else NEW,
        "priority": "p3", "cover_type": "contract", "case_type": "ppm",
        "service_kind": "blue_light",
        "title": f"Blue Light Service — {site.get('site_name', '')}",
        "description": (f"Multi-site PTE service & calibration visit for "
                        f"{site.get('site_name', '')} ({contract.get('company_name', '')}). "
                        f"{pack['expected_asset_count']} assets · {pack['treadmill_count']} treadmills."),
        "site_id": site.get("id", ""), "site_name": site.get("site_name", ""),
        "site_postcode": site.get("postcode", ""),
        "contract_id": contract["id"], "contract_site_id": site.get("id", ""),
        "station_visit_id": visit["id"],
        "customer_name": contract.get("company_name", ""),
        "customer_email": site.get("email", ""),
        "customer_phone": site.get("telephone", site.get("phone", "")),
        "equipment_ids": [e["asset_id"] for e in pack["expected_assets"] if e["asset_id"]],
        "equipment_serials": [e["serial_number"] for e in pack["expected_assets"] if e["serial_number"]],
        "assigned_engineer_id": engineer_id or "",
        "assigned_engineer_name": engineer_name or "",
        "scheduled_at": visit.get("scheduled_date") or None,
        "estimated_minutes": max(45, pack["expected_asset_count"] * 12 + pack["treadmill_count"] * 20),
        "sla_response_at": sla.get("sla_response_at"),
        "sla_resolve_at": sla.get("sla_resolve_at"),
        "blue_light": pack,
        "source": "blue_light_planner",
        "logged_by_id": user.get("id"),
        "logged_by_name": user.get("full_name") or user.get("email") or "",
        "created_at": _now(), "updated_at": _now(),
    }
    await db.svc_cases.insert_one(doc)
    return job_id


@router.post("/contracts/{contract_id}/plan-visits")
async def blue_light_plan_visits(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Bulk-schedule stations, allocate an engineer, and auto-create the
    pre-visit engineer job packs (§4/§5). Duplicate-protected per service
    cycle (§61) unless force=true."""
    contract = await _get_bl_contract(contract_id, user)
    org_id = contract.get("organization_id")
    site_ids = data.get("site_ids") or []
    if not site_ids:
        raise HTTPException(400, "Select at least one station to plan")
    scheduled_date = (data.get("scheduled_date") or "").strip()
    if not scheduled_date:
        raise HTTPException(400, "A scheduled date is required")
    window_end = (data.get("service_window_end") or "").strip()
    engineer_id = (data.get("engineer_id") or "").strip()
    engineer_name = data.get("engineer_name") or await _engineer_name(org_id, engineer_id)
    force = bool(data.get("force"))
    freq = int((contract.get("blue_light") or {}).get("service_frequency_months", 6))
    cycle_tag, cycle_label = _cycle_tag(scheduled_date, freq)

    created, skipped = [], []
    for sid in site_ids:
        site = await db.crm2_contract_sites.find_one({"id": sid, "contract_id": contract_id}, {"_id": 0})
        if not site:
            skipped.append({"site_id": sid, "reason": "Station not found"})
            continue
        if not force:
            dupe = await db.crm2_station_visits.find_one(
                {"contract_id": contract_id, "site_id": sid, "cycle_tag": cycle_tag,
                 "status": {"$in": list(_OPEN_VISIT_STATES)}}, {"_id": 0, "id": 1})
            if dupe:
                skipped.append({"site_id": sid, "station_name": site.get("site_name", ""),
                                "reason": f"A visit already exists for this station in the {cycle_label} service cycle"})
                continue
        assets = await db.crm2_contract_assets.find(
            {"contract_id": contract_id, "site_id": sid}, {"_id": 0}).to_list(2000)
        pack = _build_job_pack(contract, site, assets)
        visit = {
            "id": _id(), "contract_id": contract_id, "organization_id": org_id,
            "site_id": sid, "station_name": site.get("site_name", ""),
            "cycle_tag": cycle_tag, "service_cycle_label": cycle_label,
            "status": "scheduled",
            "scheduled_date": scheduled_date, "service_window_end": window_end,
            "assigned_engineer_id": engineer_id, "assigned_engineer_name": engineer_name,
            "expected_asset_count": pack["expected_asset_count"],
            "treadmill_count": pack["treadmill_count"],
            "calibration_required": pack["calibration"]["required"],
            "calibration_status": "pending" if pack["treadmill_count"] else "n/a",
            "asset_audit_status": "pending" if pack["expected_asset_count"] else "n/a",
            "faults_raised": 0, "follow_up_required": False,
            "created_by": user.get("id"), "created_at": _now(), "updated_at": _now(),
        }
        job_id = await _create_engineer_job(contract, site, visit, pack,
                                            engineer_id, engineer_name, user)
        visit["svc_case_id"] = job_id
        await db.crm2_station_visits.insert_one(visit)
        # reflect on the station row so the matrix + overview update immediately
        await db.crm2_contract_sites.update_one(
            {"id": sid, "contract_id": contract_id},
            {"$set": {"scheduled_date": scheduled_date, "visit_status": "scheduled",
                      "assigned_engineer_id": engineer_id, "assigned_engineer_name": engineer_name,
                      "service_cycle_tag": cycle_tag, "updated_at": _now()}})
        created.append({"site_id": sid, "station_name": site.get("site_name", ""),
                        "visit_id": visit["id"], "svc_case_id": job_id})

    await record_audit(entity_type="contract", entity_id=contract_id, action="plan_visits",
                       user=user, after={"created": len(created), "skipped": len(skipped),
                                         "cycle": cycle_tag, "engineer_id": engineer_id})
    return {"success": True, "created": created, "skipped": skipped,
            "created_count": len(created), "skipped_count": len(skipped),
            "cycle_tag": cycle_tag, "cycle_label": cycle_label}


@router.post("/contracts/{contract_id}/reassign-visits")
async def blue_light_reassign_visits(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Bulk-reassign the engineer on selected stations' open visits + jobs (§4)."""
    contract = await _get_bl_contract(contract_id, user)
    org_id = contract.get("organization_id")
    site_ids = data.get("site_ids") or []
    engineer_id = (data.get("engineer_id") or "").strip()
    if not site_ids:
        raise HTTPException(400, "Select at least one station")
    engineer_name = data.get("engineer_name") or await _engineer_name(org_id, engineer_id)
    updated = 0
    for sid in site_ids:
        v = await db.crm2_station_visits.find_one(
            {"contract_id": contract_id, "site_id": sid, "status": {"$in": list(_OPEN_VISIT_STATES)}},
            {"_id": 0, "id": 1, "svc_case_id": 1})
        if not v:
            continue
        await db.crm2_station_visits.update_one(
            {"id": v["id"]}, {"$set": {"assigned_engineer_id": engineer_id,
                                       "assigned_engineer_name": engineer_name, "updated_at": _now()}})
        if v.get("svc_case_id"):
            from utils.svc_state import ASSIGNED, NEW
            await db.svc_cases.update_one(
                {"id": v["svc_case_id"]},
                {"$set": {"assigned_engineer_id": engineer_id, "assigned_engineer_name": engineer_name,
                          "status": ASSIGNED if engineer_id else NEW, "updated_at": _now()}})
        await db.crm2_contract_sites.update_one(
            {"id": sid, "contract_id": contract_id},
            {"$set": {"assigned_engineer_id": engineer_id, "assigned_engineer_name": engineer_name,
                      "updated_at": _now()}})
        updated += 1
    return {"success": True, "updated": updated,
            "engineer_id": engineer_id, "engineer_name": engineer_name}


@router.delete("/contracts/{contract_id}/visits/{site_id}")
async def blue_light_unschedule_visit(contract_id: str, site_id: str, user=Depends(get_crm_user)):
    """Cancel an open planned visit for a station (frees it for re-planning)."""
    await _get_bl_contract(contract_id, user)
    v = await db.crm2_station_visits.find_one(
        {"contract_id": contract_id, "site_id": site_id, "status": {"$in": list(_OPEN_VISIT_STATES)}},
        {"_id": 0, "id": 1, "svc_case_id": 1})
    if not v:
        raise HTTPException(404, "No open planned visit for this station")
    await db.crm2_station_visits.update_one(
        {"id": v["id"]}, {"$set": {"status": "cancelled", "updated_at": _now()}})
    if v.get("svc_case_id"):
        await db.svc_cases.update_one({"id": v["svc_case_id"]},
                                      {"$set": {"status": "cancelled", "updated_at": _now()}})
    await db.crm2_contract_sites.update_one(
        {"id": site_id, "contract_id": contract_id},
        {"$set": {"visit_status": "not_planned", "scheduled_date": "",
                  "assigned_engineer_id": "", "assigned_engineer_name": "", "updated_at": _now()}})
    return {"success": True}



# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — PHASE 3: ENGINEER GUIDED SERVICE + CALIBRATION WIZARD
# ════════════════════════════════════════════════════════════════════

VISIT_STEPS = ["asset_check", "service", "calibration", "faults", "review", "sign"]


async def _get_visit(visit_id: str, user: dict) -> dict:
    v = await db.crm2_station_visits.find_one({"id": visit_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Service visit not found")
    # ownership via the parent contract (tenant boundary — §63/§64)
    await _get_bl_contract(v["contract_id"], user)
    return v


def _calc_calibration(speed_rows, incline_rows, cfg):
    """Compute pass/review/fail per test + overall (§17). Failure = variance
    strictly outside tolerance (% of target; absolute band when target is 0)."""
    tol = float(cfg.get("tolerance_pct") or 5.0)
    review = cfg.get("review_pct")
    zero_abs = float(cfg.get("incline_zero_abs_tolerance") or 0.5)

    def grade(target, measured, is_incline):
        try:
            t = float(target); m = float(measured)
        except (TypeError, ValueError):
            return {"target": target, "measured": measured, "variance": None,
                    "variance_pct": None, "result": "incomplete"}
        var = round(m - t, 3)
        if t == 0:
            res = "pass" if abs(m) <= zero_abs else "fail"
            return {"target": t, "measured": m, "variance": var,
                    "variance_pct": None, "result": res}
        pct = round(abs(var) / abs(t) * 100, 2)
        if pct > tol:
            res = "fail"
        elif review is not None and pct > float(review):
            res = "review"
        else:
            res = "pass"
        return {"target": t, "measured": m, "variance": var, "variance_pct": pct, "result": res}

    speed = [grade(r.get("target"), r.get("measured"), False) for r in (speed_rows or [])]
    incline = [grade(r.get("target"), r.get("measured"), True) for r in (incline_rows or [])]
    allr = speed + incline
    if any(x["result"] == "incomplete" for x in allr) or not allr:
        overall = "incomplete"
    elif any(x["result"] == "fail" for x in allr):
        overall = "fail"
    elif any(x["result"] == "review" for x in allr):
        overall = "review"
    else:
        overall = "pass"
    return speed, incline, overall


async def _visit_state(visit: dict, user: dict) -> dict:
    """Assemble the full wizard state + progress + completion blockers (§22)."""
    contract = await db.crm2_contracts.find_one({"id": visit["contract_id"]}, {"_id": 0})
    pack = None
    job = await db.svc_cases.find_one({"id": visit.get("svc_case_id")}, {"_id": 0, "blue_light": 1})
    if job:
        pack = job.get("blue_light")
    if not pack:
        assets = await db.crm2_contract_assets.find(
            {"contract_id": visit["contract_id"], "site_id": visit["site_id"]}, {"_id": 0}).to_list(2000)
        site = await db.crm2_contract_sites.find_one({"id": visit["site_id"]}, {"_id": 0}) or {}
        pack = _build_job_pack(contract or {}, site, assets)

    verifs = {v["asset_key"]: v for v in await db.crm2_asset_verifications.find(
        {"visit_id": visit["id"]}, {"_id": 0}).to_list(5000)}
    calibs = {cr["asset_key"]: cr for cr in await db.crm2_calibration_records.find(
        {"visit_id": visit["id"]}, {"_id": 0}).sort("created_at", 1).to_list(5000)}
    fault_rows = await db.svc_cases.find(
        {"station_visit_id": visit["id"], "case_type": "reactive"},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "priority": 1,
         "asset_serial": 1, "out_of_service": 1, "status": 1}).to_list(500)

    expected = pack.get("expected_assets", [])
    # merge audit verification onto each expected asset + include added assets
    audited = []
    for a in expected:
        key = a.get("contract_asset_id") or a.get("asset_id") or a.get("serial_number")
        ver = verifs.get(key)
        audited.append({**a, "asset_key": key,
                        "audit": ver.get("action") if ver else None,
                        "audit_status": "done" if ver else "pending",
                        "service_outcome": (ver or {}).get("service_outcome"),
                        "changes": (ver or {}).get("changes")})
    known = {a["asset_key"] for a in audited}
    for key, ver in verifs.items():
        if key not in known and ver.get("action") == "add":
            na = ver.get("new_asset") or {}
            audited.append({"asset_key": key, "asset_name": na.get("asset_name", "New asset"),
                            "serial_number": na.get("serial_number", ""),
                            "equipment_type": na.get("equipment_type", ""),
                            "is_treadmill": _is_treadmill(na), "audit": "add",
                            "audit_status": "done", "service_outcome": ver.get("service_outcome"),
                            "is_new": True})

    # progress counters
    expected_count = len([a for a in audited if a.get("audit") != "not_found"])
    accounted = len([a for a in audited if a.get("audit_status") == "done"])
    present_assets = [a for a in audited if a.get("audit") in ("present", "update", "replaced", "add")]
    serviced = len([a for a in present_assets if a.get("service_outcome")])
    treadmills = [a for a in present_assets if a.get("is_treadmill")]
    calibrated = [t for t in treadmills if calibs.get(t["asset_key"], {}).get("overall") not in (None, "incomplete")]

    # completion blockers (§22) — plain English
    blockers = []
    unaccounted = [a for a in audited if a.get("audit_status") != "done"]
    if unaccounted:
        blockers.append({"type": "asset_audit",
                         "message": f"{len(unaccounted)} asset(s) still need to be confirmed, updated or marked as not found.",
                         "asset_key": unaccounted[0]["asset_key"]})
    unserviced = [a for a in present_assets if not a.get("service_outcome")]
    if unserviced:
        blockers.append({"type": "service",
                         "message": f"{len(unserviced)} machine(s) still need a service outcome recorded.",
                         "asset_key": unserviced[0]["asset_key"]})
    if pack.get("calibration", {}).get("required"):
        pending_cal = [t for t in treadmills if t not in calibrated]
        if pending_cal:
            t0 = pending_cal[0]
            blockers.append({"type": "calibration",
                             "message": f"Treadmill {t0.get('serial_number') or t0.get('asset_name')} still requires calibration.",
                             "asset_key": t0["asset_key"]})

    return {
        "visit": visit, "pack": pack,
        "contract": {"id": contract.get("id"), "contract_number": contract.get("contract_number"),
                     "company_name": contract.get("company_name"),
                     "customer_type": contract.get("customer_type"),
                     "blue_light": contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG} if contract else {},
        "assets": audited,
        "calibrations": calibs,
        "faults": fault_rows,
        "progress": {
            "expected_assets": expected_count, "accounted": accounted,
            "confirmed": len([a for a in audited if a.get("audit") == "present"]),
            "updated": len([a for a in audited if a.get("audit") == "update"]),
            "new": len([a for a in audited if a.get("audit") == "add"]),
            "not_found": len([a for a in audited if a.get("audit") == "not_found"]),
            "serviced": serviced, "to_service": len(present_assets),
            "treadmills_required": len(treadmills), "treadmills_calibrated": len(calibrated),
            "faults_raised": len(fault_rows),
            "assets_remaining": len(unaccounted),
        },
        "completion_blockers": blockers,
        "can_complete": len(blockers) == 0,
        "steps": VISIT_STEPS,
    }


@router.get("/visits/{visit_id}")
async def blue_light_visit_state(visit_id: str, user=Depends(get_crm_user)):
    visit = await _get_visit(visit_id, user)
    return await _visit_state(visit, user)


@router.post("/visits/{visit_id}/start")
async def blue_light_visit_start(visit_id: str, data: dict, user=Depends(get_crm_user)):
    """§6 — engineer confirms they are at the correct station and begins."""
    visit = await _get_visit(visit_id, user)
    if not data.get("confirmed_on_site"):
        raise HTTPException(400, "Please confirm you are at the correct station")
    upd = {"status": "in_progress", "started_at": _now(),
           "confirmed_on_site": True, "gps": data.get("gps"), "updated_at": _now()}
    await db.crm2_station_visits.update_one({"id": visit_id}, {"$set": upd})
    await db.crm2_contract_sites.update_one(
        {"id": visit["site_id"]}, {"$set": {"visit_status": "in_progress", "updated_at": _now()}})
    if visit.get("svc_case_id"):
        await db.svc_cases.update_one({"id": visit["svc_case_id"]},
                                      {"$set": {"status": "in_progress", "updated_at": _now()}})
    return await _visit_state({**visit, **upd}, user)


@router.post("/visits/{visit_id}/assets/{asset_key}/audit")
async def blue_light_asset_audit(visit_id: str, asset_key: str, data: dict, user=Depends(get_crm_user)):
    """§8 — CONFIRM PRESENT / UPDATE / NOT FOUND / REPLACED / ADD NEW.
    Applies approved changes to the asset register with a full audit trail (§36)."""
    visit = await _get_visit(visit_id, user)
    action = (data.get("action") or "").strip()
    if action not in ("present", "update", "not_found", "replaced", "add"):
        raise HTTPException(400, "Invalid audit action")
    now = _now()
    ver = {"visit_id": visit_id, "contract_id": visit["contract_id"], "site_id": visit["site_id"],
           "asset_key": asset_key, "action": action, "reason": data.get("reason", ""),
           "changes": data.get("changes"), "new_asset": data.get("new_asset"),
           "replacement": data.get("replacement"), "photo_url": data.get("photo_url"),
           "engineer_id": user.get("id"), "engineer_name": user.get("full_name") or user.get("email"),
           "at": now}

    if action in ("update", "replaced") and data.get("changes"):
        target = await db.crm2_contract_assets.find_one(
            {"id": asset_key, "contract_id": visit["contract_id"]}, {"_id": 0})
        if target:
            changes = {k: v for k, v in data["changes"].items()
                       if k in ("asset_name", "model_code", "serial_number", "equipment_type",
                                "location", "supplier", "asset_number") and v != target.get(k)}
            if changes:
                await db.crm2_asset_changes.insert_one({
                    "id": _id(), "visit_id": visit_id, "contract_id": visit["contract_id"],
                    "site_id": visit["site_id"], "asset_id": asset_key, "field_changes":
                    {k: {"old": target.get(k), "new": v} for k, v in changes.items()},
                    "engineer_id": user.get("id"), "engineer_name": ver["engineer_name"],
                    "status": "auto_approved", "at": now})
                await db.crm2_contract_assets.update_one(
                    {"id": asset_key}, {"$set": {**changes, "updated_at": now}})
    if action == "add" and data.get("new_asset"):
        na = data["new_asset"]
        new_id = _id()
        await db.crm2_contract_assets.insert_one({
            "id": new_id, "contract_id": visit["contract_id"], "site_id": visit["site_id"],
            "asset_name": na.get("asset_name", ""), "equipment_type": na.get("equipment_type", ""),
            "model_code": na.get("model_code", ""), "serial_number": na.get("serial_number", ""),
            "coverage_type": "full", "discovered_on_visit": visit_id, "office_review": True,
            "created_at": now})
        ver["created_asset_id"] = new_id
    if action == "not_found":
        await db.crm2_contract_assets.update_one(
            {"id": asset_key}, {"$set": {"status": "not_found", "not_found_reason": data.get("reason", ""),
                                         "updated_at": now}})

    await db.crm2_asset_verifications.update_one(
        {"visit_id": visit_id, "asset_key": asset_key}, {"$set": ver}, upsert=True)
    await db.crm2_station_visits.update_one({"id": visit_id}, {"$set": {"updated_at": now}})
    return await _visit_state(visit, user)


def _asset_soft_key(model, name, asset_number) -> str:
    return _norm_serial("".join([model or "", name or "", asset_number or ""]))


@router.get("/visits/{visit_id}/assets/lookup")
async def blue_light_asset_lookup(visit_id: str, serial: str = "", model: str = "",
                                  name: str = "", asset_number: str = "",
                                  user=Depends(get_crm_user)):
    """§37 — find a machine already on the register at ANOTHER station (so the
    engineer can request a transfer instead of creating a duplicate). Matches on
    serial; when serial is blank, on a soft key of model + name + asset number."""
    visit = await _get_visit(visit_id, user)
    can = _norm_serial(serial) if serial else ""
    soft = _asset_soft_key(model, name, asset_number) if not can else ""
    if not can and len(soft) < 4:
        return {"matches": []}
    names = await _station_name_map(visit["contract_id"])
    matches = []
    async for a in db.crm2_contract_assets.find(
            {"contract_id": visit["contract_id"]}, {"_id": 0}):
        if a.get("site_id") == visit["site_id"]:
            continue
        if a.get("status") in ("removed", "rejected"):
            continue
        hit = False
        if can and a.get("serial_number"):
            hit = _norm_serial(a.get("serial_number", "")) == can
        elif soft:
            hit = _asset_soft_key(a.get("model_code"), a.get("asset_name"),
                                  a.get("asset_number")) == soft
        if hit:
            matches.append({
                "asset_id": a["id"], "asset_name": a.get("asset_name", ""),
                "serial_number": a.get("serial_number", ""), "model_code": a.get("model_code", ""),
                "site_id": a.get("site_id"), "station_name": names.get(a.get("site_id"), ""),
                "match": "serial" if can else "details"})
    return {"matches": matches}


@router.post("/visits/{visit_id}/assets/{asset_id}/transfer-request")
async def blue_light_transfer_request(visit_id: str, asset_id: str, data: dict = None,
                                      user=Depends(get_crm_user)):
    """§37 — request moving an asset from its current station to this visit's
    station. Does NOT move it — office approves in Asset Reconciliation."""
    data = data or {}
    visit = await _get_visit(visit_id, user)
    asset = await db.crm2_contract_assets.find_one(
        {"id": asset_id, "contract_id": visit["contract_id"]}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Asset not found on this contract")
    if asset.get("site_id") == visit["site_id"]:
        raise HTTPException(400, "That machine is already registered at this station")
    now = _now()
    existing = await db.crm2_asset_transfers.find_one(
        {"asset_id": asset_id, "contract_id": visit["contract_id"], "status": "pending"}, {"_id": 0, "id": 1})
    tr = {
        "id": existing["id"] if existing else _id(),
        "contract_id": visit["contract_id"], "asset_id": asset_id,
        "from_site_id": asset.get("site_id"), "to_site_id": visit["site_id"],
        "visit_id": visit_id, "asset_name": asset.get("asset_name", ""),
        "serial_number": asset.get("serial_number", ""),
        "reason": data.get("reason", ""), "status": "pending",
        "engineer_id": user.get("id"), "engineer_name": user.get("full_name") or user.get("email"),
        "at": now, "updated_at": now,
    }
    await db.crm2_asset_transfers.update_one(
        {"id": tr["id"]}, {"$set": tr}, upsert=True)
    await db.crm2_asset_verifications.update_one(
        {"visit_id": visit_id, "asset_key": asset_id},
        {"$set": {"visit_id": visit_id, "asset_key": asset_id, "action": "transfer_requested",
                  "site_id": visit["site_id"], "contract_id": visit["contract_id"],
                  "engineer_id": user.get("id"), "engineer_name": tr["engineer_name"], "at": now}},
        upsert=True)
    return await _visit_state(visit, user)



@router.post("/visits/{visit_id}/assets/{asset_key}/service")
async def blue_light_asset_service(visit_id: str, asset_key: str, data: dict, user=Depends(get_crm_user)):
    """§11 — record the service outcome for a machine (check sheet outcome)."""
    visit = await _get_visit(visit_id, user)
    outcome = (data.get("outcome") or "").strip()
    valid = {"serviced_operational", "serviced_minor_issue", "serviced_fault_raised",
             "out_of_service", "unable_to_service", "asset_not_present", "further_visit_required"}
    if outcome not in valid:
        raise HTTPException(400, "Invalid service outcome")
    await db.crm2_asset_verifications.update_one(
        {"visit_id": visit_id, "asset_key": asset_key},
        {"$set": {"service_outcome": outcome, "service_notes": data.get("notes", ""),
                  "check_sheet_id": data.get("check_sheet_id"),
                  "serviced_at": _now(), "serviced_by": user.get("id"),
                  "visit_id": visit_id, "asset_key": asset_key}},
        upsert=True)
    return await _visit_state(visit, user)


@router.post("/visits/{visit_id}/treadmills/{asset_key}/calibration")
async def blue_light_calibration(visit_id: str, asset_key: str, data: dict, user=Depends(get_crm_user)):
    """§14-§19 — record treadmill speed + incline calibration, grade pass/review/fail,
    keep original + retest measurements in history (§17/§20)."""
    visit = await _get_visit(visit_id, user)
    contract = await db.crm2_contracts.find_one({"id": visit["contract_id"]}, {"_id": 0})
    cfg = (contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG)
    speed, incline, overall = _calc_calibration(data.get("speed"), data.get("incline"), cfg)
    now = _now()
    existing = await db.crm2_calibration_records.find_one(
        {"visit_id": visit_id, "asset_key": asset_key}, {"_id": 0})
    entry = {"speed": speed, "incline": incline, "overall": overall,
             "device": data.get("device"), "action_if_fail": data.get("action_if_fail"),
             "is_retest": bool(existing), "engineer_id": user.get("id"),
             "engineer_name": user.get("full_name") or user.get("email"), "at": now}
    if existing:
        history = existing.get("history", [])
        if not history:  # first record becomes the original
            history = [{k: existing.get(k) for k in ("speed", "incline", "overall", "at")}]
        history.append(entry)
        await db.crm2_calibration_records.update_one(
            {"visit_id": visit_id, "asset_key": asset_key},
            {"$set": {"speed": speed, "incline": incline, "overall": overall,
                      "device": data.get("device"), "action_if_fail": data.get("action_if_fail"),
                      "history": history, "updated_at": now}})
    else:
        serial = ""
        a = await db.crm2_contract_assets.find_one({"id": asset_key}, {"_id": 0, "serial_number": 1, "asset_name": 1})
        if a:
            serial = a.get("serial_number", "")
        await db.crm2_calibration_records.insert_one({
            "id": _id(), "visit_id": visit_id, "contract_id": visit["contract_id"],
            "site_id": visit["site_id"], "asset_key": asset_key, "asset_id": asset_key,
            "serial_number": serial, "speed": speed, "incline": incline, "overall": overall,
            "device": data.get("device"), "action_if_fail": data.get("action_if_fail"),
            "history": [entry], "created_at": now, "updated_at": now})
    # keep permanent history against the asset (§20)
    await db.crm2_contract_assets.update_one(
        {"id": asset_key}, {"$push": {"calibration_history": {
            "visit_id": visit_id, "overall": overall, "speed": speed, "incline": incline, "at": now}}})
    st = await _visit_state(visit, user)
    st["last_calibration"] = {"asset_key": asset_key, "overall": overall, "speed": speed, "incline": incline}
    return st


@router.post("/visits/{visit_id}/faults")
async def blue_light_raise_fault(visit_id: str, data: dict, user=Depends(get_crm_user)):
    """§12/§44 — raise a fault using the EXISTING Service Desk (a reactive svc_case),
    prefilled with station/asset/engineer/visit context. No new fault record type."""
    visit = await _get_visit(visit_id, user)
    contract = await db.crm2_contracts.find_one({"id": visit["contract_id"]}, {"_id": 0})
    site = await db.crm2_contract_sites.find_one({"id": visit["site_id"]}, {"_id": 0}) or {}
    org_id = contract.get("organization_id")
    if not (data.get("description") or "").strip():
        raise HTTPException(400, "A fault description is required")
    from routes.svc.cases import next_reference, compute_sla_targets
    from utils.svc_state import NEW
    severity = (data.get("severity") or "p3").lower()
    reference = await next_reference(org_id)
    sla = await compute_sla_targets(organization_id=org_id, priority=severity, cover_type="contract")
    fault = {
        "id": _id(), "organization_id": org_id, "reference": reference, "status": NEW,
        "priority": severity, "cover_type": "contract", "case_type": "reactive",
        "title": data.get("title") or f"Fault — {data.get('asset_name') or site.get('site_name', '')}",
        "description": data["description"],
        "site_id": visit["site_id"], "site_name": site.get("site_name", ""),
        "site_postcode": site.get("postcode", ""),
        "contract_id": visit["contract_id"], "contract_site_id": visit["site_id"],
        "station_visit_id": visit_id,
        "asset_serial": data.get("asset_serial", ""), "asset_key": data.get("asset_key", ""),
        "customer_name": contract.get("company_name", ""),
        "out_of_service": bool(data.get("out_of_service")),
        "safety_concern": bool(data.get("safety_concern")),
        "photos": data.get("photos") or [],
        "assigned_engineer_id": user.get("id"),
        "assigned_engineer_name": user.get("full_name") or user.get("email"),
        "sla_response_at": sla.get("sla_response_at"), "sla_resolve_at": sla.get("sla_resolve_at"),
        "source": "blue_light_visit", "created_at": _now(), "updated_at": _now(),
    }
    await db.svc_cases.insert_one(fault)
    await db.crm2_station_visits.update_one(
        {"id": visit_id}, {"$inc": {"faults_raised": 1}, "$set": {"updated_at": _now()}})
    if data.get("out_of_service") and data.get("asset_key"):
        await db.crm2_contract_assets.update_one(
            {"id": data["asset_key"]}, {"$set": {"status": "out_of_service", "updated_at": _now()}})
    return {"success": True, "fault": {"id": fault["id"], "reference": reference,
                                       "title": fault["title"], "priority": severity}}


@router.post("/visits/{visit_id}/complete")
async def blue_light_visit_complete(visit_id: str, data: dict, user=Depends(get_crm_user)):
    """§22-§24 — dummy-proof completion, capture signature, compute next service date.
    Certificate generation/distribution is handled in Phase 4."""
    visit = await _get_visit(visit_id, user)
    state = await _visit_state(visit, user)
    override = data.get("override_reason")
    if not state["can_complete"] and not override:
        return {"success": False, "blocked": True,
                "completion_blockers": state["completion_blockers"],
                "message": "This visit cannot be completed yet."}
    if not (data.get("signature") or data.get("signature_data")):
        raise HTTPException(400, "An engineer signature is required to complete the visit")
    contract = await db.crm2_contracts.find_one({"id": visit["contract_id"]}, {"_id": 0})
    cfg = contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG
    freq = int(cfg.get("service_frequency_months", 6))
    completed_at = datetime.now(timezone.utc)
    next_due = data.get("next_service_due_override")
    if not next_due:
        nd = completed_at + timedelta(days=int(freq * 30.44))
        next_due = nd.strftime("%Y-%m-%d")
    prog = state["progress"]
    approval = cfg.get("certificate_approval_mode", "office_review")
    cert_status = "awaiting_review" if approval in ("office_review", "manager_approval") else "pending_generation"
    upd = {
        "status": "completed", "completed_at": _now(),
        "completed_by": user.get("id"),
        "engineer_name": data.get("engineer_name") or user.get("full_name") or user.get("email"),
        "signature_data": data.get("signature_data") or data.get("signature"),
        "override_reason": override, "next_service_due": next_due,
        "calibration_status": "complete" if prog["treadmills_required"] else "n/a",
        "asset_audit_status": "complete",
        "certificate_status": cert_status,
        "summary": prog, "updated_at": _now(),
    }
    await db.crm2_station_visits.update_one({"id": visit_id}, {"$set": upd})
    await db.crm2_contract_sites.update_one(
        {"id": visit["site_id"]},
        {"$set": {"visit_status": "completed", "last_service": _now()[:10],
                  "next_service_due": next_due, "scheduled_date": "", "updated_at": _now()}})
    if visit.get("svc_case_id"):
        await db.svc_cases.update_one(
            {"id": visit["svc_case_id"]},
            {"$set": {"status": "repaired", "resolved_at": _now(), "updated_at": _now()}})
    await record_audit(entity_type="station_visit", entity_id=visit_id, action="complete",
                       user=user, after={"next_service_due": next_due, "override": bool(override)})
    # Generate the certificate record now (§25). auto_send also emails it.
    cert = await _generate_certificate(visit_id, user, auto_send=(approval == "auto_send"))
    return {"success": True, "next_service_due": next_due,
            "certificate_status": cert_status, "certificate_id": cert.get("id"),
            "override": bool(override)}


@router.post("/visits/{visit_id}/partial")
async def blue_light_visit_partial(visit_id: str, data: dict, user=Depends(get_crm_user)):
    """§39 — save as a partial visit (no certificate). A follow-up continues the cycle."""
    visit = await _get_visit(visit_id, user)
    await db.crm2_station_visits.update_one(
        {"id": visit_id}, {"$set": {"status": "follow_up_required", "partial_reason": data.get("reason", ""),
                                    "follow_up_required": True, "updated_at": _now()}})
    await db.crm2_contract_sites.update_one(
        {"id": visit["site_id"]}, {"$set": {"visit_status": "follow_up_required",
                                            "follow_up_required": True, "updated_at": _now()}})
    return {"success": True, "status": "follow_up_required"}



# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — PHASE 4: SERVICE & CALIBRATION CERTIFICATE
# ════════════════════════════════════════════════════════════════════


async def _build_cert_pdf_bytes(visit: dict):
    """Assemble the certificate PDF bytes from the stored visit + calibration
    records (final measured values). Returns (bytes, contract, station, filename)."""
    import base64
    from utils.blue_light_certificate_pdf import build_certificate_pdf, certificate_filename, TEMPLATE_VERSION
    contract = await db.crm2_contracts.find_one({"id": visit["contract_id"]}, {"_id": 0}) or {}
    station = await db.crm2_contract_sites.find_one({"id": visit["site_id"]}, {"_id": 0}) or {}
    cfg = contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG
    cal_rows = await db.crm2_calibration_records.find(
        {"visit_id": visit["id"]}, {"_id": 0}).to_list(500)
    treadmills = [{
        "serial_number": c.get("serial_number", ""),
        "asset_name": c.get("asset_name", ""),
        "speed": c.get("speed", []), "incline": c.get("incline", []),
        "overall": c.get("overall"),
    } for c in cal_rows]
    sig = visit.get("signature_data") or ""
    if isinstance(sig, str) and sig.startswith("data:image"):
        try:
            visit = {**visit, "_signature_image_bytes": base64.b64decode(sig.split(",", 1)[1])}
        except Exception:
            pass
    pdf = build_certificate_pdf(contract=contract, station=station, visit=visit,
                                treadmills=treadmills, config=cfg)
    fname = certificate_filename(contract, station, (visit.get("completed_at") or "")[:10])
    return pdf, contract, station, fname, TEMPLATE_VERSION


async def _generate_certificate(visit_id: str, user: dict, auto_send: bool = False) -> dict:
    """Create/refresh the crm2_certificates record + store the PDF, and send it
    when auto_send. Certificate status drives the contract dashboard."""
    import base64
    visit = await db.crm2_station_visits.find_one({"id": visit_id}, {"_id": 0})
    if not visit:
        return {}
    pdf, contract, station, fname, tver = await _build_cert_pdf_bytes(visit)
    cfg = contract.get("blue_light") or DEFAULT_BLUE_LIGHT_CONFIG
    approval = cfg.get("certificate_approval_mode", "office_review")
    status = "sent" if auto_send else ("generated" if approval == "auto_send" else "awaiting_review")
    existing = await db.crm2_certificates.find_one(
        {"visit_id": visit_id}, {"_id": 0, "id": 1})
    cert_id = existing["id"] if existing else _id()
    cert = {
        "id": cert_id, "organization_id": contract.get("organization_id"),
        "contract_id": visit["contract_id"], "site_id": visit["site_id"],
        "visit_id": visit_id, "svc_case_id": visit.get("svc_case_id"),
        "station_name": station.get("site_name"), "filename": fname,
        "template_version": tver, "status": status,
        "generated_at": _now(), "generated_by": user.get("id"),
        "approval_mode": approval,
        "recipients": cfg.get("certificate_recipients", []),
        "updated_at": _now(),
    }
    await db.crm2_certificates.update_one({"visit_id": visit_id}, {"$set": cert}, upsert=True)
    await db.crm2_certificate_files.update_one(
        {"cert_id": cert_id},
        {"$set": {"cert_id": cert_id, "pdf_b64": base64.b64encode(pdf).decode(), "at": _now()}},
        upsert=True)
    await db.crm2_station_visits.update_one(
        {"id": visit_id}, {"$set": {"certificate_status": status, "certificate_id": cert_id}})
    await record_audit(entity_type="certificate", entity_id=cert_id, action="generate",
                       user=user, after={"status": status, "visit_id": visit_id})
    if auto_send:
        await _send_certificate(cert_id, user)
    return cert


async def _send_certificate(cert_id: str, user: dict, override_recipients=None) -> dict:
    import base64
    from utils.email import send_email
    cert = await db.crm2_certificates.find_one({"id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    f = await db.crm2_certificate_files.find_one({"cert_id": cert_id}, {"_id": 0, "pdf_b64": 1})
    if not f:
        raise HTTPException(400, "Certificate file missing — regenerate it")
    recipients = override_recipients or cert.get("recipients") or []
    if not recipients:
        raise HTTPException(400, "No certificate recipients configured for this contract")
    station = cert.get("station_name", "")
    visit = await db.crm2_station_visits.find_one({"id": cert["visit_id"]}, {"_id": 0}) or {}
    html = (f"<p>Dear customer,</p><p>Please find attached the completed Pulse Fitness "
            f"Service &amp; Calibration Certificate for:</p><p><b>{station}</b></p>"
            f"<p>Service completed: {(visit.get('completed_at') or '')[:10]}<br/>"
            f"Engineer: {visit.get('engineer_name', '')}</p>"
            f"<p>Any faults requiring additional action will continue to be managed through the "
            f"Pulse Fitness Service Team.</p><p>Kind regards,<br/>Pulse Fitness Service Team</p>")
    attachments = [{"filename": cert.get("filename", "certificate.pdf"), "content": f["pdf_b64"]}]
    sent_ok, error = True, None
    try:
        await send_email(to=recipients[0], subject=f"{station} — Service & Calibration Certificate",
                         html=html, attachments=attachments,
                         cc=recipients[1:] or None,
                         organization_id=cert.get("organization_id"), kind="blue_light_certificate")
    except Exception as e:  # preview Resend key is a placeholder — record + surface
        sent_ok, error = False, str(e)
    upd = {"status": "sent" if sent_ok else "send_failed", "sent_at": _now() if sent_ok else None,
           "sent_recipients": recipients, "send_error": error, "updated_at": _now()}
    await db.crm2_certificates.update_one({"id": cert_id}, {"$set": upd})
    await db.crm2_station_visits.update_one(
        {"id": cert["visit_id"]}, {"$set": {"certificate_status": upd["status"]}})
    return {"success": sent_ok, "status": upd["status"], "recipients": recipients, "error": error}


@router.post("/visits/{visit_id}/certificate/generate")
async def blue_light_certificate_generate(visit_id: str, user=Depends(get_crm_user)):
    """Manually (re)generate the certificate for a completed visit (§25/§56)."""
    visit = await _get_visit(visit_id, user)
    if visit.get("status") != "completed":
        raise HTTPException(400, "Complete the visit before generating a certificate")
    cert = await _generate_certificate(visit_id, user, auto_send=False)
    return {"success": True, "certificate": cert}


@router.get("/certificates/{cert_id}/download")
async def blue_light_certificate_download(cert_id: str, user=Depends(get_crm_user)):
    import base64
    from fastapi.responses import Response
    cert = await db.crm2_certificates.find_one({"id": cert_id, **_of(user)}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    f = await db.crm2_certificate_files.find_one({"cert_id": cert_id}, {"_id": 0, "pdf_b64": 1})
    if not f:
        raise HTTPException(404, "Certificate file not available")
    await record_audit(entity_type="certificate", entity_id=cert_id, action="download", user=user)
    return Response(content=base64.b64decode(f["pdf_b64"]), media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={cert.get('filename', 'certificate.pdf')}"})


@router.post("/certificates/{cert_id}/approve")
async def blue_light_certificate_approve(cert_id: str, data: dict = None, user=Depends(get_crm_user)):
    """Office/Manager review → approve + send (§31)."""
    cert = await db.crm2_certificates.find_one({"id": cert_id, **_of(user)}, {"_id": 0})
    if not cert:
        raise HTTPException(404, "Certificate not found")
    res = await _send_certificate(cert_id, user, (data or {}).get("recipients"))
    await record_audit(entity_type="certificate", entity_id=cert_id, action="approve_send",
                       user=user, after=res)
    return res


@router.post("/certificates/{cert_id}/send")
async def blue_light_certificate_send(cert_id: str, data: dict = None, user=Depends(get_crm_user)):
    return await _send_certificate(cert_id, user, (data or {}).get("recipients"))


@router.get("/contracts/{contract_id}/certificates")
async def blue_light_certificates(contract_id: str, status: str = "", user=Depends(get_crm_user)):
    """Central 82-station certificate dashboard feed (§33)."""
    await _get_bl_contract(contract_id, user)
    q = {"contract_id": contract_id}
    if status:
        q["status"] = status
    rows = await db.crm2_certificates.find(q, {"_id": 0}).sort("generated_at", -1).to_list(2000)
    counts = {}
    for r in rows:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
    return {"certificates": rows, "count": len(rows), "by_status": counts}


# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — ASSET REGISTER RECONCILIATION (§35/§36/§37)
# ════════════════════════════════════════════════════════════════════


async def _station_name_map(contract_id: str) -> dict:
    sites = await db.crm2_contract_sites.find(
        {"contract_id": contract_id}, {"_id": 0, "id": 1, "site_name": 1}).to_list(2000)
    return {s["id"]: s.get("site_name", "") for s in sites}


async def _reconciliation_items(contract_id: str) -> list[dict]:
    """Unified stream of asset changes from service visits: new / corrected /
    not-found. Each item carries old/new + who/where/when (§36) + review state."""
    names = await _station_name_map(contract_id)
    items = []
    # NEW assets discovered on a visit
    async for a in db.crm2_contract_assets.find(
            {"contract_id": contract_id, "discovered_on_visit": {"$exists": True, "$ne": None}}, {"_id": 0}):
        items.append({
            "id": f"new:{a['id']}", "kind": "new", "asset_id": a["id"],
            "site_id": a.get("site_id"), "station_name": names.get(a.get("site_id"), ""),
            "asset_name": a.get("asset_name"), "serial_number": a.get("serial_number"),
            "equipment_type": a.get("equipment_type"),
            "detail": f"New machine discovered: {a.get('asset_name')} ({a.get('serial_number') or 'no serial'})",
            "visit_id": a.get("discovered_on_visit"), "at": a.get("created_at"),
            "review_status": "pending" if a.get("office_review") else "approved",
        })
    # CORRECTIONS (field changes)
    async for ch in db.crm2_asset_changes.find({"contract_id": contract_id}, {"_id": 0}):
        fc = ch.get("field_changes") or {}
        summary = "; ".join(f"{k}: '{v.get('old') or '—'}' → '{v.get('new')}'" for k, v in fc.items())
        items.append({
            "id": f"corr:{ch['id']}", "kind": "correction", "asset_id": ch.get("asset_id"),
            "site_id": ch.get("site_id"), "station_name": names.get(ch.get("site_id"), ""),
            "field_changes": fc, "detail": summary,
            "engineer_name": ch.get("engineer_name"), "visit_id": ch.get("visit_id"),
            "at": ch.get("at"),
            "review_status": ch.get("review_status", "auto_approved"),
        })
    # NOT FOUND / removed
    async for v in db.crm2_asset_verifications.find(
            {"contract_id": contract_id, "action": "not_found"}, {"_id": 0}):
        a = await db.crm2_contract_assets.find_one({"id": v.get("asset_key")}, {"_id": 0, "asset_name": 1, "serial_number": 1, "status": 1})
        items.append({
            "id": f"nf:{v['asset_key']}:{v['visit_id']}", "kind": "not_found",
            "asset_id": v.get("asset_key"), "site_id": v.get("site_id"),
            "station_name": names.get(v.get("site_id"), ""),
            "asset_name": (a or {}).get("asset_name", ""), "serial_number": (a or {}).get("serial_number", ""),
            "reason": v.get("reason"),
            "detail": f"Not found: {(a or {}).get('asset_name', 'asset')} — {v.get('reason') or 'no reason'}",
            "engineer_name": v.get("engineer_name"), "visit_id": v.get("visit_id"), "at": v.get("at"),
            "review_status": "removed" if (a or {}).get("status") == "removed" else "pending",
        })
    # TRANSFER requests (§37) — move an asset between stations
    async for tr in db.crm2_asset_transfers.find({"contract_id": contract_id}, {"_id": 0}):
        from_name = names.get(tr.get("from_site_id"), "")
        to_name = names.get(tr.get("to_site_id"), "")
        items.append({
            "id": f"xfer:{tr['id']}", "kind": "transfer", "asset_id": tr.get("asset_id"),
            "site_id": tr.get("to_site_id"), "station_name": to_name,
            "from_station": from_name, "to_station": to_name,
            "asset_name": tr.get("asset_name"), "serial_number": tr.get("serial_number"),
            "detail": (f"Transfer requested: {tr.get('asset_name')} "
                       f"({tr.get('serial_number') or 'no serial'}) from {from_name or '—'} → {to_name or '—'}"),
            "engineer_name": tr.get("engineer_name"), "visit_id": tr.get("visit_id"),
            "at": tr.get("at"), "review_status": tr.get("status", "pending"),
        })
    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return items


@router.get("/contracts/{contract_id}/asset-changes")
async def blue_light_asset_changes(contract_id: str, kind: str = "", status: str = "",
                                   user=Depends(get_crm_user)):
    """Central 'asset changes from service visits' review feed (§35)."""
    await _get_bl_contract(contract_id, user)
    items = await _reconciliation_items(contract_id)
    counts = {"new": 0, "correction": 0, "not_found": 0, "transfer": 0, "pending": 0}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
        if it["review_status"] == "pending":
            counts["pending"] += 1
    if kind:
        items = [i for i in items if i["kind"] == kind]
    if status:
        items = [i for i in items if i["review_status"] == status]
    return {"items": items, "count": len(items), "counts": counts}


async def _notify_transfer_approved(contract: dict, tr: dict, user: dict, names: dict) -> dict:
    """Best-effort office email when a transfer is approved. Never raises."""
    from utils.email import send_email
    cfg = contract.get("blue_light") or {}
    raw = cfg.get("office_notification_emails") or []
    if isinstance(raw, str):
        raw = [e.strip() for e in raw.replace(";", ",").split(",")]
    recipients = [e for e in raw if e and "@" in e]
    if not recipients:  # fallback to the approver
        approver = user.get("email")
        recipients = [approver] if approver and "@" in approver else []
    result = {"notified_ok": False, "notify_error": None,
              "notified_recipients": recipients, "notified_at": _now()}
    if not recipients:
        result["notify_error"] = "No office recipients and approver has no email"
        return result
    from_name = names.get(tr.get("from_site_id"), "—")
    to_name = names.get(tr.get("to_site_id"), "—")
    asset = tr.get("asset_name") or "Asset"
    serial = tr.get("serial_number") or "no serial"
    label = contract.get("contract_number") or contract.get("title") or contract.get("id", "")
    html = (
        "<p>An asset transfer has been <b>approved</b> and the register has been updated.</p>"
        "<table cellpadding='6' style='border-collapse:collapse;font-size:14px'>"
        f"<tr><td><b>Machine</b></td><td>{asset} ({serial})</td></tr>"
        f"<tr><td><b>From station</b></td><td>{from_name}</td></tr>"
        f"<tr><td><b>To station</b></td><td>{to_name}</td></tr>"
        f"<tr><td><b>Requested by</b></td><td>{tr.get('engineer_name') or '—'}</td></tr>"
        f"<tr><td><b>Approved by</b></td><td>{user.get('full_name') or user.get('email', '')}</td></tr>"
        f"<tr><td><b>Contract</b></td><td>{label}</td></tr>"
        "</table>"
        "<p>Both station records have been updated to reflect this move.</p>"
        "<p>Kind regards,<br/>Pulse Fitness Service Team</p>")
    try:
        await send_email(to=recipients[0], subject=f"Asset transfer approved — {asset} → {to_name}",
                         html=html, cc=recipients[1:] or None,
                         organization_id=contract.get("organization_id"), kind="blue_light_transfer")
        result["notified_ok"] = True
    except Exception as e:  # preview Resend key is a placeholder — record + surface
        result["notify_error"] = str(e)
    return result


@router.post("/contracts/{contract_id}/asset-changes/review")
async def blue_light_asset_change_review(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Approve or revert an asset change (§35/§36). Nothing is silently lost —
    reverts restore the previous value and are audit-logged."""
    contract = await _get_bl_contract(contract_id, user)
    item_id = (data.get("item_id") or "").strip()
    action = (data.get("action") or "").strip()  # approve | revert
    if action not in ("approve", "revert"):
        raise HTTPException(400, "action must be approve or revert")
    kind, _, rest = item_id.partition(":")
    now = _now()
    notify_result = None
    if kind == "new":
        asset_id = rest
        if action == "approve":
            await db.crm2_contract_assets.update_one(
                {"id": asset_id, "contract_id": contract_id},
                {"$set": {"office_review": False, "review_status": "approved", "updated_at": now}})
        else:  # revert = remove the erroneously-added asset
            await db.crm2_contract_assets.update_one(
                {"id": asset_id, "contract_id": contract_id},
                {"$set": {"status": "rejected", "office_review": False, "updated_at": now}})
    elif kind == "corr":
        change_id = rest
        ch = await db.crm2_asset_changes.find_one({"id": change_id, "contract_id": contract_id}, {"_id": 0})
        if not ch:
            raise HTTPException(404, "Change not found")
        if action == "approve":
            await db.crm2_asset_changes.update_one(
                {"id": change_id}, {"$set": {"review_status": "approved", "reviewed_by": user.get("id"), "reviewed_at": now}})
        else:  # revert asset fields to the recorded OLD values
            revert = {k: v.get("old") for k, v in (ch.get("field_changes") or {}).items()}
            await db.crm2_contract_assets.update_one(
                {"id": ch.get("asset_id")}, {"$set": {**revert, "updated_at": now}})
            await db.crm2_asset_changes.update_one(
                {"id": change_id}, {"$set": {"review_status": "reverted", "reviewed_by": user.get("id"), "reviewed_at": now}})
    elif kind == "nf":
        asset_id, _, _vid = rest.partition(":")
        if action == "approve":  # confirm removal
            await db.crm2_contract_assets.update_one(
                {"id": asset_id, "contract_id": contract_id},
                {"$set": {"status": "removed", "updated_at": now}})
        else:  # restore the asset to active
            await db.crm2_contract_assets.update_one(
                {"id": asset_id, "contract_id": contract_id},
                {"$set": {"status": "active", "updated_at": now}})
    elif kind == "xfer":
        tr = await db.crm2_asset_transfers.find_one({"id": rest, "contract_id": contract_id}, {"_id": 0})
        if not tr:
            raise HTTPException(404, "Transfer request not found")
        if action == "approve":  # move the asset to the requested station
            await db.crm2_contract_assets.update_one(
                {"id": tr.get("asset_id"), "contract_id": contract_id},
                {"$set": {"site_id": tr.get("to_site_id"), "status": "active",
                          "not_found_reason": "", "updated_at": now}})
            await db.crm2_asset_transfers.update_one(
                {"id": rest}, {"$set": {"status": "approved", "reviewed_by": user.get("id"),
                                        "reviewed_at": now}})
            # keep BOTH stations in sync + leave an audit trail on each
            names = await _station_name_map(contract_id)
            from_name = names.get(tr.get("from_site_id"), "—")
            to_name = names.get(tr.get("to_site_id"), "—")
            asset_label = f"{tr.get('asset_name')} ({tr.get('serial_number') or 'no serial'})"
            for sid in (tr.get("from_site_id"), tr.get("to_site_id")):
                if sid:
                    await db.crm2_contract_sites.update_one({"id": sid}, {"$set": {"updated_at": now}})
            if tr.get("from_site_id"):
                await record_audit(entity_type="contract_site", entity_id=tr["from_site_id"],
                                   action="update", user=user,
                                   summary=f"Machine transferred out: {asset_label} → {to_name}")
            if tr.get("to_site_id"):
                await record_audit(entity_type="contract_site", entity_id=tr["to_site_id"],
                                   action="update", user=user,
                                   summary=f"Machine transferred in: {asset_label} ← {from_name}")
            # notify the office (best-effort)
            notify_result = await _notify_transfer_approved(contract, tr, user, names)
            await db.crm2_asset_transfers.update_one(
                {"id": rest}, {"$set": {"notified_ok": notify_result["notified_ok"],
                                        "notify_error": notify_result["notify_error"],
                                        "notified_recipients": notify_result["notified_recipients"],
                                        "notified_at": notify_result["notified_at"]}})
        else:  # reject — leave the asset where it is
            await db.crm2_asset_transfers.update_one(
                {"id": rest}, {"$set": {"status": "rejected", "reviewed_by": user.get("id"),
                                        "reviewed_at": now}})
    else:
        raise HTTPException(400, "Unknown change type")
    await record_audit(entity_type="asset_reconciliation", entity_id=item_id, action=action, user=user)
    resp = {"success": True, "item_id": item_id, "action": action}
    if notify_result is not None:
        resp["notification"] = {"ok": notify_result["notified_ok"],
                                "recipients": notify_result["notified_recipients"],
                                "error": notify_result["notify_error"]}
    return resp



# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — CONTRACT ONBOARDING IMPORT (§51/§52)
# Bulk-import a contract's stations + assets from a spreadsheet with a
# validation summary + duplicate warnings BEFORE anything is created.
# ════════════════════════════════════════════════════════════════════

@router.get("/blue-light/import/template.csv")
async def blue_light_import_template(user=Depends(get_crm_user)):
    """Downloadable CSV template with the exact import columns + sample rows."""
    from fastapi.responses import Response
    from utils.blue_light_import import template_csv
    return Response(
        content=template_csv(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=blue-light-import-template.csv"})


async def _bl_import_validate(contract_id: str, rows: list) -> dict:
    """Annotate rows with duplicate/validity flags and build a summary.
    Mutates each row dict in place (adds is_treadmill/dup_*/station_exists/valid)."""
    existing_assets = await db.crm2_contract_assets.find(
        {"contract_id": contract_id},
        {"_id": 0, "serial_number": 1, "manufacturer": 1, "model_code": 1,
         "asset_number": 1, "equipment_type": 1, "site_id": 1}).to_list(200000)
    site_docs = await db.crm2_contract_sites.find(
        {"contract_id": contract_id}, {"_id": 0, "id": 1, "site_name": 1}).to_list(200000)
    existing_station_names = {(d.get("site_name") or "").strip().lower() for d in site_docs}
    site_name_by_id = {d.get("id"): (d.get("site_name") or "") for d in site_docs}

    def _soft_key(station, manufacturer, model, asset_number, equipment_type):
        return _norm_serial("|".join([(station or "").lower(), manufacturer or "",
                                       model or "", asset_number or "", equipment_type or ""]))

    existing_serials = set()
    existing_soft = set()   # soft key for assets with NO serial (re-import guard)
    for a in existing_assets:
        if a.get("serial_number"):
            existing_serials.add(_norm_serial(a.get("serial_number", "")))
        else:
            existing_soft.add(_soft_key(site_name_by_id.get(a.get("site_id"), ""),
                                        a.get("manufacturer"), a.get("model_code"),
                                        a.get("asset_number"), a.get("equipment_type")))

    seen, seen_soft, warnings, errors, stations = set(), set(), [], [], {}
    for r in rows:
        st = (r.get("station_name") or "").strip()
        r["is_treadmill"] = _is_treadmill({
            "equipment_type": r.get("equipment_type", ""),
            "model_code": r.get("model", ""),
            "asset_name": r.get("asset_name", "")})
        r["dup_in_file"] = r["dup_on_contract"] = r["station_exists"] = False
        r["valid"] = True
        if not st:
            r["valid"] = False
            errors.append({"row": r.get("source_row"), "sheet": r.get("source_sheet", ""),
                           "message": "No station / location for this row"})
            continue
        r["station_exists"] = st.lower() in existing_station_names
        can = _norm_serial(r.get("serial_number", "")) if r.get("serial_number") else ""
        if can:
            if can in seen:
                r["dup_in_file"] = True
            else:
                seen.add(can)
            if can in existing_serials:
                r["dup_on_contract"] = True
        else:
            # No serial — de-dupe on a soft key so re-imports don't recreate rows
            soft = _soft_key(st, r.get("manufacturer"), r.get("model"),
                             r.get("asset_number"), r.get("equipment_type"))
            if soft in seen_soft:
                r["dup_in_file"] = True
            else:
                seen_soft.add(soft)
            if soft in existing_soft:
                r["dup_on_contract"] = True
        if r["dup_in_file"]:
            warnings.append({"row": r.get("source_row"), "type": "duplicate_in_file",
                             "serial": r.get("serial_number"), "station": st,
                             "message": (f"Serial {r.get('serial_number')} appears more than once in the file"
                                         if can else f"{r.get('asset_name')} (no serial) appears more than once in the file")})
        if r["dup_on_contract"]:
            warnings.append({"row": r.get("source_row"), "type": "duplicate_on_contract",
                             "serial": r.get("serial_number"), "station": st,
                             "message": (f"Serial {r.get('serial_number')} already exists on this contract"
                                         if can else f"{r.get('asset_name')} (no serial) already looks present on this contract")})
        if not can and not r["dup_in_file"] and not r["dup_on_contract"]:
            warnings.append({"row": r.get("source_row"), "type": "missing_serial", "station": st,
                             "message": f"{r.get('asset_name')} has no serial number"})
        grp = stations.setdefault(st, {"name": st, "exists": r["station_exists"],
                                       "asset_count": 0, "treadmill_count": 0})
        grp["asset_count"] += 1
        if r["is_treadmill"]:
            grp["treadmill_count"] += 1

    station_list = list(stations.values())
    valid_rows = [r for r in rows if r.get("valid")]
    counts = {
        "rows_total": len(rows),
        "assets_valid": len(valid_rows),
        "assets_duplicate": sum(1 for r in valid_rows if r["dup_in_file"] or r["dup_on_contract"]),
        "assets_blank_serial": sum(1 for r in valid_rows if not r.get("serial_number")),
        "treadmills": sum(1 for r in valid_rows if r["is_treadmill"]),
        "stations_total": len(station_list),
        "stations_new": sum(1 for s in station_list if not s["exists"]),
        "stations_existing": sum(1 for s in station_list if s["exists"]),
    }
    return {"counts": counts, "stations": station_list, "warnings": warnings, "errors": errors}


@router.post("/contracts/{contract_id}/blue-light/import/preview")
async def blue_light_import_preview(
    contract_id: str,
    file: UploadFile = File(None),
    text: str = Form(None),
    default_station: str = Form(""),
    mapping: str = Form(None),
    user=Depends(get_crm_user),
):
    """Parse a spreadsheet/CSV/paste and return a validation summary WITHOUT
    creating anything. Returns per-row flags + the detected column mapping so the
    operator can review dupes and adjust/remember the layout."""
    import json as _json
    from utils.blue_light_import import parse_import
    await _get_bl_contract(contract_id, user)
    if not file and not text:
        raise HTTPException(400, "Provide a file upload or pasted text")
    column_map = None
    if mapping:
        try:
            column_map = _json.loads(mapping)
        except ValueError:
            raise HTTPException(400, "Invalid column mapping")
    content = await file.read() if file else None
    fname = file.filename if file else None

    def _parse(cmap):
        return parse_import(content=content, filename=fname, text=text,
                            default_station=default_station or "", column_map=cmap)
    try:
        rows, meta = _parse(column_map)
        saved = None
        if not column_map:  # auto-apply a remembered layout for this header set
            doc = await db.crm2_import_mappings.find_one(
                {"organization_id": user.get("organization_id"), "signature": meta["signature"]},
                {"_id": 0})
            if doc:
                rows, meta = _parse(doc.get("columns") or {})
                saved = {"id": doc["id"], "name": doc["name"]}
                await db.crm2_import_mappings.update_one(
                    {"id": doc["id"]},
                    {"$set": {"last_used_at": _now()}, "$inc": {"use_count": 1}})
        meta["saved"] = saved
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — surface parse errors to the operator
        raise HTTPException(400, f"Could not read the spreadsheet: {e}")

    if not rows:
        # Columns were found but nothing mapped yet — let the operator map them.
        if meta.get("columns"):
            empty = {"counts": {"rows_total": 0, "assets_valid": 0, "assets_duplicate": 0,
                                "assets_blank_serial": 0, "treadmills": 0, "stations_total": 0,
                                "stations_new": 0, "stations_existing": 0},
                     "stations": [], "warnings": [], "errors": []}
            return {**empty, "rows": [], "meta": meta}
        raise HTTPException(400, "No data rows found in the file")
    summary = await _bl_import_validate(contract_id, rows)
    return {**summary, "rows": rows, "meta": meta}


@router.get("/blue-light/import/mappings")
async def blue_light_import_mappings_list(user=Depends(get_crm_user)):
    """Saved column layouts for this organisation (shared across the team)."""
    docs = await db.crm2_import_mappings.find(
        {"organization_id": user.get("organization_id")},
        {"_id": 0}).sort("last_used_at", -1).to_list(200)
    return {"mappings": docs}


@router.post("/blue-light/import/mappings")
async def blue_light_import_mappings_save(data: dict, user=Depends(get_crm_user)):
    """Create/update a remembered layout, keyed by the header signature."""
    name = (data.get("name") or "").strip()
    sig = (data.get("signature") or "").strip()
    columns = data.get("columns") or {}
    if not name:
        raise HTTPException(400, "Give the layout a name")
    if not sig:
        raise HTTPException(400, "Missing layout signature")
    org, now = user.get("organization_id"), _now()
    existing = await db.crm2_import_mappings.find_one(
        {"organization_id": org, "signature": sig}, {"_id": 0, "id": 1, "use_count": 1})
    doc = {
        "id": existing["id"] if existing else _id(),
        "organization_id": org, "name": name, "signature": sig,
        "columns": columns, "updated_at": now,
        "created_at": now if not existing else None,
        "last_used_at": now, "use_count": (existing or {}).get("use_count", 0),
    }
    doc = {k: v for k, v in doc.items() if v is not None}
    await db.crm2_import_mappings.update_one(
        {"id": doc["id"]}, {"$set": doc}, upsert=True)
    return {"success": True, "id": doc["id"], "name": name}


@router.delete("/blue-light/import/mappings/{mapping_id}")
async def blue_light_import_mappings_delete(mapping_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_import_mappings.delete_one(
        {"id": mapping_id, "organization_id": user.get("organization_id")})
    if not r.deleted_count:
        raise HTTPException(404, "Saved layout not found")
    return {"success": True}



@router.post("/contracts/{contract_id}/blue-light/import/commit")
async def blue_light_import_commit(contract_id: str, data: dict, user=Depends(get_crm_user)):
    """Create stations (deduped by name) + assets from reviewed import rows.
    Skips duplicate serials when skip_duplicates is true (default)."""
    await _get_bl_contract(contract_id, user)
    rows = data.get("rows") or []
    if not rows:
        raise HTTPException(400, "No rows to import")
    skip_duplicates = data.get("skip_duplicates", True)
    summary = await _bl_import_validate(contract_id, rows)  # recompute flags fresh
    org, now = user.get("organization_id"), _now()

    site_docs = await db.crm2_contract_sites.find(
        {"contract_id": contract_id}, {"_id": 0, "id": 1, "site_name": 1}).to_list(200000)
    site_map = {(d.get("site_name") or "").strip().lower(): d["id"] for d in site_docs}

    new_sites, stations_created = [], 0
    for s in summary["stations"]:
        key = s["name"].strip().lower()
        if key and key not in site_map:
            sid = _id()
            new_sites.append({
                "id": sid, "contract_id": contract_id, "organization_id": org,
                "site_name": s["name"], "address": "", "city": "", "postcode": "",
                "visit_status": "not_planned", "next_service_due": "", "scheduled_date": "",
                "last_service": "", "follow_up_required": False,
                "source": "onboarding_import", "created_at": now})
            site_map[key] = sid
            stations_created += 1
    if new_sites:
        await db.crm2_contract_sites.insert_many(new_sites)

    assets, skipped = [], 0
    for r in rows:
        if not r.get("valid", True):
            continue
        if skip_duplicates and (r.get("dup_in_file") or r.get("dup_on_contract")):
            skipped += 1
            continue
        sid = site_map.get((r.get("station_name") or "").strip().lower(), "")
        assets.append({
            "id": _id(), "contract_id": contract_id, "organization_id": org,
            "site_id": sid, "asset_id": "",
            "asset_name": r.get("asset_name", ""), "equipment_type": r.get("equipment_type", ""),
            "model_code": r.get("model", ""), "manufacturer": r.get("manufacturer", ""),
            "serial_number": r.get("serial_number", ""), "asset_number": r.get("asset_number", ""),
            "mod_code": r.get("mod_code", ""), "sub_location": r.get("sub_location", ""),
            "warranty_end": r.get("warranty_end", ""), "coverage_type": "full",
            "notes": r.get("notes", ""), "source": "onboarding_import", "created_at": now})
    if assets:
        await db.crm2_contract_assets.insert_many(assets)

    result = {
        "success": True,
        "stations_created": stations_created,
        "stations_matched": summary["counts"]["stations_existing"],
        "assets_created": len(assets),
        "assets_skipped": skipped,
        "treadmills": sum(1 for a in assets if _is_treadmill(a)),
    }
    await record_audit(entity_type="contract", entity_id=contract_id,
                       action="blue_light_import", user=user, after=result)
    return result


# ════════════════════════════════════════════════════════════════════
# BLUE LIGHT — CERTIFICATE LOGO (swappable customer crest per contract)
# ════════════════════════════════════════════════════════════════════

@router.post("/contracts/{contract_id}/blue-light/logo")
async def blue_light_upload_logo(contract_id: str, file: UploadFile = File(...),
                                 user=Depends(get_crm_user)):
    """Upload a customer logo/crest (PNG/JPG) shown on this contract's
    certificates. Stored securely in object storage; everything else on the
    certificate stays the same."""
    import io as _io
    import base64 as _b64
    from PIL import Image as _PILImage
    from utils.database import APP_NAME as _APP, put_object
    contract = await _get_bl_contract(contract_id, user)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Logo must be 8 MB or smaller")
    try:
        img = _PILImage.open(_io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(400, "Could not parse image — please use PNG or JPG")
    is_png = (img.format or "").upper() == "PNG"
    img.thumbnail((512, 512), _PILImage.LANCZOS)
    out = _io.BytesIO()
    if is_png:
        img.save(out, format="PNG", optimize=True)
        content_type, ext = "image/png", "png"
    else:
        img = img.convert("RGB")
        img.save(out, format="JPEG", quality=88, optimize=True)
        content_type, ext = "image/jpeg", "jpg"
    compressed = out.getvalue()
    path = f"{_APP}/bl_certificate_logos/{contract_id}/{_id()}.{ext}"
    cfg = contract.get("blue_light") or {}
    try:
        put_object(path, compressed, content_type)
        cfg["customer_logo_path"] = path
        cfg["customer_logo_content_type"] = content_type
        cfg["customer_logo_url"] = f"/api/crm/v2/contracts/{contract_id}/blue-light/logo?v={_id()[:8]}"
    except Exception as exc:  # object store unavailable — inline as data URL
        cfg["customer_logo_path"] = None
        cfg["customer_logo_url"] = f"data:{content_type};base64," + _b64.b64encode(compressed).decode("ascii")
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"blue_light": cfg}})
    await record_audit(entity_type="contract", entity_id=contract_id,
                       action="blue_light_logo_upload", user=user)
    return {"success": True, "customer_logo_url": cfg["customer_logo_url"]}


@router.get("/contracts/{contract_id}/blue-light/logo")
async def blue_light_serve_logo(contract_id: str):
    """Public proxy for the certificate logo (used by the settings preview)."""
    from fastapi.responses import Response
    from utils.database import get_object
    contract = await db.crm2_contracts.find_one(
        {"id": contract_id}, {"_id": 0, "blue_light": 1})
    cfg = (contract or {}).get("blue_light") or {}
    path = cfg.get("customer_logo_path")
    if not path:
        raise HTTPException(404, "No logo")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        raise HTTPException(404, "Logo not available") from exc
    return Response(content=data,
                    media_type=cfg.get("customer_logo_content_type") or content_type or "image/png",
                    headers={"Cache-Control": "public, max-age=600"})


@router.delete("/contracts/{contract_id}/blue-light/logo")
async def blue_light_delete_logo(contract_id: str, user=Depends(get_crm_user)):
    contract = await _get_bl_contract(contract_id, user)
    cfg = contract.get("blue_light") or {}
    cfg["customer_logo_path"] = None
    cfg["customer_logo_url"] = None
    cfg["customer_logo_content_type"] = None
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": {"blue_light": cfg}})
    return {"success": True}
