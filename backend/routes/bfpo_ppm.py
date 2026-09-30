"""
MOD / BFPO — Planned Preventative Maintenance (PPM) service checklists.

A "service" covers every asset at a site. An engineer inspects each asset
against a category checklist (pass / fail / n/a), raises a linked BFPO job
if an item fails, and on completion a branded PDF service certificate is
generated, auto-filed into the site's org documents, and the site is emailed.

Reuses the shared service-case engine + BFPO scoping from routes.bfpo.
"""
from datetime import datetime, timezone
import io
import uuid
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response

from utils.database import db
from utils.svc_state import OPEN_STATES, NEW
from routes.bfpo import (
    BFPO_ORG_ID, _require_bfpo, _require_staff, _role, _visible_site_ids, _now, _today,
)
from routes.svc.cases import next_reference, compute_sla_targets
from utils.svc_state import append_event
from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bfpo/ppm", tags=["MOD · BFPO PPM"])

# Default checklists per equipment category (seeded; staff can edit in-app).
DEFAULT_TEMPLATES = {
    "treadmill": ["Emergency stop / safety key operates", "Running belt tension & alignment", "Deck & belt wear", "Drive motor & belt condition", "Console & display function", "Incline mechanism", "Handrails & frame secure", "Cleanliness & lubrication"],
    "cross_trainer": ["Pedal arms & straps secure", "Flywheel / drive smooth, no grinding", "Resistance adjusts through range", "Console & display function", "Handlebars & frame secure", "Bearings & rollers condition", "Cleanliness & lubrication"],
    "bike": ["Pedals & straps secure", "Seat post & saddle adjust/lock", "Resistance adjusts through range", "Console & display function", "Frame & stabilisers secure", "Drive/belt condition", "Cleanliness"],
    "rower": ["Seat rollers run smoothly on rail", "Handle & chain/strap condition", "Damper / resistance operates", "Footplate straps secure", "Console & display function", "Frame secure", "Cleanliness"],
    "strength": ["Cables & pulleys free of fray/wear", "Weight stack pins & selector", "Guide rods lubricated", "Upholstery & pads intact", "Frame bolts secure", "Safety stops operate", "Cleanliness"],
}
GENERIC_ITEMS = ["Visual condition & safety", "Function test", "Cleanliness"]


def _items(labels):
    return [{"id": str(uuid.uuid4()), "label": lbl} for lbl in labels]


async def _ppm_ref() -> str:
    doc = await db.bfpo_ppm_counter.find_one_and_update(
        {"organization_id": BFPO_ORG_ID}, {"$inc": {"value": 1}},
        upsert=True, return_document=True,
    )
    return f"PPM-{(doc or {}).get('value', 1):05d}"


async def _template_for(category: str) -> dict | None:
    return await db.bfpo_ppm_templates.find_one(
        {"organization_id": BFPO_ORG_ID, "category": category}, {"_id": 0})


async def _service_in_scope(user: dict, service: dict) -> bool:
    if _role(user) in ("staff", "lead"):
        return True
    ids = await _visible_site_ids(user)
    if ids is None:
        return True
    return service.get("site_id") in ids or service.get("assigned_engineer_id") == user["id"]


