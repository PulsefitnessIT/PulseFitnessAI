"""
CRM v2 — Core Data Model & Activity Engine
All CRM entities with full cross-linking and org-scoped queries.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
from pydantic import BaseModel
from utils.database import db
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit
from routes.crm_permissions import compute_visibility, redact
import uuid
import re
import json

router = APIRouter(prefix="/crm/v2", tags=["CRM v2"])


def _of(user: dict) -> dict:
    """Org-scoped filter. Returns impossible match if no org."""
    org_id = user.get("organization_id")
    return {"organization_id": org_id} if org_id else {"organization_id": "__NONE__"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


# ═══════════════════════════════════════════
# ACTIVITIES — The unified timeline engine
# ═══════════════════════════════════════════

def _build_activity_filter(user: dict, **kwargs) -> dict:
    """Build a MongoDB query from activity filter parameters."""
    q = {**_of(user)}
    filter_fields = ("company_id", "contact_id", "opportunity_id", "case_id", "asset_id", "type")
    for field in filter_fields:
        val = kwargs.get(field, "")
        if val:
            q[field] = val
    return q


class ActivityFilters(BaseModel):
    """Grouped query-string filters for `GET /activities`. Bound via FastAPI Depends."""
    company_id: str = ""
    contact_id: str = ""
    opportunity_id: str = ""
    case_id: str = ""
    asset_id: str = ""
    type: str = ""


@router.get("/activities")
async def list_activities(
    filters: ActivityFilters = Depends(),
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_crm_user),
):
    """List activities filtered by any linked entity."""
    q = _build_activity_filter(user, **filters.dict())
    total = await db.crm2_activities.count_documents(q)
    items = await db.crm2_activities.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"activities": items, "total": total}


@router.post("/activities")
async def create_activity(data: dict, user=Depends(get_crm_user)):
    """Create an activity linked to any entity."""
    activity = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": data.get("type", "note"),  # note, call, email, meeting, task, visit
        "subject": data.get("subject", ""),
        "body": data.get("body", ""),
        "company_id": data.get("company_id"),
        "contact_id": data.get("contact_id"),
        "opportunity_id": data.get("opportunity_id"),
        "case_id": data.get("case_id"),
        "asset_id": data.get("asset_id"),
        "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""),
        "due_date": data.get("due_date"),
        "completed_at": data.get("completed_at"),
        "priority": data.get("priority", "normal"),
        "metadata": data.get("metadata", {}),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_activities.insert_one(activity)
    return {k: v for k, v in activity.items() if k != "_id"}


@router.put("/activities/{activity_id}")
async def update_activity(activity_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_activities.find_one({"id": activity_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Activity not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    updates["updated_at"] = _now()
    await db.crm2_activities.update_one({"id": activity_id}, {"$set": updates})
    return {"success": True}


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_activities.delete_one({"id": activity_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Activity not found")
    return {"success": True}


# ═══════════════════════════════════════════
# COMPANIES — The master commercial record
# ═══════════════════════════════════════════

@router.get("/companies")
async def list_companies(
    search: str = "", sector: str = "", status: str = "", type: str = "",
    scope: str = "", territory_id: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = await compute_visibility(user, "company")
    if search:
        q["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"sector": {"$regex": search, "$options": "i"}},
        ]
    if sector:
        q["sector"] = sector
    # Iter 215bi — canonical classification field is `type` (prospect /
    # customer / partner / former). Frontend used to send the value as
    # `status` which silently matched nothing and caused the customer
    # filter to look broken. Accept either alias for backwards-compat.
    type_value = type or status
    if type_value:
        q["type"] = type_value
    if territory_id:
        q["territory_id"] = territory_id
    if scope == "mine":
        q["owner_id"] = user.get("id")
    elif scope == "team":
        from routes.crm_territories import collect_team_ids
        ids = await collect_team_ids(user.get("id"), user.get("organization_id"))
        q["owner_id"] = {"$in": ids}
    total = await db.crm2_companies.count_documents(q)
    items = await db.crm2_companies.find(q, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)

    # Enrich with counts
    for c in items:
        cid = c["id"]
        c["contact_count"] = await db.crm2_contacts.count_documents({"company_id": cid, **_of(user)})
        c["opportunity_count"] = await db.crm2_opportunities.count_documents({"company_id": cid, **_of(user)})
        c["open_cases"] = await db.crm2_cases.count_documents({"company_id": cid, "status": {"$nin": ["closed", "resolved"]}, **_of(user)})
        c["asset_count"] = await db.crm2_assets.count_documents({"company_id": cid, **_of(user)})

    items = await redact(user, "company", items)
    return {"companies": items, "total": total}


@router.post("/companies")
async def create_company(data: dict, user=Depends(get_crm_user)):
    company = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "name": data.get("name", ""), "sector": data.get("sector", ""),
        "type": data.get("type", "prospect"),  # prospect, customer, partner, former
        "parent_id": data.get("parent_id"),
        "website": data.get("website", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "address": data.get("address", ""),
        # Iter 215eq — structured 8-field address. Backwards-compatible
        # with the legacy single-line `address`.
        "address_line1": data.get("address_line1", "") or data.get("address", ""),
        "address_line2": data.get("address_line2", ""),
        "address_line3": data.get("address_line3", ""),
        "city": data.get("city", ""), "postcode": data.get("postcode", ""),
        "county": data.get("county", ""),
        "country": data.get("country", "United Kingdom"),
        "company_number": data.get("company_number", ""),
        "description": data.get("description", ""),
        "directors": data.get("directors", []),
        "account_owner_id": data.get("account_owner_id") or user.get("id"),
        "account_owner_name": data.get("account_owner_name") or user.get("full_name", ""),
        "sla_tier": data.get("sla_tier", "standard"),
        "revenue_band": data.get("revenue_band", ""),
        "status": "active",
        "tags": data.get("tags", []),
        "notes": data.get("notes", ""),
        # Iter 215dc — enterprise territory & ownership.
        "territory_id": data.get("territory_id") or None,
        "owner_id": data.get("owner_id") or user.get("id"),
        "owner_name": data.get("owner_name") or user.get("full_name", ""),
        "region": data.get("region", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    # Iter 215dc — territory-based auto-assignment. Only applied when
    # the caller didn't pass an explicit owner/territory.
    if not data.get("territory_id") and not data.get("owner_id"):
        try:
            from routes.crm_territories import assign_from_territory
            assignment = await assign_from_territory(company, user.get("organization_id"))
            if assignment:
                company["territory_id"] = assignment.get("territory_id")
                if assignment.get("owner_id"):
                    company["owner_id"] = assignment["owner_id"]
                    company["owner_name"] = assignment.get("owner_name", "")
                    # Keep account_owner aligned with territory assignment.
                    company["account_owner_id"] = assignment["owner_id"]
                    company["account_owner_name"] = assignment.get("owner_name", "")
        except Exception:
            pass  # never block company creation on territory logic
    await db.crm2_companies.insert_one(company)
    await record_audit(entity_type="company", entity_id=company["id"], action="create", user=user, after=company)
    # Auto-create activity
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": "Company created",
        "body": f"{user.get('full_name', '')} created company {company['name']}",
        "company_id": company["id"], "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""), "created_at": _now(), "updated_at": _now(),
    })
    await evaluate_workflows("company_created", company, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in company.items() if k != "_id"}


@router.get("/companies/{company_id}")
async def get_company(company_id: str, user=Depends(get_crm_user)):
    c = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Company not found")
    # Enrich with linked data
    of = _of(user)
    c["contacts"] = await db.crm2_contacts.find({"company_id": company_id, **of}, {"_id": 0}).to_list(100)
    c["opportunities"] = await db.crm2_opportunities.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["quotes"] = await db.crm2_quotes.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["cases"] = await db.crm2_cases.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["assets"] = await db.crm2_assets.find({"company_id": company_id, **of}, {"_id": 0}).to_list(100)
    c["contracts"] = await db.crm2_contracts.find({"company_id": company_id, **of}, {"_id": 0}).to_list(50)
    c["activities"] = await db.crm2_activities.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    # Revenue summary
    won_opps = await db.crm2_opportunities.find({"company_id": company_id, "stage": "closed_won", **of}, {"_id": 0, "value": 1}).to_list(500)
    c["total_revenue"] = sum(o.get("value", 0) for o in won_opps)
    c["open_pipeline"] = sum(o.get("value", 0) for o in c["opportunities"] if o.get("stage") not in ("closed_won", "closed_lost"))
    return c


@router.put("/companies/{company_id}")
async def update_company(company_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_companies.find_one({"id": company_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Company not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    updates["updated_at"] = _now()
    await db.crm2_companies.update_one({"id": company_id}, {"$set": updates})
    after = {**existing, **updates}
    await record_audit(entity_type="company", entity_id=company_id, action="update", user=user, before=existing, after=after)
    return {"success": True}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, user=Depends(get_crm_user)):
    existing = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    r = await db.crm2_companies.delete_one({"id": company_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Company not found")
    await record_audit(entity_type="company", entity_id=company_id, action="delete", user=user, before=existing)
    return {"success": True}


# ═══════════════════════════════════════════
# CONTACTS — Full contact intelligence
# ═══════════════════════════════════════════

@router.get("/contacts")
async def list_contacts(
    search: str = "", company_id: str = "", tag: str = "",
    decision_maker: str = "", scope: str = "", territory_id: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = await compute_visibility(user, "contact")
    if search:
        q["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    if company_id:
        q["company_id"] = company_id
    if tag:
        q["tags"] = tag
    if decision_maker == "true":
        q["is_decision_maker"] = True
    if territory_id:
        q["territory_id"] = territory_id
    if scope == "mine":
        q["owner_id"] = user.get("id")
    elif scope == "team":
        from routes.crm_territories import collect_team_ids
        ids = await collect_team_ids(user.get("id"), user.get("organization_id"))
        q["owner_id"] = {"$in": ids}
    total = await db.crm2_contacts.count_documents(q)
    items = await db.crm2_contacts.find(q, {"_id": 0}).sort("last_name", 1).skip(skip).limit(limit).to_list(limit)
    items = await redact(user, "contact", items)
    return {"contacts": items, "total": total}


@router.post("/contacts")
async def create_contact(data: dict, user=Depends(get_crm_user)):
    contact = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "mobile": data.get("mobile", ""),
        "job_title": data.get("job_title", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        "is_decision_maker": data.get("is_decision_maker", False),
        "is_champion": data.get("is_champion", False),
        "linkedin": data.get("linkedin", ""),
        "source": data.get("source", "manual"),
        "status": data.get("status", "active"),
        "tags": data.get("tags", []),
        "lifecycle": data.get("lifecycle", "lead"),
        "gdpr_consent": data.get("gdpr_consent", False),
        "gdpr_consent_date": data.get("gdpr_consent_date"),
        "communication_preferences": data.get("communication_preferences", {}),
        # Per-channel GDPR opt-outs (UK GDPR Article 21). Stored as
        # explicit booleans so the marketing engine can hard-skip
        # opted-out contacts without ambiguity. Default = opted in
        # ONLY when gdpr_consent is true; otherwise default = opted
        # out for all channels (safer).
        "opt_out_email":     data.get("opt_out_email",     not data.get("gdpr_consent", False)),
        "opt_out_sms":       data.get("opt_out_sms",       not data.get("gdpr_consent", False)),
        "opt_out_phone":     data.get("opt_out_phone",     not data.get("gdpr_consent", False)),
        "opt_out_post":      data.get("opt_out_post",      not data.get("gdpr_consent", False)),
        "opt_out_marketing": data.get("opt_out_marketing", not data.get("gdpr_consent", False)),
        "opt_out_updated_at": _now(),
        "relationship_score": 0,
        "owner_id": data.get("owner_id") or user.get("id"),
        "owner_name": data.get("owner_name") or user.get("full_name", ""),
        "notes": data.get("notes", ""),
        # Iter 215dc — enterprise territory attribution for contacts.
        "territory_id": data.get("territory_id") or None,
        "postcode": data.get("postcode", ""),
        "county": data.get("county", ""),
        "region": data.get("region", ""),
        "country": data.get("country", "UK"),
        "created_at": _now(), "updated_at": _now(),
    }
    # Territory auto-assignment — inherit from the linked company first
    # (all employees in the same company belong in the same territory)
    # then fall back to geo criteria on the contact itself.
    if not data.get("territory_id") and not data.get("owner_id"):
        try:
            from routes.crm_territories import assign_from_territory
            assignment = {}
            if contact.get("company_id"):
                parent = await db.crm2_companies.find_one(
                    {"id": contact["company_id"]}, {"_id": 0, "territory_id": 1, "owner_id": 1, "owner_name": 1},
                )
                if parent and parent.get("territory_id"):
                    assignment = {
                        "territory_id": parent["territory_id"],
                        "owner_id": parent.get("owner_id"),
                        "owner_name": parent.get("owner_name", ""),
                    }
            if not assignment:
                assignment = await assign_from_territory(contact, user.get("organization_id"))
            if assignment:
                contact["territory_id"] = assignment.get("territory_id")
                if assignment.get("owner_id"):
                    contact["owner_id"] = assignment["owner_id"]
                    contact["owner_name"] = assignment.get("owner_name", "")
        except Exception:
            pass
    await db.crm2_contacts.insert_one(contact)
    await record_audit(entity_type="contact", entity_id=contact["id"], action="create", user=user, after=contact)
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": "Contact created",
        "body": f"{user.get('full_name', '')} created contact {contact['first_name']} {contact['last_name']}",
        "contact_id": contact["id"], "company_id": contact.get("company_id"),
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    })
    await evaluate_workflows("contact_created", contact, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in contact.items() if k != "_id"}


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, user=Depends(get_crm_user)):
    c = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contact not found")
    of = _of(user)
    c["activities"] = await db.crm2_activities.find({"contact_id": contact_id, **of}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    c["opportunities"] = await db.crm2_opportunities.find({"contact_id": contact_id, **of}, {"_id": 0}).to_list(50)
    c["cases"] = await db.crm2_cases.find({"contact_id": contact_id, **of}, {"_id": 0}).to_list(50)
    if c.get("company_id"):
        company = await db.crm2_companies.find_one({"id": c["company_id"], **of}, {"_id": 0, "name": 1, "sector": 1, "type": 1})
        c["company"] = company
    return c


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Contact not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    updates["updated_at"] = _now()
    await db.crm2_contacts.update_one({"id": contact_id}, {"$set": updates})
    after = {**existing, **updates}
    await record_audit(entity_type="contact", entity_id=contact_id, action="update", user=user, before=existing, after=after)
    return {"success": True}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user=Depends(get_crm_user)):
    existing = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)}, {"_id": 0})
    r = await db.crm2_contacts.delete_one({"id": contact_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Contact not found")
    await record_audit(entity_type="contact", entity_id=contact_id, action="delete", user=user, before=existing)
    return {"success": True}


# ═══════════════════════════════════════════
# LEAD CONVERSION — Iter 216h66
# Salesforce-style "Convert Lead" — link/create a Company,
# optionally create an Opportunity, and bump the contact's
# lifecycle from 'lead' to 'customer' (or operator override).
# ═══════════════════════════════════════════

@router.post("/contacts/{contact_id}/convert")
async def convert_lead(contact_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Contact not found")
    if existing.get("lifecycle") != "lead":
        raise HTTPException(
            400,
            f"Cannot convert — contact lifecycle is already '{existing.get('lifecycle', 'unknown')}'. "
            "Only leads can be converted.",
        )

    org_id = user.get("organization_id")
    of = _of(user)
    new_lifecycle = (data.get("new_lifecycle") or "customer").strip()
    if new_lifecycle not in ("customer", "prospect", "champion"):
        new_lifecycle = "customer"

    # ─── 1. Resolve company ──────────────────────────────────────
    company_action = (data.get("company_action") or "skip").strip()
    company_id = data.get("company_id") or existing.get("company_id") or None
    company_name = existing.get("company_name", "")

    if company_action == "link":
        if not company_id:
            raise HTTPException(400, "company_action='link' requires a company_id")
        co = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0, "name": 1})
        if not co:
            raise HTTPException(404, "Linked company not found")
        company_name = co.get("name", "")

    elif company_action == "create":
        cd = data.get("company_data") or {}
        if not (cd.get("name") or "").strip():
            raise HTTPException(400, "company_action='create' requires company_data.name")
        company = {
            "id": _id(), "organization_id": org_id,
            "name": cd.get("name", "").strip(),
            "sector": cd.get("sector", ""),
            "type": "customer",  # converted lead → customer account by default
            "website": cd.get("website", ""),
            "phone": cd.get("phone", "") or existing.get("phone", ""),
            "email": cd.get("email", "") or existing.get("email", ""),
            "address": "",
            "address_line1": "", "address_line2": "", "address_line3": "",
            "city": "", "postcode": "", "county": "",
            "country": cd.get("country", "United Kingdom"),
            "company_number": cd.get("company_number", ""),
            "description": "",
            "directors": [],
            "account_owner_id": user.get("id"),
            "account_owner_name": user.get("full_name", ""),
            "sla_tier": "standard",
            "revenue_band": "",
            "status": "active",
            "tags": [],
            "notes": "",
            "territory_id": None,
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "region": "",
            "created_at": _now(), "updated_at": _now(),
        }
        # Reuse the territory auto-assignment used in create_company().
        try:
            from routes.crm_territories import assign_from_territory
            assignment = await assign_from_territory(company, org_id)
            if assignment:
                company["territory_id"] = assignment.get("territory_id")
                if assignment.get("owner_id"):
                    company["owner_id"] = assignment["owner_id"]
                    company["owner_name"] = assignment.get("owner_name", "")
                    company["account_owner_id"] = assignment["owner_id"]
                    company["account_owner_name"] = assignment.get("owner_name", "")
        except Exception:
            pass
        await db.crm2_companies.insert_one(company)
        await record_audit(entity_type="company", entity_id=company["id"], action="create", user=user, after=company)
        await db.crm2_activities.insert_one({
            "id": _id(), "organization_id": org_id,
            "type": "system", "subject": "Company created (lead conversion)",
            "body": f"{user.get('full_name', '')} created {company['name']} during lead conversion of {existing.get('first_name', '')} {existing.get('last_name', '')}",
            "company_id": company["id"], "contact_id": contact_id,
            "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
            "created_at": _now(), "updated_at": _now(),
        })
        try:
            await evaluate_workflows("company_created", company, org_id, user.get("full_name", ""))
        except Exception:
            pass
        company_id = company["id"]
        company_name = company["name"]
    # company_action == 'skip' (default) — keep existing company link if any.

    # ─── 2. Optionally create the opportunity ────────────────────
    opportunity_id = None
    if data.get("create_opportunity"):
        op = data.get("opportunity") or {}
        title = (op.get("title") or "").strip()
        if not title:
            raise HTTPException(400, "opportunity.title is required when create_opportunity=true")
        stage = op.get("stage") or "qualified"
        stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == stage), None)
        if not stage_info:
            raise HTTPException(400, f"Unknown stage '{stage}'")
        value = float(op.get("value") or 0)
        opp = {
            "id": _id(), "organization_id": org_id,
            "title": title,
            "company_id": company_id,
            "company_name": company_name,
            "contact_id": contact_id,
            "contact_name": f"{existing.get('first_name', '')} {existing.get('last_name', '')}".strip(),
            "stage": stage,
            "value": value,
            "probability": stage_info["probability"],
            "weighted_value": value * stage_info["probability"] / 100,
            "close_date": op.get("close_date", ""),
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "source": op.get("source", "lead_conversion"),
            "competitor": "",
            "risk_factors": [],
            "next_step": op.get("next_step", ""),
            "tags": [],
            "stage_entered_at": _now(),
            "stage_history": [{"stage": stage, "entered_at": _now(), "by": user.get("full_name", "")}],
            "territory_id": None,
            "created_at": _now(), "updated_at": _now(),
        }
        # Inherit territory & owner from the linked company when present.
        if company_id:
            try:
                parent = await db.crm2_companies.find_one(
                    {"id": company_id}, {"_id": 0, "territory_id": 1, "owner_id": 1, "owner_name": 1},
                )
                if parent and parent.get("territory_id"):
                    opp["territory_id"] = parent["territory_id"]
                    if parent.get("owner_id"):
                        opp["owner_id"] = parent["owner_id"]
                        opp["owner_name"] = parent.get("owner_name", "")
            except Exception:
                pass
        await db.crm2_opportunities.insert_one(opp)
        await record_audit(entity_type="opportunity", entity_id=opp["id"], action="create", user=user, after=opp)
        await db.crm2_activities.insert_one({
            "id": _id(), "organization_id": org_id,
            "type": "system", "subject": f"Opportunity created from lead conversion: {opp['title']}",
            "body": f"£{opp['value']:,.0f} | Stage: {stage_info['name']}",
            "company_id": company_id, "contact_id": contact_id, "opportunity_id": opp["id"],
            "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
            "created_at": _now(), "updated_at": _now(),
        })
        try:
            await evaluate_workflows("deal_created", opp, org_id, user.get("full_name", ""))
            if value > 0:
                await evaluate_workflows("deal_value_above", opp, org_id, user.get("full_name", ""))
        except Exception:
            pass
        opportunity_id = opp["id"]

    # ─── 3. Update the contact lifecycle + company link ──────────
    updates = {
        "lifecycle": new_lifecycle,
        "converted_at": _now(),
        "converted_by": user.get("full_name", ""),
        "updated_at": _now(),
    }
    if company_id:
        updates["company_id"] = company_id
        updates["company_name"] = company_name
    await db.crm2_contacts.update_one({"id": contact_id}, {"$set": updates})
    after_contact = {**{k: v for k, v in existing.items() if k != "_id"}, **updates}
    await record_audit(
        entity_type="contact", entity_id=contact_id, action="convert",
        user=user, before={k: v for k, v in existing.items() if k != "_id"}, after=after_contact,
    )
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": org_id,
        "type": "system",
        "subject": f"Lead converted → {new_lifecycle}",
        "body": (
            f"{user.get('full_name', '')} converted lead "
            f"{existing.get('first_name', '')} {existing.get('last_name', '')}"
            + (f" · company: {company_name}" if company_name else "")
            + (" · opportunity created" if opportunity_id else "")
        ),
        "company_id": company_id, "contact_id": contact_id,
        "opportunity_id": opportunity_id,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    })

    return {
        "ok": True,
        "contact_id": contact_id,
        "company_id": company_id,
        "opportunity_id": opportunity_id,
        "new_lifecycle": new_lifecycle,
    }


# ═══════════════════════════════════════════
# OPPORTUNITIES — Sales pipeline engine
# ═══════════════════════════════════════════

OPPORTUNITY_STAGES = [
    {"id": "lead", "name": "Lead", "order": 0, "probability": 5},
    {"id": "qualified", "name": "Qualified", "order": 1, "probability": 15},
    {"id": "discovery", "name": "Discovery", "order": 2, "probability": 25},
    {"id": "solution", "name": "Solution Review", "order": 3, "probability": 40},
    {"id": "proposal", "name": "Proposal Sent", "order": 4, "probability": 60},
    {"id": "negotiation", "name": "Negotiation", "order": 5, "probability": 75},
    {"id": "verbal_won", "name": "Verbal Won", "order": 6, "probability": 90},
    {"id": "closed_won", "name": "Closed Won", "order": 7, "probability": 100},
    {"id": "closed_lost", "name": "Closed Lost", "order": 8, "probability": 0},
]


@router.get("/opportunities/stages")
async def get_stages(user=Depends(get_crm_user)):
    return {"stages": OPPORTUNITY_STAGES}


@router.get("/opportunities")
async def list_opportunities(
    stage: str = "", company_id: str = "", owner_id: str = "",
    scope: str = "", territory_id: str = "",
    skip: int = 0, limit: int = 100,
    user=Depends(get_crm_user),
):
    q = await compute_visibility(user, "opportunity")
    if stage:
        q["stage"] = stage
    if company_id:
        q["company_id"] = company_id
    if owner_id:
        q["owner_id"] = owner_id
    if territory_id:
        q["territory_id"] = territory_id
    # Iter 215dc — `scope=mine` filters to the caller only; `scope=team`
    # expands to every direct/indirect report via the manager hierarchy.
    if scope == "mine":
        q["owner_id"] = user.get("id")
    elif scope == "team":
        from routes.crm_territories import collect_team_ids
        ids = await collect_team_ids(user.get("id"), user.get("organization_id"))
        q["owner_id"] = {"$in": ids}
    total = await db.crm2_opportunities.count_documents(q)
    items = await db.crm2_opportunities.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    items = await redact(user, "opportunity", items)
    return {"opportunities": items, "total": total}


@router.post("/opportunities")
async def create_opportunity(data: dict, user=Depends(get_crm_user)):
    stage = data.get("stage", "lead")
    stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == stage), OPPORTUNITY_STAGES[0])
    opp = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "title": data.get("title", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "stage": stage,
        "value": float(data.get("value", 0)),
        "probability": stage_info["probability"],
        "weighted_value": float(data.get("value", 0)) * stage_info["probability"] / 100,
        "close_date": data.get("close_date", ""),
        "owner_id": data.get("owner_id") or user.get("id"),
        "owner_name": data.get("owner_name") or user.get("full_name", ""),
        "source": data.get("source", ""),
        "competitor": data.get("competitor", ""),
        "risk_factors": data.get("risk_factors", []),
        "next_step": data.get("next_step", ""),
        "tags": data.get("tags", []),
        "stage_entered_at": _now(),
        "stage_history": [{"stage": stage, "entered_at": _now(), "by": user.get("full_name", "")}],
        # Iter 215dc — opportunity territory always inherits from the
        # linked company when present; explicit overrides still win.
        "territory_id": data.get("territory_id") or None,
        "created_at": _now(), "updated_at": _now(),
    }
    if not opp.get("territory_id") and opp.get("company_id"):
        try:
            parent = await db.crm2_companies.find_one(
                {"id": opp["company_id"]}, {"_id": 0, "territory_id": 1, "owner_id": 1, "owner_name": 1},
            )
            if parent and parent.get("territory_id"):
                opp["territory_id"] = parent["territory_id"]
                # If caller didn't pass an owner, inherit the account owner too.
                if not data.get("owner_id") and parent.get("owner_id"):
                    opp["owner_id"] = parent["owner_id"]
                    opp["owner_name"] = parent.get("owner_name", "")
                    opp["probability"] = stage_info["probability"]
        except Exception:
            pass
    await db.crm2_opportunities.insert_one(opp)
    await record_audit(entity_type="opportunity", entity_id=opp["id"], action="create", user=user, after=opp)
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Opportunity created: {opp['title']}",
        "body": f"£{opp['value']:,.0f} | Stage: {stage_info['name']}",
        "company_id": opp.get("company_id"), "contact_id": opp.get("contact_id"),
        "opportunity_id": opp["id"], "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""), "created_at": _now(), "updated_at": _now(),
    })
    await evaluate_workflows("deal_created", opp, user.get("organization_id"), user.get("full_name", ""))
    if opp["value"] > 0:
        await evaluate_workflows("deal_value_above", opp, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in opp.items() if k != "_id"}


async def _handle_stage_change(opp_id: str, new_stage: str, existing: dict, updates: dict, user: dict):
    """Handle pipeline stage transitions: update probability, log activity, fire events."""
    stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == new_stage), None)
    if not stage_info:
        return
    updates["probability"] = stage_info["probability"]
    updates["weighted_value"] = float(updates.get("value", existing.get("value", 0))) * stage_info["probability"] / 100
    updates["stage_entered_at"] = _now()
    await db.crm2_opportunities.update_one(
        {"id": opp_id},
        {"$push": {"stage_history": {"stage": new_stage, "entered_at": _now(), "by": user.get("full_name", "")}}}
    )
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Stage changed to {stage_info['name']}",
        "body": f"From {existing.get('stage', '?')} → {new_stage}",
        "opportunity_id": opp_id, "company_id": existing.get("company_id"),
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    })


@router.put("/opportunities/{opp_id}")
async def update_opportunity(opp_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_opportunities.find_one({"id": opp_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Opportunity not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at", "stage_history")}

    if "stage" in updates and updates["stage"] != existing.get("stage"):
        await _handle_stage_change(opp_id, updates["stage"], existing, updates, user)

    if "value" in updates:
        updates["value"] = float(updates["value"])
        prob = updates.get("probability", existing.get("probability", 0))
        updates["weighted_value"] = updates["value"] * prob / 100

    updates["updated_at"] = _now()
    await db.crm2_opportunities.update_one({"id": opp_id}, {"$set": updates})
    after = {**existing, **updates}
    stage_changed = "stage" in data and data["stage"] != existing.get("stage")
    await record_audit(
        entity_type="opportunity", entity_id=opp_id,
        action="stage_change" if stage_changed else "update",
        user=user, before=existing, after=after,
    )

    if "stage" in data and data["stage"] != existing.get("stage"):
        updated_record = {**existing, **updates, "id": opp_id}
        await evaluate_workflows("deal_stage_changed", updated_record, user.get("organization_id"), user.get("full_name", ""))
        if data["stage"] == "closed_won":
            from routes.integration_hub import publish_event
            await publish_event(
                event_type="deal_closed_won", source_system="crm", target_system="finance",
                entity_type="opportunity", entity_id=opp_id,
                payload={
                    "opportunity_id": opp_id, "title": existing.get("title", ""),
                    "value": updates.get("value", existing.get("value", 0)),
                    "company_id": existing.get("company_id", ""),
                    "company_name": existing.get("company_name", ""),
                    "contact_id": existing.get("contact_id", ""),
                },
                organization_id=user.get("organization_id", ""),
                triggered_by=user.get("full_name", ""),
            )
            # Iter 215by — when a corporate deal closes won, drop a
            # ready-to-invite record into `memberships_corporate_invites`
            # so the Memberships team can one-click bulk-invite the
            # company's employees. Closes the bi-directional Memberships
            # ↔ CRM loop the user asked for.
            try:
                from utils.crm_sync import upsert_crm_company  # noqa: F401 (proves helper present)
                org_id = user.get("organization_id", "")
                contact_email = ""
                if existing.get("contact_id"):
                    c = await db.crm2_contacts.find_one(
                        {"id": existing["contact_id"]}, {"_id": 0, "email": 1, "first_name": 1, "last_name": 1},
                    )
                    contact_email = (c or {}).get("email", "")
                await db.memberships_corporate_invites.insert_one({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "company_id": existing.get("company_id"),
                    "company_name": existing.get("company_name", ""),
                    "deal_value": float(updates.get("value", existing.get("value", 0)) or 0),
                    "primary_contact_id": existing.get("contact_id"),
                    "primary_contact_email": contact_email,
                    "deal_id": opp_id,
                    "deal_title": existing.get("title", ""),
                    "status": "pending_invite",
                    "created_at": _now(),
                })
            except Exception:
                pass  # best-effort — never block the deal close
    return {"success": True}


@router.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str, user=Depends(get_crm_user)):
    o = await db.crm2_opportunities.find_one({"id": opp_id, **_of(user)}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Opportunity not found")
    of = _of(user)
    o["activities"] = await db.crm2_activities.find({"opportunity_id": opp_id, **of}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    o["quotes"] = await db.crm2_quotes.find({"opportunity_id": opp_id, **of}, {"_id": 0}).to_list(20)
    if o.get("company_id"):
        o["company"] = await db.crm2_companies.find_one({"id": o["company_id"], **of}, {"_id": 0, "name": 1, "sector": 1})
    if o.get("contact_id"):
        o["contact"] = await db.crm2_contacts.find_one({"id": o["contact_id"], **of}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "job_title": 1})
    return o


@router.delete("/opportunities/{opp_id}")
async def delete_opportunity(opp_id: str, user=Depends(get_crm_user)):
    existing = await db.crm2_opportunities.find_one({"id": opp_id, **_of(user)}, {"_id": 0})
    r = await db.crm2_opportunities.delete_one({"id": opp_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Opportunity not found")
    await record_audit(entity_type="opportunity", entity_id=opp_id, action="delete", user=user, before=existing)
    return {"success": True}


# ═══════════════════════════════════════════
# DASHBOARD — Real operating metrics
# ═══════════════════════════════════════════

async def _dashboard_pipeline_metrics(of: dict) -> tuple:
    """Compute pipeline value, weighted forecast, stage breakdown."""
    active_opps = await db.crm2_opportunities.find(
        {**of, "stage": {"$nin": ["closed_won", "closed_lost"]}},
        {"_id": 0, "value": 1, "weighted_value": 1, "stage": 1, "stage_entered_at": 1,
         "owner_id": 1, "owner_name": 1, "title": 1, "company_name": 1, "close_date": 1, "created_at": 1}
    ).to_list(500)
    pipeline_value = sum(o.get("value", 0) for o in active_opps)
    weighted_forecast = sum(o.get("weighted_value", 0) for o in active_opps)
    stage_counts, stage_values = {}, {}
    for o in active_opps:
        s = o.get("stage", "lead")
        stage_counts[s] = stage_counts.get(s, 0) + 1
        stage_values[s] = stage_values.get(s, 0) + o.get("value", 0)
    return active_opps, pipeline_value, weighted_forecast, stage_counts, stage_values


async def _dashboard_win_metrics(of: dict) -> tuple:
    """Compute win rate, won revenue, counts."""
    won_opps = await db.crm2_opportunities.find({**of, "stage": "closed_won"}, {"_id": 0, "value": 1}).to_list(500)
    won_revenue = sum(o.get("value", 0) for o in won_opps)
    total_closed = await db.crm2_opportunities.count_documents({**of, "stage": {"$in": ["closed_won", "closed_lost"]}})
    won_count = len(won_opps)
    win_rate = round((won_count / total_closed * 100) if total_closed > 0 else 0, 1)
    return won_revenue, win_rate, won_count, total_closed - won_count


def _find_stagnating_deals(active_opps: list, threshold_days: int = 14) -> list:
    """Identify deals stuck in the same stage beyond threshold."""
    now_ts = datetime.now(timezone.utc)
    stagnating = []
    for o in active_opps:
        entered = o.get("stage_entered_at") or o.get("created_at", "")
        try:
            entered_dt = datetime.fromisoformat(entered.replace("Z", "+00:00"))
            days = (now_ts - entered_dt).days
            if days > threshold_days:
                stagnating.append({**o, "days_in_stage": days})
        except (ValueError, AttributeError):
            pass
    stagnating.sort(key=lambda x: x.get("days_in_stage", 0), reverse=True)
    return stagnating[:5]


@router.get("/dashboard")
async def dashboard(user=Depends(get_crm_user)):
    of = _of(user)

    active_opps, pipeline_value, weighted_forecast, stage_counts, stage_values = await _dashboard_pipeline_metrics(of)
    won_revenue, win_rate, won_count, lost_count = await _dashboard_win_metrics(of)

    total_contacts = await db.crm2_contacts.count_documents(of)
    total_companies = await db.crm2_companies.count_documents(of)
    total_opportunities = len(active_opps)
    open_cases = await db.crm2_cases.count_documents({**of, "status": {"$nin": ["closed", "resolved"]}})
    tasks_due = await db.crm2_activities.count_documents({**of, "type": "task", "completed_at": None})
    recent = await db.crm2_activities.find(of, {"_id": 0}).sort("created_at", -1).limit(15).to_list(15)

    high_cases = await db.crm2_cases.count_documents({**of, "status": {"$nin": ["closed", "resolved"]}, "severity": "high"})
    med_cases = await db.crm2_cases.count_documents({**of, "status": {"$nin": ["closed", "resolved"]}, "severity": "medium"})
    low_cases = await db.crm2_cases.count_documents({**of, "status": {"$nin": ["closed", "resolved"]}, "severity": "low"})

    my_tasks = await db.crm2_activities.find(
        {**of, "type": "task", "completed_at": None, "owner_id": user.get("id")}, {"_id": 0}
    ).sort("due_date", 1).limit(10).to_list(10)
    upcoming_meetings = await db.crm2_activities.find(
        {**of, "type": "meeting", "completed_at": None}, {"_id": 0}
    ).sort("due_date", 1).limit(5).to_list(5)

    return {
        "role": user.get("role", "user"),
        "pipeline_value": pipeline_value,
        "weighted_forecast": weighted_forecast,
        "won_revenue": won_revenue,
        "win_rate": win_rate,
        "won_count": won_count,
        "lost_count": lost_count,
        "total_contacts": total_contacts,
        "total_companies": total_companies,
        "active_opportunities": total_opportunities,
        "open_cases": open_cases,
        "total_assets": await db.crm2_assets.count_documents(of),
        "tasks_due": tasks_due,
        "stage_breakdown": [
            {"stage": s["id"], "name": s["name"], "count": stage_counts.get(s["id"], 0), "value": stage_values.get(s["id"], 0)}
            for s in OPPORTUNITY_STAGES if s["id"] not in ("closed_won", "closed_lost")
        ],
        "recent_activities": recent,
        "stagnating_deals": _find_stagnating_deals(active_opps),
        "cases_by_severity": {"high": high_cases, "medium": med_cases, "low": low_cases},
        "my_tasks": my_tasks,
        "upcoming_meetings": upcoming_meetings,
    }


# ═══════════════════════════════════════════
# SERVICE CASES (linked to self-service)
# ═══════════════════════════════════════════

@router.get("/cases")
async def list_cases(
    company_id: str = "", status: str = "", severity: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if company_id:
        q["company_id"] = company_id
    if status:
        q["status"] = status
    if severity:
        q["severity"] = severity
    total = await db.crm2_cases.count_documents(q)
    items = await db.crm2_cases.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"cases": items, "total": total}


@router.post("/cases")
async def create_case(data: dict, user=Depends(get_crm_user)):
    case = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "case_number": f"CS-{str(uuid.uuid4())[:6].upper()}",
        "subject": data.get("subject", ""),
        "description": data.get("description", ""),
        "company_id": data.get("company_id"),
        "contact_id": data.get("contact_id"),
        "asset_id": data.get("asset_id"),
        "severity": data.get("severity", "medium"),
        "status": "open",
        "priority": data.get("priority", "normal"),
        "assigned_to": data.get("assigned_to"),
        "source": data.get("source", "crm"),  # crm, self_service, email, phone
        "sla_due": data.get("sla_due"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_cases.insert_one(case)
    await evaluate_workflows("case_created", case, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in case.items() if k != "_id"}


# ═══════════════════════════════════════════
# ASSETS / INSTALLED BASE
# ═══════════════════════════════════════════

@router.get("/assets")
async def list_assets(
    company_id: str = "", site_id: str = "", status: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if company_id:
        q["company_id"] = company_id
    if site_id:
        q["site_id"] = site_id
    if status:
        q["status"] = status
    total = await db.crm2_assets.count_documents(q)
    items = await db.crm2_assets.find(q, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    return {"assets": items, "total": total}


@router.post("/assets")
async def create_asset(data: dict, user=Depends(get_crm_user)):
    asset = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "name": data.get("name", ""),
        "serial_number": data.get("serial_number", ""),
        "product_id": data.get("product_id"),
        "company_id": data.get("company_id"),
        "site_id": data.get("site_id"),
        "status": data.get("status", "active"),
        "install_date": data.get("install_date"),
        "warranty_expiry": data.get("warranty_expiry"),
        "contract_id": data.get("contract_id"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_assets.insert_one(asset)
    return {k: v for k, v in asset.items() if k != "_id"}


# ═══════════════════════════════════════════
# QUOTES
# ═══════════════════════════════════════════

@router.get("/quotes")
async def list_quotes(
    company_id: str = "", opportunity_id: str = "", status: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if company_id:
        q["company_id"] = company_id
    if opportunity_id:
        q["opportunity_id"] = opportunity_id
    if status:
        q["status"] = status
    total = await db.crm2_quotes.count_documents(q)
    items = await db.crm2_quotes.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"quotes": items, "total": total}


@router.post("/quotes")
async def create_quote(data: dict, user=Depends(get_crm_user)):
    lines = data.get("lines", [])
    subtotal = sum(float(line.get("quantity", 0)) * float(line.get("unit_price", 0)) for line in lines)
    vat_rate = float(data.get("vat_rate", 20))
    vat = subtotal * vat_rate / 100
    # Resolve company and contact names
    company_name = ""
    contact_name = ""
    if data.get("company_id"):
        co = await db.crm2_companies.find_one({"id": data["company_id"]}, {"_id": 0, "name": 1})
        company_name = (co or {}).get("name", "")
    if data.get("contact_id"):
        ct = await db.crm2_contacts.find_one({"id": data["contact_id"]}, {"_id": 0, "first_name": 1, "last_name": 1})
        if ct:
            contact_name = f"{ct.get('first_name', '')} {ct.get('last_name', '')}".strip()
    quote = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "quote_number": f"QT-{str(uuid.uuid4())[:6].upper()}",
        "company_id": data.get("company_id"),
        "company_name": company_name,
        "contact_id": data.get("contact_id"),
        "contact_name": contact_name,
        "opportunity_id": data.get("opportunity_id"),
        "status": "draft",
        "lines": lines,
        "subtotal": round(subtotal, 2),
        "vat_rate": vat_rate, "vat_amount": round(vat, 2),
        "total": round(subtotal + vat, 2),
        "valid_until": data.get("valid_until", ""),
        "notes": data.get("notes", ""),
        "version": 1,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_quotes.insert_one(quote)
    await evaluate_workflows("quote_created", quote, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in quote.items() if k != "_id"}



@router.post("/quotes/{quote_id}/revise")
async def revise_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Create a new version of a quote. The original is preserved, a new doc is created with version+1."""
    original = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not original:
        raise HTTPException(404, "Quote not found")

    new_version = original.get("version", 1) + 1
    base_number = original.get("quote_number", "").split("/")[0]
    lines = data.get("lines", original.get("lines", []))
    subtotal = sum(float(ln.get("quantity", 0)) * float(ln.get("unit_price", 0)) * (1 - float(ln.get("discount", 0)) / 100) for ln in lines)
    vat_rate = float(data.get("vat_rate", original.get("vat_rate", 20)))
    vat = subtotal * vat_rate / 100

    new_quote = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "quote_number": f"{base_number}/v{new_version}",
        "parent_quote_id": original.get("parent_quote_id") or original["id"],
        "previous_version_id": original["id"],
        "company_id": data.get("company_id", original.get("company_id")),
        "company_name": original.get("company_name", ""),
        "contact_id": data.get("contact_id", original.get("contact_id")),
        "contact_name": original.get("contact_name", ""),
        "opportunity_id": original.get("opportunity_id"),
        "status": "draft",
        "lines": lines,
        "subtotal": round(subtotal, 2),
        "vat_rate": vat_rate, "vat_amount": round(vat, 2),
        "total": round(subtotal + vat, 2),
        "valid_until": data.get("valid_until", original.get("valid_until", "")),
        "notes": data.get("notes", original.get("notes", "")),
        "version": new_version,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_quotes.insert_one(new_quote)
    # Mark original as superseded
    await db.crm2_quotes.update_one({"id": quote_id}, {"$set": {"status": "superseded", "superseded_by": new_quote["id"]}})
    return {k: v for k, v in new_quote.items() if k != "_id"}


