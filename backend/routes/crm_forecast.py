"""
CRM Forecasting + Quota Management — iter 215de.

Two new collections:
  - `crm_quotas`      → {user_id, period_type, period_key, target_value, ...}
  - opportunities now carry `forecast_category` ∈ {pipeline, best_case, commit, omitted}

The forecast endpoint groups open opportunities by owner, splits them
into the four categories above, then joins quota targets to compute
attainment % per rep + a manager rollup.

Period keys:
  - month   → "YYYY-MM"   (e.g. "2026-05")
  - quarter → "YYYY-Qn"   (e.g. "2026-Q2")

All money handling is float pence-level for simplicity (matches the
rest of the platform). Org-scoped via `_of(user)`.
"""
from datetime import datetime, timezone
from typing import Iterable
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from routes.crm_auth import get_crm_user, _is_master_admin_user

router = APIRouter(prefix="/crm/forecast", tags=["CRM Forecast"])

PERIOD_TYPES = {"month", "quarter"}
FORECAST_CATEGORIES = {"pipeline", "best_case", "commit", "omitted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id") or "__none__"}


def _current_month_key(d: datetime | None = None) -> str:
    d = d or datetime.now(timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def _current_quarter_key(d: datetime | None = None) -> str:
    d = d or datetime.now(timezone.utc)
    q = (d.month - 1) // 3 + 1
    return f"{d.year:04d}-Q{q}"


def _period_window(period_type: str, period_key: str) -> tuple[datetime, datetime]:
    """Return [start, end) UTC datetime window for a period key."""
    if period_type == "month":
        year, month = period_key.split("-")
        y, m = int(year), int(month)
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        end = datetime(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc)
        return start, end
    # quarter
    year, qpart = period_key.split("-Q")
    y, q = int(year), int(qpart)
    start_month = (q - 1) * 3 + 1
    start = datetime(y, start_month, 1, tzinfo=timezone.utc)
    end_month = start_month + 3
    end_year = y + (1 if end_month > 12 else 0)
    end_month = end_month - 12 if end_month > 12 else end_month
    end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)
    return start, end


# ─────────────────────────────────────────────────────────────────────
# QUOTAS
# ─────────────────────────────────────────────────────────────────────


@router.get("/quotas")
async def list_quotas(
    period_type: str = Query("month"),
    period_key: str = Query(""),
    user=Depends(get_crm_user),
):
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    q = {**_of(user), "period_type": period_type}
    if period_key:
        q["period_key"] = period_key
    rows = await db.crm_quotas.find(q, {"_id": 0}).sort("period_key", -1).to_list(500)
    return {"quotas": rows}


