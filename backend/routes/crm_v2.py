"""
CRM v2 — Core Data Model & Activity Engine
All CRM entities with full cross-linking and org-scoped queries.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from utils.security_plus import safe_regex, safe_regex_exact
from datetime import datetime, timezone
from pydantic import BaseModel
from utils.database import db
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit
from utils.web_security import sanitize_rich_text, sanitize_rich_text_dict
from utils.audit_log import audit_export
from routes.crm_permissions import compute_visibility, redact
from routes.crm_product_perms import redact_quote_cost
from utils.site_scope import effective_site_filter, get_requested_site, resolve_stamp_site_id
from utils.sites_isolation import get_primary_site_id
import uuid
import re
import json
import logging

# Iter 220bs — strict picklist enforcement at CRUD boundaries.
from routes.crm_picklists import validate_picklist_fields

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm/v2", tags=["CRM v2"])


def _of(user: dict) -> dict:
    """Org-scoped + site-scoped filter. Returns impossible match if no org.

    Merges the per-request site filter (X-Site-Id → RBAC) so a restricted
    manager only reads their assigned site(s) on this v2 read path too."""
    org_id = user.get("organization_id")
    if not org_id:
        return {"organization_id": "__NONE__"}
    return {"organization_id": org_id, **effective_site_filter()}


async def _v2_stamp_site(user: dict) -> str | None:
    return resolve_stamp_site_id(get_requested_site(), await get_primary_site_id(user.get("organization_id")))


# Platform-org names that must NEVER bleed into tenant-facing PDFs.
# When the logged-in user's organization happens to be the platform
# itself ("Pulse Fitness AI"), tender PDFs would otherwise read "A pitch
# from Pulse Fitness AI for X" — instead, fall back to the CRM tenant brand
# (currently always Pulse Fitness).
_PLATFORM_ORG_NAMES = {"gymaxis ai", "gymaxis", "gymaxis ltd", "gymaxis limited"}


async def _resolve_crm_brand(user: dict) -> dict:
    """Resolve the company brand used on tender PDFs / pitch decks.

    Priority for company name:
      1. `org.theme_overrides.tender_company_name` (Master-Admin set,
         per-tenant — Iter 216h107)
      2. `org.branding.company_name` (legacy operator override)
      3. `org.name` if it's a real tenant (not the platform org)
      4. "Pulse Fitness" — CRM is Pulse-only today

    Primary colour and logo URL also accept tender-specific overrides
    from `theme_overrides` so a future second CRM tenant can ship a
    fully branded pitch deck without code changes.
    """
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "name": 1, "branding": 1, "theme_overrides": 1},
    ) or {}
    overrides = org.get("theme_overrides") or {}
    branding = org.get("branding") or {}
    tender_company = (overrides.get("tender_company_name") or "").strip()
    legacy_company = (branding.get("company_name") or "").strip()
    raw_name = (org.get("name") or "").strip()
    if tender_company:
        company = tender_company
    elif legacy_company:
        company = legacy_company
    elif raw_name and raw_name.lower() not in _PLATFORM_ORG_NAMES:
        company = raw_name
    else:
        company = "Pulse Fitness"
    primary_color = (
        (overrides.get("tender_primary_color") or "").strip()
        or branding.get("primary_color")
        or "#19CDFF"
    )
    logo_url = (
        (overrides.get("tender_logo_url") or "").strip()
        or branding.get("logo_url")
        or None
    )
    return {
        "company_name": company,
        "primary_color": primary_color,
        "logo_url": logo_url,
    }


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


async def _maybe_regional_activity_scope(user: dict, kwargs: dict):
    """For the GLOBAL appointments/calendar view (no specific entity
    filter), restrict regional staff to activities in their area — i.e.
    linked to a company in one of their assigned territories, or owned by
    them. Returns an extra query fragment, or None to leave unchanged.

    Safe by design: admins/owners and any user with no assigned territory
    are unaffected, and record-scoped reads (company_id/contact_id/etc.)
    are never double-filtered.
    """
    if any(kwargs.get(f) for f in ("company_id", "contact_id", "opportunity_id", "case_id", "asset_id")):
        return None
    from routes.crm_permissions import is_unrestricted
    if is_unrestricted(user):
        return None
    from routes.crm_territories import covered_territory_ids
    tids = await covered_territory_ids(user)
    if not tids:
        return None  # not regional staff → behaviour unchanged
    org = user.get("organization_id")
    comp_ids = [c["id"] async for c in db.crm2_companies.find(
        {"organization_id": org, "territory_id": {"$in": tids}}, {"_id": 0, "id": 1})]
    return {"$or": [{"company_id": {"$in": comp_ids}}, {"owner_id": user.get("id")}]}


@router.get("/activities")
async def list_activities(
    filters: ActivityFilters = Depends(),
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_crm_user),
):
    """List activities filtered by any linked entity."""
    q = _build_activity_filter(user, **filters.dict())
    regional = await _maybe_regional_activity_scope(user, filters.dict())
    if regional:
        q = {"$and": [q, regional]}
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
    # Iter 220av · F-04 — scrub stored rich text through the bleach
    # allow-list so any future render (timeline UI, tender PDF, email
    # digest) can't be used to ship XSS.
    sanitize_rich_text_dict(activity, fields=("subject", "body"))
    await db.crm2_activities.insert_one(activity)
    return {k: v for k, v in activity.items() if k != "_id"}


@router.put("/activities/{activity_id}")
async def update_activity(activity_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_activities.find_one({"id": activity_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Activity not found")
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    # Iter 220av · F-04 — same scrub on every update.
    sanitize_rich_text_dict(updates, fields=("subject", "body"))
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
            {"name": safe_regex(search)},
            {"sector": safe_regex(search)},
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
        "site_id": await _v2_stamp_site(user),
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
    # Iter 216h265 — auto-link Companies House directors as stub
    # contacts on the new company. Customer feedback: directors were
    # scraped onto the company row but never appeared in the Contacts
    # tab. We create a contact stub per director with influence_type
    # "decision_maker" (Miller Heiman) and source "companies_house"
    # so they can be tagged later without bypassing the email-required
    # rule (we pass force_no_email since Companies House doesn't
    # publish director emails).
    try:
        await _seed_director_contacts(company, user)
    except Exception:
        logger.exception("[crm.companies] director seeding failed")
    await evaluate_workflows("company_created", company, user.get("organization_id"), user.get("full_name", ""))
    return {k: v for k, v in company.items() if k != "_id"}


async def _seed_director_contacts(company: dict, user: dict) -> int:
    """Create one stub contact per director scraped from Companies House.

    Returns the number of contacts created. Idempotent on
    (organization × company × full_name) so calling twice doesn't
    duplicate. Directors with no name are skipped. Emails are left
    blank — the strict email-required rule is bypassed because we
    have a verifiable source (Companies House) and the manager will
    fill the email in later.
    """
    directors = company.get("directors") or []
    if not directors:
        return 0
    org_id = user.get("organization_id")
    created = 0
    for raw in directors:
        # Accept either plain strings or {name, role} dicts.
        if isinstance(raw, dict):
            full_name = (raw.get("name") or "").strip()
            director_role = (raw.get("role") or raw.get("officer_role") or "Director").strip() or "Director"
        else:
            full_name = str(raw).strip()
            director_role = "Director"
        if not full_name:
            continue
        parts = full_name.split()
        first = parts[0]
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        existing = await db.crm2_contacts.find_one(
            {
                "organization_id": org_id,
                "company_id": company["id"],
                "first_name": first,
                "last_name": last,
            },
            {"_id": 0, "id": 1},
        )
        if existing:
            continue
        contact_doc = {
            "id": _id(),
            "organization_id": org_id,
            "first_name": first,
            "last_name": last,
            "email": "",
            "phone": "",
            "mobile": "",
            "job_title": director_role,
            "company_id": company["id"],
            "company_name": company.get("name", ""),
            "influence_types": ["decision_maker"],
            "is_decision_maker": True,
            "is_champion": False,
            "linkedin": "",
            "source": "companies_house",
            "status": "active",
            "tags": ["director", "auto-imported"],
            "lifecycle": "lead",
            "gdpr_consent": False,
            "gdpr_consent_date": None,
            "opt_out_email": True,
            "opt_out_sms": True,
            "opt_out_phone": True,
            "opt_out_post": True,
            "opt_out_marketing": True,
            "opt_out_updated_at": _now(),
            "communication_preferences": {},
            "relationship_score": 0,
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "notes": "Auto-created from Companies House director list.",
            "territory_id": company.get("territory_id"),
            "postcode": company.get("postcode", ""),
            "county": company.get("county", ""),
            "region": company.get("region", ""),
            "country": company.get("country", "United Kingdom"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.crm2_contacts.insert_one(contact_doc)
        created += 1
    return created


@router.post("/companies/{company_id}/seed-directors")
async def seed_directors_endpoint(company_id: str, user=Depends(get_crm_user)):
    """Manually re-run the director → contact seeding for an existing
    company (e.g. after the user re-pulls the Companies House data).
    """
    company = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    created = await _seed_director_contacts(company, user)
    return {"ok": True, "created": created, "directors_on_file": len(company.get("directors") or [])}


@router.get("/companies/{company_id}")
async def get_company(company_id: str, user=Depends(get_crm_user)):
    c = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Company not found")
    # Enrich with linked data
    of = _of(user)
    c["contacts"] = await db.crm2_contacts.find({"company_id": company_id, "gdpr_erased": {"$ne": True}, **of}, {"_id": 0}).to_list(100)
    c["opportunities"] = await db.crm2_opportunities.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["quotes"] = await db.crm2_quotes.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["cases"] = await db.crm2_cases.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    c["assets"] = await db.crm2_assets.find({"company_id": company_id, **of}, {"_id": 0}).to_list(100)
    c["contracts"] = await db.crm2_contracts.find({"company_id": company_id, **of}, {"_id": 0}).to_list(50)
    c["activities"] = await db.crm2_activities.find({"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    # Iter 220an — deep-linking: surface tenders raised against this company
    # so the 360° view shows every revenue stream (deals + tenders + quotes).
    c["tenders"] = await db.crm2_tenders.find(
        {"company_id": company_id, **of},
        {"_id": 0, "id": 1, "title": 1, "type": 1, "status": 1, "issuer": 1,
         "deadline": 1, "opportunity_id": 1, "total_questions": 1,
         "answered_questions": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(50)
    # Revenue summary
    won_opps = await db.crm2_opportunities.find({"company_id": company_id, "stage": "closed_won", **of}, {"_id": 0, "value": 1}).to_list(500)
    c["total_revenue"] = sum(o.get("value", 0) for o in won_opps)
    c["open_pipeline"] = sum(o.get("value", 0) for o in c["opportunities"] if o.get("stage") not in ("closed_won", "closed_lost"))
    # Iter 291 — only surface the "Service & Engineers" tab when this org
    # actually uses Service Ops (has engineers or service cases). Keeps the
    # CRM clean for customers who don't run the Service Desk.
    _org = c.get("organization_id")
    c["has_service_ops"] = bool(
        await db.svc_engineers.find_one({"organization_id": _org}, {"_id": 1})
        or await db.svc_cases.find_one({"organization_id": _org}, {"_id": 1}))
    return c


@router.get("/companies/{company_id}/portal-invite")
async def company_portal_invite(company_id: str, user=Depends(get_crm_user)):
    """Pulse customer portal onboarding status for the CRM company record."""
    c = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Company not found")
    from routes.pulse_onboarding import compute_invite_status
    status = await compute_invite_status(c)
    return status


@router.post("/companies/{company_id}/portal-invite/resend")
async def company_portal_invite_resend(company_id: str, user=Depends(get_crm_user)):
    """Resend (or provision) the customer's Pulse portal set-up invite.
    Owners/managers only."""
    role = (user.get("role") or "").lower()
    if not (role in ("owner", "manager") or user.get("is_org_owner") or user.get("is_master_admin")):
        raise HTTPException(403, "Only owners or managers can resend the portal invite")
    c = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(404, "Company not found")
    from routes.pulse_onboarding import resend_portal_invite
    return await resend_portal_invite(company_id, owner_email=user.get("email"))


@router.get("/companies/{company_id}/service-activity")
async def company_service_activity(company_id: str, user=Depends(get_crm_user)):
    """Consolidated Service Desk view for a CRM account — so a sales
    manager sees live service operations and *where engineers are* without
    leaving the CRM. Reads the linked Service Ops collections by canonical
    ``company_id`` (with a name fallback) so the two halves of the Pulse
    team work as one. Org-scoped; never duplicates data."""
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    company = await db.crm2_companies.find_one(
        {"id": company_id, "organization_id": org}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")

    from utils.svc_state import OPEN_STATES, TERMINAL_STATES
    name = (company.get("name") or "").strip()
    or_clause = [{"company_id": company_id}]
    if name:
        or_clause.append({"customer_name": safe_regex_exact(name)})

    fields = {
        "_id": 0, "id": 1, "reference": 1, "title": 1, "status": 1, "priority": 1,
        "case_type": 1, "site_name": 1, "site_postcode": 1, "scheduled_at": 1,
        "assigned_engineer_id": 1, "assigned_engineer_name": 1, "company_id": 1,
        "created_at": 1, "updated_at": 1, "closed_at": 1,
    }
    cases = await db.svc_cases.find(
        {"organization_id": org, "$or": or_clause}, fields
    ).sort("updated_at", -1).to_list(200)

    open_cases = [c for c in cases if c.get("status") in OPEN_STATES]
    closed_cases = [c for c in cases if c.get("status") in TERMINAL_STATES]

    # Engineers active on this account + where each one is right now.
    eng_ids = sorted({c.get("assigned_engineer_id") for c in open_cases if c.get("assigned_engineer_id")})
    engineers = []
    for eid in eng_ids:
        eng = await db.svc_engineers.find_one(
            {"organization_id": org, "id": eid},
            {"_id": 0, "full_name": 1, "name": 1, "phone": 1, "status": 1, "on_site": 1, "en_route": 1})
        loc = await db.svc_engineer_locations.find_one(
            {"engineer_id": eid}, {"_id": 0, "lat": 1, "lng": 1, "recorded_at": 1, "case_id": 1})
        eng_cases = [c for c in open_cases if c.get("assigned_engineer_id") == eid]
        current = next((c for c in eng_cases if c.get("status") in ("en_route", "on_site")),
                       eng_cases[0] if eng_cases else None)
        eng = eng or {}
        cur_status = (current or {}).get("status")
        status = eng.get("status") or ("on_site" if cur_status == "on_site" else "en_route" if cur_status == "en_route" else "assigned")
        engineers.append({
            "id": eid,
            "name": eng.get("full_name") or eng.get("name") or (current or {}).get("assigned_engineer_name") or "Engineer",
            "phone": eng.get("phone"),
            "status": status,
            "on_site": bool(eng.get("on_site")) or cur_status == "on_site",
            "en_route": bool(eng.get("en_route")) or cur_status == "en_route",
            "open_case_count": len(eng_cases),
            "current_case": ({
                "id": current["id"], "reference": current.get("reference"),
                "title": current.get("title"), "site_name": current.get("site_name"),
                "site_postcode": current.get("site_postcode"),
                "scheduled_at": current.get("scheduled_at"), "status": current.get("status"),
            } if current else None),
            "last_location": ({
                "lat": loc.get("lat"), "lng": loc.get("lng"), "recorded_at": loc.get("recorded_at"),
            } if loc else None),
        })

    ppm_or = [{"company_id": company_id}]
    if name:
        ppm_or.append({"customer_name": safe_regex_exact(name)})
    next_ppm = await db.svc_ppm_schedules.find_one(
        {"organization_id": org, "active": True, "$or": ppm_or},
        {"_id": 0, "next_due_date": 1, "visits_per_year": 1, "tier": 1, "interval_days": 1},
        sort=[("next_due_date", 1)])

    last = closed_cases[0] if closed_cases else None
    linked = any(c.get("company_id") == company_id for c in cases) or bool(
        await db.svc_engineer_customers.find_one(
            {"organization_id": org, "company_id": company_id}, {"_id": 1}))

    return {
        "linked": linked,
        "company_id": company_id,
        "total_cases": len(cases),
        "open_case_count": len(open_cases),
        "open_cases": open_cases[:50],
        "engineers": engineers,
        "next_ppm": next_ppm,
        "last_visit": ({
            "reference": last.get("reference"), "title": last.get("title"),
            "site_name": last.get("site_name"),
            "closed_at": last.get("closed_at") or last.get("updated_at"),
            "engineer_name": last.get("assigned_engineer_name"),
        } if last else None),
    }


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
    # Iter 220ao++ — Exclude GDPR-erased contacts from list responses so
    # operators don't see rows of "[REDACTED] [REDACTED]". The row still
    # exists (preserves linked deals/quotes/activities) but is hidden
    # from CRM surfaces.
    q["gdpr_erased"] = {"$ne": True}
    if search:
        q["$or"] = [
            {"first_name": safe_regex(search)},
            {"last_name": safe_regex(search)},
            {"email": safe_regex(search)},
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
    # Iter 220bs — strict picklist enforcement for contact metadata.
    await validate_picklist_fields(data, {
        "job_title": "job_title",
        "department": "department",
        "contact_role": "contact_role",
    }, user.get("organization_id"))
    # Iter 216h223 — tighten email validation + stakeholder mapping.
    # Email is required by default; the `force=true` query/body flag
    # (master-admin only) keeps the legacy importer paths working for
    # contacts where the email genuinely isn't known yet.
    email = (data.get("email") or "").strip().lower()
    force_no_email = bool(data.get("force_no_email")) and (
        user.get("is_master_admin") or user.get("is_pulse_admin")
    )
    if not email and not force_no_email:
        raise HTTPException(
            422,
            "An email address is required for contact creation. Master admins can pass "
            "`force_no_email: true` to bypass for legacy imports.",
        )
    if email:
        # Cheap, RFC-friendly check. Heavier DNS/MX validation lives at
        # the marketing-engine layer where the cost of a wrong send is high.
        import re as _re
        if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(422, "Invalid email address")
        # Duplicate-email guard (within the same org). Soft 409 so the
        # importer can decide whether to merge or skip.
        dup = await db.crm2_contacts.find_one(
            {"organization_id": user.get("organization_id"), "email": email},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1},
        )
        if dup and not data.get("allow_duplicate_email"):
            raise HTTPException(
                409,
                f"A contact with email '{email}' already exists "
                f"(id={dup['id']}, {dup.get('first_name','')} {dup.get('last_name','')}). "
                "Pass `allow_duplicate_email: true` to override.",
            )

    # Iter 216h223 — Miller Heiman stakeholder tags. We accept either
    # the new `influence_types: []` array OR the legacy booleans (or
    # both — booleans win when explicitly set).
    raw_types = data.get("influence_types") or []
    if isinstance(raw_types, list):
        from routes.crm_stakeholders import _validate_types, _derive_legacy_booleans
        influence_types = _validate_types(raw_types)
    else:
        influence_types = []
    legacy = _derive_legacy_booleans(influence_types)

    # Iter 216h270 — Strategic Selling extension fields. Stored
    # alongside the contact so a Blue Sheet review can read them
    # without a second collection.
    from routes.crm_stakeholders import _validate_miller_heiman
    mh = _validate_miller_heiman(data)

    contact = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "site_id": await _v2_stamp_site(user),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "email": email,
        "phone": data.get("phone", ""),
        "mobile": data.get("mobile", ""),
        "job_title": data.get("job_title", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        # Multi-tag stakeholder field (Miller Heiman + ops roles).
        "influence_types": influence_types,
        # Legacy booleans — kept in sync from the multi-tag field but
        # also overridable when callers pass them explicitly.
        "is_decision_maker": data.get("is_decision_maker", legacy["is_decision_maker"]),
        "is_champion": data.get("is_champion", legacy["is_champion"]),
        # Iter 216h270 — Miller Heiman scoring fields (Blue Sheet).
        "buying_influence_level": mh.get("buying_influence_level"),
        "adoption_sentiment": mh.get("adoption_sentiment"),
        "coverage_confidence": mh.get("coverage_confidence"),
        "reports_to_id": mh.get("reports_to_id"),
        "personal_wins": mh.get("personal_wins", ""),
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
    # Iter 216h270 — hydrate the `reports_to` link so the Strategic
    # Selling panel can show "Reports to: Jane Doe (CFO)" without a
    # second round-trip.
    if c.get("reports_to_id"):
        boss = await db.crm2_contacts.find_one(
            {"id": c["reports_to_id"], **of},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "job_title": 1, "email": 1},
        )
        c["reports_to"] = boss
    return c


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_contacts.find_one({"id": contact_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Contact not found")
    # Iter 220bs — strict picklist enforcement (same fields as create).
    await validate_picklist_fields(data, {
        "job_title": "job_title",
        "department": "department",
        "contact_role": "contact_role",
    }, user.get("organization_id"))
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


@router.get("/tags")
async def list_crm_tags(user=Depends(get_crm_user)):
    """Aggregated tag vocabulary used by the workflow builder + tag
    autocomplete. Iter 216h195 — distinct tag values across contacts,
    companies, and deals so operators can pick from what they've
    already typed rather than coining "VIP" / "vip" / "Vip" copies.
    """
    org_filter = await compute_visibility(user, "contact")
    org_filter.pop("$or", None)  # don't drag the user-visibility OR clause; tags are public

    pipelines = [
        ("crm2_contacts", {"_id": 0, "tags": 1}),
        ("crm2_companies", {"_id": 0, "tags": 1}),
        ("crm2_opportunities", {"_id": 0, "tags": 1}),
    ]
    seen: dict[str, int] = {}
    for coll_name, proj in pipelines:
        coll = getattr(db, coll_name)
        async for doc in coll.find(org_filter, proj).limit(5000):
            for t in (doc.get("tags") or []):
                if not t:
                    continue
                key = str(t).strip()
                if not key:
                    continue
                seen[key] = seen.get(key, 0) + 1
    tags = [{"name": k, "count": v} for k, v in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0].lower()))]
    return {"tags": tags, "total": len(tags)}


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
    # Iter 216h265 — surface attached quotes on each opp so the pipeline
    # UI can show "£X quoted" inline. Customer feedback: quotes they
    # created weren't appearing in the Sales Pipeline view.
    opp_ids = [o["id"] for o in items if o.get("id")]
    if opp_ids:
        quotes_by_opp: dict[str, list[dict]] = {}
        cur = db.crm2_quotes.find(
            {"organization_id": user.get("organization_id"),
             "opportunity_id": {"$in": opp_ids}},
            {"_id": 0, "id": 1, "quote_number": 1, "status": 1,
             "total": 1, "currency": 1, "opportunity_id": 1, "created_at": 1,
             "approval_required": 1, "approval_status": 1},
        ).sort("created_at", -1)
        async for q_doc in cur:
            quotes_by_opp.setdefault(q_doc["opportunity_id"], []).append(q_doc)
        for opp in items:
            attached = quotes_by_opp.get(opp.get("id"), [])
            opp["quotes"] = attached
            opp["quote_count"] = len(attached)
            opp["quoted_value"] = sum(float(q.get("total") or 0) for q in attached)
    return {"opportunities": items, "total": total}


@router.post("/opportunities")
async def create_opportunity(data: dict, user=Depends(get_crm_user)):
    # Iter 220bs — strict picklist enforcement. Normalises casing and
    # rejects values not in the org's picklist with a 400 listing the
    # valid options.
    await validate_picklist_fields(data, {
        "lead_source": "lead_source",
        "opportunity_type": "opportunity_type",
        "lost_reason": "lost_reason",
    }, user.get("organization_id"))
    stage = data.get("stage", "lead")
    stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == stage), OPPORTUNITY_STAGES[0])
    opp = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "site_id": await _v2_stamp_site(user),
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
    # Iter 220bs — strict picklist enforcement (same fields as create).
    await validate_picklist_fields(data, {
        "lead_source": "lead_source",
        "opportunity_type": "opportunity_type",
        "lost_reason": "lost_reason",
    }, user.get("organization_id"))
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
    # Iter 220an — deep-linking: surface tenders raised under this deal.
    o["tenders"] = await db.crm2_tenders.find(
        {"opportunity_id": opp_id, **of},
        {"_id": 0, "id": 1, "title": 1, "type": 1, "status": 1, "issuer": 1,
         "deadline": 1, "total_questions": 1, "answered_questions": 1,
         "created_at": 1},
    ).sort("created_at", -1).to_list(20)
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
# UNIFIED TIMELINE — Iter 220bu
# Merges activities + quotes + cases + tender events into a single
# chronological feed, scoped to any one of company / opportunity /
# tender. Powers the "360° view" timeline panel in the CRM UI.
# ═══════════════════════════════════════════

import asyncio as _asyncio_timeline  # noqa: E402  (local alias)


def _ts(row: dict) -> str:
    """Best-available occurrence timestamp for sorting."""
    return (
        row.get("completed_at")
        or row.get("created_at")
        or row.get("updated_at")
        or ""
    )


def _norm_activity(a: dict) -> dict:
    """Normalise an `crm2_activities` row to the timeline shape."""
    return {
        "id": f"act:{a['id']}",
        "source_collection": "crm2_activities",
        "source_id": a["id"],
        "type": f"activity:{a.get('type', 'note')}",
        "occurred_at": _ts(a),
        "subject": a.get("subject", ""),
        "body": a.get("body", ""),
        "actor": a.get("owner_name", ""),
        "icon_hint": a.get("type", "note"),
        "status_hint": "completed" if a.get("completed_at") else None,
        "deep_link": f"/crm/activities/{a['id']}",
    }


def _norm_quote(q: dict) -> dict:
    cur = q.get("currency", "GBP")
    total = q.get("total") or 0
    return {
        "id": f"qt:{q['id']}",
        "source_collection": "crm_quotes",
        "source_id": q["id"],
        "type": f"quote:{q.get('status', 'draft')}",
        "occurred_at": _ts(q),
        "subject": f"Quote {q.get('quote_number', '')} — {q.get('title', '')}".strip(" —"),
        "body": f"{cur} {total:,.0f} · status: {q.get('status', 'draft')}",
        "actor": q.get("created_by_name", ""),
        "icon_hint": "quote",
        "status_hint": q.get("status"),
        "deep_link": f"/crm/quotes/{q['id']}",
    }


def _norm_case(c: dict) -> dict:
    return {
        "id": f"case:{c['id']}",
        "source_collection": "crm2_cases",
        "source_id": c["id"],
        "type": f"case:{c.get('status', 'open')}",
        "occurred_at": _ts(c),
        "subject": f"Case {c.get('case_number', '')} — {c.get('subject', '')}".strip(" —"),
        "body": c.get("description", "")[:240] if c.get("description") else "",
        "actor": c.get("owner_name", ""),
        "icon_hint": "case",
        "status_hint": c.get("status"),
        "deep_link": f"/crm/cases/{c['id']}",
    }


def _norm_tender_event(t: dict, *, event: str) -> dict:
    """Synthesise a tender event from the tender row itself.

    Tenders don't have a dedicated event log so we emit two events per
    tender — one ``tender:created`` at ``created_at`` and one
    ``tender:status_changed`` at ``updated_at`` IF it differs from
    ``created_at`` (i.e. the row has been touched after creation).
    """
    when = t.get("created_at", "") if event == "created" else t.get("updated_at", "")
    return {
        "id": f"tend:{t['id']}:{event}",
        "source_collection": "crm2_tenders",
        "source_id": t["id"],
        "type": f"tender:{event}",
        "occurred_at": when,
        "subject": t.get("title", "") or "Untitled tender",
        "body": f"Status: {t.get('status', 'draft')}",
        "actor": t.get("bid_owner", "") or t.get("created_by", ""),
        "icon_hint": "tender",
        "status_hint": t.get("status"),
        "deep_link": f"/crm/tenders/{t['id']}",
    }


@router.get("/timeline")
async def unified_timeline(
    company_id: str = "",
    opportunity_id: str = "",
    tender_id: str = "",
    limit: int = 100,
    skip: int = 0,
    user=Depends(get_crm_user),
):
    """Unified chronological feed for one of the three top-level
    entities. Pass exactly one of ``company_id`` / ``opportunity_id``
    / ``tender_id``.

    The feed merges:

    * **Activities** (notes, calls, emails, meetings, tasks, system
      events) from ``crm2_activities``.
    * **Quotes** (any status, sorted by created_at) from
      ``crm_quotes``.
    * **Cases** (opened against the company) from ``crm2_cases`` —
      only when scoped by company.
    * **Tender events** (``created`` + ``status_changed`` synthetic
      events) from ``crm2_tenders``.

    All rows are org-scoped via ``_of(user)`` so cross-tenant access
    is impossible. Results are sorted by ``occurred_at`` descending
    and paginated via ``limit`` / ``skip``.
    """
    scopes = [bool(company_id), bool(opportunity_id), bool(tender_id)]
    if sum(scopes) != 1:
        raise HTTPException(
            400, "Pass exactly one of company_id, opportunity_id, tender_id.",
        )
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    of = _of(user)

    # ── Validate scope belongs to the requesting org ────────────────
    if company_id:
        scope_doc = await db.crm2_companies.find_one(
            {"id": company_id, **of}, {"_id": 0, "id": 1, "name": 1},
        )
    elif opportunity_id:
        scope_doc = await db.crm2_opportunities.find_one(
            {"id": opportunity_id, **of},
            {"_id": 0, "id": 1, "title": 1, "company_id": 1},
        )
    else:
        scope_doc = await db.crm2_tenders.find_one(
            {"id": tender_id, **of},
            {"_id": 0, "id": 1, "title": 1, "company_id": 1, "opportunity_id": 1},
        )
    if not scope_doc:
        raise HTTPException(404, "Scope entity not found in this organisation")

    # ── Build per-source queries based on scope ─────────────────────
    if company_id:
        act_q = {"company_id": company_id, **of}
        quote_q = {"company_id": company_id, "organization_id": user.get("organization_id")}
        case_q = {"company_id": company_id, **of}
        tender_q = {"company_id": company_id, **of}
    elif opportunity_id:
        act_q = {"opportunity_id": opportunity_id, **of}
        # Quotes store the opportunity id on ``deal_id``.
        quote_q = {"deal_id": opportunity_id, "organization_id": user.get("organization_id")}
        case_q = None  # cases don't link directly to opportunities
        tender_q = {"opportunity_id": opportunity_id, **of}
    else:
        # tender_id scope — activities don't link directly to tenders
        # (yet); the related quotes carry the link instead.
        act_q = None
        quote_q = {"tender_id": tender_id, "organization_id": user.get("organization_id")}
        case_q = None
        # The tender events themselves come from the scope_doc.
        tender_q = {"id": tender_id, **of}

    async def _q_activities():
        if act_q is None:
            return []
        return await db.crm2_activities.find(act_q, {"_id": 0}).sort(
            "created_at", -1).limit(limit + skip).to_list(limit + skip)

    async def _q_quotes():
        return await db.crm_quotes.find(quote_q, {"_id": 0}).sort(
            "created_at", -1).limit(limit + skip).to_list(limit + skip)

    async def _q_cases():
        if case_q is None:
            return []
        return await db.crm2_cases.find(case_q, {"_id": 0}).sort(
            "created_at", -1).limit(limit + skip).to_list(limit + skip)

    async def _q_tenders():
        return await db.crm2_tenders.find(tender_q, {"_id": 0}).sort(
            "created_at", -1).limit(limit + skip).to_list(limit + skip)

    activities, quotes, cases, tenders = await _asyncio_timeline.gather(
        _q_activities(), _q_quotes(), _q_cases(), _q_tenders(),
    )

    # ── Normalise everything to the timeline shape ──────────────────
    events: list[dict] = []
    for a in activities:
        events.append(_norm_activity(a))
    for q in quotes:
        events.append(_norm_quote(q))
    for c in cases:
        events.append(_norm_case(c))
    for t in tenders:
        events.append(_norm_tender_event(t, event="created"))
        # Only emit a status_changed event if updated_at meaningfully
        # differs from created_at (avoids dupes for never-touched tenders).
        upd = t.get("updated_at") or ""
        crt = t.get("created_at") or ""
        if upd and upd != crt:
            events.append(_norm_tender_event(t, event="status_changed"))

    # ── Sort + paginate ─────────────────────────────────────────────
    events.sort(key=lambda e: e["occurred_at"], reverse=True)
    total = len(events)
    page = events[skip:skip + limit]

    return {
        "scope": {
            "type": "company" if company_id else ("opportunity" if opportunity_id else "tender"),
            "id": company_id or opportunity_id or tender_id,
            "label": (scope_doc.get("name") or scope_doc.get("title", "")),
        },
        "events": page,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


# ═══════════════════════════════════════════
# SERVICE REVENUE YTD — Iter 216h152
# Aggregates `crm2_activities` of type "service_invoice" emitted by
# the Service Ops billing flow (see utils/svc_crm_sync.py). Keeps the
# join one-way: CRM reads SVC, SVC does not import CRM.
# ═══════════════════════════════════════════

@router.get("/service-revenue/ytd")
async def service_revenue_ytd(
    company_id: str = "", user=Depends(get_crm_user),
):
    """Year-to-date service invoice revenue.

    Returns a top-line `total_net` (£) plus per-month split and the
    top-5 companies by service spend YTD. When `company_id` is set the
    response is scoped to that company (drives the company drawer
    tile).
    """
    of = _of(user)
    year_start = datetime(
        datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc,
    ).isoformat()
    q = {
        **of,
        "type": "service_invoice",
        "created_at": {"$gte": year_start},
    }
    if company_id:
        q["company_id"] = company_id
    # Pull just the metadata we need; service_invoice volume is low
    # (hundreds per org per year), no need for a Mongo $group pipeline.
    rows = await db.crm2_activities.find(
        q,
        {"_id": 0, "company_id": 1, "created_at": 1, "metadata": 1,
         "case_id": 1, "subject": 1},
    ).to_list(5000)
    total_net = 0.0
    per_month: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    per_company: dict[str, float] = {}
    case_count = 0
    for r in rows:
        meta = r.get("metadata") or {}
        amt = float(meta.get("amount_net") or 0)
        if amt <= 0:
            continue
        total_net += amt
        case_count += 1
        # Bucket by month from ISO created_at.
        try:
            m = int(r["created_at"][5:7])
            per_month[m] = per_month.get(m, 0.0) + amt
        except (KeyError, ValueError, TypeError):
            pass
        cid = r.get("company_id") or ""
        if cid:
            per_company[cid] = per_company.get(cid, 0.0) + amt
    # Resolve top-5 company names (single batched read).
    top_ids = sorted(per_company, key=per_company.get, reverse=True)[:5]
    name_map: dict[str, str] = {}
    if top_ids:
        async for c in db.crm2_companies.find(
            {**of, "id": {"$in": top_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            name_map[c["id"]] = c.get("name") or "(unnamed)"
    top_companies = [
        {"company_id": cid,
         "name": name_map.get(cid, "(deleted)"),
         "revenue_net": round(per_company[cid], 2)}
        for cid in top_ids
    ]
    return {
        "year": datetime.now(timezone.utc).year,
        "total_net": round(total_net, 2),
        "invoice_count": case_count,
        "currency": "GBP",
        "per_month": [
            {"month": m, "revenue_net": round(per_month[m], 2)}
            for m in range(1, 13)
        ],
        "top_companies": top_companies,
        "scope": "company" if company_id else "organization",
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
    # Iter 220bs — strict picklist enforcement for case taxonomy.
    await validate_picklist_fields(data, {
        "case_type": "case_type",
    }, user.get("organization_id"))
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
        "equipment_id": data.get("equipment_id"),
        "sicon_equipment_id": data.get("sicon_equipment_id"),
        "source": "register" if data.get("equipment_id") else "crm",
        "status": data.get("status", "active"),
        "install_date": data.get("install_date"),
        "warranty_expiry": data.get("warranty_expiry"),
        "contract_id": data.get("contract_id"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_assets.insert_one(asset)
    return {k: v for k, v in asset.items() if k != "_id"}


@router.get("/contacts/{contact_id}/member-identity")
async def contact_member_identity(contact_id: str, user=Depends(get_crm_user)):
    """Person-identity link — is this CRM contact also a gym member?

    Matches db.members (the Memberships module) by canonical email, then
    exact phone, within the org. Read-only: surfaces the unified person so
    the CRM and Memberships stay one identity rather than duplicating."""
    of = _of(user)
    contact = await db.crm2_contacts.find_one(
        {"id": contact_id, **of}, {"_id": 0, "email": 1, "phone": 1})
    if not contact:
        raise HTTPException(404, "Contact not found")
    org = user.get("organization_id")
    email = (contact.get("email") or "").strip().lower()
    phone = (contact.get("phone") or "").strip()

    proj = {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "name": 1,
            "status": 1, "plan_id": 1, "site_id": 1, "joined_at": 1, "email": 1}
    match, via = None, None
    if email:
        match = await db.members.find_one({"organization_id": org, "email": email}, proj)
        if match:
            via = "email"
    if not match and phone:
        match = await db.members.find_one({"organization_id": org, "phone": phone}, proj)
        if match:
            via = "phone"
    if not match:
        return {"is_member": False}

    plan = await db.membership_plans.find_one({"id": match.get("plan_id")}, {"_id": 0, "name": 1}) if match.get("plan_id") else None
    site = await db.sites.find_one({"id": match.get("site_id")}, {"_id": 0, "name": 1}) if match.get("site_id") else None
    name = (f"{match.get('first_name', '')} {match.get('last_name', '')}").strip() or match.get("name")
    return {
        "is_member": True,
        "matched_via": via,
        "member": {
            "id": match.get("id"),
            "name": name,
            "status": match.get("status"),
            "plan": (plan or {}).get("name"),
            "site": (site or {}).get("name"),
            "joined_at": match.get("joined_at"),
            "email": match.get("email"),
        },
    }


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
    items = await redact_quote_cost(user, items)
    return {"quotes": items, "total": total}


@router.get("/quotes/compare")
async def compare_quotes(company_id: str = "", user=Depends(get_crm_user)):
    """Like-for-like comparison of a customer's quotes.

    Returns one row per distinct item — matched on **manufacturer + model**
    (resolved via each line's product) — with the net unit price quoted in
    every quote, plus latest-vs-previous deltas, so a rep can see how a
    customer's pricing has moved across quotes.
    """
    if not company_id:
        raise HTTPException(400, "company_id is required")
    quotes = await db.crm2_quotes.find(
        {"company_id": company_id, **_of(user)}, {"_id": 0},
    ).sort("created_at", 1).to_list(500)

    pids = {ln.get("product_id") for q in quotes for ln in (q.get("lines") or []) if ln.get("product_id")}
    prod_map: dict = {}
    if pids:
        async for p in db.crm_products.find(
            {"id": {"$in": list(pids)}, **_of(user)},
            {"_id": 0, "id": 1, "manufacturer": 1, "model": 1, "name": 1, "sku": 1},
        ):
            prod_map[p["id"]] = p

    def _key_label(ln: dict):
        p = prod_map.get(ln.get("product_id")) or {}
        mfr = (p.get("manufacturer") or "").strip()
        model = (p.get("model") or "").strip()
        if mfr or model:
            label = f"{mfr} {model}".strip()
        else:  # fall back to the line description / product name / sku
            label = (ln.get("description") or p.get("name") or ln.get("sku") or "Unspecified").strip()
        return label.lower(), label, mfr, model, (ln.get("sku") or p.get("sku") or "")

    quote_meta = []
    items_map: dict = {}
    for q in quotes:
        quote_meta.append({
            "quote_id": q["id"],
            "quote_number": q.get("quote_number", ""),
            "title": q.get("title", ""),
            "status": q.get("status", ""),
            "created_at": q.get("created_at", ""),
            "currency": q.get("currency", "GBP"),
            "total": q.get("total", 0),
        })
        for ln in (q.get("lines") or []):
            key, label, mfr, model, sku = _key_label(ln)
            unit = float(ln.get("unit_price", 0) or 0)
            qty = float(ln.get("quantity", 0) or 0)
            disc = float(ln.get("discount", 0) or 0)
            net = round(unit * (1 - disc / 100), 2)
            it = items_map.setdefault(key, {
                "key": key, "label": label, "manufacturer": mfr, "model": model,
                "sku": sku, "prices": {},
            })
            it["prices"][q["id"]] = {"unit_price": round(unit, 2), "net_price": net, "quantity": qty, "discount": disc}

    rows = []
    for it in items_map.values():
        prices = it["prices"]
        nets = [v["net_price"] for v in prices.values() if v["net_price"] > 0]
        ordered_qids = [qm["quote_id"] for qm in quote_meta if qm["quote_id"] in prices]
        latest_qid = ordered_qids[-1] if ordered_qids else None
        prev_qid = ordered_qids[-2] if len(ordered_qids) > 1 else None
        latest = prices.get(latest_qid, {}).get("net_price") if latest_qid else None
        prev = prices.get(prev_qid, {}).get("net_price") if prev_qid else None
        delta = round(latest - prev, 2) if (latest is not None and prev is not None) else None
        delta_pct = round(delta / prev * 100, 1) if (delta is not None and prev) else None
        rows.append({
            "key": it["key"], "label": it["label"], "manufacturer": it["manufacturer"],
            "model": it["model"], "sku": it["sku"],
            "appears_in": len(prices), "prices": prices,
            "min": min(nets) if nets else None, "max": max(nets) if nets else None,
            "latest": latest, "previous": prev, "delta": delta, "delta_pct": delta_pct,
        })
    rows.sort(key=lambda r: (-r["appears_in"], r["label"].lower()))

    company = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0, "name": 1})
    return {
        "company_id": company_id,
        "company_name": (company or {}).get("name", ""),
        "quotes": quote_meta,
        "items": rows,
        "compared_count": sum(1 for r in rows if r["appears_in"] > 1),
    }


@router.post("/quotes")
async def create_quote(data: dict, user=Depends(get_crm_user)):
    from routes.crm_quote_sage import hydrate_quote_lines
    from utils.localization import org_localization
    lines = await hydrate_quote_lines(data.get("lines", []), user)
    subtotal = sum(float(line.get("quantity", 0)) * float(line.get("unit_price", 0)) * (1 - float(line.get("discount", 0) or 0) / 100) for line in lines)
    # Iter 220p1 — tax rate follows the org market when not supplied
    # (0% US, 20% GB); currency/tax label snapshotted onto the quote.
    _org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "country_code": 1, "currency": 1, "timezone": 1},
    )
    loc = org_localization(_org)
    vat_rate = float(data["vat_rate"]) if data.get("vat_rate") is not None else float(loc["default_tax_rate"])
    vat = subtotal * vat_rate / 100
    # Resolve company and contact names
    company_name = ""
    contact_name = ""
    if data.get("company_id"):
        co = await db.crm2_companies.find_one({"id": data["company_id"], **_of(user)}, {"_id": 0, "name": 1})
        company_name = (co or {}).get("name", "")
    if data.get("contact_id"):
        ct = await db.crm2_contacts.find_one({"id": data["contact_id"], **_of(user)}, {"_id": 0, "first_name": 1, "last_name": 1})
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
        "tax_rate": vat_rate,  # PDF reads `tax_rate`; keep in sync with vat_rate
        "total": round(subtotal + vat, 2),
        # Iter 220p1 — localization snapshot (frozen at creation).
        "currency": loc["currency"], "tax_label": loc["tax_label"],
        "country_code": loc["country_code"],
        "valid_until": data.get("valid_until", ""),
        "notes": data.get("notes", ""),
        "version": 1,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_quotes.insert_one(quote)
    # Iter 216h265 — workflow tightening. When a quote is created on
    # an opportunity, auto-advance the opp to at least "proposal" (so
    # the pipeline view always reflects reality). Contact lifecycle
    # gets nudged lead → prospect since they've now received a quote.
    if data.get("opportunity_id"):
        opp = await db.crm2_opportunities.find_one(
            {"id": data["opportunity_id"], **_of(user)}, {"_id": 0}
        )
        if opp and opp.get("stage") in (None, "", "lead", "qualified", "discovery", "solution"):
            stage_info = next((s for s in OPPORTUNITY_STAGES if s["id"] == "proposal"), None)
            if stage_info:
                await db.crm2_opportunities.update_one(
                    {"id": opp["id"]},
                    {"$set": {
                        "stage": "proposal",
                        "probability": stage_info["probability"],
                        "stage_entered_at": _now(),
                        "updated_at": _now(),
                    }, "$push": {
                        "stage_history": {"stage": "proposal", "entered_at": _now(),
                                          "by": user.get("full_name", ""),
                                          "reason": "Quote created"},
                    }},
                )
    if data.get("contact_id"):
        await db.crm2_contacts.update_one(
            {"id": data["contact_id"], **_of(user), "lifecycle": "lead"},
            {"$set": {"lifecycle": "prospect", "updated_at": _now()}},
        )
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
    from routes.crm_quote_sage import hydrate_quote_lines
    lines = await hydrate_quote_lines(data.get("lines", original.get("lines", [])), user)
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
    regex = safe_regex(q)
    results = []

    # Companies
    companies = await db.crm2_companies.find({**of, "name": regex}, {"_id": 0, "id": 1, "name": 1}).limit(5).to_list(5)
    for c in companies:
        results.append({"type": "company", "id": c["id"], "label": c["name"]})

    # Contacts
    contacts = await db.crm2_contacts.find({**of, "gdpr_erased": {"$ne": True}, "$or": [{"first_name": regex}, {"last_name": regex}, {"email": regex}]}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).limit(5).to_list(5)
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
        {"site_name": safe_regex(company_name)},
        {"location": safe_regex(company_name)},
        {"site": safe_regex(company_name)},
        {"organization_name": safe_regex(company_name)},
        {"gym_name": safe_regex(company_name)},
        {"company": safe_regex(company_name)},
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
    "general", "contract", "proposal", "invoice", "other",
    "certificates", "processes",
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
        q["original_filename"] = safe_regex(search)
    total = await db.crm2_documents.count_documents(q)
    items = await db.crm2_documents.find(q, {"_id": 0, "data_b64": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"documents": items, "total": total, "categories": DOCUMENT_CATEGORIES}


@router.get("/documents-expiring-count")
async def documents_expiring_count(user=Depends(get_crm_user)):
    """Iter 284b — count certificates that are expired or within 30 days of
    expiry, so the CRM Documents tab can surface an 'expiring soon' badge.
    expiry_date is stored as an ISO YYYY-MM-DD string → lexical compare works."""
    from datetime import date, timedelta
    cutoff = (date.today() + timedelta(days=30)).isoformat()
    count = await db.crm2_documents.count_documents({
        **_of(user),
        "category": "certificates",
        "expiry_date": {"$ne": None, "$lte": cutoff},
    })
    return {"expiring_soon": count}


@router.post("/documents")
async def upload_v2_document(
    category: str = "general",
    notes: str = "",
    expiry_date: str = "",
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
        # Iter 284 — optional expiry (mainly for Certificates) so staff can see
        # at a glance which certificates are near/past expiry and replace them.
        "expiry_date": (expiry_date or "").strip() or None,
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
    # Iter 220an — deep-linking: hydrate each tender row with the linked
    # company + opportunity names so the list grid can render clickable
    # badges without N+1 round-trips from the frontend.
    of = _of(user)
    co_ids = {t["company_id"] for t in items if t.get("company_id")}
    opp_ids = {t["opportunity_id"] for t in items if t.get("opportunity_id")}
    co_map: dict = {}
    opp_map: dict = {}
    if co_ids:
        async for co in db.crm2_companies.find(
            {"id": {"$in": list(co_ids)}, **of},
            {"_id": 0, "id": 1, "name": 1},
        ):
            co_map[co["id"]] = co["name"]
    if opp_ids:
        async for op in db.crm2_opportunities.find(
            {"id": {"$in": list(opp_ids)}, **of},
            {"_id": 0, "id": 1, "title": 1, "stage": 1},
        ):
            opp_map[op["id"]] = {"title": op["title"], "stage": op.get("stage")}
    for t in items:
        if t.get("company_id") and t["company_id"] in co_map:
            t["company_name"] = co_map[t["company_id"]]
        if t.get("opportunity_id") and t["opportunity_id"] in opp_map:
            t["opportunity_title"] = opp_map[t["opportunity_id"]]["title"]
            t["opportunity_stage"] = opp_map[t["opportunity_id"]]["stage"]
    return {"tenders": items, "total": total}


@router.post("/tenders")
async def create_tender(data: dict, user=Depends(get_crm_user)):
    # Iter 220an — deep-linking: validate company + opportunity belong to
    # the same org before persisting, so we can never silently leak across
    # tenants.
    of = _of(user)
    # Iter 220bs — strict picklist enforcement for tender taxonomy.
    await validate_picklist_fields(data, {
        "status": "tender_status",
        "outcome_reason": "tender_outcome_reason",
    }, user.get("organization_id"))
    if data.get("company_id"):
        co = await db.crm2_companies.find_one(
            {"id": data["company_id"], **of}, {"_id": 0, "id": 1},
        )
        if not co:
            raise HTTPException(400, "Linked company not found in this organisation")
    if data.get("opportunity_id"):
        op = await db.crm2_opportunities.find_one(
            {"id": data["opportunity_id"], **of},
            {"_id": 0, "id": 1, "company_id": 1},
        )
        if not op:
            raise HTTPException(400, "Linked opportunity not found in this organisation")
        if data.get("company_id") and op.get("company_id") and op["company_id"] != data["company_id"]:
            raise HTTPException(400, "Opportunity does not belong to the linked company")
        # Auto-link the company from the opportunity for convenience.
        if not data.get("company_id") and op.get("company_id"):
            data["company_id"] = op["company_id"]
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
    # Iter 220av · F-04 — scrub stored rich text before persist.
    sanitize_rich_text_dict(tender, fields=("title", "issuer", "executive_summary"))
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
    # Iter 220an — deep-linking: enrich with company + opportunity stubs so
    # the UI can render clickable badges without a second round-trip.
    of = _of(user)
    if t.get("company_id"):
        t["company"] = await db.crm2_companies.find_one(
            {"id": t["company_id"], **of},
            {"_id": 0, "id": 1, "name": 1, "sector": 1, "website": 1},
        )
    if t.get("opportunity_id"):
        t["opportunity"] = await db.crm2_opportunities.find_one(
            {"id": t["opportunity_id"], **of},
            {"_id": 0, "id": 1, "title": 1, "stage": 1, "value": 1,
             "close_date": 1, "company_id": 1},
        )
    # Iter 220bs — Tender ↔ Quote deep-linking: surface every quote
    # that names this tender as its source so the bid team can see
    # commercial responses against the spec in one screen. Org-scoped
    # so a crafted tender_id can never pull a sibling tenant's quotes.
    quote_cur = db.crm_quotes.find(
        {"tender_id": tender_id, "organization_id": user.get("organization_id")},
        {"_id": 0, "id": 1, "quote_number": 1, "title": 1, "status": 1,
         "total": 1, "currency": 1, "version": 1, "is_latest_version": 1,
         "created_at": 1},
    ).sort("created_at", -1)
    t["quotes"] = await quote_cur.to_list(50)
    return t


@router.put("/tenders/{tender_id}")
async def update_tender(tender_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Tender not found")
    # Iter 220bs — strict picklist enforcement on update too.
    await validate_picklist_fields(data, {
        "status": "tender_status",
        "outcome_reason": "tender_outcome_reason",
    }, user.get("organization_id"))
    # Iter 220an — deep-linking: when re-pointing a tender to a different
    # company / opportunity we must enforce same-org ownership so a tender
    # can't be silently leaked to another tenant via a crafted PUT.
    of = _of(user)
    if "company_id" in data and data["company_id"]:
        co = await db.crm2_companies.find_one(
            {"id": data["company_id"], **of}, {"_id": 0, "id": 1},
        )
        if not co:
            raise HTTPException(400, "Linked company not found in this organisation")
    if "opportunity_id" in data and data["opportunity_id"]:
        op = await db.crm2_opportunities.find_one(
            {"id": data["opportunity_id"], **of}, {"_id": 0, "id": 1, "company_id": 1},
        )
        if not op:
            raise HTTPException(400, "Linked opportunity not found in this organisation")
        # If we have a company_id (either incoming or already on the tender)
        # we expect the opportunity to belong to it; otherwise auto-link.
        target_company = data.get("company_id") or existing.get("company_id")
        if target_company and op.get("company_id") and op["company_id"] != target_company:
            raise HTTPException(400, "Opportunity does not belong to the linked company")
        if not target_company and op.get("company_id"):
            data["company_id"] = op["company_id"]
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "created_at")}
    # Iter 220av · F-04 — scrub stored rich text on tender update too.
    sanitize_rich_text_dict(updates, fields=("title", "issuer", "executive_summary"))
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
    # Iter 216h101 — extract searchable text up front so the AI parse +
    # RAG generation surfaces can read what was uploaded without us
    # storing yet-another column elsewhere.
    from utils.document_extractor import extract_text
    extracted = extract_text(file.filename or "", file.content_type or "", content)
    doc = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "tender_id": tender_id,
        "category": category,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "data_b64": b64,
        "extracted_text": extracted,
        "extracted_chars": len(extracted),
        "uploaded_by": user.get("full_name", ""),
        "created_at": _now(),
    }
    await db.crm2_tender_docs.insert_one(doc)
    await db.crm2_tenders.update_one(
        {"id": tender_id}, {"$inc": {"documents_uploaded": 1}, "$set": {"updated_at": _now()}}
    )
    return {k: v for k, v in doc.items() if k not in ("_id", "data_b64", "extracted_text")}


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
    # Iter 220av · F-04 — scrub stored tender question text.
    sanitize_rich_text_dict(question, fields=("text",))
    await db.crm2_tender_questions.insert_one(question)
    await db.crm2_tenders.update_one(
        {"id": tender_id}, {"$inc": {"total_questions": 1}, "$set": {"updated_at": _now()}}
    )
    return {k: v for k, v in question.items() if k != "_id"}


@router.put("/tenders/{tender_id}/questions/{q_id}")
async def update_tender_question(tender_id: str, q_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k not in ("id", "organization_id", "tender_id")}
    # Iter 220av · F-04 — scrub user-supplied rich text on every update
    # (operators sometimes paste in formatted HTML from Word).
    sanitize_rich_text_dict(updates, fields=("text", "response", "ai_draft"))
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
    # Iter 216h101 — extract text up front so this snippet is usable
    # by the RAG retrieval inside ai_generate_response.
    from utils.document_extractor import extract_text
    extracted = extract_text(file.filename or "", file.content_type or "", content)
    item = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "title": file.filename,
        "category": category,
        "tags": tag_list,
        "content": extracted or "",
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
# emergentintegrations (litellm) imported lazily inside functions to keep it off the startup import path

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def _ai_call(system_msg, user_msg, model_pref: str = "gpt"):
    """Send a message to the configured LLM and return the response text.

    Iter 216h101 — model_pref:
      * ``"gpt"``    → GPT-5.2 (default, used for parsing / strategy /
                       JSON output where structured response matters).
      * ``"claude"`` → Claude Sonnet 4.5 (used for response writing
                       where rich, persuasive prose matters more than
                       strict JSON).
    Both use the Emergent universal key via the same emergentintegrations
    interface.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"tender-{_id()[:8]}",
        system_message=system_msg,
    )
    if model_pref == "claude":
        chat = chat.with_model("anthropic", "claude-sonnet-4-5")
    else:
        chat = chat.with_model("openai", "gpt-5.2")
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



