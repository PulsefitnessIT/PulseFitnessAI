"""Equipment coverage resolver.

Iter 216h199 — Phase 3 of Ops↔CRM↔ServiceDesk link. A single function
that, given an equipment row + database handle, returns the resolved
coverage state (manufacturer warranty + CRM aftersales contract). Used by:

  • GET /api/equipment/{id}/coverage (Operations Equipment Detail panel)
  • Service Desk case intake (auto-warranty-check at ticket creation)

By centralising the logic here we guarantee the three modules
(Operations, CRM, Service Desk) never disagree about whether a piece of
equipment is in-warranty / under contract.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional


def _parse_iso(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return None


def _days_until(date_str: Optional[str]) -> Optional[int]:
    """Days until `date_str` (YYYY-MM-DD or ISO). None if unparseable."""
    parsed = _parse_iso(date_str)
    if not parsed:
        return None
    return (parsed - datetime.now(timezone.utc)).days


async def resolve_equipment_coverage(equipment: dict, db) -> dict:
    """Resolve full coverage state for an equipment row.

    Returns a dict with:
      - has_crm_contract: bool — any active aftersales contract attached?
      - warranty_active: bool — manufacturer warranty still in date?
      - warranty_expiry: str | None
      - warranty_days_remaining: int | None
      - best: dict | None — highest-tier active contract (or None)
                            keys: contract_id, contract_number,
                            contract_title, tier, coverage_type,
                            start_date, end_date, exclusions,
                            expiring_soon (<90d), days_until_expiry
      - all_contracts: list[dict] — every active contract (sorted by tier desc)
      - cover_type: "warranty" | "contract" | "chargeable"
                     The flag Service Desk uses to route the case
                     (warranty = supplier callback, contract = our engineer,
                      chargeable = customer pays).
    """
    if not equipment:
        return _empty_coverage()

    equipment_id = equipment.get("id") or ""

    # Manufacturer warranty layer (lives on the equipment doc itself).
    warranty_expiry = equipment.get("warranty_expiry") or None
    warranty_parsed = _parse_iso(warranty_expiry)
    warranty_active = bool(
        warranty_parsed and warranty_parsed > datetime.now(timezone.utc)
    )
    warranty_days = None
    if warranty_active and warranty_parsed:
        warranty_days = (warranty_parsed - datetime.now(timezone.utc)).days

    # CRM aftersales contract layer.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff_90d = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")

    crm_rows: list[dict] = []
    if equipment_id:
        assets = await db.crm2_contract_assets.find(
            {"asset_id": equipment_id}, {"_id": 0},
        ).to_list(200)
        contract_ids = list({a.get("contract_id") for a in assets if a.get("contract_id")})
        if contract_ids:
            contracts = await db.crm2_contracts.find(
                {"id": {"$in": contract_ids}}, {"_id": 0},
            ).to_list(200)
        else:
            contracts = []
        contracts_by_id = {c.get("id"): c for c in contracts}

        try:
            from routes.crm_contracts import CONTRACT_TIERS as _TIERS
            tier_order = {t["id"]: i for i, t in enumerate(_TIERS)}
        except Exception:  # pragma: no cover
            tier_order = {}

        for a in assets:
            contract = contracts_by_id.get(a.get("contract_id"))
            if not contract:
                continue
            end = contract.get("end_date", "")
            if end and end < today:
                continue
            if contract.get("status") not in {"active", "signed", "expiring"}:
                continue
            crm_rows.append({
                "contract_id": contract.get("id"),
                "contract_number": contract.get("contract_number"),
                "contract_title": contract.get("title"),
                "tier": contract.get("tier"),
                "coverage_type": a.get("coverage_type", "full"),
                "start_date": contract.get("start_date"),
                "end_date": end,
                "exclusions": a.get("exclusions", ""),
                "expiring_soon": bool(end and end <= cutoff_90d),
                "days_until_expiry": _days_until(end),
                "_rank": tier_order.get(contract.get("tier", ""), -1),
            })
        crm_rows.sort(key=lambda r: (r["_rank"], r.get("end_date") or ""), reverse=True)

    best = dict(crm_rows[0]) if crm_rows else None
    if best:
        best.pop("_rank", None)
    for r in crm_rows:
        r.pop("_rank", None)

    has_crm_contract = bool(best)
    # Service-Desk routing flag. Contract beats warranty when both exist
    # (operators normally invoke the contract since it covers labour;
    # manufacturer warranty is parts-only most of the time).
    if has_crm_contract:
        cover_type = "contract"
    elif warranty_active:
        cover_type = "warranty"
    else:
        cover_type = "chargeable"

    return {
        "has_crm_contract": has_crm_contract,
        "warranty_active": warranty_active,
        "warranty_expiry": warranty_expiry,
        "warranty_days_remaining": warranty_days,
        "best": best,
        "all_contracts": crm_rows,
        "cover_type": cover_type,
    }


def _empty_coverage() -> dict:
    return {
        "has_crm_contract": False,
        "warranty_active": False,
        "warranty_expiry": None,
        "warranty_days_remaining": None,
        "best": None,
        "all_contracts": [],
        "cover_type": "chargeable",
    }


def coverage_to_case_meta(coverage: dict) -> dict:
    """Flatten the coverage dict into the keys that get stamped on
    `db.issues` rows AND propagated to `db.svc_cases` as
    `source_meta.coverage_*` — so the Service Desk UI can pre-fill the
    contract reference + show a "✓ In contract" badge at intake.

    Returns ALL keys (with sensible defaults) even when uncovered, so
    downstream code can rely on the shape.
    """
    best = coverage.get("best") or {}
    return {
        "cover_type": coverage.get("cover_type", "chargeable"),
        "coverage_status": (
            "covered_contract" if coverage.get("has_crm_contract")
            else "covered_warranty" if coverage.get("warranty_active")
            else "uncovered"
        ),
        "contract_id": best.get("contract_id") or "",
        "contract_number": best.get("contract_number") or "",
        "contract_title": best.get("contract_title") or "",
        "contract_tier": best.get("tier") or "",
        "contract_end_date": best.get("end_date") or "",
        "contract_coverage_type": best.get("coverage_type") or "",
        "contract_expiring_soon": bool(best.get("expiring_soon")),
        "warranty_active": coverage.get("warranty_active", False),
        "warranty_expiry": coverage.get("warranty_expiry"),
        "warranty_days_remaining": coverage.get("warranty_days_remaining"),
    }