@router.get("/quotes/{quote_id}/versions")
async def get_quote_versions(quote_id: str, user=Depends(get_crm_user)):
    """Get all versions of a quote chain (original + all revisions)."""
    quote = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    root_id = quote.get("parent_quote_id") or quote["id"]
    versions = await db.crm2_quotes.find(
        {"$or": [{"id": root_id}, {"parent_quote_id": root_id}], **_of(user)},
        {"_id": 0}
    ).sort("version", 1).to_list(50)
    return {"versions": versions, "current_id": quote_id}



# ═══════════════════════════════════════════
# CONTRACTS
# ═══════════════════════════════════════════

@router.get("/contracts")
async def list_contracts(
    company_id: str = "", status: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if company_id:
        q["company_id"] = company_id
    if status:
        q["status"] = status
    total = await db.crm2_contracts.count_documents(q)
    items = await db.crm2_contracts.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"contracts": items, "total": total}


# ═══════════════════════════════════════════
# GLOBAL SEARCH
# ═══════════════════════════════════════════

@router.get("/search")
async def global_search(q: str = Query("", min_length=1), user=Depends(get_crm_user)):
    """Search across all entity types."""
    of = _of(user)
    regex = {"$regex": q, "$options": "i"}
    results = []

    # Companies
    companies = await db.crm2_companies.find({**of, "name": regex}, {"_id": 0, "id": 1, "name": 1}).limit(5).to_list(5)
    for c in companies:
        results.append({"type": "company", "id": c["id"], "label": c["name"]})

    # Contacts
    contacts = await db.crm2_contacts.find({**of, "$or": [{"first_name": regex}, {"last_name": regex}, {"email": regex}]}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5).to_list(5)
    for c in contacts:
        results.append({"type": "contact", "id": c["id"], "label": f"{c['first_name']} {c['last_name']}"})

    # Opportunities
    opps = await db.crm2_opportunities.find({**of, "title": regex}, {"_id": 0, "id": 1, "title": 1, "value": 1}).limit(5).to_list(5)
    for o in opps:
        results.append({"type": "opportunity", "id": o["id"], "label": o["title"], "value": o.get("value", 0)})

    # Cases
    cases = await db.crm2_cases.find({**of, "$or": [{"subject": regex}, {"case_number": regex}]}, {"_id": 0, "id": 1, "subject": 1, "case_number": 1}).limit(5).to_list(5)
    for c in cases:
        results.append({"type": "case", "id": c["id"], "label": f"{c['case_number']}: {c['subject']}"})

    return {"results": results, "query": q}