@router.post("/tenders/{tender_id}/ai/parse-from-doc")
async def ai_parse_from_doc(tender_id: str, data: dict, user=Depends(get_crm_user)):
    """Iter 216h101 — parse questions directly from a previously uploaded tender doc."""
    doc_id = (data or {}).get("doc_id")
    if not doc_id:
        raise HTTPException(400, "doc_id is required")
    doc = await db.crm2_tender_docs.find_one(
        {"id": doc_id, "tender_id": tender_id, **_of(user)}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Tender document not found")
    text = (doc.get("extracted_text") or "").strip()
    if len(text) < 40:
        raise HTTPException(
            422,
            "Could not extract usable text from this document — likely scanned/image-only. Paste the questions manually or upload a text-searchable copy.",
        )
    return await ai_parse_tender(tender_id, {"text": text}, user)


@router.post("/tenders/{tender_id}/questions/{q_id}/ai/suggest-snippets")
async def ai_suggest_snippets(tender_id: str, q_id: str, user=Depends(get_crm_user)):
    """Return the 3 most relevant bid-library snippets for a question."""
    question = await db.crm2_tender_questions.find_one(
        {"id": q_id, "tender_id": tender_id}, {"_id": 0},
    )
    if not question:
        raise HTTPException(404, "Question not found")
    kb_items = await db.crm2_knowledge_base.find(
        {**_of(user)}, {"_id": 0, "content_b64": 0},
    ).limit(50).to_list(50)
    from utils.document_extractor import chunk_text, retrieve_relevant
    candidates: list[dict] = []
    for item in kb_items:
        body = (item.get("content") or "").strip()
        if not body:
            continue
        for ch_idx, ch in enumerate(chunk_text(body)):
            candidates.append({
                "kb_id": item.get("id"),
                "title": item.get("title", ""),
                "category": item.get("category", ""),
                "chunk_index": ch_idx,
                "text": ch,
            })
    top = retrieve_relevant(question.get("text", ""), candidates, top_k=3)
    return {"suggestions": top, "candidate_count": len(candidates)}


@router.get("/tenders/{tender_id}/export/submission")
@audit_export("tender.submission.pdf", resource_kwarg="tender_id")
async def export_submission_pdf(tender_id: str, user=Depends(get_crm_user)):
    """Generate the formal tender submission PDF."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from utils.tender_pdf_exporter import build_submission_pdf

    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")
    questions = await db.crm2_tender_questions.find(
        {"tender_id": tender_id, **_of(user)}, {"_id": 0},
    ).sort("order", 1).to_list(500)
    brand = await _resolve_crm_brand(user)
    pdf = build_submission_pdf(tender, questions, brand)
    safe = (tender.get("title") or "tender-submission").replace(" ", "_")[:60]
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-submission.pdf"'},
    )


@router.get("/tenders/{tender_id}/export/pitch")
@audit_export("tender.pitch.pdf", resource_kwarg="tender_id")
async def export_pitch_pdf(tender_id: str, user=Depends(get_crm_user)):
    """Generate the 8-slide pitch deck PDF."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from utils.tender_pdf_exporter import build_pitch_deck_pdf

    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")
    brand = await _resolve_crm_brand(user)
    pdf = build_pitch_deck_pdf(tender, brand)
    safe = (tender.get("title") or "tender-pitch").replace(" ", "_")[:60]
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-pitch.pdf"'},
    )


