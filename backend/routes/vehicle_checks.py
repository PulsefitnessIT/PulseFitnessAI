"""Vehicle Check feature — Pulse Fitness weekly driver vehicle inspections.

ENTER ONCE → USE EVERYWHERE: drivers are `staff_members`, vehicle registrations
sync to/from engineer profiles (engineers.vehicle_reg), and defects raise a
maintenance record + manager notification. No data is re-keyed.

Two official check templates (verbatim from Pulse forms):
  • van_maintenance  — Vanarama vans (breakdown contacts, no EV section)
  • vehicle_check    — company vehicles (adds Safety Equipment + EV, tax/insurance)
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from utils.auth import get_current_user, get_current_user_portal, verify_token
from utils.database import APP_NAME, db, get_object, put_object
from routes.staffing import _org, _require_manager
from routes.staff_portal import _line_manager_user_id, _portal_staff, notify_staff

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────── Official templates ────────────────────────────
def _section(key: str, title: str, labels: list[str]) -> dict:
    return {"key": key, "title": title,
            "items": [{"id": f"{key}_{i}", "label": lab} for i, lab in enumerate(labels)]}


_EXTERIOR_VAN = [
    "Tyres — tread at least 1.6mm; no cuts, bulges or visible damage; pressures correct.",
    "Wheels — no cracks or obvious damage; wheel nuts appear secure.",
    "Lights & reflectors — headlights, indicators, brake, reverse and hazard lights working and clean.",
    "Mirrors & windows — secure, clean and free from damage that affects the driver's view.",
    "Wipers & washers — operate correctly and screen wash is sufficient.",
    "Number plates — secure, clean and legible.",
    "Bodywork, doors & locks — no loose/sharp/dangerous damage; doors close and secure correctly.",
    "Ground/leak check — no obvious fuel, oil, coolant or brake-fluid leaks under the vehicle.",
]
_EXTERIOR_VEHICLE = _EXTERIOR_VAN + [
    "Glass / windscreen — no cracks, chips or damage that obstructs or impairs the driver's view.",
]
_UNDER_BONNET = [
    "Engine oil — correct level and no obvious contamination/leakage.",
    "Coolant — correct level when safe to check; no obvious leakage.",
    "Brake fluid — correct level.",
    "Battery — secure with no obvious damage or heavy corrosion.",
    "Screen wash — filled to a suitable level.",
]
_INTERIOR = [
    "Seat belts — latch and retract correctly; no obvious damage.",
    "Dashboard — no unexplained warning lights or warning messages.",
    "Horn — working.",
    "Brakes — effective with no unusual feel, noise or pulling.",
    "Handbrake / parking brake — operates and holds the vehicle securely.",
    "Steering & clutch — operate normally with no unusual noises or excessive play.",
    "Heating, ventilation & demisting — working sufficiently for safe visibility.",
    "Fuel / AdBlue / charge — sufficient for planned work and no related warnings.",
    "Load / luggage area, racking, tools & stock — secure; nothing likely to move or create a hazard.",
    "Interior / load area — reasonably clean and clear; supplied safety equipment is present and serviceable.",
]
_SAFETY_TECH = [
    "Hands-free equipment — available and working where fitted / required.",
    "Sat Nav / navigation equipment — secure and working where supplied.",
    "First Aid Kit — present, accessible and serviceable where supplied / required.",
    "Fire Extinguisher — present, secure and in serviceable condition where supplied / required.",
    "Vehicle is clean and tidy — interior and storage areas are reasonably clear and safe.",
]
_EV = [
    "Charging cable & connector — present where supplied, no cuts, damage, exposed conductors or excessive wear.",
    "Charge port / flap — clean, undamaged and closes / secures correctly.",
    "EV dashboard / battery system — no unexplained warning lights or charging-system fault messages.",
    "Charging cable storage — cable and any adapters are stored securely and cannot move around the vehicle.",
    "Home charging lead / portable lead (if used) — visually checked before use; plugs and connectors show no obvious damage.",
]


def _build_template(check_type: str, is_ev: bool) -> dict:
    if check_type == "van_maintenance":
        sections = [
            _section("exterior", "Exterior", _EXTERIOR_VAN),
            _section("under_bonnet", "Under the Bonnet", _UNDER_BONNET),
            _section("interior", "Interior & Operation", _INTERIOR),
        ]
        photos = ["Cab", "Nearside", "Offside", "Rear"]
        provider_label = "Vanarama"
        declaration = ("I confirm that I have completed the vehicle checks and reported all known "
                       "defects. If the vehicle appears unsafe or unroadworthy, I will not drive it "
                       "until advice or repair confirms it is safe.")
    else:
        sections = [
            _section("exterior", "Exterior", _EXTERIOR_VEHICLE),
            _section("under_bonnet", "Under the Bonnet", _UNDER_BONNET),
            _section("interior", "Interior & Operation", _INTERIOR),
            _section("safety_tech", "Safety Equipment & Technology", _SAFETY_TECH),
        ]
        if is_ev:
            sections.append(_section("ev", "Electric Vehicle Checks", _EV))
        photos = ["Interior/Cab", "Nearside", "Offside", "Front", "Rear"]
        provider_label = "Provider / garage"
        declaration = ("I confirm that I have completed this weekly vehicle check and reported all "
                       "known defects. If the vehicle appears unsafe or unroadworthy, I will not "
                       "drive it until advice or repair confirms it is safe.")
    return {
        "check_type": check_type,
        "title": "Van Maintenance — Weekly Vehicle Check" if check_type == "van_maintenance"
                 else "Weekly Company Vehicle Check",
        "sections": sections,
        "photo_slots": photos,
        "provider_label": provider_label,
        "declaration": declaration,
        "is_ev": is_ev,
    }


def _all_item_ids(template: dict) -> list[str]:
    return [it["id"] for s in template["sections"] for it in s["items"]]


CHECK_TYPES = {"van_maintenance", "vehicle_check"}


# ──────────────────────────────── Helpers ────────────────────────────────
def _week_commencing(d: date | None = None) -> str:
    d = d or date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(doc: dict | None) -> dict | None:
    if doc:
        doc.pop("_id", None)
    return doc


async def _sync_engineer_reg(org: str, staff_id: str | None, reg: str | None) -> None:
    """Feed a vehicle's registration into the engineer profile (if the driver is
    an engineer) so the Service Desk never holds a stale/duplicate reg."""
    if not staff_id or not reg:
        return
    sm = await db.staff_members.find_one({"organization_id": org, "id": staff_id}, {"_id": 0, "user_id": 1})
    uid = (sm or {}).get("user_id")
    if not uid:
        return
    await db.engineers.update_one(
        {"organization_id": org, "user_id": uid}, {"$set": {"vehicle_reg": reg}})


async def _this_week_status(org: str, vehicle_id: str, week: str) -> dict:
    doc = await db.vehicle_checks.find_one(
        {"organization_id": org, "vehicle_id": vehicle_id, "week_commencing": week}, {"_id": 0})
    if not doc:
        return {"status": "due", "has_defects": False, "check_id": None}
    return {"status": doc.get("status", "in_progress"),
            "has_defects": bool(doc.get("has_defects")),
            "check_id": doc.get("id")}


# Weekly checks are due by Friday (per the Pulse van form). From Friday onward
# an outstanding check is "overdue" and gets escalated to the line manager.
CHASE_FROM_WEEKDAY = 4  # Monday=0 … Friday=4


def _is_chase_time() -> bool:
    return date.today().weekday() >= CHASE_FROM_WEEKDAY


async def run_vehicle_chase(org: str) -> None:
    """Opportunistic missed-check chaser (no cron): from Friday, escalate every
    still-outstanding weekly vehicle check to the driver's line manager, once per
    vehicle per week (deduped). Fires whenever a driver or manager opens their
    notifications — idempotent."""
    if not _is_chase_time():
        return
    week = _week_commencing()
    vehicles = await db.vehicles.find(
        {"organization_id": org, "active": {"$ne": False}}, {"_id": 0}).to_list(1000)
    if not vehicles:
        return
    veh_ids = [v["id"] for v in vehicles]
    done = set(await db.vehicle_checks.distinct(
        "vehicle_id", {"organization_id": org, "week_commencing": week,
                       "vehicle_id": {"$in": veh_ids},
                       "status": {"$in": ["submitted", "reviewed"]}}))
    staff = await db.staff_members.find(
        {"organization_id": org},
        {"_id": 0, "id": 1, "full_name": 1, "line_manager_staff_id": 1, "user_id": 1}).to_list(2000)
    smap = {s["id"]: s for s in staff}
    for v in vehicles:
        if v["id"] in done:
            continue
        drivers = v.get("driver_staff_ids") or []
        primary = v.get("primary_driver_staff_id") or (drivers[0] if drivers else None)
        mgr_uid = None
        if primary and smap.get(primary):
            lm_sid = smap[primary].get("line_manager_staff_id")
            if lm_sid and smap.get(lm_sid):
                mgr_uid = smap[lm_sid].get("user_id")
        driver_names = ", ".join(smap[s]["full_name"] for s in drivers if smap.get(s)) or "unassigned"
        await notify_staff(
            org=org, recipient_kind="manager", recipient_user_id=mgr_uid,
            type="vehicle_check_overdue",
            title="Vehicle check overdue",
            body=f"{v['reg_no']} ({driver_names}) still has no completed check for the week of {week}.",
            link="vehicles",
            dedupe_key=f"veh_chase:{v['id']}:{week}")



# ════════════════════════════ Templates endpoint ════════════════════════════
@router.get("/vehicle-checks/templates")
async def vehicle_templates(user: dict = Depends(get_current_user)):
    return {
        "van_maintenance": _build_template("van_maintenance", False),
        "vehicle_check": _build_template("vehicle_check", False),
        "vehicle_check_ev": _build_template("vehicle_check", True),
    }


# ═══════════════════════════ Vehicle registry (mgr) ═══════════════════════════
class VehicleBody(BaseModel):
    reg_no: str
    make_model: str = ""
    check_type: str = "vehicle_check"
    is_ev: bool = False
    provider: str = ""
    driver_staff_ids: list[str] = []
    primary_driver_staff_id: str | None = None
    odometer: str = ""
    service_record: dict = {}
    notes: str = ""


@router.get("/vehicles")
async def list_vehicles(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    week = _week_commencing()
    rows = await db.vehicles.find({"organization_id": org, "active": {"$ne": False}}, {"_id": 0}).sort("reg_no", 1).to_list(500)
    staff = await db.staff_members.find({"organization_id": org}, {"_id": 0, "id": 1, "full_name": 1}).to_list(2000)
    names = {s["id"]: s.get("full_name") for s in staff}
    for r in rows:
        r["driver_names"] = [names.get(sid) for sid in (r.get("driver_staff_ids") or []) if names.get(sid)]
        r["this_week"] = await _this_week_status(org, r["id"], week)
    return {"vehicles": rows, "week_commencing": week}


@router.post("/vehicles")
async def create_vehicle(body: VehicleBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    if body.check_type not in CHECK_TYPES:
        raise HTTPException(400, "invalid check_type")
    reg = body.reg_no.strip().upper()
    if not reg:
        raise HTTPException(400, "Registration is required.")
    primary = body.primary_driver_staff_id or (body.driver_staff_ids[0] if body.driver_staff_ids else None)
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org, "active": True,
        "reg_no": reg, "make_model": body.make_model.strip(),
        "check_type": body.check_type, "is_ev": bool(body.is_ev),
        "provider": body.provider.strip() or ("Vanarama" if body.check_type == "van_maintenance" else ""),
        "driver_staff_ids": body.driver_staff_ids,
        "primary_driver_staff_id": primary,
        "odometer": body.odometer.strip(),
        "service_record": body.service_record or {},
        "notes": body.notes.strip(),
        "created_at": _now(),
    }
    await db.vehicles.insert_one(doc.copy())
    await _sync_engineer_reg(org, primary, reg)
    return _clean(doc)


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: str, body: VehicleBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    if body.check_type not in CHECK_TYPES:
        raise HTTPException(400, "invalid check_type")
    reg = body.reg_no.strip().upper()
    primary = body.primary_driver_staff_id or (body.driver_staff_ids[0] if body.driver_staff_ids else None)
    upd = {
        "reg_no": reg, "make_model": body.make_model.strip(),
        "check_type": body.check_type, "is_ev": bool(body.is_ev),
        "provider": body.provider.strip(),
        "driver_staff_ids": body.driver_staff_ids,
        "primary_driver_staff_id": primary,
        "odometer": body.odometer.strip(),
        "service_record": body.service_record or {},
        "notes": body.notes.strip(),
        "updated_at": _now(),
    }
    r = await db.vehicles.update_one({"organization_id": org, "id": vehicle_id}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "vehicle not found")
    await _sync_engineer_reg(org, primary, reg)
    return {"ok": True}


@router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    await db.vehicles.update_one({"organization_id": org, "id": vehicle_id}, {"$set": {"active": False}})
    return {"ok": True}


@router.get("/vehicles/driver-options")
async def driver_options(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    staff = await db.staff_members.find(
        {"organization_id": org, "active": {"$ne": False}},
        {"_id": 0, "id": 1, "full_name": 1, "department": 1, "job_title": 1}).sort("full_name", 1).to_list(2000)
    return {"drivers": staff}


@router.get("/vehicles/import-candidates")
async def import_candidates(user: dict = Depends(get_current_user)):
    """Engineers who already have a vehicle_reg on their Service Desk profile that
    isn't yet in the vehicle register — link, don't re-key."""
    _require_manager(user)
    org = _org(user)
    existing = set(v.get("reg_no") for v in await db.vehicles.find(
        {"organization_id": org, "active": {"$ne": False}}, {"_id": 0, "reg_no": 1}).to_list(500))
    engs = await db.engineers.find(
        {"organization_id": org, "vehicle_reg": {"$nin": ["", None]}},
        {"_id": 0, "user_id": 1, "vehicle_reg": 1, "full_name": 1}).to_list(500)
    out = []
    for e in engs:
        reg = (e.get("vehicle_reg") or "").strip().upper()
        if not reg or reg in existing:
            continue
        sm = await db.staff_members.find_one({"organization_id": org, "user_id": e.get("user_id")}, {"_id": 0, "id": 1, "full_name": 1})
        out.append({"reg_no": reg, "engineer_name": e.get("full_name") or (sm or {}).get("full_name"),
                    "staff_id": (sm or {}).get("id")})
    return {"candidates": out}


class ImportBody(BaseModel):
    items: list[dict] = []  # [{reg_no, staff_id, check_type?}]


@router.post("/vehicles/import")
async def import_vehicles(body: ImportBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    created = 0
    for it in body.items:
        reg = (it.get("reg_no") or "").strip().upper()
        if not reg:
            continue
        if await db.vehicles.find_one({"organization_id": org, "reg_no": reg, "active": {"$ne": False}}):
            continue
        sid = it.get("staff_id")
        await db.vehicles.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "active": True,
            "reg_no": reg, "make_model": it.get("make_model", ""),
            "check_type": it.get("check_type", "van_maintenance"),
            "is_ev": False, "provider": "Vanarama" if it.get("check_type", "van_maintenance") == "van_maintenance" else "",
            "driver_staff_ids": [sid] if sid else [],
            "primary_driver_staff_id": sid, "odometer": "", "service_record": {},
            "notes": "Imported from engineer profile", "created_at": _now(),
        })
        created += 1
    return {"ok": True, "created": created}


# ═══════════════════════════ Defect tracker (mgr) ═══════════════════════════
DEFECT_STATES = {"open", "booked_in", "resolved"}


def _days_until(iso: str | None) -> int | None:
    """Days from today to an ISO/UK date string; None if unparseable."""
    if not iso:
        return None
    s = str(iso).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return (datetime.strptime(s, fmt).date() - date.today()).days
        except ValueError:
            continue
    return None


@router.get("/vehicle-checks/dashboard")
async def fleet_dashboard(user: dict = Depends(get_current_user)):
    """One-glance fleet compliance: this week's check completion, open defects,
    and upcoming MOT / tax / insurance / service dates — all from existing data."""
    _require_manager(user)
    org = _org(user)
    week = _week_commencing()
    vehicles = await db.vehicles.find(
        {"organization_id": org, "active": {"$ne": False}}, {"_id": 0}).to_list(1000)
    total = len(vehicles)
    veh_ids = [v["id"] for v in vehicles]

    done_ids = set(await db.vehicle_checks.distinct(
        "vehicle_id", {"organization_id": org, "week_commencing": week,
                       "vehicle_id": {"$in": veh_ids},
                       "status": {"$in": ["submitted", "reviewed"]}}))
    submitted = len(done_ids)
    reviewed = await db.vehicle_checks.count_documents(
        {"organization_id": org, "week_commencing": week, "vehicle_id": {"$in": veh_ids},
         "status": "reviewed"})
    pct = round((submitted / total) * 100) if total else 0

    open_defects = await db.vehicle_defects.count_documents({"organization_id": org, "status": "open"})
    booked_defects = await db.vehicle_defects.count_documents({"organization_id": org, "status": "booked_in"})
    not_safe = await db.vehicle_defects.count_documents(
        {"organization_id": org, "status": {"$in": ["open", "booked_in"]}, "safe_to_drive": False})

    outstanding = [
        {"id": v["id"], "reg_no": v["reg_no"], "make_model": v.get("make_model"),
         "driver_names": [], "check_type": v.get("check_type")}
        for v in vehicles if v["id"] not in done_ids
    ]
    # driver names for the outstanding list
    if outstanding:
        staff = await db.staff_members.find({"organization_id": org}, {"_id": 0, "id": 1, "full_name": 1}).to_list(2000)
        names = {s["id"]: s.get("full_name") for s in staff}
        vmap = {v["id"]: v for v in vehicles}
        for o in outstanding:
            o["driver_names"] = [names.get(sid) for sid in (vmap[o["id"]].get("driver_staff_ids") or []) if names.get(sid)]

    # upcoming legal dates within 60 days (or overdue)
    expiries = []
    for v in vehicles:
        sr = v.get("service_record") or {}
        for key, label in (("mot_due", "MOT"), ("tax_status", "Tax"),
                           ("insurance_expiry", "Insurance"), ("next_service", "Service")):
            d = _days_until(sr.get(key))
            if d is not None and d <= 60:
                expiries.append({"reg_no": v["reg_no"], "make_model": v.get("make_model"),
                                 "kind": label, "date": sr.get(key), "days": d})
    expiries.sort(key=lambda x: x["days"])

    return {
        "week_commencing": week, "total_vehicles": total,
        "checks_done": submitted, "checks_reviewed": reviewed, "checks_pct": pct,
        "open_defects": open_defects, "booked_defects": booked_defects, "not_safe": not_safe,
        "outstanding": outstanding, "expiries": expiries,
    }


@router.get("/vehicle-defects")
async def list_defects(status: str | None = Query(None), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    q: dict = {"organization_id": org}
    if status in DEFECT_STATES:
        q["status"] = status
    rows = await db.vehicle_defects.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    counts = {
        s: await db.vehicle_defects.count_documents({"organization_id": org, "status": s})
        for s in ("open", "booked_in", "resolved")
    }
    return {"defects": rows, "counts": counts}


class DefectUpdate(BaseModel):
    status: str
    booking_ref: str | None = None
    booking_date: str | None = None
    note: str | None = None


@router.patch("/vehicle-defects/{defect_id}")
async def update_defect(defect_id: str, body: DefectUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    if body.status not in DEFECT_STATES:
        raise HTTPException(400, "invalid status")
    doc = await db.vehicle_defects.find_one({"organization_id": org, "id": defect_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "defect not found")
    now = _now()
    upd: dict = {"status": body.status, "updated_at": now, "updated_by": user.get("email")}
    if body.status == "booked_in":
        upd["booked_at"] = now
        if body.booking_ref is not None:
            upd["booking_ref"] = body.booking_ref.strip()
        if body.booking_date is not None:
            upd["booking_date"] = body.booking_date.strip()
    if body.status == "resolved":
        upd["resolved_at"] = now
        if body.note is not None:
            upd["resolved_note"] = body.note.strip()
    await db.vehicle_defects.update_one({"organization_id": org, "id": defect_id}, {"$set": upd})
    return {"ok": True, "status": body.status}


# ═══════════════════════ Weekly register + review (mgr) ═══════════════════════
@router.get("/vehicle-checks/register")
async def check_register(week: str | None = Query(None), status: str | None = Query(None),
                         user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    q: dict = {"organization_id": org}
    if week:
        q["week_commencing"] = week
    if status:
        q["status"] = status
    rows = await db.vehicle_checks.find(q, {"_id": 0}).sort("week_commencing", -1).to_list(1000)
    return {"checks": rows}


@router.get("/vehicle-checks/export.csv")
async def export_csv(week: str | None = Query(None), user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    q: dict = {"organization_id": org}
    if week:
        q["week_commencing"] = week
    rows = await db.vehicle_checks.find(q, {"_id": 0}).sort("week_commencing", -1).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Week", "Reg", "Make/Model", "Check type", "Driver", "Status",
                "Defects", "Safe to drive", "Odometer", "Submitted", "Reviewed by"])
    for r in rows:
        rv = r.get("manager_review") or {}
        df = r.get("defect") or {}
        w.writerow([
            r.get("week_commencing"), (r.get("details") or {}).get("reg_no"),
            (r.get("details") or {}).get("make_model"), r.get("check_type"),
            r.get("driver_name"), r.get("status"),
            "Yes" if r.get("has_defects") else "No",
            {True: "Yes", False: "No"}.get(df.get("safe_to_drive"), ""),
            (r.get("details") or {}).get("odometer"),
            r.get("submitted_at", ""), rv.get("reviewer", ""),
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=vehicle-checks-{week or 'all'}.csv"})


FIT_LABEL = {"yes": "Fit to return", "phased": "Phased return", "no": "Not yet fit"}
ITEM_STATUS_LABEL = {"ok": "OK", "defect": "DEFECT", "na": "N/A"}


def _build_check_pdf(check: dict, template: dict, org_company: dict | None,
                     photos_bytes: list[bytes] | None = None) -> bytes:
    """Pulse-branded PDF of a completed weekly vehicle check for the H&S file."""
    import io as _io
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
    from utils.pulse_doc_template import (
        pulse_styles, pulse_header, pulse_title, section_label,
        make_pulse_doc, PULSE_NAVY, PULSE_BORDER, PULSE_LIGHT, PULSE_MUTED,
    )

    s = pulse_styles()
    buf = _io.BytesIO()
    doc = make_pulse_doc(buf, f"Vehicle Check {check.get('details', {}).get('reg_no', '')}", company=org_company)
    body = s["body"]
    story = [pulse_header(s, org_company)]
    story += pulse_title(s, template["title"],
                         f"Registration {check.get('details', {}).get('reg_no', '—')} · "
                         f"Week commencing {check.get('week_commencing', '—')}")
    story.append(Spacer(1, 6 * mm))

    det = check.get("details", {})
    mr = check.get("manager_review") or {}
    meta = [
        ["Driver", check.get("driver_name") or det.get("driver_name") or "—",
         "Make / model", det.get("make_model") or "—"],
        ["Odometer", det.get("odometer") or "—", "Check completed", check.get("submitted_at", "—")[:10] if check.get("submitted_at") else "—"],
        ["Status", (check.get("status") or "—").replace("_", " ").title(),
         "Reviewed by", mr.get("reviewer") or "Not yet reviewed"],
    ]
    mt = Table(meta, colWidths=[26 * mm, 60 * mm, 30 * mm, 58 * mm])
    mt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), PULSE_NAVY),
        ("TEXTCOLOR", (2, 0), (2, -1), PULSE_NAVY),
        ("BACKGROUND", (0, 0), (-1, -1), PULSE_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(mt)
    story.append(Spacer(1, 5 * mm))

    items = check.get("items") or {}
    for sec in template["sections"]:
        story.append(section_label(s, sec["title"]))
        rows = []
        for it in sec["items"]:
            st = items.get(it["id"], "")
            rows.append([Paragraph(it["label"], body), ITEM_STATUS_LABEL.get(st, "—")])
        t = Table(rows, colWidths=[150 * mm, 24 * mm])
        style = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
            ("FONT", (1, 0), (1, -1), "Helvetica-Bold", 8.5),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, PULSE_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, it in enumerate(sec["items"]):
            st = items.get(it["id"], "")
            if st == "defect":
                style.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#dc2626")))
            elif st == "ok":
                style.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#16a34a")))
            else:
                style.append(("TEXTCOLOR", (1, i), (1, i), PULSE_MUTED))
        t.setStyle(TableStyle(style))
        story.append(t)
        story.append(Spacer(1, 4 * mm))

    df = check.get("defect") or {}
    if check.get("has_defects") or df.get("details"):
        story.append(section_label(s, "Defects / corrective action"))
        yn = lambda v: "Yes" if v is True else "No" if v is False else "—"
        story.append(Paragraph(_esc(df.get("details") or "No description provided."), body))
        story.append(Spacer(1, 2 * mm))
        drow = [["Safe to drive", yn(df.get("safe_to_drive")), "Manager told", yn(df.get("manager_told")),
                 "Provider contacted", yn(df.get("provider_contacted")), "Repair booked", yn(df.get("repair_booked"))]]
        dt = Table(drow, colWidths=[24 * mm, 12 * mm, 22 * mm, 12 * mm, 30 * mm, 12 * mm, 22 * mm, 12 * mm])
        dt.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 8),
            ("TEXTCOLOR", (0, 0), (0, 0), PULSE_NAVY),
            ("BOX", (0, 0), (-1, -1), 0.5, PULSE_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(dt)
        story.append(Spacer(1, 4 * mm))

    if photos_bytes:
        story.append(section_label(s, "Defect photos"))
        cells = []
        for raw in photos_bytes:
            try:
                cells.append(Image(_io.BytesIO(raw), width=54 * mm, height=40 * mm, kind="proportional"))
            except Exception:
                continue
        if cells:
            per_row = 3
            rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
            for r in rows:
                while len(r) < per_row:
                    r.append("")
            pt = Table(rows, colWidths=[58 * mm] * per_row)
            pt.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(pt)
            story.append(Spacer(1, 3 * mm))

    decl = check.get("declaration") or {}
    story.append(section_label(s, "Driver declaration"))
    story.append(Paragraph(_esc(template.get("declaration", "")), body))
    story.append(Spacer(1, 2 * mm))
    sig = f"Signed: <b>{_esc(decl.get('driver_name') or check.get('driver_name') or '—')}</b> · {(decl.get('at') or '')[:19].replace('T', ' ')}"
    story.append(Paragraph(sig, body))
    if mr.get("reviewer"):
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph(f"Manager review: <b>{_esc(mr.get('reviewer'))}</b> · {(mr.get('at') or '')[:19].replace('T', ' ')}"
                               + (f" — {_esc(mr.get('notes'))}" if mr.get("notes") else ""), body))

    doc.build(story)
    return buf.getvalue()


def _esc(text) -> str:
    return (str(text or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@router.get("/vehicle-checks/{check_id}/pdf")
async def check_pdf(check_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    doc = await db.vehicle_checks.find_one({"organization_id": org, "id": check_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    template = _build_template(doc.get("check_type", "vehicle_check"), doc.get("is_ev", False))
    # Pull uploaded defect photos from object storage so the PDF is self-contained.
    photos_bytes: list[bytes] = []
    photo_ids = ((doc.get("photos") or {}).get("defect")) or []
    for fid in photo_ids[:9]:
        try:
            f = await db.files.find_one({"id": fid, "organization_id": org, "category": "vehicle-photos"}, {"_id": 0})
            if f and f.get("storage_path"):
                data, _ = get_object(f["storage_path"])
                if data:
                    photos_bytes.append(data)
        except Exception:
            logger.warning("vehicle PDF: could not load photo %s", fid)
    try:
        pdf = _build_check_pdf(doc, template, None, photos_bytes)
    except Exception as e:
        logger.exception("vehicle check PDF failed")
        raise HTTPException(500, f"Could not generate PDF: {e}")
    reg = (doc.get("details") or {}).get("reg_no", "vehicle").replace(" ", "")
    fname = f"vehicle-check-{reg}-{doc.get('week_commencing', '')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})



@router.get("/vehicle-checks/{check_id}")
async def check_detail(check_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    doc = await db.vehicle_checks.find_one({"organization_id": org, "id": check_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    doc["template"] = _build_template(doc.get("check_type", "vehicle_check"), doc.get("is_ev", False))
    return doc


class ReviewBody(BaseModel):
    notes: str = ""


@router.post("/vehicle-checks/{check_id}/review")
async def review_check(check_id: str, body: ReviewBody, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org = _org(user)
    doc = await db.vehicle_checks.find_one({"organization_id": org, "id": check_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    if doc.get("status") != "submitted":
        raise HTTPException(400, "Only submitted checks can be reviewed.")
    await db.vehicle_checks.update_one(
        {"organization_id": org, "id": check_id},
        {"$set": {"status": "reviewed",
                  "manager_review": {"reviewer": user.get("email"), "at": _now(), "notes": body.notes.strip()}}})
    return {"ok": True}


# ═══════════════════════════ Staff Portal (driver) ═══════════════════════════
@router.get("/new-starter/portal/vehicles")
async def portal_vehicles(user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    week = _week_commencing()
    rows = await db.vehicles.find(
        {"organization_id": org, "active": {"$ne": False}, "driver_staff_ids": staff["id"]},
        {"_id": 0}).sort("reg_no", 1).to_list(100)
    for r in rows:
        r["this_week"] = await _this_week_status(org, r["id"], week)
    return {"vehicles": rows, "week_commencing": week, "driver_name": staff.get("full_name")}


@router.get("/new-starter/portal/vehicle-check")
async def portal_get_check(vehicle_id: str = Query(...), week: str | None = Query(None),
                           user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    week = week or _week_commencing()
    veh = await db.vehicles.find_one({"organization_id": org, "id": vehicle_id, "active": {"$ne": False}}, {"_id": 0})
    if not veh:
        raise HTTPException(404, "vehicle not found")
    if staff["id"] not in (veh.get("driver_staff_ids") or []):
        raise HTTPException(403, "This vehicle isn't assigned to you.")
    template = _build_template(veh.get("check_type", "vehicle_check"), veh.get("is_ev", False))
    existing = await db.vehicle_checks.find_one(
        {"organization_id": org, "vehicle_id": vehicle_id, "week_commencing": week}, {"_id": 0})
    if not existing:
        existing = {
            "vehicle_id": vehicle_id, "week_commencing": week,
            "check_type": veh.get("check_type"), "is_ev": veh.get("is_ev", False),
            "driver_staff_id": staff["id"], "driver_name": staff.get("full_name"),
            "details": {"reg_no": veh.get("reg_no"), "make_model": veh.get("make_model"),
                        "odometer": veh.get("odometer", ""), "date": date.today().isoformat()},
            "items": {}, "defect": {}, "photos": {"vehicle": {}, "defect": []},
            "declaration": {}, "status": "due",
        }
    return {"vehicle": veh, "template": template, "check": existing, "week_commencing": week}


class SaveCheckBody(BaseModel):
    vehicle_id: str
    week_commencing: str | None = None
    details: dict = {}
    items: dict = {}
    defect: dict = {}
    photos: dict = {}


async def _upsert_check(user, body: SaveCheckBody, submit: bool):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    week = body.week_commencing or _week_commencing()
    veh = await db.vehicles.find_one({"organization_id": org, "id": body.vehicle_id, "active": {"$ne": False}}, {"_id": 0})
    if not veh:
        raise HTTPException(404, "vehicle not found")
    if staff["id"] not in (veh.get("driver_staff_ids") or []):
        raise HTTPException(403, "This vehicle isn't assigned to you.")
    template = _build_template(veh.get("check_type", "vehicle_check"), veh.get("is_ev", False))
    all_ids = _all_item_ids(template)
    items = {k: v for k, v in (body.items or {}).items() if k in all_ids and v in ("ok", "defect", "na")}
    has_defects = any(v == "defect" for v in items.values())
    defect = body.defect or {}
    not_safe = defect.get("safe_to_drive") is False

    if submit:
        missing = [i for i in all_ids if i not in items]
        if missing:
            raise HTTPException(400, "Please answer every check item (OK / Defect / N/A) before submitting.")
        if not (body.details or {}).get("driver_name") and not staff.get("full_name"):
            raise HTTPException(400, "Driver name is required.")
        if (has_defects or not_safe) and not (defect.get("details") or "").strip():
            raise HTTPException(400, "Please describe the defect before submitting.")

    now = _now()
    existing = await db.vehicle_checks.find_one(
        {"organization_id": org, "vehicle_id": body.vehicle_id, "week_commencing": week}, {"_id": 0})
    set_doc = {
        "organization_id": org, "vehicle_id": body.vehicle_id, "week_commencing": week,
        "check_type": veh.get("check_type"), "is_ev": veh.get("is_ev", False),
        "driver_staff_id": staff["id"], "driver_name": staff.get("full_name"),
        "details": {**(body.details or {}),
                    "reg_no": veh.get("reg_no"), "make_model": veh.get("make_model")},
        "items": items, "defect": defect,
        "has_defects": has_defects or not_safe, "updated_at": now,
    }
    # Don't wipe previously-uploaded photos when a save omits them.
    incoming_photos = body.photos or {}
    if incoming_photos.get("vehicle") or incoming_photos.get("defect"):
        set_doc["photos"] = incoming_photos
    elif not existing:
        set_doc["photos"] = {"vehicle": {}, "defect": []}
    if submit:
        set_doc["status"] = "submitted"
        set_doc["submitted_at"] = now
        set_doc["declaration"] = {"confirmed": True, "driver_name": (body.details or {}).get("driver_name") or staff.get("full_name"), "at": now}
    else:
        set_doc.setdefault("status", "in_progress")
        if not existing or existing.get("status") not in ("submitted", "reviewed"):
            set_doc["status"] = "in_progress"

    if existing:
        await db.vehicle_checks.update_one(
            {"organization_id": org, "id": existing["id"]}, {"$set": set_doc})
        check_id = existing["id"]
    else:
        set_doc["id"] = str(uuid.uuid4())
        set_doc["created_at"] = now
        await db.vehicle_checks.insert_one(set_doc.copy())
        check_id = set_doc["id"]

    # sync latest odometer back to the vehicle record (single source of truth)
    odo = (body.details or {}).get("odometer")
    if odo:
        await db.vehicles.update_one({"organization_id": org, "id": body.vehicle_id}, {"$set": {"odometer": odo}})

    if submit and (has_defects or not_safe):
        # Raise a maintenance record + ping the line manager — no duplicate keying.
        await db.vehicle_defects.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "vehicle_id": body.vehicle_id,
            "check_id": check_id, "reg_no": veh.get("reg_no"), "make_model": veh.get("make_model"),
            "reported_by_staff_id": staff["id"], "reported_by": staff.get("full_name"),
            "details": defect.get("details", ""), "safe_to_drive": defect.get("safe_to_drive"),
            "provider": veh.get("provider", ""), "status": "open", "created_at": now,
        })
        mgr_uid = await _line_manager_user_id(org, staff)
        await notify_staff(
            org=org, recipient_kind="manager", recipient_user_id=mgr_uid,
            type="vehicle_defect",
            title=("⚠ Vehicle not safe to drive" if not_safe else "Vehicle defect reported"),
            body=f"{staff.get('full_name')} reported a defect on {veh.get('reg_no')} "
                 f"({veh.get('make_model') or veh.get('check_type')}): {(defect.get('details') or '').strip()[:120]}",
            link="vehicles")
    return {"ok": True, "check_id": check_id, "status": set_doc["status"], "has_defects": set_doc["has_defects"]}


@router.post("/new-starter/portal/vehicle-check/save")
async def portal_save_check(body: SaveCheckBody, user: dict = Depends(get_current_user_portal)):
    return await _upsert_check(user, body, submit=False)


@router.post("/new-starter/portal/vehicle-check/submit")
async def portal_submit_check(body: SaveCheckBody, user: dict = Depends(get_current_user_portal)):
    return await _upsert_check(user, body, submit=True)


@router.post("/new-starter/portal/vehicle-check/photo")
async def portal_upload_photo(file: UploadFile = File(...), user: dict = Depends(get_current_user_portal)):
    staff = await _portal_staff(user)
    org = staff["organization_id"]
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "heic", "heif"):
        raise HTTPException(415, "Please upload an image (JPG, PNG, WEBP or HEIC).")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Image too large — keep under 15MB.")
    ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
          "webp": "image/webp", "heic": "image/heic", "heif": "image/heif"}.get(ext, "image/jpeg")
    path = f"{APP_NAME}/vehicle-photos/{org}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ct)
    fid = str(uuid.uuid4())
    await db.files.insert_one({
        "id": fid, "user_id": user.get("id"), "organization_id": org,
        "category": "vehicle-photos", "storage_path": result["path"],
        "original_filename": file.filename, "content_type": ct,
        "size": result.get("size", len(data)), "created_at": _now(),
    })
    return {"file_id": fid}


@router.get("/vehicle-checks/photo/{file_id}")
async def vehicle_photo(file_id: str, authorization: str = Header(None), auth: str = Query(None)):
    """Dual-auth image serve (manager platform token OR driver portal token, via
    header or ?auth= query param so <img src> works)."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    payload = verify_token(token) if token else None
    if not payload:
        raise HTTPException(401, "unauthorised")
    viewer = await db.users.find_one({"id": payload.get("user_id")}, {"_id": 0, "organization_id": 1, "is_master_admin": 1})
    if not viewer:
        raise HTTPException(401, "unauthorised")
    doc = await db.files.find_one({"id": file_id, "category": "vehicle-photos"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    if not viewer.get("is_master_admin") and doc.get("organization_id") != viewer.get("organization_id"):
        raise HTTPException(403, "forbidden")
    data, ct = get_object(doc["storage_path"])
    return Response(content=data, media_type=doc.get("content_type", ct))
