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
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, File, Query, UploadFile

from utils.auth import get_current_user, hash_password
from utils.database import db
from routes.master_admin import (
    _generate_initial_password,
    _mint_invite_link,
    log_activity,
    merge_address,
    require_master_admin,
)

logger = logging.getLogger(__name__)
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


async def _compute_estate_readiness(estate_id: str) -> dict:
    """Shared readiness computation used by the JSON endpoint and the Excel export."""
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

    # Equipment mix by category per site (one aggregation across all sites), so
    # HQ sees the kit mix at a glance on each site card. Coalesce category →
    # equipment_type → "Uncategorised" and ignore archived rows.
    oids = [s["id"] for s in sites]
    cat_map: dict = {}
    if oids:
        try:
            pipeline = [
                {"$match": {"organization_id": {"$in": oids},
                            "archived": {"$ne": True}}},
                {"$group": {
                    "_id": {
                        "oid": "$organization_id",
                        "cat": {"$let": {
                            "vars": {
                                "c": {"$ifNull": ["$category", ""]},
                                "t": {"$ifNull": ["$equipment_type", ""]},
                            },
                            "in": {"$cond": [
                                {"$ne": ["$$c", ""]}, "$$c",
                                {"$cond": [{"$ne": ["$$t", ""]}, "$$t", "Uncategorised"]},
                            ]},
                        }},
                    },
                    "count": {"$sum": 1},
                }},
            ]
            async for row in db.equipment.aggregate(pipeline):
                oid_ = row["_id"]["oid"]
                cat_ = (row["_id"]["cat"] or "Uncategorised")
                cat_map.setdefault(oid_, {})[cat_] = cat_map.get(oid_, {}).get(cat_, 0) + row["count"]
        except Exception:
            cat_map = {}

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
        kit_by_category = sorted(
            [{"category": k, "count": v} for k, v in cat_map.get(oid, {}).items()],
            key=lambda x: (-x["count"], x["category"].lower()),
        )
        out.append({
            "id": oid, "name": s.get("name"), "site_code": s.get("site_code"),
            "force": s.get("mod_force"), "is_overseas": bool(s.get("is_overseas")),
            "region": s.get("region"),
            "steps": steps,
            "kit_by_category": kit_by_category,
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


@router.get("/master-admin/mod-estate/site-readiness")
async def mod_site_readiness(estate_id: str = DEFAULT_ESTATE_ID,
                             user: dict = Depends(get_current_user)) -> dict:
    """Per-site onboarding readiness for the MOD estate — the guided
    checklist. For each site returns counts + ready flags for Equipment,
    Staff, Suppliers, Documents and Check Sheets so HQ can see, at a glance,
    what each site still needs before going live."""
    require_master_admin(user)
    return await _compute_estate_readiness(estate_id)


@router.get("/master-admin/mod-estate/site/{site_id}/equipment-by-category")
async def mod_site_equipment_by_category(site_id: str, category: str = Query(...),
                                         user: dict = Depends(get_current_user)) -> dict:
    """Drill-down for the 'Kit by category' chip on a MOD site card: the actual
    machines that make up a category count. Category is coalesced the same way
    the readiness aggregation does (category → equipment_type → 'Uncategorised')."""
    require_master_admin(user)
    want = (category or "").strip().lower()
    docs = await db.equipment.find(
        {"organization_id": site_id, "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "manufacturer": 1, "model": 1,
         "model_code": 1, "serial_number": 1, "asset_number": 1, "asset_tag": 1,
         "location": 1, "sub_location": 1, "category": 1, "equipment_type": 1,
         "mod_code": 1},
    ).sort("name", 1).to_list(5000)

    def _cat(d: dict) -> str:
        c = (d.get("category") or "").strip()
        if c:
            return c
        t = (d.get("equipment_type") or "").strip()
        return t or "Uncategorised"

    items = []
    for d in docs:
        if _cat(d).lower() != want:
            continue
        items.append({
            "id": d.get("id"),
            "name": d.get("name") or "—",
            "manufacturer": d.get("manufacturer") or "",
            "model": d.get("model") or d.get("model_code") or "",
            "serial_number": d.get("serial_number") or "",
            "asset_number": d.get("asset_number") or d.get("asset_tag") or "",
            "location": d.get("location") or d.get("sub_location") or "",
            "mod_code": d.get("mod_code") or "",
        })
    return {"site_id": site_id, "category": category, "count": len(items), "items": items}


def build_readiness_xlsx_bytes(data: dict) -> bytes:
    """Build the whole-of-MOD go-live readiness workbook from a readiness
    payload (see `_compute_estate_readiness`) and return the raw .xlsx bytes.
    Shared by the download endpoint and the scheduled HQ email."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Go-live readiness"
    hdr_fill = PatternFill("solid", fgColor="19398D")
    hdr_font = Font(bold=True, color="FFFFFF")
    ok_fill = PatternFill("solid", fgColor="D9F2E3")
    bad_fill = PatternFill("solid", fgColor="FBE0E0")

    headers = ["Site", "Site code", "Force", "Location", "Equipment", "Staff",
               "Suppliers", "Documents", "Check Sheets", "Ready steps", "Go-live ready?"]
    ws.append(headers)
    for i, _ in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")
    widths = [34, 12, 8, 12, 12, 8, 10, 11, 12, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    def cell_txt(step):
        return f"{step['count']}" if step["ready"] else f"{step['count']} ✗"

    for s in data["sites"]:
        st = s["steps"]
        ws.append([
            s["name"], s.get("site_code") or "", (s.get("force") or "").upper(),
            "Overseas" if s.get("is_overseas") else (s.get("region") or "UK"),
            cell_txt(st["equipment"]), cell_txt(st["staff"]), cell_txt(st["suppliers"]),
            cell_txt(st["documents"]), cell_txt(st["checks"]),
            f"{s['ready_count']}/{s['total_steps']}",
            "READY" if s["fully_ready"] else "Not yet",
        ])
        r = ws.max_row
        for col in range(5, 10):  # per-step cells
            key = ["equipment", "staff", "suppliers", "documents", "checks"][col - 5]
            ws.cell(row=r, column=col).fill = ok_fill if st[key]["ready"] else bad_fill
        ws.cell(row=r, column=11).fill = ok_fill if s["fully_ready"] else bad_fill
    ws.freeze_panes = "A2"

    # Summary sheet
    sm = wb.create_sheet("Summary")
    t = data["totals"]
    sm.append(["MOD estate go-live readiness"])
    sm["A1"].font = Font(bold=True, size=13, color="19398D")
    sm.append([])
    sm.append(["Total sites", t["sites"]])
    sm.append(["Fully ready", t["fully_ready"]])
    sm.append(["Sites still needing equipment", t["no_equipment"]])
    sm.column_dimensions["A"].width = 32
    sm.column_dimensions["B"].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


@router.get("/master-admin/mod-estate/readiness-export.xlsx")
async def readiness_export_xlsx(estate_id: str = DEFAULT_ESTATE_ID,
                                user: dict = Depends(get_current_user)):
    """One-click Excel of the whole estate's go-live checklist."""
    require_master_admin(user)
    data = await _compute_estate_readiness(estate_id)
    from fastapi.responses import Response
    return Response(
        content=build_readiness_xlsx_bytes(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=MOD_Estate_Readiness.xlsx"},
    )


@router.post("/master-admin/mod-estate/readiness-email/send")
async def send_readiness_email_now(estate_id: str = DEFAULT_ESTATE_ID,
                                   payload: dict = Body(default={}),
                                   user: dict = Depends(get_current_user)) -> dict:
    """Master Admin 'Send now' — email the readiness Excel + summary to HQ
    immediately (bypasses the once-per-week lock). Optional {email} override."""
    require_master_admin(user)
    from utils.mod_readiness_digest import send_mod_readiness_email, _hq_recipient
    to = (payload or {}).get("email") or None
    res = await send_mod_readiness_email(estate_id=estate_id, to=to, force=True)
    res.setdefault("recipient", to or _hq_recipient())
    return res


@router.get("/master-admin/mod-estate/readiness-email/status")
async def readiness_email_status(user: dict = Depends(get_current_user)) -> dict:
    """Last scheduled/manual readiness email + the configured HQ recipient."""
    require_master_admin(user)
    from utils.mod_readiness_digest import JOB_KEY, _hq_recipient, SEND_HOUR_UTC
    doc = await db.system_jobs.find_one({"job": JOB_KEY}, {"_id": 0})
    return {
        "recipient": _hq_recipient(),
        "send_hour_utc": SEND_HOUR_UTC,
        "schedule": "Every Monday",
        "last_sent_at": (doc or {}).get("last_sent_at"),
        "last_recipient": (doc or {}).get("last_recipient"),
        "last_ok": (doc or {}).get("last_ok"),
        "last_totals": (doc or {}).get("last_totals"),
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


def _norm(v) -> str:
    return (str(v) if v is not None else "").strip().lower()


DUP_FLAGS = ("duplicate_serial", "duplicate_in_sheet", "possible_duplicate")


async def _analyse_capture_rows(site_id: str, rows: list) -> tuple:
    """Flag likely duplicates in captured rows. Returns (analysed, existing_count)."""
    existing = await db.equipment.find(
        {"organization_id": site_id}, {"_id": 0, "serial_number": 1, "name": 1, "model": 1},
    ).to_list(50000)
    exist_serials = {_norm(e.get("serial_number")) for e in existing if e.get("serial_number")}
    exist_namemodel = {(_norm(e.get("name")), _norm(e.get("model"))) for e in existing}
    seen_serials: set = set()
    analysed = []
    for i, r in enumerate(rows):
        serial, name, model = _norm(r.get("serial_number")), _norm(r.get("name")), _norm(r.get("model"))
        flags = []
        if not name:
            flags.append("missing_name")
        if serial and serial in exist_serials:
            flags.append("duplicate_serial")        # already on the platform
        if serial and serial in seen_serials:
            flags.append("duplicate_in_sheet")       # listed twice in this sheet
        if "duplicate_serial" not in flags and name and (name, model) in exist_namemodel:
            flags.append("possible_duplicate")        # same make/model already present
        if serial:
            seen_serials.add(serial)
        analysed.append({"index": i, "row": r, "flags": flags})
    return analysed, len(existing)


async def _import_rows_to_site(site_id: str, rows: list, user: dict) -> dict:
    """Build a CSV from captured rows and feed the battle-tested equipment importer."""
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
    return await _do_bulk_import_equipment(upload, site_id, user, validate_org=True)


@router.get("/master-admin/mod-estate/captures/{capture_id}")
async def get_capture_detail(capture_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Full submission for review — every row the site entered, with likely
    duplicates flagged against existing equipment AND within the sheet itself."""
    require_master_admin(user)
    c = await db.mod_equipment_captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture not found")
    rows = c.get("rows") or []
    analysed, existing_count = await _analyse_capture_rows(c["site_id"], rows)
    dup_count = sum(1 for a in analysed if any(f in DUP_FLAGS for f in a["flags"]))
    return {
        "capture": {k: v for k, v in c.items() if k != "rows"},
        "rows": analysed,
        "columns": [f[0] for f in _MOD_EQUIP_FIELDS],
        "field_labels": {f[0]: f[1] for f in _MOD_EQUIP_FIELDS},
        "row_count": len(rows),
        "duplicate_count": dup_count,
        "existing_equipment_count": existing_count,
    }


async def _resolve_site_email(site_id: str, override: str = "") -> str:
    def _valid(e):
        e = (e or "").strip().lower()
        return e if ("@" in e and not e.endswith("@site.mod.local")) else ""
    if _valid(override):
        return _valid(override)
    site = await db.organizations.find_one(
        {"id": site_id},
        {"_id": 0, "site_manager_email": 1, "primary_contact_email": 1, "contact_email": 1},
    ) or {}
    email = _valid(site.get("site_manager_email")) or _valid(site.get("primary_contact_email")) \
        or _valid(site.get("contact_email"))
    if not email:
        owner = await db.users.find_one({"organization_id": site_id, "role": "owner"}, {"_id": 0, "email": 1})
        email = _valid(owner.get("email")) if owner else ""
    return email


@router.post("/master-admin/mod-estate/captures/{capture_id}/remind")
async def remind_capture(capture_id: str, data: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Re-email the capture link to a site that hasn't submitted yet."""
    require_master_admin(user)
    c = await db.mod_equipment_captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture not found")
    if c.get("status") not in ("open", "changes_requested"):
        raise HTTPException(400, "This site has already submitted — nothing to remind about")
    to_email = await _resolve_site_email(c["site_id"], data.get("email") or c.get("last_emailed_to") or "")
    if not to_email:
        return {"reminded": False, "needs_email": True}
    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
    url = f"{frontend_url}/mod-capture/{c['token']}" if frontend_url else f"/mod-capture/{c['token']}"
    reminded = False
    try:
        from utils.email import send_mod_equipment_capture_email
        reminded = await send_mod_equipment_capture_email(
            to_email, c.get("site_name") or "your site", url,
            sender_name=user.get("full_name") or "Pulse Fitness",
        )
    except Exception as exc:
        logger.warning("MOD capture reminder failed for %s: %s", capture_id, exc)
    if reminded:
        await db.mod_equipment_captures.update_one(
            {"id": capture_id},
            {"$set": {"last_emailed_to": to_email, "last_reminded_at": _now(), "updated_at": _now()},
             "$inc": {"reminder_count": 1}},
        )
    return {"reminded": reminded, "site_email": to_email}


@router.post("/master-admin/mod-estate/captures/{capture_id}/approve")
async def approve_capture(capture_id: str, data: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Confirm a submitted capture — import its rows into the site's equipment.
    Pass skip_duplicates=true to drop the flagged duplicate rows at import time."""
    require_master_admin(user)
    skip_dups = bool(data.get("skip_duplicates"))
    c = await db.mod_equipment_captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Capture not found")
    if c.get("status") not in ("submitted", "changes_requested", "open"):
        raise HTTPException(400, f"Capture is '{c.get('status')}' and cannot be imported")
    rows = c.get("rows") or []
    if not rows:
        raise HTTPException(400, "Nothing to import — the site has not added any equipment")

    skipped_duplicates = 0
    if skip_dups:
        analysed, _ = await _analyse_capture_rows(c["site_id"], rows)
        keep = [a["row"] for a in analysed if not (set(a["flags"]) & set(DUP_FLAGS))]
        skipped_duplicates = len(rows) - len(keep)
        rows = keep
        if not rows:
            raise HTTPException(400, "Every row was flagged as a duplicate — nothing left to import")

    result = await _import_rows_to_site(c["site_id"], rows, user)
    result["skipped_duplicates"] = skipped_duplicates
    await db.mod_equipment_captures.update_one(
        {"id": capture_id},
        {"$set": {"status": "approved", "reviewed_at": _now(), "updated_at": _now(),
                  "reviewed_by": user.get("email", "system"), "import_result": result}},
    )
    return {"success": True, "import_result": result, "skipped_duplicates": skipped_duplicates}


@router.post("/master-admin/mod-estate/captures/bulk-approve")
async def bulk_approve_captures(data: dict = Body(default={}), user: dict = Depends(get_current_user)) -> dict:
    """Confirm ALL submitted site submissions at once. By default drops the
    flagged duplicate rows in each (skip_duplicates), importing only clean rows."""
    require_master_admin(user)
    skip_dups = data.get("skip_duplicates", True)
    subs = await db.mod_equipment_captures.find({"status": "submitted"}, {"_id": 0}).to_list(500)
    results = []
    total_imported = 0
    total_skipped_dups = 0
    for c in subs:
        rows = c.get("rows") or []
        skipped = 0
        if skip_dups and rows:
            analysed, _ = await _analyse_capture_rows(c["site_id"], rows)
            keep = [a["row"] for a in analysed if not (set(a["flags"]) & set(DUP_FLAGS))]
            skipped = len(rows) - len(keep)
            rows = keep
        if not rows:
            results.append({"capture_id": c["id"], "site_name": c.get("site_name"),
                            "imported": 0, "skipped_duplicates": skipped, "note": "all rows flagged / empty"})
            total_skipped_dups += skipped
            continue
        try:
            r = await _import_rows_to_site(c["site_id"], rows, user)
            imported = r.get("imported", 0)
            total_imported += imported
            total_skipped_dups += skipped
            await db.mod_equipment_captures.update_one(
                {"id": c["id"]},
                {"$set": {"status": "approved", "reviewed_at": _now(), "updated_at": _now(),
                          "reviewed_by": user.get("email", "system"),
                          "import_result": {**r, "skipped_duplicates": skipped}}},
            )
            results.append({"capture_id": c["id"], "site_name": c.get("site_name"),
                            "imported": imported, "skipped_duplicates": skipped, "skipped_import": r.get("skipped", 0)})
        except Exception as exc:
            logger.warning("bulk-approve failed for %s: %s", c.get("id"), exc)
            results.append({"capture_id": c["id"], "site_name": c.get("site_name"),
                            "imported": 0, "skipped_duplicates": skipped, "error": str(exc)[:200]})
    return {
        "processed": len(subs),
        "total_imported": total_imported,
        "total_skipped_duplicates": total_skipped_dups,
        "results": results,
        "run_id": await _save_bulk_run(user, len(subs), total_imported, total_skipped_dups, results),
    }


async def _save_bulk_run(user, processed, total_imported, total_skipped, results) -> str:
    run_id = str(uuid.uuid4())
    await db.mod_bulk_import_runs.insert_one({
        "id": run_id, "run_at": _now(), "by": user.get("email", "system"),
        "processed": processed, "total_imported": total_imported,
        "total_skipped_duplicates": total_skipped, "results": results,
    })
    return run_id


@router.get("/master-admin/mod-estate/bulk-report/{run_id}.xlsx")
async def bulk_report_xlsx(run_id: str, user: dict = Depends(get_current_user)):
    """Downloadable proof of a bulk confirm — per-site imported vs skipped."""
    require_master_admin(user)
    run = await db.mod_bulk_import_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Report not found")
    from fastapi.responses import Response
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bulk import report"
    hdr_fill = PatternFill("solid", fgColor="19398D")
    hdr_font = Font(bold=True, color="FFFFFF")
    ws.append([f"MOD bulk equipment import — {run.get('run_at', '')[:19].replace('T', ' ')} UTC · by {run.get('by')}"])
    ws["A1"].font = Font(bold=True, size=12, color="19398D")
    ws.append([f"Sites processed: {run['processed']} · Machines imported: {run['total_imported']} · Duplicate rows skipped: {run['total_skipped_duplicates']}"])
    ws.append([])
    headers = ["Site", "Imported", "Duplicates skipped", "Skipped on import", "Notes / errors"]
    ws.append(headers)
    hr = ws.max_row
    for i in range(1, len(headers) + 1):
        ws.cell(row=hr, column=i).fill = hdr_fill
        ws.cell(row=hr, column=i).font = hdr_font
    for r in run.get("results", []):
        ws.append([
            r.get("site_name", ""), r.get("imported", 0), r.get("skipped_duplicates", 0),
            r.get("skipped_import", 0), r.get("error") or r.get("note") or "",
        ])
    for i, w in enumerate([36, 10, 18, 16, 40], start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.freeze_panes = "A5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=MOD_Bulk_Import_Report_{run_id[:8]}.xlsx"},
    )


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


# ── Contract Activation Board (Type A service contracts) ───────────

@router.get("/master-admin/mod-estate/contracts")
async def list_mod_service_contracts(user: dict = Depends(get_current_user)) -> dict:
    """Live board of Type A MOD service contracts for the Pulse Fitness MOD
    Service team: shows each activated contract and its auto-scheduled annual
    visit awaiting the team's confirmation."""
    require_master_admin(user)
    rows = await db.mod_service_contracts.find(
        {}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    contracts = []
    pending = 0
    for c in rows:
        av = c.get("annual_visit") or {}
        visit_status = av.get("status") or ("pending_confirmation" if c.get("status") == "active" else "none")
        if c.get("status") == "active" and visit_status == "pending_confirmation":
            pending += 1
        contracts.append({
            "id": c.get("id"),
            "quote_id": c.get("quote_id"),
            "quote_number": c.get("quote_number"),
            "mod_site_id": c.get("mod_site_id"),
            "mod_site_name": c.get("mod_site_name"),
            "status": c.get("status"),
            "annual_value": c.get("annual_value"),
            "currency": c.get("currency", "GBP"),
            "term_months": c.get("term_months", 12),
            "equipment_count": c.get("equipment_count"),
            "start_date": c.get("start_date"),
            "activated_at": c.get("activated_at"),
            "created_at": c.get("created_at"),
            "visit_status": visit_status,
            "proposed_date": av.get("proposed_date"),
            "scheduled_date": av.get("scheduled_date"),
            "engineer": av.get("engineer"),
            "visit_notes": av.get("notes"),
            "confirmed_by": av.get("confirmed_by"),
            "confirmed_at": av.get("confirmed_at"),
        })
    return {"contracts": contracts, "pending_confirmation": pending,
            "active_count": sum(1 for c in contracts if c["status"] == "active")}


@router.post("/master-admin/mod-estate/contracts/{contract_id}/confirm-visit")
async def confirm_contract_visit(contract_id: str, data: dict = Body(default={}),
                                 user: dict = Depends(get_current_user)) -> dict:
    """MOD Service team confirms (or reschedules) a contract's annual visit."""
    require_master_admin(user)
    contract = await db.mod_service_contracts.find_one({"id": contract_id}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    av = contract.get("annual_visit") or {}
    scheduled = (data.get("scheduled_date") or av.get("proposed_date"))
    now = datetime.now(timezone.utc).isoformat()
    av.update({
        "status": "confirmed",
        "scheduled_date": scheduled,
        "engineer": data.get("engineer") or av.get("engineer"),
        "notes": data.get("notes") if data.get("notes") is not None else av.get("notes"),
        "confirmed_by": user.get("full_name") or user.get("email"),
        "confirmed_at": now,
    })
    await db.mod_service_contracts.update_one(
        {"id": contract_id}, {"$set": {"annual_visit": av, "updated_at": now}})
    # Sync to Sicon: Service Call + engineer Appointment linked to the Contract
    # (queues + simulates until live Sicon credentials are supplied).
    try:
        from routes.svc.mod_visits import enqueue_contract_visit_sicon
        fresh = await db.mod_service_contracts.find_one({"id": contract_id}, {"_id": 0})
        if fresh:
            await enqueue_contract_visit_sicon(fresh)
    except Exception:
        logger.exception("[mod-visit] Sicon enqueue on confirm failed")
    return {"ok": True, "annual_visit": av}


@router.post("/master-admin/mod-estate/contracts/{contract_id}/reschedule-visit")
async def reschedule_contract_visit(contract_id: str, data: dict = Body(...),
                                    user: dict = Depends(get_current_user)) -> dict:
    """Move a proposed/confirmed annual visit back to a new proposed date."""
    require_master_admin(user)
    contract = await db.mod_service_contracts.find_one({"id": contract_id}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    new_date = data.get("proposed_date")
    if not new_date:
        raise HTTPException(400, "proposed_date is required")
    av = contract.get("annual_visit") or {}
    av.update({"status": "pending_confirmation", "proposed_date": new_date,
               "scheduled_date": None, "confirmed_by": None, "confirmed_at": None})
    await db.mod_service_contracts.update_one(
        {"id": contract_id},
        {"$set": {"annual_visit": av, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "annual_visit": av}


# ─────────────────────────────────────────────────────────────────────────
# AI Kit-List Import (Iter 216h240) — read ANY equipment spreadsheet, AI-clean
# it (derive Name, title-case, tabs → sub-locations), review, then import via
# the SAME bulk-import engine so there is one import path and serial de-dupe.
# ─────────────────────────────────────────────────────────────────────────
@router.post("/master-admin/mod-estate/ai-kit-import/analyse")
async def ai_kit_import_analyse(
    file: UploadFile = File(...),
    site_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    from utils.file_validation import MIME_SPREADSHEETS, validate_upload
    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename,
                    allowed=MIME_SPREADSHEETS, max_size=50 * 1024 * 1024)
    from utils.kit_list_ai import analyse_kit_workbook
    try:
        preview = await analyse_kit_workbook(contents, file.filename or "kit-list.xlsx")
    except Exception as exc:
        raise HTTPException(400, f"Could not read that spreadsheet: {exc}")

    # Flag duplicate serials — against the target site's existing kit and
    # within the uploaded file itself — so nothing is double-imported.
    existing: set = set()
    if site_id:
        cursor = db.equipment.find(
            {"organization_id": site_id, "serial_number": {"$exists": True, "$ne": ""}},
            {"_id": 0, "serial_number": 1})
        existing = {d["serial_number"] async for d in cursor if d.get("serial_number")}
    seen: set = set()
    dupes = 0
    for sh in preview["sheets"]:
        if sh["is_summary"]:
            continue
        for r in sh["rows"]:
            s = (r.get("serial_number") or "").strip()
            dup = bool(s) and (s in existing or s in seen)
            r["duplicate"] = dup
            if s:
                seen.add(s)
            if dup:
                dupes += 1
    preview["duplicate_serials"] = dupes
    preview["site_id"] = site_id
    # MOD sites the operator can retarget individual tabs to (multi-base kit lists).
    site_rows = await db.organizations.find(
        {"account_type": "mod_site"}, {"_id": 0, "id": 1, "name": 1},
    ).sort("name", 1).to_list(5000)
    preview["mod_sites"] = site_rows
    return preview


@router.post("/master-admin/mod-estate/ai-kit-import/commit")
async def ai_kit_import_commit(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    require_master_admin(user)
    default_site = (payload.get("site_id") or "").strip()
    rows = payload.get("rows") or []
    if not default_site:
        raise HTTPException(400, "site_id is required.")
    if not rows:
        raise HTTPException(400, "No equipment rows to import.")
    skip_duplicates = bool(payload.get("skip_duplicates", True))

    import csv as _csv
    import io as _io
    from routes.master_admin_bulk_import import _do_bulk_import_equipment

    # Group rows by their target MOD site (a tab may target another base).
    groups: dict = {}
    for r in rows:
        if skip_duplicates and r.get("duplicate"):
            continue
        if not (r.get("name") or "").strip():
            continue
        target = (r.get("target_site_id") or "").strip() or default_site
        groups.setdefault(target, []).append(r)
    if not groups:
        raise HTTPException(400, "Nothing to import after de-duplication.")

    class _MemUpload:
        def __init__(self, data: bytes, filename: str):
            self._data, self.filename = data, filename
            self.content_type = "text/csv"

        async def read(self):
            return self._data

    headers = ["name", "equipment_type", "manufacturer", "model",
               "serial_number", "asset_number", "sub_location", "quantity",
               "category", "mod_code"]
    totals = {"imported": 0, "skipped": 0, "errors": []}
    per_site = []
    site_names = {s["id"]: s.get("name") for s in await db.organizations.find(
        {"account_type": "mod_site"}, {"_id": 0, "id": 1, "name": 1}).to_list(5000)}

    for target, grp in groups.items():
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(headers)
        written = 0
        for r in grp:
            w.writerow([
                (r.get("name") or "").strip(),
                (r.get("equipment_type") or "").strip(),
                (r.get("manufacturer") or "").strip(),
                (r.get("model") or "").strip(),
                (r.get("serial_number") or "").strip(),
                (r.get("asset_number") or "").strip(),
                (r.get("sub_location") or "").strip(),
                r.get("quantity") or 1,
                (r.get("category") or "").strip(),
                (r.get("mod_code") or "").strip(),
            ])
            written += 1
        shim = _MemUpload(buf.getvalue().encode("utf-8"), f"ai-kit-{target}.csv")
        res = await _do_bulk_import_equipment(shim, target, user, validate_org=True)
        totals["imported"] += res.get("imported", 0)
        totals["skipped"] += res.get("skipped", 0)
        totals["errors"].extend(res.get("errors", []) or [])
        per_site.append({
            "site_id": target, "site_name": site_names.get(target, target),
            "rows_submitted": written,
            "imported": res.get("imported", 0), "skipped": res.get("skipped", 0),
        })

    totals["per_site"] = per_site
    totals["rows_submitted"] = sum(p["rows_submitted"] for p in per_site)
    return totals


__all__ = ["router"]
