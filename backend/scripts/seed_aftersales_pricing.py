"""
Aftersales Contract Automation — deterministic pricing/config importer.

Parses the real Pulse Fitness "Contract Quoting" workbook into MongoDB so the
Aftersales engine prices from AUTHORISED Pulse data (never invented figures).

Collections seeded (all org-scoped by organization_id):
  crm2_afs_rate_groups, crm2_afs_contract_types, crm2_afs_console_rules,
  crm2_afs_service_configs, crm2_afs_skus, crm2_afs_legacy_crosswalk,
  crm2_afs_packages, crm2_afs_pricing_versions, crm2_afs_settings

Idempotent: wipes the org's rows tagged seed_source='contract_quoting_xlsx'
then re-inserts. Package definitions come from the supplied
"Maintenance Agreement Packages" brief (Silver/Gold/Platinum).

Run:  cd /app/backend && PYTHONPATH=/app/backend python scripts/seed_aftersales_pricing.py
Env:  AFS_ORG_ID (default 'iso-demo-org'), AFS_XLSX (default bundled workbook)
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import db  # noqa: E402

SEED_SOURCE = "contract_quoting_xlsx"
ORG_ID = os.environ.get("AFS_ORG_ID", "iso-demo-org")
XLSX = os.environ.get(
    "AFS_XLSX",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "contract_quoting.xlsx"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id():
    return str(uuid.uuid4())


def _num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _s(v):
    return "" if v is None else str(v).strip()


def _find_header_row(ws, anchor, max_scan=8):
    """Return (row_index, {header_text: col_index}) for the row containing anchor."""
    for ri in range(1, max_scan + 1):
        row = [c.value for c in ws[ri]]
        for ci, val in enumerate(row):
            if _s(val).lower() == anchor.lower():
                headers = {}
                for cj, hv in enumerate(row):
                    h = _s(hv)
                    if h:
                        headers[h] = cj
                return ri, headers
    raise RuntimeError(f"Header anchor {anchor!r} not found in sheet {ws.title!r}")


def _rows_after(ws, header_row):
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if any(c is not None and _s(c) != "" for c in row):
            yield row


# ── PACKAGE DEFINITIONS (from Maintenance Agreement Packages brief) ──────────
PACKAGES = [
    {
        "key": "silver",
        "name": "Silver",
        "description": "Reactive cover — technical support, call-out & labour.",
        "technical_support": ["Technical Call Centre", "Online Support", "24/7 Portal Access", "Online Manuals"],
        "maintenance": ["Call Out & Labour"],
        "extras": ["10% off Wear & Tear and Aesthetic Parts"],
        "exclusions": [
            "Preventative Maintenance", "Major Parts", "Organised Response Time", "Toolbox",
            "Software Updates", "Consumables", "Treadmill Beds & Belts", "Upholstery",
            "Carriage & Insurance",
        ],
        "coverage": {
            "callout": True, "labour": True, "preventative_maintenance": False,
            "major_parts": False, "wear_tear_parts": False, "treadmill_beds_belts": False,
            "upholstery": False, "software_updates": False, "consumables": False,
            "carriage_insurance": False, "organised_response_time": False, "toolbox": False,
            "local_engineer": False, "portal_access": True,
        },
        "response_type": "reactive",
    },
    {
        "key": "gold",
        "name": "Gold",
        "description": "Preventative cover — PM visits, major parts, organised response.",
        "technical_support": ["Technical Call Centre", "Local Service Engineer", "Online Support", "24/7 Portal Access", "Online Manuals"],
        "maintenance": ["Call Out & Labour", "Preventative Maintenance", "Major Parts", "Organised Response Time", "Toolbox"],
        "extras": ["10% off Wear & Tear and Aesthetic Parts"],
        "exclusions": ["Treadmill Beds & Belts", "Wear & Tear Parts", "Upholstery", "Carriage & Insurance"],
        "coverage": {
            "callout": True, "labour": True, "preventative_maintenance": True,
            "major_parts": True, "wear_tear_parts": False, "treadmill_beds_belts": False,
            "upholstery": False, "software_updates": False, "consumables": False,
            "carriage_insurance": False, "organised_response_time": True, "toolbox": True,
            "local_engineer": True, "portal_access": True,
        },
        "response_type": "organised",
    },
    {
        "key": "platinum",
        "name": "Platinum",
        "description": "Full comprehensive cover — parts, beds/belts, upholstery, priority response.",
        "technical_support": ["Full Technical Support", "Local Service Engineer", "Preventative Maintenance Training", "Online Support", "24/7 Portal Access", "Online Manuals"],
        "maintenance": [
            "Call Out & Labour", "Preventative Maintenance", "Major Parts", "Wear & Tear Parts",
            "Treadmill Beds & Belts", "Upholstery", "Priority Response Time", "Toolbox",
            "Software Updates", "Carriage & Insurance",
        ],
        "extras": ["10% off Wear & Tear and Aesthetic Parts"],
        # Package doc says N/A — but a wording conflict exists vs the master
        # agreement (Carriage & Insurance). Flag for governance, do not silently resolve.
        "exclusions": [],
        "coverage": {
            "callout": True, "labour": True, "preventative_maintenance": True,
            "major_parts": True, "wear_tear_parts": True, "treadmill_beds_belts": True,
            "upholstery": True, "software_updates": True, "consumables": False,
            "carriage_insurance": True, "organised_response_time": True, "toolbox": True,
            "local_engineer": True, "portal_access": True,
        },
        "response_type": "priority",
        "wording_conflicts": [
            {
                "field": "carriage_insurance",
                "note": "Package sheet lists Carriage & Insurance as INCLUDED (Exclusions: N/A) whereas the master Maintenance Agreement wording treats carriage & insurance as chargeable. Requires management/legal approval before use in a live agreement.",
                "status": "unresolved",
            }
        ],
    },
]


async def seed():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    org = ORG_ID
    now = _now()

    # Wipe prior seed for this org.
    cols = [
        "crm2_afs_rate_groups", "crm2_afs_contract_types", "crm2_afs_console_rules",
        "crm2_afs_service_configs", "crm2_afs_skus", "crm2_afs_legacy_crosswalk",
        "crm2_afs_packages", "crm2_afs_pricing_versions",
    ]
    for c in cols:
        await db[c].delete_many({"organization_id": org, "seed_source": SEED_SOURCE})

    base = {"organization_id": org, "seed_source": SEED_SOURCE, "created_at": now, "updated_at": now}

    # ── Pricing Rules: rate groups + contract types ──────────────────────
    ws = wb["Pricing Rules"]
    hr, H = _find_header_row(ws, "Rate Group")
    rate_groups, contract_types = [], []
    for row in ws.iter_rows(min_row=hr + 1, values_only=True):
        rg = _s(row[H["Rate Group"]]) if "Rate Group" in H else ""
        if rg:
            rate_groups.append({
                **base, "id": _id(), "key": rg.lower().replace(" ", "_").replace("/", "_"),
                "name": rg,
                "standard_pct": _num(row[H["Standard %"]]),
                "preferred_pct": _num(row[H["Preferred %"]]),
                "minimum_pct": _num(row[H["Minimum %"]]),
                "fixed_uplift": _num(row[H["Fixed Annual Uplift"]]),
                "status": _s(row[H["Status"]]) or "Active",
                "notes": _s(row[H["Notes"]]),
            })
        ct = _s(row[H["Contract Type"]]) if "Contract Type" in H else ""
        _factor_cell = row[H["Pricing Factor"]] if "Pricing Factor" in H else None
        if ct and isinstance(_factor_cell, (int, float)):
            contract_types.append({
                **base, "id": _id(), "key": ct.lower(),
                "name": ct,
                "adjustment_pct": _num(row[H["Adjustment %"]]),
                "pricing_factor": _num(row[H["Pricing Factor"]], 1.0),
            })
    if rate_groups:
        await db.crm2_afs_rate_groups.insert_many(rate_groups)
    if contract_types:
        await db.crm2_afs_contract_types.insert_many(contract_types)

    # ── Console Rules ────────────────────────────────────────────────────
    ws = wb["Console Rules"]
    hr, H = _find_header_row(ws, "Console Type")
    console_rules = []
    for row in _rows_after(ws, hr):
        ctp = _s(row[H["Console Type"]])
        if not ctp:
            continue
        console_rules.append({
            **base, "id": _id(), "console_type": ctp,
            "series": _s(row[H["Series"]]),
            "service_multiplier": _num(row[H["Service Multiplier"]], 1.0),
            "fixed_uplift": _num(row[H["Fixed Annual Uplift"]]),
        })
    if console_rules:
        await db.crm2_afs_console_rules.insert_many(console_rules)

    # ── Service Config Master ────────────────────────────────────────────
    ws = wb["Service Config Master"]
    hr, H = _find_header_row(ws, "Service Key")
    configs = []
    for row in _rows_after(ws, hr):
        model = _s(row[H["Model"]])
        console = _s(row[H["Console Type"]])
        if not model:
            continue
        configs.append({
            **base, "id": _id(),
            "display_key": _s(row[H["Service Key"]]),
            "model": model, "console_type": console,
            "series": _s(row[H["Series"]]),
            "description": _s(row[H["Equipment Description"]]),
            "reference_sku": _s(row[H["Reference SKU"]]),
            "sku_count": int(_num(row[H["SKU Count"]])),
            "rrp_snapshot": _num(row[H["RRP Snapshot"]]),
            "highest_rrp": _num(row[H["Highest RRP"]]),
            "rrp_spread_pct": _num(row[H["RRP Spread %"]]),
            "manual_rrp_override": _num(row[H["Manual RRP Override"]]) or None,
            "rate_group": _s(row[H["Rate Group"]]),
            "contract_eligible": _s(row[H["Contract Eligible"]]).lower() in ("yes", "true", "y"),
            "match_quality": _s(row[H["Match Quality"]]),
            "approval_status": _s(row[H["Approval Status"]]),
            "notes": _s(row[H["Notes"]]),
        })
    if configs:
        for i in range(0, len(configs), 500):
            await db.crm2_afs_service_configs.insert_many(configs[i:i + 500])

    # ── SKU Catalogue ────────────────────────────────────────────────────
    ws = wb["SKU Catalogue"]
    hr, H = _find_header_row(ws, "Product Code")
    skus = []
    for row in _rows_after(ws, hr):
        code = _s(row[H["Product Code"]])
        if not code:
            continue
        skus.append({
            **base, "id": _id(), "product_code": code,
            "description": _s(row[H["Description"]]),
            "current_rrp": _num(row[H["Current RRP"]]),
            "model": _s(row[H["Model"]]),
            "product_group": _s(row[H.get("Product Group", -1)]) if "Product Group" in H else "",
            "product_category": _s(row[H.get("Product Category", -1)]) if "Product Category" in H else "",
            "raw_console": _s(row[H["Raw Console"]]) if "Raw Console" in H else "",
            "console_type": _s(row[H["Contract Console Type"]]) if "Contract Console Type" in H else "",
            "service_key": _s(row[H["Service Key"]]) if "Service Key" in H else "",
            "legacy_resale_code": _s(row[H["Legacy Resale Code"]]) if "Legacy Resale Code" in H else "",
            "data_match": _s(row[H["Data Match"]]) if "Data Match" in H else "",
        })
    if skus:
        for i in range(0, len(skus), 1000):
            await db.crm2_afs_skus.insert_many(skus[i:i + 1000])

    # ── Legacy Crosswalk ─────────────────────────────────────────────────
    ws = wb["Legacy Crosswalk"]
    hr, H = _find_header_row(ws, "Legacy Resale Code")
    legacy = []
    for row in _rows_after(ws, hr):
        lrc = _s(row[H["Legacy Resale Code"]])
        if not lrc:
            continue
        legacy.append({
            **base, "id": _id(), "legacy_resale_code": lrc,
            "legacy_sku": _s(row[H["Legacy SKU"]]) if "Legacy SKU" in H else "",
            "current_sku": _s(row[H["Current SKU"]]) if "Current SKU" in H else "",
            "model": _s(row[H["Model"]]),
            "product_name": _s(row[H["Product Name"]]) if "Product Name" in H else "",
            "product_group": _s(row[H["Product Group"]]) if "Product Group" in H else "",
            "raw_console": _s(row[H["Raw Console"]]) if "Raw Console" in H else "",
            "console_type": _s(row[H["Contract Console Type"]]) if "Contract Console Type" in H else "",
            "status": _s(row[H["Status"]]) if "Status" in H else "",
            "service_key": _s(row[H["Service Key"]]) if "Service Key" in H else "",
        })
    if legacy:
        for i in range(0, len(legacy), 1000):
            await db.crm2_afs_legacy_crosswalk.insert_many(legacy[i:i + 1000])

    # ── Packages ─────────────────────────────────────────────────────────
    pkg_docs = []
    for p in PACKAGES:
        pkg_docs.append({
            **base, "id": _id(), **p,
            "version": 1, "status": "approved", "effective_date": now[:10],
            "approved_by": "system_seed",
        })
    await db.crm2_afs_packages.insert_many(pkg_docs)

    # ── Initial pricing version snapshot ─────────────────────────────────
    await db.crm2_afs_pricing_versions.insert_one({
        **base, "id": _id(), "version": 1, "reason": "Initial import from Contract Quoting workbook",
        "created_by": "system_seed",
        "rate_groups": [{k: v for k, v in r.items() if k not in ("_id", "seed_source", "created_at", "updated_at", "organization_id")} for r in rate_groups],
        "contract_types": [{k: v for k, v in r.items() if k not in ("_id", "seed_source", "created_at", "updated_at", "organization_id")} for r in contract_types],
        "console_rules": [{k: v for k, v in r.items() if k not in ("_id", "seed_source", "created_at", "updated_at", "organization_id")} for r in console_rules],
    })

    # ── Settings (current version pointer + defaults) ────────────────────
    await db.crm2_afs_settings.update_one(
        {"organization_id": org},
        {"$set": {
            "organization_id": org, "pricing_version": 1, "vat_pct": 0.20,
            "default_pricing_level": "standard", "updated_at": now,
            "discount_thresholds": [
                {"max_pct": 5, "role": "coordinator", "label": "Coordinator permitted"},
                {"max_pct": 10, "role": "service_manager", "label": "Service Manager approval"},
                {"max_pct": 100, "role": "director", "label": "Director approval"},
            ],
            "renewal_windows_days": [180, 120, 90, 60, 30],
        }},
        upsert=True,
    )

    print("Aftersales seed complete for org", org)
    print("  rate_groups     :", len(rate_groups))
    print("  contract_types  :", len(contract_types), [(c["name"], c["pricing_factor"]) for c in contract_types])
    print("  console_rules   :", len(console_rules))
    print("  service_configs :", len(configs))
    print("  skus            :", len(skus))
    print("  legacy_crosswalk:", len(legacy))
    print("  packages        :", len(pkg_docs))


if __name__ == "__main__":
    asyncio.run(seed())
