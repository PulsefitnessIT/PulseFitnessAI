"""
Aftersales Contract Automation Engine
=====================================
A command centre over the EXISTING CRM / Contracts / Quotes / Assets / Service
Desk records. This module adds only what did not exist:
  • Versioned Package + Pricing-Rules master (Gold-baseline model)
  • Deterministic pricing calculator (single engine for manual + auto quotes)
  • Supportability engine + Service-Manager decision memory
  • Aftersales command-centre dashboard aggregation

Source-of-truth rules (do NOT duplicate): customers/sites/assets/quotes/
contracts all remain in their existing collections. Pricing data comes from the
imported Pulse workbook (crm2_afs_* collections). AI never invents prices —
figures come only from these authorised rules or an authorised manual override.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import asyncio
import logging
import uuid
import re
import io
import os
import secrets

from utils.database import db, EMERGENT_LLM_KEY
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit

from routes.crm_workspace import require_crm_perm  # noqa: E402

router = APIRouter(prefix="/crm/v2/aftersales", tags=["Aftersales Contracts"])


def _id():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc).isoformat()


def _org(user):
    return user.get("organization_id") or "__none__"


def _of(user):
    return {"organization_id": _org(user)}


_PUBLIC = {"_id": 0}
_STRIP = {"_id", "seed_source", "created_at", "updated_at", "organization_id"}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in _STRIP}


# ══════════════════════════════════════════════════════════════════════════
# PRICING / PACKAGE RULES MASTER  (editable + versioned)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/settings")
async def get_settings(user=Depends(get_crm_user)):
    s = await db.crm2_afs_settings.find_one(_of(user), _PUBLIC)
    if not s:
        s = {
            "organization_id": _org(user), "pricing_version": 1, "vat_pct": 0.20,
            "default_pricing_level": "standard",
            "discount_thresholds": [
                {"max_pct": 5, "role": "coordinator", "label": "Coordinator permitted"},
                {"max_pct": 10, "role": "service_manager", "label": "Service Manager approval"},
                {"max_pct": 100, "role": "director", "label": "Director approval"},
            ],
            "renewal_windows_days": [180, 120, 90, 60, 30],
            "alert_email": "",
            "quote_chase_days": "14,5",
            "labour_rate": 75.0,
            "high_claim_ratio": 0.5,
        }
    s.setdefault("alert_email", "")
    s.setdefault("quote_chase_days", "14,5")
    s.setdefault("labour_rate", 75.0)
    s.setdefault("high_claim_ratio", 0.5)
    return s


class SettingsUpdate(BaseModel):
    alert_email: Optional[str] = None
    quote_chase_days: Optional[str] = None
    labour_rate: Optional[float] = None
    high_claim_ratio: Optional[float] = None
    vat_pct: Optional[float] = None
    default_pricing_level: Optional[str] = None


@router.put("/settings")
async def update_settings(body: SettingsUpdate, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        return await get_settings(user)
    patch["updated_at"] = _now()
    await db.crm2_afs_settings.update_one(of, {"$set": patch, "$setOnInsert": {"organization_id": _org(user)}}, upsert=True)
    return await get_settings(user)


@router.get("/ruleset")
async def get_ruleset(user=Depends(get_crm_user)):
    of = _of(user)
    rate_groups = await db.crm2_afs_rate_groups.find(of, _PUBLIC).to_list(200)
    contract_types = await db.crm2_afs_contract_types.find(of, _PUBLIC).to_list(50)
    console_rules = await db.crm2_afs_console_rules.find(of, _PUBLIC).to_list(100)
    settings = await get_settings(user)
    return {
        "rate_groups": sorted(rate_groups, key=lambda r: r.get("name", "")),
        "contract_types": sorted(contract_types, key=lambda c: c.get("pricing_factor", 0)),
        "console_rules": console_rules,
        "version": settings.get("pricing_version", 1),
        "vat_pct": settings.get("vat_pct", 0.20),
    }


async def _snapshot_version(user, reason: str):
    """Freeze the current ruleset into a new version so historic quotes never change."""
    of = _of(user)
    settings = await db.crm2_afs_settings.find_one(of) or {"pricing_version": 1}
    new_version = int(settings.get("pricing_version", 1)) + 1
    rate_groups = await db.crm2_afs_rate_groups.find(of, _PUBLIC).to_list(200)
    contract_types = await db.crm2_afs_contract_types.find(of, _PUBLIC).to_list(50)
    console_rules = await db.crm2_afs_console_rules.find(of, _PUBLIC).to_list(100)
    await db.crm2_afs_pricing_versions.insert_one({
        "id": _id(), "organization_id": _org(user), "version": new_version,
        "reason": reason, "created_by": user.get("email") or user.get("id"),
        "created_at": _now(),
        "rate_groups": [_clean(r) for r in rate_groups],
        "contract_types": [_clean(c) for c in contract_types],
        "console_rules": [_clean(c) for c in console_rules],
    })
    await db.crm2_afs_settings.update_one(
        of, {"$set": {"pricing_version": new_version, "updated_at": _now()}}, upsert=True)
    return new_version


class RateGroupUpdate(BaseModel):
    standard_pct: Optional[float] = None
    preferred_pct: Optional[float] = None
    minimum_pct: Optional[float] = None
    fixed_uplift: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.put("/rate-groups/{rg_id}")
async def update_rate_group(rg_id: str, body: RateGroupUpdate, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    existing = await db.crm2_afs_rate_groups.find_one({"id": rg_id, **of}, _PUBLIC)
    if not existing:
        raise HTTPException(404, "Rate group not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        return existing
    patch["updated_at"] = _now()
    await db.crm2_afs_rate_groups.update_one({"id": rg_id, **of}, {"$set": patch})
    version = await _snapshot_version(user, f"Rate group '{existing.get('name')}' updated")
    await record_audit(entity_type="afs_rate_group", entity_id=rg_id, action="update",
                       user=user, before=_clean(existing), after=patch,
                       summary=f"Rate group '{existing.get('name')}' updated (v{version})")
    return await db.crm2_afs_rate_groups.find_one({"id": rg_id, **of}, _PUBLIC)


class ContractTypeUpdate(BaseModel):
    adjustment_pct: Optional[float] = None
    pricing_factor: Optional[float] = None
    name: Optional[str] = None


@router.put("/contract-types/{ct_id}")
async def update_contract_type(ct_id: str, body: ContractTypeUpdate, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    existing = await db.crm2_afs_contract_types.find_one({"id": ct_id, **of}, _PUBLIC)
    if not existing:
        raise HTTPException(404, "Contract type not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    # keep factor and adjustment% consistent if only one supplied
    if "adjustment_pct" in patch and "pricing_factor" not in patch:
        patch["pricing_factor"] = round(1.0 + patch["adjustment_pct"], 6)
    if "pricing_factor" in patch and "adjustment_pct" not in patch:
        patch["adjustment_pct"] = round(patch["pricing_factor"] - 1.0, 6)
    if not patch:
        return existing
    patch["updated_at"] = _now()
    await db.crm2_afs_contract_types.update_one({"id": ct_id, **of}, {"$set": patch})
    version = await _snapshot_version(user, f"Contract type '{existing.get('name')}' adjustment changed")
    await record_audit(entity_type="afs_contract_type", entity_id=ct_id, action="update",
                       user=user, before=_clean(existing), after=patch,
                       summary=f"Contract type '{existing.get('name')}' adjustment changed (v{version})")
    return await db.crm2_afs_contract_types.find_one({"id": ct_id, **of}, _PUBLIC)


@router.get("/versions")
async def list_versions(user=Depends(get_crm_user)):
    vs = await db.crm2_afs_pricing_versions.find(_of(user), _PUBLIC).sort("version", -1).to_list(100)
    return {"versions": vs}


# ══════════════════════════════════════════════════════════════════════════
# PACKAGES
# ══════════════════════════════════════════════════════════════════════════

@router.get("/packages")
async def list_packages(user=Depends(get_crm_user)):
    pkgs = await db.crm2_afs_packages.find(_of(user), _PUBLIC).to_list(50)
    order = {"silver": 0, "gold": 1, "platinum": 2}
    return {"packages": sorted(pkgs, key=lambda p: order.get(p.get("key"), 9))}


class PackageUpdate(BaseModel):
    description: Optional[str] = None
    technical_support: Optional[List[str]] = None
    maintenance: Optional[List[str]] = None
    extras: Optional[List[str]] = None
    exclusions: Optional[List[str]] = None
    coverage: Optional[dict] = None
    response_type: Optional[str] = None
    status: Optional[str] = None


@router.put("/packages/{pkg_id}")
async def update_package(pkg_id: str, body: PackageUpdate, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    existing = await db.crm2_afs_packages.find_one({"id": pkg_id, **of}, _PUBLIC)
    if not existing:
        raise HTTPException(404, "Package not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        return existing
    patch["version"] = int(existing.get("version", 1)) + 1
    patch["updated_at"] = _now()
    await db.crm2_afs_packages.update_one({"id": pkg_id, **of}, {"$set": patch})
    await record_audit(entity_type="afs_package", entity_id=pkg_id, action="update",
                       user=user, summary=f"Package '{existing.get('key')}' updated (v{patch['version']})")
    return await db.crm2_afs_packages.find_one({"id": pkg_id, **of}, _PUBLIC)


@router.get("/wording-conflicts")
async def wording_conflicts(user=Depends(get_crm_user)):
    """Surface any unresolved commercial-wording conflicts (governance)."""
    pkgs = await db.crm2_afs_packages.find(_of(user), _PUBLIC).to_list(50)
    conflicts = []
    for p in pkgs:
        for w in (p.get("wording_conflicts") or []):
            if w.get("status") != "resolved":
                conflicts.append({"package": p.get("name"), "package_id": p.get("id"), **w})
    return {"conflicts": conflicts, "count": len(conflicts)}


# ══════════════════════════════════════════════════════════════════════════
# SERVICE CONFIG MASTER + SKU / LEGACY lookups
# ══════════════════════════════════════════════════════════════════════════

@router.get("/service-configs")
async def list_service_configs(
    q: str = "", rate_group: str = "", approval: str = "",
    eligible_only: bool = False, limit: int = 100, skip: int = 0,
    user=Depends(get_crm_user),
):
    of = _of(user)
    query = dict(of)
    if q:
        from utils.security_plus import safe_regex
        rx = safe_regex(q)
        query["$or"] = [{"model": rx}, {"console_type": rx}, {"description": rx}, {"display_key": rx}]
    if rate_group:
        query["rate_group"] = rate_group
    if approval:
        query["approval_status"] = {"$regex": approval, "$options": "i"}
    if eligible_only:
        query["contract_eligible"] = True
    total = await db.crm2_afs_service_configs.count_documents(query)
    rows = await db.crm2_afs_service_configs.find(query, _PUBLIC).sort("model", 1).skip(skip).limit(min(limit, 500)).to_list(500)
    return {"configs": rows, "total": total, "skip": skip, "limit": limit}


@router.get("/service-configs/stats")
async def service_config_stats(user=Depends(get_crm_user)):
    of = _of(user)
    total = await db.crm2_afs_service_configs.count_documents(of)
    eligible = await db.crm2_afs_service_configs.count_documents({**of, "contract_eligible": True})
    rrp_required = await db.crm2_afs_service_configs.count_documents({**of, "approval_status": {"$regex": "RRP Required", "$options": "i"}})
    provisional = await db.crm2_afs_service_configs.count_documents({**of, "approval_status": {"$regex": "Provisional", "$options": "i"}})
    by_group = await db.crm2_afs_service_configs.aggregate([
        {"$match": of}, {"$group": {"_id": "$rate_group", "count": {"$sum": 1}}},
    ]).to_list(50)
    return {
        "total": total, "eligible": eligible, "rrp_required": rrp_required,
        "provisional": provisional,
        "by_rate_group": [{"rate_group": g["_id"], "count": g["count"]} for g in by_group],
    }


class ServiceConfigUpdate(BaseModel):
    manual_rrp_override: Optional[float] = None
    approval_status: Optional[str] = None
    rate_group: Optional[str] = None
    contract_eligible: Optional[bool] = None
    notes: Optional[str] = None


@router.put("/service-configs/{cfg_id}")
async def update_service_config(cfg_id: str, body: ServiceConfigUpdate, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    existing = await db.crm2_afs_service_configs.find_one({"id": cfg_id, **of}, _PUBLIC)
    if not existing:
        raise HTTPException(404, "Service configuration not found")
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        return existing
    patch["updated_at"] = _now()
    await db.crm2_afs_service_configs.update_one({"id": cfg_id, **of}, {"$set": patch})
    await record_audit(entity_type="afs_service_config", entity_id=cfg_id, action="update",
                       user=user, before=_clean(existing), after=patch,
                       summary="Service config updated")
    return await db.crm2_afs_service_configs.find_one({"id": cfg_id, **of}, _PUBLIC)


@router.get("/skus")
async def lookup_skus(q: str = "", limit: int = 25, user=Depends(get_crm_user)):
    of = _of(user)
    query = dict(of)
    if q:
        from utils.security_plus import safe_regex
        rx = safe_regex(q)
        query["$or"] = [{"product_code": rx}, {"description": rx}, {"model": rx}]
    rows = await db.crm2_afs_skus.find(query, _PUBLIC).limit(min(limit, 100)).to_list(100)
    return {"skus": rows}


@router.get("/legacy/resolve")
async def resolve_legacy(code: str, user=Depends(get_crm_user)):
    of = _of(user)
    doc = await db.crm2_afs_legacy_crosswalk.find_one(
        {**of, "legacy_resale_code": _eq(code)}, _PUBLIC)
    if not doc:
        doc = await db.crm2_afs_legacy_crosswalk.find_one(
            {**of, "legacy_sku": _eq(code)}, _PUBLIC)
    return {"match": doc, "found": bool(doc)}


# ══════════════════════════════════════════════════════════════════════════
# DETERMINISTIC PRICING ENGINE  (single engine — manual + auto quotes)
# ══════════════════════════════════════════════════════════════════════════

async def _load_engine(org_id: str):
    of = {"organization_id": org_id}
    rate_groups = {r["name"]: r for r in await db.crm2_afs_rate_groups.find(of, _PUBLIC).to_list(200)}
    contract_types = {c["key"]: c for c in await db.crm2_afs_contract_types.find(of, _PUBLIC).to_list(50)}
    console_rules = {c["console_type"]: c for c in await db.crm2_afs_console_rules.find(of, _PUBLIC).to_list(100)}
    settings = await db.crm2_afs_settings.find_one(of) or {}
    return rate_groups, contract_types, console_rules, settings


def _eq(val: str):
    """Case-insensitive exact-match regex with metachars escaped."""
    return {"$regex": f"^{re.escape(val)}$", "$options": "i"}


async def _resolve_config(org_id: str, line: dict):
    """Resolve a quote line to its service config (by config_id, service_key, or model+console)."""
    of = {"organization_id": org_id}
    if line.get("config_id"):
        return await db.crm2_afs_service_configs.find_one({"id": line["config_id"], **of}, _PUBLIC)
    model = (line.get("model") or "").strip()
    console = (line.get("console_type") or "").strip()
    if model:
        query = {**of, "model": _eq(model)}
        if console:
            q2 = {**query, "console_type": _eq(console)}
            cfg = await db.crm2_afs_service_configs.find_one(q2, _PUBLIC)
            if cfg:
                return cfg
        # Model-only (or console not found): prefer a config that can actually
        # be priced — has an RRP and isn't on RRP-hold — so a bare asset maps to
        # its priceable configuration rather than a legacy no-RRP stub.
        cands = await db.crm2_afs_service_configs.find(query, _PUBLIC).to_list(50)
        if cands:
            def _rank(c):
                rrp = c.get("manual_rrp_override") or c.get("rrp_snapshot") or 0
                hold = "hold" in (c.get("approval_status", "").lower())
                approved = "provisional" not in (c.get("approval_status", "").lower()) and not hold
                return (1 if rrp > 0 else 0, 1 if not hold else 0, 1 if approved else 0, rrp)
            cands.sort(key=_rank, reverse=True)
            return cands[0]
    if line.get("service_key"):
        return await db.crm2_afs_service_configs.find_one(
            {**of, "display_key": _eq(line["service_key"])}, _PUBLIC)
    return None


def _price_line(cfg, line, rate_groups, console_rules, pricing_level):
    """Compute the GOLD-baseline annual price for one line.
    Formula (matches Pulse Quote Builder):
      RRP × RateGroup%[level] × ConsoleMultiplier + RateFixedUplift + ConsoleFixedUplift
    """
    qty = max(1, int(line.get("qty") or 1))
    manual = line.get("manual_rrp")
    warnings, status = [], "OK"

    rrp = None
    if manual not in (None, "", 0):
        rrp = float(manual)
    elif cfg:
        rrp = cfg.get("manual_rrp_override") or cfg.get("rrp_snapshot") or 0
    rrp = float(rrp or 0)

    rate_group_name = (cfg or {}).get("rate_group") or line.get("rate_group") or "Standard Equipment"
    rg = rate_groups.get(rate_group_name) or {}
    pct_key = {"standard": "standard_pct", "preferred": "preferred_pct", "minimum": "minimum_pct"}.get(pricing_level, "standard_pct")
    rate_pct = float(rg.get(pct_key, 0) or 0)
    rate_fixed = float(rg.get("fixed_uplift", 0) or 0)

    console = (cfg or {}).get("console_type") or line.get("console_type") or ""
    cr = console_rules.get(console) or {}
    console_mult = float(cr.get("service_multiplier", 1.0) or 1.0)
    console_fixed = float(cr.get("fixed_uplift", 0) or 0)

    if rrp <= 0:
        status = "RRP_REQUIRED"
        warnings.append(f"Manual RRP required for {(cfg or line).get('model') or line.get('model') or 'line'}")
    if rate_pct <= 0 and rate_group_name not in ("Manual Review",):
        warnings.append(f"Rate group '{rate_group_name}' has no rate — manual quote only")
    if rate_group_name == "Manual Review":
        status = "MANUAL_REVIEW"
        warnings.append("Manual Review rate group — requires a manual quote")

    annual_unit = rrp * rate_pct * console_mult + rate_fixed + console_fixed
    annual_line = round(annual_unit * qty, 4)

    if cfg and "hold" in (cfg.get("approval_status", "").lower()):
        if status == "OK":
            status = "PROVISIONAL"
    elif cfg and "provisional" in (cfg.get("approval_status", "").lower()) and status == "OK":
        status = "PROVISIONAL"

    return {
        "model": (cfg or {}).get("model") or line.get("model") or "",
        "console_type": console,
        "description": (cfg or {}).get("description") or line.get("description") or "",
        "qty": qty,
        "service_rrp": round(rrp, 2),
        "rate_group": rate_group_name,
        "rate_pct": rate_pct,
        "console_mult": console_mult,
        "uplift": round(rate_fixed + console_fixed, 2),
        "annual_unit_gold": round(annual_unit, 4),
        "annual_line_gold": annual_line,
        "config_id": (cfg or {}).get("id"),
        "approval_status": (cfg or {}).get("approval_status", ""),
        "status": status,
        "warnings": warnings,
    }


class QuoteLineIn(BaseModel):
    config_id: Optional[str] = None
    service_key: Optional[str] = None
    model: Optional[str] = None
    console_type: Optional[str] = None
    description: Optional[str] = None
    qty: int = 1
    manual_rrp: Optional[float] = None
    rate_group: Optional[str] = None


class CalculateIn(BaseModel):
    lines: List[QuoteLineIn]
    contract_type: str = "gold"
    pricing_level: str = "standard"
    quote_discount_pct: float = 0.0
    term_years: int = 1
    visits_per_year: int = 1
    vat_pct: Optional[float] = None
    has_customer: bool = True
    has_site: bool = True


async def _compute_quote(org_id, lines, contract_type="gold", pricing_level="standard",
                         quote_discount_pct=0.0, term_years=1, vat_pct=None,
                         has_customer=True, has_site=True):
    """Shared deterministic engine used by both manual /pricing/calculate and
    the estate auto-quoter. `lines` = list of dicts (config_id / model+console / qty / manual_rrp)."""
    rate_groups, contract_types, console_rules, settings = await _load_engine(org_id)
    ct = contract_types.get((contract_type or "gold").lower()) or {}
    factor = float(ct.get("pricing_factor", 1.0) or 1.0)
    vat = vat_pct if vat_pct is not None else float(settings.get("vat_pct", 0.20))

    priced, warnings = [], []
    gold_base_annual = 0.0
    for ln in lines:
        cfg = await _resolve_config(org_id, ln)
        row = _price_line(cfg, ln, rate_groups, console_rules, pricing_level)
        gold_base_annual += row["annual_line_gold"]
        warnings.extend(row["warnings"])
        priced.append(row)

    contract_type_annual = round(gold_base_annual * factor, 2)
    discount = max(0.0, float(quote_discount_pct or 0))
    final_annual = round(contract_type_annual * (1 - discount / 100.0), 2)
    vat_amount = round(final_annual * vat, 2)

    health, reasons = "READY_TO_ISSUE", []
    if not has_customer:
        health = "BLOCKED"
        reasons.append("Customer required")
    if not has_site:
        health = "BLOCKED"
        reasons.append("Site required")
    rrp_needed = [p for p in priced if p["status"] == "RRP_REQUIRED"]
    if rrp_needed:
        health = "REVIEW_REQUIRED"
        reasons.append(f"Manual RRP required for {len(rrp_needed)} line(s): " + ", ".join(sorted({p['model'] for p in rrp_needed})))
    manual_review = [p for p in priced if p["status"] == "MANUAL_REVIEW"]
    if manual_review:
        health = "REVIEW_REQUIRED"
        reasons.append(f"{len(manual_review)} line(s) require a manual quote")
    provisional = [p for p in priced if p["status"] == "PROVISIONAL"]
    if provisional and health == "READY_TO_ISSUE":
        health = "REVIEW_REQUIRED"
        reasons.append(f"{len(provisional)} configuration(s) still need Aftersales approval")
    approval_role = None
    for thr in settings.get("discount_thresholds", []):
        if discount <= thr["max_pct"]:
            approval_role = thr
            break
    if approval_role and approval_role.get("role") != "coordinator" and discount > 0:
        health = "REVIEW_REQUIRED" if health != "BLOCKED" else health
        reasons.append(f"{discount:g}% discount requires {approval_role['label']}")
    if not lines:
        health = "BLOCKED"
        reasons.append("Add at least one equipment line")

    return {
        "lines": priced,
        "summary": {
            "units": sum(p["qty"] for p in priced),
            "line_count": len(priced),
            "gold_base_annual": round(gold_base_annual, 2),
            "contract_type": contract_type,
            "contract_factor": factor,
            "contract_type_annual": contract_type_annual,
            "quote_discount_pct": discount,
            "final_annual": final_annual,
            "monthly": round(final_annual / 12.0, 2),
            "term_years": term_years,
            "term_total": round(final_annual * max(1, term_years), 2),
            "vat_pct": vat,
            "vat_amount": vat_amount,
            "final_annual_inc_vat": round(final_annual + vat_amount, 2),
        },
        "quote_health": health,
        "health_reasons": reasons,
        "warnings": sorted(set(warnings)),
        "pricing_version": settings.get("pricing_version", 1),
    }


@router.post("/pricing/calculate")
async def calculate(body: CalculateIn, user=Depends(get_crm_user)):
    return await _compute_quote(
        _org(user), [ln.dict() for ln in body.lines], body.contract_type, body.pricing_level,
        body.quote_discount_pct, body.term_years, body.vat_pct, body.has_customer, body.has_site)


# ══════════════════════════════════════════════════════════════════════════
# SUPPORTABILITY ENGINE  +  decision memory
# ══════════════════════════════════════════════════════════════════════════

SUPPORTABILITY_STATUSES = [
    {"id": "fully_supported", "name": "Fully Supported", "color": "#22C55E"},
    {"id": "supported_with_exclusions", "name": "Supported with Exclusions", "color": "#84CC16"},
    {"id": "limited_support", "name": "Limited Support", "color": "#F59E0B"},
    {"id": "manual_review", "name": "Manual Review", "color": "#F59E0B"},
    {"id": "do_not_contract", "name": "Do Not Contract", "color": "#EF4444"},
    {"id": "third_party_review", "name": "Third-Party Review", "color": "#19CDFF"},
]


@router.get("/supportability/statuses")
async def supportability_statuses(user=Depends(get_crm_user)):
    return {"statuses": SUPPORTABILITY_STATUSES}


@router.get("/supportability/decisions")
async def list_supportability_decisions(q: str = "", status: str = "", user=Depends(get_crm_user)):
    of = _of(user)
    query = dict(of)
    if status:
        query["status"] = status
    if q:
        from utils.security_plus import safe_regex
        rx = safe_regex(q)
        query["$or"] = [{"model": rx}, {"manufacturer": rx}, {"console_type": rx}]
    rows = await db.crm2_afs_supportability.find(query, _PUBLIC).sort("updated_at", -1).to_list(500)
    return {"decisions": rows, "total": len(rows)}


class SupportabilityIn(BaseModel):
    manufacturer: str = "Pulse Fitness"
    model: str
    console_type: Optional[str] = ""
    config: Optional[str] = ""
    status: str
    permitted_contract_types: List[str] = []
    exclusions: List[str] = []
    reason: str = ""
    review_date: Optional[str] = None


@router.post("/supportability/decisions")
async def upsert_supportability_decision(body: SupportabilityIn, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    valid = {s["id"] for s in SUPPORTABILITY_STATUSES}
    if body.status not in valid:
        raise HTTPException(400, f"Invalid status. One of {sorted(valid)}")
    key = {**of, "manufacturer": body.manufacturer, "model": body.model,
           "console_type": body.console_type or ""}
    now = _now()
    doc = {
        **key, "config": body.config or "", "status": body.status,
        "permitted_contract_types": body.permitted_contract_types,
        "exclusions": body.exclusions, "reason": body.reason,
        "review_date": body.review_date,
        "approved_by": user.get("email") or user.get("id"),
        "approval_date": now, "updated_at": now,
    }
    existing = await db.crm2_afs_supportability.find_one(key, _PUBLIC)
    if existing:
        await db.crm2_afs_supportability.update_one(key, {"$set": doc})
        doc["id"] = existing["id"]
        action = "afs_supportability_updated"
    else:
        doc["id"] = _id()
        doc["created_at"] = now
        await db.crm2_afs_supportability.insert_one(doc)
        action = "afs_supportability_created"
    await record_audit(entity_type="afs_supportability", entity_id=doc["id"],
                       action="update" if action == "afs_supportability_updated" else "create",
                       user=user, summary=f"Supportability decision {body.model} → {body.status}",
                       extra={"model": body.model, "status": body.status})
    return await db.crm2_afs_supportability.find_one(key, _PUBLIC)


@router.delete("/supportability/decisions/{dec_id}")
async def delete_supportability_decision(dec_id: str, user=Depends(require_crm_perm("pricing.manage"))):
    res = await db.crm2_afs_supportability.delete_one({"id": dec_id, **_of(user)})
    if not res.deleted_count:
        raise HTTPException(404, "Decision not found")
    return {"deleted": True}


@router.post("/supportability/evaluate")
async def evaluate_supportability(body: dict, user=Depends(get_crm_user)):
    """Derive a supportability status for a piece of equipment using the
    decision memory first, then rate-group / RRP heuristics. Never rejects
    purely on age — falls back to Manual Review."""
    of = _of(user)
    model = (body.get("model") or "").strip()
    console = (body.get("console_type") or "").strip()
    (body.get("manufacturer") or "Pulse Fitness").strip()

    # 1. Exact decision memory (model + console).
    mem = None
    if model:
        mem = await db.crm2_afs_supportability.find_one(
            {**of, "model": _eq(model), "console_type": _eq(console)}, _PUBLIC)
        if not mem:
            mem = await db.crm2_afs_supportability.find_one(
                {**of, "model": _eq(model)}, _PUBLIC)
    if mem:
        return {"status": mem["status"], "source": "decision_memory",
                "permitted_contract_types": mem.get("permitted_contract_types", []),
                "exclusions": mem.get("exclusions", []), "reason": mem.get("reason", ""),
                "decision_id": mem.get("id")}

    # 2. Service config heuristics.
    cfg = await _resolve_config(_org(user), {"model": model, "console_type": console})
    if not cfg:
        return {"status": "manual_review", "source": "no_config",
                "reason": "No service configuration found for this model — Service Manager review required."}
    if not cfg.get("contract_eligible", False):
        return {"status": "do_not_contract", "source": "config",
                "reason": "Marked not contract-eligible in the Service Config Master."}
    if "hold" in (cfg.get("approval_status", "").lower()) or (cfg.get("rrp_snapshot") or 0) <= 0:
        return {"status": "manual_review", "source": "config",
                "reason": "Legacy configuration with no current RRP — Aftersales must approve a reference price first."}
    if cfg.get("rate_group") == "Manual Review":
        return {"status": "manual_review", "source": "config",
                "reason": "Rate group is Manual Review."}
    return {"status": "fully_supported", "source": "config",
            "permitted_contract_types": ["silver", "gold", "platinum"],
            "reason": "Current configuration with an approved reference RRP."}


# ══════════════════════════════════════════════════════════════════════════
# COMMAND-CENTRE DASHBOARD  (aggregates EXISTING records)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def dashboard(user=Depends(get_crm_user)):
    of = _of(user)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    def plus(days):
        return (now + timedelta(days=days)).strftime("%Y-%m-%d")

    # Contracts (existing crm2_contracts).
    active = await db.crm2_contracts.count_documents({**of, "status": "active"})
    renew_90 = await db.crm2_contracts.count_documents(
        {**of, "status": "active", "end_date": {"$lte": plus(90), "$gte": today}})
    renew_180 = await db.crm2_contracts.count_documents(
        {**of, "status": "active", "end_date": {"$lte": plus(180), "$gte": today}})
    expired = await db.crm2_contracts.count_documents({**of, "status": "expired"})

    acv_agg = await db.crm2_contracts.aggregate([
        {"$match": {**of, "status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$annual_value"}}},
    ]).to_list(1)
    acv = acv_agg[0]["total"] if acv_agg else 0

    # RPI reviews due (contracts with an anniversary in the next 60 days
    # that have not had an RPI review this cycle). Uses start_date month/day.
    rpi_due = 0
    async for c in db.crm2_contracts.find({**of, "status": "active"}, {"_id": 0, "start_date": 1, "rpi_last_review": 1}):
        sd = c.get("start_date") or ""
        if len(sd) >= 10:
            try:
                anniv = datetime.strptime(sd[:10], "%Y-%m-%d").replace(year=now.year, tzinfo=timezone.utc)
                if anniv < now:
                    anniv = anniv.replace(year=now.year + 1)
                if (anniv - now).days <= 60 and (c.get("rpi_last_review") or "")[:7] != now.strftime("%Y-%m"):
                    rpi_due += 1
            except ValueError:
                pass

    # Quotes (existing crm_quotes / CPQ).
    q_draft = await db.crm_quotes.count_documents({**of, "status": {"$in": ["draft", "pending"]}})
    q_draft += await db.crm2_afs_quotes.count_documents({**of, "status": "draft"})
    q_approval = await db.crm_quotes.count_documents({**of, "status": {"$in": ["pending_approval", "awaiting_approval"]}})
    q_sent = await db.crm_quotes.count_documents({**of, "status": {"$in": ["sent", "viewed"]}})
    q_accepted = await db.crm_quotes.count_documents({**of, "status": "accepted"})

    # Agreements awaiting signature / ready to activate (existing contracts).
    awaiting_sig = await db.crm2_contracts.count_documents({**of, "status": {"$in": ["sent", "negotiation"]}})
    awaiting_sig += await db.crm2_afs_agreements.count_documents({**of, "status": {"$in": ["ready", "sent"]}})
    ready_activate = await db.crm2_contracts.count_documents({**of, "status": "signed"})
    ready_activate += await db.crm2_afs_agreements.count_documents({**of, "status": "signed"})

    # Supportability review count (config-level, not yet decided).
    support_review = await db.crm2_afs_service_configs.count_documents(
        {**of, "contract_eligible": True, "approval_status": {"$regex": "Hold|Provisional", "$options": "i"}})

    # Wording conflicts.
    wc = await wording_conflicts(user)

    return {
        "cards": {
            "renewal_opportunities": renew_90,
            "renewal_window_180": renew_180,
            "quotes_to_prepare": q_draft,
            "quotes_awaiting_approval": q_approval,
            "quotes_with_customer": q_sent,
            "quotes_accepted": q_accepted,
            "agreements_awaiting_signature": awaiting_sig,
            "contracts_ready_to_activate": ready_activate,
            "rpi_reviews_due": rpi_due,
            "supportability_reviews": support_review,
            "wording_conflicts": wc["count"],
            "active_contracts": active,
            "expired_contracts": expired,
            "annual_contract_value": round(acv, 2),
        },
        "generated_at": _now(),
    }


@router.get("/priorities")
async def priorities(user=Depends(get_crm_user)):
    """MY PRIORITIES TODAY — a ranked action list drawn from existing records."""
    of = _of(user)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    items = []

    # Expiring contracts without an issued renewal quote → HIGH.
    for c in await db.crm2_contracts.find(
        {**of, "status": "active", "end_date": {"$gte": today}},
        {"_id": 0, "id": 1, "company_name": 1, "title": 1, "end_date": 1, "tier": 1, "annual_value": 1},
    ).sort("end_date", 1).to_list(200):
        try:
            days = (datetime.strptime(c["end_date"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) - now).days
        except (ValueError, KeyError):
            continue
        if days <= 90:
            level = "HIGH" if days <= 30 else ("ACTION" if days <= 60 else "REVIEW")
            items.append({
                "level": level, "kind": "renewal",
                "title": c.get("company_name") or c.get("title") or "Contract",
                "detail": f"Contract expires in {days} days — renewal not yet issued",
                "contract_id": c.get("id"), "value": c.get("annual_value", 0),
                "sort": days,
            })

    # Accepted MAINTENANCE quotes (crm2_afs_quotes) → agreement ready to generate.
    for q in await db.crm2_afs_quotes.find({**of, "status": "accepted"},
                                           {"_id": 0, "id": 1, "company_name": 1, "summary": 1}).to_list(100):
        if await db.crm2_afs_agreements.find_one({**of, "quote_id": q["id"], "status": {"$nin": ["cancelled", "superseded"]}}, {"_id": 1}):
            continue
        items.append({
            "level": "ACTION", "kind": "agreement",
            "title": q.get("company_name") or "Customer",
            "detail": "Customer accepted maintenance quote — agreement ready to generate",
            "quote_id": q.get("id"), "value": (q.get("summary") or {}).get("annual_total", 0), "sort": -1,
        })
    # Accepted EQUIPMENT sales (crm_quotes) never go straight to an agreement —
    # they surface only as a maintenance opportunity once equipment is confirmed.
    for a in await db.crm2_activities.find({**of, "type": "sales_handover", "status": "open"},
                                           {"_id": 0, "company_name": 1, "source_sales_quote_id": 1, "equipment_count": 1}).to_list(50):
        items.append({
            "level": "ACTION", "kind": "maintenance_opportunity",
            "title": a.get("company_name") or "Customer",
            "detail": f"Equipment sale delivered — {a.get('equipment_count', 0)} confirmed machine(s) ready for a maintenance quote",
            "sales_quote_id": a.get("source_sales_quote_id"), "value": 0, "sort": -1,
        })

    order = {"HIGH": 0, "ACTION": 1, "REVIEW": 2, "RPI": 3}
    items.sort(key=lambda i: (order.get(i["level"], 9), i.get("sort", 0)))
    return {"priorities": items[:50], "count": len(items)}



# ══════════════════════════════════════════════════════════════════════════
# BUILD QUOTE FROM ESTATE  (one-click auto-quoter + exception queue)
# ══════════════════════════════════════════════════════════════════════════

async def _resolve_linked_org_for_company(company: dict, user: dict) -> str:
    linked = company.get("linked_organization_id") or ""
    if linked:
        return linked
    uoid = user.get("organization_id") or ""
    if uoid:
        uo = await db.organizations.find_one({"id": uoid}, {"_id": 0, "name": 1}) or {}
        if (uo.get("name") or "").strip().lower() == (company.get("name") or "").strip().lower():
            return uoid
    return ""


async def _annotate_asset(org_id, eq):
    """Match an asset to its service config + supportability + pricing status."""
    model = eq.get("model") or eq.get("model_code") or ""
    console = eq.get("console_type") or ""
    cfg = await _resolve_config(org_id, {"model": model, "console_type": console}) if model else None
    supp = None
    if model:
        supp = await db.crm2_afs_supportability.find_one(
            {"organization_id": org_id, "model": _eq(model)}, _PUBLIC)
    rrp = None
    rate_group = ""
    approval = ""
    eligible = False
    if cfg:
        rrp = cfg.get("manual_rrp_override") or cfg.get("rrp_snapshot") or 0
        rate_group = cfg.get("rate_group", "")
        approval = cfg.get("approval_status", "")
        eligible = bool(cfg.get("contract_eligible"))
    # pricing status
    if not cfg:
        pstatus = "NOT_MATCHED"
    elif not eligible:
        pstatus = "NOT_ELIGIBLE"
    elif (rrp or 0) <= 0 or "hold" in approval.lower():
        pstatus = "RRP_REQUIRED"
    elif "provisional" in approval.lower():
        pstatus = "PROVISIONAL"
    else:
        pstatus = "SUPPORTED"
    supp_status = supp.get("status") if supp else None
    if supp_status in ("do_not_contract", "manual_review", "third_party_review", "limited_support"):
        pstatus = "SUPPORTABILITY_REVIEW" if pstatus == "SUPPORTED" else pstatus
    return {
        "id": eq.get("id"), "name": eq.get("name"), "model": model, "console_type": console,
        "serial_number": eq.get("serial_number", ""), "site_id": eq.get("site_id"),
        "warranty_expiry": eq.get("warranty_expiry", ""),
        "config_id": cfg.get("id") if cfg else None,
        "rrp": round(float(rrp or 0), 2), "rate_group": rate_group,
        "approval_status": approval, "contract_eligible": eligible,
        "supportability": supp_status, "pricing_status": pstatus,
        "lifecycle_stage": eq.get("lifecycle_stage"), "equipment_status": eq.get("status"),
    }


@router.get("/estate/{company_id}")
async def estate(company_id: str, user=Depends(get_crm_user)):
    """Load the customer's estate (existing asset register) annotated with
    service-config match, supportability and pricing status — grouped by site."""
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    org_id = _org(user)
    linked = await _resolve_linked_org_for_company(company, user)
    if not linked:
        return {"company": {"id": company_id, "name": company.get("name")},
                "linked_organization_id": None, "sites": [], "totals": {}}
    sites = await db.sites.find(
        {"organization_id": linked, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "city": 1, "postcode": 1}).sort("name", 1).to_list(500)
    equipment = await db.equipment.find(
        {"organization_id": linked},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
         "manufacturer": 1, "serial_number": 1, "site_id": 1, "warranty_expiry": 1, "status": 1, "lifecycle_stage": 1}).to_list(None)
    annotated = [await _annotate_asset(org_id, e) for e in equipment]
    by_site = {}
    for a in annotated:
        by_site.setdefault(a.get("site_id") or "__unassigned__", []).append(a)
    site_rows = []
    for s in sites:
        assets = by_site.get(s["id"], [])
        site_rows.append({**s, "assets": assets, "asset_count": len(assets),
                          "supported": sum(1 for a in assets if a["pricing_status"] == "SUPPORTED")})
    if by_site.get("__unassigned__"):
        ua = by_site["__unassigned__"]
        site_rows.append({"id": "__unassigned__", "name": "Unassigned (no site)", "assets": ua,
                          "asset_count": len(ua), "supported": sum(1 for a in ua if a["pricing_status"] == "SUPPORTED")})
    flat = [a for s in site_rows for a in s["assets"]]
    return {
        "company": {"id": company_id, "name": company.get("name")},
        "linked_organization_id": linked,
        "sites": site_rows,
        "totals": {
            "sites": len(site_rows), "assets": len(flat),
            "supported": sum(1 for a in flat if a["pricing_status"] == "SUPPORTED"),
            "exceptions": sum(1 for a in flat if a["pricing_status"] not in ("SUPPORTED",)),
        },
    }


class BuildFromEstateIn(BaseModel):
    company_id: str
    site_ids: Optional[List[str]] = None          # None/empty = all sites
    asset_ids: Optional[List[str]] = None          # restrict to specific assets (e.g. warranty conversion)
    contract_type: str = "gold"
    pricing_level: str = "standard"
    term_years: int = 1
    quote_discount_pct: float = 0.0
    save: bool = False
    source: str = "auto_estate"
    source_sales_quote_id: Optional[str] = None
    source_import_id: Optional[str] = None
    force_new: bool = False


@router.post("/build-quote-from-estate")
async def build_quote_from_estate(body: BuildFromEstateIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    of = _of(user)
    org_id = _org(user)
    company = await db.crm2_companies.find_one({"id": body.company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    linked = await _resolve_linked_org_for_company(company, user)
    if not linked:
        raise HTTPException(400, "This company is not linked to an operations organisation — no estate to quote.")

    eq_query = {"organization_id": linked}
    if body.site_ids:
        eq_query["site_id"] = {"$in": body.site_ids}
    equipment = await db.equipment.find(
        eq_query,
        {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
         "serial_number": 1, "site_id": 1, "warranty_expiry": 1, "contract_cover": 1, "status": 1, "lifecycle_stage": 1}).to_list(None)
    if body.asset_ids:
        _wanted = set(body.asset_ids)
        equipment = [e for e in equipment if e.get("id") in _wanted]
    annotated = [await _annotate_asset(org_id, e) for e in equipment]
    cover_ids = {(e.get("contract_cover") or {}).get("contract_id") for e in equipment} - {None}
    live = {c["id"] for c in await db.crm2_contracts.find(
        {**of, "id": {"$in": list(cover_ids)}, "status": "active"}, {"_id": 0, "id": 1}).to_list(None)} if cover_ids else set()
    covered_by = {e["id"]: e["contract_cover"]["contract_id"] for e in equipment
                  if (e.get("contract_cover") or {}).get("contract_id") in live}
    for a in annotated:
        if a["id"] in covered_by:
            a["pricing_status"], a["covered_by_contract_id"] = "ALREADY_COVERED", covered_by[a["id"]]
    priceable = [a for a in annotated if a["pricing_status"] in ("SUPPORTED", "PROVISIONAL", "RRP_REQUIRED")]
    lines = [{"config_id": a["config_id"], "model": a["model"], "console_type": a["console_type"], "qty": 1}
             for a in priceable]
    result = await _compute_quote(org_id, lines, body.contract_type, body.pricing_level,
                                  body.quote_discount_pct, body.term_years,
                                  has_customer=True, has_site=bool(equipment))

    # Group priced assets by (model, console) for the commercial view; retain serials.
    rate_groups, contract_types, console_rules, _s = await _load_engine(org_id)
    factor = float((contract_types.get(body.contract_type.lower()) or {}).get("pricing_factor", 1.0))
    disc_mult = (1 - max(0.0, body.quote_discount_pct) / 100.0)
    row_by_cfg = {r.get("config_id"): r for r in result["lines"] if r.get("config_id")}
    groups = {}
    for a in priceable:
        cid = a["config_id"]
        row = row_by_cfg.get(cid) or {}
        g = groups.setdefault(cid, {
            "config_id": cid,
            "model": row.get("model") or a["model"],
            "console_type": row.get("console_type") or a["console_type"],
            "description": row.get("description", ""),
            "qty": 0, "serials": [], "asset_ids": [],
            "annual_unit": round((row.get("annual_unit_gold", 0)) * factor * disc_mult, 2),
        })
        g["qty"] += 1
        g["serials"].append(a["serial_number"])
        g["asset_ids"].append(a["id"])
    for g in groups.values():
        g["annual_total"] = round(g["annual_unit"] * g["qty"], 2)
    grouped = list(groups.values())

    # Stamp each priceable asset with its computed annual (from its group).
    for a in annotated:
        g = groups.get(a["config_id"])
        a["annual"] = g["annual_unit"] if (g and a["pricing_status"] in ("SUPPORTED", "PROVISIONAL")) else 0

    # Exceptions (§22 / §99).
    exceptions = []
    for a in annotated:
        st = a["pricing_status"]
        if st == "RRP_REQUIRED":
            exceptions.append({"kind": "RRP_REQUIRED", "asset_id": a["id"], "model": a["model"],
                               "console_type": a["console_type"], "config_id": a["config_id"],
                               "detail": f"{a['model']} needs an approved manual RRP before it can be priced."})
        elif st == "SUPPORTABILITY_REVIEW":
            exceptions.append({"kind": "SUPPORTABILITY", "asset_id": a["id"], "model": a["model"],
                               "console_type": a["console_type"],
                               "detail": f"{a['model']} needs a Service-Manager supportability decision."})
        elif st == "NOT_ELIGIBLE":
            exceptions.append({"kind": "NOT_ELIGIBLE", "asset_id": a["id"], "model": a["model"],
                               "detail": f"{a['model']} is marked not contract-eligible."})
        elif st == "NOT_MATCHED":
            exceptions.append({"kind": "NOT_MATCHED", "asset_id": a["id"], "model": a["model"],
                               "detail": f"No service configuration matches '{a['model']}'."})
        elif st == "ALREADY_COVERED":
            exceptions.append({"kind": "ALREADY_COVERED", "asset_id": a["id"], "model": a["model"],
                               "detail": f"{a['model']} {a.get('serial_number') or ''} is already covered by an active "
                                         f"maintenance contract — excluded from this quote."})
        elif st == "PROVISIONAL":
            exceptions.append({"kind": "PROVISIONAL", "asset_id": a["id"], "model": a["model"],
                               "config_id": a["config_id"],
                               "detail": f"{a['model']} configuration still needs Aftersales approval."})

    for a in annotated:
        if a["pricing_status"] == "SUPPORTED" and not a.get("annual"):
            exceptions.append({"kind": "TARIFF_MISSING", "asset_id": a["id"], "model": a["model"],
                               "config_id": a.get("config_id"),
                               "detail": f"{a['model']} is matched and eligible, but no approved maintenance tariff "
                                         f"gives it a price — add the tariff before issuing."})
    total_assets = len(annotated)
    priced_with_value = sum(1 for a in annotated if a.get("annual", 0) > 0)
    pct_priced = round(100.0 * priced_with_value / total_assets, 1) if total_assets else 0
    if total_assets == 0 or priced_with_value == 0:
        confidence = "CANNOT_AUTO_QUOTE"
    elif exceptions:
        confidence = "REVIEW_REQUIRED"
    else:
        confidence = "READY_FOR_REVIEW"

    auto = {
        "confidence": confidence,
        "assets_total": total_assets,
        "assets_priced": priced_with_value,
        "pct_automatically_priced": pct_priced,
        "exception_count": len(exceptions),
        "exceptions": exceptions,
        "grouped_lines": grouped,
        "asset_register": annotated,
        **result,
    }

    src_key = ({"source_sales_quote_id": body.source_sales_quote_id} if body.source_sales_quote_id else
               {"source_import_id": body.source_import_id} if body.source_import_id else None)
    if body.save and src_key and not body.force_new:
        prior = await db.crm2_afs_quotes.find_one(
            {**of, **src_key, "status": {"$nin": ["cancelled", "superseded", "declined"]}},
            {"_id": 0, "id": 1, "quote_number": 1})
        if prior:
            auto["saved_quote_id"], auto["quote_number"], auto["existing"] = prior["id"], prior["quote_number"], True
            return auto
    if body.save:
        qid = _id()
        unpriced = [a["id"] for a in priceable if a["pricing_status"] != "SUPPORTED" or not a.get("annual")]
        imp = await db.crm2_afs_quote_imports.find_one({**of, "id": body.source_import_id}, {"_id": 0}) \
            if body.source_import_id else None
        live_pl = await db.crm_price_list_versions.find_one({**of, "status": "live"}, {"_id": 0, "id": 1, "name": 1})
        doc = {
            "source_sales_quote_id": body.source_sales_quote_id or (imp or {}).get("source_sales_quote_id"),
            "source_import_id": body.source_import_id,
            "source_documents": [{"import_id": imp["id"], "doc_type": imp["doc_type"], "filename": imp["filename"],
                                  "document_ref": (imp.get("extracted") or {}).get("document_ref"),
                                  "sha256": imp["sha256"], "storage_path": imp["storage_path"]}] if imp else [],
            "unpriced_count": len(unpriced), "unpriced_asset_ids": unpriced,
            "price_list_version": live_pl, "tariff_version": result.get("pricing_version"),
            "visits_per_year": result.get("summary", {}).get("visits_per_year"),
            "id": qid, "organization_id": org_id,
            "quote_number": f"AFS-{datetime.now(timezone.utc).strftime('%Y')}-{qid[:5].upper()}",
            "company_id": body.company_id, "company_name": company.get("name"),
            "linked_organization_id": linked, "site_ids": body.site_ids or [],
            "contract_type": body.contract_type, "pricing_level": body.pricing_level,
            "term_years": body.term_years, "quote_discount_pct": body.quote_discount_pct,
            "status": "draft", "source": body.source,
            "confidence": confidence, "pct_automatically_priced": pct_priced,
            "exception_count": len(exceptions), "exceptions": exceptions,
            "grouped_lines": grouped, "asset_register": annotated,
            "summary": result["summary"], "quote_health": result["quote_health"],
            "health_reasons": result["health_reasons"],
            "pricing_version": result["pricing_version"],
            "created_by": user.get("email") or user.get("id"),
            "created_at": _now(), "updated_at": _now(),
        }
        await db.crm2_afs_quotes.insert_one(doc)
        await record_audit(entity_type="afs_quote", entity_id=qid, action="create",
                           user=user, extra={"company": company.get("name"), "confidence": confidence})
        auto["saved_quote_id"] = qid
        auto["quote_number"] = doc["quote_number"]
        auto["unpriced_count"] = len(unpriced)
        if imp:
            await db.crm2_afs_quote_imports.update_one({"id": imp["id"]}, {"$set": {
                "quote_id": qid, "quote_number": doc["quote_number"], "status": "quoted", "updated_at": _now()}})
        if body.source_sales_quote_id:
            from utils.cm_actions import resolve_action
            await db.crm2_activities.update_one(
                {**of, "dedupe_key": f"cm:sale-handover:{body.source_sales_quote_id}"},
                {"$set": {"maintenance_quote_id": qid, "maintenance_quote_number": doc["quote_number"]}})
            await resolve_action(org_id, f"cm:sale-handover:{body.source_sales_quote_id}",
                                 f"Maintenance quote {doc['quote_number']} prepared.")

    return auto


# ── Custom tender pricing (AI upload) ──────────────────────────────
# When a customer's tender fixes bespoke prices (e.g. a signed agreement
# Schedule of Charges), the operator uploads that paperwork; Claude extracts
# the per-machine-type service prices + per-site travel costs; the operator
# reviews/edits, then builds a quote that applies those bespoke rates to the
# customer's actual machine estate. AI is suggestion-only — never auto-saved.

_TYPE_SYNONYMS = {
    "treadmill": ["treadmill"],
    "bike": ["bike", "cycle", "cycling", "spin", "ergometer bike"],
    "rower": ["rower", "rowing"],
    "cross trainer": ["cross trainer", "crosstrainer", "elliptical", "x-trainer", "xtrainer"],
    "power rack": ["power rack", "smith", "rack"],
    "free weights": ["free weight", "dumbbell", "barbell", "bench", "plate"],
    "ski erg": ["ski erg", "skierg"],
    "stepper": ["stepper", "step mill", "stairmaster", "climber"],
}


def _type_keywords(type_name: str) -> list:
    t = (type_name or "").strip().lower()
    kws = {t} if t else set()
    for w in t.split():
        if len(w) > 2:
            kws.add(w)
    for canon, syns in _TYPE_SYNONYMS.items():
        if t == canon or t in syns or any(s in t for s in syns):
            kws.update([canon, *syns])
    return [k for k in kws if len(k) > 2]


def _match_machine_type(haystack: str, machine_rates: list):
    """Return the machine_rate whose type keywords appear in the asset text."""
    hay = (haystack or "").lower()
    best = None
    best_len = 0
    for mr in machine_rates:
        for kw in _type_keywords(mr.get("type", "")):
            if kw in hay and len(kw) > best_len:
                best, best_len = mr, len(kw)
    return best


def _extract_document_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            from pdfminer.high_level import extract_text
            import io as _io
            return extract_text(_io.BytesIO(data)) or ""
        if name.endswith(".xlsx") or name.endswith(".xls"):
            import io as _io
            from openpyxl import load_workbook
            wb = load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
            out = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        out.append(" | ".join(cells))
            return "\n".join(out)
        if name.endswith(".docx"):
            import io as _io
            from docx import Document
            doc = Document(_io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs if p.text]
            for tbl in doc.tables:
                for r in tbl.rows:
                    parts.append(" | ".join(cell.text for cell in r.cells))
            return "\n".join(parts)
        return data.decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not read that document ({exc}). Try a text-based PDF, Excel or Word file.")


def _render_pdf_images(data: bytes, max_pages: int = 30) -> list:
    """Render PDF pages to downscaled JPEG base64 strings for vision OCR."""
    import base64
    import io as _io
    import fitz
    from PIL import Image
    out = []
    doc = fitz.open(stream=data, filetype="pdf")
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=120)
        mode = "RGBA" if pix.n >= 4 else "RGB"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if mode == "RGBA":
            img = img.convert("RGB")
        if img.width > 1000:
            ratio = 1000 / img.width
            img = img.resize((1000, int(img.height * ratio)))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


@router.post("/extract-pricing-document")
async def extract_pricing_document(file: UploadFile = File(None), file_id: str = Query(None),
                                   user=Depends(require_crm_perm("quotes.maintenance"))):
    """Upload a tender/agreement and let Claude pull out the bespoke per-machine
    service prices and per-site travel costs. Suggestion only — nothing saved.

    Large files are uploaded via /files/upload first (bypasses the proxy body
    limit) and passed here by `file_id`; small files may be posted directly."""
    api_key = EMERGENT_LLM_KEY or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI is not configured")
    if file_id:
        fdoc = await db.files.find_one(
            {"id": file_id, "organization_id": user.get("organization_id")}, {"_id": 0})
        if not fdoc:
            raise HTTPException(404, "Uploaded file not found")
        from utils.database import get_object
        data, _ct = get_object(fdoc["storage_path"])
        filename = fdoc.get("original_filename") or "document.pdf"
    elif file is not None:
        data = await file.read()
        filename = file.filename
    else:
        raise HTTPException(400, "Provide a file or file_id")
    if not data:
        raise HTTPException(400, "Empty file")
    from utils.afs_doc_sections import page_images, read_document
    doc = read_document(filename, data)
    if not doc["sections"] and not doc["vision_batches"]:
        raise HTTPException(422, "No readable text found in that document.")
    system = (
        "You extract commercial pricing from maintenance/service tender agreements. "
        "Return STRICT JSON only. Never invent prices — only include what is written. "
        "Prices are numbers (no currency symbol)."
    )
    instruction = (
        "Extract, from this PART of a maintenance/service tender, THREE pricing schedules plus a short summary. "
        "1) SERVICE prices per machine TYPE. 2) REPAIR labour rates per machine TYPE (£ per hour) — if the "
        "tender gives a single flat repair rate for everything, return one entry with type 'All'. 3) TRAVEL cost per site/location. "
        'Return JSON exactly like: {"currency":"GBP",'
        '"machine_services":[{"type":"Treadmill","service_price":12.0}],'
        '"repairs":[{"type":"Treadmill","hourly_rate":25.0}],'
        '"travel":[{"location":"Barnstaple","price":60.0}],'
        '"summary":{"headline":"one-line description of the contract","term":"e.g. 3 years","ppm_visits":"e.g. 2 per year",'
        '"sla":"e.g. 48h response","key_points":["notable clause","min charge","etc"]}}. '
        "Use the machine type / location text EXACTLY as written in its row (keep codes and numbers; never shorten or generalise), "
        "and return one entry per priced row. "
        "Never invent values. If a section is absent in this part, use an empty array; if unknown, use an empty string."
    )
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    sem = asyncio.Semaphore(3)

    async def _ask(label: str, text: str = "", images: list | None = None) -> dict:
        async with sem:
            chat = LlmChat(api_key=api_key, session_id=f"afs-pricing-{uuid.uuid4()}",
                           system_message=system).with_model("anthropic", "claude-sonnet-4-6")
            msg = (UserMessage(text="These images are scanned pages of a maintenance agreement. Read the pricing pages. " + instruction,
                               file_contents=[ImageContent(image_base64=b) for b in images])
                   if images else UserMessage(text=instruction + f"\n\nDOCUMENT PART ({label}):\n" + text))
            try:
                raw = (await chat.send_message(msg) or "").strip()
            except Exception:  # noqa: BLE001
                return {"_label": label, "_failed": True}
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "", 1).strip()
        s, e = raw.find("{"), raw.rfind("}")
        try:
            import json as _json
            out = _json.loads(raw[s:e + 1]) if s != -1 and e != -1 else {}
        except Exception:  # noqa: BLE001
            out = {"_unparsed": True}
        return {**(out if isinstance(out, dict) else {}), "_label": label}

    jobs = [_ask(s["label"], s["text"]) for s in doc["sections"]]
    jobs += [_ask(f"scanned pages {b[0]}–{b[-1]}", images=page_images(data, b)) for b in doc["vision_batches"]]
    parts = list(await asyncio.gather(*jobs))
    short_notes = []
    if doc["kind"] in ("xlsx", "csv"):
        # Tabular sources: every row carrying a price cell must come back as an item. A short reply is
        # re-read in halves once; anything still missing is reported, never silently dropped.
        import re as _re
        priced = _re.compile(r"\|\s*£?\s*\d[\d,]*\.\d{1,2}\s*(?:\||$)")
        n_items = lambda p: sum(len(p.get(k) or []) for k in ("machine_services", "repairs", "travel"))  # noqa: E731
        for i, sec in enumerate(doc["sections"]):
            rows = [ln for ln in sec["text"].split("\n") if priced.search(ln)]
            if not rows or n_items(parts[i]) >= len(rows):
                continue
            lines = sec["text"].split("\n")
            half = len(lines) // 2
            a, b = await asyncio.gather(_ask(sec["label"] + " (a)", "\n".join(lines[:half])), _ask(sec["label"] + " (b)", "\n".join(lines[half:])))
            merged = {"_label": sec["label"], **{k: (a.get(k) or []) + (b.get(k) or []) for k in ("machine_services", "repairs", "travel")},
                      "summary": a.get("summary") or b.get("summary"), "currency": a.get("currency") or b.get("currency")}
            if n_items(merged) >= n_items(parts[i]):
                parts[i] = merged
            if n_items(parts[i]) < len(rows):
                short_notes.append(f"{sec['label']}: {len(rows)} priced row(s) but {n_items(parts[i])} item(s) extracted — check this part")
    failed = [p["_label"] for p in parts if p.get("_failed") or p.get("_unparsed")]
    if failed and len(failed) == len(parts):
        raise HTTPException(503, "AI is temporarily unavailable — please try again")

    def _merge(key: str, name_key: str, price_key: str) -> list:
        """Same item in several parts: identical price → one row; different prices → every value kept, flagged."""
        seen: dict = {}
        for p in parts:
            for m in (p.get(key) or []):
                if not isinstance(m, dict) or not str(m.get(name_key) or "").strip():
                    continue
                try:
                    price = round(float(m.get(price_key)), 2)
                except (TypeError, ValueError):
                    continue
                nm = str(m[name_key]).strip()
                row = seen.setdefault(nm.lower(), {name_key: nm, price_key: price, "sources": [], "values": []})
                row["sources"].append(p["_label"])
                if price not in row["values"]:
                    row["values"].append(price)
        out = []
        for row in seen.values():
            if len(row["values"]) > 1:
                row["needs_review"] = True
                row["review_reason"] = "Different prices found: " + ", ".join(f"{v:,.2f}" for v in row["values"])
            out.append(row)
        return out

    machine_services = _merge("machine_services", "type", "service_price")
    repairs = _merge("repairs", "type", "hourly_rate")
    travel = _merge("travel", "location", "price")
    if doc["kind"] in ("xlsx", "csv"):
        total_priced = sum(sum(1 for ln in sec["text"].split("\n") if priced.search(ln)) for sec in doc["sections"])
        total_items = len(machine_services) + len(repairs) + len(travel)
        if total_items < total_priced:
            short_notes.append(f"{total_priced} priced row(s) in the document but {total_items} distinct item(s) extracted — "
                               "some rows may share a name or be missing; check against the source")
    summaries = [p["summary"] for p in parts if isinstance(p.get("summary"), dict)]
    first = next((s for s in summaries if s.get("headline")), summaries[0] if summaries else {})
    points: list = []
    for s in summaries:
        points += [str(k)[:200] for k in (s.get("key_points") or []) if k and str(k)[:200] not in points]
    summary = {
        "headline": str(first.get("headline") or "")[:400],
        "term": str(next((s.get("term") for s in summaries if s.get("term")), "") or "")[:120],
        "ppm_visits": str(next((s.get("ppm_visits") for s in summaries if s.get("ppm_visits")), "") or "")[:120],
        "sla": str(next((s.get("sla") for s in summaries if s.get("sla")), "") or "")[:200],
        "key_points": points[:20],
    }
    cov = doc["coverage"]
    coverage = {**cov, "parts_total": len(parts), "parts_read": len(parts) - len(failed), "parts_failed": failed,
                "notes": (cov.get("notes") or []) + short_notes,
                "complete": not failed and not cov.get("unread") and not short_notes,
                "chars_read": sum(len(s["text"]) for s in doc["sections"])}
    return {
        "currency": next((p.get("currency") for p in parts if p.get("currency")), "GBP"),
        "machine_services": machine_services,
        "repairs": repairs,
        "travel": travel,
        "summary": summary,
        "source_filename": filename,
        "extracted_chars": coverage["chars_read"],
        "coverage": coverage,
    }


async def _archive_quote_version(existing: dict, user) -> int:
    """Snapshot the current quote doc into crm2_afs_quote_versions before it is
    overwritten/reverted, so edits keep a viewable, revertible history."""
    last = await db.crm2_afs_quote_versions.find_one(
        {"quote_id": existing["id"]}, {"_id": 0, "version": 1}, sort=[("version", -1)])
    ver = (int(last["version"]) + 1) if last else 1
    snap = {k: v for k, v in existing.items() if k != "_id"}
    await db.crm2_afs_quote_versions.insert_one({
        "id": _id(), "quote_id": existing["id"],
        "organization_id": existing.get("organization_id"),
        "version": ver, "snapshot": snap,
        "edited_by": (user.get("email") or user.get("id")) if isinstance(user, dict) else None,
        "created_at": _now(),
        "final_annual": (existing.get("summary") or {}).get("final_annual"),
        "quote_health": existing.get("quote_health"),
        "quote_number": existing.get("quote_number"),
    })
    return ver


class CustomQuoteIn(BaseModel):
    company_id: str
    site_ids: Optional[List[str]] = None
    machine_rates: List[dict] = []      # [{type, service_price}]
    travel_rates: List[dict] = []       # [{location, price}]  price = per-visit
    repair_rates: List[dict] = []       # [{type, hourly_rate}]
    estimated_repair_hours: float = 0.0
    term_years: int = 1
    quote_discount_pct: float = 0.0
    visits_per_year: int = 1            # PPM visits/year — travel is charged per visit
    vat_pct: float = 0.20              # 20% UK VAT by default (override per quote)
    excluded_asset_ids: Optional[List[str]] = None   # machines deliberately left off the quote
    overwrite_quote_id: Optional[str] = None          # edit an existing saved quote (keeps number)
    include_site_annexe: bool = False                 # append a per-site equipment appendix to the PDF
    save: bool = False


@router.post("/build-custom-quote")
async def build_custom_quote(body: CustomQuoteIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Apply a bespoke (tender) rate card to the customer's machine estate:
    each machine gets its type's service price; each selected site is charged its
    matched travel cost per visit × the number of PPM visits/year. Machines we
    can't match (and haven't been excluded) are returned in `needs_review` and the
    quote is held BLOCKED until every machine is either priced or excluded."""
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": body.company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    linked = await _resolve_linked_org_for_company(company, user)
    if not linked:
        raise HTTPException(400, "This company is not linked to an operations organisation — no estate to quote.")

    machine_rates = [m for m in body.machine_rates if m.get("type")]
    excluded = set(body.excluded_asset_ids or [])
    eq_query = {"organization_id": linked}
    if body.site_ids:
        eq_query["site_id"] = {"$in": body.site_ids}
    equipment = await db.equipment.find(
        eq_query, {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "equipment_type": 1,
                   "console_type": 1, "manufacturer": 1, "serial_number": 1, "site_id": 1}).to_list(None)

    groups = {}
    unmatched = {}          # model → grouped unmatched machines
    excluded_lines = []
    unpriced_asset_ids = []
    for e in equipment:
        aid = e.get("id")
        model_label = e.get("model") or e.get("name") or "Unknown"
        if aid in excluded:
            excluded_lines.append({"asset_id": aid, "model": model_label, "site_id": e.get("site_id")})
            continue
        hay = " ".join(str(e.get(k) or "") for k in ("equipment_type", "model", "name", "model_code", "console_type", "manufacturer"))
        mr = _match_machine_type(hay, machine_rates)
        if not mr:
            u = unmatched.setdefault(model_label, {"kind": "MACHINE", "model": model_label, "asset_ids": [], "count": 0})
            u["asset_ids"].append(aid)
            u["count"] += 1
            unpriced_asset_ids.append(aid)
            continue
        typ = mr["type"]
        price = round(float(mr.get("service_price") or 0), 2)
        # Keep model/annual_unit/annual_total keys so the shared PDF renderer itemises correctly.
        g = groups.setdefault(typ, {"type": typ, "model": typ, "unit_price": price,
                                    "annual_unit": price, "qty": 0, "serials": []})
        g["qty"] += 1
        if e.get("serial_number"):
            g["serials"].append(e["serial_number"])
    grouped = [dict(g, line_total=round(g["unit_price"] * g["qty"], 2),
                    annual_total=round(g["unit_price"] * g["qty"], 2)) for g in groups.values()]
    needs_review = [dict(u, detail=f"{u['count']} asset(s) — no matching machine type in the pricing.")
                    for u in unmatched.values()]

    # Travel per selected site: per-visit rate × number of visits/year.
    visits = max(1, int(body.visits_per_year or 1))
    sites = await db.sites.find(
        {"organization_id": linked, **({"id": {"$in": body.site_ids}} if body.site_ids else {})},
        {"_id": 0, "id": 1, "name": 1}).to_list(2000)
    travel_rates = [t for t in body.travel_rates if t.get("location")]
    travel_lines = []
    for s in sites:
        sname = (s.get("name") or "").lower()
        matched = None
        for tr in travel_rates:
            loc = (tr.get("location") or "").lower()
            if loc and (loc in sname or sname in loc):
                matched = tr
                break
        if matched:
            per_visit = round(float(matched.get("price") or 0), 2)
            annual = round(per_visit * visits, 2)
            travel_lines.append({"site_id": s["id"], "site_name": s.get("name"),
                                 "location": matched["location"], "per_visit": per_visit,
                                 "visits": visits, "annual": annual, "price": annual})
        else:
            needs_review.append({"kind": "TRAVEL", "site_id": s["id"], "site_name": s.get("name"),
                                 "detail": "No matching travel location in the uploaded pricing."})

    service_annual = round(sum(g["line_total"] for g in grouped), 2)
    travel_total = round(sum(t["annual"] for t in travel_lines), 2)
    # Indicative repair cost = estimated annual hours × effective repair rate.
    repair_rates = [r for r in body.repair_rates if r.get("hourly_rate") is not None]
    rates = [float(r.get("hourly_rate") or 0) for r in repair_rates if float(r.get("hourly_rate") or 0) > 0]
    effective_repair_rate = round(sum(rates) / len(rates), 2) if rates else 0.0
    est_hours = max(0.0, float(body.estimated_repair_hours or 0))
    repair_cost = round(est_hours * effective_repair_rate, 2)
    disc = max(0.0, float(body.quote_discount_pct or 0))
    disc_mult = (1 - disc / 100.0)
    final_annual = round((service_annual + travel_total + repair_cost) * disc_mult, 2)
    term_years = max(1, int(body.term_years or 1))
    term_total = round(final_annual * term_years, 2)
    vat_pct = float(body.vat_pct if body.vat_pct is not None else 0.20)
    vat_amount = round(final_annual * vat_pct, 2)
    summary = {
        "service_annual": service_annual, "travel_total": travel_total,
        "repair_cost": repair_cost, "effective_repair_rate": effective_repair_rate,
        "estimated_repair_hours": est_hours, "visits_per_year": visits,
        "quote_discount_pct": disc, "final_annual": final_annual,
        "term_years": term_years, "term_total": term_total,
        "vat_pct": vat_pct, "vat_amount": vat_amount,
        "final_annual_inc_vat": round(final_annual + vat_amount, 2),
        "monthly": round(final_annual / 12.0, 2),
    }
    unpriced_count = len(unpriced_asset_ids)
    quote_health = "BLOCKED" if unpriced_count else "READY"
    out = {
        "pricing_mode": "custom_tender",
        "grouped_lines": grouped, "travel_lines": travel_lines,
        "repair_rates": repair_rates,
        "needs_review": needs_review, "needs_review_count": len(needs_review),
        "excluded_lines": excluded_lines, "excluded_count": len(excluded_lines),
        "unpriced_asset_ids": unpriced_asset_ids, "unpriced_count": unpriced_count,
        "quote_health": quote_health,
        "include_site_annexe": bool(body.include_site_annexe),
        "assets_total": len(equipment), "assets_priced": sum(g["qty"] for g in grouped),
        "summary": summary,
    }
    if body.save:
        base = {
            "company_id": body.company_id, "company_name": company.get("name"),
            "linked_organization_id": linked, "site_ids": body.site_ids or [],
            "contract_type": "custom", "pricing_level": "custom_tender",
            "pricing_mode": "custom_tender", "source": "custom_tender_upload",
            "term_years": term_years, "quote_discount_pct": disc,
            "visits_per_year": visits, "vat_pct": vat_pct,
            "grouped_lines": grouped, "travel_lines": travel_lines,
            "needs_review": needs_review, "excluded_lines": excluded_lines,
            "excluded_asset_ids": list(excluded),
            "unpriced_asset_ids": unpriced_asset_ids, "unpriced_count": unpriced_count,
            "quote_health": quote_health, "summary": summary,
            "include_site_annexe": bool(body.include_site_annexe),
            "machine_rates": machine_rates, "travel_rates": travel_rates,
            "repair_rates": repair_rates, "estimated_repair_hours": est_hours,
            "updated_at": _now(),
        }
        if body.overwrite_quote_id:
            existing = await db.crm2_afs_quotes.find_one(
                {"id": body.overwrite_quote_id, **of}, {"_id": 0})
            if not existing:
                raise HTTPException(404, "Quote to edit not found")
            archived_ver = await _archive_quote_version(existing, user)
            base["version"] = archived_ver + 1
            await db.crm2_afs_quotes.update_one({"id": body.overwrite_quote_id, **of}, {"$set": base})
            qid = body.overwrite_quote_id
            out["saved_quote_id"] = qid
            out["quote_number"] = existing.get("quote_number")
            out["version"] = base["version"]
            await record_audit(entity_type="afs_quote", entity_id=qid, action="update",
                               user=user, extra={"company": company.get("name"), "mode": "custom_tender"})
        else:
            qid = _id()
            doc = {
                "id": qid, "organization_id": _org(user),
                "quote_number": f"AFS-{datetime.now(timezone.utc).strftime('%Y')}-{qid[:5].upper()}",
                "status": "draft", "created_by": user.get("email") or user.get("id"),
                "version": 1, "created_at": _now(), **base,
            }
            await db.crm2_afs_quotes.insert_one(doc)
            await record_audit(entity_type="afs_quote", entity_id=qid, action="create",
                               user=user, extra={"company": company.get("name"), "mode": "custom_tender"})
            out["saved_quote_id"] = qid
            out["quote_number"] = doc["quote_number"]
            out["version"] = 1
    return out