# ═══════════════════════════════════════════
# WORKFLOWS — Automation Engine (MongoDB-backed)
# ═══════════════════════════════════════════

WORKFLOW_TRIGGERS = [
    {"id": "deal_stage_changed", "label": "Deal stage changes", "entity": "opportunity"},
    {"id": "deal_created", "label": "New deal created", "entity": "opportunity"},
    {"id": "deal_value_above", "label": "Deal value exceeds threshold", "entity": "opportunity"},
    {"id": "contact_created", "label": "New contact added", "entity": "contact"},
    {"id": "case_created", "label": "New service case", "entity": "case"},
    {"id": "quote_created", "label": "New quote created", "entity": "quote"},
    {"id": "company_created", "label": "New company added", "entity": "company"},
]

WORKFLOW_ACTIONS = [
    {"id": "create_task", "label": "Create a task"},
    {"id": "send_notification", "label": "Send notification"},
    {"id": "create_activity", "label": "Log activity"},
    {"id": "move_deal_stage", "label": "Move deal to stage"},
    {"id": "add_tag", "label": "Add tag to record"},
    {"id": "update_field", "label": "Update a field"},
]

WORKFLOW_TEMPLATES = [
    {
        "id": "lead_nurture",
        "name": "Lead Nurture Sequence",
        "description": "When a new deal is created at Lead stage, create follow-up tasks",
        "trigger": {"type": "deal_created"},
        "conditions": [{"field": "stage", "operator": "equals", "value": "lead"}],
        "actions": [
            {"type": "create_task", "config": {"description": "Send introduction email", "priority": "high", "due_days": 1}},
            {"type": "create_task", "config": {"description": "Schedule discovery call", "priority": "normal", "due_days": 3}},
        ],
    },
    {
        "id": "quote_followup",
        "name": "Quote Follow-Up",
        "description": "When a deal moves to Proposal Sent, create a follow-up task",
        "trigger": {"type": "deal_stage_changed"},
        "conditions": [{"field": "stage", "operator": "equals", "value": "proposal"}],
        "actions": [
            {"type": "create_task", "config": {"description": "Follow up on sent quote", "priority": "high", "due_days": 3}},
            {"type": "create_activity", "config": {"type": "note", "subject": "Quote sent - follow up needed"}},
        ],
    },
    {
        "id": "service_escalation",
        "name": "Service Case Escalation",
        "description": "When a high-severity case is created, notify the team",
        "trigger": {"type": "case_created"},
        "conditions": [{"field": "severity", "operator": "equals", "value": "high"}],
        "actions": [
            {"type": "send_notification", "config": {"message": "High severity case created - immediate attention required"}},
            {"type": "create_task", "config": {"description": "Review high-severity case", "priority": "high", "due_days": 0}},
        ],
    },
    {
        "id": "deal_won",
        "name": "Deal Won Celebration",
        "description": "When a deal is closed-won, create onboarding tasks",
        "trigger": {"type": "deal_stage_changed"},
        "conditions": [{"field": "stage", "operator": "equals", "value": "closed_won"}],
        "actions": [
            {"type": "create_task", "config": {"description": "Schedule kick-off meeting with customer", "priority": "high", "due_days": 1}},
            {"type": "create_task", "config": {"description": "Create installation plan", "priority": "normal", "due_days": 5}},
            {"type": "send_notification", "config": {"message": "Deal won! Time to onboard the customer."}},
        ],
    },
]


