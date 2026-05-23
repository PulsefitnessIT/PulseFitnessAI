"""The Pulse Score — a single 0-100 hero metric per site / org.

Iter 217 — Signature differentiator. No competitor has a one-number
operational pulse. We compose it from data we already collect:

    1. Fault freshness     — median age of currently-open issues
    2. Self-fix rate       — % of issues resolved on-base (no engineer call-out)
    3. Audit coverage      — % of machines with at least one check-sheet in last 7d
    4. Warranty health     — % of equipment in active warranty
    5. SLA adherence       — % of issues acknowledged within 24h

Each input lands as a 0-100 sub-score; the composite is a weighted mean.

The result is a single number the operator can read at a glance, with a
breakdown drawer that explains *why* it is what it is.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from utils.auth import get_current_user

router = APIRouter(prefix="/pulse-score", tags=["pulse-score"])

# Reuse the same Mongo connection pattern as every other module.
_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]


# ─── Weights ──────────────────────────────────────────────────────
# Tunable from a single place. Sum should equal 1.0. Picked to favour
# *current* operational health (freshness + SLA) over historical
# discipline (audit coverage + warranty) — which is what a duty
# manager actually cares about right now.
WEIGHTS: dict[str, float] = {
    "fault_freshness": 0.30,
    "self_fix_rate":   0.15,
    "audit_coverage":  0.20,
    "warranty_health": 0.10,
    "sla_adherence":   0.25,
}


def _clamp(v: float) -> int:
    """Snap a 0-100 float to int and clamp."""
    if v < 0:
        return 0
    if v > 100:
        return 100
    return int(round(v))


def _scope_filter(org_id: str, site_id: Optional[str]) -> dict[str, Any]:
    base: dict[str, Any] = {"organization_id": org_id}
    if site_id:
        base["site_id"] = site_id
    return base


async def _fault_freshness(scope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """100 = no open faults. Drops as median age of open faults grows.
    A 7-day median lands at ~77. A 30-day median lands at 0."""
    now = datetime.now(timezone.utc)
    flt = dict(scope)
    flt["status"] = {"$nin": ["closed", "resolved"]}
    cursor = _db["issues"].find(flt, {"created_at": 1, "_id": 0})
    ages_days: list[float] = []
    async for d in cursor:
        created = d.get("created_at")
        if not created:
            continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        ages_days.append((now - created).total_seconds() / 86400.0)

    if not ages_days:
        return 100, {"open_faults": 0, "median_age_days": 0}

    ages_days.sort()
    mid = len(ages_days) // 2
    median = ages_days[mid] if len(ages_days) % 2 else (ages_days[mid - 1] + ages_days[mid]) / 2
    score = _clamp(100 * (1 - median / 30.0))
    return score, {"open_faults": len(ages_days), "median_age_days": round(median, 1)}


async def _self_fix_rate(scope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """% of issues resolved in the last 30 days marked self-fix."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    flt = dict(scope)
    flt["status"] = {"$in": ["closed", "resolved"]}
    flt["closed_at"] = {"$gte": since}
    cur = _db["issues"].find(flt, {"resolution_type": 1, "self_fix": 1, "_id": 0})
    total = 0
    self_fix = 0
    async for d in cur:
        total += 1
        if d.get("self_fix") is True or d.get("resolution_type") == "self_fix":
            self_fix += 1
    if total == 0:
        return 65, {"resolved_30d": 0, "self_fix_pct": None}
    pct = 100.0 * self_fix / total
    return _clamp(pct), {"resolved_30d": total, "self_fix_pct": round(pct, 1)}


async def _audit_coverage(scope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """% of equipment with at least one check-sheet in the last 7 days."""
    eq_flt = dict(scope)
    eq_flt["active"] = {"$ne": False}
    eq_count = await _db["equipment"].count_documents(eq_flt)
    if eq_count == 0:
        return 50, {"equipment_count": 0, "covered_pct": None}

    since = datetime.now(timezone.utc) - timedelta(days=7)
    cs_flt = dict(scope)
    cs_flt["completed_at"] = {"$gte": since}
    covered = await _db["check_sheets"].distinct("equipment_id", cs_flt)
    pct = 100.0 * len(covered) / eq_count
    return _clamp(pct), {"equipment_count": eq_count, "covered_pct": round(pct, 1)}


async def _warranty_health(scope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """% of equipment in active warranty or active service contract."""
    eq_flt = dict(scope)
    eq_flt["active"] = {"$ne": False}
    eq_count = await _db["equipment"].count_documents(eq_flt)
    if eq_count == 0:
        return 50, {"equipment_count": 0, "in_warranty_pct": None}

    today = datetime.now(timezone.utc)
    cov_flt = dict(eq_flt)
    cov_flt["$or"] = [
        {"warranty_expires_at": {"$gte": today}},
        {"service_contract_expires_at": {"$gte": today}},
    ]
    in_warranty = await _db["equipment"].count_documents(cov_flt)
    pct = 100.0 * in_warranty / eq_count
    return _clamp(pct), {"equipment_count": eq_count, "in_warranty_pct": round(pct, 1)}


async def _sla_adherence(scope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """% of issues in the last 30 days acknowledged within 24h."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    flt = dict(scope)
    flt["created_at"] = {"$gte": since}
    cur = _db["issues"].find(flt, {"created_at": 1, "acknowledged_at": 1, "_id": 0})
    total = 0
    on_time = 0
    async for d in cur:
        total += 1
        ack = d.get("acknowledged_at")
        created = d.get("created_at")
        if not ack or not created:
            continue
        if isinstance(ack, str):
            try:
                ack = datetime.fromisoformat(ack.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
        if (ack - created).total_seconds() <= 86400:
            on_time += 1
    if total == 0:
        return 85, {"faults_30d": 0, "ack_within_24h_pct": None}
    pct = 100.0 * on_time / total
    return _clamp(pct), {"faults_30d": total, "ack_within_24h_pct": round(pct, 1)}


@router.get("/me")
async def get_my_pulse_score(
    site_id: Optional[str] = None,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """Return the Pulse Score for the current user's org (optionally a
    single site within it).

    Response shape:
        {
          "score": 78,                 # 0-100 composite
          "band": "good",              # poor | fair | good | excellent
          "scope": {"organization_id": "...", "site_id": "..." | null},
          "components": {
            "fault_freshness": {"score": 82, "weight": 0.30, "detail": {...}},
            ...
          },
          "generated_at": "2026-..."
        }
    """
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organisation context")

    # Honour the user's primary site as default scope when not given.
    effective_site = site_id or user.get("site_id") or user.get("primary_site_id")
    scope = _scope_filter(org_id, effective_site)

    components: dict[str, dict[str, Any]] = {}
    composite = 0.0
    for key, fn in (
        ("fault_freshness", _fault_freshness),
        ("self_fix_rate",   _self_fix_rate),
        ("audit_coverage",  _audit_coverage),
        ("warranty_health", _warranty_health),
        ("sla_adherence",   _sla_adherence),
    ):
        score, detail = await fn(scope)
        weight = WEIGHTS[key]
        components[key] = {"score": score, "weight": weight, "detail": detail}
        composite += score * weight

    score_int = _clamp(composite)
    if score_int >= 85:
        band = "excellent"
    elif score_int >= 70:
        band = "good"
    elif score_int >= 50:
        band = "fair"
    else:
        band = "poor"

    return {
        "score": score_int,
        "band": band,
        "scope": {"organization_id": org_id, "site_id": effective_site},
        "components": components,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

