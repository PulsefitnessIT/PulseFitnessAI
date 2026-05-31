"""Iter 220e3 — CRM → Contracts: Templates + structured cover schema.

Extends the existing Contracts module (``routes/crm_contracts.py``)
WITHOUT duplicating any data. Adds two new resources:

1.  ``crm2_contract_templates`` — admin-editable cover templates
    (Silver / Gold / Platinum / Custom by default, but the tier
    slug + display name are user-controlled). A template carries the
    SAME structured cover shape as a contract so a contract can be
    drafted from a template in one POST.

2.  ``GET /crm/v2/contract-catalog`` — read-only canonical catalog
    of inclusion / exclusion / consumable / response-time items.
    Drives the wizard tick-boxes without forcing every tenant to
    re-seed their own copy. Tenants may override labels by stashing
    a customised catalog in ``crm2_contract_catalog`` (single doc
    per organisation); the GET merges tenant overrides on top.

Schema additions on contract documents (no migration needed — these
fields are optional and additive on existing ``crm2_contracts`` rows):

    {
      "inclusions": {
        "technical_support": ["technical_support", "remote_support", ...],
        "online_support": [...],
        "maintenance": [...],
        "extras": [...],
      },
      "exclusions": ["misuse", "vandalism", ...],
      "consumables": [
        {"name": "Belt lubricant", "included": true, "charge": 0.0},
        ...
      ],
      "response_times": {
        "emergency": {"hours": 4, "unit": "hours"},
        "urgent":    {"hours": 24, "unit": "hours"},
        "standard":  {"hours": 72, "unit": "hours"},
        "remote_support":   {"hours": 2, "unit": "hours"},
        "parts_quotation":  {"hours": 48, "unit": "hours"},
        "first_attendance": {"hours": 48, "unit": "hours"},
      },
      "pricing": {
        "annual_value": 0.0, "monthly_value": 0.0,
        "price_per_asset": 0.0, "setup_fee": 0.0,
        "vat_percent": 20.0, "discount_percent": 0.0,
        "uplift_percent": 0.0,
        "cost_estimate": 0.0,    # internal — never on customer PDF
        "margin_percent": 0.0,   # computed
      },
      "terms_md": "..."  # markdown body merged into the PDF T&Cs
    }
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit
from utils.database import db


router = APIRouter(prefix="/crm/v2", tags=["Contracts · Templates"])


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org if org else "__none__"}


# ── Canonical catalog ────────────────────────────────────────────
#
# Source-of-truth list for the wizard tick-boxes. Mirrors the spec.
# Tenants override LABELS only (not slugs) via ``crm2_contract_catalog``.

INCLUSION_GROUPS: list[dict[str, Any]] = [
    {
        "key": "technical_support",
        "label": "Technical Support",
        "items": [
            {"key": "technical_support",        "label": "Technical support"},
            {"key": "remote_support",           "label": "Remote support"},
            {"key": "local_engineer_support",   "label": "Local engineer support"},
            {"key": "pm_training",              "label": "Preventative maintenance guidance / training"},
        ],
    },
    {
        "key": "online_support",
        "label": "Online Support",
        "items": [
            {"key": "portal_access",            "label": "Customer portal access"},
            {"key": "online_manuals",           "label": "Online manuals"},
            {"key": "service_report_access",    "label": "Service report access"},
            {"key": "asset_history",            "label": "Asset history access"},
            {"key": "customer_fault_logging",   "label": "Customer fault logging"},
        ],
    },
    {
        "key": "maintenance",
        "label": "Maintenance",
        "items": [
            {"key": "callout",                  "label": "Callout included"},
            {"key": "labour",                   "label": "Labour included"},
            {"key": "preventative_maintenance", "label": "Preventative maintenance"},
            {"key": "major_parts",              "label": "Major parts"},
            {"key": "wear_tear_parts",          "label": "Wear & tear parts"},
            {"key": "treadmill_beds",           "label": "Treadmill beds"},
            {"key": "treadmill_belts",          "label": "Treadmill belts"},
            {"key": "upholstery",               "label": "Upholstery"},
            {"key": "software_updates",         "label": "Software updates"},
            {"key": "response_time",            "label": "Organised response time"},
            {"key": "annual_inspection",        "label": "Annual inspection"},
            {"key": "safety_inspection",        "label": "Safety inspection"},
            {"key": "asset_condition_report",   "label": "Asset condition report"},
            {"key": "capex_recommendation",     "label": "CAPEX recommendation"},
        ],
    },
    {
        "key": "extras",
        "label": "Extra Services",
        "items": [
            {"key": "discounted_wear_tear",     "label": "Discounted wear & tear parts"},
            {"key": "discounted_aesthetic",     "label": "Discounted aesthetic parts"},
            {"key": "discounted_labour_rate",   "label": "Discounted labour rate"},
            {"key": "discounted_callout_rate",  "label": "Discounted callout rate"},
            {"key": "priority_booking",         "label": "Priority engineer booking"},
            {"key": "emergency_upgrade",        "label": "Emergency response upgrade"},
            {"key": "annual_audit",             "label": "Annual equipment audit"},
            {"key": "staff_training",           "label": "Staff equipment checks / training"},
            {"key": "monthly_site_report",      "label": "Monthly site report"},
            {"key": "quarterly_asset_review",   "label": "Quarterly asset review"},
        ],
    },
]


EXCLUSION_ITEMS: list[dict[str, str]] = [
    {"key": "misuse",               "label": "Customer misuse"},
    {"key": "accidental",            "label": "Accidental damage"},
    {"key": "vandalism",             "label": "Vandalism"},
    {"key": "cosmetic",              "label": "Cosmetic damage"},
    {"key": "upholstery_excl",       "label": "Upholstery (if not included)"},
    {"key": "beds_excl",             "label": "Treadmill beds / decks (if not included)"},
    {"key": "belts_excl",            "label": "Treadmill belts (if not included)"},
    {"key": "consumables_excl",      "label": "Consumables"},
    {"key": "cleaning",              "label": "Cleaning products"},
    {"key": "corrosion",             "label": "Corrosion / rust due to environment"},
    {"key": "electrical_supply",     "label": "Poor site electrical supply"},
    {"key": "equipment_misuse",      "label": "Misuse of equipment"},
    {"key": "relocation",            "label": "Movement / relocation of equipment"},
    {"key": "carriage",              "label": "Carriage and insurance"},
    {"key": "third_party_delays",    "label": "Third-party manufacturer delays"},
    {"key": "obsolete_parts",        "label": "Obsolete / unavailable parts"},
]


CONSUMABLE_PRESETS: list[dict[str, Any]] = [
    {"name": "Belt lubricant",        "default_charge": 0.0,  "included_default": True},
    {"name": "Wax / silicone spray",  "default_charge": 0.0,  "included_default": True},
    {"name": "Cleaning solutions",    "default_charge": 12.0, "included_default": False},
    {"name": "Replacement keys/fobs", "default_charge": 25.0, "included_default": False},
    {"name": "Touch-up paint",        "default_charge": 18.0, "included_default": False},
]


RESPONSE_TIME_BANDS: list[dict[str, Any]] = [
    {"key": "emergency",        "label": "Emergency",         "default_hours": 4},
    {"key": "urgent",           "label": "Urgent",            "default_hours": 24},
    {"key": "standard",         "label": "Standard",          "default_hours": 72},
    {"key": "remote_support",   "label": "Remote support",    "default_hours": 2},
    {"key": "parts_quotation",  "label": "Parts quotation",   "default_hours": 48},
    {"key": "first_attendance", "label": "First attendance",  "default_hours": 48},
]


# ── Default tier templates ───────────────────────────────────────
#
# Returned on first call to ``GET /contract-templates`` if the
# organisation has none seeded. Tenants then edit / rename them.

def _tier_template(tier: str, name: str, blurb: str,
                   inclusions: dict[str, list[str]],
                   response_overrides: dict[str, int] | None = None) -> dict:
    rt = {b["key"]: {"hours": b["default_hours"], "unit": "hours"} for b in RESPONSE_TIME_BANDS}
    for k, v in (response_overrides or {}).items():
        if k in rt:
            rt[k] = {"hours": v, "unit": "hours"}
    return {
        "tier_slug": tier,
        "name": name,
        "blurb": blurb,
        "is_system_default": True,
        "inclusions": inclusions,
        "exclusions": ["misuse", "vandalism", "accidental", "cleaning"],
        "consumables": [
            {"name": c["name"], "included": c["included_default"],
             "charge": c["default_charge"]}
            for c in CONSUMABLE_PRESETS
        ],
        "response_times": rt,
        "pricing": {
            "annual_value": 0.0, "monthly_value": 0.0,
            "price_per_asset": 0.0, "setup_fee": 0.0,
            "vat_percent": 20.0, "discount_percent": 0.0,
            "uplift_percent": 0.0,
            "cost_estimate": 0.0, "margin_percent": 0.0,
        },
        "terms_md": (
            f"### {name} cover terms\n\n"
            "These terms incorporate the inclusions, exclusions and "
            "response times configured above. Bespoke clauses may be "
            "added per agreement and will appear here.\n"
        ),
    }


def _default_templates() -> list[dict]:
    return [
        _tier_template(
            "silver", "Silver",
            "Essential cover for low-volume sites.",
            inclusions={
                "technical_support": ["technical_support", "remote_support"],
                "online_support": ["portal_access", "online_manuals"],
                "maintenance": ["callout", "labour", "annual_inspection", "safety_inspection"],
                "extras": ["discounted_wear_tear"],
            },
            response_overrides={"emergency": 8, "urgent": 48, "standard": 96},
        ),
        _tier_template(
            "gold", "Gold",
            "Balanced cover for mid-sized estates.",
            inclusions={
                "technical_support": ["technical_support", "remote_support", "local_engineer_support"],
                "online_support": ["portal_access", "online_manuals", "service_report_access", "asset_history"],
                "maintenance": [
                    "callout", "labour", "preventative_maintenance", "major_parts",
                    "wear_tear_parts", "software_updates", "response_time",
                    "annual_inspection", "safety_inspection",
                ],
                "extras": ["discounted_aesthetic", "discounted_labour_rate", "priority_booking"],
            },
            response_overrides={"emergency": 4, "urgent": 24, "standard": 72},
        ),
        _tier_template(
            "platinum", "Platinum",
            "Premium cover with white-glove response.",
            inclusions={
                "technical_support": ["technical_support", "remote_support", "local_engineer_support", "pm_training"],
                "online_support": ["portal_access", "online_manuals", "service_report_access", "asset_history", "customer_fault_logging"],
                "maintenance": [
                    "callout", "labour", "preventative_maintenance", "major_parts",
                    "wear_tear_parts", "treadmill_beds", "treadmill_belts", "upholstery",
                    "software_updates", "response_time", "annual_inspection",
                    "safety_inspection", "asset_condition_report", "capex_recommendation",
                ],
                "extras": [
                    "discounted_aesthetic", "discounted_labour_rate", "discounted_callout_rate",
                    "priority_booking", "emergency_upgrade", "annual_audit",
                    "staff_training", "monthly_site_report", "quarterly_asset_review",
                ],
            },
            response_overrides={"emergency": 2, "urgent": 8, "standard": 24},
        ),
        _tier_template(
            "custom", "Custom",
            "Blank canvas — tick exactly what's required.",
            inclusions={"technical_support": [], "online_support": [],
                        "maintenance": [], "extras": []},
        ),
    ]


# ── Catalog endpoint ─────────────────────────────────────────────


@router.get("/contract-catalog")
async def get_contract_catalog(user: dict = Depends(get_crm_user)):
    """Return the canonical inclusion / exclusion / consumable /
    response-time catalog used by the wizard + templates editor.

    Tenants may stash a single override doc on
    ``crm2_contract_catalog`` keyed by ``organization_id`` that
    relabels (but never renumbers) items. Slugs are immutable so
    contract documents and the comparison matrix stay readable
    across all tenants.
    """
    catalog = {
        "inclusion_groups": INCLUSION_GROUPS,
        "exclusion_items": EXCLUSION_ITEMS,
        "consumable_presets": CONSUMABLE_PRESETS,
        "response_time_bands": RESPONSE_TIME_BANDS,
    }
    org = (user.get("organization_id") or "").strip()
    if not org:
        return catalog
    overrides = await db.crm2_contract_catalog.find_one(
        {"organization_id": org}, {"_id": 0},
    )
    if not overrides:
        return catalog
    # Merge override LABELS in place — never replace keys/slugs.
    label_map = overrides.get("label_overrides") or {}
    if label_map:
        for grp in catalog["inclusion_groups"]:
            for item in grp["items"]:
                item["label"] = label_map.get(item["key"], item["label"])
        for item in catalog["exclusion_items"]:
            item["label"] = label_map.get(item["key"], item["label"])
        for band in catalog["response_time_bands"]:
            band["label"] = label_map.get(band["key"], band["label"])
    return catalog


@router.put("/contract-catalog/labels")
async def update_catalog_labels(data: dict, user: dict = Depends(get_crm_user)):
    """Save tenant-specific label overrides. Slugs cannot be changed."""
    org = (user.get("organization_id") or "").strip()
    if not org:
        raise HTTPException(400, "organization_id required")
    labels = data.get("label_overrides") or {}
    if not isinstance(labels, dict):
        raise HTTPException(400, "label_overrides must be a mapping")
    await db.crm2_contract_catalog.update_one(
        {"organization_id": org},
        {"$set": {
            "organization_id": org,
            "label_overrides": labels,
            "updated_at": _now(),
            "updated_by": user.get("full_name", ""),
        }},
        upsert=True,
    )
    return {"success": True, "count": len(labels)}


# ── Template CRUD ────────────────────────────────────────────────


@router.get("/contract-templates")
async def list_contract_templates(user: dict = Depends(get_crm_user)):
    """List the org's contract templates. Seeds the four defaults
    (Silver / Gold / Platinum / Custom) on first call so the wizard
    always has something to pick from."""
    of = _of(user)
    existing = await db.crm2_contract_templates.find(of, {"_id": 0}).sort("created_at", 1).to_list(200)
    if existing:
        return {"templates": existing}
    # Seed defaults for this tenant.
    seeded = []
    for tpl in _default_templates():
        doc = {
            "id": _id(), "organization_id": user.get("organization_id"),
            "created_at": _now(), "updated_at": _now(),
            "created_by": user.get("full_name", "system"),
            **tpl,
        }
        await db.crm2_contract_templates.insert_one(doc)
        seeded.append({k: v for k, v in doc.items() if k != "_id"})
    return {"templates": seeded}


@router.post("/contract-templates")
async def create_contract_template(data: dict, user: dict = Depends(get_crm_user)):
    """Create a bespoke template. Use ``tier_slug='custom'`` for
    user-defined cover. ``inclusions`` / ``exclusions`` / etc. follow
    the same shape as a contract."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    doc = {
        "id": _id(), "organization_id": user.get("organization_id"),
        "tier_slug": (data.get("tier_slug") or "custom").lower(),
        "name": name,
        "blurb": data.get("blurb", ""),
        "is_system_default": False,
        "inclusions": data.get("inclusions") or {},
        "exclusions": data.get("exclusions") or [],
        "consumables": data.get("consumables") or [],
        "response_times": data.get("response_times") or {},
        "pricing": data.get("pricing") or {},
        "terms_md": data.get("terms_md", ""),
        "created_at": _now(), "updated_at": _now(),
        "created_by": user.get("full_name", ""),
    }
    await db.crm2_contract_templates.insert_one(doc)
    await record_audit(
        entity_type="contract_template", entity_id=doc["id"],
        action="create", user=user, after={k: v for k, v in doc.items() if k != "_id"},
    )
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/contract-templates/{template_id}")
async def update_contract_template(template_id: str, data: dict,
                                   user: dict = Depends(get_crm_user)):
    """Update a template. Renames the tier (e.g. "Silver" → "Basic")
    by setting ``name``; slug is immutable so existing contracts
    still link cleanly."""
    of = _of(user)
    existing = await db.crm2_contract_templates.find_one({"id": template_id, **of}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Template not found")
    exclude = {"id", "organization_id", "created_at", "tier_slug", "is_system_default"}
    updates = {k: v for k, v in data.items() if k not in exclude}
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("full_name", "")
    await db.crm2_contract_templates.update_one({"id": template_id}, {"$set": updates})
    await record_audit(
        entity_type="contract_template", entity_id=template_id,
        action="update", user=user, before=existing, after={**existing, **updates},
    )
    return {"success": True}


@router.delete("/contract-templates/{template_id}")
async def delete_contract_template(template_id: str,
                                   user: dict = Depends(get_crm_user)):
    """Delete a template. System defaults cannot be deleted — rename
    them instead."""
    of = _of(user)
    existing = await db.crm2_contract_templates.find_one({"id": template_id, **of}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Template not found")
    if existing.get("is_system_default"):
        raise HTTPException(400, "System defaults cannot be deleted — rename them instead")
    await db.crm2_contract_templates.delete_one({"id": template_id})
    await record_audit(
        entity_type="contract_template", entity_id=template_id,
        action="delete", user=user, before=existing,
    )
    return {"success": True}


@router.post("/contract-templates/{template_id}/apply/{contract_id}")
async def apply_template_to_contract(template_id: str, contract_id: str,
                                     user: dict = Depends(get_crm_user)):
    """Overlay a template onto an existing draft contract. Useful in
    the wizard when an operator picks Silver/Gold/Platinum mid-flow.
    Only writes the structured cover fields — leaves customer / site /
    asset / dates alone so prior wizard steps aren't clobbered."""
    of = _of(user)
    tpl = await db.crm2_contract_templates.find_one({"id": template_id, **of}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template not found")
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.get("status") not in ("draft", "pending_approval", "negotiation", "amended"):
        raise HTTPException(400, f"Cannot apply template to status '{contract.get('status')}'")
    updates = {
        "tier": tpl.get("tier_slug") or contract.get("tier"),
        "inclusions": tpl.get("inclusions") or {},
        "exclusions_structured": tpl.get("exclusions") or [],
        "consumables": tpl.get("consumables") or [],
        "response_times": tpl.get("response_times") or {},
        "pricing": tpl.get("pricing") or {},
        "terms_md": tpl.get("terms_md", ""),
        "template_id": template_id,
        "updated_at": _now(),
    }
    await db.crm2_contracts.update_one({"id": contract_id}, {"$set": updates})
    await record_audit(
        entity_type="contract", entity_id=contract_id,
        action="apply_template", user=user, before=contract,
        after={**contract, **updates},
        extra={"template_id": template_id, "template_name": tpl.get("name")},
    )
    return {"success": True, "applied": tpl.get("name")}