# ── Quote version history (view / revert) ──────────────────────────
@router.get("/quotes/{quote_id}/versions")
async def list_quote_versions(quote_id: str, user=Depends(get_crm_user)):
    """History list for a quote (metadata only), newest first. The live quote is
    the current version; each entry is a prior snapshot captured before an edit."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    versions = await db.crm2_afs_quote_versions.find(
        {"quote_id": quote_id}, {"_id": 0, "snapshot": 0}).sort("version", -1).to_list(200)
    return {
        "quote_id": quote_id, "quote_number": q.get("quote_number"),
        "current_version": int(q.get("version") or 1),
        "current": {
            "final_annual": (q.get("summary") or {}).get("final_annual"),
            "quote_health": q.get("quote_health"),
            "updated_at": q.get("updated_at") or q.get("created_at"),
        },
        "versions": versions,
    }


@router.get("/quotes/{quote_id}/versions/{version}")
async def get_quote_version(quote_id: str, version: int, user=Depends(get_crm_user)):
    """Full snapshot of a historical version (for read-only viewing)."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, {"_id": 0, "id": 1})
    if not q:
        raise HTTPException(404, "Quote not found")
    v = await db.crm2_afs_quote_versions.find_one(
        {"quote_id": quote_id, "version": version}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@router.post("/quotes/{quote_id}/versions/{version}/revert")
async def revert_quote_version(quote_id: str, version: int, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Restore a historical version as the current quote. The current state is
    archived first, so a revert is itself reversible. Quote number is preserved."""
    of = _of(user)
    current = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, {"_id": 0})
    if not current:
        raise HTTPException(404, "Quote not found")
    ver_doc = await db.crm2_afs_quote_versions.find_one(
        {"quote_id": quote_id, "version": version}, {"_id": 0})
    if not ver_doc:
        raise HTTPException(404, "Version not found")
    archived_ver = await _archive_quote_version(current, user)
    snap = ver_doc.get("snapshot") or {}
    restore_keys = [
        "grouped_lines", "travel_lines", "needs_review", "excluded_lines", "excluded_asset_ids",
        "unpriced_asset_ids", "unpriced_count", "quote_health", "summary", "include_site_annexe",
        "machine_rates", "travel_rates", "repair_rates", "estimated_repair_hours",
        "term_years", "quote_discount_pct", "visits_per_year", "vat_pct", "site_ids",
        "company_id", "company_name", "linked_organization_id",
        "contract_type", "pricing_level", "pricing_mode", "source",
    ]
    setdoc = {k: snap.get(k) for k in restore_keys if k in snap}
    setdoc["version"] = archived_ver + 1
    setdoc["updated_at"] = _now()
    setdoc["reverted_from_version"] = version
    await db.crm2_afs_quotes.update_one({"id": quote_id, **of}, {"$set": setdoc})
    await record_audit(entity_type="afs_quote", entity_id=quote_id, action="revert",
                       user=user, extra={"to_version": version})
    updated = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    return {"ok": True, "quote": updated, "current_version": setdoc["version"]}


# ── Reusable customer rate cards (saved tenders) ───────────────────
class RateCardIn(BaseModel):
    company_id: str
    name: Optional[str] = None
    machine_rates: List[dict] = []
    travel_rates: List[dict] = []
    repair_rates: List[dict] = []
    currency: str = "GBP"
    source_filename: Optional[str] = None


@router.post("/rate-cards")
async def save_rate_card(body: RateCardIn, user=Depends(require_crm_perm("pricing.manage"))):
    """Persist an extracted/edited tender as a reusable rate card on the customer."""
    of = _of(user)
    company = await db.crm2_companies.find_one({"id": body.company_id, **of}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    machine_rates = [{"type": str(m.get("type")).strip(), "service_price": round(float(m.get("service_price") or 0), 2)}
                     for m in body.machine_rates if m.get("type")]
    travel_rates = [{"location": str(t.get("location")).strip(), "price": round(float(t.get("price") or 0), 2)}
                    for t in body.travel_rates if t.get("location")]
    repair_rates = [{"type": str(r.get("type")).strip(), "hourly_rate": round(float(r.get("hourly_rate") or 0), 2)}
                    for r in body.repair_rates if r.get("type")]
    rid = _id()
    label = (body.name or "").strip() or (body.source_filename or f"Rate card {datetime.now(timezone.utc).strftime('%d %b %Y')}")
    doc = {
        "id": rid, "organization_id": _org(user), "company_id": body.company_id,
        "company_name": company.get("name"), "name": label, "currency": body.currency or "GBP",
        "machine_rates": machine_rates, "travel_rates": travel_rates, "repair_rates": repair_rates,
        "source_filename": body.source_filename,
        "created_by": user.get("email") or user.get("id"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_afs_rate_cards.insert_one(doc)
    doc.pop("_id", None)
    try:
        await record_audit(entity_type="afs_rate_card", entity_id=rid, action="create",
                           user=user, extra={"company": company.get("name"), "name": label})
    except Exception:  # noqa: BLE001
        pass
    return doc


@router.get("/rate-cards")
async def list_rate_cards(company_id: str, user=Depends(get_crm_user)):
    of = _of(user)
    cards = await db.crm2_afs_rate_cards.find(
        {"company_id": company_id, **of}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"rate_cards": cards}


@router.delete("/rate-cards/{card_id}")
async def delete_rate_card(card_id: str, user=Depends(require_crm_perm("pricing.manage"))):
    of = _of(user)
    r = await db.crm2_afs_rate_cards.delete_one({"id": card_id, **of})
    if not r.deleted_count:
        raise HTTPException(404, "Rate card not found")
    return {"ok": True}



@router.get("/quotes")
async def list_afs_quotes(status: str = "", user=Depends(get_crm_user)):
    of = _of(user)
    query = dict(of)
    if status:
        query["status"] = status
    rows = await db.crm2_afs_quotes.find(
        query, {"_id": 0, "asset_register": 0}).sort("created_at", -1).to_list(200)
    return {"quotes": rows, "total": len(rows)}


@router.get("/quotes/{quote_id}")
async def get_afs_quote(quote_id: str, user=Depends(get_crm_user)):
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **_of(user)}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    return q


@router.get("/quotes/{quote_id}/pdf")
async def afs_quote_pdf(quote_id: str, user=Depends(get_crm_user)):
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **_of(user)}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    from utils.afs_quote_pdf import render_afs_quote_pdf
    pdf = await render_afs_quote_pdf(q, organization_id=_org(user))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{q.get("quote_number", "quote")}.pdf"'})


class PortalLinkIn(BaseModel):
    valid_days: int = 30
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None


@router.post("/quotes/{quote_id}/portal-link")
async def afs_quote_portal_link(quote_id: str, body: PortalLinkIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Mint (or reuse) a no-login customer acceptance link for an aftersales quote.
    Commercial customers only — MOD keeps its existing SOR portal flow."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    if int(q.get("unpriced_count") or 0) > 0:
        raise HTTPException(400, f"This quote still has {q['unpriced_count']} machine(s) that aren't priced or excluded. Resolve them in Build Quote before sharing it.")
    if q.get("status") in ("accepted", "agreement", "declined"):
        # already progressed — still return the existing link if present
        shortcode = q.get("public_shortcode")
    else:
        shortcode = q.get("public_shortcode")
    if not shortcode:
        shortcode = secrets.token_urlsafe(8)[:10]
    valid_until = (datetime.now(timezone.utc) + timedelta(days=max(1, body.valid_days))).isoformat()
    patch = {
        "public_shortcode": shortcode, "valid_until": valid_until,
        "portal_contact_name": (body.contact_name or "").strip(),
        "portal_contact_email": (body.contact_email or "").strip(),
        "updated_at": _now(),
    }
    # Only advance a fresh draft to "sent"; never regress an accepted/agreement quote.
    if q.get("status") in (None, "draft"):
        patch["status"] = "sent"
        patch["sent_at"] = _now()
    await db.crm2_afs_quotes.update_one({"id": quote_id, **of}, {"$set": patch})
    await record_audit(entity_type="afs_quote", entity_id=quote_id, action="portal_link", user=user,
                       extra={"shortcode": shortcode})
    frontend = os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    return {"shortcode": shortcode, "url": f"{frontend}/aq/{shortcode}", "valid_until": valid_until,
            "status": patch.get("status", q.get("status"))}


class SendQuoteEmailIn(BaseModel):
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    valid_days: int = 30
    attach_pdf: bool = True


@router.post("/quotes/{quote_id}/send-email")
async def send_afs_quote_email(quote_id: str, body: SendQuoteEmailIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Email the customer their acceptance link (with the branded PDF attached).
    Commercial only. Mints a portal link if one doesn't exist yet."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    if int(q.get("unpriced_count") or 0) > 0:
        raise HTTPException(400, f"This quote still has {q['unpriced_count']} machine(s) that aren't priced or excluded. Resolve them in Build Quote before emailing it.")
    email = (body.contact_email or q.get("portal_contact_email") or "").strip()
    if "@" not in email:
        raise HTTPException(400, "A customer email address is required to send this quote.")
    contact_name = (body.contact_name or q.get("portal_contact_name") or "").strip()
    shortcode = q.get("public_shortcode") or secrets.token_urlsafe(8)[:10]
    valid_until = (datetime.now(timezone.utc) + timedelta(days=max(1, body.valid_days))).isoformat()
    patch = {"public_shortcode": shortcode, "valid_until": valid_until,
             "portal_contact_email": email, "portal_contact_name": contact_name,
             "emailed_at": _now(), "updated_at": _now()}
    if q.get("status") in (None, "draft"):
        patch["status"] = "sent"
        patch["sent_at"] = _now()
    await db.crm2_afs_quotes.update_one({"id": quote_id, **of}, {"$set": patch})

    frontend = os.environ.get("FRONTEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or ""
    link = f"{frontend}/aq/{shortcode}"
    summary = q.get("summary", {}) or {}
    tier = (q.get("contract_type") or "gold").title()
    greeting = f"Hi {contact_name.split()[0]}," if contact_name else "Hello,"
    html = (
        f"<p>{greeting}</p>"
        f"<p>Please find your Pulse Fitness <strong>{tier} maintenance quotation</strong> "
        f"(<strong>{q.get('quote_number')}</strong>) attached as a PDF.</p>"
        f"<p style='font-size:15px'>Annual value: <strong>£{float(summary.get('final_annual') or 0):,.2f}</strong> "
        f"(£{float(summary.get('final_annual_inc_vat') or 0):,.2f} inc VAT).</p>"
        f"<p>You can review the full quote and <strong>accept or decline online</strong> here:</p>"
        f"<p style='margin:22px 0'><a href='{link}' "
        f"style='background:#0073A4;color:#fff;text-decoration:none;padding:12px 22px;"
        f"border-radius:10px;font-weight:700;display:inline-block'>Review &amp; respond to your quote</a></p>"
        f"<p style='color:#6E7476;font-size:12px'>If the button doesn't work, paste this link into your browser:<br>{link}</p>")
    attachments = None
    if body.attach_pdf:
        try:
            from utils.afs_quote_pdf import render_afs_quote_pdf
            import base64
            pdf = await render_afs_quote_pdf(q, organization_id=_org(user))
            attachments = [{"filename": f"{q.get('quote_number', 'quote')}.pdf",
                            "content": base64.b64encode(pdf).decode("ascii")}]
        except Exception:
            import logging
            logging.getLogger(__name__).warning("AFS quote PDF render failed for %s; sending without attachment", quote_id, exc_info=True)
            attachments = None

    from utils.email import send_email
    sent = await send_email(email, f"Your Pulse Fitness maintenance quote — {q.get('quote_number')}",
                            html, attachments=attachments, organization_id=_org(user),
                            category="service", kind="afs_quote")
    await record_audit(entity_type="afs_quote", entity_id=quote_id, action="send_email", user=user,
                       extra={"to": email, "sent": bool(sent)})
    return {"sent": bool(sent), "to": email, "shortcode": shortcode, "url": link}


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3 — AGREEMENT BUILDER + ACTIVATION ENGINE
# Accepted quote → Schedules 1-6 → Agreement Health → Generate → Sign →
# Activate (crm2_contracts + asset cover + service schedule + billing + Sicon/Sage)
# ══════════════════════════════════════════════════════════════════════════

# Controlled legal/contract content (approved wording — versioned templates).
SCHEDULE5_OBLIGATIONS = [
    "Use the equipment only for its intended purpose and in accordance with the manufacturer's instructions.",
    "Carry out and record daily visual inspections of all equipment before use.",
    "Carry out the customer-level preventative maintenance tasks specified for CV and resistance equipment.",
    "Keep CV equipment clean and free from debris; ensure running surfaces are kept clean and dry.",
    "Ensure resistance equipment cables, belts and upholstery are checked for wear and reported promptly.",
    "Maintain accurate maintenance records and make them available to Pulse Fitness on request.",
    "Ensure only trained staff operate and supervise the equipment.",
    "Report all faults promptly via the agreed reporting channels.",
]
SCHEDULE6_EXCEPTIONS = [
    "Consumable items (unless expressly included in the selected package).",
    "Damage caused by misuse, neglect, vandalism or failure to meet customer obligations.",
    "Cosmetic and aesthetic parts beyond the stated allowance.",
    "Works required due to environmental conditions outside agreed operating parameters.",
    "Carriage & insurance where stated as chargeable in the selected package (subject to wording governance).",
]
TC_VERSION = "T&C-2026.1"
TEMPLATE_VERSION = "AGREEMENT-TEMPLATE-2026.1"


def _supplier_block(settings):
    s = settings.get("supplier") or {}
    return {
        "name": s.get("name", "Pulse Fitness Limited"),
        "address": s.get("address", "Radnor Park, Greenfield Road, Congleton, Cheshire, CW12 4TW"),
        "company_number": s.get("company_number", ""),
        "vat_number": s.get("vat_number", ""),
    }


def _service_contacts(settings):
    s = settings.get("service_contacts") or {}
    return {
        "service_email": s.get("service_email", "Service.Dept@pulsefitness.com"),
        "service_phone": s.get("service_phone", "01260 294600 option 2"),
        "portal_url": s.get("portal_url", "https://service.pulsefitness.com/SelfService/SignIn"),
        "parts_email": s.get("parts_email", "parts@pulsefitness.com"),
        "office_hours": s.get("office_hours", "Mon–Thu 08:00–17:00, Fri 08:00–15:30"),
    }


def _billing_schedule(annual, frequency, start_date, term_years, end_date=None):
    """Calendar-aware billing schedule; [] when the start date is missing."""
    from utils.cm_dates import billing_schedule
    return billing_schedule(annual, frequency, start_date, end_date, term_years)


def _service_schedule(start_date, visits_per_year, term_years, end_date=None):
    """Calendar-aware contractual PPM obligations; [] when the start is missing."""
    from utils.cm_dates import service_schedule
    return service_schedule(start_date, visits_per_year, end_date, term_years)


async def _build_agreement_doc(org_id, quote):
    of = {"organization_id": org_id}
    settings = await db.crm2_afs_settings.find_one(of) or {}
    company = await db.crm2_companies.find_one({"id": quote["company_id"], **of}, {"_id": 0}) or {}
    linked = quote.get("linked_organization_id") or company.get("linked_organization_id") or ""
    linked_org = await db.organizations.find_one({"id": linked}, {"_id": 0}) if linked else None
    sites = await db.sites.find(
        {"organization_id": linked, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "city": 1, "postcode": 1, "address": 1}).to_list(500) if linked else []
    if quote.get("site_ids"):
        sites = [s for s in sites if s["id"] in quote["site_ids"]] or sites

    pkg = await db.crm2_afs_packages.find_one({**of, "key": (quote.get("contract_type") or "gold").lower()}, _PUBLIC) or {}
    summary = quote.get("summary", {})
    grouped = quote.get("grouped_lines", [])
    register = quote.get("asset_register", [])

    legal_name = company.get("legal_name") or (linked_org or {}).get("name") or company.get("name")
    cust_address = company.get("registered_address") or company.get("address") or (linked_org or {}).get("address") or ""

    annual = summary.get("final_annual", 0)
    schedules = {
        "schedule1_parties": {
            "supplier": _supplier_block(settings),
            "customer": {"legal_name": legal_name, "trading_name": company.get("name"),
                         "billing_address": company.get("billing_address") or cust_address,
                         "address": cust_address},
            "sites": [{"name": s["name"], "address": s.get("address") or "",
                       "city": s.get("city") or "", "postcode": s.get("postcode") or ""} for s in sites],
        },
        "schedule2_agreement": {
            "agreement_type": f"{pkg.get('name', quote.get('contract_type', '').title())} Maintenance Agreement",
            "package": quote.get("contract_type"),
            "start_date": None, "end_date": None,
            "term_years": summary.get("term_years", 1),
            "services_included": pkg.get("maintenance", []),
            "whats_covered": pkg.get("maintenance", []) + pkg.get("technical_support", []),
            "exclusions": pkg.get("exclusions", []),
            "payment_options": {
                "monthly": round(annual / 12.0, 2),
                "annual": round(annual, 2),
                "lump_sum": round(annual * max(1, summary.get("term_years", 1)), 2),
            },
            "annual_value": annual, "vat_pct": summary.get("vat_pct"),
        },
        "schedule3_equipment": [
            {"machine": g["model"], "description": g.get("description", ""), "quantity": g["qty"],
             "serial_numbers": [s for s in g.get("serials", []) if s],
             "serials_expected": g["qty"], "serials_assigned": len([s for s in g.get("serials", []) if s]),
             "annual_total": g.get("annual_total", 0)}
            for g in grouped
        ],
        "schedule4_fault_reporting": _service_contacts(settings),
        "schedule5_customer_obligations": SCHEDULE5_OBLIGATIONS,
        "schedule6_exceptions": SCHEDULE6_EXCEPTIONS,
    }
    return {
        "company_id": quote["company_id"], "company_name": company.get("name"),
        "linked_organization_id": linked,
        "quote_id": quote["id"], "quote_number": quote.get("quote_number"),
        "contract_type": quote.get("contract_type"), "pricing_level": quote.get("pricing_level"),
        "term_years": summary.get("term_years", 1),
        "annual_value": annual, "vat_pct": summary.get("vat_pct"),
        "pricing_version": quote.get("pricing_version"),
        "package_version": pkg.get("version"), "tc_version": TC_VERSION, "template_version": TEMPLATE_VERSION,
        "schedules": schedules, "asset_register": register,
        "billing_frequency": "annual", "payment_method": None,
        "wording_conflicts": pkg.get("wording_conflicts", []),
    }


def _agreement_health(ag):
    """AGREEMENT HEALTH — plain-English readiness checks (§58)."""
    reasons = []
    s = ag.get("schedules", {})
    if not s.get("schedule1_parties", {}).get("customer", {}).get("legal_name"):
        reasons.append("Customer legal entity is missing")
    if not (s.get("schedule1_parties", {}).get("sites")):
        reasons.append("No sites on the agreement")
    if not ag.get("start_date") or not ag.get("end_date"):
        reasons.append("Start / end dates not set")
    if not ag.get("payment_method"):
        reasons.append("Payment method not selected")
    if ag.get("payment_method") == "monthly" and not ag.get("direct_debit_received"):
        reasons.append("Direct Debit mandate required for monthly payments")
    # serial validation
    incomplete = [row for row in s.get("schedule3_equipment", []) if row["serials_assigned"] < row["serials_expected"]
                  and not (ag.get("serial_exceptions") or {}).get(row["machine"])]
    if incomplete:
        reasons.append(f"{len(incomplete)} equipment line(s) have incomplete serial numbers")
    if not s.get("schedule3_equipment"):
        reasons.append("No equipment on the agreement")
    # unresolved wording conflicts on the selected package
    unresolved = [w for w in (ag.get("wording_conflicts") or []) if w.get("status") != "resolved"]
    if unresolved:
        reasons.append(f"{len(unresolved)} package wording conflict(s) require management approval")
    if (ag.get("annual_value") or 0) <= 0:
        reasons.append("Final contract value is zero")
    return {"ready": len(reasons) == 0, "reasons": reasons}


class AcceptQuoteIn(BaseModel):
    accepted_by: Optional[str] = None
    start_date: Optional[str] = None
    payment_method: Optional[str] = None
    prepare_agreement: bool = True


@router.post("/quotes/{quote_id}/accept")
async def accept_quote(quote_id: str, body: AcceptQuoteIn, user=Depends(require_crm_perm("agreements.process"))):
    """Record acceptance and pre-fill a draft agreement (one per quote)."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.get("status") in ("declined",) or q.get("portal_status") == "declined":
        raise HTTPException(400, "This quote was declined — prepare a fresh quote.")
    if (q.get("unpriced_count") or 0) > 0:
        raise HTTPException(400, "Resolve unpriced machines before recording acceptance.")
    if q.get("status") != "agreement":
        await db.crm2_afs_quotes.update_one({"id": quote_id, **of}, {"$set": {
            "status": "accepted", "accepted_at": q.get("accepted_at") or _now(),
            "accepted_by": body.accepted_by or q.get("accepted_by") or user.get("email"), "updated_at": _now()}})
        await record_audit(entity_type="afs_quote", entity_id=quote_id, action="accept", user=user)
    if not body.prepare_agreement:
        return {"status": "accepted", "quote_id": quote_id}
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    ag = await _insert_agreement_from_quote(
        _org(user), q, user.get("email") or user.get("id"), start_date=body.start_date,
        payment_method=body.payment_method,
        timeline_note=f"Agreement pre-filled from accepted quote {q.get('quote_number') or quote_id}")
    return {"status": "accepted", "quote_id": quote_id, "agreement_id": ag["id"],
            "agreement_number": ag.get("agreement_number"), "health": _agreement_health(ag)}


class PrepareAgreementIn(BaseModel):
    start_date: str
    payment_method: str = "annual"          # monthly | annual | lump_sum
    billing_frequency: Optional[str] = None
    visits_per_year: int = 2


async def _insert_agreement_from_quote(org_id, quote, actor, *, start_date=None,
                                       payment_method=None, billing_frequency=None,
                                       visits_per_year=None, timeline_note=None):
    """Shared: build + insert a DRAFT agreement from a saved quote. Idempotent —
    returns any existing non-cancelled agreement for the same quote. Used by the
    coordinator (prepare) and by public portal acceptance (auto-prep)."""
    of = {"organization_id": org_id}
    existing = await db.crm2_afs_agreements.find_one(
        {**of, "quote_id": quote["id"], "status": {"$nin": ["cancelled", "superseded"]}}, _PUBLIC)
    if existing:
        return existing
    doc = await _build_agreement_doc(org_id, quote)
    _apply_dates(doc, start_date or quote.get("requested_start_date"))
    doc["payment_method"] = payment_method or quote.get("preferred_payment") or "annual"
    doc["billing_frequency"] = billing_frequency or doc["payment_method"]
    doc["visits_per_year"] = int(visits_per_year or quote.get("visits_per_year") or 2)
    doc["source_sales_quote_id"] = quote.get("source_sales_quote_id")
    aid = _id()
    doc.update({
        "id": aid, "organization_id": org_id,
        "agreement_number": f"PF-MA-{aid[:6].upper()}",
        "status": "draft", "serial_exceptions": {},
        "created_by": actor,
        "created_at": _now(), "updated_at": _now(),
        "timeline": [{"at": _now(),
                      "event": timeline_note or ("Agreement prepared from quote " + (quote.get("quote_number") or quote["id"])),
                      "by": actor}],
    })
    doc["health"] = _agreement_health(doc)
    await db.crm2_afs_agreements.insert_one(doc)
    await db.crm2_afs_quotes.update_one({"id": quote["id"], **of}, {"$set": {
        "status": "agreement", "agreement_id": aid, "updated_at": _now()}})
    await _agreement_step_action(org_id, doc)
    return await db.crm2_afs_agreements.find_one({"id": aid, **of}, _PUBLIC)


def _apply_dates(doc: dict, start_date) -> None:
    from utils.cm_dates import parse_date, term_end
    sd = parse_date(start_date)
    if not sd:
        return
    doc["start_date"] = sd.isoformat()
    doc["end_date"] = term_end(sd, doc.get("term_years") or 1).isoformat()
    s2 = doc.setdefault("schedules", {}).setdefault("schedule2_agreement", {})
    s2["start_date"], s2["end_date"] = doc["start_date"], doc["end_date"]


_AG_STEPS = {
    "draft": ("complete", "Complete agreement", "fill the missing details and generate the agreement"),
    "ready": ("send", "Send for signature", "send the agreement to the customer for electronic signature"),
    "sent": ("sign", "Awaiting customer signature", "the customer has been sent the agreement to sign"),
    "viewed": ("sign", "Awaiting customer signature", "the customer has opened the agreement but not signed yet"),
    "signed": ("activate", "Activate contract", "activate the contract to create the service plan and billing"),
    "declined": ("declined", "Customer declined agreement", "review the customer's reason and agree next steps"),
}
_AG_STEP_KEYS = {"complete", "send", "sign", "email-failed", "activate", "declined"}


async def _agreement_step_action(org_id: str, ag: dict) -> None:
    """Exactly one Action Centre item per agreement — the current stage only.
    Conflict / missing-information reviews (raised by activation) take precedence."""
    from utils.cm_actions import raise_action, resolve_action
    cur = _AG_STEPS.get(ag.get("status"))
    req = ag.get("signature_request") or {}
    if cur and cur[0] == "sign" and req.get("delivery_status") == "failed":
        cur = ("email-failed", "Signature email not delivered",
               f"the email to {req.get('email')} was not accepted — check the address, copy the link or resend")
    for key in _AG_STEP_KEYS - ({cur[0]} if cur else set()):
        await resolve_action(org_id, f"cm:agreement-{key}:{ag['id']}", "Agreement moved to the next stage.")
    if not cur:
        return
    reasons = (ag.get("health") or {}).get("reasons") or []
    tail = f" Outstanding: {'; '.join(reasons[:4])}." if cur[0] == "complete" and reasons else ""
    if cur[0] == "declined" and ag.get("declined_reason"):
        tail = f" Reason: {ag['declined_reason']}"
    await raise_action(org_id, f"cm:agreement-{cur[0]}:{ag['id']}", type_="agreement_step",
                       subject=f"{cur[1]}: {ag.get('agreement_number')}",
                       body=f"{ag.get('company_name')} — {cur[2]}.{tail}",
                       contract={"id": ag["id"], "company_id": ag.get("company_id"),
                                 "contract_number": ag.get("agreement_number")},
                       extra={"agreement_id": ag["id"], "quote_id": ag.get("quote_id")})


@router.post("/agreements/from-quote/{quote_id}")
async def prepare_agreement(quote_id: str, body: PrepareAgreementIn, user=Depends(require_crm_perm("agreements.process"))):
    of = _of(user)
    quote = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not quote:
        raise HTTPException(404, "Maintenance quote not found")
    existing = await db.crm2_afs_agreements.find_one(
        {**of, "quote_id": quote_id, "status": {"$nin": ["cancelled", "superseded"]}}, _PUBLIC)
    if existing:
        if existing.get("status") == "draft" and not existing.get("start_date"):
            # Auto-prepared on acceptance without a start date — complete it with the coordinator's details.
            return await patch_agreement(existing["id"], AgreementPatchIn(
                start_date=body.start_date, visits_per_year=body.visits_per_year,
                payment_method=body.payment_method), user)
        return existing
    if quote.get("status") != "accepted":
        raise HTTPException(400, "Only an accepted maintenance quotation can proceed to an agreement.")
    try:
        datetime.strptime(body.start_date[:10], "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "start_date must be YYYY-MM-DD")
    ag = await _insert_agreement_from_quote(
        _org(user), quote, user.get("email") or user.get("id"),
        start_date=body.start_date, payment_method=body.payment_method,
        billing_frequency=body.billing_frequency, visits_per_year=body.visits_per_year)
    await record_audit(entity_type="afs_agreement", entity_id=ag["id"], action="create", user=user,
                       extra={"quote": quote.get("quote_number")})
    return ag


@router.get("/agreements")
async def list_agreements(status: str = "", user=Depends(get_crm_user)):
    of = _of(user)
    query = dict(of)
    if status:
        query["status"] = status
    rows = await db.crm2_afs_agreements.find(
        query, {"_id": 0, "asset_register": 0}).sort("created_at", -1).to_list(200)
    return {"agreements": rows, "total": len(rows)}


@router.get("/agreements/{agreement_id}")
async def get_agreement(agreement_id: str, user=Depends(get_crm_user)):
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **_of(user)}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    ag["health"] = _agreement_health(ag)
    return ag


class AgreementPatchIn(BaseModel):
    payment_method: Optional[str] = None
    direct_debit_received: Optional[bool] = None
    serial_exceptions: Optional[dict] = None   # {machine: "TO_CONFIRM_ON_FIRST_SERVICE"|"NOT_APPLICABLE"}
    resolve_wording: Optional[bool] = None
    start_date: Optional[str] = None
    visits_per_year: Optional[int] = None
    service_dates: Optional[List[str]] = None   # agreed contract-specific PPM dates (override the calendar)


@router.patch("/agreements/{agreement_id}")
async def patch_agreement(agreement_id: str, body: AgreementPatchIn, user=Depends(require_crm_perm("agreements.process"))):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    patch = {}
    content_change = any(v is not None for v in (body.payment_method, body.serial_exceptions, body.resolve_wording,
                                                  body.start_date, body.visits_per_year, body.service_dates))
    if content_change and ag.get("status") not in ("draft", "ready"):
        raise HTTPException(400, "This agreement has been issued for signature — its content can no longer change. "
                                 "Revoke the link first if a correction is needed.")
    if content_change and ag.get("status") == "ready":
        patch.update({"status": "draft", "document": None})
    if body.start_date is not None or body.visits_per_year is not None:
        if ag.get("status") not in ("draft", "ready"):
            raise HTTPException(400, "Dates and visits can only change before the agreement is issued.")
    if body.start_date is not None:
        from utils.cm_dates import parse_date
        if not parse_date(body.start_date):
            raise HTTPException(400, "start_date must be YYYY-MM-DD")
        tmp = {"term_years": ag.get("term_years"), "schedules": dict(ag.get("schedules") or {})}
        tmp["schedules"]["schedule2_agreement"] = dict(tmp["schedules"].get("schedule2_agreement") or {})
        _apply_dates(tmp, body.start_date)
        patch.update({"start_date": tmp["start_date"], "end_date": tmp["end_date"],
                      "schedules": tmp["schedules"]})
    if body.visits_per_year is not None:
        if not 1 <= body.visits_per_year <= 12:
            raise HTTPException(400, "Visits per year must be between 1 and 12")
        patch["visits_per_year"] = body.visits_per_year
    if body.service_dates is not None:
        from utils.cm_dates import parse_date
        start = parse_date(patch.get("start_date") or ag.get("start_date"))
        end = parse_date(patch.get("end_date") or ag.get("end_date"))
        bad = [d for d in body.service_dates if not parse_date(d) or (start and parse_date(d) < start)
               or (end and parse_date(d) > end)]
        if bad:
            raise HTTPException(400, f"Service dates must be YYYY-MM-DD within the contract term: {', '.join(bad)}")
        patch["service_dates"] = sorted(set(body.service_dates))
    if body.payment_method is not None:
        patch["payment_method"] = body.payment_method
        patch["billing_frequency"] = body.payment_method
    if body.direct_debit_received is not None:
        patch["direct_debit_received"] = body.direct_debit_received
    if body.serial_exceptions is not None:
        patch["serial_exceptions"] = {**(ag.get("serial_exceptions") or {}), **body.serial_exceptions}
    if body.resolve_wording:
        wc = [{**w, "status": "resolved"} for w in (ag.get("wording_conflicts") or [])]
        patch["wording_conflicts"] = wc
    patch["updated_at"] = _now()
    merged = {**ag, **patch}
    patch["health"] = _agreement_health(merged)
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": patch})
    out = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    await _agreement_step_action(_org(user), out)
    return out


@router.post("/agreements/{agreement_id}/generate")
async def generate_agreement(agreement_id: str, user=Depends(require_crm_perm("agreements.process"))):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    health = _agreement_health(ag)
    if not health["ready"]:
        raise HTTPException(400, {"message": "Agreement not ready", "reasons": health["reasons"]})
    tl = ag.get("timeline", []) + [{"at": _now(), "event": "Maintenance Agreement generated", "by": user.get("email")}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "status": "ready", "generated_at": _now(), "timeline": tl, "updated_at": _now()}})
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="generate", user=user)
    await _agreement_step_action(_org(user), {**ag, "status": "ready"})
    return {"status": "ready", "generated_at": _now(), "agreement_number": ag.get("agreement_number")}


class SignIn(BaseModel):
    signatory_name: str
    position: str
    email: str
    authority_confirmed: bool = False
    signature: Optional[str] = None          # typed name / data-url


@router.post("/agreements/{agreement_id}/sign")
async def sign_agreement(agreement_id: str, body: SignIn, user=Depends(require_crm_perm("agreements.process"))):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    if ag.get("status") not in ("ready", "sent", "viewed"):
        raise HTTPException(400, "Agreement must be generated (Ready) before signing")
    if not body.authority_confirmed:
        raise HTTPException(400, "Signatory must confirm they have authority to sign")
    sig = {
        "signatory_name": body.signatory_name, "position": body.position, "email": body.email,
        "signature": body.signature or body.signatory_name, "authority_confirmed": True,
        "signed_at": _now(), "tc_version": ag.get("tc_version"),
        "template_version": ag.get("template_version"),
        "method": "staff_recorded", "recorded_by": user.get("email"),
    }
    who = f"{body.signatory_name} ({body.position})" if body.position.strip() else body.signatory_name
    tl = ag.get("timeline", []) + [{"at": _now(), "event": f"Signed by {who}", "by": body.email}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "status": "signed", "signature": sig, "signed_at": _now(), "timeline": tl, "updated_at": _now(),
        **({"signature_request.revoked": True} if ag.get("signature_request") else {})}})
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="sign", user=user,
                       extra={"signatory": body.signatory_name})
    await _agreement_step_action(_org(user), {**ag, "status": "signed"})
    return {"status": "signed", "signature": sig}


class ActivateIn(BaseModel):
    conflict_review_note: Optional[str] = None   # authorised override of a genuine conflict


def _merge_invoices(existing: list, planned: list) -> list:
    """Posted / invoiced / paid rows (and their Sage refs) are never replaced."""
    kept = [i for i in (existing or []) if (i.get("status") or "scheduled") != "scheduled" or i.get("sage_invoice_ref")]
    dates = {i.get("due_date") for i in kept}
    return sorted(kept + [i for i in planned if i["due_date"] not in dates], key=lambda r: r.get("due_date") or "")


async def _activation_conflicts(of: dict, ag: dict, cid: Optional[str]) -> list:
    out = []
    start = ag.get("start_date") or ""
    async for d in db.crm2_contracts.find(
            {**of, "company_id": ag["company_id"], "status": {"$in": ["active", "signed"]},
             "source_agreement_id": {"$ne": ag["id"]}, "end_date": {"$gte": start}},
            {"_id": 0, "id": 1, "contract_number": 1, "end_date": 1}):
        if d["id"] != cid:
            out.append({"type": "overlapping_contract", "contract_id": d["id"],
                        "detail": f"{d.get('contract_number')} is active until {d.get('end_date')}"})
    linked = ag.get("linked_organization_id")
    ids = [x["id"] for x in (ag.get("asset_register") or []) if x.get("annual", 0) > 0 and x.get("id")]
    if linked and ids:
        async for e in db.equipment.find({"organization_id": linked, "id": {"$in": ids},
                                          "contract_cover.contract_id": {"$nin": [None, cid or "__none__"]}},
                                         {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "contract_cover": 1}):
            cov = e.get("contract_cover") or {}
            if (cov.get("end") or "9999") >= start:
                out.append({"type": "equipment_already_covered", "equipment_id": e["id"],
                            "detail": f"{e.get('name')} ({e.get('serial_number') or 'no serial'}) is covered by {cov.get('contract_number')}"})
        async for e in db.equipment.find({"organization_id": linked, "id": {"$in": ids},
                                          "lifecycle_stage": {"$in": list(PENDING_INSTALL_STAGES)}},
                                         {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "lifecycle_stage": 1}):
            out.append({"type": "installation_unverified", "equipment_id": e["id"],
                        "detail": f"{e.get('name')} ({e.get('serial_number') or 'no serial'}) — installation not yet "
                                  f"confirmed ({e['lifecycle_stage'].replace('_', ' ')})"})
    return out


@router.post("/agreements/{agreement_id}/activate")
async def activate_agreement(agreement_id: str, body: Optional[ActivateIn] = None,
                             user=Depends(require_crm_perm("agreements.process"))):
    """CONTRACT ACTIVATION ENGINE — one agreement → one live contract.

    Idempotent (an active agreement returns its contract), atomic (concurrent
    calls cannot both run), blocks genuine conflicts until an authorised
    reviewer overrides, never invents dates, and preserves completed visits,
    posted invoices and confirmed Sage/Sicon references on retry."""
    from utils.cm_actions import raise_action, resolve_action
    of = _of(user)
    org_id = _org(user)
    body = body or ActivateIn()
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    if ag.get("status") == "active" and ag.get("contract_id"):
        c = await db.crm2_contracts.find_one({"id": ag["contract_id"], **of}, {"_id": 0, "contract_number": 1}) or {}
        return {"status": "active", "already_active": True, "contract_id": ag["contract_id"],
                "contract_number": c.get("contract_number") or ag.get("agreement_number"),
                "steps": ag.get("activation_steps") or []}
    if ag.get("status") not in ("signed", "activation_attention"):
        raise HTTPException(400, "Agreement must be signed before activation")

    sig, docu = ag.get("signature") or {}, ag.get("document") or {}
    if sig.get("method") == "customer_esignature" and (ag.get("signed_document") or {}).get("status") != "verified":
        raise HTTPException(409, {"code": "signed_document_missing",
                                  "message": "The customer's signed agreement PDF has not been stored and verified — retry storage first."})
    if sig.get("document_hash") and sig["document_hash"] != docu.get("sha256"):
        raise HTTPException(409, {"code": "document_changed",
                                  "message": "The signed document no longer matches the agreement — re-issue for signature."})
    missing = [f for f in ("start_date", "end_date", "billing_frequency") if not ag.get(f)]
    if missing:
        await _agreement_step_action(org_id, {**ag, "status": "activation_attention"})
        await raise_action(org_id, f"cm:activation-missing:{agreement_id}", type_="contract_missing_info",
                           subject=f"Activation blocked: {ag.get('agreement_number')}",
                           body=f"{ag.get('company_name')} — add the {', '.join(missing).replace('_', ' ')} to the agreement before activation.",
                           contract={"id": agreement_id, "company_id": ag.get("company_id"), "contract_number": ag.get("agreement_number")})
        raise HTTPException(409, {"code": "missing_information", "missing": missing,
                                  "message": "Agreement is missing " + ", ".join(missing).replace("_", " ")})

    existing_contract = await db.crm2_contracts.find_one({**of, "source_agreement_id": agreement_id}, {"_id": 0})
    cid = existing_contract["id"] if existing_contract else _id()
    conflicts = await _activation_conflicts(of, ag, cid)
    prior_override = next((st for st in (ag.get("activation_steps") or [])
                           if st.get("step") == "duplicate_check" and st.get("status") == "approved_override"), None)
    if conflicts and existing_contract and prior_override:
        reviewed = {(x.get("type"), x.get("contract_id") or x.get("equipment_id")) for x in prior_override.get("conflicts") or []}
        if all((x["type"], x.get("contract_id") or x.get("equipment_id")) in reviewed for x in conflicts):
            body.conflict_review_note = body.conflict_review_note or prior_override.get("detail") or "previously reviewed"
            user = {**user, "crm_permissions": list(set((user.get("crm_permissions") or []) + ["exceptions.approve"]))}
    if conflicts:
        if not body.conflict_review_note:
            await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
                "status": "activation_attention", "activation_conflicts": conflicts, "updated_at": _now()}})
            await _agreement_step_action(org_id, {**ag, "status": "activation_attention"})
            await raise_action(org_id, f"cm:activation-conflict:{agreement_id}", type_="activation_conflict",
                               subject=f"Review before activation: {ag.get('agreement_number')}",
                               body="; ".join(c["detail"] for c in conflicts[:5]),
                               contract={"id": agreement_id, "company_id": ag.get("company_id"), "contract_number": ag.get("agreement_number")})
            raise HTTPException(409, {"code": "activation_conflict", "conflicts": conflicts,
                                      "message": "Possible duplicate cover — an authorised manager must review before activation."})
        if "exceptions.approve" not in (user.get("crm_permissions") or []):
            raise HTTPException(403, "Only a Service & Aftersales Manager or Administrator can approve activation over a conflict.")

    claimed = await db.crm2_afs_agreements.find_one_and_update(
        {"id": agreement_id, **of, "status": {"$in": ["signed", "activation_attention"]}},
        {"$set": {"status": "activating", "updated_at": _now()}})
    if not claimed:
        raise HTTPException(409, "Activation already in progress — refresh in a moment.")

    steps = [{"step": "duplicate_check", "status": "ok" if not conflicts else "approved_override",
              **({"detail": body.conflict_review_note, "by": user.get("email"), "conflicts": conflicts} if conflicts else {})}]
    try:
        # 1. Contract record — create once; preserve confirmed external refs + created_at.
        contract_doc = {
            "organization_id": org_id, "contract_number": ag.get("agreement_number"),
            "company_id": ag["company_id"], "company_name": ag.get("company_name"),
            "linked_organization_id": ag.get("linked_organization_id"),
            "title": ag["schedules"]["schedule2_agreement"]["agreement_type"],
            "type": "service", "tier": ag.get("contract_type"), "contract_type": ag.get("contract_type"),
            "annual_value": ag.get("annual_value", 0),
            "total_value": round(ag.get("annual_value", 0) * max(1, ag.get("term_years", 1)), 2),
            "start_date": ag.get("start_date"), "end_date": ag.get("end_date"),
            "billing_frequency": ag.get("billing_frequency"), "status": "active", "source": "aftersales",
            "source_agreement_id": agreement_id, "source_quote_id": ag.get("quote_id"),
            "source_sales_quote_id": ag.get("source_sales_quote_id"),
            "pricing_version": ag.get("pricing_version"), "package_version": ag.get("package_version"),
            "tc_version": ag.get("tc_version"), "updated_at": _now(),
        }
        await db.crm2_contracts.update_one(
            {"id": cid, **of},
            {"$set": contract_doc, "$setOnInsert": {"id": cid, "created_at": _now(), "activated_at": _now()}},
            upsert=True)
        steps.append({"step": "contract_record", "status": "ok", "contract_id": cid,
                      "reused": bool(existing_contract)})

        # 2. Asset cover on the operations equipment register.
        linked = ag.get("linked_organization_id")
        asset_ids = [a["id"] for a in (ag.get("asset_register") or []) if a.get("annual", 0) > 0 and a.get("id")]
        cover = {"contract_id": cid, "contract_number": ag.get("agreement_number"),
                 "cover": ag.get("contract_type"), "start": ag.get("start_date"), "end": ag.get("end_date")}
        if linked and asset_ids:
            res = await db.equipment.update_many({"organization_id": linked, "id": {"$in": asset_ids}},
                                                 {"$set": {"contract_cover": cover, "updated_at": _now()}})
            steps.append({"step": "asset_cover", "status": "ok", "assets_covered": res.modified_count})
        else:
            steps.append({"step": "asset_cover", "status": "skipped", "detail": "No priced assets to cover"})

        # 3. Contractual PPM obligations (merged — completed visits untouched).
        from utils.cm_service_link import plan_obligations, merge_obligations
        planned = plan_obligations(cid, ag, _service_schedule(ag.get("start_date"), ag.get("visits_per_year", 2),
                                                              ag.get("term_years", 1), ag.get("end_date")))
        prev_svc = await db.crm2_afs_service_schedules.find_one({"contract_id": cid, "organization_id": org_id}, {"_id": 0}) or {}
        svc = merge_obligations(cid, prev_svc.get("visits"), planned)
        await db.crm2_afs_service_schedules.update_one(
            {"contract_id": cid, "organization_id": org_id},
            {"$set": {"contract_id": cid, "organization_id": org_id, "agreement_id": agreement_id,
                      "linked_organization_id": ag.get("linked_organization_id"),
                      "visits_per_year": ag.get("visits_per_year", 2), "visits": svc, "updated_at": _now()},
             "$inc": {"rev": 1}}, upsert=True)
        steps.append({"step": "service_schedule", "status": "ok", "visits": len(svc),
                      "preserved": len(svc) - len([v for v in svc if v.get("status") == "planned"])})

        # 4. Billing schedule (merged — posted invoices untouched).
        planned_b = _billing_schedule(ag.get("annual_value", 0), ag.get("billing_frequency"), ag.get("start_date"),
                                      ag.get("term_years", 1), ag.get("end_date"))
        prev_b = await db.crm2_afs_billing.find_one({"contract_id": cid, "organization_id": org_id}, {"_id": 0}) or {}
        bills = _merge_invoices(prev_b.get("invoices"), planned_b)
        await db.crm2_afs_billing.update_one(
            {"contract_id": cid, "organization_id": org_id},
            {"$set": {"contract_id": cid, "organization_id": org_id, "agreement_id": agreement_id,
                      "frequency": ag.get("billing_frequency"), "invoices": bills, "updated_at": _now()}}, upsert=True)
        steps.append({"step": "billing_schedule", "status": "ok", "invoices": len(bills)})

        if ag.get("billing_frequency") == "monthly" and not ag.get("direct_debit_received"):
            steps.append({"step": "direct_debit", "status": "warning", "detail": "Direct Debit mandate outstanding"})
        else:
            steps.append({"step": "direct_debit", "status": "ok"})

        # 5. Finance outbox (idempotent; "synced" only with a real Sage reference).
        from utils.finance_sync import enqueue_finance_sync
        fin = await enqueue_finance_sync(org_id, cid, "activation", user.get("email") or user.get("id"))
        steps.append({"step": "sage_sync", "status": "ok" if fin["status"] == "synced" else (
            "warning" if fin["status"] == "failed" else "queued"),
            "detail": fin.get("external_ref") or fin.get("detail") or "Queued for finance"})
    except Exception as e:
        await db.crm2_afs_agreements.update_one({"id": agreement_id, **of, "status": "activating"}, {"$set": {
            "status": "activation_attention", "activation_steps": steps + [{"step": "error", "status": "failed", "detail": str(e)}],
            "updated_at": _now()}})
        raise HTTPException(500, f"Activation stopped part-way and can be retried safely: {e}")

    tl = ag.get("timeline", []) + [{"at": _now(), "event": "Contract activated", "by": user.get("email")}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "status": "active", "contract_id": cid, "activated_at": _now(), "activation_conflicts": conflicts,
        "activation_steps": steps, "timeline": tl, "updated_at": _now()}})
    await resolve_action(org_id, f"cm:activation-conflict:{agreement_id}", "Activated after review.")
    await resolve_action(org_id, f"cm:activation-missing:{agreement_id}", "Information completed.")
    await _agreement_step_action(org_id, {**ag, "status": "active"})
    welcome = None
    try:
        from utils.cm_agreements import send_welcome_pack
        welcome = await send_welcome_pack(org_id, cid, actor=user.get("email") or "system")
    except Exception:
        import logging
        logging.getLogger(__name__).warning("welcome pack failed for %s", cid, exc_info=True)
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="activate", user=user,
                       extra={"contract_id": cid, "conflict_override": body.conflict_review_note})
    return {"status": "active", "contract_id": cid, "contract_number": ag.get("agreement_number"), "steps": steps,
            "service_visits": len(svc), "invoices": len(bills), "assets_covered": len(asset_ids),
            "welcome_pack": welcome}


@router.get("/contracts/{contract_id}/schedules")
async def contract_schedules(contract_id: str, user=Depends(get_crm_user)):
    """Live contract compliance view — service + billing schedule (§71-75)."""
    of = _of(user)
    org_id = _org(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    from utils.cm_service_link import sync_contract, obligation_bucket
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    visits = (await sync_contract(org_id, contract))["visits"]
    for v in visits:
        v["bucket"] = obligation_bucket(v, today)
    bill = await db.crm2_afs_billing.find_one({"contract_id": contract_id, "organization_id": org_id}, _PUBLIC)
    done = {"completed", "verified", "cancelled", "excluded"}
    outstanding = sorted((v for v in visits if (v.get("status") or "planned") not in done),
                         key=lambda v: v.get("planned_date") or "")
    overdue = [v for v in outstanding if (v.get("planned_date") or "9999") < today and not v.get("case_id")]
    nxt = outstanding[0] if outstanding else None
    return {
        "contract": {"id": contract_id, "contract_number": contract.get("contract_number"),
                     "status": contract.get("status"), "annual_value": contract.get("annual_value"),
                     "sicon_sync_status": contract.get("sicon_sync_status"),
                     "sage_sync_status": contract.get("sage_sync_status")},
        "service": {"visits": visits, "required": len(visits),
                    "completed": sum(1 for v in visits if v.get("status") in ("completed", "verified")),
                    "booked": sum(1 for v in visits if v.get("status") == "booked" and v.get("case_id")),
                    "cancelled": sum(1 for v in visits if v.get("status") in ("cancelled", "excluded")),
                    "overdue": len(overdue),
                    "next_due": nxt.get("planned_date") if nxt else None,
                    "next_due_overdue": bool(nxt and nxt in overdue),
                    "next_due_status": (nxt or {}).get("status") or ("planned" if nxt else None)},
        "welcome_pack": {k: v for k, v in (contract.get("welcome_pack") or {}).items() if k != "history"} or None,
        "billing": (bill or {}).get("invoices", []),
    }


# ══════════════════════════════════════════════════════════════════════════
# MID-TERM AMENDMENTS (§Task 5) — add/remove equipment on a live contract with
# deterministic pro-rata pricing. Reuses the pricing engine + billing helpers.
# ══════════════════════════════════════════════════════════════════════════

async def _price_assets(org_id, assets, contract_type):
    """Deterministic per-asset annual at the contract's tier (no extra discount)."""
    lines = [{"model": a.get("model") or a.get("model_code") or "",
              "console_type": a.get("console_type") or "", "qty": 1} for a in assets]
    if not lines:
        return [], 0.0, []
    res = await _compute_quote(org_id, lines, contract_type=contract_type,
                               pricing_level="standard", quote_discount_pct=0)
    factor = res["summary"]["contract_factor"]
    priced = []
    for a, ln in zip(assets, res["lines"]):
        annual = round(float(ln.get("annual_line_gold", 0)) * factor, 2)
        priced.append({
            "asset_id": a.get("id"), "name": a.get("name"),
            "model": a.get("model") or a.get("model_code") or "",
            "console_type": a.get("console_type") or "",
            "serial_number": a.get("serial_number", ""), "site_id": a.get("site_id"),
            "annual": annual, "status": ln.get("status"),
        })
    return priced, round(res["summary"]["contract_type_annual"], 2), res.get("warnings", [])


async def _amendment_context(contract, org_id):
    """Return (linked_org, covered_assets, coverable_assets) from the register."""
    linked = contract.get("linked_organization_id")
    if not linked:
        return None, [], []
    equipment = await db.equipment.find(
        {"organization_id": linked},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
         "serial_number": 1, "site_id": 1, "contract_cover": 1}).to_list(None)
    covered, coverable = [], []
    for e in equipment:
        cover = e.get("contract_cover")
        if isinstance(cover, dict) and cover.get("contract_id") == contract["id"]:
            covered.append(e)
        elif not cover:
            coverable.append(e)
    return linked, covered, coverable


@router.get("/contracts/{contract_id}/amendable-assets")
async def amendable_assets(contract_id: str, user=Depends(get_crm_user)):
    of = _of(user)
    org_id = _org(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    linked, covered, coverable = await _amendment_context(contract, org_id)
    ct = contract.get("contract_type") or contract.get("tier") or "gold"
    covered_priced, _, _ = await _price_assets(org_id, covered, ct)
    coverable_priced, _, _ = await _price_assets(org_id, coverable, ct)
    now = datetime.now(timezone.utc)
    anniv = _next_anniversary(contract.get("start_date"), now)
    return {
        "contract": {"id": contract_id, "contract_number": contract.get("contract_number"),
                     "contract_type": ct, "annual_value": contract.get("annual_value", 0),
                     "end_date": contract.get("end_date"),
                     "next_anniversary": anniv.strftime("%Y-%m-%d") if anniv else None,
                     "billing_frequency": contract.get("billing_frequency", "annual")},
        "covered": covered_priced, "coverable": coverable_priced,
        "linked_organization_id": linked,
    }


class AmendmentIn(BaseModel):
    action: str  # "add" | "remove"
    asset_ids: List[str]
    effective_date: Optional[str] = None


async def _compute_amendment(contract, org_id, body: "AmendmentIn"):
    if body.action not in ("add", "remove"):
        raise HTTPException(400, "action must be 'add' or 'remove'")
    if not body.asset_ids:
        raise HTTPException(400, "Select at least one machine")
    eff = (body.effective_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    try:
        eff_dt = datetime.strptime(eff, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "effective_date must be YYYY-MM-DD")
    linked, covered, coverable = await _amendment_context(contract, org_id)
    pool = {a["id"]: a for a in (covered if body.action == "remove" else coverable)}
    selected = [pool[i] for i in body.asset_ids if i in pool]
    if not selected:
        raise HTTPException(400, "None of the selected machines are valid for this action")
    ct = contract.get("contract_type") or contract.get("tier") or "gold"
    priced, delta_annual, warnings = await _price_assets(org_id, selected, ct)
    anniv = _next_anniversary(contract.get("start_date"), eff_dt)
    days_remaining = max(0, (anniv - eff_dt).days) if anniv else 0
    pro_rata = round(delta_annual * days_remaining / 365.0, 2)
    signed = 1 if body.action == "add" else -1
    current_annual = round(float(contract.get("annual_value") or 0), 2)
    new_annual = round(current_annual + signed * delta_annual, 2)
    return {
        "action": body.action, "effective_date": eff, "linked_organization_id": linked,
        "next_anniversary": anniv.strftime("%Y-%m-%d") if anniv else None,
        "days_remaining": days_remaining, "lines": priced,
        "delta_annual": round(signed * delta_annual, 2),
        "pro_rata_amount": round(signed * pro_rata, 2),
        "current_annual": current_annual, "new_annual": new_annual,
        "warnings": warnings, "selected_ids": [a["id"] for a in selected],
    }


@router.post("/contracts/{contract_id}/amendments/preview")
async def preview_amendment(contract_id: str, body: AmendmentIn, user=Depends(require_crm_perm("contracts.manage"))):
    of = _of(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    return await _compute_amendment(contract, _org(user), body)


@router.post("/contracts/{contract_id}/amendments")
async def apply_amendment(contract_id: str, body: AmendmentIn, user=Depends(require_crm_perm("contracts.manage"))):
    of = _of(user)
    org_id = _org(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.get("status") != "active":
        raise HTTPException(400, "Only active contracts can be amended")
    calc = await _compute_amendment(contract, org_id, body)
    linked = calc["linked_organization_id"]
    ids = calc["selected_ids"]

    # 1. Update asset cover on the operations register (single source).
    if body.action == "add":
        cover = {"contract_id": contract_id, "contract_number": contract.get("contract_number"),
                 "cover": contract.get("contract_type"), "start": calc["effective_date"],
                 "end": contract.get("end_date")}
        await db.equipment.update_many({"organization_id": linked, "id": {"$in": ids}},
                                       {"$set": {"contract_cover": cover, "updated_at": _now()}})
    else:
        await db.equipment.update_many({"organization_id": linked, "id": {"$in": ids}},
                                       {"$set": {"contract_cover": None, "updated_at": _now()}})

    # 2. Adjust the authoritative contract value.
    new_annual = calc["new_annual"]
    term_years = max(1, contract.get("term_years", 1) or 1)
    await db.crm2_contracts.update_one({"id": contract_id, **of}, {"$set": {
        "annual_value": new_annual, "total_value": round(new_annual * term_years, 2),
        "last_amended_at": _now(), "updated_at": _now()}})

    # 3. Rebuild billing — keep paid/past, regenerate future unpaid at new annual,
    #    prepend a one-off pro-rata adjustment.
    bill = await db.crm2_afs_billing.find_one({"contract_id": contract_id, "organization_id": org_id}, _PUBLIC)
    invoices = (bill or {}).get("invoices", [])
    freq = (bill or {}).get("frequency") or contract.get("billing_frequency", "annual")
    eff = calc["effective_date"]
    if freq == "monthly":
        new_amt = round(new_annual / 12.0, 2)
    elif freq == "lump_sum":
        new_amt = round(new_annual * term_years, 2)
    else:
        new_amt = round(new_annual, 2)
    rebuilt = []
    for inv in invoices:
        if (inv.get("status") == "paid" or inv.get("type") == "pro_rata_amendment"
                or (inv.get("due_date") or "") < eff):
            rebuilt.append(inv)
        else:
            rebuilt.append({**inv, "amount": new_amt})
    if calc["pro_rata_amount"] != 0:
        rebuilt.append({"due_date": eff, "amount": calc["pro_rata_amount"], "status": "scheduled",
                        "type": "pro_rata_amendment",
                        "note": f"Pro-rata {body.action} ({calc['days_remaining']}d to anniversary)"})
    rebuilt.sort(key=lambda i: i.get("due_date") or "")
    await db.crm2_afs_billing.update_one(
        {"contract_id": contract_id, "organization_id": org_id},
        {"$set": {"contract_id": contract_id, "organization_id": org_id, "frequency": freq,
                  "invoices": rebuilt, "updated_at": _now()}}, upsert=True)

    # 4. Re-sync finance — refresh the Sicon Sales Order with the new value/billing.
    from utils.finance_sync import enqueue_finance_sync
    await enqueue_finance_sync(org_id, contract_id, "amendment", user.get("email") or user.get("id"))

    # 5. Persist the amendment history record.
    amd = {
        "id": _id(), "organization_id": org_id, "contract_id": contract_id,
        "contract_number": contract.get("contract_number"),
        "action": body.action, "effective_date": eff,
        "next_anniversary": calc["next_anniversary"], "days_remaining": calc["days_remaining"],
        "asset_ids": ids, "lines": calc["lines"],
        "delta_annual": calc["delta_annual"], "pro_rata_amount": calc["pro_rata_amount"],
        "previous_annual": calc["current_annual"], "new_annual": new_annual,
        "created_by": user.get("email") or user.get("id"), "created_at": _now(),
    }
    await db.crm2_afs_amendments.insert_one(dict(amd))
    await record_audit(entity_type="afs_contract", entity_id=contract_id, action="amend", user=user,
                       extra={"action": body.action, "assets": len(ids), "new_annual": new_annual})
    amd.pop("_id", None)
    return {"amendment": amd, "new_annual_value": new_annual,
            "pro_rata_amount": calc["pro_rata_amount"], "assets_changed": len(ids)}


@router.get("/contracts/{contract_id}/amendments")
async def list_amendments(contract_id: str, user=Depends(get_crm_user)):
    of = _of(user)
    rows = await db.crm2_afs_amendments.find(
        {"contract_id": contract_id, **of}, _PUBLIC).sort("created_at", -1).to_list(200)
    return {"amendments": rows, "count": len(rows)}


# ══════════════════════════════════════════════════════════════════════════
# PROFITABILITY & FORECAST REPORTING (§Task 8) — 12-month recurring-revenue
# forecast (from billing schedules) + high-claim contract warnings (svc_cases).
# ══════════════════════════════════════════════════════════════════════════

def _month_key(y, m):
    return f"{y:04d}-{m:02d}"


def _add_months(dt, n):
    idx = dt.month - 1 + n
    return dt.year + idx // 12, idx % 12 + 1


def _part_value(p):
    if not isinstance(p, dict):
        return 0.0
    for k in ("total", "line_total", "cost", "price_total"):
        if p.get(k) not in (None, ""):
            try:
                return float(p[k])
            except (ValueError, TypeError):
                pass
    unit = p.get("unit_price") or p.get("price") or p.get("unit_cost") or 0
    qty = p.get("qty") or p.get("quantity") or 1
    try:
        return float(unit) * float(qty)
    except (ValueError, TypeError):
        return 0.0


@router.get("/reports")
async def profitability_report(user=Depends(get_crm_user)):
    """Deterministic reporting: 12-month recurring-revenue forecast (actual
    scheduled invoices) + high-claim contract warnings (reactive/repair cases)."""
    of = _of(user)
    org_id = _org(user)
    settings = await db.crm2_afs_settings.find_one(of, {"_id": 0, "labour_rate": 1, "high_claim_ratio": 1}) or {}
    labour_rate = float(settings.get("labour_rate") or 75.0)
    ratio = float(settings.get("high_claim_ratio") or 0.5)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    contracts = await db.crm2_contracts.find(
        {**of, "status": "active"},
        {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "title": 1,
         "annual_value": 1, "end_date": 1, "contract_type": 1, "tier": 1}).to_list(1000)
    ids = [c["id"] for c in contracts]
    arr = round(sum(float(c.get("annual_value") or 0) for c in contracts), 2)

    # ── Forecast: sum scheduled invoices per month over the next 12 months ──
    month_keys = [_month_key(*_add_months(now, i)) for i in range(12)]
    buckets = {k: 0.0 for k in month_keys}
    horizon_end = _month_key(*_add_months(now, 12))
    start_key = month_keys[0]
    if ids:
        async for b in db.crm2_afs_billing.find(
                {"organization_id": org_id, "contract_id": {"$in": ids}}, {"_id": 0, "invoices": 1}):
            for inv in b.get("invoices", []):
                if inv.get("status") == "paid":
                    continue
                mk = (inv.get("due_date") or "")[:7]
                if start_key <= mk < horizon_end and mk in buckets:
                    buckets[mk] = round(buckets[mk] + float(inv.get("amount") or 0), 2)
    months = [{"month": k, "amount": round(buckets[k], 2)} for k in month_keys]
    total_12m = round(sum(buckets.values()), 2)

    horizon_date = (now + timedelta(days=365)).strftime("%Y-%m-%d")
    expiring = sorted(
        [{"contract_id": c["id"], "contract_number": c.get("contract_number"),
          "company_name": c.get("company_name") or c.get("title"),
          "annual_value": c.get("annual_value", 0), "end_date": c.get("end_date")}
         for c in contracts if today <= (c.get("end_date") or "") <= horizon_date],
        key=lambda x: x["end_date"] or "")

    # ── High-claim: reactive/repair cases in the trailing 12 months ──
    since = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    claim_rows = []
    for c in contracts:
        cases = await db.svc_cases.find(
            {"organization_id": org_id, "contract_id": c["id"],
             "case_type": {"$in": ["reactive", "repair"]},
             "created_at": {"$gte": since}},
            {"_id": 0, "estimated_minutes": 1, "allocated_parts": 1, "case_type": 1}).to_list(1000)
        if not cases:
            continue
        labour_minutes = sum(float(x.get("estimated_minutes") or 0) for x in cases)
        parts_cost = round(sum(_part_value(p) for x in cases for p in (x.get("allocated_parts") or [])), 2)
        est_cost = round(labour_minutes / 60.0 * labour_rate + parts_cost, 2)
        annual = float(c.get("annual_value") or 0)
        margin = round(annual - est_cost, 2)
        margin_pct = round(margin / annual * 100, 1) if annual > 0 else None
        flagged = (annual > 0 and est_cost >= annual * ratio) or (annual <= 0 and est_cost > 0)
        claim_rows.append({
            "contract_id": c["id"], "contract_number": c.get("contract_number"),
            "company_name": c.get("company_name") or c.get("title"),
            "annual_value": round(annual, 2), "claim_count": len(cases),
            "labour_minutes": labour_minutes, "parts_cost": parts_cost,
            "est_claim_cost": est_cost, "est_margin": margin, "margin_pct": margin_pct,
            "flagged": flagged,
        })
    claim_rows.sort(key=lambda r: (r["est_claim_cost"] / r["annual_value"]) if r["annual_value"] else 9e9, reverse=True)

    return {
        "forecast": {"arr": arr, "active_contracts": len(contracts),
                     "months": months, "total_12m": total_12m, "expiring_soon": expiring},
        "high_claim": {"labour_rate": labour_rate, "ratio_threshold": ratio,
                       "contracts": claim_rows,
                       "flagged_count": sum(1 for r in claim_rows if r["flagged"])},
        "generated_at": _now(),
    }




def _service_compliance(visits, today):
    """Summarise a service schedule into a compliance snapshot."""
    if not visits:
        return {"has_schedule": False, "required": 0, "completed": 0, "overdue": 0,
                "next_due": None, "state": "no_schedule"}
    from utils.cm_service_link import FINAL_VISIT
    visits = [v for v in visits if v.get("status") not in ("cancelled", "excluded")]
    completed = sum(1 for v in visits if v.get("status") in ("completed", "verified"))
    outstanding = sorted((v for v in visits if v.get("status") not in FINAL_VISIT), key=lambda v: v.get("planned_date") or "")
    overdue = sum(1 for v in outstanding if (v.get("planned_date") or "9999") < today and not v.get("case_id"))
    nxt = outstanding[0] if outstanding else None  # earliest outstanding — an older missed visit is never hidden
    state = "overdue" if overdue else ("complete" if completed >= len(visits) else "on_track")
    return {"has_schedule": True, "required": len(visits), "completed": completed,
            "booked": sum(1 for v in outstanding if v.get("case_id")),
            "overdue": overdue, "next_due": (nxt or {}).get("planned_date"), "state": state}


def _billing_compliance(invoices, today):
    """Summarise a billing schedule into a compliance snapshot."""
    if not invoices:
        return {"has_schedule": False, "total": 0, "paid": 0, "overdue": 0,
                "paid_to_date": 0.0, "next_due": None, "next_amount": None, "state": "no_schedule"}
    paid = sum(1 for i in invoices if i.get("status") == "paid")
    paid_to_date = round(sum(float(i.get("amount") or 0) for i in invoices if i.get("status") == "paid"), 2)
    overdue = sum(1 for i in invoices
                  if i.get("status") != "paid" and (i.get("due_date") or "") < today)
    upcoming = sorted((i for i in invoices
                       if i.get("status") != "paid" and (i.get("due_date") or "") >= today),
                      key=lambda i: i.get("due_date") or "")
    nxt = upcoming[0] if upcoming else None
    state = "overdue" if overdue else ("settled" if paid >= len(invoices) else "on_track")
    return {"has_schedule": True, "total": len(invoices), "paid": paid, "overdue": overdue,
            "paid_to_date": paid_to_date, "next_due": (nxt or {}).get("due_date"),
            "next_amount": (nxt or {}).get("amount"), "state": state}


@router.get("/contracts/compliance")
async def contracts_compliance(user=Depends(get_crm_user)):
    """Live compliance snapshot for every active contract — service visits due,
    billing status and Sicon/Sage sync — aggregated for the Contracts & Renewals
    tab. Reuses the same schedule collections as the per-contract view."""
    of = _of(user)
    org_id = _org(user)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    contracts = await db.crm2_contracts.find(
        {**of, "status": "active"},
        {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "title": 1,
         "tier": 1, "contract_type": 1, "annual_value": 1, "start_date": 1, "end_date": 1,
         "billing_frequency": 1, "sicon_sync_status": 1, "sage_sync_status": 1}).sort("end_date", 1).to_list(500)
    ids = [c["id"] for c in contracts]
    svc_map, bill_map = {}, {}
    if ids:
        async for s in db.crm2_afs_service_schedules.find(
                {"organization_id": org_id, "contract_id": {"$in": ids}}, _PUBLIC):
            svc_map[s["contract_id"]] = s.get("visits", [])
        async for b in db.crm2_afs_billing.find(
                {"organization_id": org_id, "contract_id": {"$in": ids}}, _PUBLIC):
            bill_map[b["contract_id"]] = b.get("invoices", [])

    rows, totals = [], {"active": len(contracts), "service_overdue": 0, "billing_overdue": 0,
                        "sync_pending": 0, "sync_failed": 0, "no_schedule": 0}
    for c in contracts:
        cid = c["id"]
        service = _service_compliance(svc_map.get(cid, []), today)
        billing = _billing_compliance(bill_map.get(cid, []), today)
        sicon = c.get("sicon_sync_status") or "not_synced"
        sage = c.get("sage_sync_status") or "not_synced"
        if service["overdue"]:
            totals["service_overdue"] += 1
        if billing["overdue"]:
            totals["billing_overdue"] += 1
        if "pending" in (sicon, sage):
            totals["sync_pending"] += 1
        if "failed" in (sicon, sage):
            totals["sync_failed"] += 1
        if not service["has_schedule"] and not billing["has_schedule"]:
            totals["no_schedule"] += 1
        rows.append({
            "contract_id": cid, "contract_number": c.get("contract_number"),
            "company_name": c.get("company_name") or c.get("title") or "Contract",
            "tier": c.get("contract_type") or c.get("tier"),
            "annual_value": c.get("annual_value"),
            "start_date": c.get("start_date"), "end_date": c.get("end_date"),
            "billing_frequency": c.get("billing_frequency"),
            "service": service, "billing": billing,
            "sicon_sync_status": sicon, "sage_sync_status": sage,
        })
    return {"contracts": rows, "count": len(rows), "totals": totals, "generated_at": _now()}


# ══════════════════════════════════════════════════════════════════════════
# FINANCE SYNC (Sage 200 via Sicon WebAPI) — durable outbox of Sicon-ready
# Sales Orders. Auto-posts live when SICON_WEBAPI_* env is set; otherwise queued
# for a one-click Sage-ready export (CSV/JSON) finance imports today. §Task-Sage
# ══════════════════════════════════════════════════════════════════════════

@router.get("/finance/sync")
async def finance_sync_list(status: str = "", user=Depends(get_crm_user)):
    from utils.finance_sync import finance_provider_configured
    of = _of(user)
    q = dict(of)
    if status:
        q["status"] = status
    rows = await db.crm2_afs_finance_sync.find(
        q, {"_id": 0, "payload": 0, "history": 0}).sort("updated_at", -1).to_list(500)
    totals = {"queued": 0, "synced": 0, "failed": 0}
    for r in rows:
        totals[r.get("status", "queued")] = totals.get(r.get("status", "queued"), 0) + 1
    return {"items": rows, "count": len(rows), "totals": totals,
            "provider": "sicon", "live_connected": finance_provider_configured()}


@router.get("/finance/sync/{contract_id}")
async def finance_sync_get(contract_id: str, user=Depends(get_crm_user)):
    doc = await db.crm2_afs_finance_sync.find_one({"contract_id": contract_id, **_of(user)}, _PUBLIC)
    if not doc:
        raise HTTPException(404, "No finance-sync record for this contract yet")
    return doc


def _sales_order_rows(items: list[dict]) -> list[dict]:
    """Flatten outbox Sales Orders → one CSV row per order line (Sage/Sicon import)."""
    out = []
    for it in items:
        p = it.get("payload") or {}
        cust = p.get("customer") or {}
        con = p.get("contract") or {}
        for ln in p.get("lines") or []:
            out.append({
                "customer_reference": cust.get("reference", ""),
                "customer_name": cust.get("name", ""),
                "customer_email": cust.get("email") or "",
                "contract_number": con.get("number", ""),
                "contract_type": con.get("type", ""),
                "document_type": p.get("document_type", "sales_order"),
                "line_due_date": ln.get("due_date", ""),
                "description": ln.get("description", ""),
                "nominal_code": ln.get("nominal_code", ""),
                "tax_code": ln.get("tax_code", ""),
                "net_amount": ln.get("net_amount", 0),
                "currency": p.get("currency", "GBP"),
                "external_id": p.get("external_id", ""),
                "sync_status": it.get("status", ""),
                "sicon_ref": it.get("external_ref") or "",
            })
    return out


def _sales_order_csv(items: list[dict]) -> bytes:
    import csv
    cols = ["customer_reference", "customer_name", "customer_email", "contract_number",
            "contract_type", "document_type", "line_due_date", "description", "nominal_code",
            "tax_code", "net_amount", "currency", "external_id", "sync_status", "sicon_ref"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for row in _sales_order_rows(items):
        w.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


@router.get("/finance/sync/{contract_id}/export")
async def finance_sync_export_one(contract_id: str, format: str = "csv", user=Depends(get_crm_user)):
    doc = await db.crm2_afs_finance_sync.find_one({"contract_id": contract_id, **_of(user)}, _PUBLIC)
    if not doc:
        raise HTTPException(404, "No finance-sync record for this contract yet")
    num = re.sub(r"[^A-Za-z0-9]+", "-", doc.get("contract_number") or contract_id).strip("-")
    if format == "json":
        import json
        body = json.dumps(doc.get("payload") or {}, indent=2).encode("utf-8")
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="sicon-{num}.json"'})
    csv_bytes = _sales_order_csv([doc])
    return Response(content=csv_bytes, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sicon-{num}.csv"'})


@router.get("/finance/sync/export/all")
async def finance_sync_export_all(status: str = "", user=Depends(get_crm_user)):
    """One-click Sage/Sicon-ready CSV of contract Sales Orders.
    status='outstanding' → only queued + failed (not yet posted to Sage)."""
    of = _of(user)
    q = dict(of)
    if status == "outstanding":
        q["status"] = {"$in": ["queued", "failed"]}
    elif status:
        q["status"] = status
    items = await db.crm2_afs_finance_sync.find(q, _PUBLIC).sort("updated_at", -1).to_list(1000)
    if not items:
        raise HTTPException(404, "Nothing to export yet")
    csv_bytes = _sales_order_csv(items)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    tag = "outstanding-" if status == "outstanding" else ""
    return Response(content=csv_bytes, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sicon-sales-orders-{tag}{stamp}.csv"'})


@router.post("/finance/sync/enqueue-outstanding")
async def finance_enqueue_outstanding(user=Depends(require_crm_perm("finance.sync"))):
    """Generate/refresh a Sicon Sales Order for every active contract not yet
    synced to Sage (no_order / queued / failed) so 'Export outstanding' captures
    them all. Attempts a live push per contract if Sicon is configured."""
    from utils.finance_sync import enqueue_finance_sync
    of = _of(user)
    org_id = _org(user)
    contracts = await db.crm2_contracts.find(
        {**of, "status": "active"}, {"_id": 0, "id": 1}).to_list(1000)
    synced_cids = set()
    async for s in db.crm2_afs_finance_sync.find({**of, "status": "synced"}, {"_id": 0, "contract_id": 1}):
        synced_cids.add(s["contract_id"])
    enqueued = 0
    for c in contracts:
        if c["id"] in synced_cids:
            continue
        await enqueue_finance_sync(org_id, c["id"], "bulk_enqueue", user.get("email"))
        enqueued += 1
    return {"enqueued": enqueued, "skipped_synced": len(synced_cids)}


@router.get("/finance/dashboard")
async def finance_dashboard(user=Depends(get_crm_user)):
    """Finance-only view — EVERY active contract with its Sage/Sicon posting
    status (merged with the finance-sync outbox). Contracts activated before the
    sync layer, or never posted, show as 'no_order' and can be pushed/exported."""
    from utils.finance_sync import finance_provider_configured
    of = _of(user)
    contracts = await db.crm2_contracts.find(
        {**of, "status": "active"},
        {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "annual_value": 1,
         "billing_frequency": 1, "end_date": 1, "contract_type": 1, "tier": 1}).sort("company_name", 1).to_list(1000)
    sync_by_cid = {}
    async for s in db.crm2_afs_finance_sync.find(of, _PUBLIC):
        sync_by_cid[s["contract_id"]] = s
    rows = []
    totals = {"total": len(contracts), "synced": 0, "queued": 0, "failed": 0,
              "no_order": 0, "outstanding": 0, "value_outstanding": 0.0}
    for c in contracts:
        s = sync_by_cid.get(c["id"])
        status = (s or {}).get("status") or "no_order"
        payload = (s or {}).get("payload") or {}
        net = payload.get("net_total")
        row = {
            "contract_id": c["id"], "contract_number": c.get("contract_number"),
            "company_name": c.get("company_name"),
            "contract_type": c.get("contract_type") or c.get("tier"),
            "annual_value": c.get("annual_value", 0),
            "billing_frequency": c.get("billing_frequency"), "end_date": c.get("end_date"),
            "status": status, "net_total": net, "lines": len(payload.get("lines") or []),
            "external_ref": (s or {}).get("external_ref"),
            "last_event": (s or {}).get("last_event"), "last_error": (s or {}).get("last_error"),
            "synced_at": (s or {}).get("synced_at"), "updated_at": (s or {}).get("updated_at"),
        }
        rows.append(row)
        totals[status] = totals.get(status, 0) + 1
        if status in ("queued", "failed", "no_order"):
            totals["outstanding"] += 1
            totals["value_outstanding"] = round(totals["value_outstanding"] + float(c.get("annual_value") or 0), 2)
    return {"contracts": rows, "totals": totals, "provider": "sicon",
            "live_connected": finance_provider_configured(), "generated_at": _now()}


@router.post("/finance/sync/{contract_id}/retry")
async def finance_sync_retry(contract_id: str, user=Depends(require_crm_perm("finance.sync"))):
    from utils.finance_sync import enqueue_finance_sync
    contract = await db.crm2_contracts.find_one({"id": contract_id, **_of(user)}, {"_id": 0, "id": 1})
    if not contract:
        raise HTTPException(404, "Contract not found")
    res = await enqueue_finance_sync(_org(user), contract_id, "manual_retry", user.get("email"))
    await record_audit(entity_type="afs_finance_sync", entity_id=contract_id, action="retry", user=user,
                       extra={"status": res.get("status")})
    return res


class FinanceMarkSyncedIn(BaseModel):
    external_ref: Optional[str] = None
    note: Optional[str] = None


@router.post("/finance/sync/{contract_id}/mark-synced")
async def finance_sync_mark_synced(contract_id: str, body: FinanceMarkSyncedIn,
                                   user=Depends(require_crm_perm("finance.post"))):
    """Manual reconcile — finance imported the Sales Order into Sage/Sicon and
    records the resulting reference (marks the outbox + contract as synced)."""
    of = _of(user)
    doc = await db.crm2_afs_finance_sync.find_one({"contract_id": contract_id, **of}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "No finance-sync record for this contract yet")
    if not ((body.external_ref or "").strip() or doc.get("external_ref")):
        raise HTTPException(400, "Enter the Sage Sales Order / invoice reference — a sync cannot be confirmed without it.")
    hist = (doc.get("history") or [])[-19:] + [{
        "at": _now(), "event": "manual_mark_synced", "status": "synced",
        "detail": body.note or f"Reconciled by {user.get('email')}", "by": user.get("email")}]
    await db.crm2_afs_finance_sync.update_one(
        {"contract_id": contract_id, **of},
        {"$set": {"status": "synced", "external_ref": body.external_ref or doc.get("external_ref"),
                  "synced_at": _now(), "last_error": None, "history": hist, "updated_at": _now()}})
    await db.crm2_contracts.update_one({"id": contract_id, **of}, {"$set": {
        "sage_sync_status": "synced", "sage_sync_detail": None,
        "finance_sync_status": "synced", "updated_at": _now()}})
    await record_audit(entity_type="afs_finance_sync", entity_id=contract_id, action="mark_synced",
                       user=user, extra={"external_ref": body.external_ref})
    return {"status": "synced", "external_ref": body.external_ref or doc.get("external_ref")}




# ══════════════════════════════════════════════════════════════════════════
# WARRANTY-TO-MAINTENANCE — revenue opportunity engine (§90-91)
# Turns every expiring Pulse warranty into a ready-made maintenance proposal.
# Live scan (no auto-contact); coordinator reviews and one-click builds a quote.
# ══════════════════════════════════════════════════════════════════════════

def _parse_dt(v):
    try:
        dt = datetime.fromisoformat((v or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/revenue/warranty-opportunities")
async def warranty_opportunities(window_days: int = 365, user=Depends(get_crm_user)):
    """Scan the estate for assets whose warranty ends within the window and are
    NOT already under maintenance cover, grouped by customer, with an estimated
    renewal value (priced by the deterministic engine — never invented)."""
    of = _of(user)
    org_id = _org(user)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, window_days))

    companies = await db.crm2_companies.find(of, {"_id": 0}).to_list(1000)
    opps = []
    for company in companies:
        linked = await _resolve_linked_org_for_company(company, user)
        if not linked:
            continue
        equipment = await db.equipment.find(
            {"organization_id": linked},
            {"_id": 0, "id": 1, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
             "serial_number": 1, "site_id": 1, "warranty_expiry": 1, "contract_cover": 1}).to_list(None)
        expiring = []
        for e in equipment:
            if e.get("contract_cover"):
                continue
            d = _parse_dt(e.get("warranty_expiry"))
            if d and now <= d <= horizon:
                expiring.append(e)
        if not expiring:
            continue
        annotated = [await _annotate_asset(org_id, e) for e in expiring]
        priceable = [{"config_id": a["config_id"], "qty": 1} for a in annotated
                     if a["pricing_status"] in ("SUPPORTED", "PROVISIONAL")]
        est = await _compute_quote(org_id, priceable, "gold", "standard") if priceable else {"summary": {"final_annual": 0}}
        dates = sorted(_parse_dt(e.get("warranty_expiry")) for e in expiring)
        supp = {"supported": sum(1 for a in annotated if a["pricing_status"] == "SUPPORTED"),
                "review": sum(1 for a in annotated if a["pricing_status"] in ("RRP_REQUIRED", "PROVISIONAL", "SUPPORTABILITY_REVIEW", "NOT_MATCHED")),
                "not_eligible": sum(1 for a in annotated if a["pricing_status"] == "NOT_ELIGIBLE")}
        opps.append({
            "company_id": company["id"], "company_name": company.get("name"),
            "linked_organization_id": linked,
            "assets_ending_warranty": len(expiring),
            "asset_ids": [a["id"] for a in annotated],
            "earliest_expiry": dates[0].strftime("%Y-%m-%d") if dates else None,
            "latest_expiry": dates[-1].strftime("%Y-%m-%d") if dates else None,
            "days_to_earliest": (dates[0] - now).days if dates else None,
            "estimated_annual_value": est["summary"]["final_annual"],
            "supportability": supp,
        })
    opps.sort(key=lambda o: (o["days_to_earliest"] if o["days_to_earliest"] is not None else 9999))
    return {"opportunities": opps, "count": len(opps), "window_days": window_days}


class WarrantyProposalIn(BaseModel):
    window_days: int = 365
    contract_type: str = "gold"
    pricing_level: str = "standard"
    term_years: int = 1
    quote_discount_pct: float = 0.0
    save: bool = True


@router.post("/revenue/warranty-opportunities/{company_id}/build-proposal")
async def build_warranty_proposal(company_id: str, body: WarrantyProposalIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """One-click: build a maintenance proposal for a customer's warranty-expiring
    assets, reusing the SAME deterministic auto-quoter."""
    of = _of(user)
    _org(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    linked = await _resolve_linked_org_for_company(company, user)
    if not linked:
        raise HTTPException(400, "Company has no linked operations organisation.")
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, body.window_days))
    equipment = await db.equipment.find(
        {"organization_id": linked}, {"_id": 0, "id": 1, "warranty_expiry": 1, "contract_cover": 1}).to_list(None)
    asset_ids = [e["id"] for e in equipment
                 if not e.get("contract_cover") and (lambda d: d and now <= d <= horizon)(_parse_dt(e.get("warranty_expiry")))]
    if not asset_ids:
        raise HTTPException(400, "No warranty-expiring assets found in this window.")
    build = BuildFromEstateIn(
        company_id=company_id, asset_ids=asset_ids, contract_type=body.contract_type,
        pricing_level=body.pricing_level, term_years=body.term_years,
        quote_discount_pct=body.quote_discount_pct, save=body.save, source="warranty_conversion")
    result = await build_quote_from_estate(build, user)
    result["source"] = "warranty_conversion"
    result["warranty_assets"] = len(asset_ids)
    return result



# ══════════════════════════════════════════════════════════════════════════
# RPI REVIEW ENGINE (§78-81) — never hard-codes an inflation figure.
# ══════════════════════════════════════════════════════════════════════════

def _next_anniversary(start_date, now):
    d = _parse_dt(start_date if "T" in (start_date or "") else (start_date or "") + "T00:00:00+00:00")
    if not d:
        return None
    anniv = d.replace(year=now.year)
    if anniv < now:
        anniv = anniv.replace(year=now.year + 1)
    return anniv


@router.get("/rpi/reviews")
async def rpi_reviews(window_days: int = 60, user=Depends(get_crm_user)):
    of = _of(user)
    now = datetime.now(timezone.utc)
    rows = []
    async for cc in db.crm2_contracts.find({**of, "status": "active"},
                                            {"_id": 0, "id": 1, "company_name": 1, "contract_number": 1,
                                             "annual_value": 1, "start_date": 1, "end_date": 1}):
        anniv = _next_anniversary(cc.get("start_date"), now)
        if not anniv:
            continue
        cycle = anniv.strftime("%Y")
        review = await db.crm2_afs_rpi_reviews.find_one({**of, "contract_id": cc["id"], "cycle": cycle}, _PUBLIC)
        days = (anniv - now).days
        rows.append({
            "contract_id": cc["id"], "contract_number": cc.get("contract_number"),
            "company_name": cc.get("company_name"), "current_annual_value": cc.get("annual_value", 0),
            "anniversary_date": anniv.strftime("%Y-%m-%d"), "days_to_anniversary": days,
            "cycle": cycle, "due": days <= window_days,
            "review": review,
        })
    rows.sort(key=lambda r: r["days_to_anniversary"])
    return {"reviews": rows, "due_count": sum(1 for r in rows if r["due"] and (r["review"] or {}).get("status") != "approved")}


class RpiSetIn(BaseModel):
    rpi_pct: float
    source: str = "Manual entry"
    effective_date: Optional[str] = None


@router.post("/rpi/reviews/{contract_id}")
async def set_rpi_review(contract_id: str, body: RpiSetIn, user=Depends(require_crm_perm("renewals.review"))):
    of = _of(user)
    cc = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not cc:
        raise HTTPException(404, "Contract not found")
    now = datetime.now(timezone.utc)
    anniv = _next_anniversary(cc.get("start_date"), now)
    cycle = anniv.strftime("%Y") if anniv else str(now.year)
    current = cc.get("annual_value", 0)
    proposed = round(current * (1 + body.rpi_pct / 100.0), 2)
    doc = {
        "organization_id": _org(user), "contract_id": contract_id, "cycle": cycle,
        "previous_value": current, "rpi_pct": body.rpi_pct, "proposed_value": proposed,
        "source": body.source, "effective_date": body.effective_date or (anniv.strftime("%Y-%m-%d") if anniv else None),
        "anniversary_date": anniv.strftime("%Y-%m-%d") if anniv else None,
        "status": "proposed", "updated_at": _now(), "created_by": user.get("email"),
    }
    existing = await db.crm2_afs_rpi_reviews.find_one({"organization_id": _org(user), "contract_id": contract_id, "cycle": cycle}, _PUBLIC)
    if existing:
        doc["id"] = existing["id"]
        await db.crm2_afs_rpi_reviews.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["id"] = _id()
        doc["created_at"] = _now()
        await db.crm2_afs_rpi_reviews.insert_one(doc)
    await record_audit(entity_type="afs_rpi", entity_id=doc["id"], action="propose", user=user,
                       extra={"contract": contract_id, "rpi_pct": body.rpi_pct, "proposed": proposed})
    return await db.crm2_afs_rpi_reviews.find_one({"id": doc["id"]}, _PUBLIC)


@router.post("/rpi/reviews/{review_id}/approve")
async def approve_rpi_review(review_id: str, user=Depends(require_crm_perm("renewals.approve"))):
    of = _of(user)
    r = await db.crm2_afs_rpi_reviews.find_one({"id": review_id, **of}, _PUBLIC)
    if not r:
        raise HTTPException(404, "RPI review not found")
    await db.crm2_afs_rpi_reviews.update_one({"id": review_id}, {"$set": {
        "status": "approved", "approved_by": user.get("email"), "approved_at": _now(), "updated_at": _now()}})
    # Apply the increase to the live contract effective from the effective date.
    await db.crm2_contracts.update_one({"id": r["contract_id"], **of}, {"$set": {
        "annual_value": r["proposed_value"], "rpi_last_review": _now(),
        "rpi_effective_date": r.get("effective_date"), "updated_at": _now()}})
    # Re-sync finance so Sicon carries the new (RPI-uplifted) contract value.
    from utils.finance_sync import enqueue_finance_sync
    await enqueue_finance_sync(_org(user), r["contract_id"], "rpi", user.get("email"))
    await record_audit(entity_type="afs_rpi", entity_id=review_id, action="approve", user=user,
                       extra={"contract": r["contract_id"], "old": r["previous_value"], "new": r["proposed_value"]})
    return {"status": "approved", "contract_id": r["contract_id"], "new_annual_value": r["proposed_value"]}


# ══════════════════════════════════════════════════════════════════════════
# RENEWALS (§82-85) — carry forward, reconcile CURRENT estate, compare.
# ══════════════════════════════════════════════════════════════════════════

@router.get("/renewals/pipeline")
async def renewals_pipeline(window_days: int = 120, user=Depends(get_crm_user)):
    of = _of(user)
    now = datetime.now(timezone.utc)
    horizon = (now + timedelta(days=max(1, window_days))).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    rows = []
    async for cc in db.crm2_contracts.find(
        {**of, "status": "active", "end_date": {"$lte": horizon, "$gte": today}},
        {"_id": 0, "id": 1, "company_id": 1, "company_name": 1, "annual_value": 1,
         "end_date": 1, "tier": 1, "contract_type": 1, "contract_number": 1}).sort("end_date", 1):
        try:
            days = (datetime.strptime(cc["end_date"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) - now).days
        except (ValueError, KeyError):
            days = None
        renewal = await db.crm2_afs_quotes.find_one(
            {**of, "source": "renewal", "renews_contract_id": cc["id"]}, {"_id": 0, "id": 1, "quote_number": 1, "summary": 1})
        rows.append({**cc, "days_to_expiry": days, "renewal_quote": renewal})
    return {"renewals": rows, "count": len(rows)}


class RenewalBuildIn(BaseModel):
    contract_type: Optional[str] = None
    pricing_level: str = "standard"
    term_years: int = 1
    quote_discount_pct: float = 0.0


@router.post("/renewals/{contract_id}/build")
async def build_renewal(contract_id: str, body: RenewalBuildIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    of = _of(user)
    cc = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not cc:
        raise HTTPException(404, "Contract not found")
    if not cc.get("company_id"):
        raise HTTPException(400, "Contract has no linked customer to renew.")
    build = BuildFromEstateIn(
        company_id=cc["company_id"], contract_type=(body.contract_type or cc.get("contract_type") or cc.get("tier") or "gold"),
        pricing_level=body.pricing_level, term_years=body.term_years,
        quote_discount_pct=body.quote_discount_pct, save=True, source="renewal")
    result = await build_quote_from_estate(build, user)
    # Tag the saved renewal quote back to the contract.
    if result.get("saved_quote_id"):
        await db.crm2_afs_quotes.update_one(
            {"id": result["saved_quote_id"], **of},
            {"$set": {"renews_contract_id": contract_id, "updated_at": _now()}})
    prev = cc.get("annual_value", 0)
    proposed = result["summary"]["final_annual"]
    change = round(proposed - prev, 2)
    result["renewal_comparison"] = {
        "previous_annual": prev, "proposed_annual": proposed,
        "change_amount": change,
        "change_pct": round((change / prev * 100.0), 2) if prev else None,
        "renews_contract_id": contract_id, "contract_number": cc.get("contract_number"),
    }
    return result



# ══════════════════════════════════════════════════════════════════════════
# PROACTIVE ALERTS (§Task 3) — warranty + RPI reminders at 180/120/90 windows.
# Auto-creates coordinator tasks (crm2_activities) + notifications.
# ══════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def list_afs_alerts(status: str = "open", limit: int = 100, user=Depends(get_crm_user)):
    """Coordinator-facing list of warranty + RPI reminder tasks for this org."""
    of = _of(user)
    query = {**of, "source": "afs_alerts"}
    if status and status != "all":
        query["status"] = status
    alerts = await db.crm2_activities.find(query, _PUBLIC).sort("created_at", -1).to_list(max(1, min(limit, 300)))
    open_alerts = await db.crm2_activities.find(
        {**of, "source": "afs_alerts", "status": "open"}, {"_id": 0, "type": 1}).to_list(1000)
    unread = await db.crm2_notifications.count_documents({**of, "type": "aftersales_alert", "read": False})
    return {
        "alerts": alerts,
        "counts": {
            "warranty": sum(1 for a in open_alerts if a.get("type") == "warranty_alert"),
            "rpi": sum(1 for a in open_alerts if a.get("type") == "rpi_review_due"),
            "contract_admin": sum(1 for a in open_alerts if a.get("type") in (
                "contract_missing_info", "renewal_approval", "renewal_blocked")),
            "open_total": len(open_alerts),
            "unread_notifications": unread,
        },
    }


@router.post("/alerts/run")
async def run_afs_alerts(user=Depends(require_crm_perm("tasks.manage"))):
    """Manual 'Run scan now' — same sweep the background worker runs, scoped to
    this org. Idempotent (dedupe_key prevents duplicates)."""
    from utils.afs_alerts import run_afs_alerts_once
    res = await run_afs_alerts_once(_org(user))
    await record_audit(entity_type="afs_alerts", entity_id="scan", action="run", user=user, extra=res)
    return res


@router.post("/quotes/chasers/run")
async def run_afs_quote_chasers(user=Depends(require_crm_perm("quotes.maintenance"))):
    """Manual 'Run follow-ups now' — emails reminders to customers whose sent
    quotes are nearing expiry (Day 14/5 by default) and notifies the coordinator
    of any that expired unsigned. Idempotent per (quote, window)."""
    from utils.afs_alerts import run_quote_chasers_once
    res = await run_quote_chasers_once(_org(user))
    await record_audit(entity_type="afs_quote_chasers", entity_id="run", action="run", user=user, extra=res)
    return res


@router.post("/alerts/{activity_id}/dismiss")
async def dismiss_afs_alert(activity_id: str, user=Depends(require_crm_perm("tasks.manage"))):
    of = _of(user)
    r = await db.crm2_activities.update_one(
        {"id": activity_id, **of, "source": "afs_alerts"},
        {"$set": {"status": "done", "dismissed_at": _now(), "dismissed_by": user.get("email"), "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Alert not found")
    await db.crm2_notifications.update_many(
        {**of, "activity_id": activity_id}, {"$set": {"read": True}})
    return {"status": "done", "id": activity_id}



# ══════════════════════════════════════════════════════════════════════════
# CONTRACT AI ASSISTANT (Task 7) — deterministic-grounded coverage summaries,
# customer-email drafts and grounded Q&A. The model ONLY writes prose from the
# fact sheet we assemble here; it is instructed NEVER to invent a figure, date,
# quantity or coverage term. All numbers come from the live contract records.
# ══════════════════════════════════════════════════════════════════════════

def _gbp(v):
    try:
        return f"£{float(v or 0):,.2f}"
    except (ValueError, TypeError):
        return "£0.00"


async def _resolve_linked_org(contract, of):
    linked = contract.get("linked_organization_id")
    if linked:
        return linked
    cid = contract.get("company_id")
    if cid:
        company = await db.crm2_companies.find_one({"id": cid, **of}, {"_id": 0, "linked_organization_id": 1})
        if company:
            return company.get("linked_organization_id")
    return None


async def _contract_fact_sheet(org_id, contract):
    """Assemble a 100% deterministic fact sheet for one contract — the ONLY
    ground truth the assistant is allowed to use."""
    of = {"organization_id": org_id}
    cid = contract["id"]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    tier = (contract.get("contract_type") or contract.get("tier") or "").lower()

    pkg = await db.crm2_afs_packages.find_one({**of, "key": tier}, _PUBLIC) or {}

    covered = []
    linked = await _resolve_linked_org(contract, of)
    if linked:
        equipment = await db.equipment.find(
            {"organization_id": linked},
            {"_id": 0, "name": 1, "model": 1, "model_code": 1, "console_type": 1,
             "serial_number": 1, "contract_cover": 1}).to_list(None)
        for e in equipment:
            cover = e.get("contract_cover")
            if isinstance(cover, dict) and cover.get("contract_id") == cid:
                covered.append({
                    "name": e.get("name") or e.get("model") or e.get("model_code"),
                    "model": e.get("model") or e.get("model_code"),
                    "serial_number": e.get("serial_number"),
                    "console_type": e.get("console_type"),
                })

    svc = await db.crm2_afs_service_schedules.find_one({**of, "contract_id": cid}, _PUBLIC) or {}
    visits = svc.get("visits", [])
    service = _service_compliance(visits, today)
    upcoming_visits = sorted(
        [v for v in visits if v.get("status") != "completed" and (v.get("planned_date") or "") >= today],
        key=lambda v: v.get("planned_date") or "")[:4]

    bill = await db.crm2_afs_billing.find_one({**of, "contract_id": cid}, _PUBLIC) or {}
    invoices = bill.get("invoices", [])
    billing = _billing_compliance(invoices, today)
    upcoming_invoices = sorted(
        [i for i in invoices if i.get("status") != "paid" and (i.get("due_date") or "") >= today],
        key=lambda i: i.get("due_date") or "")[:4]

    anniv = _next_anniversary(contract.get("start_date"), now)
    cycle = anniv.strftime("%Y") if anniv else str(now.year)
    rpi = await db.crm2_afs_rpi_reviews.find_one({**of, "contract_id": cid, "cycle": cycle}, _PUBLIC)

    cust_email, cust_name = await _contract_customer_email(contract, of)

    # Recent service-desk history for this contract (Voice of Customer) —
    # so the assistant can reference recent visits, faults and open work.
    since_12m = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    open_states = {"closed", "invoiced", "cancelled", "resolved"}
    all_cases = await db.svc_cases.find(
        {**of, "contract_id": cid},
        {"_id": 0, "reference": 1, "title": 1, "status": 1, "case_type": 1,
         "fault_code": 1, "fault_category": 1, "priority": 1, "asset_name": 1,
         "site_name": 1, "created_at": 1, "closed_at": 1}).sort("created_at", -1).to_list(500)
    recent_cases = [{
        "reference": x.get("reference"),
        "title": x.get("title") or x.get("fault_category") or x.get("case_type"),
        "case_type": x.get("case_type"),
        "fault_code": x.get("fault_code"),
        "priority": x.get("priority"),
        "asset_name": x.get("asset_name"),
        "status": x.get("status"),
        "created_at": (x.get("created_at") or "")[:10],
        "closed_at": (x.get("closed_at") or "")[:10] or None,
    } for x in all_cases[:6]]
    cases_open = sum(1 for x in all_cases if (x.get("status") or "").lower() not in open_states)
    cases_12m = sum(1 for x in all_cases if (x.get("created_at") or "")[:10] >= since_12m)

    return {
        "contract_number": contract.get("contract_number"),
        "company_name": contract.get("company_name") or contract.get("title") or "Customer",
        "status": contract.get("status"),
        "package": pkg.get("name") or (tier.title() if tier else "Maintenance"),
        "package_description": pkg.get("description"),
        "package_coverage": pkg.get("coverage"),
        "annual_value": contract.get("annual_value", 0),
        "total_value": contract.get("total_value"),
        "billing_frequency": contract.get("billing_frequency") or "annual",
        "start_date": contract.get("start_date"),
        "end_date": contract.get("end_date"),
        "next_anniversary": anniv.strftime("%Y-%m-%d") if anniv else None,
        "covered_equipment_count": len(covered),
        "covered_equipment": covered,
        "service": service,
        "upcoming_visits": [{"planned_date": v.get("planned_date"), "status": v.get("status")} for v in upcoming_visits],
        "billing": billing,
        "upcoming_invoices": [{"due_date": i.get("due_date"), "amount": i.get("amount"), "status": i.get("status")} for i in upcoming_invoices],
        "rpi_review": ({"status": rpi.get("status"), "rpi_pct": rpi.get("rpi_pct"),
                        "proposed_value": rpi.get("proposed_value"),
                        "effective_date": rpi.get("effective_date")} if rpi else None),
        "service_cases_total": len(all_cases),
        "service_cases_open": cases_open,
        "service_cases_12m": cases_12m,
        "recent_cases": recent_cases,
        "customer_email": cust_email,
        "customer_name": cust_name,
    }


def _facts_to_text(f):
    """Render the fact sheet as a compact text block for the model prompt."""
    lines = [
        f"Contract number: {f['contract_number']}",
        f"Customer: {f['company_name']}",
        f"Contract status: {f['status']}",
        f"Package: {f['package']}" + (f" — {f['package_description']}" if f.get('package_description') else ""),
    ]
    if f.get("package_coverage"):
        lines.append(f"Package coverage terms: {f['package_coverage']}")
    lines.append(f"Annual value: {_gbp(f['annual_value'])} (billed {f['billing_frequency']})")
    if f.get("total_value"):
        lines.append(f"Total contract value: {_gbp(f['total_value'])}")
    lines.append(f"Contract term: {f.get('start_date') or 'n/a'} to {f.get('end_date') or 'n/a'}")
    lines.append(f"Next anniversary / RPI review point: {f.get('next_anniversary') or 'n/a'}")

    ce = f.get("covered_equipment") or []
    lines.append(f"Covered equipment ({f['covered_equipment_count']} machines):")
    if ce:
        for e in ce[:40]:
            bits = [e.get("name") or "Machine"]
            if e.get("serial_number"):
                bits.append(f"S/N {e['serial_number']}")
            if e.get("console_type"):
                bits.append(str(e["console_type"]))
            lines.append("  - " + " · ".join(bits))
        if len(ce) > 40:
            lines.append(f"  - (+{len(ce) - 40} more)")
    else:
        lines.append("  - (no equipment cover records available in the system)")

    s = f.get("service") or {}
    if s.get("has_schedule"):
        lines.append(f"Service schedule: {s.get('completed', 0)} of {s.get('required', 0)} visits completed, "
                     f"{s.get('overdue', 0)} overdue, next visit due {s.get('next_due') or 'n/a'}.")
        for v in f.get("upcoming_visits") or []:
            lines.append(f"  - Upcoming visit: {v.get('planned_date')}")
    else:
        lines.append("Service schedule: none recorded.")

    b = f.get("billing") or {}
    if b.get("has_schedule"):
        lines.append(f"Billing: {b.get('paid', 0)} of {b.get('total', 0)} invoices paid ({_gbp(b.get('paid_to_date'))} to date), "
                     f"{b.get('overdue', 0)} overdue. Next invoice {_gbp(b.get('next_amount'))} due {b.get('next_due') or 'n/a'}.")
        for i in f.get("upcoming_invoices") or []:
            lines.append(f"  - Upcoming invoice: {_gbp(i.get('amount'))} due {i.get('due_date')}")
    else:
        lines.append("Billing: no invoice schedule recorded.")

    r = f.get("rpi_review")
    if r:
        lines.append(f"RPI review ({r.get('status')}): proposed {r.get('rpi_pct')}% increase to "
                     f"{_gbp(r.get('proposed_value'))}, effective {r.get('effective_date') or 'n/a'}.")
    else:
        lines.append("RPI review: none proposed for the current cycle.")

    rc = f.get("recent_cases") or []
    lines.append(f"Service history: {f.get('service_cases_total', 0)} case(s) logged against this contract "
                 f"({f.get('service_cases_open', 0)} currently open, {f.get('service_cases_12m', 0)} in the last 12 months).")
    if rc:
        lines.append("Most recent service cases (newest first):")
        for x in rc:
            bits = [x.get("reference") or "case", x.get("title") or x.get("case_type") or "service"]
            if x.get("fault_code"):
                bits.append(f"fault {x['fault_code']}")
            if x.get("asset_name"):
                bits.append(x["asset_name"])
            meta = f"{x.get('status') or ''}; logged {x.get('created_at') or 'n/a'}"
            if x.get("closed_at"):
                meta += f"; closed {x['closed_at']}"
            lines.append(f"  - {' · '.join(bits)} ({meta})")
    else:
        lines.append("Service history: no service cases recorded against this contract.")
    return "\n".join(lines)


_AI_SYSTEM = (
    "You are the Pulse Fitness Aftersales assistant, helping a maintenance-contracts coordinator. "
    "You will be given a CONTRACT FACTS block. You must use ONLY those facts. "
    "NEVER invent, estimate, round differently or change any figure, price, date, quantity, serial "
    "number or coverage term. If a needed detail is not in the facts, say it is not available in the "
    "system and suggest checking the contract record — do not guess. All money is in GBP (£). "
    "Write in clear, professional British English. Do not use markdown headings or asterisks; use plain "
    "paragraphs and simple hyphen bullet points where helpful."
)

_EMAIL_BRIEFS = {
    "renewal_reminder": "Draft a friendly renewal-reminder email to the customer. Note the contract end date, "
                        "the package and current annual value, and invite them to renew or discuss options. "
                        "Do not quote a new renewal price unless it is in the facts.",
    "rpi_increase": "Draft an email explaining the upcoming RPI (inflation-linked) price review. State the current "
                    "annual value, the proposed percentage and new value, and the effective date, taken only from "
                    "the RPI review facts. If no RPI review is present, say a review has not yet been proposed.",
    "service_due": "Draft an email letting the customer know their next preventative service visit is coming up, "
                   "using the next-visit date from the facts, and confirming what their package covers.",
    "welcome": "Draft a warm welcome / onboarding email confirming their new maintenance cover — package, covered "
               "equipment count, annual value, billing frequency and term dates, and how to raise a service request.",
    "coverage_confirmation": "Draft an email confirming exactly what their contract covers — package, covered "
                             "equipment and service commitments — for the customer's records.",
    "general": "Draft the customer email the coordinator has asked for, grounded only in the facts.",
}


class AfsAiIn(BaseModel):
    contract_id: str
    mode: str  # "summary" | "email" | "question"
    email_type: Optional[str] = None
    instruction: Optional[str] = None
    question: Optional[str] = None


@router.get("/ai/contracts")
async def ai_contract_list(user=Depends(get_crm_user)):
    """Active contracts available to the AI assistant (picker)."""
    of = _of(user)
    rows = await db.crm2_contracts.find(
        {**of, "status": "active"},
        {"_id": 0, "id": 1, "contract_number": 1, "company_name": 1, "title": 1,
         "contract_type": 1, "tier": 1, "annual_value": 1, "end_date": 1}).sort("end_date", 1).to_list(1000)
    return {"contracts": [{
        "id": r["id"], "contract_number": r.get("contract_number"),
        "company_name": r.get("company_name") or r.get("title") or "Contract",
        "tier": r.get("contract_type") or r.get("tier"),
        "annual_value": r.get("annual_value", 0), "end_date": r.get("end_date"),
    } for r in rows]}


@router.get("/ai/contracts/{contract_id}/context")
async def ai_contract_context(contract_id: str, user=Depends(get_crm_user)):
    """The deterministic fact sheet the assistant is grounded on (for preview)."""
    of = _of(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    facts = await _contract_fact_sheet(_org(user), contract)
    return {"facts": facts, "generated_at": _now()}


@router.post("/ai/assistant")
async def ai_assistant(body: AfsAiIn, user=Depends(get_crm_user)):
    """Deterministic-grounded assistant: coverage summary, customer-email draft
    or grounded Q&A. Figures come only from the contract fact sheet."""
    if body.mode not in ("summary", "email", "question"):
        raise HTTPException(400, "mode must be summary, email or question")
    of = _of(user)
    contract = await db.crm2_contracts.find_one({"id": body.contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI assistant is not configured (missing LLM key).")

    facts = await _contract_fact_sheet(_org(user), contract)
    facts_text = _facts_to_text(facts)

    if body.mode == "summary":
        task = ("Write a concise plain-English summary of this maintenance contract's coverage for the "
                "coordinator: the package and what it covers, the equipment covered, service commitments, "
                "billing and term, any RPI review status, and a short note on recent service history "
                "(recent cases / faults) if any are present. Keep it factual and skimmable.")
    elif body.mode == "email":
        brief = _EMAIL_BRIEFS.get((body.email_type or "general"), _EMAIL_BRIEFS["general"])
        extra = f"\nAdditional instruction from the coordinator: {body.instruction.strip()}" if (body.instruction or "").strip() else ""
        task = (brief + extra + "\nStart with a 'Subject:' line, then the email body. Address the customer "
                "politely, sign off as the Pulse Fitness Aftersales team, and keep it professional and warm.")
    else:  # question
        q = (body.question or "").strip()
        if not q:
            raise HTTPException(400, "Please provide a question.")
        task = (f"Answer the coordinator's question using only the contract facts. If the facts don't contain "
                f"the answer, say so.\n\nQuestion: {q}")

    prompt = f"CONTRACT FACTS:\n{facts_text}\n\n---\nTASK:\n{task}"

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"afs_ai_{body.contract_id}_{uuid.uuid4().hex[:8]}",
            system_message=_AI_SYSTEM,
        ).with_model("anthropic", "claude-sonnet-4-6")
        text = (await chat.send_message(UserMessage(text=prompt))).strip()
    except Exception as e:
        raise HTTPException(502, f"AI generation failed: {e}")

    await record_audit(entity_type="afs_ai_assistant", entity_id=body.contract_id, action=body.mode, user=user,
                       extra={"email_type": body.email_type, "has_question": bool(body.question)})
    return {"text": text, "mode": body.mode, "email_type": body.email_type,
            "facts": facts, "generated_at": _now()}



async def _contract_customer_email(contract, of):
    """Best-effort resolve a customer contact for a contract — company primary
    contact first, then the linked operations org owner. UI can override."""
    cid = contract.get("company_id")
    if cid:
        co = await db.crm2_companies.find_one({"id": cid, **of}, {"_id": 0})
        if co:
            for k in ("primary_contact_email", "contact_email", "email"):
                v = (co.get(k) or "").strip()
                if "@" in v:
                    return v, (co.get("primary_contact_name") or co.get("name") or "")
            for ct in (co.get("contacts") or []):
                v = (ct.get("email") or "").strip()
                if "@" in v:
                    return v, ct.get("name") or ""
    linked = contract.get("linked_organization_id")
    if linked:
        owner = await db.users.find_one(
            {"organization_id": linked, "role": {"$in": ["owner", "org_owner"]}},
            {"_id": 0, "email": 1, "full_name": 1})
        if owner and "@" in (owner.get("email") or ""):
            return owner["email"], owner.get("full_name") or ""
    return "", ""


def _text_to_html(text):
    """Turn a plain-text email draft into simple branded HTML (paragraphs +
    bullet lists). send_email() adds the Pulse branded header/footer."""
    import html as _h
    out, bullets = [], []

    def flush():
        if bullets:
            out.append("<ul style='margin:8px 0;padding-left:20px'>"
                       + "".join(f"<li>{_h.escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for ln in (text or "").split("\n"):
        s = ln.strip()
        if not s:
            flush()
            continue
        if s.startswith(("- ", "* ", "• ")):
            bullets.append(s[2:].strip())
        else:
            flush()
            out.append(f"<p style='margin:10px 0'>{_h.escape(s)}</p>")
    flush()
    return "".join(out)


class AfsAiSendIn(BaseModel):
    contract_id: str
    subject: str
    body: str
    to_email: Optional[str] = None
    to_name: Optional[str] = None


@router.post("/ai/assistant/send-email")
async def ai_assistant_send(body: AfsAiSendIn, user=Depends(get_crm_user)):
    """Send an AI-drafted customer email via the branded Resend flow. Preview
    uses a test key so delivery shows 'failed' but the send TRIGGERS + AUDITS;
    real delivery happens in production."""
    of = _of(user)
    contract = await db.crm2_contracts.find_one({"id": body.contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    email = (body.to_email or "").strip()
    name = (body.to_name or "").strip()
    if "@" not in email:
        email, resolved_name = await _contract_customer_email(contract, of)
        name = name or resolved_name
    if "@" not in email:
        raise HTTPException(400, "A customer email address is required to send this email.")
    text_body = (body.body or "").strip()
    if not text_body:
        raise HTTPException(400, "The email body is empty.")
    subject = (body.subject or "").strip() or f"Your Pulse Fitness maintenance contract — {contract.get('contract_number')}"
    html = _text_to_html(text_body)

    from utils.email import send_email
    sent = await send_email(email, subject, html, organization_id=_org(user),
                            category="service", kind="afs_ai_email")
    await record_audit(entity_type="afs_ai_assistant", entity_id=body.contract_id, action="send_email",
                       user=user, extra={"to": email, "sent": bool(sent), "subject": subject})
    return {"sent": bool(sent), "to": email, "subject": subject}


# ── Milestone 1: approved terms, customer e-signature, welcome pack ──────

@router.get("/terms")
async def list_terms(user=Depends(require_crm_perm("agreements.process"))):
    rows = await db.crm2_afs_terms.find(_of(user), _PUBLIC).sort("uploaded_at", -1).to_list(50)
    approved = next((t for t in rows if t["status"] == "approved"), None)
    return {"terms": rows, "approved": approved}


@router.post("/terms")
async def upload_terms(version: str = Query(..., min_length=1), file: UploadFile = File(...),
                       user=Depends(require_crm_perm("exceptions.approve"))):
    from utils.cm_agreements import store_terms
    name = file.filename or "terms"
    if not name.lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "Upload the Terms & Conditions as a PDF or Word (.docx) file.")
    data = await file.read()
    if not data or len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File is empty or larger than 15 MB.")
    if name.lower().endswith(".pdf") and not data.startswith(b"%PDF"):
        raise HTTPException(400, "This file is not a valid PDF.")
    t = await store_terms(_org(user), version, name, data, user.get("email"))
    await record_audit(entity_type="afs_terms", entity_id=t["id"], action="upload", user=user,
                       extra={"version": version, "sha256": t["sha256"]})
    return t


@router.post("/terms/{terms_id}/approve")
async def approve_terms_version(terms_id: str, user=Depends(require_crm_perm("exceptions.approve"))):
    from utils.cm_agreements import approve_terms
    t = await approve_terms(_org(user), terms_id, user.get("email"))
    if t.get("error"):
        raise HTTPException(*t["error"])
    await record_audit(entity_type="afs_terms", entity_id=terms_id, action="approve", user=user,
                       extra={"version": t["version"], "sha256": t["sha256"]})
    return t


@router.get("/terms/{terms_id}/file")
async def terms_file(terms_id: str, user=Depends(require_crm_perm("agreements.process"))):
    from utils.cm_agreements import load_object
    t = await db.crm2_afs_terms.find_one({"id": terms_id, **_of(user)}, _PUBLIC)
    if not t:
        raise HTTPException(404, "Terms not found")
    await db.crm2_afs_terms.update_one({"id": terms_id}, {"$push": {"inspections": {"by": user.get("email"), "at": _now()}}})
    pdf = t.get("file_type", "pdf") == "pdf"
    return Response(await load_object(t["storage_path"]),
                    media_type="application/pdf" if pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'{"inline" if pdf else "attachment"}; filename="Terms-{t["version"]}.{"pdf" if pdf else "docx"}"'})


class TermsReviewIn(BaseModel):
    reason: str


@router.post("/terms/{terms_id}/flag-review")
async def flag_terms_review(terms_id: str, body: TermsReviewIn, user=Depends(require_crm_perm("exceptions.approve"))):
    """Mark a PDF as needing review (e.g. differs from the Word original). An approved
    version flagged here stops being issued until a reviewed version is approved."""
    t = await db.crm2_afs_terms.find_one({"id": terms_id, **_of(user)}, _PUBLIC)
    if not t or t.get("file_type", "pdf") != "pdf":
        raise HTTPException(404, "PDF terms not found")
    if not body.reason.strip():
        raise HTTPException(400, "Explain what needs reviewing")
    await db.crm2_afs_terms.update_one({"id": terms_id}, {"$set": {
        "status": "requires_review", "review_reason": body.reason.strip(), "flagged_by": user.get("email"),
        "flagged_at": _now(), "previous_status": t["status"]}})
    await record_audit(entity_type="afs_terms", entity_id=terms_id, action="flag_review", user=user,
                       extra={"reason": body.reason.strip()})
    return {"status": "requires_review"}


@router.get("/agreements/{agreement_id}/document")
async def agreement_document(agreement_id: str, user=Depends(require_crm_perm("contracts.read"))):
    """The exact signed / issued document, or a preview of the draft."""
    from utils.cm_agreements import approved_terms, compose_pdf, load_object
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **_of(user)}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    d = ag.get("signed_document") or ag.get("document")
    if d:
        pdf = await load_object(d["storage_path"])
    else:
        pdf = await compose_pdf(ag, await approved_terms(_org(user)), 0)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{ag.get("agreement_number")}.pdf"'})


class SendForSignatureIn(BaseModel):
    signatory_name: str
    email: str


@router.post("/agreements/{agreement_id}/send-for-signature")
async def send_for_signature(agreement_id: str, body: SendForSignatureIn,
                             user=Depends(require_crm_perm("agreements.process"))):
    """Freeze the document, issue a 14-day personal link and email it.
    Re-sending issues a fresh link (the previous one stops working)."""
    from utils import cm_agreements as cma
    of, org_id = _of(user), _org(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    if ag.get("status") not in ("ready", "sent", "viewed"):
        raise HTTPException(400, "Generate the agreement (all readiness checks passed) before sending for signature.")
    health = _agreement_health(ag)
    if not health["ready"]:
        raise HTTPException(400, {"message": "Agreement not ready", "reasons": health["reasons"]})
    email = (body.email or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or not body.signatory_name.strip():
        raise HTTPException(400, "Enter the customer signatory's name and a valid email address.")
    terms = await cma.approved_terms(org_id)
    if not terms:
        await cma.raise_terms_missing(org_id)
        raise HTTPException(409, {"code": "terms_not_approved",
                                  "message": "No approved Terms & Conditions — an administrator must upload and approve them first."})
    claim = await db.crm2_afs_agreements.find_one_and_update(
        {"id": agreement_id, **of, "signature_sending": {"$ne": True}},
        {"$set": {"signature_sending": True}})
    if not claim:
        raise HTTPException(409, "A signature request is already being sent — refresh in a moment.")
    try:
        doc = ag.get("document")
        if not doc or doc.get("terms_id") != terms["id"]:
            doc = await cma.freeze_document(org_id, ag, terms)
        token, req = cma.new_link(doc, email, body.signatory_name.strip())
        base = os.environ.get("PUBLIC_APP_URL") or os.environ.get("FRONTEND_URL") or ""
        url = f"{base.rstrip('/')}/as/{token}"
        delivery = await cma.deliver_signature_email(org_id, ag, req, url)
        req.update(delivery)
        req["events"] = [{"at": _now(), "event": "issued", "by": user.get("email")},
                         {"at": _now(), "event": f"email_{delivery['delivery_status']}"}]
        prev = ag.get("signature_request")
        history = (ag.get("signature_history") or []) + ([{**prev, "revoked": True, "superseded_at": _now()}] if prev else [])
        tl = ag.get("timeline", []) + [{"at": _now(), "by": user.get("email"), "event":
              f"Sent for signature to {email} (document v{doc['version']}) — "
              + ("accepted by email provider" if delivery["delivery_status"] == "accepted_by_provider" else "EMAIL NOT DELIVERED")}]
        await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
            "status": "sent", "document": doc, "signature_request": req, "signature_history": history,
            "timeline": tl, "updated_at": _now()}})
    finally:
        await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$unset": {"signature_sending": ""}})
    out = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    await _agreement_step_action(org_id, out)
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="send_for_signature", user=user,
                       extra={"to": email, "document_version": doc["version"], "delivery": delivery["delivery_status"]})
    return {"status": "sent", "link": url, "path": f"/as/{token}", "expires_at": req["expires_at"],
            "delivery_status": delivery["delivery_status"], "document_version": doc["version"],
            "document_hash": doc["sha256"]}


@router.post("/agreements/{agreement_id}/signature-link/revoke")
async def revoke_signature_link(agreement_id: str, user=Depends(require_crm_perm("agreements.process"))):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag or not ag.get("signature_request"):
        raise HTTPException(404, "No signature link to revoke")
    if ag.get("status") not in ("sent", "viewed"):
        raise HTTPException(400, "Only an outstanding signature link can be revoked.")
    tl = ag.get("timeline", []) + [{"at": _now(), "event": "Signature link revoked", "by": user.get("email")}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "signature_request.revoked": True, "signature_request.revoked_at": _now(), "status": "ready",
        "timeline": tl, "updated_at": _now()}})
    await _agreement_step_action(_org(user), {**ag, "status": "ready"})
    return {"revoked": True}


@router.post("/contracts/{contract_id}/welcome-pack")
async def resend_welcome_pack(contract_id: str, user=Depends(require_crm_perm("agreements.process"))):
    from utils.cm_agreements import send_welcome_pack
    res = await send_welcome_pack(_org(user), contract_id, actor=user.get("email"), reissue=True)
    if res.get("status") == "skipped":
        raise HTTPException(400, res.get("detail"))
    await record_audit(entity_type="contract", entity_id=contract_id, action="welcome_pack", user=user,
                       extra={"status": res.get("status")})
    return res


@router.post("/agreements/{agreement_id}/signed-document/retry")
async def retry_signed_document(agreement_id: str, user=Depends(require_crm_perm("agreements.process"))):
    from utils.cm_agreements import store_signed_copy, try_auto_activate
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **_of(user)}, _PUBLIC)
    if not ag or (ag.get("signature") or {}).get("method") != "customer_esignature":
        raise HTTPException(404, "No customer e-signature on this agreement")
    if (ag.get("signed_document") or {}).get("status") != "verified":
        if not await store_signed_copy(_org(user), agreement_id):
            raise HTTPException(502, "Signed agreement still could not be stored — try again shortly.")
    activation = {"activated": False}
    if ag.get("status") == "signed":
        activation = await try_auto_activate(_org(user), agreement_id)
    return {"stored": True, "activation": activation}


# ── Build Quote: start from a sales invoice / delivery note / maintenance invoice ──

# Equipment lifecycle for machines first seen on a document. None of these is
# "installed": status stays pending_installation until an authorised installation
# confirmation (equipment PATCH install_date by owner/manager, or commissioning).
PENDING_INSTALL_STAGES = ("identified_from_invoice", "delivered", "verification_required")
IMPORT_STAGE = {"sales_invoice": "identified_from_invoice", "delivery_note": "delivered",
                "maintenance_invoice": "verification_required"}
STAGE_RANK = {"verification_required": 1, "identified_from_invoice": 1, "delivered": 2, "installed": 3}

AFS_IMPORT_MAX_BYTES = int(os.environ.get("AFS_IMPORT_MAX_MB", "50")) * 1024 * 1024


@router.post("/build-quote/imports")
async def create_quote_import(doc_type: str = Form(...), company_id: str = Form(""), file: UploadFile = File(...),
                              user=Depends(require_crm_perm("quotes.maintenance"))):
    """Small direct upload (kept for compatibility). Large documents use /build-quote/imports/from-file."""
    return await _create_import(user, doc_type, company_id, await file.read(), file.filename)


class ImportFromFileIn(BaseModel):
    file_id: str
    doc_type: str
    company_id: str = ""


@router.post("/build-quote/imports/from-file")
async def create_quote_import_from_file(body: ImportFromFileIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Start reading a document already uploaded in ~1 MB pieces via /files/upload/chunks (org-scoped file id).
    Reading runs in the background (large files take minutes) — poll GET /build-quote/jobs/{job_id}."""
    fdoc = await _org_file(body.file_id, user)
    from utils import cm_quote_import as qi
    if body.doc_type not in qi.DOC_TYPES:
        raise HTTPException(400, "Choose sales invoice, delivery note or maintenance invoice.")
    prior = await db.crm2_afs_quote_imports.find_one({**_of(user), "sha256": fdoc.get("content_hash"), "doc_type": body.doc_type}, _PUBLIC)
    if prior:
        return {"job_id": None, "status": "done", "import": {**prior, "existing": True}}

    async def work():
        from utils.database import get_object
        data, _ct = get_object(fdoc["storage_path"])
        doc = await _create_import(user, body.doc_type, body.company_id, data,
                                   fdoc.get("original_filename") or "document.pdf", file_id=fdoc["id"])
        return {"import_id": doc["id"]}
    return await _start_job(user, "import", f"{fdoc.get('content_hash')}:{body.doc_type}", work)


@router.post("/extract-pricing-jobs")
async def start_pricing_extraction(file_id: str = Query(...), user=Depends(require_crm_perm("quotes.maintenance"))):
    """Background version of /extract-pricing-document for large tenders — poll GET /build-quote/jobs/{job_id}."""
    fdoc = await _org_file(file_id, user)
    if (fdoc.get("size") or 0) > AFS_IMPORT_MAX_BYTES:
        raise HTTPException(413, f"The document is larger than {AFS_IMPORT_MAX_BYTES // (1024 * 1024)} MB.")

    async def work():
        return await extract_pricing_document(file=None, file_id=file_id, user=user)
    return await _start_job(user, "pricing", f"{fdoc.get('content_hash')}:pricing", work)


@router.get("/build-quote/jobs/{job_id}")
async def doc_job_status(job_id: str, user=Depends(require_crm_perm("quotes.maintenance"))):
    j = await db.crm2_afs_doc_jobs.find_one({"id": job_id, "organization_id": _org(user)}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] == "running" and j.get("started_at", "") < (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat():
        await db.crm2_afs_doc_jobs.update_one({"id": job_id, "status": "running"}, {"$set": {"status": "failed", "error": "Processing was interrupted — please try again"}})
        j = {**j, "status": "failed", "error": "Processing was interrupted — please try again"}
    if j["status"] == "done" and j["kind"] == "import":
        j["import"] = await db.crm2_afs_quote_imports.find_one({"id": j["result"]["import_id"], **_of(user)}, _PUBLIC)
    return j


async def _org_file(file_id: str, user: dict) -> dict:
    fdoc = await db.files.find_one({"id": file_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not fdoc:
        raise HTTPException(404, "Uploaded file not found")
    return fdoc


_DOC_TASKS: set = set()


async def _start_job(user: dict, kind: str, dedupe: str, work) -> dict:
    """One active job per document (repeat clicks return the same job); the work runs after the response."""
    active = await db.crm2_afs_doc_jobs.find_one({"organization_id": _org(user), "dedupe": dedupe, "status": {"$in": ["queued", "running"]}}, {"_id": 0})
    if active:
        return {"job_id": active["id"], "status": active["status"]}
    jid = _id()
    await db.crm2_afs_doc_jobs.insert_one({"id": jid, "organization_id": _org(user), "kind": kind, "dedupe": dedupe,
                                          "status": "running", "created_by": user.get("email"), "created_at": _now(), "started_at": _now()})

    async def runner():
        try:
            res = await work()
            await db.crm2_afs_doc_jobs.update_one({"id": jid}, {"$set": {"status": "done", "result": res, "finished_at": _now()}})
        except HTTPException as e:
            await db.crm2_afs_doc_jobs.update_one({"id": jid}, {"$set": {"status": "failed", "error": str(e.detail), "finished_at": _now()}})
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).exception("[afs-doc-job] %s failed", jid)
            await db.crm2_afs_doc_jobs.update_one({"id": jid}, {"$set": {"status": "failed", "error": "The document could not be processed",
                                                                        "diagnostic": f"{type(e).__name__}: {str(e)[:300]}", "finished_at": _now()}})
    t = asyncio.create_task(runner())
    _DOC_TASKS.add(t)
    t.add_done_callback(_DOC_TASKS.discard)
    return {"job_id": jid, "status": "running"}


async def _create_import(user: dict, doc_type: str, company_id: str, data: bytes, filename: str, file_id: str | None = None):
    """Store the source document, extract it once (same file → same import), recognise
    the existing customer and match every machine. Nothing is priced or created yet."""
    from utils import cm_quote_import as qi
    from utils.cm_agreements import _put
    if doc_type not in qi.DOC_TYPES:
        raise HTTPException(400, "Choose sales invoice, delivery note or maintenance invoice.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload the document as a PDF.")
    if len(data) > AFS_IMPORT_MAX_BYTES:
        raise HTTPException(413, f"The document is larger than {AFS_IMPORT_MAX_BYTES // (1024 * 1024)} MB.")
    of, org_id, digest = _of(user), _org(user), qi.sha256(data)
    prior = await db.crm2_afs_quote_imports.find_one({**of, "sha256": digest, "doc_type": doc_type}, _PUBLIC)
    if prior:
        return {**prior, "existing": True}
    iid = _id()
    path = f"pulse/afs-quote-sources/{org_id}/{iid}.pdf"
    await _put(path, data)
    extracted = await qi.extract_document(data, doc_type)
    if company_id:
        co = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0, "id": 1, "name": 1, "linked_organization_id": 1})
        if not co:
            raise HTTPException(404, "Customer not found")
        cust = {"status": "selected", "company": co, "basis": "chosen by coordinator", "candidates": []}
    else:
        cust = await qi.match_customer(org_id, extracted)
    linked = await _resolve_linked_org_for_company(cust["company"], user) if cust.get("company") else None
    lines = await qi.match_lines(org_id, extracted.get("lines") or [], doc_type, linked)
    doc = {"id": iid, "organization_id": org_id, "doc_type": doc_type, "filename": filename, "sha256": digest,
           "storage_path": path, "size": len(data), "file_id": file_id, "extracted": extracted,
           "coverage": extracted.pop("coverage", None), "customer": cust,
           "company_id": (cust.get("company") or {}).get("id"), "lines": lines, "summary": qi.summarise(lines),
           "status": "review",
           "created_by": user.get("email"), "created_at": _now(), "updated_at": _now()}
    await db.crm2_afs_quote_imports.insert_one(dict(doc))
    await record_audit(entity_type="afs_quote_import", entity_id=iid, action="create", user=user,
                       extra={"doc_type": doc_type, "lines": len(lines), "customer": cust["status"]})
    return doc


@router.get("/build-quote/imports/{import_id}")
async def get_quote_import(import_id: str, user=Depends(require_crm_perm("quotes.maintenance"))):
    doc = await db.crm2_afs_quote_imports.find_one({"id": import_id, **_of(user)}, _PUBLIC)
    if not doc:
        raise HTTPException(404, "Import not found")
    return doc


class ImportCustomerIn(BaseModel):
    company_id: str


@router.post("/build-quote/imports/{import_id}/customer")
async def set_import_customer(import_id: str, body: ImportCustomerIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    from utils import cm_quote_import as qi
    of = _of(user)
    imp = await db.crm2_afs_quote_imports.find_one({"id": import_id, **of}, _PUBLIC)
    co = await db.crm2_companies.find_one({"id": body.company_id, **of}, {"_id": 0, "id": 1, "name": 1, "linked_organization_id": 1})
    if not imp or not co:
        raise HTTPException(404, "Import or customer not found")
    if imp.get("quote_id"):
        raise HTTPException(400, f"Already used for quote {imp.get('quote_number')} — upload again for a different customer.")
    linked = await _resolve_linked_org_for_company(co, user)
    lines = await qi.match_lines(_org(user), (imp.get("extracted") or {}).get("lines") or [], imp["doc_type"], linked)
    cust = {**imp["customer"], "status": "selected", "company": co, "basis": "chosen by coordinator"}
    await db.crm2_afs_quote_imports.update_one({"id": import_id}, {"$set": {
        "customer": cust, "company_id": co["id"], "lines": lines, "summary": qi.summarise(lines), "updated_at": _now()}})
    return await db.crm2_afs_quote_imports.find_one({"id": import_id}, _PUBLIC)


class ImportLineDecision(BaseModel):
    line_no: int
    decision: str                       # accepted | excluded
    config_id: Optional[str] = None     # coordinator-chosen machine for unknown / ambiguous lines
    reuse_equipment_ids: List[str] = []  # coordinator-confirmed: these serial-less units ARE the machines on this line


class ImportApplyIn(BaseModel):
    site_id: str
    decisions: List[ImportLineDecision] = []


@router.post("/build-quote/imports/{import_id}/apply")
async def apply_quote_import(import_id: str, body: ImportApplyIn, user=Depends(require_crm_perm("quotes.maintenance"))):
    """Confirm the reviewed lines against the customer's existing equipment register.
    Existing serials are reused; new machines are created once (keyed per import line)."""
    of = _of(user)
    imp = await db.crm2_afs_quote_imports.find_one({"id": import_id, **of}, _PUBLIC)
    if not imp or not imp.get("company_id"):
        raise HTTPException(400, "Confirm the customer before applying the document.")
    co = await db.crm2_companies.find_one({"id": imp["company_id"], **of}, {"_id": 0})
    linked = await _resolve_linked_org_for_company(co, user)
    if not linked:
        raise HTTPException(400, "This customer is not linked to an operations organisation.")
    site = await db.sites.find_one({"id": body.site_id, "organization_id": linked}, {"_id": 0, "id": 1, "name": 1})
    if not site:
        raise HTTPException(400, "Choose one of the customer's sites.")
    dec = {d.line_no: d for d in body.decisions}
    lines, asset_ids, created, reused = imp["lines"], [], 0, 0
    for ln in lines:
        d = dec.get(ln["line_no"])
        decision = d.decision if d else ln["decision"]
        if decision not in ("accepted", "excluded"):
            raise HTTPException(400, f"Line {ln['line_no']} ({ln.get('model') or ln.get('item_code')}) still needs a decision.")
        if d and d.config_id:
            cfg = await db.crm2_afs_service_configs.find_one({"id": d.config_id, **of}, _PUBLIC)
            if not cfg:
                raise HTTPException(400, f"Line {ln['line_no']}: machine not found")
            if decision == "accepted" and cfg.get("contract_eligible") is False:
                raise HTTPException(400, f"Line {ln['line_no']}: {cfg.get('model')} is not eligible for maintenance — exclude it.")
            ln["matched"] = {"config_id": cfg["id"], "model": cfg.get("model"), "console_type": cfg.get("console_type") or "",
                             "reference_sku": cfg.get("reference_sku"), "basis": "chosen by coordinator"}
        ln["decision"], ln["decided_by"] = decision, (user.get("email") if d else "auto")
        if decision == "excluded":
            continue
        if "already_covered" in ln.get("flags", []):
            raise HTTPException(400, f"Line {ln['line_no']} is already under an active contract — exclude it.")
        if "unsupported" in ln.get("flags", []):
            raise HTTPException(400, f"Line {ln['line_no']} is not eligible for maintenance — exclude it or refer it for a supportability decision.")
        if not ln.get("matched"):
            raise HTTPException(400, f"Line {ln['line_no']} needs a machine chosen before it can be included.")
    stage = IMPORT_STAGE[imp["doc_type"]]
    ref = (imp.get("extracted") or {}).get("document_ref")
    evidence = {"import_id": import_id, "doc_type": imp["doc_type"], "document_ref": ref,
                "document_date": (imp.get("extracted") or {}).get("document_date"), "sha256": imp["sha256"]}
    # One apply at a time per document (a stale lock older than 2 minutes is ignored).
    stale = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    lock = await db.crm2_afs_quote_imports.update_one(
        {"id": import_id, "$or": [{"applying_at": {"$exists": False}}, {"applying_at": None}, {"applying_at": {"$lt": stale}}]},
        {"$set": {"applying_at": _now()}})
    if not lock.modified_count:
        raise HTTPException(409, "This document is already being applied — refresh in a moment.")
    try:
        created, reused, asset_ids, review = await _apply_import_lines(
            imp, lines, dec, linked, site, stage, ref, evidence)
    finally:
        await db.crm2_afs_quote_imports.update_one({"id": import_id}, {"$set": {"applying_at": None}})
    if review:
        from utils.cm_actions import raise_action
        await raise_action(_org(user), f"import:{import_id}:serialless", type_="equipment_verification",
                           subject=f"Confirm serial-less machines: {ref or imp.get('filename') or 'document'}",
                           body=f"{co.get('name')}: {len(review)} machine(s) without serial numbers may already be on the "
                                "register from an earlier document. They were kept as separate provisional records — "
                                "confirm whether they are the same physical machines before quoting.",
                           contract={"company_id": co["id"]}, extra={"import_id": import_id, "candidates": review})
    await db.crm2_afs_quote_imports.update_one({"id": import_id}, {"$set": {
        "lines": lines, "site_id": site["id"], "asset_ids": asset_ids, "status": "applied", "updated_at": _now()}})
    return {"import_id": import_id, "company_id": co["id"], "company_name": co.get("name"), "site_ids": [site["id"]],
            "asset_ids": asset_ids, "equipment_created": created, "equipment_reused": reused,
            "possible_duplicates": review,
            "document_ref": (imp.get("extracted") or {}).get("document_ref"), "doc_type": imp["doc_type"]}


async def _claim_equipment(key: str, eq: dict) -> dict:
    """Create the machine once per claim key; a concurrent loser gets the winner's record."""
    from pymongo.errors import DuplicateKeyError
    try:
        await db.crm2_afs_equipment_claims.insert_one({"key": key, "equipment_id": eq["id"], "created_at": _now()})
    except DuplicateKeyError:
        import asyncio
        won = await db.crm2_afs_equipment_claims.find_one({"key": key}, {"_id": 0})
        for _ in range(40):  # the winner inserts its record right after claiming
            got = await db.equipment.find_one({"id": won["equipment_id"]}, {"_id": 0})
            if got:
                return {**got, "_reused": True}
            await asyncio.sleep(0.05)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        took = await db.crm2_afs_equipment_claims.update_one(  # orphaned claim (creator failed) — take it over
            {"key": key, "equipment_id": won["equipment_id"], "created_at": {"$lt": stale}},
            {"$set": {"equipment_id": eq["id"], "created_at": _now()}})
        if took.modified_count:
            await db.equipment.insert_one(dict(eq))
            return eq
        raise HTTPException(409, "Another document is creating this machine — try again in a moment.")
    await db.equipment.insert_one(dict(eq))
    return eq


async def _apply_import_lines(imp, lines, dec, linked, site, stage, ref, evidence):
    """Existing serials are reused; serial-less units are only reused for the same
    document line or when the coordinator confirms them — never merged on model+site."""
    await db.crm2_afs_equipment_claims.create_index("key", unique=True)
    import_id = imp["id"]
    asset_ids, created, reused, review, claimed = [], 0, 0, [], set()
    for ln in lines:
        if ln["decision"] == "excluded":
            continue
        m = ln["matched"]
        d = dec.get(ln["line_no"])
        confirmed = list((d.reuse_equipment_ids if d else []) or [])
        for k in range(ln["quantity"]):
            serial = ln["serials"][k] if k < len(ln["serials"]) else ""
            key = f"{import_id}:{ln['line_no']}:{k}"
            eq = await db.equipment.find_one({"organization_id": linked, "serial_number": serial}, {"_id": 0}) if serial \
                else await db.equipment.find_one({"organization_id": linked, "source_import_line": key}, {"_id": 0})
            if not eq and not serial and confirmed:
                eq = await db.equipment.find_one(
                    {"organization_id": linked, "site_id": site["id"], "id": confirmed.pop(0),
                     "serial_number": {"$in": [None, ""]}, "lifecycle_stage": {"$in": list(PENDING_INSTALL_STAGES)}},
                    {"_id": 0})
                if not eq:
                    raise HTTPException(400, f"Line {ln['line_no']}: the confirmed machine is not an unverified serial-less unit at this site.")
            if eq and eq["id"] in claimed:
                raise HTTPException(400, f"Line {ln['line_no']}: the same machine cannot be used twice in one document.")
            if not eq and not serial:
                cands = await db.equipment.find(
                    {"organization_id": linked, "site_id": site["id"], "model": m.get("model"),
                     "serial_number": {"$in": [None, ""]}, "lifecycle_stage": {"$in": list(PENDING_INSTALL_STAGES)},
                     "source_import_line": {"$not": {"$regex": f"^{re.escape(import_id)}:"}}},
                    {"_id": 0, "id": 1, "source_document_ref": 1, "lifecycle_stage": 1}).to_list(50)
                if cands:
                    review.append({"line_no": ln["line_no"], "unit": k + 1, "model": m.get("model"),
                                   "candidates": [c["id"] for c in cands],
                                   "candidate_documents": sorted({c.get("source_document_ref") or "" for c in cands})})
            if eq:
                reused += 1
                upd = {"$addToSet": {"source_evidence": evidence}, "$set": {"updated_at": _now()}}
                if STAGE_RANK.get(stage, 0) > STAGE_RANK.get(eq.get("lifecycle_stage"), 99):
                    upd["$set"]["lifecycle_stage"] = stage       # forward only; verified/active kit untouched
                await db.equipment.update_one({"id": eq["id"]}, upd)
            else:
                new = {"id": _id(), "organization_id": linked, "site_id": site["id"], "location": site["name"],
                       "name": m.get("model") or ln.get("model"), "model": m.get("model"),
                       "console_type": m.get("console_type") or "", "manufacturer": ln.get("make") or "",
                       "serial_number": serial, "status": "pending_installation", "lifecycle_stage": stage,
                       "install_verified": False, "install_date": None, "warranty_expiry": None,
                       "source": "quote_import", "source_import_line": key, "source_doc_type": imp["doc_type"],
                       "source_document_ref": ref, "source_evidence": [evidence],
                       "item_code": ln.get("item_code"), "created_at": _now(), "updated_at": _now()}
                eq = await _claim_equipment(f"{linked}:sn:{serial}" if serial else f"{linked}:line:{key}", new)
                if eq.pop("_reused", False):
                    reused += 1
                else:
                    created += 1
            claimed.add(eq["id"])
            asset_ids.append(eq["id"])
    return created, reused, asset_ids, review
