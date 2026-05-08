"""GymAxis Memberships — Phase 6: CRM Integration.

Closes the loop between Memberships and Marketing/CRM by detecting
member behaviour signals and auto-firing the right outbound message.

Signal kinds detected:
  • missed_class       — booking flipped to no_show in the last 24h
  • inactive_30d       — no attended class in the last 30+ days (was active before)
  • low_attendance     — booked at least 1 class in last 30d but attended <2
                         (early-warning churn signal)
  • high_engagement    — attended 8+ classes in the last 30 days
                         (celebrate + ask for referral)

Default rules ship enabled out-of-the-box. Each rule has a cooldown so
we don't spam the same member twice for the same signal in a window.
Operators toggle/edit rules via the CRM Loop tab in the Memberships console.

Endpoints:
  GET  /memberships/crm-loop/dashboard  — counts + recent signals + recent sends
  GET  /memberships/crm-loop/rules      — list rules (with org-overrides applied)
  PUT  /memberships/crm-loop/rules/{kind}  — toggle/cooldown override
  POST /memberships/crm-loop/scan       — run detector now (operator)
  GET  /memberships/crm-loop/signals    — recent signals (paged)
  GET  /memberships/crm-loop/sends      — recent triggered sends

Background:
  `run_crm_loop_cycle` is invoked once per poller tick (5 min). It walks
  every org with the memberships module enabled and runs the detector +
  dispatcher idempotently.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email  # noqa: F401  (kept for future external callers)
from utils.memberships_emails import (
    send_high_engagement_celebration,
    send_low_attendance_checkin,
    send_missed_class_followup,
)
from utils.memberships_winback import send_winback_for_member
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-phase6"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


# ─────────────────── Default rule set ───────────────────


SIGNAL_KINDS = ("missed_class", "inactive_30d", "low_attendance", "high_engagement")


DEFAULT_RULES: dict[str, dict] = {
    "missed_class": {
        "enabled": True,
        "cooldown_hours": 72,
        "label": "Missed class follow-up",
        "description": "When a booking flips to no-show, gently invite the member to rebook this week.",
        "severity": "info",
        "tone": "supportive",
    },
    "inactive_30d": {
        "enabled": True,
        "cooldown_hours": 30 * 24,
        "label": "30-day winback",
        "description": "Member hasn't attended in 30+ days — fire the existing winback email (which includes a £ token).",
        "severity": "warning",
        "tone": "supportive",
    },
    "low_attendance": {
        "enabled": True,
        "cooldown_hours": 14 * 24,
        "label": "Low-attendance check-in",
        "description": "Member booked but attended less than 2 of the last 30 days — early-warning churn signal.",
        "severity": "info",
        "tone": "empathic",
    },
    "high_engagement": {
        "enabled": True,
        "cooldown_hours": 30 * 24,
        "label": "High-engagement celebration",
        "description": "Member attended 8+ classes in 30 days — celebrate and prompt a referral.",
        "severity": "positive",
        "tone": "celebratory",
    },
}


async def _resolve_rules_for_org(org_id: str) -> dict[str, dict]:
    """Merge platform defaults with this org's overrides."""
    overrides = await db.crm_loop_rules.find(
        {"organization_id": org_id}, {"_id": 0},
    ).to_list(20)
    by_kind = {o["kind"]: o for o in overrides}
    out: dict[str, dict] = {}
    for kind, base in DEFAULT_RULES.items():
        merged = {**base, "kind": kind}
        ov = by_kind.get(kind)
        if ov:
            if "enabled" in ov:
                merged["enabled"] = bool(ov["enabled"])
            if "cooldown_hours" in ov:
                merged["cooldown_hours"] = int(ov["cooldown_hours"])
        out[kind] = merged
    return out


# ─────────────────── Signal detector ───────────────────