@router.put("/quotas")
async def upsert_quota(data: dict, user=Depends(get_crm_user)):
    """Create or update a quota for a rep. Only admins can set quotas for others."""
    user_id = (data.get("user_id") or "").strip()
    period_type = (data.get("period_type") or "month").lower()
    period_key = (data.get("period_key") or "").strip()
    target_value = float(data.get("target_value") or 0)
    if not user_id or not period_key:
        raise HTTPException(400, "user_id and period_key required")
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    role = (user.get("role") or "").lower()
    if user_id != user.get("id") and not _is_master_admin_user(user) and role not in ("admin", "owner", "manager"):
        raise HTTPException(403, "Only admins/managers can set quotas for other reps")
    org_id = user.get("organization_id")
    await db.crm_quotas.update_one(
        {"organization_id": org_id, "user_id": user_id, "period_type": period_type, "period_key": period_key},
        {"$set": {"target_value": target_value, "updated_at": _now(), "updated_by": user.get("full_name", "")},
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
        upsert=True,
    )
    return {"success": True}


@router.delete("/quotas/{quota_id}")
async def delete_quota(quota_id: str, user=Depends(get_crm_user)):
    role = (user.get("role") or "").lower()
    if not _is_master_admin_user(user) and role not in ("admin", "owner", "manager"):
        raise HTTPException(403, "Forbidden")
    await db.crm_quotas.delete_one({"id": quota_id, **_of(user)})
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────
# OPPORTUNITY FORECAST CATEGORY
# ─────────────────────────────────────────────────────────────────────


@router.put("/opportunities/{opp_id}/category")
async def set_forecast_category(opp_id: str, data: dict, user=Depends(get_crm_user)):
    cat = (data.get("forecast_category") or "").lower()
    if cat not in FORECAST_CATEGORIES:
        raise HTTPException(400, f"forecast_category must be one of {sorted(FORECAST_CATEGORIES)}")
    existing = await db.crm2_opportunities.find_one({"id": opp_id, **_of(user)})
    if not existing:
        raise HTTPException(404, "Opportunity not found")
    # Ownership: must be owner or admin/manager
    role = (user.get("role") or "").lower()
    is_admin = _is_master_admin_user(user) or role in ("admin", "owner", "manager")
    if not is_admin and existing.get("owner_id") != user.get("id"):
        raise HTTPException(403, "Only the deal owner or a manager can set the forecast category")
    await db.crm2_opportunities.update_one(
        {"id": opp_id},
        {"$set": {"forecast_category": cat, "updated_at": _now()}},
    )
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────
# FORECAST ROLLUP
# ─────────────────────────────────────────────────────────────────────


def _empty_bucket() -> dict:
    return {"pipeline": 0.0, "best_case": 0.0, "commit": 0.0, "closed_won": 0.0, "count": 0}


def _bucket_opps(opps: Iterable[dict], window: tuple[datetime, datetime]) -> dict[str, dict]:
    """Bucket opportunities by owner_id → category sums."""
    start, end = window
    by_owner: dict[str, dict] = {}
    for o in opps:
        owner = o.get("owner_id") or "_unowned"
        b = by_owner.setdefault(owner, {**_empty_bucket(), "owner_name": o.get("owner_name", "")})
        if o.get("owner_name"):
            b["owner_name"] = o["owner_name"]
        b["count"] += 1
        value = float(o.get("value") or 0)
        stage = o.get("stage")
        if stage == "closed_won":
            close = (o.get("close_date") or "")[:10]
            try:
                close_dt = datetime.fromisoformat(close).replace(tzinfo=timezone.utc) if close else None
            except ValueError:
                close_dt = None
            if not close_dt or (start <= close_dt < end):
                b["closed_won"] += value
            continue
        if stage == "closed_lost":
            continue
        cat = (o.get("forecast_category") or "pipeline").lower()
        if cat == "omitted":
            continue
        if cat == "commit":
            b["commit"] += value
            b["best_case"] += value
            b["pipeline"] += value
        elif cat == "best_case":
            b["best_case"] += value
            b["pipeline"] += value
        else:
            b["pipeline"] += value
    return by_owner


@router.get("")
async def forecast_rollup(
    period_type: str = Query("month"),
    period_key: str = Query(""),
    user=Depends(get_crm_user),
):
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    if not period_key:
        period_key = _current_quarter_key() if period_type == "quarter" else _current_month_key()
    window = _period_window(period_type, period_key)
    of = _of(user)

    # Pull all open + closed_won-in-window deals.
    opps = await db.crm2_opportunities.find(
        {**of},
        {"_id": 0, "id": 1, "owner_id": 1, "owner_name": 1, "value": 1, "stage": 1,
         "forecast_category": 1, "close_date": 1, "title": 1, "company_name": 1},
    ).to_list(5000)
    by_owner = _bucket_opps(opps, window)

    # Join quotas for the period
    quotas = await db.crm_quotas.find(
        {**of, "period_type": period_type, "period_key": period_key},
        {"_id": 0},
    ).to_list(500)
    quota_map = {q["user_id"]: float(q.get("target_value") or 0) for q in quotas}

    # Roster — pull owner names for users with a quota but no deal yet
    if quota_map:
        uids = [uid for uid in quota_map if uid not in by_owner]
        if uids:
            users = await db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1}).to_list(200)
            for u in users:
                bucket = {**_empty_bucket(), "owner_name": u.get("full_name") or u.get("email", "")}
                by_owner[u["id"]] = bucket

    rows = []
    org_totals = {**_empty_bucket(), "quota": 0.0}
    for uid, b in by_owner.items():
        quota = quota_map.get(uid, 0.0)
        attainment = (b["closed_won"] / quota * 100.0) if quota > 0 else None
        commit_attainment = ((b["closed_won"] + b["commit"]) / quota * 100.0) if quota > 0 else None
        row = {
            "user_id": uid,
            "owner_name": b.get("owner_name") or "Unknown",
            "pipeline": round(b["pipeline"], 2),
            "best_case": round(b["best_case"], 2),
            "commit": round(b["commit"], 2),
            "closed_won": round(b["closed_won"], 2),
            "count": b["count"],
            "quota": round(quota, 2),
            "attainment_pct": None if attainment is None else round(attainment, 1),
            "commit_plus_won_pct": None if commit_attainment is None else round(commit_attainment, 1),
        }
        rows.append(row)
        for k in ("pipeline", "best_case", "commit", "closed_won"):
            org_totals[k] += b[k]
        org_totals["count"] += b["count"]
        org_totals["quota"] += quota

    rows.sort(key=lambda r: (r["closed_won"] + r["commit"]), reverse=True)
    overall_att = (org_totals["closed_won"] / org_totals["quota"] * 100.0) if org_totals["quota"] > 0 else None
    return {
        "period_type": period_type,
        "period_key": period_key,
        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
        "rows": rows,
        "totals": {
            **{k: round(v, 2) for k, v in org_totals.items() if k != "count"},
            "count": org_totals["count"],
            "attainment_pct": None if overall_att is None else round(overall_att, 1),
        },
    }


