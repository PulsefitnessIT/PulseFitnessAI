"""Master Admin · MOD Estate onboarding + whole-of-MOD reporting.

Model (per founder decision, 2026-07):
  • Army / RAF / Navy are each an INDEPENDENT service HQ (`account_type=mod_org`,
    `is_head_office=True`, `mod_root_id = self.id`). They have NO shared parent
    org — but they all carry the same `mod_estate_id` so we can report on the
    MOD *as a whole* across the three commands.
  • Sites (`account_type=mod_site`) hang under ONE service HQ via `mod_root_id`
    (= that HQ's id) and carry the estate id for rollups. Sites are GLOBAL:
    country + region + derived currency/locale.
  • Suppliers: UK sites are serviced by Pulse Fitness (no external supplier).
    OVERSEAS sites get ONE external service supplier assigned from an
    estate-level registry (`mod_estate_suppliers`); it is instantiated into
    the site's own supplier directory so the existing MOD fault-routing
    (`_resolve_equipment_supplier`) keeps working. Pulse Fitness is ALWAYS
    notified of faults regardless (handled in mod_portal.py).

This orchestrates — it does NOT replace — the existing CSV bulk importer
(`mod_sites_bulk_import.py` / `mod_bulk_import.py`), which still works per HQ.
"""
from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from utils.auth import get_current_user, hash_password
from utils.database import db
from routes.master_admin import (
    _generate_initial_password,
    _mint_invite_link,
    log_activity,
    merge_address,
    require_master_admin,
)

router = APIRouter()

DEFAULT_ESTATE_ID = "uk-mod"
DEFAULT_ESTATE_NAME = "UK Ministry of Defence"

# The three independent services. `force` is the canonical lowercase key
# already used across the codebase (mod_force, bulk importer branch aliases).
MOD_SERVICES = [
    {"force": "army", "label": "British Army", "branch": "Army"},
    {"force": "raf", "label": "Royal Air Force", "branch": "RAF"},
    {"force": "navy", "label": "Royal Navy", "branch": "Navy"},
]
_SERVICE_BY_FORCE = {s["force"]: s for s in MOD_SERVICES}