@router.get("/workflows/meta")
async def get_workflow_meta(user=Depends(get_crm_user)):
    return {
        "triggers": WORKFLOW_TRIGGERS,
        "actions": WORKFLOW_ACTIONS,
        "templates": WORKFLOW_TEMPLATES,
    }


@router.get("/workflows")
async def list_workflows(
    active: str = "", skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if active == "true":
        q["active"] = True
    elif active == "false":
        q["active"] = False
    total = await db.crm2_workflows.count_documents(q)
    items = await db.crm2_workflows.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"workflows": items, "total": total}


@router.post("/workflows")
async def create_workflow(data: dict, user=Depends(get_crm_user)):
    wf = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "trigger": data.get("trigger", {}),
        "conditions": data.get("conditions", []),
        "actions": data.get("actions", []),
        "active": data.get("active", True),
        "execution_count": 0,
        "last_run_at": None,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_workflows.insert_one(wf)
    return {k: v for k, v in wf.items() if k != "_id"}


@router.post("/workflows/from-template")
async def create_from_template(data: dict, user=Depends(get_crm_user)):
    tpl_id = data.get("template_id", "")
    tpl = next((t for t in WORKFLOW_TEMPLATES if t["id"] == tpl_id), None)
    if not tpl:
        raise HTTPException(404, "Template not found")
    wf = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "name": data.get("name") or tpl["name"],
        "description": tpl["description"],
        "trigger": tpl["trigger"],
        "conditions": tpl["conditions"],
        "actions": tpl["actions"],
        "active": True, "execution_count": 0, "last_run_at": None,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_workflows.insert_one(wf)
    return {k: v for k, v in wf.items() if k != "_id"}


