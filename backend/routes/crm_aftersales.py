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
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import re
import io
import os
import secrets

from utils.database import db, EMERGENT_LLM_KEY
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit

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
async def update_settings(body: SettingsUpdate, user=Depends(get_crm_user)):
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
async def update_rate_group(rg_id: str, body: RateGroupUpdate, user=Depends(get_crm_user)):
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
async def update_contract_type(ct_id: str, body: ContractTypeUpdate, user=Depends(get_crm_user)):
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
async def update_package(pkg_id: str, body: PackageUpdate, user=Depends(get_crm_user)):
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
async def update_service_config(cfg_id: str, body: ServiceConfigUpdate, user=Depends(get_crm_user)):
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
        health = "BLOCKED"; reasons.append("Customer required")
    if not has_site:
        health = "BLOCKED"; reasons.append("Site required")
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
        health = "BLOCKED"; reasons.append("Add at least one equipment line")

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
    {"id": "manual_review", "name": "Manual Review", "color": "#F97316"},
    {"id": "do_not_contract", "name": "Do Not Contract", "color": "#EF4444"},
    {"id": "third_party_review", "name": "Third-Party Review", "color": "#8B5CF6"},
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
async def upsert_supportability_decision(body: SupportabilityIn, user=Depends(get_crm_user)):
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
async def delete_supportability_decision(dec_id: str, user=Depends(get_crm_user)):
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
    manufacturer = (body.get("manufacturer") or "Pulse Fitness").strip()

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

    # Accepted quotes → agreement ready to generate.
    for q in await db.crm_quotes.find({**of, "status": "accepted"},
                                      {"_id": 0, "id": 1, "customer_name": 1, "company_name": 1, "total": 1}).to_list(50):
        items.append({
            "level": "ACTION", "kind": "agreement",
            "title": q.get("company_name") or q.get("customer_name") or "Customer",
            "detail": "Customer accepted quote — agreement ready to generate",
            "quote_id": q.get("id"), "value": q.get("total", 0), "sort": -1,
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
         "manufacturer": 1, "serial_number": 1, "site_id": 1, "warranty_expiry": 1}).to_list(5000)
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


@router.post("/build-quote-from-estate")
async def build_quote_from_estate(body: BuildFromEstateIn, user=Depends(get_crm_user)):
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
         "serial_number": 1, "site_id": 1, "warranty_expiry": 1}).to_list(5000)
    annotated = [await _annotate_asset(org_id, e) for e in equipment]
    if body.asset_ids:
        _wanted = set(body.asset_ids)
        annotated = [a for a in annotated if a.get("id") in _wanted]
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
        elif st == "PROVISIONAL":
            exceptions.append({"kind": "PROVISIONAL", "asset_id": a["id"], "model": a["model"],
                               "config_id": a["config_id"],
                               "detail": f"{a['model']} configuration still needs Aftersales approval."})

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

    if body.save:
        qid = _id()
        doc = {
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

    return auto


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
async def afs_quote_portal_link(quote_id: str, body: PortalLinkIn, user=Depends(get_crm_user)):
    """Mint (or reuse) a no-login customer acceptance link for an aftersales quote.
    Commercial customers only — MOD keeps its existing SOR portal flow."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
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
async def send_afs_quote_email(quote_id: str, body: SendQuoteEmailIn, user=Depends(get_crm_user)):
    """Email the customer their acceptance link (with the branded PDF attached).
    Commercial only. Mints a portal link if one doesn't exist yet."""
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
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
        f"style='background:#0B3D91;color:#fff;text-decoration:none;padding:12px 22px;"
        f"border-radius:10px;font-weight:700;display:inline-block'>Review &amp; respond to your quote</a></p>"
        f"<p style='color:#777;font-size:12px'>If the button doesn't work, paste this link into your browser:<br>{link}</p>")
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
        "name": s.get("name", "Pulse Fitness Ltd"),
        "address": s.get("address", "Pulse Fitness, Radbourne Road, Radbourne Park, Congleton, Cheshire, CW12 4XB"),
        "company_number": s.get("company_number", ""),
        "vat_number": s.get("vat_number", ""),
    }


def _service_contacts(settings):
    s = settings.get("service_contacts") or {}
    return {
        "service_email": s.get("service_email", "service@pulsefitness.com"),
        "service_phone": s.get("service_phone", "+44 (0)1260 294600"),
        "portal_url": s.get("portal_url", "https://portal.pulsefitness.com"),
        "parts_email": s.get("parts_email", "parts@pulsefitness.com"),
        "office_hours": s.get("office_hours", "Mon–Fri 08:30–17:00"),
    }


def _billing_schedule(annual, frequency, start_date, term_years):
    """Deterministic billing schedule from the authoritative contract value."""
    try:
        sd = datetime.strptime((start_date or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        sd = datetime.now(timezone.utc)
    rows = []
    freq = (frequency or "annual").lower()
    months = max(1, term_years) * 12
    if freq == "monthly":
        amt = round(annual / 12.0, 2)
        for m in range(months):
            due = sd + timedelta(days=30 * m)
            rows.append({"due_date": due.strftime("%Y-%m-%d"), "amount": amt, "status": "scheduled"})
    elif freq == "lump_sum":
        rows.append({"due_date": sd.strftime("%Y-%m-%d"), "amount": round(annual * max(1, term_years), 2), "status": "scheduled"})
    else:  # annual
        for y in range(max(1, term_years)):
            due = sd.replace(year=sd.year + y)
            rows.append({"due_date": due.strftime("%Y-%m-%d"), "amount": round(annual, 2), "status": "scheduled"})
    return rows


def _service_schedule(start_date, visits_per_year, term_years):
    try:
        sd = datetime.strptime((start_date or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        sd = datetime.now(timezone.utc)
    visits = max(1, int(visits_per_year or 1))
    interval = max(1, round(365 / visits))
    rows = []
    for y in range(max(1, term_years)):
        for v in range(visits):
            due = sd + timedelta(days=365 * y + interval * v)
            rows.append({"planned_date": due.strftime("%Y-%m-%d"), "status": "planned", "visit_no": v + 1, "year": y + 1})
    return rows


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


@router.post("/quotes/{quote_id}/accept")
async def accept_quote(quote_id: str, body: AcceptQuoteIn, user=Depends(get_crm_user)):
    of = _of(user)
    q = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not q:
        raise HTTPException(404, "Quote not found")
    await db.crm2_afs_quotes.update_one({"id": quote_id, **of}, {"$set": {
        "status": "accepted", "accepted_at": _now(),
        "accepted_by": body.accepted_by or user.get("email"), "updated_at": _now()}})
    await record_audit(entity_type="afs_quote", entity_id=quote_id, action="accept", user=user)
    return {"status": "accepted", "quote_id": quote_id}


class PrepareAgreementIn(BaseModel):
    start_date: str
    payment_method: str = "annual"          # monthly | annual | lump_sum
    billing_frequency: Optional[str] = None
    visits_per_year: int = 2


async def _insert_agreement_from_quote(org_id, quote, actor, *, start_date=None,
                                       payment_method="annual", billing_frequency=None,
                                       visits_per_year=2, timeline_note=None):
    """Shared: build + insert a DRAFT agreement from a saved quote. Idempotent —
    returns any existing non-cancelled agreement for the same quote. Used by the
    coordinator (prepare) and by public portal acceptance (auto-prep)."""
    of = {"organization_id": org_id}
    existing = await db.crm2_afs_agreements.find_one(
        {**of, "quote_id": quote["id"], "status": {"$nin": ["cancelled", "superseded"]}}, _PUBLIC)
    if existing:
        return existing
    doc = await _build_agreement_doc(org_id, quote)
    if start_date:
        sd = datetime.strptime(start_date[:10], "%Y-%m-%d")
        end = sd.replace(year=sd.year + max(1, doc["term_years"]))
        doc["start_date"] = sd.strftime("%Y-%m-%d")
        doc["end_date"] = end.strftime("%Y-%m-%d")
        doc["schedules"]["schedule2_agreement"]["start_date"] = doc["start_date"]
        doc["schedules"]["schedule2_agreement"]["end_date"] = doc["end_date"]
    doc["payment_method"] = payment_method
    doc["billing_frequency"] = billing_frequency or payment_method
    doc["visits_per_year"] = visits_per_year
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
    await db.crm2_afs_quotes.update_one({"id": quote["id"], **of}, {"$set": {"status": "agreement", "updated_at": _now()}})
    return await db.crm2_afs_agreements.find_one({"id": aid, **of}, _PUBLIC)


@router.post("/agreements/from-quote/{quote_id}")
async def prepare_agreement(quote_id: str, body: PrepareAgreementIn, user=Depends(get_crm_user)):
    of = _of(user)
    quote = await db.crm2_afs_quotes.find_one({"id": quote_id, **of}, _PUBLIC)
    if not quote:
        raise HTTPException(404, "Quote not found")
    existing = await db.crm2_afs_agreements.find_one(
        {**of, "quote_id": quote_id, "status": {"$nin": ["cancelled", "superseded"]}}, _PUBLIC)
    if existing:
        return existing
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


@router.patch("/agreements/{agreement_id}")
async def patch_agreement(agreement_id: str, body: AgreementPatchIn, user=Depends(get_crm_user)):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    patch = {}
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
    return await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)


@router.post("/agreements/{agreement_id}/generate")
async def generate_agreement(agreement_id: str, user=Depends(get_crm_user)):
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
    return {"status": "ready", "generated_at": _now(), "agreement_number": ag.get("agreement_number")}


class SignIn(BaseModel):
    signatory_name: str
    position: str
    email: str
    authority_confirmed: bool = False
    signature: Optional[str] = None          # typed name / data-url


@router.post("/agreements/{agreement_id}/sign")
async def sign_agreement(agreement_id: str, body: SignIn, user=Depends(get_crm_user)):
    of = _of(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    if ag.get("status") not in ("ready", "sent"):
        raise HTTPException(400, "Agreement must be generated (Ready) before signing")
    if not body.authority_confirmed:
        raise HTTPException(400, "Signatory must confirm they have authority to sign")
    sig = {
        "signatory_name": body.signatory_name, "position": body.position, "email": body.email,
        "signature": body.signature or body.signatory_name, "authority_confirmed": True,
        "signed_at": _now(), "tc_version": ag.get("tc_version"),
        "template_version": ag.get("template_version"),
    }
    tl = ag.get("timeline", []) + [{"at": _now(), "event": f"Signed by {body.signatory_name} ({body.position})", "by": body.email}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "status": "signed", "signature": sig, "signed_at": _now(), "timeline": tl, "updated_at": _now()}})
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="sign", user=user,
                       extra={"signatory": body.signatory_name})
    return {"status": "signed", "signature": sig}


@router.post("/agreements/{agreement_id}/activate")
async def activate_agreement(agreement_id: str, user=Depends(get_crm_user)):
    """CONTRACT ACTIVATION ENGINE (§65-71) — creates the live contract and runs
    the downstream automation, reusing existing collections. Never invents data;
    surfaces per-step status and preserves work on partial failure (§131)."""
    of = _of(user)
    org_id = _org(user)
    ag = await db.crm2_afs_agreements.find_one({"id": agreement_id, **of}, _PUBLIC)
    if not ag:
        raise HTTPException(404, "Agreement not found")
    if ag.get("status") not in ("signed", "activation_attention"):
        raise HTTPException(400, "Agreement must be signed before activation")

    steps = []

    # Duplicate contract guard (§67).
    dup = await db.crm2_contracts.find_one(
        {**of, "company_id": ag["company_id"], "status": {"$in": ["active", "signed"]},
         "source_agreement_id": {"$ne": agreement_id},
         "end_date": {"$gte": ag.get("start_date", "")}}, {"_id": 0, "id": 1, "contract_number": 1})
    if dup:
        steps.append({"step": "duplicate_check", "status": "warning",
                      "detail": f"Possible existing contract {dup.get('contract_number')} — review before activating"})
    else:
        steps.append({"step": "duplicate_check", "status": "ok"})

    # 1. Create/refresh the live contract record (reuse crm2_contracts schema).
    existing_contract = await db.crm2_contracts.find_one({**of, "source_agreement_id": agreement_id}, {"_id": 0, "id": 1})
    cid = existing_contract["id"] if existing_contract else _id()
    contract_doc = {
        "id": cid, "organization_id": org_id,
        "contract_number": ag.get("agreement_number"),
        "company_id": ag["company_id"], "company_name": ag.get("company_name"),
        "linked_organization_id": ag.get("linked_organization_id"),
        "title": ag["schedules"]["schedule2_agreement"]["agreement_type"],
        "type": "service", "tier": ag.get("contract_type"), "contract_type": ag.get("contract_type"),
        "annual_value": ag.get("annual_value", 0),
        "total_value": round(ag.get("annual_value", 0) * max(1, ag.get("term_years", 1)), 2),
        "start_date": ag.get("start_date"), "end_date": ag.get("end_date"),
        "billing_frequency": ag.get("billing_frequency", "annual"),
        "status": "active", "source": "aftersales",
        "source_agreement_id": agreement_id, "source_quote_id": ag.get("quote_id"),
        "pricing_version": ag.get("pricing_version"), "package_version": ag.get("package_version"),
        "tc_version": ag.get("tc_version"),
        "created_at": _now(), "updated_at": _now(), "activated_at": _now(),
    }
    await db.crm2_contracts.update_one({"id": cid, **of}, {"$set": contract_doc}, upsert=True)
    steps.append({"step": "contract_record", "status": "ok", "contract_id": cid})

    # 2. Link asset cover onto the operations equipment register (single source).
    linked = ag.get("linked_organization_id")
    asset_ids = [a["id"] for a in (ag.get("asset_register") or [])
                 if a.get("annual", 0) > 0 and a.get("id")]
    cover = {
        "contract_id": cid, "contract_number": ag.get("agreement_number"),
        "cover": ag.get("contract_type"), "start": ag.get("start_date"), "end": ag.get("end_date"),
    }
    if linked and asset_ids:
        res = await db.equipment.update_many(
            {"organization_id": linked, "id": {"$in": asset_ids}},
            {"$set": {"contract_cover": cover, "updated_at": _now()}})
        steps.append({"step": "asset_cover", "status": "ok", "assets_covered": res.modified_count})
    else:
        steps.append({"step": "asset_cover", "status": "skipped", "detail": "No priced assets to cover"})

    # 3. Preventative-maintenance / service schedule.
    svc = _service_schedule(ag.get("start_date"), ag.get("visits_per_year", 2), ag.get("term_years", 1))
    await db.crm2_afs_service_schedules.update_one(
        {"contract_id": cid, "organization_id": org_id},
        {"$set": {"contract_id": cid, "organization_id": org_id, "agreement_id": agreement_id,
                  "visits_per_year": ag.get("visits_per_year", 2), "visits": svc, "updated_at": _now()}},
        upsert=True)
    steps.append({"step": "service_schedule", "status": "ok", "visits": len(svc)})

    # 4. Billing schedule.
    bills = _billing_schedule(ag.get("annual_value", 0), ag.get("billing_frequency", "annual"),
                              ag.get("start_date"), ag.get("term_years", 1))
    await db.crm2_afs_billing.update_one(
        {"contract_id": cid, "organization_id": org_id},
        {"$set": {"contract_id": cid, "organization_id": org_id, "agreement_id": agreement_id,
                  "frequency": ag.get("billing_frequency", "annual"), "invoices": bills, "updated_at": _now()}},
        upsert=True)
    steps.append({"step": "billing_schedule", "status": "ok", "invoices": len(bills)})

    # 5. Direct Debit mandate flag.
    if ag.get("billing_frequency") == "monthly" and not ag.get("direct_debit_received"):
        steps.append({"step": "direct_debit", "status": "warning", "detail": "Direct Debit mandate outstanding"})
    else:
        steps.append({"step": "direct_debit", "status": "ok"})

    # 6. Queue Sicon / Sage synchronisation (reuse existing integrations — queued state).
    await db.crm2_contracts.update_one({"id": cid, **of}, {"$set": {
        "sicon_sync_status": "pending", "sage_sync_status": "pending", "updated_at": _now()}})
    steps.append({"step": "sicon_sync", "status": "queued", "detail": "Queued for Sicon Service sync"})
    steps.append({"step": "sage_sync", "status": "queued", "detail": "Queued for Sage 200 billing sync"})

    # Finalise agreement.
    tl = ag.get("timeline", []) + [{"at": _now(), "event": "Contract activated", "by": user.get("email")}]
    await db.crm2_afs_agreements.update_one({"id": agreement_id, **of}, {"$set": {
        "status": "active", "contract_id": cid, "activated_at": _now(),
        "activation_steps": steps, "timeline": tl, "updated_at": _now()}})
    await record_audit(entity_type="afs_agreement", entity_id=agreement_id, action="activate", user=user,
                       extra={"contract_id": cid})

    return {
        "status": "active", "contract_id": cid, "contract_number": ag.get("agreement_number"),
        "steps": steps,
        "service_visits": len(svc), "invoices": len(bills),
        "assets_covered": len(asset_ids),
    }


@router.get("/contracts/{contract_id}/schedules")
async def contract_schedules(contract_id: str, user=Depends(get_crm_user)):
    """Live contract compliance view — service + billing schedule (§71-75)."""
    of = _of(user)
    org_id = _org(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    svc = await db.crm2_afs_service_schedules.find_one({"contract_id": contract_id, "organization_id": org_id}, _PUBLIC)
    bill = await db.crm2_afs_billing.find_one({"contract_id": contract_id, "organization_id": org_id}, _PUBLIC)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    visits = (svc or {}).get("visits", [])
    return {
        "contract": {"id": contract_id, "contract_number": contract.get("contract_number"),
                     "status": contract.get("status"), "annual_value": contract.get("annual_value"),
                     "sicon_sync_status": contract.get("sicon_sync_status"),
                     "sage_sync_status": contract.get("sage_sync_status")},
        "service": {"visits": visits, "required": len(visits),
                    "completed": sum(1 for v in visits if v.get("status") == "completed"),
                    "next_due": next((v["planned_date"] for v in visits if v["planned_date"] >= today), None)},
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
         "serial_number": 1, "site_id": 1, "contract_cover": 1}).to_list(5000)
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
async def preview_amendment(contract_id: str, body: AmendmentIn, user=Depends(get_crm_user)):
    of = _of(user)
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, _PUBLIC)
    if not contract:
        raise HTTPException(404, "Contract not found")
    return await _compute_amendment(contract, _org(user), body)


@router.post("/contracts/{contract_id}/amendments")
async def apply_amendment(contract_id: str, body: AmendmentIn, user=Depends(get_crm_user)):
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

    # 4. Re-queue Sicon/Sage sync (value + cover changed).
    await db.crm2_contracts.update_one({"id": contract_id, **of}, {"$set": {
        "sicon_sync_status": "pending", "sage_sync_status": "pending"}})

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
    completed = sum(1 for v in visits if v.get("status") == "completed")
    overdue = sum(1 for v in visits
                  if v.get("status") != "completed" and (v.get("planned_date") or "") < today)
    upcoming = sorted((v.get("planned_date") for v in visits
                       if v.get("status") != "completed" and (v.get("planned_date") or "") >= today))
    state = "overdue" if overdue else ("complete" if completed >= len(visits) else "on_track")
    return {"has_schedule": True, "required": len(visits), "completed": completed,
            "overdue": overdue, "next_due": upcoming[0] if upcoming else None, "state": state}


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
            "annual_value": c.get("annual_value", 0),
            "start_date": c.get("start_date"), "end_date": c.get("end_date"),
            "billing_frequency": c.get("billing_frequency"),
            "service": service, "billing": billing,
            "sicon_sync_status": sicon, "sage_sync_status": sage,
        })
    return {"contracts": rows, "count": len(rows), "totals": totals, "generated_at": _now()}



# ══════════════════════════════════════════════════════════════════════════
# WARRANTY-TO-MAINTENANCE — revenue opportunity engine (§90-91)
# Turns every expiring Pulse warranty into a ready-made maintenance proposal.
# Live scan (no auto-contact); coordinator reviews and one-click builds a quote.
# ══════════════════════════════════════════════════════════════════════════

def _parse_dt(v):
    try:
        return datetime.fromisoformat((v or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


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
             "serial_number": 1, "site_id": 1, "warranty_expiry": 1, "contract_cover": 1}).to_list(5000)
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
async def build_warranty_proposal(company_id: str, body: WarrantyProposalIn, user=Depends(get_crm_user)):
    """One-click: build a maintenance proposal for a customer's warranty-expiring
    assets, reusing the SAME deterministic auto-quoter."""
    of = _of(user)
    org_id = _org(user)
    company = await db.crm2_companies.find_one({"id": company_id, **of}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    linked = await _resolve_linked_org_for_company(company, user)
    if not linked:
        raise HTTPException(400, "Company has no linked operations organisation.")
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, body.window_days))
    equipment = await db.equipment.find(
        {"organization_id": linked}, {"_id": 0, "id": 1, "warranty_expiry": 1, "contract_cover": 1}).to_list(5000)
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
    return {"reviews": rows, "due_count": sum(1 for r in rows if r["due"] and not (r["review"] or {}).get("status") == "approved")}


class RpiSetIn(BaseModel):
    rpi_pct: float
    source: str = "Manual entry"
    effective_date: Optional[str] = None


@router.post("/rpi/reviews/{contract_id}")
async def set_rpi_review(contract_id: str, body: RpiSetIn, user=Depends(get_crm_user)):
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
        doc["id"] = _id(); doc["created_at"] = _now()
        await db.crm2_afs_rpi_reviews.insert_one(doc)
    await record_audit(entity_type="afs_rpi", entity_id=doc["id"], action="propose", user=user,
                       extra={"contract": contract_id, "rpi_pct": body.rpi_pct, "proposed": proposed})
    return await db.crm2_afs_rpi_reviews.find_one({"id": doc["id"]}, _PUBLIC)


@router.post("/rpi/reviews/{review_id}/approve")
async def approve_rpi_review(review_id: str, user=Depends(get_crm_user)):
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
async def build_renewal(contract_id: str, body: RenewalBuildIn, user=Depends(get_crm_user)):
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
            "open_total": len(open_alerts),
            "unread_notifications": unread,
        },
    }


@router.post("/alerts/run")
async def run_afs_alerts(user=Depends(get_crm_user)):
    """Manual 'Run scan now' — same sweep the background worker runs, scoped to
    this org. Idempotent (dedupe_key prevents duplicates)."""
    from utils.afs_alerts import run_afs_alerts_once
    res = await run_afs_alerts_once(_org(user))
    await record_audit(entity_type="afs_alerts", entity_id="scan", action="run", user=user, extra=res)
    return res


@router.post("/quotes/chasers/run")
async def run_afs_quote_chasers(user=Depends(get_crm_user)):
    """Manual 'Run follow-ups now' — emails reminders to customers whose sent
    quotes are nearing expiry (Day 14/5 by default) and notifies the coordinator
    of any that expired unsigned. Idempotent per (quote, window)."""
    from utils.afs_alerts import run_quote_chasers_once
    res = await run_quote_chasers_once(_org(user))
    await record_audit(entity_type="afs_quote_chasers", entity_id="run", action="run", user=user, extra=res)
    return res


@router.post("/alerts/{activity_id}/dismiss")
async def dismiss_afs_alert(activity_id: str, user=Depends(get_crm_user)):
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
        return "£{:,.2f}".format(float(v or 0))
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
             "serial_number": 1, "contract_cover": 1}).to_list(5000)
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
