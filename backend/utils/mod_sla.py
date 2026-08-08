"""MOD SLA targets + live status computation.

Response / fix targets differ for UK vs OVERSEAS sites (overseas jobs
inherently take longer — travel, customs, local providers). Each MOD
site can override the defaults via ``organization.sla_response_hours`` /
``organization.sla_fix_hours``; when unset the site falls back to the
UK-or-overseas default below.

Nothing here is classified — pure durations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

# Default targets (hours) — deliberately more generous for overseas.
DEFAULT_SLA = {
    "uk":       {"response_hours": 24,  "fix_hours": 72},   # 1 day / 3 days
    "overseas": {"response_hours": 48,  "fix_hours": 168},  # 2 days / 7 days
}

# When a fault is still open, flag "due soon" once we're within this
# fraction of the target remaining.
_DUE_SOON_FRACTION = 0.2


def _to_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def sla_targets_for_org(org: dict) -> dict:
    """Resolve the effective SLA targets for a MOD site org doc."""
    is_overseas = bool(org.get("is_overseas"))
    base = DEFAULT_SLA["overseas"] if is_overseas else DEFAULT_SLA["uk"]
    resp = org.get("sla_response_hours")
    fix = org.get("sla_fix_hours")
    resp_custom = resp not in (None, "", 0)
    fix_custom = fix not in (None, "", 0)
    return {
        "is_overseas": is_overseas,
        "response_hours": int(resp) if resp_custom else base["response_hours"],
        "fix_hours": int(fix) if fix_custom else base["fix_hours"],
        "response_source": "custom" if resp_custom else "default",
        "fix_source": "custom" if fix_custom else "default",
        "default_response_hours": base["response_hours"],
        "default_fix_hours": base["fix_hours"],
    }


def _fmt_remaining(delta: timedelta) -> str:
    total_h = delta.total_seconds() / 3600.0
    overdue = total_h < 0
    total_h = abs(total_h)
    if total_h >= 24:
        val = f"{total_h / 24:.1f}d"
    else:
        val = f"{total_h:.0f}h"
    return f"{val} overdue" if overdue else f"{val} left"


def compute_sla_status(issue: dict, org: dict, now: Optional[datetime] = None) -> dict:
    """Compute the live SLA state for a single fault.

    Returns a dict safe to embed on an API response. ``state`` is one of
    ``met`` / ``on_track`` / ``due_soon`` / ``breached``.
    """
    now = now or datetime.now(timezone.utc)
    targets = sla_targets_for_org(org)
    created = _to_dt(issue.get("created_at")) or now
    resp_due = created + timedelta(hours=targets["response_hours"])
    fix_due = created + timedelta(hours=targets["fix_hours"])

    first_response = _to_dt(issue.get("first_response_at")) or _to_dt(issue.get("engineer_assigned_at"))
    resolved_at = _to_dt(issue.get("resolved_at")) if (issue.get("status") == "resolved") else None

    # Response leg.
    if first_response:
        response_breached = first_response > resp_due
        response_met = not response_breached
    else:
        response_breached = now > resp_due
        response_met = False

    # Fix leg.
    if resolved_at:
        fix_breached = resolved_at > fix_due
        fix_met = not fix_breached
    else:
        fix_breached = now > fix_due
        fix_met = False

    # Overall.
    if resolved_at:
        state = "breached" if fix_breached else "met"
    elif response_breached or fix_breached:
        state = "breached"
    else:
        remaining = (fix_due - now).total_seconds()
        window = targets["fix_hours"] * 3600.0
        state = "due_soon" if (window > 0 and remaining <= window * _DUE_SOON_FRACTION) else "on_track"

    return {
        "response_hours": targets["response_hours"],
        "fix_hours": targets["fix_hours"],
        "is_overseas": targets["is_overseas"],
        "response_source": targets["response_source"],
        "fix_source": targets["fix_source"],
        "response_due_at": resp_due.isoformat(),
        "fix_due_at": fix_due.isoformat(),
        "response_breached": response_breached,
        "response_met": response_met,
        "fix_breached": fix_breached,
        "fix_met": fix_met,
        "state": state,
        "response_remaining_label": _fmt_remaining(resp_due - now) if not resolved_at else ("met" if response_met else "breached"),
        "fix_remaining_label": _fmt_remaining(fix_due - now) if not resolved_at else ("met" if fix_met else "breached"),
    }
