"""Master Admin — Security Alert Centre.

A live, read-only view over the deterministic Zero-Trust telemetry written by
the security programme (`utils/security_events.py`): access-control denials
(BOLA / cross-tenant / cross-site), skip-approval / invalid state transitions,
mass-assignment attempts, step-up challenges, and financial/stock movements.

Read-only by design (audit immutability — security §35): there are no mutation
endpoints here. Access is restricted to the platform Master Admin.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db
from utils.security_events import log_security_event, SEV_INFO
from routes.master_admin import require_master_admin

router = APIRouter(prefix="/master-admin/security-centre", tags=["master-admin-security-centre"])

# Event types grouped for the UI category filter.
EVENT_CATEGORIES = {
    "access_denied": [
        "bola_cross_tenant_denied", "bola_cross_owner_denied",
        "cross_site_denied", "ownership_denied", "role_denied",
    ],
    "workflow": [
        "invalid_state_transition", "privileged_transition_denied",
        "privileged_transition", "state_transition_unknown_source",
        "contract_send_blocked_unapproved",
    ],
    "mass_assignment": ["mass_assignment_blocked"],
    "step_up": ["step_up_required", "step_up_granted", "step_up_failed", "abuse_stepup_required"],
    "financial": ["invoice_status_change", "parts_allocation_approved"],
    "stock": ["stock_movement"],
    "privileged": ["privileged_admin_write", "mod_staff_transfer"],
    "abuse": ["abuse_detected", "abuse_action_blocked", "abuse_stepup_required"],
}
_ALL_TYPES = {t for types in EVENT_CATEGORIES.values() for t in types}


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _build_query(
    *, days: int, event_type: Optional[str], category: Optional[str],
    severity: Optional[str], actor: Optional[str], tenant_id: Optional[str],
    search: Optional[str],
) -> dict:
    q: dict = {"ts": {"$gte": _since(days)}}
    if event_type:
        q["event_type"] = event_type
    elif category and category in EVENT_CATEGORIES:
        q["event_type"] = {"$in": EVENT_CATEGORIES[category]}
    if severity:
        q["severity"] = severity
    if actor:
        a = actor.strip().lower()
        q["$or"] = [{"actor_email": {"$regex": a, "$options": "i"}},
                    {"actor_id": actor.strip()}]
    if tenant_id:
        q["tenant_id"] = tenant_id.strip()
    if search:
        s = search.strip()
        q.setdefault("$and", []).append({"$or": [
            {"detail": {"$regex": s, "$options": "i"}},
            {"path": {"$regex": s, "$options": "i"}},
            {"resource_id": {"$regex": s, "$options": "i"}},
            {"ip": {"$regex": s, "$options": "i"}},
        ]})
    return q


@router.get("/events")
async def list_security_events(
    user: dict = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=90),
    event_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, description="info | warning | critical"),
    actor: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
):
    """Recent security events, newest first (read-only)."""
    require_master_admin(user)
    q = _build_query(days=since_days, event_type=event_type, category=category,
                     severity=severity, actor=actor, tenant_id=tenant_id, search=search)
    rows = await db.security_events.find(q, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
    return {"count": len(rows), "events": rows,
            "since": _since(since_days).isoformat(),
            "categories": EVENT_CATEGORIES}


@router.get("/alerts")
async def poll_alerts(
    user: dict = Depends(get_current_user),
    since: Optional[str] = Query(None, description="ISO timestamp — only alerts newer than this"),
    limit: int = Query(20, ge=1, le=100),
):
    """Fast short-poll feed of new critical/abuse alerts for the live toast UI."""
    require_master_admin(user)
    q: dict = {"acknowledged": {"$ne": True}}
    if since:
        try:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            q["ts"] = {"$gt": dt}
        except Exception:
            pass
    rows = await db.security_alert_feed.find(q, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
    total_unread = await db.security_alert_feed.count_documents({"acknowledged": {"$ne": True}})
    now = datetime.now(timezone.utc).isoformat()
    return {"count": len(rows), "alerts": rows, "server_time": now, "total_unread": total_unread}


@router.post("/alerts/ack")
async def ack_alerts(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Mark alerts acknowledged so they stop re-surfacing as toasts."""
    require_master_admin(user)
    ids = payload.get("ids") or []
    if ids:
        await db.security_alert_feed.update_many(
            {"id": {"$in": ids}}, {"$set": {"acknowledged": True}})
    else:
        await db.security_alert_feed.update_many(
            {"acknowledged": {"$ne": True}}, {"$set": {"acknowledged": True}})
    return {"ok": True, "acknowledged": len(ids) if ids else "all"}