_PULSE_BID_LIBRARY_SEEDS = [
    {"title": "Company Overview — Pulse Fitness", "category": "company", "tags": ["overview"], "win_score": 90,
     "content": "Pulse Fitness has been designing, supplying and maintaining commercial gym and leisure facilities across the UK for over 30 years. We work with local authority leisure trusts, education, hotels, MOD, prisons and corporate wellness clients — handling everything from initial floor design through manufacture, installation, training and lifetime servicing. Directly-employed engineers, UK-stocked parts, and a 4-hour critical-response SLA mean our clients see uptime north of 99% across multi-site rollouts."},
    {"title": "ISO 9001 Quality Management", "category": "accreditation", "tags": ["iso", "quality"], "win_score": 95,
     "content": "Pulse Fitness operates a fully certified ISO 9001:2015 Quality Management System covering design, manufacture, supply, installation, and after-sales service of commercial fitness equipment. The certificate is independently audited annually by BSI and is supplied with every tender response. Internal NCR rates have run below 0.4% across the last three audit cycles."},
    {"title": "ISO 14001 Environmental Management", "category": "accreditation", "tags": ["iso", "environment"], "win_score": 90,
     "content": "Pulse Fitness is ISO 14001:2015 certified for environmental management. Our manufacturing facilities operate a closed-loop steel & aluminium recycling programme that recovers 94% of off-cuts. Carbon emissions have fallen 38% since 2019 against a Science-Based Target Initiative aligned reduction plan. Equipment is shipped in returnable steel frames to eliminate single-use packaging."},
    {"title": "Health & Safety Policy", "category": "health_safety", "tags": ["hse", "compliance"], "win_score": 88,
     "content": "All Pulse Fitness engineers operate to a CHAS Premium Plus accredited Health & Safety Management System. RAMS are issued for every site visit and countersigned on arrival. Engineers carry IPAF & PASMA tickets where powered access is involved. Zero RIDDOR-reportable incidents in the last 36 months. Annual independent audit by SafeContractor (Achilles) — score: 98/100."},
    {"title": "Case Study — Local Authority Leisure Trust (12 sites)", "category": "case_study", "tags": ["leisure-trust", "multi-site"], "win_score": 92,
     "content": "A north-of-England leisure trust (12 sites, 2,400 pieces of equipment) appointed Pulse Fitness in 2022 under a 5-year framework. Outcomes by year 2: first-time fix rate 98.7%, average response time 2h 14m, member NPS up from 31 to 58. Quarterly business reviews aligned the trust's capex schedule with our manufacturing slots, reducing site disruption windows by 41%."},
    {"title": "Mobilisation Plan Template", "category": "mobilisation", "tags": ["delivery", "implementation"], "win_score": 85,
     "content": "Standard 90-day mobilisation: Week 1-2 contract sign-off + RAMS + site surveys. Week 3-6 equipment manufactured, delivered, installed (max 2 sites/week). Week 7-10 commissioning, staff training (CPD-accredited), member orientation with on-site coach for the first opening weekend. Week 11-12 service handover, BAU reporting templates configured in the client portal, first quarterly review scheduled."},
    {"title": "Service Desk SLA & Response Times", "category": "service", "tags": ["sla", "support"], "win_score": 89,
     "content": "Pulse Fitness Service Desk operates 7am-7pm Mon-Sat with a 24/7 emergency line for safety-critical incidents. Standard SLAs (calendar hours): P1 critical 4h on-site, P2 high 24h, P3 medium 72h, P4 routine 5 working days. Average first-call resolution: 41%. Performance is reported monthly via the Pulse Fitness Service Desk client portal with raw data exportable to CSV."},
    {"title": "Sustainability & Circular Economy", "category": "sustainability", "tags": ["esg", "carbon"], "win_score": 87,
     "content": "Pulse Fitness offers a take-back & refurbishment programme: redundant equipment is collected free of charge at end-of-life and either refurbished for the resale market or stripped to component level for recycling. Less than 3% of equipment by mass goes to landfill. The programme has prevented 412 tonnes of steel from secondary smelting since 2019 — equivalent to ~620 tCO2e of avoided emissions."},
    {"title": "Social Value Commitments", "category": "social_value", "tags": ["toms", "community"], "win_score": 86,
     "content": "Pulse Fitness offers tendered Social Value commitments aligned to the TOMs framework: apprenticeship roles created (target: 1 per £250k contract value), ring-fenced local sub-contractor spend (target: 35% within 30-mile radius), school equipment donation programme (recurring quarterly), and free community open days at every installed site for the first 12 months."},
    {"title": "Account Management & Reporting Cadence", "category": "service", "tags": ["account", "kpi"], "win_score": 84,
     "content": "Each client is assigned a named Account Director plus a Technical Service Lead. Monthly KPI reports cover uptime, first-time fix rate, parts consumption, engineer attendance times, and outstanding warranty claims — delivered via the Pulse Fitness client portal and a PDF executive summary. Quarterly business reviews are held in-person and include a forward-look capacity plan for the next 12 months."},
]