@router.get("/categories")
async def list_categories():
    """Constants for the UI's category dropdown."""
    return {"categories": sorted(FORECAST_CATEGORIES)}


# ─────────────────────────────────────────────────────────────────────
# MANAGER FORECAST REVIEW — team rollup + commit calls
# ─────────────────────────────────────────────────────────────────────


def _is_manager(user: dict) -> bool:
    if _is_master_admin_user(user):
        return True
    return (user.get("role") or "").lower() in ("admin", "owner", "manager")


async def _team_member_ids(manager_id: str, organization_id: str) -> list[str]:
    """Direct + indirect reports of `manager_id` (includes the manager)."""
    try:
        from routes.crm_territories import collect_team_ids
        ids = await collect_team_ids(manager_id, organization_id)
        return ids or [manager_id]
    except Exception:
        return [manager_id]


@router.get("/team")
async def team_forecast(
    period_type: str = Query("quarter"),
    period_key: str = Query(""),
    user=Depends(get_crm_user),
):
    """Manager view — rep rows + active commit-call for the period."""
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    if not period_key:
        period_key = _current_quarter_key() if period_type == "quarter" else _current_month_key()
    window = _period_window(period_type, period_key)
    of = _of(user)
    org_id = user.get("organization_id")

    # Scope: master admins see the whole org; managers see their team only.
    if _is_master_admin_user(user):
        owner_ids: list[str] | None = None  # all
    else:
        owner_ids = await _team_member_ids(user.get("id", ""), org_id or "")

    opp_q = {**of}
    if owner_ids is not None:
        opp_q["owner_id"] = {"$in": owner_ids}
    opps = await db.crm2_opportunities.find(
        opp_q,
        {"_id": 0, "id": 1, "owner_id": 1, "owner_name": 1, "value": 1, "stage": 1,
         "forecast_category": 1, "close_date": 1, "title": 1, "company_name": 1},
    ).to_list(5000)
    by_owner = _bucket_opps(opps, window)

    quota_q = {**of, "period_type": period_type, "period_key": period_key}
    if owner_ids is not None:
        quota_q["user_id"] = {"$in": owner_ids}
    quotas = await db.crm_quotas.find(quota_q, {"_id": 0}).to_list(500)
    quota_map = {q["user_id"]: float(q.get("target_value") or 0) for q in quotas}

    # Latest commit-call per rep
    call_q = {**of, "period_type": period_type, "period_key": period_key}
    if owner_ids is not None:
        call_q["user_id"] = {"$in": owner_ids}
    calls = await db.crm_commit_calls.find(call_q, {"_id": 0}).sort("called_at", -1).to_list(500)
    call_map: dict[str, dict] = {}
    for c in calls:
        uid = c.get("user_id")
        if uid and uid not in call_map:
            call_map[uid] = c

    # Hydrate rep names for users with quotas/calls but zero deals
    extras = [
        uid for uid in (set(quota_map) | set(call_map))
        if uid and uid not in by_owner
    ]
    if extras:
        users = await db.users.find(
            {"id": {"$in": extras}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1},
        ).to_list(200)
        for u in users:
            by_owner[u["id"]] = {**_empty_bucket(), "owner_name": u.get("full_name") or u.get("email", "")}

    rows = []
    totals = {**_empty_bucket(), "quota": 0.0, "manager_call": 0.0}
    for uid, b in by_owner.items():
        if owner_ids is not None and uid not in owner_ids:
            continue
        quota = quota_map.get(uid, 0.0)
        attainment = (b["closed_won"] / quota * 100.0) if quota > 0 else None
        call = call_map.get(uid, {})
        rows.append({
            "user_id": uid,
            "owner_name": b.get("owner_name") or "Unknown",
            "pipeline": round(b["pipeline"], 2),
            "best_case": round(b["best_case"], 2),
            "commit": round(b["commit"], 2),
            "closed_won": round(b["closed_won"], 2),
            "count": b["count"],
            "quota": round(quota, 2),
            "attainment_pct": None if attainment is None else round(attainment, 1),
            "manager_call": round(float(call.get("manager_call_value") or 0), 2),
            "manager_call_notes": call.get("notes", ""),
            "manager_call_at": call.get("called_at", ""),
            "manager_call_by": call.get("called_by", ""),
        })
        for k in ("pipeline", "best_case", "commit", "closed_won"):
            totals[k] += b[k]
        totals["quota"] += quota
        totals["manager_call"] += float(call.get("manager_call_value") or 0)
        totals["count"] += b["count"]
    rows.sort(key=lambda r: (r["manager_call"], r["closed_won"] + r["commit"]), reverse=True)

    overall_att = (totals["closed_won"] / totals["quota"] * 100.0) if totals["quota"] > 0 else None
    return {
        "period_type": period_type,
        "period_key": period_key,
        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
        "scope": "org" if owner_ids is None else "team",
        "rows": rows,
        "totals": {
            **{k: round(v, 2) for k, v in totals.items() if k != "count"},
            "count": totals["count"],
            "attainment_pct": None if overall_att is None else round(overall_att, 1),
        },
    }