async def _detect_for_member(org_id: str, member: dict, now: datetime) -> list[dict]:
    """Pure detector — returns a list of signals applicable to this member.
    Doesn't write to DB, doesn't fire emails. Idempotent given the input."""
    signals: list[dict] = []
    member_id = member["id"]
    if member.get("status") not in ("active", "trialling"):
        return signals
    last_24h = now - timedelta(hours=24)
    last_30d = now - timedelta(days=30)

    # 1. missed_class — most recent no_show flagged in last 24h
    last_no_show = await db.bookings.find_one(
        {"member_id": member_id, "status": "no_show",
         "marked_at": {"$gte": last_24h.isoformat()}},
        {"_id": 0, "id": 1, "occurrence_id": 1, "marked_at": 1},
        sort=[("marked_at", -1)],
    )
    if last_no_show:
        signals.append({
            "kind": "missed_class",
            "booking_id": last_no_show["id"],
            "occurrence_id": last_no_show.get("occurrence_id"),
            "ref_at": last_no_show.get("marked_at"),
        })

    # 2. low_attendance vs high_engagement — count attended in last 30d
    attended = await db.bookings.count_documents({
        "member_id": member_id, "status": "attended",
        "marked_at": {"$gte": last_30d.isoformat()},
    })
    booked_or_attended = await db.bookings.count_documents({
        "member_id": member_id,
        "status": {"$in": ["booked", "attended", "no_show", "late_cancel"]},
        "booked_at": {"$gte": last_30d.isoformat()},
    })
    if attended >= 8:
        signals.append({
            "kind": "high_engagement",
            "attended_count": attended, "window_days": 30,
        })
    elif booked_or_attended >= 1 and attended < 2:
        signals.append({
            "kind": "low_attendance",
            "attended_count": attended, "window_days": 30,
        })

    # 3. inactive_30d — no attended in 30d AND last attended/booked older than 30d
    if attended == 0:
        last_attended = await db.bookings.find_one(
            {"member_id": member_id, "status": "attended"},
            {"_id": 0, "marked_at": 1},
            sort=[("marked_at", -1)],
        )
        if last_attended and last_attended.get("marked_at", "") < last_30d.isoformat():
            signals.append({
                "kind": "inactive_30d",
                "last_attended_at": last_attended.get("marked_at"),
            })
    return signals


async def _fire_signal(org_id: str, member: dict, signal: dict, rule: dict) -> Optional[dict]:
    """Persist the signal + dispatch the corresponding email if cooldown clear.
    Returns the send record (or None if cooldown-blocked / disabled)."""
    if not rule.get("enabled"):
        return None
    kind = signal["kind"]
    member_id = member["id"]
    cooldown = timedelta(hours=int(rule.get("cooldown_hours", 72)))
    cooldown_floor = (_now() - cooldown).isoformat()
    # Cooldown — last send for this (member, kind) within window?
    recent = await db.crm_loop_sends.find_one(
        {"organization_id": org_id, "member_id": member_id, "kind": kind,
         "sent_at": {"$gte": cooldown_floor}},
        {"_id": 0, "id": 1, "sent_at": 1},
    )
    if recent:
        return None
    # Persist the detected signal regardless (for audit / analytics)
    sig_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "member_id": member_id,
        "kind": kind,
        "payload": {k: v for k, v in signal.items() if k != "kind"},
        "detected_at": _now_iso(),
        "fired": False,
    }
    await db.crm_loop_signals.insert_one(sig_doc)

    # Dispatch the email
    sent_ok = False
    err: Optional[str] = None
    try:
        if kind == "missed_class":
            occ = await db.class_occurrences.find_one(
                {"id": signal.get("occurrence_id")}, {"_id": 0},
            ) if signal.get("occurrence_id") else None
            if occ:
                sent_ok = await send_missed_class_followup(member, occ)
        elif kind == "inactive_30d":
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
            res = await send_winback_for_member(member, org, force=False)
            sent_ok = bool(res and res.get("sent"))
        elif kind == "low_attendance":
            sent_ok = await send_low_attendance_checkin(
                member, signal.get("attended_count", 0), 30,
            )
        elif kind == "high_engagement":
            sent_ok = await send_high_engagement_celebration(
                member, signal.get("attended_count", 0), 30,
            )
    except Exception as exc:
        err = str(exc)[:200]
        logger.warning("[crm-loop] send failed for %s/%s: %s",
                       member_id, kind, err)

    send_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "member_id": member_id,
        "kind": kind,
        "signal_id": sig_doc["id"],
        "sent_at": _now_iso(),
        "ok": sent_ok,
        "error": err,
    }
    await db.crm_loop_sends.insert_one(send_doc)
    if sent_ok:
        await db.crm_loop_signals.update_one(
            {"id": sig_doc["id"]}, {"$set": {"fired": True}},
        )
    return send_doc


