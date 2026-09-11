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
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import re

from utils.database import db
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
        }
    return s


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
    ready_activate = await db.crm2_contracts.count_documents({**of, "status": "signed"})

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
    contract_type: str = "gold"
    pricing_level: str = "standard"
    term_years: int = 1
    quote_discount_pct: float = 0.0
    save: bool = False


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

    # Exclude assets we must NOT price silently; price the rest.
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
            "status": "draft", "source": "auto_estate",
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
