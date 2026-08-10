"""Abuse / automated-attack auto-response — escalation ladder (security §33).

Detects abnormal BEHAVIOUR (not "which AI product") from the deterministic
denial signals the authorisation engine already emits, and responds
progressively per actor:

    denials in window   →  level        →  enforcement (on WRITE actions only)
    ───────────────────────────────────────────────────────────────────────
    < THROTTLE           NONE            (nothing)
    ≥ THROTTLE           THROTTLE        monitored + soft cooldown flag
    ≥ STEPUP             STEPUP          force fresh re-authentication (step-up)
    ≥ SUSPEND            SUSPEND         temporarily block sensitive/write ops

Design guarantees (never lock a legitimate user out of the whole app):
  * Only DENIED authorisation attempts increment the counter — normal activity
    never does. A legit user effectively never trips this.
  * READ actions are always allowed; only WRITE/destructive actions are gated.
  * Master/Pulse admins are exempt.
  * Everything is time-boxed with an automatic cooldown, and every escalation
    is written to `security_events` (surfaces in the Master Admin Alert Centre).

Enforcement is on by default but conservative; disable with
ABUSE_GUARD_ENFORCED=false.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo import ReturnDocument

from utils.database import db
from utils.security_events import log_security_event, SEV_WARNING, SEV_CRITICAL

ABUSE_GUARD_ENFORCED = os.environ.get("ABUSE_GUARD_ENFORCED", "true").lower() in ("1", "true", "yes")
WINDOW_SECONDS = int(os.environ.get("ABUSE_WINDOW_SECONDS", "300"))
SUSPEND_SECONDS = int(os.environ.get("ABUSE_SUSPEND_SECONDS", "900"))
T_THROTTLE = int(os.environ.get("ABUSE_THROTTLE_AT", "8"))
T_STEPUP = int(os.environ.get("ABUSE_STEPUP_AT", "15"))
T_SUSPEND = int(os.environ.get("ABUSE_SUSPEND_AT", "25"))

LEVEL_NONE, LEVEL_THROTTLE, LEVEL_STEPUP, LEVEL_SUSPEND = 0, 1, 2, 3
_LEVEL_NAME = {0: "none", 1: "throttle", 2: "step_up", 3: "suspend"}

_COLLECTION = "abuse_counters"

# Actions that abuse controls will gate (writes / destructive). Reads never blocked.
_WRITE = frozenset({
    "create", "update", "delete", "cancel", "approve", "reject", "assign",
    "transition", "status_change", "transfer", "close", "reopen",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _actor_key(user: Optional[dict], ip: Optional[str]) -> str:
    if user:
        if user.get("email"):
            return "user:" + str(user["email"]).strip().lower()
        if user.get("id"):
            return "user:" + str(user["id"])
    return "ip:" + (ip or "unknown")


def _ip(request) -> Optional[str]:
    if request is None:
        return None
    try:
        from utils.security import client_ip
        return client_ip(request)
    except Exception:
        try:
            return request.client.host if request.client else None
        except Exception:
            return None


def _level_for(count: int) -> int:
    if count >= T_SUSPEND:
        return LEVEL_SUSPEND
    if count >= T_STEPUP:
        return LEVEL_STEPUP
    if count >= T_THROTTLE:
        return LEVEL_THROTTLE
    return LEVEL_NONE


async def record_denial(user: Optional[dict], request=None, *, reason: str = "access_denied") -> int:
    """Count one denied authorisation attempt for the actor and escalate if a
    new threshold is crossed. Returns the current level. Best-effort."""
    try:
        ip = _ip(request)
        key = _actor_key(user, ip)
        now = _now()
        doc = await db[_COLLECTION].find_one({"id": key})
        win = _parse(doc.get("window_start")) if doc else None
        if not doc or not win or (now - win).total_seconds() > WINDOW_SECONDS:
            # New / expired window → reset count (keep any active suspension).
            await db[_COLLECTION].update_one(
                {"id": key},
                {"$set": {"id": key, "window_start": now.isoformat(), "count": 1,
                          "last_ip": ip, "actor": (user or {}).get("email"), "ts": now}},
                upsert=True,
            )
            count = 1
            prev_level = 0
        else:
            updated = await db[_COLLECTION].find_one_and_update(
                {"id": key},
                {"$inc": {"count": 1}, "$set": {"last_ip": ip, "ts": now}},
                return_document=ReturnDocument.AFTER,
            )
            count = (updated or {}).get("count", 1)
            prev_level = (doc or {}).get("level", 0)

        level = _level_for(count)
        if level > prev_level and level > LEVEL_NONE:
            cooldown = SUSPEND_SECONDS if level == LEVEL_SUSPEND else WINDOW_SECONDS
            until = now + timedelta(seconds=cooldown)
            await db[_COLLECTION].update_one(
                {"id": key}, {"$set": {"level": level, "until": until.isoformat()}})
            await log_security_event(
                "abuse_detected", user=user, request=request,
                severity=SEV_CRITICAL if level == LEVEL_SUSPEND else SEV_WARNING,
                action="abuse_escalation", result="escalated",
                detail=f"level={_LEVEL_NAME[level]} denials={count} in {WINDOW_SECONDS}s reason={reason}",
                extra={"level": _LEVEL_NAME[level], "count": count, "cooldown_seconds": cooldown},
            )
        return level
    except Exception:
        return LEVEL_NONE


async def _active_state(user: Optional[dict], ip: Optional[str]) -> tuple[int, Optional[datetime]]:
    doc = await db[_COLLECTION].find_one({"id": _actor_key(user, ip)},
                                         {"_id": 0, "level": 1, "until": 1})
    if not doc:
        return LEVEL_NONE, None
    until = _parse(doc.get("until"))
    if not until or _now() > until:
        return LEVEL_NONE, None  # cooldown expired
    return int(doc.get("level", 0)), until


async def check_abuse(user: Optional[dict], request=None, *, action: str = "read") -> None:
    """Enforce the escalation ladder for the caller. No-op for reads, admins,
    or when disabled. Raises 429 (suspended) or 403 step_up_required (step-up)."""
    if not ABUSE_GUARD_ENFORCED:
        return
    if action not in _WRITE:
        return  # reads are never blocked
    if user and (user.get("is_master_admin") or user.get("is_pulse_admin")):
        return

    ip = _ip(request)
    level, until = await _active_state(user, ip)
    if level == LEVEL_NONE:
        return

    if level >= LEVEL_SUSPEND:
        retry = max(1, int((until - _now()).total_seconds())) if until else SUSPEND_SECONDS
        await log_security_event(
            "abuse_action_blocked", user=user, request=request, severity=SEV_CRITICAL,
            action=action, result="blocked", detail="actor temporarily suspended")
        raise HTTPException(
            status_code=429,
            detail="Unusual activity detected — sensitive actions are temporarily paused. Please try again shortly.",
            headers={"Retry-After": str(retry)},
        )

    if level >= LEVEL_STEPUP:
        from utils.step_up import is_step_up_fresh
        if not (user and await is_step_up_fresh(user)):
            from utils.mfa import user_mfa_state
            mfa = await user_mfa_state(user.get("id")) if (user and user.get("id")) else {"enabled": False}
            await log_security_event(
                "abuse_stepup_required", user=user, request=request, severity=SEV_WARNING,
                action=action, result="denied", detail="re-authentication forced by abuse guard")
            raise HTTPException(
                status_code=403,
                detail={"error": "step_up_required", "action": action,
                        "mfa_enabled": bool(mfa.get("enabled")),
                        "reason": "unusual_activity",
                        "message": "Please re-confirm your identity to continue."},
            )
    # THROTTLE level → monitored only (already logged); no hard block.


async def ensure_indexes() -> None:
    try:
        await db[_COLLECTION].create_index("id", unique=True)
        await db[_COLLECTION].create_index("ts", expireAfterSeconds=SUSPEND_SECONDS * 4)
    except Exception:
        pass


__all__ = [
    "ABUSE_GUARD_ENFORCED", "record_denial", "check_abuse", "ensure_indexes",
    "LEVEL_NONE", "LEVEL_THROTTLE", "LEVEL_STEPUP", "LEVEL_SUSPEND",
]