@router.post("/knowledge-base/seed-pulse-defaults")
async def seed_bid_library_defaults(user=Depends(get_crm_user)):
    """Idempotent one-shot seed of pre-approved Pulse Fitness bid-library snippets."""
    org_id = user.get("organization_id")
    seeded = 0
    skipped = 0
    for entry in _PULSE_BID_LIBRARY_SEEDS:
        exists = await db.crm2_knowledge_base.find_one(
            {"organization_id": org_id, "title": entry["title"]},
            {"_id": 0, "id": 1},
        )
        if exists:
            skipped += 1
            continue
        await db.crm2_knowledge_base.insert_one({
            "id": _id(), "organization_id": org_id,
            "title": entry["title"],
            "category": entry["category"],
            "tags": entry.get("tags", []),
            "content": entry["content"],
            "source_type": "seed_pulse_default",
            "win_score": entry.get("win_score"),
            "usage_count": 0,
            "uploaded_by": "system",
            "created_at": _now(), "updated_at": _now(),
        })
        seeded += 1
    return {"seeded": seeded, "skipped": skipped}



# ── Iter 216h102 — Tender Engine v3 ────────────────────────────────────


# Vision OCR fallback for scanned PDF tender packs.
@router.post("/tenders/{tender_id}/documents/{doc_id}/ocr")
async def ocr_tender_doc(tender_id: str, doc_id: str, user=Depends(get_crm_user)):
    """Re-extract text from a tender doc using a vision-capable LLM.

    Used when ``extract_text`` returned <40 chars (typically scanned
    PDFs). Sends the original PDF/image bytes to GPT-5.2 via the
    Emergent universal key and persists the resulting text back on
    the document record.
    """
    doc = await db.crm2_tender_docs.find_one({"id": doc_id, "tender_id": tender_id, **_of(user)})
    if not doc:
        raise HTTPException(404, "Tender document not found")
    if not doc.get("data_b64"):
        raise HTTPException(422, "No file bytes available for this document")

    from emergentintegrations.llm.chat import FileContent, LlmChat, UserMessage
    fc = FileContent(content_type=(doc.get("content_type") or "application/pdf"), file_content_base64=doc["data_b64"])
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"ocr-{_id()[:8]}",
        system_message=(
            "You are a high-accuracy document OCR engine. Extract ALL "
            "human-readable text from the attached file verbatim. "
            "Preserve question numbering, bullets, and section headings. "
            "Output the text only — no commentary."
        ),
    ).with_model("openai", "gpt-5.2")
    try:
        text = await chat.send_message(UserMessage(text="Extract the full text content of this document.", file_contents=[fc]))
    except Exception as e:
        raise HTTPException(502, f"Vision OCR failed: {e}")

    text = (text or "").strip()
    await db.crm2_tender_docs.update_one(
        {"id": doc_id},
        {"$set": {
            "extracted_text": text,
            "extracted_chars": len(text),
            "ocr_applied_at": _now(),
            "ocr_applied_by": user.get("full_name", ""),
        }},
    )
    return {"ok": True, "extracted_chars": len(text)}