async def _load_service(user: dict, service_id: str) -> dict:
    svc = await db.bfpo_ppm_services.find_one(
        {"id": service_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not svc or not await _service_in_scope(user, svc):
        raise HTTPException(404, "Service not found")
    return svc


def _progress(inspections: list) -> dict:
    total = len(inspections)
    done = sum(1 for i in inspections if i.get("status") and i["status"] != "pending")
    failed = sum(1 for i in inspections if i.get("status") == "failed")
    return {"total": total, "done": done, "failed": failed, "remaining": total - done}


async def _spawn_service(site: dict, due_date: str, engineer_id: str = "", source: str = "manual") -> dict | None:
    """Create a PPM service for a site, snapshotting its equipment into
    pending inspections keyed to each asset's category template. Returns the
    service, or None if the site has no equipment."""
    equipment = await db.equipment.find(
        {"organization_id": BFPO_ORG_ID, "site_id": site["id"]}, {"_id": 0}).to_list(1000)
    if not equipment:
        return None
    svc = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "reference": await _ppm_ref(),
        "site_id": site["id"], "site_name": site.get("name"),
        "territory_id": site.get("territory_id"), "territory_name": site.get("territory_name"),
        "country": site.get("country"), "status": "due",
        "assigned_engineer_id": engineer_id or "", "assigned_engineer_name": "",
        "due_date": due_date or "", "asset_count": len(equipment), "source": source,
        "certificate_doc_id": "", "cert_emailed_to": "",
        "created_at": _now(), "started_at": None, "completed_at": None,
    }
    if engineer_id:
        eng = await db.users.find_one({"id": engineer_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
        svc["assigned_engineer_name"] = (eng or {}).get("full_name") or ""
    await db.bfpo_ppm_services.insert_one(dict(svc))
    for eq in equipment:
        tpl = await _template_for(eq.get("equipment_type") or "")
        items = (tpl or {}).get("items") or _items(GENERIC_ITEMS)
        await db.bfpo_ppm_inspections.insert_one({
            "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "service_id": svc["id"],
            "equipment_id": eq["id"], "equipment_name": eq.get("name"),
            "serial": eq.get("serial_number"), "category": eq.get("equipment_type"),
            "template_id": (tpl or {}).get("id"), "template_name": (tpl or {}).get("name"),
            "results": [{"item_id": it["id"], "label": it["label"], "result": "", "note": ""} for it in items],
            "status": "pending", "fault_case_id": "", "inspected_at": None, "inspected_by": "",
        })
    return svc


# ─────────────────────────────────────────────────────────────────
# Templates (MOD Operations staff)
# ─────────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(user=Depends(_require_bfpo)):
    rows = await db.bfpo_ppm_templates.find(
        {"organization_id": BFPO_ORG_ID}, {"_id": 0}).sort("category", 1).to_list(50)
    return {"templates": rows}


@router.post("/templates")
async def upsert_template(data: dict = Body(...), user=Depends(_require_staff)):
    category = (data.get("category") or "").strip()
    if not category:
        raise HTTPException(400, "category required")
    raw_items = data.get("items") or []
    items = []
    for it in raw_items:
        label = (it.get("label") if isinstance(it, dict) else str(it)).strip()
        if not label:
            continue
        items.append({"id": (it.get("id") if isinstance(it, dict) and it.get("id") else str(uuid.uuid4())), "label": label})
    doc = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "category": category,
        "name": (data.get("name") or category.replace("_", " ").title() + " service").strip(),
        "items": items, "updated_at": _now(), "updated_by": user.get("full_name") or user.get("email"),
    }
    existing = await _template_for(category)
    if existing:
        doc["id"] = existing["id"]
        await db.bfpo_ppm_templates.update_one(
            {"id": existing["id"], "organization_id": BFPO_ORG_ID},
            {"$set": {k: doc[k] for k in ("name", "items", "updated_at", "updated_by")}})
    else:
        await db.bfpo_ppm_templates.insert_one(dict(doc))
    return {"ok": True, "template": doc}


# ─────────────────────────────────────────────────────────────────
# Services
# ─────────────────────────────────────────────────────────────────

@router.get("/services")
async def list_services(status: str = "", user=Depends(_require_bfpo)):
    q = {"organization_id": BFPO_ORG_ID}
    if _role(user) not in ("staff", "lead"):
        ids = await _visible_site_ids(user)
        if ids is not None:
            q["$or"] = [{"site_id": {"$in": ids}}, {"assigned_engineer_id": user["id"]}]
    if status:
        q["status"] = status
    rows = await db.bfpo_ppm_services.find(q, {"_id": 0}).sort("created_at", -1).to_list(300)
    for s in rows:
        insp = await db.bfpo_ppm_inspections.find(
            {"service_id": s["id"], "organization_id": BFPO_ORG_ID}, {"_id": 0, "status": 1}).to_list(500)
        s["progress"] = _progress(insp)
    return {"services": rows, "count": len(rows)}


@router.post("/services")
async def create_service(data: dict = Body(...), user=Depends(_require_staff)):
    site_id = data.get("site_id")
    site = await db.sites.find_one({"id": site_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not site:
        raise HTTPException(404, "Site not found")
    equipment = await db.equipment.find(
        {"organization_id": BFPO_ORG_ID, "site_id": site_id}, {"_id": 0}).to_list(1000)
    if not equipment:
        raise HTTPException(400, "This site has no equipment to inspect")
    svc = await _spawn_service(site, data.get("due_date") or "", data.get("engineer_id") or "", "manual")
    return {"ok": True, "service": svc}


@router.post("/services/{service_id}/allocate")
async def allocate_service(service_id: str, data: dict = Body(...), user=Depends(_require_staff)):
    await _load_service(user, service_id)
    eng = await db.users.find_one({"id": data.get("engineer_id"), "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not eng:
        raise HTTPException(404, "Engineer not found")
    await db.bfpo_ppm_services.update_one(
        {"id": service_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"assigned_engineer_id": eng["id"], "assigned_engineer_name": eng.get("full_name") or eng.get("email")}})
    return {"ok": True}


@router.get("/services/{service_id}")
async def get_service(service_id: str, user=Depends(_require_bfpo)):
    svc = await _load_service(user, service_id)
    insp = await db.bfpo_ppm_inspections.find(
        {"service_id": service_id, "organization_id": BFPO_ORG_ID}, {"_id": 0}).to_list(1000)
    insp.sort(key=lambda i: (i.get("status") != "pending", i.get("equipment_name") or ""))
    svc["inspections"] = insp
    svc["progress"] = _progress(insp)
    svc["viewer_role"] = _role(user)
    return svc


@router.post("/services/{service_id}/start")
async def start_service(service_id: str, user=Depends(_require_bfpo)):
    svc = await _load_service(user, service_id)
    updates = {"status": "in_progress"}
    if not svc.get("started_at"):
        updates["started_at"] = _now()
    if not svc.get("assigned_engineer_id") and _role(user) in ("engineer", "lead"):
        updates["assigned_engineer_id"] = user["id"]
        updates["assigned_engineer_name"] = user.get("full_name") or user.get("email")
    await db.bfpo_ppm_services.update_one(
        {"id": service_id, "organization_id": BFPO_ORG_ID}, {"$set": updates})
    return await get_service(service_id, user)


@router.post("/inspections/{inspection_id}")
async def save_inspection(inspection_id: str, data: dict = Body(...), user=Depends(_require_bfpo)):
    insp = await db.bfpo_ppm_inspections.find_one(
        {"id": inspection_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not insp:
        raise HTTPException(404, "Inspection not found")
    await _load_service(user, insp["service_id"])
    results = data.get("results") or []
    any_fail = any((r.get("result") == "fail") for r in results)
    all_answered = results and all((r.get("result") in ("pass", "fail", "na")) for r in results)
    status = "failed" if any_fail else ("passed" if all_answered else "pending")
    await db.bfpo_ppm_inspections.update_one(
        {"id": inspection_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"results": results, "status": status,
                  "inspected_at": _now(), "inspected_by": user.get("full_name") or user.get("email")}})
    # move service to in_progress on first activity
    await db.bfpo_ppm_services.update_one(
        {"id": insp["service_id"], "organization_id": BFPO_ORG_ID, "status": "due"},
        {"$set": {"status": "in_progress", "started_at": _now()}})
    return {"ok": True, "status": status}


@router.post("/inspections/{inspection_id}/raise-fault")
async def raise_fault(inspection_id: str, data: dict = Body(default={}), user=Depends(_require_bfpo)):
    insp = await db.bfpo_ppm_inspections.find_one(
        {"id": inspection_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not insp:
        raise HTTPException(404, "Inspection not found")
    svc = await _load_service(user, insp["service_id"])
    title = (data.get("title") or f"PPM fault: {insp.get('equipment_name')}").strip()
    priority = (data.get("priority") or "p3").lower()
    if priority not in ("p1", "p2", "p3", "p4"):
        priority = "p3"
    sla = await compute_sla_targets(organization_id=BFPO_ORG_ID, priority=priority)
    case = {
        "id": str(uuid.uuid4()), "organization_id": BFPO_ORG_ID, "bfpo": True,
        "reference": await next_reference(BFPO_ORG_ID), "status": NEW, "priority": priority,
        "case_type": "repair", "title": title, "description": (data.get("description") or "").strip(),
        "safety_critical": bool(data.get("safety_critical")),
        "territory_id": svc.get("territory_id"), "territory_name": svc.get("territory_name"),
        "country": svc.get("country"), "site_id": svc.get("site_id"), "site_name": svc.get("site_name"),
        "customer_name": "Ministry of Defence", "asset_id": insp.get("equipment_id"),
        "asset_name": insp.get("equipment_name"), "equipment_ids": [insp.get("equipment_id")],
        "assigned_engineer_id": "", "assigned_engineer_name": "", "scheduled_at": None,
        "sla_response_at": sla["sla_response_at"], "sla_resolve_at": sla["sla_resolve_at"],
        "source": "ppm_inspection", "ppm_service_id": svc["id"], "ppm_service_ref": svc.get("reference"),
        "logged_by_id": user["id"], "logged_by_name": user.get("full_name") or user.get("email"),
        "closed_at": None, "created_at": _now(), "updated_at": _now(),
    }
    await db.svc_cases.insert_one(dict(case))
    await append_event(case_id=case["id"], organization_id=BFPO_ORG_ID, event_type="intake",
                       actor=user, body=f"Fault raised during PPM {svc.get('reference')}",
                       extra={"ppm_service_id": svc["id"]})
    await db.bfpo_ppm_inspections.update_one(
        {"id": inspection_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"fault_case_id": case["id"], "fault_reference": case["reference"], "status": "failed"}})
    return {"ok": True, "case_id": case["id"], "reference": case["reference"]}


@router.post("/services/{service_id}/complete")
async def complete_service(service_id: str, data: dict = Body(default={}), user=Depends(_require_bfpo)):
    svc = await _load_service(user, service_id)
    insp = await db.bfpo_ppm_inspections.find(
        {"service_id": service_id, "organization_id": BFPO_ORG_ID}, {"_id": 0}).to_list(1000)
    pending = [i for i in insp if not i.get("status") or i["status"] == "pending"]
    if pending:
        raise HTTPException(400, f"{len(pending)} asset(s) still to inspect")
    pdf = _build_certificate_pdf(svc, insp, user)
    fname = f"PPM Certificate - {svc.get('reference')} - {svc.get('site_name')}.pdf"
    # Auto-file into the site's org documents library (best-effort).
    doc_id = ""
    try:
        from routes.master_admin_documents_lib import record_generated_document
        doc_id = await record_generated_document(
            title=f"PPM Service Certificate — {svc.get('site_name')} ({svc.get('reference')})",
            category="compliance", body=pdf, content_type="application/pdf", filename=fname,
            organization_id=BFPO_ORG_ID, linked_type="ppm_service", linked_id=service_id,
            tags=["ppm", "certificate", svc.get("site_name") or "", svc.get("country") or ""],
            actor_id=user.get("id"))
    except Exception:
        logger.exception("PPM cert auto-file failed")
    # Email the site that the certificate is available (best-effort).
    site = await db.sites.find_one({"id": svc["site_id"], "organization_id": BFPO_ORG_ID}, {"_id": 0}) or {}
    emailed_to = ""
    to = site.get("contact_email")
    if to:
        try:
            from utils.email import send_email
            failed = sum(1 for i in insp if i.get("status") == "failed")
            await send_email(
                to=to, kind="mod_ppm_certificate", organization_id=BFPO_ORG_ID,
                subject=f"PPM service certificate available — {svc.get('site_name')} ({svc.get('reference')})",
                html=f"""<p>Dear {site.get('contact_name') or 'Site contact'},</p>
                <p>The planned maintenance service at <strong>{svc.get('site_name')}</strong>
                ({svc.get('territory_name')}, {svc.get('country')}) is complete.</p>
                <p>{svc.get('asset_count')} asset(s) inspected · {failed} fault(s) raised.
                Reference <strong>{svc.get('reference')}</strong>.</p>
                <p>Your service certificate is now available to view in your MOD Service Operations
                portal documents.</p>
                <p>— Pulse Fitness MOD Operations</p>""")
            emailed_to = to
        except Exception:
            logger.exception("PPM cert email failed")
    await db.bfpo_ppm_services.update_one(
        {"id": service_id, "organization_id": BFPO_ORG_ID},
        {"$set": {"status": "completed", "completed_at": _now(),
                  "completed_by": user.get("full_name") or user.get("email"),
                  "certificate_doc_id": doc_id, "cert_emailed_to": emailed_to,
                  "notes": (data.get("notes") or "").strip()}})
    return {"ok": True, "certificate_doc_id": doc_id, "emailed_to": emailed_to,
            "certificate_url": f"/api/bfpo/ppm/services/{service_id}/certificate.pdf"}


@router.get("/services/{service_id}/certificate.pdf")
async def certificate_pdf(service_id: str, user=Depends(_require_bfpo)):
    svc = await _load_service(user, service_id)
    insp = await db.bfpo_ppm_inspections.find(
        {"service_id": service_id, "organization_id": BFPO_ORG_ID}, {"_id": 0}).to_list(1000)
    pdf = _build_certificate_pdf(svc, insp, user)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="PPM {svc.get("reference")}.pdf"'})


def _build_certificate_pdf(svc: dict, inspections: list, user: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    cyan = colors.HexColor("#0891b2")
    ink = colors.HexColor("#0f172a")
    c.setFillColor(ink)
    c.rect(0, h - 30 * mm, w, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(18 * mm, h - 18 * mm, "PULSE FITNESS")
    c.setFillColor(cyan)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, h - 24 * mm, "MOD / BFPO — Planned Maintenance Service Certificate")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - 18 * mm, h - 20 * mm, svc.get("reference") or "")

    y = h - 40 * mm
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(18 * mm, y, svc.get("site_name") or "Site")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(18 * mm, y, f"{svc.get('territory_name') or ''} · {svc.get('country') or ''}   |   "
                             f"Completed {(svc.get('completed_at') or _now())[:10]}   |   "
                             f"Engineer: {svc.get('assigned_engineer_name') or (user.get('full_name') or '')}")
    y -= 10 * mm
    total = len(inspections)
    passed = sum(1 for i in inspections if i.get("status") == "passed")
    failed = sum(1 for i in inspections if i.get("status") == "failed")
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18 * mm, y, f"Assets inspected: {total}    Passed: {passed}    Faults raised: {failed}")
    y -= 8 * mm
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(18 * mm, y, w - 18 * mm, y)
    y -= 8 * mm

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(18 * mm, y, "ASSET")
    c.drawString(120 * mm, y, "SERIAL")
    c.drawString(165 * mm, y, "RESULT")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    for i in inspections:
        if y < 25 * mm:
            c.showPage(); y = h - 25 * mm
        c.setFillColor(ink)
        c.drawString(18 * mm, y, str(i.get("equipment_name") or "")[:52])
        c.drawString(120 * mm, y, str(i.get("serial") or "")[:18])
        res = i.get("status") or "pending"
        c.setFillColor(colors.HexColor("#dc2626") if res == "failed" else colors.HexColor("#059669") if res == "passed" else colors.HexColor("#64748b"))
        label = "FAULT" + (f" ({i.get('fault_reference')})" if i.get("fault_reference") else "") if res == "failed" else res.upper()
        c.drawString(165 * mm, y, label)
        y -= 6 * mm

    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 7)
    c.drawString(18 * mm, 12 * mm, f"Generated {_now()[:16].replace('T', ' ')} · Pulse Fitness Ltd · MOD/BFPO Planned Maintenance")
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = ["router", "site_portal_router", "DEFAULT_TEMPLATES", "_items"]


# ─────────────────────────────────────────────────────────────────
# Recurring auto-scheduling (quarterly / annual per site)
# ─────────────────────────────────────────────────────────────────

_FREQ_MONTHS = {"quarterly": 3, "annual": 12}


def _add_months(iso_date: str, months: int) -> str:
    from datetime import date
    y, m, d = (int(x) for x in iso_date[:10].split("-"))
    m2 = m - 1 + months
    y += m2 // 12
    m = m2 % 12 + 1
    for dd in (d, 28):
        try:
            return date(y, m, dd).isoformat()
        except ValueError:
            continue
    return date(y, m, 28).isoformat()


@router.get("/schedules")
async def list_schedules(user=Depends(_require_staff)):
    sites = await db.sites.find({"organization_id": BFPO_ORG_ID}, {"_id": 0}).sort("name", 1).to_list(500)
    return {"schedules": [{"site_id": s["id"], "site_name": s.get("name"),
                           "territory_name": s.get("territory_name"),
                           "frequency": s.get("ppm_frequency") or "none",
                           "next_due": s.get("ppm_next_due") or ""} for s in sites]}


@router.post("/schedules")
async def set_schedule(data: dict = Body(...), user=Depends(_require_staff)):
    site_id = data.get("site_id")
    freq = (data.get("frequency") or "none").lower()
    if freq not in ("none", "quarterly", "annual"):
        raise HTTPException(400, "frequency must be none | quarterly | annual")
    site = await db.sites.find_one({"id": site_id, "organization_id": BFPO_ORG_ID}, {"_id": 0})
    if not site:
        raise HTTPException(404, "Site not found")
    upd = {"ppm_frequency": freq}
    if freq != "none":
        upd["ppm_next_due"] = data.get("next_due") or _today()
    await db.sites.update_one({"id": site_id, "organization_id": BFPO_ORG_ID}, {"$set": upd})
    return {"ok": True}


async def _run_autoschedule() -> dict:
    """For each site whose schedule is due, create a 'due' PPM service (unless one
    is already open) and advance next_due by the cadence. Idempotent per day."""
    today = _today()
    created, advanced = [], 0
    sites = await db.sites.find(
        {"organization_id": BFPO_ORG_ID, "ppm_frequency": {"$in": list(_FREQ_MONTHS.keys())}}, {"_id": 0},
    ).to_list(500)
    for s in sites:
        nxt = s.get("ppm_next_due") or today
        if nxt[:10] > today:
            continue
        open_exists = await db.bfpo_ppm_services.find_one(
            {"organization_id": BFPO_ORG_ID, "site_id": s["id"], "status": {"$ne": "completed"}}, {"_id": 0, "id": 1})
        if not open_exists:
            svc = await _spawn_service(s, due_date=nxt, source="auto-schedule")
            if svc:
                created.append(svc["reference"])
        new_next = _add_months(nxt, _FREQ_MONTHS[s["ppm_frequency"]])
        while new_next <= today:
            new_next = _add_months(new_next, _FREQ_MONTHS[s["ppm_frequency"]])
        await db.sites.update_one({"id": s["id"], "organization_id": BFPO_ORG_ID},
                                  {"$set": {"ppm_next_due": new_next, "ppm_last_generated": _now()}})
        advanced += 1
    logger.info("PPM autoschedule: created=%s advanced=%s", created, advanced)
    return {"created": created, "sites_advanced": advanced}


@router.post("/cron/autoschedule")
async def cron_autoschedule(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    import hmac
    import os as _os
    import asyncio as _asyncio
    secret = _os.environ.get("WEBHOOK_CRON_SECRET")
    auth = request.headers.get("authorization") or ""
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(status_code=401, detail="unauthorized")
    _asyncio.create_task(_run_autoschedule())
    return {"accepted": True}


# ─────────────────────────────────────────────────────────────────
# Site-facing view — surfaces PPM in the MODService portal under
# Faults > Planned Preventative Maintenance. Matches the caller's site.
# ─────────────────────────────────────────────────────────────────

site_portal_router = APIRouter(prefix="/mod/site", tags=["MOD · BFPO PPM (site portal)"])


@site_portal_router.get("/ppm")
async def site_portal_ppm(site_name: str = "", site_id: str = "", user=Depends(get_current_user)):
    """PPM services for a site, for display in the MODService site portal.
    Keyed by site_id or site_name so it lines up with the site's own record."""
    q = {"organization_id": BFPO_ORG_ID}
    if site_id:
        q["site_id"] = site_id
    elif site_name:
        q["site_name"] = site_name
    else:
        return {"services": []}
    rows = await db.bfpo_ppm_services.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    for s in rows:
        insp = await db.bfpo_ppm_inspections.find(
            {"service_id": s["id"], "organization_id": BFPO_ORG_ID}, {"_id": 0, "status": 1}).to_list(1000)
        s["progress"] = _progress(insp)
        s["certificate_url"] = (f"/api/bfpo/ppm/services/{s['id']}/certificate.pdf"
                                if s.get("status") == "completed" else "")
    return {"services": rows}