@router.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str, user=Depends(get_crm_user)):
    wf = await db.crm2_workflows.find_one({"id": wf_id, **_of(user)}, {"_id": 0})
    if not wf:
        raise HTTPException(404, "Workflow not found")
    runs = await db.crm2_workflow_runs.find(
        {"workflow_id": wf_id, **_of(user)}, {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    wf["runs"] = runs
    return wf


@router.put("/workflows/{wf_id}")
async def update_workflow(wf_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_workflows.find_one({"id": wf_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Workflow not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    updates["updated_at"] = _now()
    await db.crm2_workflows.update_one({"id": wf_id}, {"$set": updates})
    return {"success": True}


@router.post("/workflows/{wf_id}/toggle")
async def toggle_workflow(wf_id: str, user=Depends(get_crm_user)):
    wf = await db.crm2_workflows.find_one({"id": wf_id, **_of(user)})
    if not wf:
        raise HTTPException(404, "Workflow not found")
    new_active = not wf.get("active", False)
    await db.crm2_workflows.update_one({"id": wf_id}, {"$set": {"active": new_active, "updated_at": _now()}})
    return {"active": new_active}


@router.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_workflows.delete_one({"id": wf_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Workflow not found")
    return {"success": True}


@router.get("/workflows/{wf_id}/runs")
async def list_workflow_runs(wf_id: str, skip: int = 0, limit: int = 50, user=Depends(get_crm_user)):
    q = {"workflow_id": wf_id, **_of(user)}
    total = await db.crm2_workflow_runs.count_documents(q)
    items = await db.crm2_workflow_runs.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"runs": items, "total": total}


# ── Workflow Execution Engine ──

async def _action_create_task(config: dict, context: dict, org_id: str, user_name: str) -> str:
    from datetime import timedelta
    due = (datetime.now(timezone.utc) + timedelta(days=int(config.get("due_days", 1)))).isoformat()
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": org_id, "type": "task",
        "subject": config.get("description", "Auto-created task"),
        "body": f"Created by workflow for {context.get('entity_type', '')} '{context.get('entity_name', '')}'",
        "company_id": context.get("company_id"), "contact_id": context.get("contact_id"),
        "opportunity_id": context.get("opportunity_id"), "case_id": context.get("case_id"),
        "owner_id": context.get("owner_id"), "owner_name": user_name,
        "due_date": due, "completed_at": None, "priority": config.get("priority", "normal"),
        "metadata": {"source": "workflow"}, "created_at": _now(), "updated_at": _now(),
    })
    return f"Task created: {config.get('description', '')}"


async def _action_create_activity(config: dict, context: dict, org_id: str, user_name: str) -> str:
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": org_id,
        "type": config.get("type", "note"),
        "subject": config.get("subject", "Workflow note"),
        "body": config.get("body", f"Auto-logged by workflow for {context.get('entity_name', '')}"),
        "company_id": context.get("company_id"), "contact_id": context.get("contact_id"),
        "opportunity_id": context.get("opportunity_id"),
        "owner_id": context.get("owner_id"), "owner_name": user_name,
        "metadata": {"source": "workflow"}, "created_at": _now(), "updated_at": _now(),
    })
    return f"Activity logged: {config.get('subject', '')}"


async def _action_send_notification(config: dict, context: dict, org_id: str) -> str:
    await db.crm2_notifications.insert_one({
        "id": _id(), "organization_id": org_id, "type": "workflow",
        "title": "Workflow Notification", "message": config.get("message", ""),
        "entity_type": context.get("entity_type"), "entity_id": context.get("entity_id"),
        "entity_name": context.get("entity_name"), "read": False, "created_at": _now(),
    })
    return f"Notification sent: {config.get('message', '')[:60]}"


async def _action_move_deal_stage(config: dict, context: dict) -> str:
    target = config.get("target_stage", "")
    if not target or not context.get("opportunity_id"):
        return "No target stage or opportunity"
    stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == target), None)
    if not stage_info:
        return f"Unknown stage: {target}"
    await db.crm2_opportunities.update_one(
        {"id": context["opportunity_id"]},
        {"$set": {"stage": target, "probability": stage_info["probability"], "updated_at": _now()},
         "$push": {"stage_history": {"stage": target, "entered_at": _now(), "by": "Workflow"}}}
    )
    return f"Deal moved to {stage_info['name']}"


async def _action_modify_entity(action_type: str, config: dict, context: dict) -> str:
    entity_type = context.get("entity_type")
    entity_id = context.get("entity_id")
    coll_map = {"company": db.crm2_companies, "contact": db.crm2_contacts, "opportunity": db.crm2_opportunities}
    coll = coll_map.get(entity_type)
    if not coll:
        return f"Unknown entity type: {entity_type}"
    if action_type == "add_tag":
        tag = config.get("tag", "")
        if tag:
            await coll.update_one({"id": entity_id}, {"$addToSet": {"tags": tag}})
            return f"Tag '{tag}' added"
    elif action_type == "update_field":
        field = config.get("field", "")
        value = config.get("value", "")
        if field:
            await coll.update_one({"id": entity_id}, {"$set": {field: value, "updated_at": _now()}})
            return f"Set {field} = {value}"
    return "No action taken"


async def _execute_action(action, context, org_id, user_name):
    """Execute a single workflow action via handler dispatch."""
    atype = action.get("type", "")
    config = action.get("config", {})

    handlers = {
        "create_task": lambda: _action_create_task(config, context, org_id, user_name),
        "create_activity": lambda: _action_create_activity(config, context, org_id, user_name),
        "send_notification": lambda: _action_send_notification(config, context, org_id),
        "move_deal_stage": lambda: _action_move_deal_stage(config, context),
        "add_tag": lambda: _action_modify_entity("add_tag", config, context),
        "update_field": lambda: _action_modify_entity("update_field", config, context),
    }

    handler = handlers.get(atype)
    detail = await handler() if handler else f"Unknown action: {atype}"
    return {"type": atype, "status": "success", "detail": detail}


_CONDITION_OPS = {
    "equals": lambda actual, val: str(actual) == str(val),
    "not_equals": lambda actual, val: str(actual) != str(val),
    "contains": lambda actual, val: val.lower() in str(actual or "").lower(),
    "greater_than": lambda actual, val: _safe_float(actual) > _safe_float(val),
    "less_than": lambda actual, val: _safe_float(actual) < _safe_float(val),
}


def _safe_float(v) -> float:
    try:
        return float(v or 0)
    except (ValueError, TypeError):
        return 0.0


def _check_conditions(conditions, record):
    """Check if all conditions match the record using operator lookup."""
    for cond in conditions:
        op_fn = _CONDITION_OPS.get(cond.get("operator", "equals"))
        if not op_fn:
            continue
        if not op_fn(record.get(cond.get("field", "")), cond.get("value", "")):
            return False
    return True


def _workflow_entity_name(record: dict) -> str:
    """Best-effort human name for an entity record."""
    return (record.get("title")
            or record.get("name")
            or record.get("subject")
            or f"{record.get('first_name', '')} {record.get('last_name', '')}".strip())


def _workflow_contact_id(trigger_type: str, record: dict) -> str | None:
    """Resolve the contact_id used in a workflow context."""
    if trigger_type == "contact_created":
        return record.get("contact_id") or record.get("id")
    return record.get("contact_id")


def _build_workflow_context(trigger_type: str, record: dict) -> dict:
    """Build the entity context passed to workflow actions."""
    return {
        "entity_type": _trigger_entity(trigger_type),
        "entity_id": record.get("id", ""),
        "entity_name": _workflow_entity_name(record),
        "company_id": record.get("company_id"),
        "contact_id": _workflow_contact_id(trigger_type, record),
        "opportunity_id": record.get("id") if "deal" in trigger_type else record.get("opportunity_id"),
        "case_id": record.get("id") if trigger_type == "case_created" else None,
        "owner_id": record.get("owner_id"),
    }


async def _run_workflow_actions(actions: list, context: dict, org_id: str, user_name: str) -> list:
    """Execute each action in a workflow and return the results list."""
    results = []
    for action in actions:
        res = await _execute_action(action, context, org_id, user_name)
        results.append(res)
    return results


async def _record_workflow_run(wf: dict, trigger_type: str, context: dict,
                               actions_results: list, org_id: str) -> None:
    """Persist a workflow run and bump the workflow's execution stats."""
    run = {
        "id": _id(), "organization_id": org_id,
        "workflow_id": wf["id"], "workflow_name": wf.get("name", ""),
        "trigger_type": trigger_type,
        "entity_type": context["entity_type"],
        "entity_id": context["entity_id"],
        "entity_name": context["entity_name"],
        "actions_executed": actions_results,
        "status": "success",
        "created_at": _now(),
    }
    await db.crm2_workflow_runs.insert_one(run)
    await db.crm2_workflows.update_one(
        {"id": wf["id"]},
        {"$inc": {"execution_count": 1}, "$set": {"last_run_at": _now()}}
    )


async def evaluate_workflows(trigger_type, record, org_id, user_name):
    """Find and execute matching workflows for a trigger event."""
    workflows = await db.crm2_workflows.find(
        {"organization_id": org_id, "active": True, "trigger.type": trigger_type}, {"_id": 0}
    ).to_list(50)

    for wf in workflows:
        if not _check_conditions(wf.get("conditions", []), record):
            continue
        context = _build_workflow_context(trigger_type, record)
        actions_results = await _run_workflow_actions(wf.get("actions", []), context, org_id, user_name)
        await _record_workflow_run(wf, trigger_type, context, actions_results, org_id)