# Pitch deck slide management with drag-and-drop reorder.

class PitchSlideIn(BaseModel):
    kicker: str | None = None
    title: str
    subtitle: str | None = None
    bullets: list[str] | None = None
    body: str | None = None


@router.get("/tenders/{tender_id}/pitch-slides")
async def get_pitch_slides(tender_id: str, user=Depends(get_crm_user)):
    """Return the persisted slide overrides, or the default Pulse deck."""
    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")
    slides = tender.get("pitch_slides")
    if slides:
        return {"slides": slides, "source": "custom"}
    from utils.tender_pdf_exporter import _default_pitch_slides
    brand = await _resolve_crm_brand(user)
    return {
        "slides": _default_pitch_slides(tender, brand["company_name"]),
        "source": "default",
    }


@router.put("/tenders/{tender_id}/pitch-slides")
async def set_pitch_slides(tender_id: str, payload: list[PitchSlideIn], user=Depends(get_crm_user)):
    """Persist the operator-edited slide list (after drag-and-drop)."""
    if not payload:
        raise HTTPException(400, "At least one slide is required")
    if len(payload) > 24:
        raise HTTPException(400, "Maximum 24 slides per pitch deck")
    slides = [s.model_dump(exclude_none=True) for s in payload]
    result = await db.crm2_tenders.update_one(
        {"id": tender_id, **_of(user)},
        {"$set": {"pitch_slides": slides, "updated_at": _now()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Tender not found")
    return {"ok": True, "slide_count": len(slides)}


# Replace the previous export_pitch_pdf so it honours stored slides.
@router.get("/tenders/{tender_id}/export/pitch-v2")
async def export_pitch_pdf_v2(tender_id: str, user=Depends(get_crm_user)):
    """Iter 216h102 — pitch deck export using the persisted slide list."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from utils.tender_pdf_exporter import build_pitch_deck_pdf

    tender = await db.crm2_tenders.find_one({"id": tender_id, **_of(user)}, {"_id": 0})
    if not tender:
        raise HTTPException(404, "Tender not found")
    brand = await _resolve_crm_brand(user)
    slides_override = tender.get("pitch_slides")
    pdf = build_pitch_deck_pdf(tender, brand, slides_override=slides_override)
    safe = (tender.get("title") or "tender-pitch").replace(" ", "_")[:60]
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-pitch.pdf"'},
    )


# Canned tender response templates.

class TenderTemplatePayload(BaseModel):
    label: str
    category: str
    body: str
    word_limit: int | None = None


@router.get("/tender-templates")
async def list_tender_templates(category: str | None = None, user=Depends(get_crm_user)):
    """List org-scoped tender response templates."""
    q = {**_of(user)}
    if category:
        q["category"] = category.lower().strip()
    cursor = db.crm2_tender_templates.find(q, {"_id": 0}).sort("label", 1)
    items = await cursor.to_list(500)
    return {"count": len(items), "items": items}


@router.post("/tender-templates")
async def create_tender_template(payload: TenderTemplatePayload, user=Depends(get_crm_user)):
    record = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "label": payload.label.strip(),
        "category": payload.category.strip().lower(),
        "body": payload.body,
        "word_limit": payload.word_limit,
        "usage_count": 0,
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_tender_templates.insert_one(record)
    record.pop("_id", None)
    return {"ok": True, "item": record}


@router.put("/tender-templates/{tpl_id}")
async def update_tender_template(tpl_id: str, payload: TenderTemplatePayload, user=Depends(get_crm_user)):
    res = await db.crm2_tender_templates.update_one(
        {"id": tpl_id, **_of(user)},
        {"$set": {
            "label": payload.label.strip(),
            "category": payload.category.strip().lower(),
            "body": payload.body,
            "word_limit": payload.word_limit,
            "updated_at": _now(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.delete("/tender-templates/{tpl_id}")
async def delete_tender_template(tpl_id: str, user=Depends(get_crm_user)):
    res = await db.crm2_tender_templates.delete_one({"id": tpl_id, **_of(user)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


_PULSE_TENDER_TEMPLATE_SEEDS = [
    {"label": "Pricing & commercial structure", "category": "pricing", "word_limit": 500,
     "body": "Our pricing is built around three transparent layers: capital outlay, ongoing service, and consumable parts. Each line item is itemised with no hidden surcharges. Volume pricing tiers apply automatically once defined contract milestones are reached. Lease & finance options are available through accredited providers. We commit to fixed prices for the first 24 months, with subsequent indexation capped at CPI."},
    {"label": "Mobilisation & implementation timeline", "category": "mobilisation", "word_limit": 600,
     "body": "Our standard 90-day mobilisation: Week 1-2 contract sign-off, site surveys, RAMS. Week 3-6 equipment manufactured, delivered & installed (max 2 sites/week). Week 7-10 commissioning, CPD-accredited staff training, member orientation with on-site coach for opening weekend. Week 11-12 service handover, BAU reporting configured, first QBR scheduled."},
    {"label": "Social value commitments (TOMs)", "category": "social_value", "word_limit": 500,
     "body": "Aligned to the TOMs framework, we commit: 1 apprenticeship per £250k contract value; 35% local sub-contractor spend within 30 miles; quarterly equipment donations to local schools; free community open days at every site for the first 12 months. Reported quarterly via the Pulse Fitness Social Value Dashboard with audit-grade evidence."},
    {"label": "Sustainability & environmental impact", "category": "sustainability", "word_limit": 500,
     "body": "ISO 14001 certified, with a closed-loop recycling programme (94% steel & aluminium recovery). Carbon emissions down 38% since 2019 against SBTi-aligned targets. End-of-life take-back at zero cost. Returnable steel shipping frames eliminate single-use packaging. Equipment refurbishment programme has prevented 412 tonnes of steel from secondary smelting (~620 tCO2e avoided)."},
    {"label": "Information security & data protection", "category": "security", "word_limit": 400,
     "body": "Our cloud platform is hosted on UK AWS regions with SOC2 Type II and Cyber Essentials Plus certification. All data in transit is TLS 1.3; at rest is AES-256. UK GDPR DPA available on request. Sub-processors are audited annually. Pen-tested twice yearly by an independent CHECK-accredited provider; reports available under NDA."},
    {"label": "Governance & contract management", "category": "governance", "word_limit": 500,
     "body": "Each client is assigned a named Account Director and Technical Service Lead. Monthly KPI reports cover uptime, first-time fix rate, parts consumption, attendance times, and warranty claims via the Pulse Fitness client portal. Quarterly business reviews are in-person and include a 12-month forward capacity plan. Annual independent service-quality audit by an agreed third party at our cost."},
    {"label": "Accreditations & certifications", "category": "accreditations", "word_limit": 350,
     "body": "ISO 9001:2015 (Quality), ISO 14001:2015 (Environmental), ISO 45001:2018 (H&S), CHAS Premium Plus, SafeContractor (Achilles 98/100), Cyber Essentials Plus, SOC2 Type II. All certificates are issued by UKAS-accredited bodies and audited annually. Copies attached as supporting documentation."},
    {"label": "Innovation & continuous improvement", "category": "innovation", "word_limit": 500,
     "body": "We commit to two material innovations per contract year, decided jointly with the client during QBRs. Recent examples: predictive-maintenance via on-equipment sensors (reduced unplanned downtime by 31%); member-app integration showing live equipment availability; QR-code self-service fault reporting that feeds straight into the engineer rota."},
]


@router.post("/tender-templates/seed-pulse-defaults")
async def seed_tender_templates(user=Depends(get_crm_user)):
    """Idempotent seed of common Pulse Fitness response templates."""
    org_id = user.get("organization_id")
    seeded = 0
    skipped = 0
    for entry in _PULSE_TENDER_TEMPLATE_SEEDS:
        exists = await db.crm2_tender_templates.find_one(
            {"organization_id": org_id, "label": entry["label"]},
            {"_id": 0, "id": 1},
        )
        if exists:
            skipped += 1
            continue
        await db.crm2_tender_templates.insert_one({
            "id": _id(), "organization_id": org_id,
            "label": entry["label"], "category": entry["category"],
            "body": entry["body"], "word_limit": entry.get("word_limit"),
            "usage_count": 0, "created_by": "system",
            "created_at": _now(), "updated_at": _now(),
        })
        seeded += 1
    return {"seeded": seeded, "skipped": skipped}


# Win/Loss analytics rollup.
@router.get("/tenders/analytics/win-loss")
async def tender_analytics(user=Depends(get_crm_user)):
    """Aggregate closed tenders into a win/loss dashboard.

    Returns: top-line win rate, value won/lost, win-rate by issuer,
    win-rate by tender type, and avg cycle time (created → closed).
    """
    base = _of(user)
    won = await db.crm2_tenders.count_documents({**base, "status": "won"})
    lost = await db.crm2_tenders.count_documents({**base, "status": "lost"})
    decided = won + lost
    win_rate = round((won / decided) * 100, 1) if decided else 0.0
    # Value rolls.
    pipeline = [
        {"$match": {**base, "status": {"$in": ["won", "lost"]}}},
        {"$group": {"_id": "$status", "total_value": {"$sum": "$value"}, "n": {"$sum": 1}}},
    ]
    by_status: dict[str, dict] = {}
    async for row in db.crm2_tenders.aggregate(pipeline):
        by_status[row["_id"]] = {"total_value": row.get("total_value") or 0, "n": row.get("n", 0)}
    # By issuer (top 8)
    by_issuer_pipeline = [
        {"$match": {**base, "status": {"$in": ["won", "lost"]}, "issuer": {"$ne": None}}},
        {"$group": {"_id": {"issuer": "$issuer", "status": "$status"}, "n": {"$sum": 1}, "value": {"$sum": "$value"}}},
    ]
    issuer_buckets: dict[str, dict] = {}
    async for row in db.crm2_tenders.aggregate(by_issuer_pipeline):
        issuer = row["_id"].get("issuer") or "Unknown"
        status = row["_id"]["status"]
        b = issuer_buckets.setdefault(issuer, {"issuer": issuer, "won": 0, "lost": 0, "won_value": 0, "lost_value": 0})
        if status == "won":
            b["won"] += row["n"]
            b["won_value"] += row.get("value") or 0
        else:
            b["lost"] += row["n"]
            b["lost_value"] += row.get("value") or 0
    issuer_rows = []
    for b in issuer_buckets.values():
        tot = b["won"] + b["lost"]
        b["win_rate"] = round((b["won"] / tot) * 100, 1) if tot else 0.0
        b["total"] = tot
        issuer_rows.append(b)
    issuer_rows.sort(key=lambda r: -r["total"])
    issuer_rows = issuer_rows[:8]
    # By type (ITT/RFP/PQQ/Framework).
    type_buckets: dict[str, dict] = {}
    async for t in db.crm2_tenders.find({**base, "status": {"$in": ["won", "lost"]}}, {"_id": 0, "type": 1, "status": 1, "value": 1}):
        ttype = t.get("type") or "other"
        b = type_buckets.setdefault(ttype, {"type": ttype, "won": 0, "lost": 0, "won_value": 0})
        if t["status"] == "won":
            b["won"] += 1
            b["won_value"] += t.get("value") or 0
        else:
            b["lost"] += 1
    type_rows = []
    for b in type_buckets.values():
        tot = b["won"] + b["lost"]
        b["win_rate"] = round((b["won"] / tot) * 100, 1) if tot else 0.0
        b["total"] = tot
        type_rows.append(b)
    type_rows.sort(key=lambda r: -r["total"])
    return {
        "won": won,
        "lost": lost,
        "decided": decided,
        "win_rate_pct": win_rate,
        "won_value": (by_status.get("won") or {}).get("total_value", 0),
        "lost_value": (by_status.get("lost") or {}).get("total_value", 0),
        "by_issuer": issuer_rows,
        "by_type": type_rows,
    }




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

    kb_items = await db.crm2_knowledge_base.find({**_of(user)}, {"_id": 0, "content_b64": 0}).limit(50).to_list(50)
    # Iter 216h101 — build chunked candidates and retrieve only the
    # most relevant 5 for this question. Falls back to the original
    # behaviour if nothing matches.
    from utils.document_extractor import chunk_text, retrieve_relevant
    candidates: list[dict] = []
    for item in kb_items:
        body = (item.get("content") or "").strip()
        if not body:
            continue
        for ch_idx, ch in enumerate(chunk_text(body)):
            candidates.append({
                "kb_id": item.get("id"),
                "title": item.get("title", ""),
                "chunk_index": ch_idx,
                "text": ch,
            })
    top = retrieve_relevant(question.get("text", ""), candidates, top_k=5)
    if top:
        kb_context = "\n\n".join(
            [f"[CITE-{i + 1}] {t['title']}\n{t['text']}" for i, t in enumerate(top)]
        )
        citations = [{"index": i + 1, "kb_id": t["kb_id"], "title": t["title"], "score": t["score"]} for i, t in enumerate(top)]
    else:
        kb_context = "\n".join([f"- {item.get('title','')}: {item.get('content','')[:300]}" for item in kb_items[:5] if item.get("content")])
        citations = []

    system = f"""You are a world-class Bid Writer for Pulse Fitness, a leading gym and fitness equipment company.
Write {tone}, compelling tender responses that WIN contracts.
Structure: Direct answer first → Evidence → Differentiation → Client benefit → Risk mitigation → Summary.
Be specific, outcome-focused, and evidence-based. Never be generic.
When you draw on the COMPANY KNOWLEDGE BASE, cite the relevant snippet by writing the matching [CITE-N] tag at the end of the supporting sentence — these citation markers will be rendered as references in the operator's review screen."""

    prompt = _build_tender_prompt(action, question, kb_context)

    try:
        # Iter 216h101 — Claude Sonnet 4.5 for response writing (richer
        # prose). Parsing / JSON / strategy continues to use GPT-5.2.
        resp = await _ai_call(system, prompt, model_pref="claude")
        word_count = len(resp.split())
        await db.crm2_tender_questions.update_one(
            {"id": q_id},
            {"$set": {
                "ai_draft": resp,
                "ai_citations": citations,
                "updated_at": _now(),
            }},
        )
        return {"response": resp, "word_count": word_count, "action": action, "citations": citations}
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

async def _crm_quote_recipients(org_id: str, *, approvers_only: bool = False, exclude_email: str = "") -> list[str]:
    """CRM user emails for quote-workflow notifications. When approvers_only,
    limit to org owners / admins / managers."""
    users = await db.crm_users.find(
        {"organization_id": org_id}, {"_id": 0, "email": 1, "role": 1, "is_org_owner": 1}
    ).to_list(500)
    ex = (exclude_email or "").strip().lower()
    out: list[str] = []
    for u in users:
        email = (u.get("email") or "").strip()
        if not email or email.lower() == ex:
            continue
        if approvers_only and not (u.get("is_org_owner") or u.get("role") in ("admin", "manager")):
            continue
        out.append(email)
    return out


async def _crm_user_email_by_name(org_id: str, full_name: str | None) -> str:
    if not full_name:
        return ""
    u = await db.crm_users.find_one(
        {"organization_id": org_id, "full_name": full_name}, {"_id": 0, "email": 1})
    return (u or {}).get("email", "") or ""


async def _send_quote_emails(org_id: str, recipients: list[str], subject: str,
                             title: str, lines: list[str], kind: str) -> None:
    if not recipients:
        return
    body = "".join(f"<p style='margin:6px 0;color:#334155;font-size:14px;'>{ln}</p>" for ln in lines)
    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;"
        "padding:24px;border:1px solid #e2e8f0;border-radius:12px;\">"
        f"<h2 style=\"color:#0f172a;margin:0 0 14px;font-size:18px;\">{title}</h2>{body}"
        "<p style=\"margin-top:22px;font-size:12px;color:#94a3b8;\">Pulse Fitness CRM</p></div>"
    )
    from utils.email import send_email
    for r in recipients:
        try:
            await send_email(to=r, subject=subject, html=html,
                             organization_id=org_id, kind=kind, category="crm_quote_workflow")
        except Exception:
            logger.warning("[crm.quote] notification email failed for %s", r)


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
    recipients = await _crm_quote_recipients(
        user.get("organization_id"), approvers_only=True, exclude_email=user.get("email", ""))
    await _send_quote_emails(
        user.get("organization_id"), recipients,
        f"Approval needed — Quote {q.get('quote_number', '')}",
        "A quote needs your approval",
        [f"{user.get('full_name', 'A colleague')} submitted quote <strong>{q.get('quote_number', '')}</strong> for approval.",
         f"Total: £{q.get('total') or q.get('total_value') or 0}",
         "Open the CRM → Quotes to review, approve or reject it."],
        "crm_quote_approval_request")
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
    approved = action == "approve"
    verb = "approved" if approved else "rejected"
    reason = (data.get("reason") or "").strip()
    await db.crm2_notifications.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "approval", "title": f"Quote {verb.capitalize()}",
        "message": f"Quote {q.get('quote_number', '')} was {verb} by {user.get('full_name', '')}"
                   + (f" — {reason}" if (not approved and reason) else ""),
        "entity_type": "quote", "entity_id": quote_id,
        "read": False, "created_at": _now(),
    })
    submitter_email = await _crm_user_email_by_name(user.get("organization_id"), q.get("submitted_by"))
    recipients = [submitter_email] if submitter_email else await _crm_quote_recipients(
        user.get("organization_id"), exclude_email=user.get("email", ""))
    lines = [f"Quote <strong>{q.get('quote_number', '')}</strong> was {verb} by {user.get('full_name', '')}."]
    if approved:
        lines.append("It can now be signed and sent to the customer.")
    elif reason:
        lines.append(f"Reason: {reason}")
    await _send_quote_emails(
        user.get("organization_id"), recipients,
        f"Quote {q.get('quote_number', '')} {verb}",
        f"Your quote was {verb}", lines, "crm_quote_approval_result")
    return {"success": True, "status": "approved" if approved else "rejected"}


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
    await db.crm2_notifications.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "approval", "title": "Quote Signed",
        "message": f"Quote {q.get('quote_number', '')} was signed by {signer_name}",
        "entity_type": "quote", "entity_id": quote_id,
        "read": False, "created_at": _now(),
    })
    recipients = await _crm_quote_recipients(
        user.get("organization_id"), approvers_only=True, exclude_email=user.get("email", ""))
    await _send_quote_emails(
        user.get("organization_id"), recipients,
        f"Quote {q.get('quote_number', '')} signed",
        "A quote has been signed",
        [f"Quote <strong>{q.get('quote_number', '')}</strong> was signed by {signer_name}.",
         f"Total: £{q.get('total') or q.get('total_value') or 0}",
         "The quote is now accepted."],
        "crm_quote_signed")
    try:
        from utils.comms_conversions import record_conversion
        org_id = q.get("organization_id")
        c_email = q.get("contact_email") or q.get("email")
        await record_conversion(org_id, c_email, "quote_accepted",
                                value_gbp=float(q.get("total") or q.get("total_value") or 0),
                                source="crm_quote", meta={"quote_id": quote_id})
    except Exception:
        pass
    return {"success": True, "status": "accepted", "signer": signer_name}