_UK_NAMES = {"united kingdom", "uk", "gb", "great britain", "england",
             "scotland", "wales", "northern ireland"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kebab(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-").lower()


def _hq_id(estate_id: str, force: str) -> str:
    return f"mod-hq-{estate_id}-{force}"


def _is_overseas(country: str) -> bool:
    return (country or "").strip().lower() not in _UK_NAMES


def _localization(body: dict) -> dict:
    from utils.localization import resolve_org_fields
    return resolve_org_fields(
        body.get("country_code"), body.get("currency"), body.get("timezone"),
    )


# ─────────────────────────── HQs (sections) ───────────────────────────


@router.post("/master-admin/mod-estate/hqs")
async def ensure_mod_hqs(data: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Idempotently create the three independent service HQs (Army / RAF /
    Navy) under a shared estate id. Re-running is safe — existing HQs are
    left untouched and reported back."""
    require_master_admin(user)
    estate_id = _kebab(data.get("estate_id") or DEFAULT_ESTATE_ID) or DEFAULT_ESTATE_ID
    estate_name = (data.get("estate_name") or DEFAULT_ESTATE_NAME).strip()
    overrides = data.get("services") or {}  # {force: {name, primary_contact_email, ...}}
    now = _now()
    result = []
    for svc in MOD_SERVICES:
        force = svc["force"]
        hq_id = _hq_id(estate_id, force)
        existing = await db.organizations.find_one({"id": hq_id}, {"_id": 0})
        ov = overrides.get(force) or {}
        if existing:
            result.append({"force": force, "id": hq_id, "name": existing.get("name"),
                           "created": False})
            continue
        name = (ov.get("name") or f"{svc['label']} — Head Office").strip()
        hq_doc = {
            "id": hq_id,
            "name": name,
            "account_type": "mod_org",
            "is_mod": True,
            "is_head_office": True,
            "mod_force": force,
            "mod_branch": svc["branch"],
            "mod_root_id": hq_id,          # independent root = itself
            "mod_estate_id": estate_id,
            "mod_estate_name": estate_name,
            "parent_organization_id": None,  # no shared parent (decision 1b)
            "enabled_modules": ["operations", "service_desk"],
            "portal_type": "service_portal",
            "subscription_tier": "mod",
            "status": "active",
            "created_at": now,
            "created_via": "mod_estate_wizard",
            "company_code": str(uuid.uuid4())[:8].upper(),
            "primary_contact_name": (ov.get("primary_contact_name") or "").strip(),
            "primary_contact_email": (ov.get("primary_contact_email") or "").strip().lower(),
            "primary_contact_phone": (ov.get("primary_contact_phone") or "").strip(),
            "branding": {"primary_color": "#19CDFF", "company_name": name},
        }
        await db.organizations.insert_one(hq_doc)
        result.append({"force": force, "id": hq_id, "name": name, "created": True})
    await log_activity("mod_estate.hqs_ensured",
                       f"Ensured MOD service HQs for estate '{estate_name}'",
                       user.get("email", "system"), "mod_estate", estate_id)
    return {"estate_id": estate_id, "estate_name": estate_name, "hqs": result}


# ─────────────────────── estate supplier registry ──────────────────────


@router.get("/master-admin/mod-estate/suppliers")
async def list_estate_suppliers(estate_id: str = DEFAULT_ESTATE_ID,
                                user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    estate_id = _kebab(estate_id) or DEFAULT_ESTATE_ID
    suppliers = await db.mod_estate_suppliers.find(
        {"mod_estate_id": estate_id}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    return {"estate_id": estate_id, "suppliers": suppliers}


@router.post("/master-admin/mod-estate/suppliers")
async def add_estate_supplier(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Register an external service supplier at estate level so it can be
    assigned to any number of OVERSEAS sites."""
    require_master_admin(user)
    estate_id = _kebab(data.get("estate_id") or DEFAULT_ESTATE_ID) or DEFAULT_ESTATE_ID
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Supplier name is required")
    email = (data.get("email") or "").strip().lower()
    supplier = {
        "id": str(uuid.uuid4()),
        "mod_estate_id": estate_id,
        "name": name,
        "contact_name": (data.get("contact_name") or "").strip(),
        "email": email,
        "phone": (data.get("phone") or "").strip(),
        "countries": [c.strip() for c in (data.get("countries") or []) if c and c.strip()],
        "regions": [r.strip() for r in (data.get("regions") or []) if r and r.strip()],
        "manufacturer_keywords": [k.strip() for k in (data.get("manufacturer_keywords") or []) if k and k.strip()],
        "notes": (data.get("notes") or "").strip(),
        "created_at": _now(),
    }
    await db.mod_estate_suppliers.insert_one({**supplier})
    supplier.pop("_id", None)
    return {"supplier": supplier}


# ───────────────────────────── add a site ─────────────────────────────


@router.post("/master-admin/mod-estate/sites")
async def create_mod_estate_site(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Create ONE MOD site under a chosen service HQ. Global (country +
    region + locale). Overseas sites get an external service supplier
    assigned from the estate registry; UK sites are Pulse-serviced."""
    require_master_admin(user)
    estate_id = _kebab(data.get("estate_id") or DEFAULT_ESTATE_ID) or DEFAULT_ESTATE_ID
    force = (data.get("force") or "").strip().lower()
    if force not in _SERVICE_BY_FORCE:
        raise HTTPException(400, "force must be one of: army, raf, navy")
    hq_id = _hq_id(estate_id, force)
    hq = await db.organizations.find_one({"id": hq_id}, {"_id": 0, "id": 1, "name": 1})
    if not hq:
        raise HTTPException(400, f"{_SERVICE_BY_FORCE[force]['label']} HQ not set up yet — run 'Set up service HQs' first")

    site_name = (data.get("site_name") or "").strip()
    if not site_name:
        raise HTTPException(400, "Site name is required")
    site_code = _kebab(data.get("site_code") or site_name)
    if not site_code:
        raise HTTPException(400, "Could not derive a site code")
    site_id = f"mod-site-{site_code}"
    if await db.organizations.find_one({"id": site_id}, {"_id": 0, "id": 1}):
        raise HTTPException(409, f"A site with code '{site_code}' already exists")

    country = (data.get("country") or "United Kingdom").strip()
    overseas = data.get("is_overseas")
    overseas = _is_overseas(country) if overseas is None else bool(overseas)
    region = (data.get("region") or "").strip()
    now = _now()

    # Resolve the external supplier for overseas sites.
    supplier_id_on_site = None
    supplier_name = None
    if overseas:
        est_sup_id = (data.get("service_supplier_id") or "").strip()
        if not est_sup_id:
            raise HTTPException(400, "Overseas sites require an external service supplier")
        est_sup = await db.mod_estate_suppliers.find_one(
            {"id": est_sup_id, "mod_estate_id": estate_id}, {"_id": 0},
        )
        if not est_sup:
            raise HTTPException(404, "Selected service supplier not found in the estate registry")
        # Instantiate the supplier into the site's own directory so the
        # existing per-site fault routing resolves it.
        supplier_id_on_site = str(uuid.uuid4())
        supplier_name = est_sup["name"]
        await db.suppliers.insert_one({
            "id": supplier_id_on_site,
            "organization_id": site_id,
            "name": est_sup["name"],
            "contact_name": est_sup.get("contact_name", ""),
            "email": est_sup.get("email", ""),
            "phone": est_sup.get("phone", ""),
            "manufacturer_keywords": est_sup.get("manufacturer_keywords", []),
            "notes": est_sup.get("notes", ""),
            "estate_supplier_id": est_sup_id,
            "created_at": now,
        })

    org_doc = {
        "id": site_id,
        "name": site_name,
        "account_type": "mod_site",
        "is_mod": True,
        "mod_root_id": hq_id,
        "mod_force": force,
        "mod_branch": _SERVICE_BY_FORCE[force]["branch"],
        "mod_estate_id": estate_id,
        "site_code": site_code,
        "parent_organization_id": hq_id,
        "is_overseas": overseas,
        "region": region,
        "enabled_modules": ["operations", "service_desk"],
        "portal_type": "service_portal",
        "subscription_tier": "lite",
        "status": "active",
        "created_at": now,
        "created_via": "mod_estate_wizard",
        "company_code": str(uuid.uuid4())[:8].upper(),
        **merge_address(data),
        "country": country,
        **_localization(data),
        "phone": (data.get("phone") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "site_manager_name": (data.get("site_manager_name") or "").strip(),
        "site_manager_email": (data.get("site_manager_email") or "").strip(),
        "oncall_phone": (data.get("oncall_phone") or "").strip(),
        "access_notes": (data.get("access_notes") or "").strip(),
        "service_supplier_id": supplier_id_on_site,
        "service_supplier": supplier_name,
        "serviced_by": "external_supplier" if overseas else "pulse_fitness",
        "branding": {"primary_color": "#19CDFF", "company_name": site_name},
    }
    await db.organizations.insert_one(org_doc)

    # ── Logins ──────────────────────────────────────────────────────
    # A MOD site gets TWO logins going forward:
    #   1. A GENERIC SHARED login (username = site_code) any site user can use
    #      day-to-day. Least-privilege role="site_staff" + is_shared_login so it
    #      CANNOT see Reports/figures, Staffing credentials or Settings.
    #   2. An individual OWNER login (their own email) with full visibility —
    #      created only when a real owner email is supplied. MOD owners rotate a
    #      lot, so ownership can later be handed over via the portal
    #      (/api/mod/site/transfer-owner).
    send_invite = bool(data.get("send_invite"))

    # 1) Generic shared login (restricted)
    shared_pwd = (data.get("password") or "").strip() or _generate_initial_password()
    shared_id = f"mod-user-{site_code}"
    await db.users.insert_one({
        "id": shared_id,
        "username": site_code,
        "email": f"{site_code}@site.mod.local",
        "full_name": f"{site_name} (shared login)",
        "organization_id": site_id,
        "role": "site_staff",
        "account_type": "mod_site",
        "mod_site_code": site_code,
        "is_username_login": True,
        "is_shared_site_login": True,
        "password": hash_password(shared_pwd),
        "password_updated_at": now,
        "created_at": now,
    })
    activation = {"mode": "password", "username": site_code,
                  "temporary_password": shared_pwd, "scope": "shared", "restricted": True}

    # 2) Individual owner login (full visibility) — only with a real owner email
    owner_email = (data.get("site_manager_email") or "").strip().lower()
    owner_name = (data.get("site_manager_name") or "").strip()
    owner_login = None
    if owner_email and "@" in owner_email and not owner_email.endswith("@site.mod.local"):
        owner_id = f"mod-owner-{site_code}"
        owner_doc = {
            "id": owner_id,
            "email": owner_email,
            "full_name": owner_name or owner_email.split("@")[0],
            "organization_id": site_id,
            "role": "owner",
            "account_type": "mod_site",
            "mod_site_code": site_code,
            "created_at": now,
        }
        if send_invite:
            owner_doc["password"] = None
            owner_doc["password_pending"] = True
            await db.users.insert_one(owner_doc)
            invite = await _mint_invite_link(owner_id, owner_email, user.get("email", "system"))
            owner_login = {"mode": "invite", "email": owner_email, "scope": "owner",
                           "invite_url": invite["invite_url"], "invite_expires_at": invite["expires_at"]}
        else:
            owner_pwd = _generate_initial_password()
            owner_doc["password"] = hash_password(owner_pwd)
            owner_doc["password_updated_at"] = now
            await db.users.insert_one(owner_doc)
            owner_login = {"mode": "password", "email": owner_email,
                           "temporary_password": owner_pwd, "scope": "owner"}

    await log_activity("mod_estate.site_created",
                       f"Created MOD site '{site_name}' ({force.upper()}, {'overseas' if overseas else 'UK'})",
                       user.get("email", "system"), "organization", site_id)

    return {
        "success": True,
        "site": {
            "id": site_id, "name": site_name, "site_code": site_code,
            "force": force, "hq_id": hq_id, "hq_name": hq.get("name"),
            "country": country, "region": region, "is_overseas": overseas,
            "serviced_by": org_doc["serviced_by"],
            "service_supplier": supplier_name,
        },
        "login": activation,
        "owner_login": owner_login,
    }


# ──────────────────── equipment onboarding template + readiness ────────────

# Canonical MOD equipment column spec — drives BOTH the presentable workbook
# and the machine-readable CSV. Headers match the bulk-import aliases exactly so
# a completed sheet uploads with zero remapping.
_MOD_EQUIP_FIELDS = [
    ("name", "Equipment name / description", "Yes", "Treadmill — Cardio Bay 3", ""),
    ("equipment_type", "Category", "Yes", "Treadmill", "Treadmill, Bike, Rower, Cross Trainer, Strength, Other"),
    ("manufacturer", "Make / brand", "Recommended", "Life Fitness", ""),
    ("model", "Model", "Recommended", "95T Discover SE3", ""),
    ("serial_number", "Serial number (dedupe key)", "Recommended", "LF-TM-001", ""),
    ("asset_number", "MOD asset number / NSN", "Optional", "NSN-7830-01-234-5678", ""),
    ("quantity", "Quantity (if identical & untagged)", "Optional", "1", "Whole number"),
    ("location", "Area / gym floor", "Recommended", "Main cardio hall", ""),
    ("sub_location", "Room / zone / rack", "Optional", "Bay 3", ""),
    ("condition", "Condition on handover", "Optional", "Good", "New, Good, Fair, Poor"),
    ("classification", "Security classification", "Optional", "OFFICIAL", "OFFICIAL, OFFICIAL-SENSITIVE"),
    ("purchase_date", "Install / purchase date", "Optional", "2024-01-15", "YYYY-MM-DD"),
    ("manufacturing_date", "Manufacturing date", "Optional", "2023-11-01", "YYYY-MM-DD"),
    ("warranty_expiry", "Warranty expiry", "Optional", "2027-01-15", "YYYY-MM-DD"),
    ("unit_price", "Unit price (£)", "Optional", "3450.00", "Number"),
    ("replacement_cost", "Replacement cost (£)", "Optional", "3800.00", "Number"),
    ("supplier", "Service supplier", "Optional", "Pulse Fitness", "Must match a supplier on the site"),
    ("service_provider", "Service provider notes", "Optional", "Pulse Fitness Service", ""),
    ("contract_number", "Service contract ref", "Optional", "CON-2024-0142", ""),
    ("contract_start", "Contract start", "Optional", "2024-01-15", "YYYY-MM-DD"),
    ("contract_end", "Contract end", "Optional", "2029-01-14", "YYYY-MM-DD"),
    ("length", "Length (m)", "Optional", "2.20", "Number"),
    ("width", "Width (m)", "Optional", "0.95", "Number"),
    ("height", "Height (m)", "Optional", "1.55", "Number"),
    ("qr_code", "Existing QR / barcode", "Optional", "", ""),
    ("sicon_equipment_id", "Sicon equipment ID", "Optional", "", "Leave blank if unknown"),
    ("sage_item_id", "Sage stock item ID", "Optional", "", "Leave blank if unknown"),
    ("notes", "Notes", "Optional", "First install", ""),
]


@router.get("/master-admin/mod-estate/equipment-template.xlsx")
async def mod_equipment_template_xlsx(user: dict = Depends(get_current_user)):
    """Presentable Excel workbook to send to a MOD site to capture its
    equipment. Sheet 1 (Equipment) is the fillable, directly-uploadable
    sheet; Sheet 2 (How to complete) is a field-by-field guide."""
    require_master_admin(user)
    from fastapi.responses import Response
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    brand = "19398D"
    hdr_fill = PatternFill("solid", fgColor=brand)
    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws = wb.active
    ws.title = "Equipment"
    headers = [f[0] for f in _MOD_EQUIP_FIELDS]
    ws.append(headers)
    for col, f in enumerate(_MOD_EQUIP_FIELDS, start=1):
        c = ws.cell(row=1, column=col)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
        ws.column_dimensions[c.column_letter].width = max(14, min(30, len(f[1]) + 4))
    # Two example rows so the site sees exactly what "good" looks like.
    ws.append([f[3] for f in _MOD_EQUIP_FIELDS])
    ws.append([
        "Upright Bike — Studio 1", "Bike", "Pulse Fitness", "Series 3 Upright",
        "PF-UB-014", "", "3", "Spin studio", "Studio 1", "Good", "OFFICIAL",
        "", "", "", "", "", "Pulse Fitness", "", "", "", "", "", "", "", "", "", "", "",
    ][: len(headers)])
    ws.freeze_panes = "A2"

    guide = wb.create_sheet("How to complete")
    guide.append(["Column", "What to enter", "Required?", "Example", "Allowed values / format"])
    for col in range(1, 6):
        c = guide.cell(row=1, column=col)
        c.fill = hdr_fill
        c.font = hdr_font
        c.border = border
    widths = [22, 34, 14, 26, 40]
    for i, w in enumerate(widths, start=1):
        guide.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for f in _MOD_EQUIP_FIELDS:
        guide.append([f[0], f[1], f[2], f[3], f[4]])
    guide.insert_rows(1)
    guide["A1"] = "Fill in the 'Equipment' sheet — one row per machine. Delete the two example rows before returning."
    guide["A1"].font = Font(bold=True, italic=True, color="19398D")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=MOD_Equipment_Capture_Template.xlsx"},
    )


@router.get("/master-admin/mod-estate/equipment-template.csv")
async def mod_equipment_template_csv(user: dict = Depends(get_current_user)):
    """Machine-readable CSV variant of the MOD equipment template (all columns)."""
    require_master_admin(user)
    from fastapi.responses import Response
    import csv as _csv
    import io
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([f[0] for f in _MOD_EQUIP_FIELDS])
    w.writerow([f[3] for f in _MOD_EQUIP_FIELDS])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=MOD_Equipment_Capture_Template.csv"})


@router.get("/master-admin/mod-estate/site-readiness")
async def mod_site_readiness(estate_id: str = DEFAULT_ESTATE_ID,
                             user: dict = Depends(get_current_user)) -> dict:
    """Per-site onboarding readiness for the MOD estate — the guided
    checklist. For each site returns counts + ready flags for Equipment,
    Staff, Suppliers, Documents and Check Sheets so HQ can see, at a glance,
    what each site still needs before going live."""
    require_master_admin(user)
    estate_id = _kebab(estate_id) or DEFAULT_ESTATE_ID
    # Estate scoping is soft: include sites explicitly on this estate AND legacy
    # sites with no estate id set (created via the CSV bulk importer / pre-estate)
    # so HQ can onboard equipment for every MOD site, not just wizard-created ones.
    sites = await db.organizations.find(
        {"account_type": "mod_site",
         "$or": [{"mod_estate_id": estate_id},
                 {"mod_estate_id": {"$in": [None, ""]}},
                 {"mod_estate_id": {"$exists": False}}]},
        {"_id": 0, "id": 1, "name": 1, "mod_force": 1, "site_code": 1,
         "is_overseas": 1, "region": 1},
    ).sort("name", 1).to_list(5000)

    async def _count(coll, oid):
        try:
            return await coll.count_documents({"organization_id": oid})
        except Exception:
            return 0

    out = []
    for s in sites:
        oid = s["id"]
        equipment = await _count(db.equipment, oid)
        staff = await db.mod_site_staff.count_documents({"site_id": oid, "is_active": {"$ne": False}})
        suppliers = await _count(db.suppliers, oid)
        documents = await _count(db.files, oid)
        checks = 0
        for c in (db.check_sheet_instances, db.check_sheets, db.checksheets):
            checks = await _count(c, oid)
            if checks:
                break
        steps = {
            "equipment": {"count": equipment, "ready": equipment > 0},
            "staff": {"count": staff, "ready": staff > 0},
            "suppliers": {"count": suppliers, "ready": suppliers > 0},
            "documents": {"count": documents, "ready": documents > 0},
            "checks": {"count": checks, "ready": checks > 0},
        }
        ready_count = sum(1 for v in steps.values() if v["ready"])
        out.append({
            "id": oid, "name": s.get("name"), "site_code": s.get("site_code"),
            "force": s.get("mod_force"), "is_overseas": bool(s.get("is_overseas")),
            "region": s.get("region"),
            "steps": steps,
            "ready_count": ready_count, "total_steps": len(steps),
            "fully_ready": ready_count == len(steps),
        })
    return {
        "estate_id": estate_id,
        "sites": out,
        "totals": {
            "sites": len(out),
            "fully_ready": sum(1 for s in out if s["fully_ready"]),
            "no_equipment": sum(1 for s in out if not s["steps"]["equipment"]["ready"]),
        },
    }


# ──────────────────── MOD equipment self-capture links ─────────────────
# A site fills its own equipment sheet online via a secure token link; NOTHING
# enters the platform until Pulse Fitness reviews and CONFIRMS the submission.

def _capture_field_spec() -> list:
    """Public field spec the self-capture form renders from."""
    out = []
    for key, label, req, example, allowed in _MOD_EQUIP_FIELDS:
        options = None
        # Turn short enum hints ("New, Good, Fair, Poor") into a dropdown.
        if allowed and "," in allowed and "/" not in allowed and len(allowed) < 60 and "YYYY" not in allowed:
            options = [o.strip() for o in allowed.split(",") if o.strip()]
        out.append({
            "key": key, "label": label,
            "required": req.lower() == "yes",
            "example": example, "hint": allowed or "", "options": options,
        })
    return out


def _safe_capture_public(c: dict) -> dict:
    return {
        "site_name": c.get("site_name"), "force": c.get("force"),
        "status": c.get("status"), "rows": c.get("rows") or [],
        "review_notes": c.get("review_notes") or "",
        "submitted_at": c.get("submitted_at"), "updated_at": c.get("updated_at"),
        "fields": _capture_field_spec(),
    }


async def _get_capture_by_token(token: str) -> dict:
    c = await db.mod_equipment_captures.find_one({"token": token}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture link not found or expired")
    exp = c.get("expires_at")
    if exp:
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(exp.replace("Z", "+00:00")):
                raise HTTPException(410, "This capture link has expired")
        except HTTPException:
            raise
        except Exception:
            pass
    return c


@router.post("/master-admin/mod-estate/capture-link")
async def create_capture_link(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Create (or reuse) a secure self-capture link for a MOD site, and
    optionally email it straight to the site."""
    require_master_admin(user)
    site_id = (data.get("site_id") or "").strip()
    site = await db.organizations.find_one(
        {"id": site_id, "account_type": "mod_site"},
        {"_id": 0, "id": 1, "name": 1, "mod_force": 1,
         "site_manager_email": 1, "primary_contact_email": 1, "contact_email": 1},
    )
    if not site:
        raise HTTPException(404, "MOD site not found")
    # Reuse an in-flight link so the URL stays stable for the site.
    existing = await db.mod_equipment_captures.find_one(
        {"site_id": site_id, "status": {"$in": ["open", "changes_requested", "submitted"]}},
        {"_id": 0},
    )
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    if existing:
        token = existing["token"]
    else:
        token = secrets.token_urlsafe(32)
        now = _now()
        await db.mod_equipment_captures.insert_one({
            "id": str(uuid.uuid4()), "token": token,
            "site_id": site_id, "site_name": site.get("name"),
            "force": site.get("mod_force"),
            "status": "open", "rows": [], "review_notes": "",
            "created_by": user.get("email", "system"), "created_at": now, "updated_at": now,
            "submitted_at": None, "reviewed_at": None,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
        })
    share_url = f"{frontend_url}/mod-capture/{token}" if frontend_url else f"/mod-capture/{token}"

    # Resolve a recipient: explicit override → stored site contact → the site's
    # individual owner login email.
    def _valid(e):
        e = (e or "").strip().lower()
        return e if ("@" in e and not e.endswith("@site.mod.local")) else ""
    to_email = _valid(data.get("email")) or _valid(site.get("site_manager_email")) \
        or _valid(site.get("primary_contact_email")) or _valid(site.get("contact_email"))
    if not to_email:
        owner = await db.users.find_one(
            {"organization_id": site_id, "role": "owner"}, {"_id": 0, "email": 1},
        )
        to_email = _valid(owner.get("email")) if owner else ""

    emailed = False
    if data.get("send_email") and to_email:
        try:
            from utils.email import send_mod_equipment_capture_email
            emailed = await send_mod_equipment_capture_email(
                to_email, site.get("name") or "your site", share_url,
                sender_name=user.get("full_name") or "Pulse Fitness",
            )
            if emailed:
                await db.mod_equipment_captures.update_one(
                    {"token": token},
                    {"$set": {"last_emailed_to": to_email, "last_emailed_at": _now()}},
                )
        except Exception as exc:
            logger.warning("MOD capture email failed for %s: %s", site_id, exc)

    return {
        "token": token, "share_url": share_url, "site_id": site_id,
        "site_name": site.get("name"), "site_email": to_email or None,
        "emailed": emailed,
        "needs_email": bool(data.get("send_email") and not to_email),
    }


@router.get("/master-admin/mod-estate/captures")
async def list_captures(user: dict = Depends(get_current_user)) -> dict:
    """List all self-capture submissions for the review queue."""
    require_master_admin(user)
    items = await db.mod_equipment_captures.find({}, {"_id": 0}).sort("updated_at", -1).to_list(1000)
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    for c in items:
        c["row_count"] = len(c.get("rows") or [])
        c["share_url"] = f"{frontend_url}/mod-capture/{c['token']}" if frontend_url else f"/mod-capture/{c['token']}"
        c.pop("rows", None)
    return {"captures": items}


@router.post("/master-admin/mod-estate/captures/{capture_id}/approve")
async def approve_capture(capture_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Confirm a submitted capture — import its rows into the site's equipment."""
    require_master_admin(user)
    c = await db.mod_equipment_captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture not found")
    if c.get("status") not in ("submitted", "changes_requested", "open"):
        raise HTTPException(400, f"Capture is '{c.get('status')}' and cannot be imported")
    rows = c.get("rows") or []
    if not rows:
        raise HTTPException(400, "Nothing to import — the site has not added any equipment")

    # Build a CSV from the captured rows and feed the battle-tested importer
    # (dedupe, supplier/site/force resolution, batching) via an in-memory upload.
    import csv as _csv
    import io as _io
    from fastapi import UploadFile
    from routes.master_admin_bulk_import import _do_bulk_import_equipment

    cols = [f[0] for f in _MOD_EQUIP_FIELDS]
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: (r.get(k) if r.get(k) is not None else "") for k in cols})
    upload = UploadFile(filename="mod_capture.csv", file=_io.BytesIO(buf.getvalue().encode("utf-8")))
    result = await _do_bulk_import_equipment(upload, c["site_id"], user, validate_org=True)

    await db.mod_equipment_captures.update_one(
        {"id": capture_id},
        {"$set": {"status": "approved", "reviewed_at": _now(), "updated_at": _now(),
                  "reviewed_by": user.get("email", "system"), "import_result": result}},
    )
    return {"success": True, "import_result": result}


@router.post("/master-admin/mod-estate/captures/{capture_id}/reject")
async def reject_capture(capture_id: str, data: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Send a capture back to the site for changes (nothing is imported)."""
    require_master_admin(user)
    c = await db.mod_equipment_captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture not found")
    await db.mod_equipment_captures.update_one(
        {"id": capture_id},
        {"$set": {"status": "changes_requested", "updated_at": _now(),
                  "review_notes": (data.get("reason") or "").strip()}},
    )
    return {"success": True}


# ── public (no-auth) self-capture form endpoints ──
@router.get("/public/mod-capture/{token}")
async def public_get_capture(token: str, request: Request) -> dict:
    from utils.security_plus import rate_limit_async
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"mod_capture_ip:{ip}", max_requests=60, window_seconds=300)
    return _safe_capture_public(await _get_capture_by_token(token))


@router.put("/public/mod-capture/{token}")
async def public_save_capture(token: str, body: dict = Body(...)) -> dict:
    c = await _get_capture_by_token(token)
    if c.get("status") not in ("open", "changes_requested"):
        raise HTTPException(400, "This sheet has been submitted and can no longer be edited")
    rows = body.get("rows")
    if not isinstance(rows, list):
        raise HTTPException(400, "rows must be a list")
    # Only persist known columns; cap to protect the doc size.
    cols = {f[0] for f in _MOD_EQUIP_FIELDS}
    clean = [{k: str(v) for k, v in r.items() if k in cols and v not in (None, "")} for r in rows[:2000]]
    await db.mod_equipment_captures.update_one(
        {"token": token},
        {"$set": {"rows": clean, "updated_at": _now(),
                  "status": "open" if c.get("status") == "changes_requested" else c.get("status")}},
    )
    return _safe_capture_public(await _get_capture_by_token(token))


@router.post("/public/mod-capture/{token}/submit")
async def public_submit_capture(token: str, body: dict = Body(default={})) -> dict:
    c = await _get_capture_by_token(token)
    if c.get("status") not in ("open", "changes_requested"):
        raise HTTPException(400, "This sheet has already been submitted")
    rows = c.get("rows") or []
    if not rows or not any((r.get("name") or "").strip() for r in rows):
        raise HTTPException(400, "Add at least one machine (with a name) before submitting")
    await db.mod_equipment_captures.update_one(
        {"token": token},
        {"$set": {"status": "submitted", "submitted_at": _now(), "updated_at": _now()}},
    )
    return {"success": True, "message": "Submitted to Pulse Fitness for review. Nothing is imported until they confirm."}


# ──────────────────── whole-of-MOD reporting rollup ────────────────────


@router.get("/master-admin/mod-estate/overview")
async def mod_estate_overview(estate_id: str = DEFAULT_ESTATE_ID,
                              user: dict = Depends(get_current_user)) -> dict:
    """Report on the MOD *as a whole* across the three independent service
    HQs: HQ status, site counts (UK vs overseas) per service, supplier
    registry size and open-fault rollup."""
    require_master_admin(user)
    estate_id = _kebab(estate_id) or DEFAULT_ESTATE_ID

    hqs = []
    for svc in MOD_SERVICES:
        hq_id = _hq_id(estate_id, svc["force"])
        hq = await db.organizations.find_one({"id": hq_id}, {"_id": 0, "id": 1, "name": 1})
        hqs.append({"force": svc["force"], "label": svc["label"], "id": hq_id,
                    "name": (hq or {}).get("name"), "exists": bool(hq)})

    site_cursor = db.organizations.find(
        {"account_type": "mod_site", "mod_estate_id": estate_id},
        {"_id": 0, "id": 1, "mod_force": 1, "is_overseas": 1, "serviced_by": 1},
    )
    per_force = {s["force"]: {"total": 0, "uk": 0, "overseas": 0} for s in MOD_SERVICES}
    site_ids = []
    total = uk = overseas = 0
    async for s in site_cursor:
        site_ids.append(s["id"])
        f = (s.get("mod_force") or "").lower()
        bucket = per_force.setdefault(f, {"total": 0, "uk": 0, "overseas": 0})
        bucket["total"] += 1
        total += 1
        if s.get("is_overseas"):
            bucket["overseas"] += 1
            overseas += 1
        else:
            bucket["uk"] += 1
            uk += 1

    open_faults = 0
    if site_ids:
        open_faults = await db.issues.count_documents({
            "organization_id": {"$in": site_ids},
            "status": {"$nin": ["resolved", "closed", "completed"]},
        })

    supplier_count = await db.mod_estate_suppliers.count_documents({"mod_estate_id": estate_id})

    return {
        "estate_id": estate_id,
        "hqs": hqs,
        "hqs_ready": all(h["exists"] for h in hqs),
        "totals": {"sites": total, "uk_sites": uk, "overseas_sites": overseas,
                   "open_faults": open_faults, "suppliers": supplier_count},
        "per_service": [
            {"force": s["force"], "label": s["label"], **per_force.get(s["force"], {"total": 0, "uk": 0, "overseas": 0})}
            for s in MOD_SERVICES
        ],
    }


__all__ = ["router"]