def _trigger_entity(trigger_type):
    mapping = {
        "deal_stage_changed": "opportunity",
        "deal_created": "opportunity",
        "deal_value_above": "opportunity",
        "contact_created": "contact",
        "case_created": "case",
        "quote_created": "quote",
        "company_created": "company",
    }
    return mapping.get(trigger_type, "unknown")


# ═══════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════

@router.get("/notifications")
async def list_notifications(
    unread_only: str = "", skip: int = 0, limit: int = 30,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if unread_only == "true":
        q["read"] = False
    total = await db.crm2_notifications.count_documents(q)
    unread = await db.crm2_notifications.count_documents({**_of(user), "read": False})
    items = await db.crm2_notifications.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"notifications": items, "total": total, "unread": unread}


@router.post("/notifications/mark-read")
async def mark_notifications_read(data: dict, user=Depends(get_crm_user)):
    ids = data.get("ids", [])
    if ids:
        await db.crm2_notifications.update_many(
            {"id": {"$in": ids}, **_of(user)}, {"$set": {"read": True}}
        )
    else:
        await db.crm2_notifications.update_many(
            {**_of(user), "read": False}, {"$set": {"read": True}}
        )
    return {"success": True}


# ═══════════════════════════════════════════
# QUICK CREATE (combined entity creation)
# ═══════════════════════════════════════════

@router.post("/quick-create")
async def quick_create(data: dict, user=Depends(get_crm_user)):
    """Create any entity type quickly from the header."""
    entity_type = data.get("entity_type", "")
    org_id = user.get("organization_id")
    user_name = user.get("full_name", "")
    user_id = user.get("id")

    creators = {
        "contact": lambda: _quick_create_contact(data, org_id, user_id, user_name),
        "deal": lambda: _quick_create_deal(data, org_id, user_id, user_name),
        "case": lambda: _quick_create_case(data, org_id, user_name),
        "task": lambda: _quick_create_task(data, org_id, user_id, user_name),
    }
    creator = creators.get(entity_type)
    if not creator:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")
    return await creator()


async def _quick_create_contact(data: dict, org_id: str, user_id: str, user_name: str) -> dict:
    contact = {
        "id": _id(), "organization_id": org_id,
        "first_name": data.get("first_name", ""), "last_name": data.get("last_name", ""),
        "email": data.get("email", ""), "phone": data.get("phone", ""),
        "job_title": data.get("job_title", ""),
        "company_id": data.get("company_id"), "company_name": data.get("company_name", ""),
        "is_decision_maker": False, "is_champion": False,
        "source": "quick_create", "status": "active", "tags": [], "relationship_score": 0,
        "owner_id": user_id, "owner_name": user_name,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_contacts.insert_one(contact)
    await evaluate_workflows("contact_created", contact, org_id, user_name)
    return {"entity_type": "contact", "id": contact["id"], "label": f"{contact['first_name']} {contact['last_name']}"}


async def _quick_create_deal(data: dict, org_id: str, user_id: str, user_name: str) -> dict:
    stage = data.get("stage", "lead")
    stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == stage), OPPORTUNITY_STAGES[0])
    val = float(data.get("value", 0))
    opp = {
        "id": _id(), "organization_id": org_id,
        "title": data.get("title", ""),
        "company_id": data.get("company_id"), "company_name": data.get("company_name", ""),
        "contact_id": data.get("contact_id"), "contact_name": data.get("contact_name", ""),
        "stage": stage, "value": val,
        "probability": stage_info["probability"],
        "weighted_value": val * stage_info["probability"] / 100,
        "close_date": data.get("close_date", ""),
        "owner_id": user_id, "owner_name": user_name,
        "source": "quick_create", "tags": [],
        "stage_entered_at": _now(),
        "stage_history": [{"stage": stage, "entered_at": _now(), "by": user_name}],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_opportunities.insert_one(opp)
    await evaluate_workflows("deal_created", opp, org_id, user_name)
    return {"entity_type": "deal", "id": opp["id"], "label": opp["title"]}


async def _quick_create_case(data: dict, org_id: str, user_name: str) -> dict:
    case = {
        "id": _id(), "organization_id": org_id,
        "case_number": f"CS-{str(uuid.uuid4())[:6].upper()}",
        "subject": data.get("subject", ""), "description": data.get("description", ""),
        "company_id": data.get("company_id"),
        "severity": data.get("severity", "medium"),
        "status": "open", "priority": data.get("priority", "normal"),
        "source": "quick_create", "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_cases.insert_one(case)
    await evaluate_workflows("case_created", case, org_id, user_name)
    return {"entity_type": "case", "id": case["id"], "label": case["case_number"]}


async def _quick_create_task(data: dict, org_id: str, user_id: str, user_name: str) -> dict:
    task = {
        "id": _id(), "organization_id": org_id,
        "type": "task", "subject": data.get("subject", ""), "body": data.get("body", ""),
        "company_id": data.get("company_id"), "contact_id": data.get("contact_id"),
        "opportunity_id": data.get("opportunity_id"),
        "owner_id": user_id, "owner_name": user_name,
        "due_date": data.get("due_date"), "completed_at": None,
        "priority": data.get("priority", "normal"),
        "metadata": {}, "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_activities.insert_one(task)
    return {"entity_type": "task", "id": task["id"], "label": task["subject"]}


# ═══════════════════════════════════════════
# COMPANY FILES (Drawings / Surveys / Invoices)
# ═══════════════════════════════════════════

from fastapi import UploadFile, File as FastAPIFile
import base64


@router.get("/companies/{company_id}/files")
async def list_company_files(company_id: str, category: str = "", user=Depends(get_crm_user)):
    q = {"company_id": company_id, **_of(user)}
    if category:
        q["category"] = category
    items = await db.crm2_company_files.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"files": items, "total": len(items)}


@router.post("/companies/{company_id}/files")
async def upload_company_file(
    company_id: str,
    category: str = "general",
    notes: str = "",
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_crm_user),
):
    content = await file.read()
    b64 = base64.b64encode(content).decode("utf-8")
    doc = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "company_id": company_id,
        "category": category,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "data_b64": b64,
        "notes": notes,
        "uploaded_by": user.get("id"),
        "uploaded_by_name": user.get("full_name", ""),
        "created_at": _now(),
    }
    await db.crm2_company_files.insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("_id", "data_b64")}