async def _run_for_org(org_id: str) -> dict:
    """Detect + dispatch for one org. Idempotent thanks to per-(member,kind)
    cooldown."""
    rules = await _resolve_rules_for_org(org_id)
    enabled_kinds = {k for k, r in rules.items() if r.get("enabled")}
    if not enabled_kinds:
        return {"members_scanned": 0, "signals_fired": 0, "rules_disabled": True}
    now = _now()
    members_scanned = 0
    signals_fired = 0
    async for mem in db.members.find(
        {"organization_id": org_id, "status": {"$in": ["active", "trialling"]}},
        {"_id": 0, "password": 0},
    ):
        members_scanned += 1
        sigs = await _detect_for_member(org_id, mem, now)
        for s in sigs:
            if s["kind"] not in enabled_kinds:
                continue
            res = await _fire_signal(org_id, mem, s, rules[s["kind"]])
            if res and res.get("ok"):
                signals_fired += 1
    return {"members_scanned": members_scanned, "signals_fired": signals_fired}


async def run_crm_loop_cycle() -> dict:
    """Periodic entry point — called by sicon_poller every 5 min.
    Walks every org with the memberships module enabled. Per-cycle audit
    log lives in `db.crm_loop_runs`."""
    from utils.module_access import has_module  # local import — avoids cycle
    started = _now()
    totals = {"orgs": 0, "members_scanned": 0, "signals_fired": 0,
              "started_at": started.isoformat()}
    async for org in db.organizations.find(
        {"status": {"$nin": ["archived", "deleted"]}},
        {"_id": 0, "id": 1, "account_type": 1, "modules": 1},
    ):
        # P1-4: skip orgs without the memberships module — saves DB load.
        if not has_module({}, org, "memberships"):
            continue
        try:
            res = await _run_for_org(org["id"])
            totals["orgs"] += 1
            totals["members_scanned"] += res.get("members_scanned", 0)
            totals["signals_fired"] += res.get("signals_fired", 0)
        except Exception as exc:
            logger.warning("[crm-loop] org %s failed: %s", org["id"], exc)
    totals["finished_at"] = _now_iso()
    await db.crm_loop_runs.insert_one({**totals, "id": str(uuid.uuid4())})
    logger.info("[crm-loop] cycle complete %s", totals)
    return totals


# ─────────────────── Operator endpoints ───────────────────


