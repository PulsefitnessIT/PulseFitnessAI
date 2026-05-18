"""Iter 216h215 — Recent platform issues (24h) digest.

Combines three live feeds into one passive trust signal for Master Admin:
  • Failed logins (audit_logs where action='login_failed').
  • Client-side render crashes (client_errors collection).
  • Trust events of severity high (trust_events collection).

Returns a counted breakdown so the Master Admin home tile can show a
single number with a per-source legend, and link to each feed's
detailed panel. Green-dot ≤ 5 / amber 6–20 / red > 20.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

router = APIRouter()


@router.get("/master-admin/platform-issues-24h")
async def platform_issues_24h(user: dict = Depends(get_current_user)) -> dict:
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()

    # Failed logins (Iter 216h210 — every reason classification audited).
    failed_logins = await db.audit_logs.count_documents({
        "action": "login_failed",
        "timestamp": {"$gte": cutoff_iso},
    })

    # Client-side render crashes (Iter 216h209 — ModalErrorBoundary).
    client_errors = await db.client_errors.count_documents({
        "server_ts": {"$gte": cutoff_iso},
    })

    # Trust events at high+ severity. Critical = bandit-style + system
    # blow-ups. Medium-severity noise is intentionally excluded.
    trust_high = await db.trust_events.count_documents({
        "created_at": {"$gte": cutoff_iso},
        "severity": {"$in": ["high", "critical"]},
    })

    total = failed_logins + client_errors + trust_high
    if total <= 5:
        tone = "green"
    elif total <= 20:
        tone = "amber"
    else:
        tone = "red"

    return {
        "total": total,
        "tone": tone,
        "breakdown": [
            {
                "key": "failed_logins",
                "label": "Failed logins",
                "count": failed_logins,
                "panel": "login-events",
                "hint": "Wrong username / password / portal mismatch / lockout / rate-limit",
            },
            {
                "key": "client_errors",
                "label": "Client crashes",
                "count": client_errors,
                "panel": "client-errors",
                "hint": "React render errors caught by ModalErrorBoundary",
            },
            {
                "key": "trust_high",
                "label": "Trust events (high+)",
                "count": trust_high,
                "panel": "trust",
                "hint": "Backend 5xx, slow API, brute-force, self-heal failures",
            },
        ],
        "window_hours": 24,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