@router.post("/quotes/{quote_id}/push-to-distribution")
async def push_quote_to_distribution_route(quote_id: str, user=Depends(get_crm_user)):
    """Push an accepted CRM quote into Inventory & Distribution as an order
    (source=crm). Authenticated with the CRM token; delegates to the inventory
    module's shared push helper. Idempotent."""
    q = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0, "status": 1})
    if not q:
        raise HTTPException(404, "Quote not found")
    from routes.inventory_distribution import push_quote_to_distribution
    return await push_quote_to_distribution(quote_id, user)


# Iter 216h265 — Print + Email Quote ════════════════════════════════
#
# Customer asked for "ability to print quotes" and "distribution via
# email". PDF generation routes through the existing reportlab helper
# (used in crm_cpq.py); email delivery uses the unified utils.email
# pipeline (same one Quotes-the-supplier and Engineer reports use).


@router.get("/quotes/{quote_id}/pdf")
async def quote_pdf(quote_id: str, user=Depends(get_crm_user)):
    """Render the quote as a downloadable PDF."""
    from fastapi.responses import Response
    quote = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    try:
        from utils.crm_quote_pdf import render_quote_pdf
        pdf_bytes = await render_quote_pdf(quote, organization_id=user.get("organization_id"))
    except Exception as exc:
        logger.exception("[crm.quote_pdf] render failed")
        raise HTTPException(500, f"Could not generate PDF: {exc}") from exc
    filename = (quote.get("quote_number") or quote_id) + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/quotes/{quote_id}/send-email")