@router.get(
    "/memberships/crm-loop/dashboard",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_dashboard(
    days: int = Query(default=30, ge=1, le=180),
    user: dict = Depends(get_current_user),
):
    """Counts by signal kind + recent sends for the operator dashboard."""
    org_id = await _require_operator_org(user)
    since = (_now() - timedelta(days=days)).isoformat()
    by_kind: dict[str, dict] = {k: {"signals": 0, "sends": 0, "last_sent_at": None}
                                 for k in SIGNAL_KINDS}
    async for s in db.crm_loop_signals.find(
        {"organization_id": org_id, "detected_at": {"$gte": since}},
        {"_id": 0, "kind": 1},
    ):
        if s["kind"] in by_kind:
            by_kind[s["kind"]]["signals"] += 1
    async for s in db.crm_loop_sends.find(
        {"organization_id": org_id, "sent_at": {"$gte": since}, "ok": True},
        {"_id": 0, "kind": 1, "sent_at": 1},
    ):
        if s["kind"] in by_kind:
            by_kind[s["kind"]]["sends"] += 1
            cur = by_kind[s["kind"]].get("last_sent_at")
            if not cur or s["sent_at"] > cur:
                by_kind[s["kind"]]["last_sent_at"] = s["sent_at"]
    last_run = await db.crm_loop_runs.find_one(
        {}, {"_id": 0}, sort=[("started_at", -1)],
    )
    return {"window_days": days, "by_kind": by_kind, "last_run": last_run}


@router.get(
    "/memberships/crm-loop/rules",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_list_rules(user: dict = Depends(get_current_user)):
    org_id = await _require_operator_org(user)
    rules = await _resolve_rules_for_org(org_id)
    return {"rules": list(rules.values())}


class RuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    cooldown_hours: Optional[int] = Field(default=None, ge=1, le=24 * 90)


@router.put(
    "/memberships/crm-loop/rules/{kind}",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_update_rule(
    kind: str, body: RuleUpdate, user: dict = Depends(get_current_user),
):
    if kind not in DEFAULT_RULES:
        raise HTTPException(404, "Unknown rule kind")
    org_id = await _require_operator_org(user)
    set_doc: dict[str, Any] = {"organization_id": org_id, "kind": kind,
                                "updated_at": _now_iso(),
                                "updated_by": user["id"]}
    if body.enabled is not None:
        set_doc["enabled"] = bool(body.enabled)
    if body.cooldown_hours is not None:
        set_doc["cooldown_hours"] = int(body.cooldown_hours)
    if len(set_doc) == 4:  # only meta — no actual change
        raise HTTPException(400, "Provide enabled or cooldown_hours")
    await db.crm_loop_rules.update_one(
        {"organization_id": org_id, "kind": kind},
        {"$set": set_doc}, upsert=True,
    )
    rules = await _resolve_rules_for_org(org_id)
    return {"ok": True, "rule": rules[kind]}


@router.post(
    "/memberships/crm-loop/scan",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_scan_now(user: dict = Depends(get_current_user)):
    """Manual scan — runs the detector for this org right now (instead
    of waiting for the 5-min poller tick). Idempotent."""
    org_id = await _require_operator_org(user)
    res = await _run_for_org(org_id)
    return {"ok": True, **res}


@router.get(
    "/memberships/crm-loop/signals",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_recent_signals(
    days: int = Query(default=14, ge=1, le=90),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    since = (_now() - timedelta(days=days)).isoformat()
    q: dict[str, Any] = {"organization_id": org_id,
                          "detected_at": {"$gte": since}}
    if kind:
        if kind not in DEFAULT_RULES:
            raise HTTPException(400, "Unknown signal kind")
        q["kind"] = kind
    rows = await db.crm_loop_signals.find(
        q, {"_id": 0},
    ).sort("detected_at", -1).limit(limit).to_list(limit)
    # Hydrate member name
    member_ids = list({r["member_id"] for r in rows})
    members: dict[str, dict] = {}
    if member_ids:
        async for m in db.members.find(
            {"id": {"$in": member_ids}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
        ):
            members[m["id"]] = m
    for r in rows:
        m = members.get(r["member_id"]) or {}
        r["member_name"] = f"{m.get('first_name') or ''} {m.get('last_name') or ''}".strip() or m.get("email") or "Member"
    return {"signals": rows, "count": len(rows)}


@router.get(
    "/memberships/crm-loop/sends",
    dependencies=[Depends(require_module("memberships"))],
)
async def crm_loop_recent_sends(
    days: int = Query(default=14, ge=1, le=90),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    org_id = await _require_operator_org(user)
    since = (_now() - timedelta(days=days)).isoformat()
    rows = await db.crm_loop_sends.find(
        {"organization_id": org_id, "sent_at": {"$gte": since}}, {"_id": 0},
    ).sort("sent_at", -1).limit(limit).to_list(limit)
    member_ids = list({r["member_id"] for r in rows})
    members: dict[str, dict] = {}
    if member_ids:
        async for m in db.members.find(
            {"id": {"$in": member_ids}},
            {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
        ):
            members[m["id"]] = m
    for r in rows:
        m = members.get(r["member_id"]) or {}
        r["member_name"] = f"{m.get('first_name') or ''} {m.get('last_name') or ''}".strip() or m.get("email") or "Member"
    return {"sends": rows, "count": len(rows)}


# ─────────────────── Indexes ───────────────────


async def ensure_phase6_indexes() -> None:
    await db.crm_loop_signals.create_index(
        [("organization_id", 1), ("detected_at", -1)],
    )
    await db.crm_loop_signals.create_index([("member_id", 1), ("kind", 1)])
    await db.crm_loop_sends.create_index(
        [("organization_id", 1), ("sent_at", -1)],
    )
    await db.crm_loop_sends.create_index(
        [("organization_id", 1), ("member_id", 1), ("kind", 1), ("sent_at", -1)],
    )
    await db.crm_loop_rules.create_index(
        [("organization_id", 1), ("kind", 1)], unique=True,
    )
    await db.crm_loop_runs.create_index([("started_at", -1)])


__all__ = ["router", "run_crm_loop_cycle", "ensure_phase6_indexes",
           "DEFAULT_RULES", "SIGNAL_KINDS"]
