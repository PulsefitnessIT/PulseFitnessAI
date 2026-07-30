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

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

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