@router.delete("/companies/{company_id}/files/{file_id}")
async def delete_company_file(company_id: str, file_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_company_files.delete_one({"id": file_id, "company_id": company_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "File not found")
    return {"success": True}


@router.get("/companies/{company_id}/files/{file_id}/download")
async def download_company_file(company_id: str, file_id: str, user=Depends(get_crm_user)):
    doc = await db.crm2_company_files.find_one({"id": file_id, "company_id": company_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "File not found")
    from fastapi.responses import Response
    data = base64.b64decode(doc.get("data_b64", ""))
    return Response(content=data, media_type=doc.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{doc.get("original_filename", "file")}"'})


# ═══════════════════════════════════════════
# EQUIPMENT FROM SERVICE PORTAL
# ═══════════════════════════════════════════

_EQUIPMENT_FIELD_MAP = {
    "name": ["name", "equipment_name", "item_name"],
    "model_code": ["model_code", "model"],
    "serial_number": ["serial_number", "serial"],
    "location": ["location", "zone", "area"],
    "status": ["status"],
    "category": ["category", "type"],
    "site_name": ["site_name", "site", "gym_name"],
}


def _map_equipment_item(item: dict, coll_name: str) -> dict:
    """Map a raw equipment document to a standardised response format using field lookup."""
    result = {"id": str(item.get("id", item.get("_id", ""))), "source_collection": coll_name}
    for target_key, source_keys in _EQUIPMENT_FIELD_MAP.items():
        result[target_key] = next((item[k] for k in source_keys if item.get(k)), "")
    result["name"] = result["name"] or "Equipment"
    result["status"] = result["status"] or "Active"
    return result


async def _search_portal_collections(company_name: str) -> list:
    """Search across service portal equipment collections for a company name."""
    equipment = []
    query = {"$or": [
        {"site_name": {"$regex": company_name, "$options": "i"}},
        {"location": {"$regex": company_name, "$options": "i"}},
        {"site": {"$regex": company_name, "$options": "i"}},
        {"organization_name": {"$regex": company_name, "$options": "i"}},
        {"gym_name": {"$regex": company_name, "$options": "i"}},
        {"company": {"$regex": company_name, "$options": "i"}},
    ]}
    for coll_name in ["equipment", "gym_items", "items", "site_equipment"]:
        try:
            coll = db[coll_name]
            if await coll.count_documents({}) == 0:
                continue
            items = await coll.find(query, {"_id": 0}).limit(200).to_list(200)
            equipment.extend(_map_equipment_item(item, coll_name) for item in items)
        except Exception:
            continue
    return equipment


@router.get("/companies/{company_id}/portal-equipment")
async def get_portal_equipment(company_id: str, user=Depends(get_crm_user)):
    """Pull equipment from Service Portal for a company."""
    company = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    name = company.get("name", "")

    equipment = await _search_portal_collections(name)

    crm_assets = await db.crm2_assets.find({"company_id": company_id, **_of(user)}, {"_id": 0}).limit(200).to_list(200)
    for a in crm_assets:
        equipment.append(_map_equipment_item({**a, "site_name": name}, "crm2_assets"))

    return {"equipment": equipment, "total": len(equipment), "company_name": name}


# ═══════════════════════════════════════════
# DOCUMENTS — Sub-categories
# ═══════════════════════════════════════════

DOCUMENT_CATEGORIES = [
    "spec_sheets", "pre_install", "maintenance", "manuals",
    "general", "contract", "proposal", "invoice", "other"
]


@router.get("/documents")
async def list_v2_documents(
    category: str = "", search: str = "",
    skip: int = 0, limit: int = 100,
    user=Depends(get_crm_user),
):
    q = {**_of(user)}
    if category:
        q["category"] = category
    if search:
        q["original_filename"] = {"$regex": search, "$options": "i"}
    total = await db.crm2_documents.count_documents(q)
    items = await db.crm2_documents.find(q, {"_id": 0, "data_b64": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"documents": items, "total": total, "categories": DOCUMENT_CATEGORIES}


@router.post("/documents")
async def upload_v2_document(
    category: str = "general",
    notes: str = "",
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_crm_user),
):
    content = await file.read()
    b64 = base64.b64encode(content).decode("utf-8")
    doc = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "category": category,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "data_b64": b64,
        "notes": notes,
        "uploaded_by": user.get("id"),
        "uploaded_by_name": user.get("full_name", ""),
        "created_at": _now(),
    }
    await db.crm2_documents.insert_one(doc)
    return {k: v for k, v in doc.items() if k not in ("_id", "data_b64")}


@router.delete("/documents/{doc_id}")
async def delete_v2_document(doc_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_documents.delete_one({"id": doc_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404, "Document not found")
    return {"success": True}


# ═══════════════════════════════════════════
# TENDER ENGINE — Core Data Model
# ═══════════════════════════════════════════

TENDER_STATUSES = ["draft", "parsing", "in_progress", "review", "submitted", "won", "lost"]


@router.get("/tenders")
async def list_tenders(skip: int = 0, limit: int = 50, user=Depends(get_crm_user)):
    q = {**_of(user)}
    total = await db.crm2_tenders.count_documents(q)
    items = await db.crm2_tenders.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"tenders": items, "total": total}


@router.post("/tenders")
async def create_tender(data: dict, user=Depends(get_crm_user)):
    tender = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "title": data.get("title", ""),
        "type": data.get("type", "ITT"),
        "issuer": data.get("issuer", ""),
        "company_id": data.get("company_id"),
        "opportunity_id": data.get("opportunity_id"),
        "deadline": data.get("deadline"),
        "status": "draft",
        "win_probability": None,
        "total_questions": 0,
        "answered_questions": 0,
        "ai_mode": data.get("ai_mode", "assist"),
        "tone": data.get("tone", "professional"),
        "bid_owner": user.get("full_name", ""),
        "bid_owner_id": user.get("id"),
        "documents_uploaded": 0,
        "strengths": [], "weaknesses": [], "recommendations": [],
        "executive_summary": "",
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_tenders.insert_one(tender)
    return {k: v for k, v in tender.items() if k != "_id"}


@router.get("/tenders/{tender_id}")
async def get_tender(tender_id: str, user=Depends(get_crm_user)):
    t = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Tender not found")
    questions = await db.crm2_tender_questions.find(
        {"tender_id": tender_id, **_of(user)}, {"_id": 0}
    ).sort("order", 1).to_list(200)
    t["questions"] = questions
    docs = await db.crm2_tender_docs.find(
        {"tender_id": tender_id, **_of(user)}, {"_id": 0, "data_b64": 0}
    ).to_list(50)
    t["tender_documents"] = docs
    return t


@router.put("/tenders/{tender_id}")
async def update_tender(tender_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Tender not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    updates["updated_at"] = _now()
    await db.crm2_tenders.update_one({"id": tender_id}, {"$set": updates})
    return {"success": True}


@router.delete("/tenders/{tender_id}")
async def delete_tender(tender_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_tenders.delete_one({"id": tender_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404)
    await db.crm2_tender_questions.delete_many({"tender_id": tender_id})
    await db.crm2_tender_docs.delete_many({"tender_id": tender_id})
    return {"success": True}


# Tender Documents
@router.post("/tenders/{tender_id}/documents")
async def upload_tender_doc(
    tender_id: str,
    category: str = "tender_pack",
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_crm_user),
):
    content = await file.read()
    b64 = base64.b64encode(content).decode("utf-8")
    doc = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "tender_id": tender_id,
        "category": category,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "data_b64": b64,
        "uploaded_by": user.get("full_name", ""),
        "created_at": _now(),
    }
    await db.crm2_tender_docs.insert_one(doc)
    await db.crm2_tenders.update_one(
        {"id": tender_id}, {"$inc": {"documents_uploaded": 1}, "$set": {"updated_at": _now()}}
    )
    return {k: v for k, v in doc.items() if k not in ("_id", "data_b64")}


# Tender Questions
@router.post("/tenders/{tender_id}/questions")
async def add_tender_question(tender_id: str, data: dict, user=Depends(get_crm_user)):
    q_count = await db.crm2_tender_questions.count_documents({"tender_id": tender_id, **_of(user)})
    question = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "tender_id": tender_id,
        "order": q_count + 1,
        "text": data.get("text", ""),
        "category": data.get("category", "general"),
        "word_limit": data.get("word_limit"),
        "weighting": data.get("weighting"),
        "mandatory": data.get("mandatory", True),
        "complexity": data.get("complexity", "medium"),
        "status": "not_started",
        "response": "",
        "ai_draft": "",
        "ai_suggestions": [],
        "score_estimate": None,
        "assigned_to": data.get("assigned_to", ""),
        "version": 1,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_tender_questions.insert_one(question)
    await db.crm2_tenders.update_one(
        {"id": tender_id}, {"$inc": {"total_questions": 1}, "$set": {"updated_at": _now()}}
    )
    return {k: v for k, v in question.items() if k != "_id"}


@router.put("/tenders/{tender_id}/questions/{q_id}")
async def update_tender_question(tender_id: str, q_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "tender_id")}
    updates["updated_at"] = _now()
    if "response" in updates and updates.get("status") == "not_started":
        updates["status"] = "draft"
    await db.crm2_tender_questions.update_one({"id": q_id, "tender_id": tender_id}, {"$set": updates})
    # Update answered count
    answered = await db.crm2_tender_questions.count_documents(
        {"tender_id": tender_id, **_of(user), "status": {"$in": ["draft", "reviewed", "final"]}}
    )
    await db.crm2_tenders.update_one({"id": tender_id}, {"$set": {"answered_questions": answered}})
    return {"success": True}


# Knowledge Base
@router.get("/knowledge-base")
async def list_kb(category: str = "", skip: int = 0, limit: int = 100, user=Depends(get_crm_user)):
    q = {**_of(user)}
    if category:
        q["category"] = category
    total = await db.crm2_knowledge_base.count_documents(q)
    items = await db.crm2_knowledge_base.find(q, {"_id": 0, "content_b64": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"items": items, "total": total}


@router.post("/knowledge-base")
async def add_kb_item(data: dict, user=Depends(get_crm_user)):
    item = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "title": data.get("title", ""),
        "category": data.get("category", "general"),
        "tags": data.get("tags", []),
        "content": data.get("content", ""),
        "source_type": data.get("source_type", "manual"),
        "win_score": data.get("win_score"),
        "usage_count": 0,
        "uploaded_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_knowledge_base.insert_one(item)
    return {k: v for k, v in item.items() if k != "_id"}


@router.post("/knowledge-base/upload")
async def upload_kb_doc(
    category: str = "general",
    tags: str = "",
    file: UploadFile = FastAPIFile(...),
    user=Depends(get_crm_user),
):
    content = await file.read()
    b64 = base64.b64encode(content).decode("utf-8")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    item = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "title": file.filename,
        "category": category,
        "tags": tag_list,
        "content": "",
        "content_b64": b64,
        "content_type": file.content_type,
        "size": len(content),
        "source_type": "document",
        "win_score": None, "usage_count": 0,
        "uploaded_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_knowledge_base.insert_one(item)
    return {k: v for k, v in item.items() if k not in ("_id", "content_b64")}


@router.delete("/knowledge-base/{item_id}")
async def delete_kb_item(item_id: str, user=Depends(get_crm_user)):
    r = await db.crm2_knowledge_base.delete_one({"id": item_id, **_of(user)})
    if r.deleted_count == 0:
        raise HTTPException(404)
    return {"success": True}


# ═══════════════════════════════════════════
# TENDER AI — GPT-5.2 Intelligence
# ═══════════════════════════════════════════

import os
from emergentintegrations.llm.chat import LlmChat, UserMessage

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def _ai_call(system_msg, user_msg):
    """Send a message to GPT-5.2 and return the response text."""
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"tender-{_id()[:8]}",
        system_message=system_msg,
    ).with_model("openai", "gpt-5.2")
    resp = await chat.send_message(UserMessage(text=user_msg))
    return resp


@router.post("/tenders/{tender_id}/ai/parse")
async def ai_parse_tender(tender_id: str, data: dict, user=Depends(get_crm_user)):
    """AI parses tender text and extracts structured questions."""
    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")

    text = data.get("text", "")
    if not text or len(text) < 20:
        raise HTTPException(400, "Provide tender text to parse (min 20 chars)")

    system = """You are an expert Bid Director and Tender Analyst. Extract structured questions from tender documents.
Return ONLY valid JSON array. Each item must have: text, category (technical/commercial/social_value/health_safety/service_delivery/mobilisation/general), word_limit (number or null), weighting (number 1-100 or null), mandatory (boolean), complexity (low/medium/high).
Example: [{"text":"Describe your approach to...","category":"technical","word_limit":500,"weighting":15,"mandatory":true,"complexity":"high"}]"""

    prompt = f"Extract ALL questions, requirements, and evaluation criteria from this tender document. Title: {tender['title']}. Type: {tender['type']}.\n\nTENDER TEXT:\n{text[:8000]}"

    try:
        resp = await _ai_call(system, prompt)
        questions = _parse_ai_json(resp)

        created = 0
        q_count = await db.crm2_tender_questions.count_documents({"tender_id": tender_id})
        for q in questions:
            q_doc = {
                "id": _id(), "organization_id": user.get("organization_id"),
                "tender_id": tender_id,
                "order": q_count + created + 1,
                "text": q.get("text", ""),
                "category": q.get("category", "general"),
                "word_limit": q.get("word_limit"),
                "weighting": q.get("weighting"),
                "mandatory": q.get("mandatory", True),
                "complexity": q.get("complexity", "medium"),
                "status": "not_started",
                "response": "", "ai_draft": "",
                "ai_suggestions": [], "score_estimate": None,
                "assigned_to": "", "version": 1,
                "created_at": _now(), "updated_at": _now(),
            }
            await db.crm2_tender_questions.insert_one(q_doc)
            created += 1

        await db.crm2_tenders.update_one(
            {"id": tender_id},
            {"$inc": {"total_questions": created}, "$set": {"status": "in_progress", "updated_at": _now()}}
        )
        return {"parsed": created, "questions": questions}
    except Exception as e:
        return {"parsed": 0, "error": str(e), "raw_response": resp[:500] if 'resp' in dir() else ""}


def _build_tender_prompt(action: str, question: dict, kb_context: str) -> str:
    """Build the appropriate AI prompt for a tender question action."""
    q_text = question["text"]
    current = question.get("response") or question.get("ai_draft", "")
    word_limit = question.get("word_limit") or 300

    if action == "generate":
        return f"""Write a winning tender response for this question.

QUESTION: {q_text}
CATEGORY: {question.get('category', 'general')}
WORD LIMIT: {word_limit}
WEIGHTING: {question.get('weighting') or 'Unknown'}%

COMPANY KNOWLEDGE BASE:
{kb_context or 'No knowledge base entries yet.'}

Write the BEST possible response. Be specific to Pulse Fitness capabilities in gym/fitness equipment supply, installation, and maintenance."""

    if action == "rewrite_higher_score":
        return f"""Rewrite this tender response to score HIGHER marks.

QUESTION: {q_text}
CURRENT RESPONSE: {current}
WORD LIMIT: {word_limit}

Improve: Add more evidence, quantify outcomes, strengthen differentiation, address risks proactively."""

    if action == "reduce_word_count":
        return f"""Reduce this response to under {word_limit} words while keeping ALL key points.

QUESTION: {q_text}
CURRENT RESPONSE: {current}

Keep the strongest evidence and differentiators. Remove filler."""

    if action == "make_evidence_based":
        return f"""Rewrite this response to be MORE evidence-based with specific examples, case studies, and metrics.

QUESTION: {q_text}
CURRENT RESPONSE: {current}

Add quantified evidence, real-world examples, and measurable outcomes."""

    return f"Respond to: {q_text}"


@router.post("/tenders/{tender_id}/questions/{q_id}/ai/generate")
async def ai_generate_response(tender_id: str, q_id: str, data: dict, user=Depends(get_crm_user)):
    """AI generates a response for a specific tender question."""
    question = await db.crm2_tender_questions.find_one({"id": q_id, "tender_id": tender_id}, {"_id": 0})
    if not question:
        raise HTTPException(404, "Question not found")

    tender = await db.crm2_tenders.find_one({"id": tender_id}, {"_id": 0})
    tone = data.get("tone") or tender.get("tone", "professional")
    action = data.get("action", "generate")

    kb_items = await db.crm2_knowledge_base.find({**_of(user)}, {"_id": 0, "content_b64": 0}).limit(10).to_list(10)
    kb_context = "\n".join([f"- {item.get('title','')}: {item.get('content','')[:300]}" for item in kb_items if item.get("content")])

    system = f"""You are a world-class Bid Writer for Pulse Fitness, a leading gym and fitness equipment company.
Write {tone}, compelling tender responses that WIN contracts.
Structure: Direct answer first → Evidence → Differentiation → Client benefit → Risk mitigation → Summary.
Be specific, outcome-focused, and evidence-based. Never be generic."""

    prompt = _build_tender_prompt(action, question, kb_context)

    try:
        resp = await _ai_call(system, prompt)
        word_count = len(resp.split())
        await db.crm2_tender_questions.update_one({"id": q_id}, {"$set": {"ai_draft": resp, "updated_at": _now()}})
        return {"response": resp, "word_count": word_count, "action": action}
    except Exception as e:
        raise HTTPException(500, f"AI generation failed: {str(e)}")


def _build_win_strategy_prompt(tender: dict, questions: list, kb_summary: str) -> tuple:
    """Build system + user prompt for tender win strategy analysis."""
    q_summary = "\n".join([
        f"Q{q.get('order', i + 1)}: [{q.get('category', 'general')}] {q.get('text', '')[:100]} (weight: {q.get('weighting', '?')}%, {q.get('complexity', 'medium')} complexity)"
        for i, q in enumerate(questions)
    ])
    system = """You are a Senior Bid Director providing strategic tender analysis. Return ONLY valid JSON with these fields:
{
  "win_probability": number (0-100),
  "executive_summary": "string",
  "strengths": ["string array"],
  "weaknesses": ["string array"],
  "recommendations": ["string array"],
  "risk_areas": ["string array"],
  "key_differentiators": ["string array"]
}"""
    prompt = f"""Analyze this tender and provide a win strategy for Pulse Fitness (gym/fitness equipment supplier).

TENDER: {tender['title']}
TYPE: {tender['type']}
ISSUER: {tender.get('issuer', 'Unknown')}
QUESTIONS ({len(questions)}):
{q_summary or 'No questions parsed yet'}

KNOWLEDGE BASE: {kb_summary}

Provide a comprehensive win strategy assessment."""
    return system, prompt


@router.post("/tenders/{tender_id}/ai/strategy")
async def ai_win_strategy(tender_id: str, user=Depends(get_crm_user)):
    """AI generates win strategy analysis for the entire tender."""
    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")

    questions = await db.crm2_tender_questions.find({"tender_id": tender_id, **_of(user)}, {"_id": 0}).to_list(200)
    kb_items = await db.crm2_knowledge_base.find({**_of(user)}, {"_id": 0, "content_b64": 0}).limit(15).to_list(15)
    kb_summary = ", ".join([item.get("title", "") for item in kb_items]) or "No knowledge base"

    system, prompt = _build_win_strategy_prompt(tender, questions, kb_summary)

    try:
        strategy = _parse_ai_json(await _ai_call(system, prompt))
        await db.crm2_tenders.update_one(
            {"id": tender_id},
            {"$set": {
                "win_probability": strategy.get("win_probability"),
                "executive_summary": strategy.get("executive_summary", ""),
                "strengths": strategy.get("strengths", []),
                "weaknesses": strategy.get("weaknesses", []),
                "recommendations": strategy.get("recommendations", []),
                "updated_at": _now(),
            }}
        )
        return strategy
    except Exception as e:
        return {"error": str(e), "win_probability": None}


# ═══════════════════════════════════════════
# CPQ — Approval Workflow + Digital Signature
# ═══════════════════════════════════════════

@router.post("/quotes/{quote_id}/submit-approval")
async def submit_quote_for_approval(quote_id: str, user=Depends(get_crm_user)):
    q = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)})
    if not q:
        raise HTTPException(404, "Quote not found")
    await db.crm2_quotes.update_one(
        {"id": quote_id},
        {"$set": {"status": "pending_approval", "submitted_by": user.get("full_name", ""), "submitted_at": _now(), "updated_at": _now()}}
    )
    await db.crm2_notifications.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "approval", "title": "Quote Awaiting Approval",
        "message": f"Quote {q.get('quote_number', '')} submitted for approval by {user.get('full_name', '')}",
        "entity_type": "quote", "entity_id": quote_id,
        "read": False, "created_at": _now(),
    })
    return {"success": True, "status": "pending_approval"}