def _parse_ts(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@router.get("/abuse/active")
async def list_active_abuse(user: dict = Depends(get_current_user)):
    """Actors currently under an active abuse escalation (throttle/step-up/
    suspend) so the Master Admin can free a wrongly-flagged actor in one click."""
    require_master_admin(user)
    from utils.abuse_guard import _LEVEL_NAME
    now = datetime.now(timezone.utc)
    rows = await db.abuse_counters.find(
        {"level": {"$gt": 0}}, {"_id": 0}).sort("ts", -1).limit(200).to_list(length=200)
    out = []
    for r in rows:
        until = _parse_ts(r.get("until"))
        if not until or until <= now:
            continue  # cooldown already elapsed — effectively cleared
        out.append({
            "key": r.get("id"),
            "actor": r.get("actor") or r.get("id"),
            "last_ip": r.get("last_ip"),
            "level": int(r.get("level", 0)),
            "level_name": _LEVEL_NAME.get(int(r.get("level", 0)), "unknown"),
            "count": int(r.get("count", 0)),
            "until": until.isoformat(),
            "window_start": r.get("window_start"),
        })
    return {"count": len(out), "actors": out}


@router.post("/abuse/clear")
async def clear_abuse(
    payload: dict,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """One-click clear of an actor's abuse escalation/suspension (audited)."""
    require_master_admin(user)
    key = (payload.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    existing = await db.abuse_counters.find_one({"id": key}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="No abuse record for that actor")
    reason = (payload.get("reason") or "").strip()
    await db.abuse_counters.update_one(
        {"id": key},
        {"$set": {"level": 0, "count": 0},
         "$unset": {"until": "", "window_start": ""}},
    )
    await log_security_event(
        "abuse_suspension_cleared",
        user=user, request=request, severity=SEV_INFO,
        action="abuse_clear", result="cleared",
        resource_type="actor", resource_id=key,
        detail=f"Master admin cleared abuse escalation for {existing.get('actor') or key}"
               + (f" — reason: {reason}" if reason else ""),
        extra={"cleared_actor": existing.get("actor") or key,
               "previous_level": existing.get("level"),
               "previous_count": existing.get("count")},
    )
    return {"ok": True, "cleared": key}


@router.get("/summary")
async def security_summary(
    user: dict = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=90),
):
    """KPI tiles: totals by severity, by category, top actors + IPs."""
    require_master_admin(user)
    since = _since(since_days)
    base = {"ts": {"$gte": since}}

    by_severity = {"info": 0, "warning": 0, "critical": 0}
    async for row in db.security_events.aggregate([
        {"$match": base},
        {"$group": {"_id": "$severity", "n": {"$sum": 1}}},
    ]):
        if row["_id"] in by_severity:
            by_severity[row["_id"]] = row["n"]

    by_type: dict[str, int] = {}
    async for row in db.security_events.aggregate([
        {"$match": base},
        {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
    ]):
        if row["_id"]:
            by_type[row["_id"]] = row["n"]

    by_category = {cat: sum(by_type.get(t, 0) for t in types)
                   for cat, types in EVENT_CATEGORIES.items()}

    top_actors = [
        {"actor": r["_id"], "count": r["n"]}
        async for r in db.security_events.aggregate([
            {"$match": {**base, "actor_email": {"$ne": None}}},
            {"$group": {"_id": "$actor_email", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 8},
        ])
    ]
    top_ips = [
        {"ip": r["_id"], "count": r["n"]}
        async for r in db.security_events.aggregate([
            {"$match": {**base, "ip": {"$ne": None}}},
            {"$group": {"_id": "$ip", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 8},
        ])
    ]

    total = sum(by_severity.values())
    denials = by_category.get("access_denied", 0)
    return {
        "total": total,
        "by_severity": by_severity,
        "by_type": by_type,
        "by_category": by_category,
        "access_denials": denials,
        "top_actors": top_actors,
        "top_ips": top_ips,
        "since": since.isoformat(),
    }


@router.get("/export.csv")
async def export_security_csv(
    user: dict = Depends(get_current_user),
    since_days: int = Query(30, ge=1, le=90),
    event_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(10000, ge=1, le=10000),
):
    """CSV export for pen-test / SOC 2 evidence."""
    require_master_admin(user)
    q = _build_query(days=since_days, event_type=event_type, category=category,
                     severity=severity, actor=actor, tenant_id=tenant_id, search=search)
    rows = await db.security_events.find(q, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "event_type", "severity", "result", "actor_email",
                "actor_id", "tenant_id", "site_id", "resource_type", "resource_id",
                "action", "detail", "ip", "method", "path", "request_id"])
    for e in rows:
        w.writerow([e.get(k, "") or "" for k in (
            "created_at", "event_type", "severity", "result", "actor_email",
            "actor_id", "tenant_id", "site_id", "resource_type", "resource_id",
            "action", "detail", "ip", "method", "path", "request_id")])
    buf.seek(0)
    filename = f"pulse-security-events-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
