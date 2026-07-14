"""Dealer Warranty Parts — Phase 4.

Parts Failure Monitoring Agent, Global Failure Intelligence, Replenishment
engine, and configurable Alerts. Reads the Phase 3 usage logs
(`dealer_parts_usage_logs`) plus store stock — no duplicate data.

Closed loop: `failure_bump()` is imported by the recommendation engine
(`routes.dealer_parts_bom`) so monitoring insights automatically raise pack
quantities for regions/dealers where a part is failing above the global rate,
and flag suspected quality issues.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user

from routes.dealer_parts import _of, _now, _audit, _get_settings

router = APIRouter(prefix="/dealer-parts", tags=["Dealer Warranty Parts"])

USAGE = "dealer_parts_usage_logs"
STORE_STOCK = "dealer_remote_store_stock"
ALERTS = "dealer_parts_alerts"

QUALITY_REASONS = {"manufacturing_defect_suspected", "electrical_failure", "mechanical_failure", "corrosion_environmental"}

ALERT_STATUSES = ["new", "under_review", "investigating", "action_required", "resolved", "dismissed"]


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


async def _usage_rows(org: str, days: int) -> list:
    return await db[USAGE].find(
        {"organization_id": org, "at": {"$gte": _since(days)}}, {"_id": 0}
    ).to_list(20000)


# ─────────────────────────────────────────────────────────────────
# Global Failure Intelligence
# ─────────────────────────────────────────────────────────────────

def _is_failure(u: dict) -> bool:
    return bool(u.get("warranty")) or (u.get("failure_reason") or "unknown") not in ("", "unknown")


@router.get("/intel/overview")
async def intel_overview(days: int = Query(90, ge=1, le=730), user=Depends(get_current_user)):
    org = _of(user)
    rows = await _usage_rows(org, days)
    by_part: dict = defaultdict(lambda: {"failures": 0, "qty": 0.0, "name": ""})
    by_country: dict = defaultdict(int)
    by_dealer: dict = defaultdict(int)
    by_model: dict = defaultdict(int)
    by_reason: dict = defaultdict(int)
    trend: dict = defaultdict(int)

    for u in rows:
        q = u.get("quantity") or 0
        fail = _is_failure(u)
        sku = u.get("part_sku") or "?"
        rec = by_part[sku]
        rec["qty"] += q
        rec["name"] = u.get("part_name") or rec["name"]
        if fail:
            rec["failures"] += 1
            by_country[u.get("country") or "Unknown"] += 1
            by_dealer[u.get("dealer_name") or "Unknown"] += 1
            by_model[u.get("machine_model") or "Unknown"] += 1
            by_reason[(u.get("failure_reason") or "unknown")] += 1
            trend[(u.get("at") or "")[:7]] += 1  # YYYY-MM

    def top(d, key="count", n=10, is_part=False):
        if is_part:
            items = [{"part_sku": k, "part_name": v["name"], "failures": v["failures"], "qty_used": v["qty"]} for k, v in d.items()]
            items.sort(key=lambda x: -x["failures"])
            return items[:n]
        items = [{"label": k, "count": v} for k, v in d.items()]
        items.sort(key=lambda x: -x["count"])
        return items[:n]

    return {
        "window_days": days,
        "total_usage_events": len(rows),
        "total_failures": sum(1 for u in rows if _is_failure(u)),
        "top_failing_parts": top(by_part, is_part=True),
        "by_country": top(by_country),
        "by_dealer": top(by_dealer),
        "by_model": top(by_model),
        "by_reason": top(by_reason),
        "trend": [{"month": k, "failures": v} for k, v in sorted(trend.items())],
    }


@router.get("/intel/failures")
async def intel_failures(
    group_by: str = Query("part", pattern="^(part|country|dealer|model|serial)$"),
    days: int = Query(90, ge=1, le=730),
    user=Depends(get_current_user),
):
    org = _of(user)
    rows = [u for u in await _usage_rows(org, days) if _is_failure(u)]
    key_map = {
        "part": lambda u: (u.get("part_sku") or "?"),
        "country": lambda u: (u.get("country") or "Unknown"),
        "dealer": lambda u: (u.get("dealer_name") or "Unknown"),
        "model": lambda u: (u.get("machine_model") or "Unknown"),
        "serial": lambda u: _serial_prefix(u.get("serial_number") or ""),
    }
    kf = key_map[group_by]
    groups: dict = defaultdict(lambda: {"failures": 0, "qty": 0.0, "quality_flags": 0, "warranty": 0})
    for u in rows:
        g = groups[kf(u)]
        g["failures"] += 1
        g["qty"] += u.get("quantity") or 0
        if (u.get("failure_reason") or "") in QUALITY_REASONS:
            g["quality_flags"] += 1
        if u.get("warranty"):
            g["warranty"] += 1
    out = [{"group": k, **v} for k, v in groups.items() if k]
    out.sort(key=lambda x: -x["failures"])
    return {"group_by": group_by, "window_days": days, "rows": out}


def _serial_prefix(serial: str) -> str:
    s = (serial or "").strip().upper()
    if not s:
        return ""
    # strip trailing digits to form a batch/range key
    i = len(s)
    while i > 0 and s[i - 1].isdigit():
        i -= 1
    prefix = s[:i] or s
    return f"{prefix}*"


# ─────────────────────────────────────────────────────────────────
# Monitoring Agent
# ─────────────────────────────────────────────────────────────────

async def _upsert_alert(org: str, alert: dict) -> bool:
    """Dedup open alerts by (alert_type, part_number, scope). Returns True if newly created."""
    key = {
        "organization_id": org,
        "alert_type": alert["alert_type"],
        "part_number": alert.get("part_number", ""),
        "scope": alert.get("scope", ""),
        "status": {"$in": ["new", "under_review", "investigating", "action_required"]},
    }
    existing = await db[ALERTS].find_one(key)
    if existing:
        await db[ALERTS].update_one({"_id": existing["_id"]}, {"$set": {
            "evidence": alert["evidence"], "severity": alert["severity"],
            "suggested_action": alert["suggested_action"], "updated_at": _now(),
        }})
        return False
    await db[ALERTS].insert_one(dict(alert))
    return True


@router.post("/monitoring/run")
async def run_monitoring(user=Depends(get_current_user)):
    org = _of(user)
    s = await _get_settings(org)
    if not s.get("enable_monitoring_agent", True):
        raise HTTPException(400, "Monitoring agent is disabled in settings")
    days = int(s.get("monitoring_window_days") or 90)
    threshold = int(s.get("failure_alert_threshold") or 5)
    spike = float(s.get("usage_spike_factor") or 2.0)
    rows = [u for u in await _usage_rows(org, days) if _is_failure(u)]

    # aggregate
    part_country = defaultdict(int)     # (sku, country) -> failures
    part_global = defaultdict(int)      # sku -> failures
    part_countries = defaultdict(set)   # sku -> {countries}
    part_dealer = defaultdict(int)      # (sku, dealer) -> failures
    part_names = {}
    quality = defaultdict(int)          # sku -> quality-reason failures
    serial_group = defaultdict(int)     # (sku, serial_prefix) -> failures

    for u in rows:
        sku = u.get("part_sku") or "?"
        part_names[sku] = u.get("part_name") or sku
        c = u.get("country") or "Unknown"
        part_country[(sku, c)] += 1
        part_global[sku] += 1
        part_countries[sku].add(c)
        part_dealer[(sku, u.get("dealer_name") or "Unknown")] += 1
        if (u.get("failure_reason") or "") in QUALITY_REASONS:
            quality[sku] += 1
        sp = _serial_prefix(u.get("serial_number") or "")
        if sp:
            serial_group[(sku, sp)] += 1

    created = 0
    now = _now()

    def mk(alert_type, part_number, scope, severity, evidence, action):
        return {
            "id": str(uuid.uuid4()), "organization_id": org,
            "reference": f"ALERT-{uuid.uuid4().hex[:8].upper()}",
            "alert_type": alert_type, "part_number": part_number,
            "part_name": part_names.get(part_number, part_number),
            "scope": scope, "severity": severity, "evidence": evidence,
            "suggested_action": action, "status": "new",
            "created_at": now, "updated_at": now,
        }

    # 1. High failure rate by country + spike vs the average of OTHER countries
    for (sku, c), cnt in part_country.items():
        n_countries = len(part_countries[sku])
        if n_countries <= 1:
            continue
        others_avg = (part_global[sku] - cnt) / (n_countries - 1)
        if cnt >= threshold and cnt >= max(0.5, others_avg) * spike:
            ratio = cnt / max(0.5, others_avg)
            sev = "critical" if cnt >= threshold * 2 else "warning"
            created += await _upsert_alert(org, mk(
                "high_failure_rate", sku, c, sev,
                f"{part_names.get(sku, sku)} ({sku}) failed {cnt} times in {c} in {days}d — {ratio:.1f}× the average of other regions.",
                "Investigate regional root cause; consider increasing dealer pack quantities for this region.",
            ))

    # 2. Potential quality issue (defect-type failures)
    for sku, qn in quality.items():
        if qn >= max(3, threshold):
            created += await _upsert_alert(org, mk(
                "potential_quality_issue", sku, "global", "warning",
                f"{part_names.get(sku, sku)} ({sku}) has {qn} defect-type failures in {days}d.",
                "Raise with quality/warranty team; request RMA of failed parts for inspection.",
            ))

    # 3. Repeated failure by serial-number range
    for (sku, sp), cnt in serial_group.items():
        if cnt >= 3:
            created += await _upsert_alert(org, mk(
                "repeated_failure_by_serial", sku, sp, "warning",
                f"Serial range {sp} shows {cnt} failures of {part_names.get(sku, sku)} ({sku}) — possible batch issue.",
                "Check build/install dates for this serial range; flag to product/quality.",
            ))

    await _audit(org, user, "monitoring_run", alerts_created=created, failures_scanned=len(rows))
    return {"alerts_created": created, "failures_scanned": len(rows), "window_days": days}


@router.get("/alerts")
async def list_alerts(status: str = Query(""), severity: str = Query(""), user=Depends(get_current_user)):
    org = _of(user)
    q: dict = {"organization_id": org}
    if status:
        q["status"] = status
    if severity:
        q["severity"] = severity
    rows = await db[ALERTS].find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)
    return {"alerts": rows, "count": len(rows)}


@router.patch("/alerts/{alert_id}")
async def update_alert(alert_id: str, data: dict, user=Depends(get_current_user)):
    org = _of(user)
    existing = await db[ALERTS].find_one({"organization_id": org, "id": alert_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Alert not found")
    patch: dict = {"updated_at": _now()}
    if "status" in data:
        if data["status"] not in ALERT_STATUSES:
            raise HTTPException(400, "Invalid status")
        patch["status"] = data["status"]
    if "assigned_owner" in data:
        patch["assigned_owner"] = data["assigned_owner"]
    if "notes" in data:
        patch["notes"] = data["notes"]
    await db[ALERTS].update_one({"organization_id": org, "id": alert_id}, {"$set": patch})
    await _audit(org, user, "alert_updated", alert_id=alert_id, changes=list(patch.keys()))
    return await db[ALERTS].find_one({"organization_id": org, "id": alert_id}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────
# Replenishment engine
# ─────────────────────────────────────────────────────────────────

@router.get("/replenishment")
async def replenishment(dealer_id: str = Query(""), days: int = Query(90, ge=1, le=365), user=Depends(get_current_user)):
    org = _of(user)
    stock_q: dict = {"organization_id": org}
    if dealer_id:
        stock_q["dealer_id"] = dealer_id
    stock = await db[STORE_STOCK].find(stock_q, {"_id": 0}).to_list(5000)

    usage_q = {"organization_id": org, "at": {"$gte": _since(days)}}
    if dealer_id:
        usage_q["dealer_id"] = dealer_id
    usage = await db[USAGE].find(usage_q, {"_id": 0}).to_list(20000)
    used = defaultdict(float)   # (dealer_id, sku) -> qty used
    for u in usage:
        used[(u.get("dealer_id"), u.get("part_sku"))] += u.get("quantity") or 0

    out = []
    for s in stock:
        on_hand = s.get("qty_on_hand") or 0
        mn = s.get("min_stock") or 0
        rec = s.get("recommended_stock") or 0
        u90 = used[(s.get("dealer_id"), s.get("part_sku"))]
        target = max(rec, mn * 2 if mn else 0, math.ceil(u90))
        if rec and on_hand > rec * 1.5:
            label, urgency = "Overstocked", "low"
        elif on_hand <= 0 and (mn or u90):
            label, urgency = "Critical Replenishment", "critical"
        elif mn and on_hand <= mn:
            label, urgency = "Replenishment Recommended", "high"
        elif u90 > on_hand:
            label, urgency = "Low Stock", "medium"
        elif u90 > 0:
            label, urgency = "Monitor", "low"
        else:
            label, urgency = "No Action Needed", "none"
        rec_qty = max(0, int(math.ceil(target - on_hand))) if label not in ("No Action Needed", "Overstocked") else 0
        out.append({
            "dealer_id": s.get("dealer_id"),
            "store_name": s.get("store_name"),
            "part_sku": s.get("part_sku"),
            "part_name": s.get("part_name"),
            "on_hand": on_hand,
            "min_stock": mn,
            "used_period": u90,
            "label": label,
            "urgency": urgency,
            "recommended_qty": rec_qty,
            "estimated_value": round(rec_qty * (s.get("unit_value") or 0), 2),
        })
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
    out.sort(key=lambda x: (order.get(x["urgency"], 5), -x["recommended_qty"]))
    return {"window_days": days, "rows": out}


# ─────────────────────────────────────────────────────────────────
# Closed loop — used by the recommendation engine
# ─────────────────────────────────────────────────────────────────

async def failure_bump(org: str, region: str, country: str, sku: str) -> tuple[int, str, bool]:
    """Return (extra_qty, note, quality_flag) for a part in a region/country
    based on recent failure signals. Drives the Recommendation Engine closed loop."""
    if not sku:
        return 0, "", False
    s = await _get_settings(org)
    days = int(s.get("monitoring_window_days") or 90)
    spike = float(s.get("usage_spike_factor") or 2.0)
    rows = await db[USAGE].find(
        {"organization_id": org, "part_sku": sku, "at": {"$gte": _since(days)}}, {"_id": 0}
    ).to_list(20000)
    rows = [u for u in rows if _is_failure(u)]
    if not rows:
        return 0, "", False
    countries = defaultdict(int)
    quality = 0
    for u in rows:
        countries[u.get("country") or "Unknown"] += 1
        if (u.get("failure_reason") or "") in QUALITY_REASONS:
            quality += 1
    local = countries.get(country, 0)
    n = len(countries)
    quality_flag = quality >= 3
    if n > 1 and local >= 3:
        others_avg = (len(rows) - local) / (n - 1)
        if local >= max(0.5, others_avg) * spike:
            ratio = local / max(0.5, others_avg)
            extra = min(5, int(math.ceil(local / 5.0)))
            note = f" Failure monitoring: {sku} is failing {ratio:.1f}× the other-region average in {country} — pack increased by {extra}."
            return extra, note, quality_flag
    if quality_flag:
        return 0, f" Quality watch: {sku} shows {quality} defect-type failures globally.", True
    return 0, "", False