@router.put("/team/call")
async def upsert_commit_call(data: dict, user=Depends(get_crm_user)):
    """Manager records / overrides their commit number for a rep this period."""
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    rep_id = (data.get("user_id") or "").strip()
    period_type = (data.get("period_type") or "quarter").lower()
    period_key = (data.get("period_key") or "").strip()
    manager_call_value = float(data.get("manager_call_value") or 0)
    notes = (data.get("notes") or "").strip()
    if not rep_id or not period_key or period_type not in PERIOD_TYPES:
        raise HTTPException(400, "user_id, period_type, period_key required")
    org_id = user.get("organization_id")
    # Ownership: master admins everyone; managers — only their own team.
    if not _is_master_admin_user(user):
        team = await _team_member_ids(user.get("id", ""), org_id or "")
        if rep_id not in team:
            raise HTTPException(403, "Rep is not part of your team")
    await db.crm_commit_calls.update_one(
        {"organization_id": org_id, "user_id": rep_id, "period_type": period_type, "period_key": period_key},
        {"$set": {
            "manager_call_value": manager_call_value,
            "notes": notes,
            "called_at": _now(),
            "called_by": user.get("full_name", "") or user.get("email", ""),
            "called_by_id": user.get("id", ""),
        }, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
        upsert=True,
    )
    return {"success": True}


@router.delete("/team/call")
async def delete_commit_call(
    user_id: str = Query(...),
    period_type: str = Query("quarter"),
    period_key: str = Query(...),
    user=Depends(get_crm_user),
):
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    if not _is_master_admin_user(user):
        team = await _team_member_ids(user.get("id", ""), user.get("organization_id") or "")
        if user_id not in team:
            raise HTTPException(403, "Rep is not part of your team")
    await db.crm_commit_calls.delete_one({
        "organization_id": user.get("organization_id"),
        "user_id": user_id,
        "period_type": period_type,
        "period_key": period_key,
    })
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────
# FORECAST ACCURACY — period snapshots + retro scoring
# ─────────────────────────────────────────────────────────────────────


async def _snapshot_for_period(
    organization_id: str, period_type: str, period_key: str, taken_by: str,
) -> dict:
    """Freeze the current pipeline/commit/call numbers for a period.

    Idempotent — re-running for the same (org, period_type, period_key)
    overwrites prior snapshot rows. Returns a summary dict.
    """
    window = _period_window(period_type, period_key)
    of = {"organization_id": organization_id}
    opps = await db.crm2_opportunities.find(
        {**of},
        {"_id": 0, "id": 1, "owner_id": 1, "owner_name": 1, "value": 1, "stage": 1,
         "forecast_category": 1, "close_date": 1},
    ).to_list(5000)
    by_owner = _bucket_opps(opps, window)

    quotas = await db.crm_quotas.find(
        {**of, "period_type": period_type, "period_key": period_key}, {"_id": 0},
    ).to_list(500)
    quota_map = {q["user_id"]: float(q.get("target_value") or 0) for q in quotas}

    calls = await db.crm_commit_calls.find(
        {**of, "period_type": period_type, "period_key": period_key}, {"_id": 0},
    ).to_list(500)
    call_map = {c["user_id"]: c for c in calls}

    # Wipe prior snapshot rows for this period — idempotent re-take.
    await db.crm_forecast_snapshots.delete_many(
        {"organization_id": organization_id, "period_type": period_type, "period_key": period_key}
    )

    rows = []
    union = set(by_owner) | set(quota_map) | set(call_map)
    for uid in union:
        b = by_owner.get(uid) or {**_empty_bucket(), "owner_name": ""}
        call = call_map.get(uid, {})
        row = {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "user_id": uid,
            "owner_name": b.get("owner_name") or "",
            "period_type": period_type,
            "period_key": period_key,
            "snapshot_at": _now(),
            "snapshot_by": taken_by,
            "pipeline": round(b["pipeline"], 2),
            "best_case": round(b["best_case"], 2),
            "commit": round(b["commit"], 2),
            "closed_won_at_snapshot": round(b["closed_won"], 2),
            "manager_call": round(float(call.get("manager_call_value") or 0), 2),
            "manager_call_notes": call.get("notes", ""),
            "quota": round(quota_map.get(uid, 0.0), 2),
        }
        rows.append(row)
    if rows:
        await db.crm_forecast_snapshots.insert_many(rows)
    return {"count": len(rows), "period_type": period_type, "period_key": period_key}


@router.post("/snapshots")
async def create_snapshot(data: dict, user=Depends(get_crm_user)):
    """Manager / admin freezes the current period's forecast numbers."""
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    period_type = (data.get("period_type") or "quarter").lower()
    period_key = (data.get("period_key") or "").strip()
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    if not period_key:
        period_key = _current_quarter_key() if period_type == "quarter" else _current_month_key()
    summary = await _snapshot_for_period(
        organization_id=user.get("organization_id") or "",
        period_type=period_type, period_key=period_key,
        taken_by=user.get("full_name", "") or user.get("email", ""),
    )
    return {"success": True, **summary}


def _accuracy_pct(call: float, actual: float) -> float | None:
    """100% means call equalled actual; lower means missed (too low or too high)."""
    if call <= 0 and actual <= 0:
        return None
    if call <= 0:
        return 0.0
    delta = abs(call - actual)
    pct = max(0.0, 100.0 * (1.0 - delta / max(call, 1e-9)))
    return round(pct, 1)


@router.get("/accuracy")
async def accuracy_report(
    period_type: str = Query("quarter"),
    period_key: str = Query(""),
    user=Depends(get_crm_user),
):
    """Per-rep snapshot vs actual closed_won-in-period scoring."""
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    if not period_key:
        period_key = _current_quarter_key() if period_type == "quarter" else _current_month_key()
    of = _of(user)
    org_id = user.get("organization_id")

    if _is_master_admin_user(user):
        owner_filter: dict = {}
    else:
        team = await _team_member_ids(user.get("id", ""), org_id or "")
        owner_filter = {"user_id": {"$in": team}}

    snaps = await db.crm_forecast_snapshots.find(
        {**of, "period_type": period_type, "period_key": period_key, **owner_filter},
        {"_id": 0},
    ).to_list(500)

    if not snaps:
        return {
            "period_type": period_type, "period_key": period_key,
            "rows": [], "totals": {}, "snapshot_taken": False,
        }

    # Compute actual closed_won per rep within window
    window = _period_window(period_type, period_key)
    user_ids = [s["user_id"] for s in snaps]
    opps = await db.crm2_opportunities.find(
        {**of, "owner_id": {"$in": user_ids}, "stage": "closed_won"},
        {"_id": 0, "owner_id": 1, "value": 1, "close_date": 1},
    ).to_list(5000)
    actuals: dict[str, float] = {}
    for o in opps:
        close = (o.get("close_date") or "")[:10]
        try:
            close_dt = datetime.fromisoformat(close).replace(tzinfo=timezone.utc) if close else None
        except ValueError:
            close_dt = None
        if not close_dt or (window[0] <= close_dt < window[1]):
            actuals[o["owner_id"]] = actuals.get(o["owner_id"], 0.0) + float(o.get("value") or 0)

    rows = []
    totals = {"manager_call": 0.0, "commit": 0.0, "actual": 0.0, "quota": 0.0}
    for s in snaps:
        uid = s["user_id"]
        actual = round(actuals.get(uid, 0.0), 2)
        call = float(s.get("manager_call") or 0)
        commit = float(s.get("commit") or 0)
        quota = float(s.get("quota") or 0)
        verdict = "on_call"
        if call > 0:
            if actual >= call * 0.95 and actual <= call * 1.05:
                verdict = "on_call"
            elif actual > call * 1.05:
                verdict = "over"  # sandbagger
            else:
                verdict = "under"  # missed
        elif commit > 0:
            verdict = "over" if actual > commit * 1.05 else ("under" if actual < commit * 0.95 else "on_call")
        rows.append({
            "user_id": uid,
            "owner_name": s.get("owner_name") or "Unknown",
            "manager_call": round(call, 2),
            "commit_at_snapshot": round(commit, 2),
            "best_case_at_snapshot": round(float(s.get("best_case") or 0), 2),
            "pipeline_at_snapshot": round(float(s.get("pipeline") or 0), 2),
            "actual_closed_won": actual,
            "delta": round(actual - call, 2) if call > 0 else round(actual - commit, 2),
            "call_accuracy_pct": _accuracy_pct(call, actual) if call > 0 else _accuracy_pct(commit, actual),
            "verdict": verdict,
            "quota_attainment_pct": round(actual / quota * 100, 1) if quota > 0 else None,
            "snapshot_at": s.get("snapshot_at"),
            "snapshot_by": s.get("snapshot_by"),
        })
        totals["manager_call"] += call
        totals["commit"] += commit
        totals["actual"] += actual
        totals["quota"] += quota

    rows.sort(key=lambda r: r["actual_closed_won"], reverse=True)
    overall_call_acc = _accuracy_pct(totals["manager_call"] or totals["commit"], totals["actual"])
    return {
        "period_type": period_type, "period_key": period_key,
        "snapshot_taken": True,
        "rows": rows,
        "totals": {
            **{k: round(v, 2) for k, v in totals.items()},
            "call_accuracy_pct": overall_call_acc,
            "quota_attainment_pct": round(totals["actual"] / totals["quota"] * 100, 1) if totals["quota"] > 0 else None,
        },
    }


@router.get("/snapshots")
async def list_snapshots(user=Depends(get_crm_user)):
    """Distinct (period_type, period_key) tuples that have a snapshot — for the picker."""
    if not _is_manager(user):
        raise HTTPException(403, "Manager access required")
    pipeline = [
        {"$match": {"organization_id": user.get("organization_id")}},
        {"$group": {
            "_id": {"period_type": "$period_type", "period_key": "$period_key"},
            "snapshot_at": {"$max": "$snapshot_at"},
            "row_count": {"$sum": 1},
        }},
        {"$sort": {"_id.period_key": -1}},
        {"$limit": 50},
    ]
    cursor = db.crm_forecast_snapshots.aggregate(pipeline)
    out = []
    async for d in cursor:
        out.append({
            "period_type": d["_id"]["period_type"],
            "period_key": d["_id"]["period_key"],
            "snapshot_at": d["snapshot_at"],
            "row_count": d["row_count"],
        })
    return {"snapshots": out}


@router.get("/track-record")
async def rep_track_record(
    user_id: str = Query("", description="Defaults to the calling user."),
    periods: int = Query(4, ge=1, le=12),
    period_type: str = Query("quarter"),
    user=Depends(get_crm_user),
):
    """Per-rep forecast accuracy trend across the last N snapshotted periods.

    Visibility rules:
      - A rep can always see their OWN track record.
      - Managers see anyone in their downline.
      - Master admins see anyone in their org.
    """
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    target_id = user_id.strip() or user.get("id", "")
    if target_id != user.get("id") and not _is_master_admin_user(user):
        if not _is_manager(user):
            raise HTTPException(403, "Cannot view another rep's track record")
        team = await _team_member_ids(user.get("id", ""), user.get("organization_id") or "")
        if target_id not in team:
            raise HTTPException(403, "Rep is not part of your team")
    of = {"organization_id": user.get("organization_id") or ""}
    snaps = await db.crm_forecast_snapshots.find(
        {**of, "user_id": target_id, "period_type": period_type},
        {"_id": 0},
    ).sort("period_key", -1).limit(periods).to_list(periods)

    if not snaps:
        return {
            "user_id": target_id, "period_type": period_type,
            "rows": [], "summary": {}, "owner_name": "",
        }

    # Pull all closed-won deals owned by this rep (filter per snapshot window in-process)
    opps = await db.crm2_opportunities.find(
        {**of, "owner_id": target_id, "stage": "closed_won"},
        {"_id": 0, "value": 1, "close_date": 1},
    ).to_list(5000)

    rows: list[dict] = []
    accs: list[float] = []
    verdict_counts = {"on_call": 0, "under": 0, "over": 0}
    for s in snaps:
        window = _period_window(period_type, s["period_key"])
        actual = 0.0
        for o in opps:
            close = (o.get("close_date") or "")[:10]
            try:
                close_dt = datetime.fromisoformat(close).replace(tzinfo=timezone.utc) if close else None
            except ValueError:
                close_dt = None
            if close_dt and window[0] <= close_dt < window[1]:
                actual += float(o.get("value") or 0)
        call = float(s.get("manager_call") or 0)
        commit = float(s.get("commit") or 0)
        quota = float(s.get("quota") or 0)
        ref_call = call if call > 0 else commit
        verdict = "on_call"
        if ref_call > 0:
            if actual >= ref_call * 1.05:
                verdict = "over"
            elif actual < ref_call * 0.95:
                verdict = "under"
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        acc = _accuracy_pct(ref_call, actual)
        if acc is not None:
            accs.append(acc)
        rows.append({
            "period_key": s["period_key"],
            "manager_call": round(call, 2),
            "commit_at_snapshot": round(commit, 2),
            "actual_closed_won": round(actual, 2),
            "delta": round(actual - ref_call, 2) if ref_call > 0 else 0,
            "call_accuracy_pct": acc,
            "verdict": verdict,
            "quota": round(quota, 2),
            "quota_attainment_pct": round(actual / quota * 100, 1) if quota > 0 else None,
        })

    rows.sort(key=lambda r: r["period_key"])  # chronological for charting
    avg_acc = round(sum(accs) / len(accs), 1) if accs else None
    summary = {
        "average_accuracy_pct": avg_acc,
        "best_pct": max(accs) if accs else None,
        "worst_pct": min(accs) if accs else None,
        "verdict_counts": verdict_counts,
        "periods_scored": len(rows),
        "trend": (
            "improving" if len(accs) >= 2 and accs[0] > accs[-1] + 5  # accs ordered newest-first from snaps
            else "declining" if len(accs) >= 2 and accs[0] < accs[-1] - 5
            else "stable"
        ),
    }
    return {
        "user_id": target_id,
        "owner_name": snaps[0].get("owner_name") or "",
        "period_type": period_type,
        "rows": rows,
        "summary": summary,
    }



@router.get("/leaderboard")
async def forecast_leaderboard(
    periods: int = Query(4, ge=1, le=12),
    period_type: str = Query("quarter"),
    user=Depends(get_crm_user),
):
    """Top callers — ranks reps by average forecast accuracy across the last N snapshotted periods.

    Scope mirrors the Manager Forecast Review:
      - Master admins see the whole org.
      - Managers see their direct + indirect reports (and themselves).
      - Plain reps fall through to a self-only ranking (still useful as a context block).

    Returns podium-style metadata for the top 3 plus a `bottom_quartile` flag
    on the lowest-accuracy 25% so leaders can spot 1:1 candidates.
    """
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {sorted(PERIOD_TYPES)}")
    of = _of(user)
    org_id = user.get("organization_id") or ""

    if _is_master_admin_user(user):
        scope_ids: list[str] | None = None
    elif _is_manager(user):
        scope_ids = await _team_member_ids(user.get("id", ""), org_id)
    else:
        scope_ids = [user.get("id", "")]

    snap_q = {**of, "period_type": period_type}
    if scope_ids is not None:
        snap_q["user_id"] = {"$in": scope_ids}

    # Pull the latest `periods * len(scope)` snapshots; we'll group in-process
    # so a single query handles every user without needing aggregation pipeline.
    snaps = await db.crm_forecast_snapshots.find(snap_q, {"_id": 0}).sort("period_key", -1).to_list(5000)
    if not snaps:
        return {
            "rows": [], "summary": {"period_type": period_type, "periods": periods},
            "scope": "org" if scope_ids is None else "team",
        }

    # group by user → list of snapshots, keep newest N
    by_user: dict[str, list[dict]] = {}
    for s in snaps:
        by_user.setdefault(s["user_id"], []).append(s)
    for uid in list(by_user.keys()):
        by_user[uid] = by_user[uid][:periods]

    # Pull closed-won deals for these reps once, then bucket per snapshot window in-process.
    user_ids = list(by_user.keys())
    if not user_ids:
        return {"rows": [], "summary": {}, "scope": "org" if scope_ids is None else "team"}

    opps = await db.crm2_opportunities.find(
        {**of, "owner_id": {"$in": user_ids}, "stage": "closed_won"},
        {"_id": 0, "owner_id": 1, "value": 1, "close_date": 1},
    ).to_list(20000)
    opps_by_owner: dict[str, list[dict]] = {}
    for o in opps:
        opps_by_owner.setdefault(o["owner_id"], []).append(o)

    rows = []
    for uid, user_snaps in by_user.items():
        accs: list[float] = []
        verdicts = {"on_call": 0, "under": 0, "over": 0}
        total_actual = 0.0
        total_call = 0.0
        owner_name = ""
        for s in user_snaps:
            owner_name = owner_name or s.get("owner_name") or ""
            window = _period_window(period_type, s["period_key"])
            actual = 0.0
            for o in opps_by_owner.get(uid, []):
                close = (o.get("close_date") or "")[:10]
                try:
                    close_dt = datetime.fromisoformat(close).replace(tzinfo=timezone.utc) if close else None
                except ValueError:
                    close_dt = None
                if close_dt and window[0] <= close_dt < window[1]:
                    actual += float(o.get("value") or 0)
            call = float(s.get("manager_call") or 0)
            commit = float(s.get("commit") or 0)
            ref_call = call if call > 0 else commit
            verdict = "on_call"
            if ref_call > 0:
                if actual >= ref_call * 1.05:
                    verdict = "over"
                elif actual < ref_call * 0.95:
                    verdict = "under"
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            acc = _accuracy_pct(ref_call, actual)
            if acc is not None:
                accs.append(acc)
            total_actual += actual
            total_call += ref_call
        if not accs:
            continue
        avg = round(sum(accs) / len(accs), 1)
        rows.append({
            "user_id": uid,
            "owner_name": owner_name or "Unknown",
            "average_accuracy_pct": avg,
            "best_pct": round(max(accs), 1),
            "worst_pct": round(min(accs), 1),
            "periods_scored": len(accs),
            "total_actual": round(total_actual, 2),
            "total_call": round(total_call, 2),
            "verdict_counts": verdicts,
        })

    rows.sort(key=lambda r: (r["average_accuracy_pct"], r["periods_scored"]), reverse=True)
    # Annotate podium + bottom-quartile flags
    cutoff_idx = max(1, int(len(rows) * 0.75))
    bottom_threshold_pct = 70.0
    bottom_count = 0
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["podium"] = ["gold", "silver", "bronze"][i] if i < 3 else None
        r["bottom_quartile"] = i >= cutoff_idx
        if r["average_accuracy_pct"] < bottom_threshold_pct:
            bottom_count += 1
    return {
        "rows": rows,
        "summary": {
            "period_type": period_type,
            "periods": periods,
            "total_reps": len(rows),
            "average_accuracy_pct": round(sum(r["average_accuracy_pct"] for r in rows) / len(rows), 1) if rows else None,
            "below_70_count": bottom_count,
            "below_70_threshold": bottom_threshold_pct,
        },
        "scope": "org" if scope_ids is None else "team",
    }
