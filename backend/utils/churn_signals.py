"""Churn-risk detection — multi-signal detector for the AI Creative
Director's True 1:1 win-back personalization.

For each active member of an org, we look for the *exact behavioural
exit signal* — not a generic risk score — so that downstream copy can
say things like:

  "We noticed you stopped booking Spin after the schedule moved to 7am
   — try our new 6:30pm Spin slot."

Six signals are detected, prioritised in this order (first match wins):

  1. payment_failure          — a recent failed transaction
  2. frozen_membership        — currently on a freeze
  3. late_cancel_streak       — cancelled or no-showed last 2 bookings
  4. class_affinity_drop      — heavy regular of one class type, then
                                stopped booking *that specific class*
                                (most powerful signal for 1:1 copy)
  5. frequency_drop           — visits in last 14d ≤ 50% of the prior
                                14-28d window (and previously regular)
  6. lapsed_visit             — no visit in 14+ days (catch-all)

Each result returns enough context for Claude to write a hyper-specific
rescue copy:
  - member id/name/email/first_name
  - signal, signal_label, signal_evidence (1-line human-readable)
  - last_class_name (when class-specific)
  - days_since_last_visit
  - tenure_days, lifetime_value_gbp
  - primary_recommendation (the lever the rescue should pull)
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.database import db

logger = logging.getLogger(__name__)


SIGNAL_LABELS: dict[str, str] = {
    "payment_failure":     "Payment failure",
    "frozen_membership":   "Plan frozen",
    "late_cancel_streak":  "Cancelled/no-showed last 2 bookings",
    "class_affinity_drop": "Stopped booking favourite class",
    "frequency_drop":      "Visits dropped >50%",
    "lapsed_visit":        "No visit in 14+ days",
}


SIGNAL_LEVERS: dict[str, str] = {
    "payment_failure": (
        "Quietly fix the payment friction; reassure them their place is "
        "safe; offer one-tap card update."
    ),
    "frozen_membership": (
        "No-pressure return invitation; celebrate one-click unfreeze; "
        "highlight any new offerings since they paused."
    ),
    "late_cancel_streak": (
        "Acknowledge life gets busy; offer to swap to a flexible class "
        "type or different time slot."
    ),
    "class_affinity_drop": (
        "Reference the SPECIFIC class they used to love by name and "
        "explain what's changed (or hasn't); offer a fresh slot."
    ),
    "frequency_drop": (
        "Notice the dip warmly; reignite habit with a 7-day mini-streak "
        "or a coach check-in."
    ),
    "lapsed_visit": (
        "Warm 'we miss you' tone; remind them what they loved; offer a "
        "low-friction return slot."
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# ───────────────────────── Public API ─────────────────────────


async def detect_churn_signals(
    org_id: str,
    *,
    lapsed_days: int = 14,
    affinity_min_history: int = 3,
    affinity_window_days: int = 21,
    limit: int = 100,
) -> list[dict]:
    """Return up to `limit` at-risk members for an org, each with a
    detected primary signal + the context Claude needs to write hyper-
    personal rescue copy.

    Sorted by signal severity (payment_failure first), then lifetime
    value descending (high-value lapsed members come first).
    """
    now = _now()
    affinity_cutoff = now - timedelta(days=affinity_window_days)
    history_window = now - timedelta(days=90)

    members = await db.members.find(
        {"organization_id": org_id, "status": {"$in": ["active", "frozen"]}},
        {"_id": 0, "password": 0},
    ).to_list(5000)
    if not members:
        return []
    by_id = {m["id"]: m for m in members}

    # ── Visit counts (90d, 14d, 14-28d) — combine checkins + attended bookings
    checkins_by_member: dict[str, list[datetime]] = defaultdict(list)
    async for cin in db.member_checkins.find(
        {"organization_id": org_id, "at": {"$gte": _iso(history_window)}},
        {"_id": 0, "member_id": 1, "at": 1},
    ):
        ts = _parse_iso(cin.get("at"))
        if ts and cin.get("member_id") in by_id:
            checkins_by_member[cin["member_id"]].append(ts)

    bookings_by_member: dict[str, list[dict]] = defaultdict(list)
    async for b in db.bookings.find(
        {"organization_id": org_id, "booked_at": {"$gte": _iso(history_window)}},
        {"_id": 0, "member_id": 1, "status": 1, "occurrence_id": 1, "booked_at": 1,
         "class_template_id": 1, "class_name": 1},
    ):
        if b.get("member_id") in by_id:
            bookings_by_member[b["member_id"]].append(b)

    # ── Resolve class names for bookings (template lookup, batched)
    occ_ids: set[str] = set()
    for blist in bookings_by_member.values():
        for b in blist:
            if b.get("occurrence_id") and not b.get("class_name"):
                occ_ids.add(b["occurrence_id"])
    occ_to_template: dict[str, str] = {}
    if occ_ids:
        async for occ in db.class_occurrences.find(
            {"id": {"$in": list(occ_ids)}},
            {"_id": 0, "id": 1, "template_id": 1, "starts_at": 1},
        ):
            if occ.get("template_id"):
                occ_to_template[occ["id"]] = occ["template_id"]
    template_ids = set(occ_to_template.values())
    template_names: dict[str, str] = {}
    if template_ids:
        async for tpl in db.class_templates.find(
            {"id": {"$in": list(template_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            if tpl.get("name"):
                template_names[tpl["id"]] = tpl["name"]

    def _class_name_for_booking(b: dict) -> Optional[str]:
        if b.get("class_name"):
            return b["class_name"]
        tpl_id = occ_to_template.get(b.get("occurrence_id") or "")
        return template_names.get(tpl_id) if tpl_id else None

    # ── Recent payment failures
    recent_failure_ids: set[str] = set()
    fail_cutoff = now - timedelta(days=21)
    async for p in db.payment_transactions.find(
        {"organization_id": org_id, "payment_status": "failed",
         "created_at": {"$gte": _iso(fail_cutoff)}},
        {"_id": 0, "member_id": 1},
    ):
        if p.get("member_id"):
            recent_failure_ids.add(p["member_id"])

    out: list[dict] = []
    for m in members:
        mid = m["id"]
        first_name = m.get("first_name") or ""
        full_name = f"{first_name} {m.get('last_name') or ''}".strip() or m.get("email") or "Member"
        joined = _parse_iso(m.get("created_at"))
        tenure_days = (now - joined).days if joined else 0

        all_visits = sorted(checkins_by_member.get(mid, []), reverse=True)
        attended_bookings = [b for b in bookings_by_member.get(mid, [])
                             if b.get("status") == "attended"]
        attended_visit_dates = [
            _parse_iso(b.get("booked_at")) for b in attended_bookings
        ]
        all_visit_dates = sorted(
            [d for d in (all_visits + [d for d in attended_visit_dates if d]) if d],
            reverse=True,
        )
        days_since_last_visit = (
            (now - all_visit_dates[0]).days if all_visit_dates else None
        )
        last_visit_iso = _iso(all_visit_dates[0]) if all_visit_dates else None

        visits_14d = sum(1 for d in all_visit_dates if d >= now - timedelta(days=14))
        visits_14_28d = sum(
            1 for d in all_visit_dates
            if now - timedelta(days=28) <= d < now - timedelta(days=14)
        )

        signals: list[dict] = []
        last_class_name: Optional[str] = None

        # 1. payment_failure — highest severity for accounts intervention
        if mid in recent_failure_ids:
            signals.append({
                "signal": "payment_failure",
                "evidence": "Recent payment attempt failed in the last 21 days.",
                "severity": 95,
            })

        # 2. frozen_membership
        if m.get("status") == "frozen":
            signals.append({
                "signal": "frozen_membership",
                "evidence": "Membership is currently on freeze.",
                "severity": 80,
            })

        # 3. late_cancel_streak — last 2 chronological bookings cancelled / no-showed / late_cancel
        member_bookings = sorted(
            bookings_by_member.get(mid, []),
            key=lambda b: b.get("booked_at") or "",
            reverse=True,
        )
        last_two = member_bookings[:2]
        if len(last_two) >= 2 and all(
            b.get("status") in ("cancelled", "no_show", "late_cancel")
            for b in last_two
        ):
            cn = _class_name_for_booking(last_two[0])
            signals.append({
                "signal": "late_cancel_streak",
                "evidence": (
                    "Cancelled or no-showed the last 2 bookings"
                    + (f" (most recent: {cn})." if cn else ".")
                ),
                "severity": 75,
            })
            if cn:
                last_class_name = cn

        # 4. class_affinity_drop — booked one specific class ≥3x in 90d, but
        #    zero of that class in last `affinity_window_days` and was their
        #    most-booked class.
        attended_class_counter: Counter = Counter()
        last_attended_per_class: dict[str, datetime] = {}
        for b in member_bookings:
            if b.get("status") != "attended":
                continue
            cn = _class_name_for_booking(b)
            if not cn:
                continue
            attended_class_counter[cn] += 1
            ts = _parse_iso(b.get("booked_at"))
            if ts and (cn not in last_attended_per_class
                       or last_attended_per_class[cn] < ts):
                last_attended_per_class[cn] = ts

        if attended_class_counter:
            top_class, top_count = attended_class_counter.most_common(1)[0]
            top_last = last_attended_per_class.get(top_class)
            if (top_count >= affinity_min_history
                    and top_last is not None
                    and top_last < affinity_cutoff):
                days_since_top = (now - top_last).days
                signals.append({
                    "signal": "class_affinity_drop",
                    "evidence": (
                        f"Booked {top_class} {top_count} times in the last 90 days "
                        f"but hasn't attended it for {days_since_top} days."
                    ),
                    "severity": 70,
                    "last_class_name": top_class,
                    "last_class_count": top_count,
                    "days_since_top_class": days_since_top,
                })
                last_class_name = top_class

        # 5. frequency_drop — was regular, halved
        if visits_14_28d >= 4 and visits_14d <= visits_14_28d / 2:
            signals.append({
                "signal": "frequency_drop",
                "evidence": (
                    f"Visited {visits_14_28d} times in days 14-28 but only "
                    f"{visits_14d} time{'s' if visits_14d != 1 else ''} in the last 14 days."
                ),
                "severity": 60,
                "visits_14d": visits_14d,
                "visits_14_28d": visits_14_28d,
            })

        # 6. lapsed_visit — catch-all, only fire if no other signal
        if (days_since_last_visit is not None
                and days_since_last_visit >= lapsed_days):
            signals.append({
                "signal": "lapsed_visit",
                "evidence": (
                    f"No visit in {days_since_last_visit} days "
                    f"(last visit {last_visit_iso[:10] if last_visit_iso else 'never'})."
                ),
                "severity": 50,
                "days_since_last_visit": days_since_last_visit,
            })
        elif days_since_last_visit is None and tenure_days >= lapsed_days:
            signals.append({
                "signal": "lapsed_visit",
                "evidence": (
                    f"Joined {tenure_days} days ago and we have no recorded visit."
                ),
                "severity": 55,
                "days_since_last_visit": None,
            })

        if not signals:
            continue

        # Highest severity wins
        signals.sort(key=lambda s: -s["severity"])
        primary = signals[0]
        ltv_gbp = round((m.get("lifetime_value_pence") or 0) / 100.0, 2)

        out.append({
            "member_id": mid,
            "first_name": first_name,
            "full_name": full_name,
            "email": m.get("email"),
            "tenure_days": tenure_days,
            "lifetime_value_gbp": ltv_gbp,
            "days_since_last_visit": days_since_last_visit,
            "last_visit_at": last_visit_iso,
            "visits_14d": visits_14d,
            "visits_14_28d": visits_14_28d,
            "last_class_name": last_class_name or primary.get("last_class_name"),
            "signal": primary["signal"],
            "signal_label": SIGNAL_LABELS.get(primary["signal"], primary["signal"]),
            "signal_evidence": primary["evidence"],
            "signal_severity": primary["severity"],
            "primary_recommendation": SIGNAL_LEVERS.get(primary["signal"], ""),
            "all_signals": [s["signal"] for s in signals],
        })

    out.sort(key=lambda r: (-r["signal_severity"], -r["lifetime_value_gbp"]))
    return out[:limit]


__all__ = ["detect_churn_signals", "SIGNAL_LABELS", "SIGNAL_LEVERS"]