@router.post("/quotes/{quote_id}/approve")
async def approve_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    q = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)})
    if not q:
        raise HTTPException(404, "Quote not found")
    action = data.get("action", "approve")
    if action == "approve":
        await db.crm2_quotes.update_one(
            {"id": quote_id},
            {"$set": {"status": "approved", "approved_by": user.get("full_name", ""), "approved_at": _now(), "updated_at": _now()}}
        )
    elif action == "reject":
        await db.crm2_quotes.update_one(
            {"id": quote_id},
            {"$set": {"status": "rejected", "rejected_by": user.get("full_name", ""), "rejected_reason": data.get("reason", ""), "rejected_at": _now(), "updated_at": _now()}}
        )
    return {"success": True, "status": "approved" if action == "approve" else "rejected"}


@router.post("/quotes/{quote_id}/sign")
async def sign_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Store a digital signature for a quote (base64 PNG from canvas)."""
    q = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)})
    if not q:
        raise HTTPException(404, "Quote not found")
    signature_b64 = data.get("signature", "")
    signer_name = data.get("signer_name", user.get("full_name", ""))
    if not signature_b64:
        raise HTTPException(400, "Signature data required")
    await db.crm2_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "signature": signature_b64,
            "signer_name": signer_name,
            "signed_at": _now(),
            "status": "accepted",
            "updated_at": _now(),
        }}
    )
    return {"success": True, "status": "accepted", "signer": signer_name}


# ═══════════════════════════════════════════
# AUTO COMPANY RECOGNITION (AI-powered lookup)
# ═══════════════════════════════════════════

def _smart_case(text: str) -> str:
    """Convert ALL CAPS text to proper title case, handling common suffixes."""
    if not text or not text.isupper():
        return text
    small_words = {'and', 'of', 'the', 'in', 'on', 'at', 'for', 'to', 'a', 'an'}
    abbrevs = {'LTD', 'PLC', 'LLP', 'UK', 'CIC', 'LLC'}
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if w.upper() in abbrevs:
            result.append(w.upper())
        elif i > 0 and w.lower() in small_words:
            result.append(w.lower())
        else:
            result.append(w.capitalize())
    return ' '.join(result)


def _parse_ai_json(resp: str):
    """Extract JSON from an AI response that may contain markdown fences."""
    json_str = resp.strip()
    if json_str.startswith("```"):
        json_str = json_str.split("```")[1]
        if json_str.startswith("json"):
            json_str = json_str[4:]
    return json.loads(json_str)


def _clean_ch_address_parts(raw: str) -> list:
    """Strip HTML tags and split into clean trimmed parts (country tokens removed).

    Iter 215ep — kept only for legacy address-string parsing in non-CH
    contexts (none currently). The Companies House lookup itself no
    longer scrapes HTML; see `_lookup_via_ch_api` below.
    """
    raw = re.sub(r'<br\s*/?>', ', ', raw)
    raw = re.sub(r'<[^>]+>', '', raw).strip()
    countries = ('united kingdom', 'england', 'uk', 'wales', 'scotland')
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    return [a for a in parts if a.lower() not in countries]


# Iter 215ep — replaced HTML scraping with the official Companies House
# REST API via `utils.companies_house_client`. Single shared cache /
# rate-limit pool with the master-admin onboarding wizard. The old
# scrape-and-regex code path was deleted entirely (~120 lines) — see
# `routes/companies_house.py` for the master-admin proxy that exposes
# the same client to the wizard.
from utils.companies_house_client import (
    CompaniesHouseError,
    is_enabled as _ch_is_enabled,
    search as _ch_search,
    profile as _ch_profile,
    officers as _ch_officers,
)


async def _lookup_via_ch_api(query: str) -> dict:
    """Look up a company on the official Companies House REST API.

    Returns the same shape the legacy `_scrape_companies_house` returned
    so the rest of `auto_recognize_company` (AI enrichment + response
    contract) didn't have to change. Returns the placeholder shape when
    the API key is unset or the lookup yields no hit — the caller falls
    back to AI-only enrichment in that case.
    """
    info = {
        "name": query, "company_number": "", "address": "", "city": "", "postcode": "",
        "status": "", "industry": "", "directors": [], "key_contacts": [],
    }
    if not _ch_is_enabled():
        return info

    try:
        items = await _ch_search(query, limit=1)
    except CompaniesHouseError:
        return info
    if not items:
        return info

    top = items[0]
    info["name"] = top.get("company_name") or query
    info["company_number"] = top.get("company_number") or ""

    # Profile call: structured registered-office address.
    try:
        prof = await _ch_profile(info["company_number"])
        info["status"] = prof.get("company_status") or ""
        # Compose `address` exactly the way the legacy scraper did so
        # downstream consumers (the AI enrichment prompt + the CRM
        # account drawer) keep working unchanged.
        addr_parts = [prof.get("address_line1") or "", prof.get("address_line2") or "", prof.get("address_line3") or ""]
        info["address"] = ", ".join(p for p in addr_parts if p)
        info["city"] = prof.get("city") or ""
        info["postcode"] = prof.get("postcode") or ""
        # SIC codes — first one becomes the industry hint for the AI
        # prompt downstream (the AI is welcome to override it).
        sics = prof.get("sic_codes") or []
        if sics:
            info["industry"] = sics[0]
        # Iter 215ep — pass the structured address through too so the
        # CRM account form can drop it straight into AddressFields
        # without needing a re-parse.
        info["address_line1"] = prof.get("address_line1") or ""
        info["address_line2"] = prof.get("address_line2") or ""
        info["address_line3"] = prof.get("address_line3") or ""
        info["county"] = prof.get("county") or ""
        info["country"] = prof.get("country") or "United Kingdom"
        info["company_type"] = prof.get("company_type") or ""
        info["date_of_creation"] = prof.get("date_of_creation") or ""
    except CompaniesHouseError:
        # Profile call failed (e.g. 404 on a delisted record) — keep
        # the search-list shape we already have.
        pass

    # Officers — directors only by default, formatted as plain names
    # for the legacy `directors[]` field plus richer dicts on
    # `key_contacts[]` for the CRM contact-import workflow.
    try:
        officers = await _ch_officers(info["company_number"])
    except CompaniesHouseError:
        officers = []
    info["directors"] = [o["name"] for o in officers if o.get("name")]
    info["key_contacts"] = [
        {"name": o["name"], "title": o.get("role") or "Director"}
        for o in officers if o.get("name")
    ]
    return info


async def _ai_enrich_company(company_info: dict) -> dict:
    """Use AI to fill in website, phone, and description."""
    if not LLM_KEY:
        return company_info
    try:
        system = """Return ONLY valid JSON: {"industry":"string","website":"url or empty","phone":"string or empty","description":"Brief 1-2 sentence description"}. Only include info you're confident about."""
        addr = f"{company_info.get('address','')}, {company_info.get('city','')}, {company_info.get('postcode','')}"
        prompt = f"Company: {company_info['name']}, UK company #{company_info.get('company_number','')}, Address: {addr}, Directors: {', '.join(company_info.get('directors',[])[:3])}. What is their website, phone, and what do they do?"
        enriched = _parse_ai_json(await _ai_call(system, prompt))
        company_info["industry"] = enriched.get("industry", company_info.get("industry", ""))
        company_info["website"] = enriched.get("website", "")
        company_info["phone"] = enriched.get("phone", "")
        company_info["description"] = enriched.get("description", "")
    except Exception:
        pass
    return company_info


@router.post("/companies/auto-recognize")
async def auto_recognize_company(data: dict, user=Depends(get_crm_user)):
    """Look up company details using Companies House + AI enrichment.

    Iter 215ep — switched from public-website HTML scraping to the
    official Companies House REST API via `utils.companies_house_client`.
    Same response shape (the legacy frontend keeps working) plus a few
    new structured fields the new CRM account drawer can consume:
    `address_line1/2/3`, `city`, `county`, `postcode`, `country`,
    `company_type`, `date_of_creation`.
    """
    query = data.get("query", "").strip()
    if not query or len(query) < 3:
        raise HTTPException(400, "Provide at least 3 characters")

    company_info = {"name": query, "address": "", "phone": "", "website": "",
                    "industry": "", "directors": [], "key_contacts": [],
                    "description": "", "company_number": "", "status": "",
                    "incorporated": "", "registered_address": ""}

    try:
        looked_up = await _lookup_via_ch_api(query)
        company_info.update(looked_up)
    except Exception:
        pass

    company_info = await _ai_enrich_company(company_info)

    has_data = bool(company_info.get("company_number") or company_info.get("address") or company_info.get("directors"))
    return {"success": has_data, "company_info": company_info, "query": query, "source": "companies_house" if has_data else "ai_only"}


# ═══════════════════════════════════════════
# DOCUMENT VIEWING (inline preview)
# ═══════════════════════════════════════════

@router.get("/documents/{doc_id}/view")
async def view_v2_document(doc_id: str, user=Depends(get_crm_user)):
    """Return document data for inline viewing."""
    doc = await db.crm2_documents.find_one({"id": doc_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    from fastapi.responses import Response
    data = base64.b64decode(doc.get("data_b64", ""))
    return Response(
        content=data,
        media_type=doc.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{doc.get("original_filename", "file")}"'},
    )


@router.get("/documents/{doc_id}/meta")
async def get_doc_meta(doc_id: str, user=Depends(get_crm_user)):
    """Return document metadata including uploader info for permission checks."""
    doc = await db.crm2_documents.find_one({"id": doc_id, **_of(user)}, {"_id": 0, "data_b64": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc
