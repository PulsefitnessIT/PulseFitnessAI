"""
Inventory & Distribution — PHASE 5 · Customer Allocation, Installation & Warranty.

Dealer allocates dealer-held machines (Phase-4 dealer_inventory_holdings) to THEIR customers
with duplicate-safe customer matching (reuses the CRM crm2_companies register — no second
customer database).  Allocation creates the ACTIVE ASSET in the EXISTING equipment register
(db.equipment) — the provisional/dealer unit becomes that one asset (unit.asset_id links it,
never a duplicate).  The Customer Operations Portal view is a customer-scoped read over
db.equipment.  Installation/commissioning (the Engineer App calls the same endpoint) activates
the asset and starts warranty per the configured rule.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db, get_object
from starlette.concurrency import run_in_threadpool
from fastapi import Response
from routes.inventory_distribution import _of, _now, _uid, _next_ref, _audit, _require_ops_role, _get_settings

router = APIRouter(prefix="/inventory/alloc", tags=["Inventory & Distribution · Customer Allocation"])
logger = logging.getLogger(__name__)

# Shared collections reused across modules (never duplicated).
SURVEYS = "pre_install_site_surveys"
SURVEY_ATTACH = "pre_install_survey_attachments"
DRAWINGS = "exploded_drawings"

# Survey statuses that make a survey the best candidate to attach to an install.
_SURVEY_PREFERRED = ("approved_for_installation", "completed", "installation_risk_identified")
_SURVEY_EXCLUDE = ("archived", "superseded")


async def _auto_match_survey(user: dict, company_id: str) -> Optional[dict]:
    """Find the most relevant pre-install site survey for a customer company.
    Prefers surveys marked ready/approved for installation, else the most recent
    current survey. Org-scoped (surveys are not always site-stamped)."""
    if not company_id:
        return None
    q = {
        "organization_id": user.get("organization_id"),
        "company_id": company_id,
        "status": {"$nin": list(_SURVEY_EXCLUDE)},
    }
    surveys = await db[SURVEYS].find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
    if not surveys:
        return None
    # Prefer a current, install-approved survey; otherwise the most recent current one.
    current = [s for s in surveys if s.get("is_current", True)] or surveys
    preferred = [s for s in current if s.get("status") in _SURVEY_PREFERRED]
    return (preferred or current)[0]


def _survey_hs_summary(survey: dict) -> dict:
    """Curate the Health & Safety / access parts of a survey for the install team."""
    data = survey.get("data") or {}
    risks = data.get("risks") or []
    access = data.get("access") or {}
    site_rules = data.get("site_rules") or {}
    return {
        "risks": [
            {
                "category": r.get("category"),
                "description": r.get("description"),
                "severity": r.get("severity"),
                "risk_level": r.get("risk_level") or r.get("severity"),
                "mitigation": r.get("mitigation"),
                "status": r.get("status"),
            }
            for r in risks if isinstance(r, dict)
        ],
        "access_risk_level": access.get("access_risk_level"),
        "access_risk_notes": access.get("access_risk_notes"),
        "site_rules": {
            "site_induction_required": site_rules.get("site_induction_required"),
            "rams_required": site_rules.get("rams_required"),
            "ppe_required": site_rules.get("ppe_required"),
            "dbs_required": site_rules.get("dbs_required"),
            "permit_to_work_required": site_rules.get("permit_to_work_required"),
            "security_clearance_required": site_rules.get("security_clearance_required"),
            "working_hours_restrictions": site_rules.get("working_hours_restrictions"),
            "emergency_contact": site_rules.get("emergency_contact"),
        },
    }


def _survey_brief(survey: dict) -> dict:
    return {
        "id": survey.get("id"),
        "reference": survey.get("reference"),
        "status": survey.get("status"),
        "readiness_status": survey.get("readiness_status"),
        "survey_type": survey.get("survey_type"),
        "target_install_date": survey.get("target_install_date"),
        "attachment_count": survey.get("attachment_count", 0),
        "company_name": survey.get("company_name"),
        "site_name": survey.get("site_name"),
        "updated_at": survey.get("updated_at"),
    }

ALLOCATION_STATUSES = ["allocated", "awaiting_delivery", "awaiting_installation", "installation_in_progress", "installed", "active", "cancelled"]

WARRANTY_MONTHS_DEFAULT = 24


async def _touch_unit(user, unit_id, status, extra=None):
    payload = {"status": status, "updated_at": _now()}
    if extra:
        payload.update(extra)
    await db.inv_equipment_units.update_one(
        {**_of(user), "id": unit_id},
        {"$set": payload, "$push": {"history": {"status": status, "at": _now(), "by": user.get("email")}}},
    )


# ──────────────────────────── Available dealer stock ────────────────────────────
@router.get("/available")
async def available_stock(dealer_id: Optional[str] = None, user=Depends(get_current_user)):
    flt = {**_of(user), "status": "available"}
    if dealer_id:
        flt["dealer_id"] = dealer_id
    rows = await db.dealer_inventory_holdings.find(flt, {"_id": 0}).sort("received_date", -1).limit(500).to_list(500)
    return {"available": rows}


# ──────────────────────────── Customer duplicate prevention ────────────────────────────
@router.get("/customers/search")
async def search_customers(q: str, user=Depends(get_current_user)):
    """Search the EXISTING CRM company register to prevent duplicate customers."""
    if not q or len(q) < 2:
        return {"matches": []}
    of = _of(user)
    rx = {"$regex": re.escape(q), "$options": "i"}
    rows = await db.crm2_companies.find(
        {**of, "$or": [{"name": rx}, {"trading_name": rx}, {"domain": rx}, {"postcode": rx}]},
        {"_id": 0, "id": 1, "name": 1, "country": 1, "company_type": 1, "postcode": 1, "domain": 1},
    ).limit(15).to_list(15)
    return {"matches": rows}


class NewCustomerIn(BaseModel):
    name: str
    country: str = "GB"
    postcode: Optional[str] = None
    domain: Optional[str] = None
    dealer_id: Optional[str] = None
    force: bool = False  # confirm-create despite possible duplicates


@router.post("/customers")
async def create_customer(body: NewCustomerIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    # duplicate scan
    rx = {"$regex": f"^{re.escape(body.name.strip())}$", "$options": "i"}
    dupes = await db.crm2_companies.find({**of, "name": rx}, {"_id": 0, "id": 1, "name": 1, "country": 1}).limit(10).to_list(10)
    if dupes and not body.force:
        return {"created": False, "duplicates": dupes, "message": "Possible existing customer(s) found — confirm to create anyway or use the existing record."}
    company_id = _uid()
    doc = {
        "id": company_id, "organization_id": user.get("organization_id"), "name": body.name.strip(),
        "country": body.country, "postcode": body.postcode, "domain": body.domain,
        "company_type": "dealer_customer", "status": "pending_validation",
        "created_by_dealer": body.dealer_id, "created_at": _now(),
    }
    await db.crm2_companies.insert_one({**doc})
    await _audit(user, "dealer_customer_created", "company", company_id, {"name": body.name, "status": "pending_validation"})
    doc.pop("_id", None)
    return {"created": True, "company": doc}


# ──────────────────────────── Allocate machines to a customer ────────────────────────────
class AllocateIn(BaseModel):
    unit_ids: List[str]
    customer_company_id: str
    customer_site: Optional[str] = None
    planned_delivery_date: Optional[str] = None
    planned_install_date: Optional[str] = None
    service_responsibility: str = "dealer"  # dealer | pulse | third_party


@router.post("/allocate")
async def allocate(body: AllocateIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    company = await db.crm2_companies.find_one({**of, "id": body.customer_company_id}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(404, "Customer company not found")
    results = []
    for unit_id in body.unit_ids:
        holding = await db.dealer_inventory_holdings.find_one({**of, "unit_id": unit_id, "status": "available"})
        if not holding:
            results.append({"unit_id": unit_id, "ok": False, "reason": "not available for allocation"})
            continue
        unit = await db.inv_equipment_units.find_one({**of, "id": unit_id}, {"_id": 0})
        # 1) create the ACTIVE ASSET in the existing equipment register (single record; unit becomes asset)
        asset_id = _uid()
        await db.equipment.insert_one({
            "id": asset_id, "user_id": user.get("id"), "organization_id": user.get("organization_id"),
            "name": f"{unit.get('model') or unit.get('product_code')} — {unit.get('serial_number')}",
            "equipment_type": "Fitness Machine", "model": unit.get("model"),
            "serial_number": unit.get("serial_number"), "manuals": [],
            "status": "awaiting_installation",
            "asset_source": "dealer_distribution", "source_unit_id": unit_id,
            "customer_company_id": company["id"], "customer_company_name": company["name"],
            "customer_site": body.customer_site, "dealer_id": holding.get("dealer_id"),
            "distribution_order_id": unit.get("order_id"),
            "created_at": _now(), "updated_at": _now(),
        })
        # 2) allocation record
        alloc_id = _uid()
        ref = await _next_ref(user, "ALL", db.dealer_customer_allocations)
        await db.dealer_customer_allocations.insert_one({
            "id": alloc_id, "organization_id": user.get("organization_id"), "reference": ref,
            "unit_id": unit_id, "asset_id": asset_id, "dealer_id": holding.get("dealer_id"),
            "customer_company_id": company["id"], "customer_company_name": company["name"],
            "customer_site": body.customer_site, "serial_number": unit.get("serial_number"),
            "model": unit.get("model"), "product_code": unit.get("product_code"),
            "planned_delivery_date": body.planned_delivery_date, "planned_install_date": body.planned_install_date,
            "service_responsibility": body.service_responsibility, "status": "awaiting_installation",
            "created_by": user.get("email"), "created_at": _now(),
        })
        # 3) mark holding + unit (unit becomes the asset — asset_id set, not duplicated)
        await db.dealer_inventory_holdings.update_one({"id": holding["id"]}, {"$set": {"status": "customer_allocated", "intended_customer_id": company["id"], "updated_at": _now()}})
        await _touch_unit(user, unit_id, "customer_allocated", extra={"asset_id": asset_id, "customer_company_id": company["id"]})
        results.append({"unit_id": unit_id, "ok": True, "allocation_id": alloc_id, "asset_id": asset_id, "reference": ref})
    ok = [r for r in results if r["ok"]]
    await _audit(user, "customer_allocation", "company", company["id"], {"allocated": len(ok)})
    return {"results": results, "allocated": len(ok), "customer": company["name"]}


@router.get("/allocations")
async def list_allocations(status: Optional[str] = None, user=Depends(get_current_user)):
    flt = _of(user)
    if status and status != "all":
        flt["status"] = status
    rows = await db.dealer_customer_allocations.find(flt, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"allocations": rows}


@router.get("/allocations/{alloc_id}")
async def get_allocation(alloc_id: str, user=Depends(get_current_user)):
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Allocation not found")
    install = await db.installation_commissioning_records.find_one({**of, "allocation_id": alloc_id}, {"_id": 0})
    warranty = await db.warranty_activation_events.find_one({**of, "unit_id": a["unit_id"]}, {"_id": 0})
    asset = await db.equipment.find_one({**of, "id": a.get("asset_id")}, {"_id": 0})
    return {"allocation": a, "installation": install, "warranty": warranty, "asset": asset}


# ──────────────────────────── Installation & commissioning (Engineer App calls this) ────────────────────────────
INSTALL_CHECKS = [
    {"key": "positioned", "label": "Machine positioned & levelled"},
    {"key": "power", "label": "Power / network connected"},
    {"key": "safety", "label": "Safety checks completed"},
    {"key": "test_run", "label": "Test run passed"},
    {"key": "customer_walkthrough", "label": "Customer walkthrough done"},
]


class InstallIn(BaseModel):
    engineer_name: str
    checklist: dict = {}
    software_version: Optional[str] = None
    condition: Optional[str] = None
    customer_acceptance: bool = False
    notes: Optional[str] = None
    # Phase 2 pt2 — on-site customer sign-off (also supplied by the logistics portal).
    customer_name: Optional[str] = None
    customer_signature: Optional[str] = None
    hs_acknowledged: bool = False


async def _warranty_dates(user, event: str):
    settings = await _get_settings(user)
    rule = settings.get("warranty_activation_rule", "installation_date")
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=WARRANTY_MONTHS_DEFAULT * 30)
    return rule, start.isoformat(), end.isoformat()


async def commission_install(alloc_id: str, data: dict, user: dict) -> dict:
    """Commission an installed asset, recording the on-site customer sign-off and
    activating warranty. Role is enforced by the CALLER (ops route requires an ops
    role; the logistics portal route requires the logistics/ops dependency)."""
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id})
    if not a:
        raise HTTPException(404, "Allocation not found")
    if a.get("status") == "active":
        raise HTTPException(409, "This installation is already completed")
    if not a.get("unit_id") or not a.get("asset_id"):
        raise HTTPException(400, "This allocation is not linked to a unit/asset and cannot be commissioned")
    if not data.get("customer_acceptance"):
        raise HTTPException(400, "Customer acceptance is required to commission the asset")
    rec_id = _uid()
    signed_at = _now()
    rec_doc = {
        "id": rec_id, "organization_id": user.get("organization_id"), "allocation_id": alloc_id,
        "unit_id": a["unit_id"], "asset_id": a.get("asset_id"),
        "engineer_name": data.get("engineer_name"),
        "checklist": data.get("checklist") or {}, "software_version": data.get("software_version"),
        "condition": data.get("condition"), "customer_acceptance": bool(data.get("customer_acceptance")),
        "notes": data.get("notes"),
        # sign-off
        "customer_name": data.get("customer_name"),
        "customer_signature": data.get("customer_signature"),
        "hs_acknowledged": bool(data.get("hs_acknowledged")),
        "signed_at": signed_at,
        "commissioned_at": signed_at, "recorded_by": user.get("email"),
    }
    await db.installation_commissioning_records.insert_one({**rec_doc})
    rule, w_start, w_end = await _warranty_dates(user, "installation_date")
    await db.warranty_activation_events.insert_one({
        "id": _uid(), "organization_id": user.get("organization_id"), "unit_id": a["unit_id"],
        "asset_id": a.get("asset_id"), "warranty_start": w_start, "warranty_end": w_end,
        "warranty_source": rule, "triggering_event": "commissioning", "created_at": _now(),
    })
    await db.equipment.update_one({**of, "id": a.get("asset_id")}, {"$set": {
        "status": "active", "warranty_expiry": w_end, "commissioned_at": _now(),
        "software_version": data.get("software_version"), "updated_at": _now(),
    }})
    await _touch_unit(user, a["unit_id"], "active_asset")
    a_patch = {
        "status": "active", "installed_at": _now(),
        "signed_off_by": data.get("customer_name"), "signed_off_at": signed_at, "updated_at": _now(),
    }
    await db.dealer_customer_allocations.update_one({"id": alloc_id}, {"$set": a_patch})
    await db.dealer_inventory_holdings.update_one({**of, "unit_id": a["unit_id"]}, {"$set": {"status": "installed", "updated_at": _now()}})
    # Branded proof-of-install certificate (stored against the asset).
    from routes.inventory_certificate import generate_and_store_certificate
    hs = {}
    if a.get("site_survey_id"):
        _sv = await db[SURVEYS].find_one({"organization_id": user.get("organization_id"), "id": a["site_survey_id"]}, {"_id": 0})
        if _sv:
            hs = _survey_hs_summary(_sv)
    cert = await generate_and_store_certificate({**a, **a_patch}, rec_doc, {"warranty_start": w_start, "warranty_end": w_end, "warranty_source": rule}, user, hs)
    # Register the machine into the customer's own Pulse org (if linked) so they
    # can see it and log faults on it from their Lite/Pro dashboard. Best-effort.
    try:
        from routes.pulse_onboarding import register_customer_equipment
        await register_customer_equipment({**a, **a_patch}, {"warranty_start": w_start, "warranty_end": w_end})
    except Exception:
        logger.exception("[inventory] customer equipment registration failed")
    await _audit(user, "installation_commissioned", "allocation", alloc_id, {"warranty_end": w_end, "signed_off_by": data.get("customer_name")})
    return {"ok": True, "asset_status": "active", "warranty_start": w_start, "warranty_end": w_end, "warranty_rule": rule, "record_id": rec_id, "certificate": bool(cert.get("storage_path"))}


@router.post("/allocations/{alloc_id}/schedule")
async def schedule_installation(alloc_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Set or reschedule the planned installation date for the logistics team's
    installation calendar. Non-destructive — does not commission the asset."""
    _require_ops_role(user)
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id})
    if not a:
        raise HTTPException(404, "Allocation not found")
    planned = (body.get("planned_install_date") or "").strip()
    if not planned:
        raise HTTPException(400, "planned_install_date is required")
    patch = {"planned_install_date": planned, "updated_at": _now()}
    if body.get("install_window"):
        patch["install_window"] = body.get("install_window")
    if body.get("logistics_note") is not None:
        patch["logistics_note"] = body.get("logistics_note")
    # Auto-attach the customer's pre-install site survey to the installation so
    # all H&S / access / drawings info is collated in one place for the team.
    linked_survey = None
    if not a.get("site_survey_id"):
        survey = await _auto_match_survey(user, a.get("customer_company_id"))
        if survey:
            patch["site_survey_id"] = survey.get("id")
            patch["site_survey_reference"] = survey.get("reference")
            patch["site_survey_status"] = survey.get("status")
            patch["site_survey_auto_linked"] = True
            linked_survey = _survey_brief(survey)
    await db.dealer_customer_allocations.update_one({"id": alloc_id}, {"$set": patch})
    await _audit(user, "installation_scheduled", "allocation", alloc_id, {"planned_install_date": planned, "site_survey_id": patch.get("site_survey_id")})
    return {"ok": True, "planned_install_date": planned, "linked_survey": linked_survey}


@router.post("/allocations/{alloc_id}/install")
async def install_commission(alloc_id: str, body: InstallIn, user=Depends(get_current_user)):
    _require_ops_role(user)
    return await commission_install(alloc_id, body.model_dump(), user)


# ──────────────────────────── Install pack (collated info for the logistics/install team) ────────────────────────────
async def _drawings_for(user: dict, manufacturer: str = "", model: str = "") -> list:
    """Match exploded/assembly drawings for a machine by model (and manufacturer
    when known). Org-owned OR globally-published drawings."""
    if not (model or "").strip() and not (manufacturer or "").strip():
        return []
    org = user.get("organization_id")
    filters = []
    if (model or "").strip():
        filters.append({"model": {"$regex": re.escape(model.strip()), "$options": "i"}})
    if (manufacturer or "").strip():
        filters.append({"manufacturer": {"$regex": re.escape(manufacturer.strip()), "$options": "i"}})
    q = {
        "is_deleted": {"$ne": True},
        "$and": [
            {"$or": [{"organization_id": org}, {"organization_id": None}]},
            {"$or": filters} if filters else {},
        ],
    }
    docs = await db[DRAWINGS].find(q, {"_id": 0, "storage_path": 0}).sort("created_at", -1).limit(10).to_list(10)
    return [
        {
            "drawing_id": d.get("id"),
            "title": d.get("title"),
            "manufacturer": d.get("manufacturer"),
            "model": d.get("model"),
            "file_url": f"/api/exploded-drawings/{d.get('id')}/file",
        }
        for d in docs
    ]


@router.get("/allocations/{alloc_id}/install-pack")
async def install_pack(alloc_id: str, user=Depends(get_current_user)):
    """Collated install pack for the logistics/install team: the machines in this
    install visit, the linked pre-install site survey (H&S / access / site rules),
    installer-visible survey attachments (photos, floor plans, CAD/drawings), and
    exploded assembly drawings for each machine."""
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Allocation not found")

    # The install visit = all allocations for the same customer on the same planned day.
    visit_q = {"organization_id": user.get("organization_id"), "customer_company_id": a.get("customer_company_id")}
    if a.get("planned_install_date"):
        visit_q["planned_install_date"] = a.get("planned_install_date")
    else:
        visit_q["id"] = alloc_id
    visit_allocs = await db.dealer_customer_allocations.find(visit_q, {"_id": 0}).to_list(200)
    if not any(x.get("id") == alloc_id for x in visit_allocs):
        visit_allocs.append(a)

    machines = []
    for m in visit_allocs:
        machines.append({
            "allocation_id": m.get("id"),
            "reference": m.get("reference"),
            "model": m.get("model"),
            "product_code": m.get("product_code"),
            "serial_number": m.get("serial_number"),
            "status": m.get("status"),
            "drawings": await _drawings_for(user, "", m.get("model") or m.get("product_code") or ""),
        })

    # Resolve the linked survey (explicit link on this allocation, else auto-match).
    survey = None
    if a.get("site_survey_id"):
        survey = await db[SURVEYS].find_one(
            {"organization_id": user.get("organization_id"), "id": a["site_survey_id"]}, {"_id": 0})
    if not survey:
        survey = await _auto_match_survey(user, a.get("customer_company_id"))

    survey_block = None
    attachments = []
    if survey:
        survey_block = {**_survey_brief(survey), "hs": _survey_hs_summary(survey), "auto_linked": bool(a.get("site_survey_auto_linked"))}
        raw = await db[SURVEY_ATTACH].find(
            {"survey_id": survey.get("id"), "is_deleted": {"$ne": True}}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)
        for att in raw:
            if att.get("visible_to_installer") is False:
                continue
            attachments.append({
                "id": att.get("id"),
                "category": att.get("category"),
                "description": att.get("description"),
                "filename": att.get("original_filename"),
                "content_type": att.get("content_type"),
                "size": att.get("size"),
                "download_url": f"/api/inventory/alloc/survey-attachment/{att.get('id')}/download",
            })

    # Completion / warranty state so the portal can show a "completed" install.
    install_rec = await db.installation_commissioning_records.find_one(
        {"organization_id": user.get("organization_id"), "allocation_id": alloc_id}, {"_id": 0, "customer_signature": 0})
    warranty = await db.warranty_activation_events.find_one(
        {"organization_id": user.get("organization_id"), "unit_id": a.get("unit_id")}, {"_id": 0})

    return {
        "allocation": a,
        "visit": {
            "customer_company_id": a.get("customer_company_id"),
            "customer_company_name": a.get("customer_company_name"),
            "customer_site": a.get("customer_site"),
            "planned_install_date": a.get("planned_install_date"),
            "install_window": a.get("install_window"),
            "logistics_note": a.get("logistics_note"),
            "machine_count": len(machines),
        },
        "machines": machines,
        "survey": survey_block,
        "survey_attachments": attachments,
        "completed": a.get("status") == "active",
        "installation": install_rec,
        "warranty": warranty,
        "certificate_url": (f"/api/inventory/alloc/allocations/{alloc_id}/certificate"
                            if install_rec and install_rec.get("certificate_storage_path") else None),
    }


@router.get("/customers/pulse-link/candidates")
async def pulse_link_candidates(q: str = "", user=Depends(get_current_user)):
    """Search Pulse operator organisations to link a distribution customer to
    their own dashboard. Owner/manager only."""
    _require_ops_role(user)
    query = {"account_type": {"$in": ["lite", "pulse_pro", "pro"]}}
    if (q or "").strip():
        import re as _re
        query["name"] = {"$regex": _re.escape(q.strip()), "$options": "i"}
    rows = await db.organizations.find(query, {"_id": 0, "id": 1, "name": 1, "account_type": 1}).limit(20).to_list(20)
    return {"candidates": rows}


@router.get("/customers/{company_id}/pulse-link")
async def get_pulse_link(company_id: str, user=Depends(get_current_user)):
    _require_ops_role(user)
    of = _of(user)
    c = await db.crm2_companies.find_one({**of, "id": company_id}, {"_id": 0, "id": 1, "name": 1, "linked_operator_org_id": 1})
    if not c:
        raise HTTPException(404, "Customer not found")
    linked = None
    if c.get("linked_operator_org_id"):
        org = await db.organizations.find_one({"id": c["linked_operator_org_id"]}, {"_id": 0, "id": 1, "name": 1, "account_type": 1})
        linked = org
    return {"company_id": company_id, "linked_org": linked}


@router.post("/customers/{company_id}/pulse-link")
async def set_pulse_link(company_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Link (or clear) the customer's Pulse account so they see their deliveries."""
    _require_ops_role(user)
    of = _of(user)
    c = await db.crm2_companies.find_one({**of, "id": company_id}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(404, "Customer not found")
    org_id = (body.get("org_id") or "").strip() or None
    linked = None
    if org_id:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1, "account_type": 1})
        if not org:
            raise HTTPException(404, "Pulse organisation not found")
        linked = org
    await db.crm2_companies.update_one({"id": company_id}, {"$set": {"linked_operator_org_id": org_id, "updated_at": _now()}})
    await _audit(user, "customer_pulse_linked", "crm2_company", company_id, {"linked_operator_org_id": org_id})
    return {"ok": True, "linked_org": linked}


@router.get("/allocations/{alloc_id}/certificate")
async def download_certificate(alloc_id: str, user=Depends(get_current_user)):
    """Stream the branded installation certificate PDF (org-scoped)."""
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id}, {"_id": 0, "id": 1})
    if not a:
        raise HTTPException(404, "Allocation not found")
    rec = await db.installation_commissioning_records.find_one(
        {"organization_id": user.get("organization_id"), "allocation_id": alloc_id}, {"_id": 0})
    if not rec or not rec.get("certificate_storage_path"):
        raise HTTPException(404, "No certificate available for this install")
    data, _ct = await run_in_threadpool(get_object, rec["certificate_storage_path"])
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{rec.get("certificate_filename", "installation-certificate.pdf")}"'})


@router.get("/allocations/{alloc_id}/survey-candidates")
async def survey_candidates(alloc_id: str, user=Depends(get_current_user)):
    """List pre-install site surveys for this allocation's customer so the team
    can pick/relink a different survey if the auto-match wasn't right."""
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id}, {"_id": 0, "customer_company_id": 1})
    if not a:
        raise HTTPException(404, "Allocation not found")
    rows = await db[SURVEYS].find(
        {"organization_id": user.get("organization_id"), "company_id": a.get("customer_company_id"),
         "status": {"$nin": list(_SURVEY_EXCLUDE)}},
        {"_id": 0},
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"candidates": [_survey_brief(s) for s in rows]}


@router.post("/allocations/{alloc_id}/link-survey")
async def link_survey(alloc_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Manually link (or clear) the pre-install site survey attached to an install."""
    _require_ops_role(user)
    of = _of(user)
    a = await db.dealer_customer_allocations.find_one({**of, "id": alloc_id})
    if not a:
        raise HTTPException(404, "Allocation not found")
    survey_id = (body.get("survey_id") or "").strip() or None
    if survey_id:
        survey = await db[SURVEYS].find_one(
            {"organization_id": user.get("organization_id"), "id": survey_id}, {"_id": 0})
        if not survey:
            raise HTTPException(404, "Survey not found")
        patch = {
            "site_survey_id": survey.get("id"),
            "site_survey_reference": survey.get("reference"),
            "site_survey_status": survey.get("status"),
            "site_survey_auto_linked": False,
            "updated_at": _now(),
        }
    else:
        patch = {"site_survey_id": None, "site_survey_reference": None,
                 "site_survey_status": None, "site_survey_auto_linked": False, "updated_at": _now()}
    await db.dealer_customer_allocations.update_one({"id": alloc_id}, {"$set": patch})
    await _audit(user, "install_survey_linked", "allocation", alloc_id, {"site_survey_id": survey_id})
    return {"ok": True, "site_survey_id": survey_id}


@router.get("/survey-attachment/{att_id}/download")
async def download_survey_attachment(att_id: str, user=Depends(get_current_user)):
    """Stream an installer-visible survey attachment (org-scoped) for the install pack."""
    att = await db[SURVEY_ATTACH].find_one(
        {"id": att_id, "organization_id": user.get("organization_id"), "is_deleted": {"$ne": True}}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    if att.get("visible_to_installer") is False:
        raise HTTPException(403, "Attachment not shared with the install team")
    if att.get("storage_path"):
        data, ct = await run_in_threadpool(get_object, att["storage_path"])
    else:
        import base64
        data = base64.b64decode(att.get("data_b64", ""))
        ct = att.get("content_type", "application/octet-stream")
    return Response(content=data, media_type=att.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "file")}"'})


# ──────────────────────────── Customer Operations Portal view (over the single asset register) ────────────────────────────
@router.get("/customer-portal/{company_id}/equipment")
async def customer_portal_equipment(company_id: str, user=Depends(get_current_user)):
    of = _of(user)
    company = await db.crm2_companies.find_one({**of, "id": company_id}, {"_id": 0, "id": 1, "name": 1})
    rows = await db.equipment.find(
        {**of, "customer_company_id": company_id, "asset_source": "dealer_distribution"},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "serial_number": 1, "status": 1, "warranty_expiry": 1,
         "customer_site": 1, "commissioned_at": 1, "software_version": 1},
    ).sort("created_at", -1).to_list(500)
    return {"company": company, "equipment": rows}


@router.get("/summary")
async def alloc_summary(user=Depends(get_current_user)):
    of = _of(user)
    return {
        "available_to_allocate": await db.dealer_inventory_holdings.count_documents({**of, "status": "available"}),
        "awaiting_installation": await db.dealer_customer_allocations.count_documents({**of, "status": "awaiting_installation"}),
        "active_assets": await db.dealer_customer_allocations.count_documents({**of, "status": "active"}),
    }