async def send_quote_email(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Email the quote PDF to the customer.

    Body: `{to?: str, cc?: list[str], subject?: str, message?: str}`.
    Defaults `to` to the linked contact's email when omitted.
    """
    quote = await db.crm2_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")
    to_addr = (data.get("to") or "").strip().lower()
    if not to_addr and quote.get("contact_id"):
        contact = await db.crm2_contacts.find_one(
            {"id": quote["contact_id"], **_of(user)},
            {"_id": 0, "email": 1, "first_name": 1, "last_name": 1},
        )
        if contact:
            to_addr = (contact.get("email") or "").strip().lower()
    if not to_addr:
        raise HTTPException(
            400,
            "No recipient email. Pass `to` or link a contact with an email address.",
        )
    cc = [c for c in (data.get("cc") or []) if isinstance(c, str) and c.strip()]
    subject = (data.get("subject") or f"Quote {quote.get('quote_number') or quote_id}").strip()
    body_html = (data.get("message") or "").strip() or (
        f"<p>Hi,</p>"
        f"<p>Please find attached quote <b>{quote.get('quote_number') or quote_id}</b> "
        f"from {user.get('full_name') or 'us'}.</p>"
        f"<p>Total: <b>£{float(quote.get('total') or 0):,.2f}</b><br>"
        f"Valid until: {quote.get('valid_until') or 'on request'}</p>"
        f"<p>Reply to this email with any questions.</p>"
    )
    try:
        from utils.crm_quote_pdf import render_quote_pdf
        from utils.email import send_email
        pdf_bytes = await render_quote_pdf(quote, organization_id=user.get("organization_id"))
        attachment = {
            "filename": (quote.get("quote_number") or quote_id) + ".pdf",
            "content": pdf_bytes,
            "content_type": "application/pdf",
        }
        await send_email(
            to=to_addr,
            subject=subject,
            html=body_html,
            cc=cc or None,
            attachments=[attachment],
            organization_id=user.get("organization_id"),
            kind="crm_quote",
        )
    except Exception as exc:
        logger.exception("[crm.quote_send_email] failed")
        raise HTTPException(500, f"Could not send quote email: {exc}") from exc

    sent_at = _now()
    await db.crm2_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "last_sent_to": to_addr,
            "last_sent_at": sent_at,
            "status": "sent" if quote.get("status") in (None, "", "draft", "approved") else quote.get("status"),
            "updated_at": sent_at,
        }, "$push": {
            "send_log": {"to": to_addr, "cc": cc, "sent_at": sent_at, "by": user.get("full_name", "")},
        }},
    )
    await db.crm2_activities.insert_one({
        "id": _id(), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Quote {quote.get('quote_number') or quote_id} emailed",
        "body": f"Sent to {to_addr}",
        "quote_id": quote_id, "company_id": quote.get("company_id"),
        "contact_id": quote.get("contact_id"),
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": sent_at, "updated_at": sent_at,
    })
    return {"ok": True, "to": to_addr, "sent_at": sent_at}


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
