"""MOD site portal · per-machine service supplier + bulk reassign.

Machines follow the site's allocated provider (``supplier_mode=site_default``)
unless site staff move them (``supplier_override=True``) to Pulse in-house,
any estate provider, or a third-party supplier they add themselves.
"""
from __future__ import annotations

import html
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from routes.mod_portal import _require_mod_site
from routes.master_admin_mod_estate import DEFAULT_ESTATE_ID
from routes.master_admin import log_activity
from utils.auth import get_current_user
from utils.database import db
from utils.default_supplier import MOD_SERVICE_EMAIL
from utils.email import send_email

router = APIRouter()

PULSE_NAME = "Pulse Fitness (MOD Service)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pulse_email() -> str:
    return (os.environ.get("MOD_SERVICE_EMAIL") or MOD_SERVICE_EMAIL).strip()


async def _site_default(org: dict) -> dict | None:
    sid = (org.get("service_supplier_id") or "").strip()
    if not sid:
        return None
    return await db.suppliers.find_one({"id": sid, "organization_id": org["id"]},
                                       {"_id": 0, "id": 1, "name": 1, "email": 1})


@router.get("/mod/site/machine-suppliers")
async def list_machine_suppliers(user: dict = Depends(get_current_user)) -> dict:
    org = await _require_mod_site(user)
    default = await _site_default(org)
    machines = await db.equipment.find(
        {"organization_id": org["id"]},
        {"_id": 0, "id": 1, "name": 1, "machine_type": 1, "serial_number": 1, "manufacturer": 1,
         "location": 1, "supplier": 1, "supplier_id": 1, "supplier_override": 1, "supplier_mode": 1},
    ).sort("name", 1).to_list(2000)
    for m in machines:
        m["follows_default"] = not m.get("supplier_override")
        if m.get("supplier_mode") == "pulse":
            m["supplier"] = PULSE_NAME
    estate_id = org.get("mod_estate_id") or DEFAULT_ESTATE_ID
    providers = await db.mod_estate_suppliers.find(
        {"mod_estate_id": estate_id, "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "countries": 1}).sort("name", 1).to_list(500)
    own = await db.suppliers.find(
        {"organization_id": org["id"], "estate_supplier_id": {"$exists": False}, "email": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "name": 1, "email": 1}).sort("name", 1).to_list(500)
    pulse_lc = _pulse_email().lower()
    providers = [p for p in providers if (p.get("email") or "").lower() != pulse_lc
                 and "in-house" not in (p.get("name") or "").lower()]
    prov_emails = {(p.get("email") or "").lower() for p in providers}
    prov_names = {(p.get("name") or "").strip().lower() for p in providers}
    own = [s for s in own if (s.get("email") or "").lower() not in prov_emails | {pulse_lc}
           and (s.get("name") or "").strip().lower() not in prov_names]
    return {
        "site_default": default,
        "machines": machines,
        "options": {
            "pulse": {"name": PULSE_NAME, "email": _pulse_email()},
            "providers": providers,
            "third_party": own,
        },
    }


@router.post("/mod/site/machine-suppliers/third-party")
async def add_third_party_supplier(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    org = await _require_mod_site(user)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name:
        raise HTTPException(400, "Supplier name is required.")
    if not email or "@" not in email:
        raise HTTPException(400, "A valid supplier email is required so faults can reach them.")
    dup = await db.suppliers.find_one(
        {"organization_id": org["id"], "email": email, "estate_supplier_id": {"$exists": False}}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(409, "A supplier with that email already exists for this site.")
    now = _now()
    row = {
        "id": str(uuid.uuid4()), "organization_id": org["id"], "name": name, "email": email,
        "contact_name": (data.get("contact_name") or "").strip(), "phone": (data.get("phone") or "").strip(),
        "notes": (data.get("notes") or "").strip(), "manufacturer_keywords": [],
        "supplier_types": ["service"], "supplier_type": "service",
        "created_via": "mod_site_third_party", "created_by": user.get("email"),
        "created_at": now, "updated_at": now,
    }
    await db.suppliers.insert_one({**row})
    row.pop("_id", None)
    await log_activity("mod_site.third_party_supplier_added", f"Site '{org.get('name')}' added supplier '{name}'",
                       user.get("email") or "", "organization", org["id"])
    return {"supplier": {"id": row["id"], "name": name, "email": email}}


async def _resolve_target(org: dict, target: str) -> dict:
    """Returns {mode, supplier_id, supplier, email, override}."""
    if target == "site_default":
        d = await _site_default(org)
        return {"mode": "site_default", "supplier_id": (d or {}).get("id"), "supplier": (d or {}).get("name"),
                "email": (d or {}).get("email") or _pulse_email(), "override": False}
    if target == "pulse":
        return {"mode": "pulse", "supplier_id": None, "supplier": PULSE_NAME, "email": _pulse_email(), "override": True}
    kind, _, tid = target.partition(":")
    if kind == "provider" and tid:
        est = await db.mod_estate_suppliers.find_one(
            {"id": tid, "mod_estate_id": org.get("mod_estate_id") or DEFAULT_ESTATE_ID}, {"_id": 0})
        if not est:
            raise HTTPException(404, "Service provider not found.")
        row = await db.suppliers.find_one({"organization_id": org["id"], "estate_supplier_id": tid}, {"_id": 0, "id": 1})
        row_id = row["id"] if row else str(uuid.uuid4())
        now = _now()
        await db.suppliers.update_one({"id": row_id}, {
            "$set": {"organization_id": org["id"], "estate_supplier_id": tid, "name": est["name"],
                     "email": est.get("email") or "", "phone": est.get("phone") or "",
                     "contact_name": est.get("contact_name") or "", "manufacturer_keywords": est.get("manufacturer_keywords") or [],
                     "supplier_types": ["service"], "supplier_type": "service", "updated_at": now},
            "$setOnInsert": {"id": row_id, "created_at": now}}, upsert=True)
        override = row_id != (org.get("service_supplier_id") or "")
        return {"mode": "site_default" if not override else "custom", "supplier_id": row_id,
                "supplier": est["name"], "email": est.get("email") or "", "override": override}
    if kind == "supplier" and tid:
        s = await db.suppliers.find_one({"id": tid, "organization_id": org["id"]}, {"_id": 0})
        if not s:
            raise HTTPException(404, "Supplier not found for this site.")
        override = tid != (org.get("service_supplier_id") or "")
        return {"mode": "custom" if override else "site_default", "supplier_id": tid, "supplier": s.get("name"),
                "email": s.get("email") or "", "override": override}
    raise HTTPException(400, "Unknown reassign target.")


def _reassign_email_html(site: str, who: str, machines: list[dict], by: str) -> str:
    rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #eee'>{html.escape(m.get('name') or '')}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{html.escape(m.get('serial_number') or '—')}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{html.escape(m.get('location') or m.get('machine_type') or '—')}</td></tr>"
        for m in machines)
    return (
        "<div style='font-family:Arial,sans-serif;color:#111;max-width:640px'>"
        f"<p>Hello {html.escape(who)},</p>"
        f"<p><b>{len(machines)}</b> machine(s) at <b>{html.escape(site)}</b> are now assigned to you for service. "
        "You will receive fault notifications for these machines from now on.</p>"
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        "<tr style='background:#f3f4f6;text-align:left'><th style='padding:6px 10px'>Machine</th>"
        "<th style='padding:6px 10px'>Serial</th><th style='padding:6px 10px'>Location / type</th></tr>"
        f"{rows}</table>"
        f"<p style='font-size:12px;color:#555'>Reassigned by {html.escape(by)} via the Pulse Fitness MOD Service Portal.</p>"
        "</div>")


@router.post("/mod/site/machine-suppliers/bulk-reassign")
async def bulk_reassign(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    org = await _require_mod_site(user)
    ids = [i for i in (data.get("equipment_ids") or []) if isinstance(i, str) and i]
    if not ids:
        raise HTTPException(400, "Select at least one machine.")
    t = await _resolve_target(org, (data.get("target") or "").strip())
    machines = await db.equipment.find(
        {"organization_id": org["id"], "id": {"$in": ids}},
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "location": 1, "machine_type": 1}).to_list(len(ids))
    if not machines:
        raise HTTPException(404, "None of the selected machines belong to this site.")
    now = _now()
    await db.equipment.update_many(
        {"organization_id": org["id"], "id": {"$in": [m["id"] for m in machines]}},
        [{"$set": {"previous_supplier": "$supplier", "supplier_id": {"$literal": t["supplier_id"]},
                   "supplier": {"$literal": t["supplier"]},
                   "supplier_override": t["override"], "supplier_mode": t["mode"],
                   "supplier_assigned_by": "site_staff_bulk", "supplier_assigned_at": now}}])
    actor = user.get("full_name") or user.get("email") or "Site staff"
    who = t["supplier"] or PULSE_NAME
    await log_activity("mod_site.machines_reassigned",
                       f"{len(machines)} machine(s) at '{org.get('name')}' reassigned to '{who}'",
                       user.get("email") or "", "organization", org["id"])
    emailed = None
    if t["email"]:
        try:
            ok = await send_email(t["email"], f"{len(machines)} machine(s) assigned to you — {org.get('name')}",
                                  _reassign_email_html(org.get("name") or "MOD site", who, machines, actor),
                                  organization_id=org["id"], kind="mod_machines_reassigned", category="mod")
            emailed = t["email"] if ok else None
        except Exception:
            emailed = None
    return {"ok": True, "updated": len(machines), "supplier": who, "mode": t["mode"], "emailed": emailed}
