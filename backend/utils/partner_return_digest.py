"""Iter 220r — Return-day welcome-back digest.

When a Partner Engineer's ``availability.resumes_on`` date arrives,
fire a single digest email summarising what they missed and what's
waiting in their referred-gym queue, then auto-flip their availability
back to ``available``.

Design notes
------------

* **Sweep model.** Same shape as ``utils.partner_compliance`` — daily
  ``sweep_once()`` driven by ``run_forever(24)`` from server startup.
  Idempotent: the per-row marker (``availability.welcome_back_fired_on``)
  matches the ``resumes_on`` date that triggered it, so a second run
  on the same return-day is a no-op.

* **Workload.** Counts open ``db.supplier_cases`` rows belonging to
  this engineer's referred-gym supplier rows. Mirrors the
  ``/api/svc/engineer/queue/my-gyms`` semantics introduced in iter
  220p so the digest copy lines up with what the engineer will see
  on the dashboard.

* **Compliance pings.** Surfaces any compliance docs (legacy +
  nested ``compliance_docs.*``) that are already expired or expire
  in the next 30 days, so a returning engineer doesn't trip the
  compliance pause unknowingly.

* **Auto-resume.** After firing, we explicitly flip
  ``availability.status = 'available'`` and clear the
  ``resumes_on`` / ``note`` fields. ``_effective_availability``
  already auto-flips at read time; this write keeps the persisted
  state consistent with what the rest of the platform queries.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from datetime import datetime, timedelta, timezone

from utils.database import db
from utils.partner_emails import send_welcome_back_digest

logger = logging.getLogger(__name__)

# Statuses a `supplier_cases` row is in while the engineer still has
# work to do. Mirrors the open-set used by `/queue/my-gyms` (iter 220p).
OPEN_CASE_STATUSES = (
    "new", "in_progress", "awaiting_parts", "scheduled",
    "awaiting_customer", "viewed",
)

# How many days into the future a compliance doc has to expire to be
# called out in the digest. Matches the loudest of the partner-
# compliance sweep windows (iter 216h281).
COMPLIANCE_HEADS_UP_DAYS = 30


def _today_utc() -> _date:
    return datetime.now(timezone.utc).date()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_until(when: datetime, today: _date) -> int:
    return (_aware(when).date() - today).days


def _format_compliance_line(label: str, expires_at: datetime, today: _date) -> str:
    days = _days_until(expires_at, today)
    on = _aware(expires_at).strftime("%-d %b")
    if days < 0:
        return f"{label} expired on {on} — update to keep getting jobs."
    if days == 0:
        return f"{label} expires today ({on}) — please renew."
    if days <= 7:
        return f"{label} expires in {days} day(s) ({on})."
    return f"{label} expires on {on} (in {days} days)."


def _collect_compliance_warnings(partner: dict, today: _date) -> list[str]:
    """Return a short, human-readable list of compliance items that
    need attention within COMPLIANCE_HEADS_UP_DAYS. Returns an empty
    list when nothing is pending."""
    warnings: list[str] = []
    legacy = {
        "Public liability insurance": partner.get("insurance_expires_at"),
        "Qualifications / certifications": partner.get("qualifications_expires_at"),
    }
    for label, exp in legacy.items():
        if isinstance(exp, datetime):
            days = _days_until(exp, today)
            if days <= COMPLIANCE_HEADS_UP_DAYS:
                warnings.append(_format_compliance_line(label, exp, today))

    nested_labels = {
        "dbs": "DBS check",
        "rtw": "Right-to-Work",
        "safeguarding": "Safeguarding certificate",
        "public_liability": "Public liability cover",
    }
    docs = partner.get("compliance_docs") or {}
    for kind, label in nested_labels.items():
        blob = docs.get(kind) or {}
        exp = blob.get("expires_at")
        if isinstance(exp, datetime):
            days = _days_until(exp, today)
            if days <= COMPLIANCE_HEADS_UP_DAYS:
                warnings.append(_format_compliance_line(label, exp, today))
    return warnings


async def _open_case_counts(partner: dict) -> tuple[int, int]:
    """Return ``(open_cases, overdue_cases)`` for this engineer's
    referred-gym queue. ``overdue`` = open and ``due_at`` already
    in the past (or ``promised_by`` for older rows). 0 / 0 when the
    engineer has no referred gyms yet."""
    email = (partner.get("email") or "").strip().lower()
    if not email:
        return 0, 0
    # Mirrors `/queue/my-gyms` filter: open cases whose supplier_email
    # matches this engineer. The supplier is auto-added at signup, so
    # this is the canonical join key.
    base_filter = {
        "supplier_email": email,
        "status": {"$in": list(OPEN_CASE_STATUSES)},
    }
    try:
        open_count = await db.supplier_cases.count_documents(base_filter)
    except Exception as exc:  # noqa: BLE001
        logger.warning("welcome-back: open-case count failed for %s: %s", email, exc)
        return 0, 0
    if not open_count:
        return 0, 0
    now = datetime.now(timezone.utc)
    overdue_filter = {
        **base_filter,
        "$or": [
            {"due_at": {"$lt": now}},
            {"promised_by": {"$lt": now}},
        ],
    }
    try:
        overdue_count = await db.supplier_cases.count_documents(overdue_filter)
    except Exception as exc:  # noqa: BLE001
        logger.warning("welcome-back: overdue count failed for %s: %s", email, exc)
        overdue_count = 0
    return int(open_count), int(overdue_count)


def _parse_iso_date(s) -> _date | None:
    if not s:
        return None
    try:
        if isinstance(s, str) and "T" in s:
            s = s.split("T", 1)[0]
        return _date.fromisoformat(str(s))
    except Exception:  # noqa: BLE001
        return None


async def _process_partner(partner: dict, today: _date) -> dict | None:
    """Returns a non-empty summary patch when the digest fired, else
    None. Marker is the ``resumes_on`` ISO string we just acted on so
    that re-running the sweep for the same date is a strict no-op
    (and the engineer can take another leave with a different
    ``resumes_on`` later without being marked spammed)."""
    av = partner.get("availability") or {}
    if av.get("status") != "unavailable":
        return None
    resumes_on_iso = av.get("resumes_on")
    resumes_on = _parse_iso_date(resumes_on_iso)
    if not resumes_on or resumes_on > today:
        return None  # not return-day yet
    if av.get("welcome_back_fired_on") == resumes_on_iso:
        return None  # already fired for this leave

    email = (partner.get("email") or "").strip()
    if not email:
        # Without email we can't send; still flip availability + mark
        # the digest as fired so we don't loop forever on the same row.
        await db.partner_engineers.update_one(
            {"id": partner["id"]},
            {"$set": {
                "availability.status": "available",
                "availability.welcome_back_fired_on": resumes_on_iso,
                "availability.resumes_on": None,
                "availability.note": None,
                "availability.updated_at": datetime.now(timezone.utc),
            }},
        )
        return {"sent": False, "reason": "no-email"}

    open_count, overdue_count = await _open_case_counts(partner)
    compliance = _collect_compliance_warnings(partner, today)
    # ``days_away`` is best-effort — derived from the most recent
    # availability_set audit row if we have it, otherwise from
    # ``availability.updated_at``. Pure UX nicety; falling back to
    # None just makes the email say "You're back —" instead of
    # "You've been away for N days —".
    days_away = None
    updated_at = av.get("updated_at")
    if isinstance(updated_at, datetime):
        delta = (datetime.now(timezone.utc).date() - _aware(updated_at).date()).days
        if delta >= 1:
            days_away = delta

    sent = False
    try:
        sent = await send_welcome_back_digest(
            email=email,
            full_name=partner.get("full_name", ""),
            leave_note=av.get("note"),
            days_away=days_away,
            my_gyms_open_count=open_count,
            my_gyms_overdue_count=overdue_count,
            compliance_warnings=compliance,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("welcome-back digest send failed for %s: %s", email, exc)

    # Persist the auto-resume + the per-leave marker.
    await db.partner_engineers.update_one(
        {"id": partner["id"]},
        {"$set": {
            "availability.status": "available",
            "availability.welcome_back_fired_on": resumes_on_iso,
            "availability.resumes_on": None,
            "availability.note": None,
            "availability.updated_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"sent": bool(sent), "open_cases": open_count, "overdue": overdue_count}


async def sweep_once() -> dict:
    """Single pass — fire digests for any partner whose
    ``resumes_on`` date has arrived. Returns a summary so the
    scheduler can log something useful."""
    today = _today_utc()
    cutoff = (today + timedelta(days=1)).isoformat()  # include "today"
    query = {
        "status": "approved",
        "availability.status": "unavailable",
        "availability.resumes_on": {"$ne": None, "$lt": cutoff},
    }
    try:
        partners = await db.partner_engineers.find(query, {"_id": 0}).to_list(2000)
    except Exception as exc:  # noqa: BLE001
        logger.error("welcome-back sweep query failed: %s", exc)
        return {"checked": 0, "sent": 0, "skipped": 0, "errors": 1}

    summary = {"checked": len(partners), "sent": 0, "skipped": 0}
    for partner in partners:
        try:
            outcome = await _process_partner(partner, today)
        except Exception as exc:  # noqa: BLE001
            logger.warning("welcome-back digest failed for partner=%s: %s", partner.get("id"), exc)
            continue
        if outcome is None:
            summary["skipped"] += 1
        elif outcome.get("sent"):
            summary["sent"] += 1
        else:
            summary["skipped"] += 1
    return summary


async def run_forever(interval_hours: int = 24) -> None:
    """Long-running task — invoked from server startup."""
    while True:
        try:
            summary = await sweep_once()
            logger.info("[welcome-back] digest sweep: %s", summary)
        except Exception as exc:  # noqa: BLE001
            logger.error("[welcome-back] sweep crashed: %s", exc)
        await asyncio.sleep(interval_hours * 3600)
