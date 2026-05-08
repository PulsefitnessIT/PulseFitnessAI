"""Marketing Autopilot — closed-loop autonomous campaign manager.

Runs hourly via the sicon_poller cron. Two responsibilities:

  1. Send-when-due sweep — any campaign with `scheduled_for <= now` and
     `status == "scheduled"` is dispatched immediately (re-uses the
     existing `marketing_send_campaign` flow).

  2. Auto post-mortem sweep — any campaign that has been `sent` for ≥72h
     without a cached `post_mortem` gets one generated automatically
     (re-uses the same Claude-powered logic the manual button uses).

Also exposes `compute_optimal_send_window(org_id)` — analyses the org's
recent campaign metrics to find the best day-of-week + hour-of-day
window for next send. Falls back to "Tuesday 18:00" when there's not
enough history yet.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)


# How far back to look when computing the optimal window
WINDOW_LOOKBACK_DAYS = 90
# Min sent campaigns required before we trust the data; below this we
# fall back to the industry-standard fitness-marketing default.
WINDOW_MIN_SAMPLE = 3
# Default fallback (UTC) — Tuesday 18:00 — matches the recurring guidance
# our own post-mortems return when no history is available.
WINDOW_DEFAULT = {"weekday": 1, "hour": 18}  # Mon=0..Sun=6


def _label_window(weekday: int, hour: int) -> str:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{days[weekday]} {h12}{suffix}"


async def compute_optimal_send_window(org_id: str) -> dict:
    """Return {weekday, hour, label, source, sample_size, open_rate}.
    `source` is "history" (computed from this org's data) or "default".
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_LOOKBACK_DAYS)
    rows: list[dict] = []
    try:
        cursor = db.marketing_campaigns.find(
            {"organization_id": org_id, "status": "sent",
             "sent_at": {"$gte": cutoff.isoformat()},
             "metrics.sent": {"$gt": 0}},
            {"_id": 0, "sent_at": 1, "metrics": 1},
        )
        async for c in cursor:
            rows.append(c)
    except Exception as exc:  # pragma: no cover
        logger.info("[autopilot] window history lookup failed: %s", exc)

    if len(rows) < WINDOW_MIN_SAMPLE:
        return {
            **WINDOW_DEFAULT,
            "label": _label_window(WINDOW_DEFAULT["weekday"], WINDOW_DEFAULT["hour"]),
            "source": "default",
            "sample_size": len(rows),
            "open_rate": None,
        }

    # Bucket by (weekday, hour) and average open rate
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for c in rows:
        sent = c.get("metrics", {}).get("sent") or 0
        opened = c.get("metrics", {}).get("opened") or 0
        if not sent:
            continue
        try:
            ts = datetime.fromisoformat((c["sent_at"] or "").replace("Z", "+00:00"))
        except Exception:
            continue
        rate = opened / sent
        buckets[(ts.weekday(), ts.hour)].append(rate)

    if not buckets:
        return {
            **WINDOW_DEFAULT,
            "label": _label_window(WINDOW_DEFAULT["weekday"], WINDOW_DEFAULT["hour"]),
            "source": "default",
            "sample_size": len(rows), "open_rate": None,
        }

    # Pick the bucket with the highest average open rate.
    best_key, best_rate = max(
        ((k, sum(v) / len(v)) for k, v in buckets.items()),
        key=lambda kv: kv[1],
    )
    weekday, hour = best_key
    return {
        "weekday": weekday, "hour": hour,
        "label": _label_window(weekday, hour),
        "source": "history",
        "sample_size": len(rows),
        "open_rate": round(best_rate, 4),
    }


async def compute_per_recipient_windows(
    org_id: str, recipient_emails: list[str],
) -> dict[str, dict]:
    """For each recipient, return their personal best send-hour-of-week
    based on past `marketing_email_events` (open events).

    Falls back to the org-level optimal window for any recipient without
    enough personal history (≥3 opens). Output keyed by lowercase email:

      { "alex@x.com": {weekday: 1, hour: 18, source: "personal", n: 7},
        "ben@x.com":  {weekday: 6, hour: 9,  source: "fallback"} }
    """
    if not recipient_emails:
        return {}

    org_window = await compute_optimal_send_window(org_id)
    fallback = {
        "weekday": org_window["weekday"], "hour": org_window["hour"],
        "source": "fallback", "n": 0,
    }
    out: dict[str, dict] = {}

    # Group opens per (recipient, weekday, hour) in a single aggregation
    try:
        pipe = [
            {"$match": {
                "organization_id": org_id,
                "event_type": "open",
                "recipient_email": {
                    "$in": [e.lower() for e in recipient_emails if e],
                },
                "ts": {"$gte": (datetime.now(timezone.utc) - timedelta(days=180)
                                ).isoformat()},
            }},
            {"$project": {
                "recipient_email": 1,
                "ts": 1,
            }},
        ]
        per_recipient: dict[str, list[tuple[int, int]]] = defaultdict(list)
        async for ev in db.marketing_email_events.aggregate(pipe):
            try:
                ts = datetime.fromisoformat((ev["ts"] or "").replace("Z", "+00:00"))
                per_recipient[ev["recipient_email"]].append((ts.weekday(), ts.hour))
            except Exception:
                continue
        for email, slots in per_recipient.items():
            if len(slots) < 3:
                continue
            counts: dict[tuple[int, int], int] = defaultdict(int)
            for s in slots:
                counts[s] += 1
            best = max(counts.items(), key=lambda kv: kv[1])
            (wd, hr), n = best
            out[email] = {"weekday": wd, "hour": hr, "source": "personal", "n": n}
    except Exception as exc:  # pragma: no cover
        logger.info("[autopilot] per-recipient lookup failed: %s", exc)

    for email in recipient_emails:
        k = (email or "").lower()
        if k and k not in out:
            out[k] = fallback
    return out


def next_window_iso(weekday: int, hour: int) -> str:
    """Next concrete UTC datetime that lands on `weekday` at `hour`."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    # walk forward until weekday matches and time is in the future
    while target.weekday() != weekday or target <= now + timedelta(minutes=15):
        target += timedelta(days=1)
        target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target.isoformat()


# ───────────────────────── Cron sweeps ─────────────────────────


async def _send_due_campaigns() -> int:
    """Dispatch every scheduled campaign whose send time has arrived."""
    sent = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cursor = db.marketing_campaigns.find(
            {"status": "scheduled", "scheduled_for": {"$lte": now_iso}},
            {"_id": 0, "id": 1, "organization_id": 1},
        )
        due = await cursor.to_list(50)
    except Exception as exc:
        logger.info("[autopilot] due-list lookup failed: %s", exc)
        return 0
    if not due:
        return 0
    try:
        from routes.marketing import marketing_send_campaign
    except Exception:
        marketing_send_campaign = None

    for camp in due:
        try:
            if marketing_send_campaign is None:
                # Mark as sent with empty metrics so we don't re-process
                await db.marketing_campaigns.update_one(
                    {"id": camp["id"]},
                    {"$set": {"status": "send_failed",
                              "send_failed_reason": "send fn not available",
                              "send_attempted_at": now_iso}},
                )
                continue
            await marketing_send_campaign(
                campaign_id=camp["id"],
                user={"id": "autopilot", "organization_id": camp["organization_id"],
                      "is_master_admin": True},
            )
            sent += 1
        except Exception as exc:
            logger.warning("[autopilot] send %s failed: %s", camp["id"], exc)
            await db.marketing_campaigns.update_one(
                {"id": camp["id"]},
                {"$set": {"send_failed_reason": str(exc)[:300],
                          "send_attempted_at": now_iso}},
            )
    return sent


async def _auto_post_mortem_sweep() -> int:
    """Find sent campaigns ≥72h old without a cached post_mortem and run it."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    try:
        cursor = db.marketing_campaigns.find(
            {"status": "sent",
             "sent_at": {"$lte": cutoff.isoformat()},
             "metrics.sent": {"$gt": 0},
             "post_mortem": {"$exists": False},
             "auto_pilot.auto_post_mortem": True},
            {"_id": 0, "id": 1, "organization_id": 1},
        )
        targets = await cursor.to_list(20)
    except Exception as exc:
        logger.info("[autopilot] post-mortem list failed: %s", exc)
        return 0

    if not targets:
        return 0

    try:
        from routes.marketing_director import campaign_post_mortem
    except Exception:
        return 0

    n = 0
    for camp in targets:
        try:
            await campaign_post_mortem(
                campaign_id=camp["id"],
                user={"id": "autopilot",
                      "organization_id": camp["organization_id"],
                      "is_master_admin": True},
            )
            n += 1
        except Exception as exc:
            logger.warning(
                "[autopilot] post-mortem %s failed: %s", camp["id"], exc,
            )
    return n


async def _send_due_rescues() -> int:
    """Dispatch approved 1:1 churn rescues whose scheduled_for has arrived.

    Multi-channel smart fallback (per user choice 3d):
      1. Try `primary_channel` (default email)
      2. If that fails or the channel isn't deliverable, fall through to
         `fallback_channel` (default in_app)
      3. Always queue an in_app message at minimum so the member sees it
         next time they log in
    """
    sent = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cursor = db.marketing_churn_rescues.find(
            {"status": "scheduled", "scheduled_for": {"$lte": now_iso}},
            {"_id": 0},
        )
        due = await cursor.to_list(50)
    except Exception as exc:
        logger.info("[autopilot] rescue due-list lookup failed: %s", exc)
        return 0
    if not due:
        return 0

    try:
        from utils.email import send_email  # type: ignore
    except Exception:
        send_email = None  # type: ignore

    for r in due:
        org_id = r["organization_id"]
        member_id = r["member_id"]
        copy = r.get("copy") or {}
        primary = (r.get("primary_channel") or "email").lower()
        fallback = (r.get("fallback_channel") or "in_app").lower()
        first_name = r.get("first_name") or "there"
        delivered_via: list[str] = []
        last_error: str | None = None

        async def _try_email() -> bool:  # noqa: ANN202
            if not send_email:
                return False
            email = r.get("member_email")
            if not email:
                return False
            subject = (copy.get("email_subject") or "").strip()
            body_html = (copy.get("email_body_html") or "").replace(
                "{{first_name}}", first_name,
            )
            if not subject or not body_html:
                return False
            try:
                await send_email(to=email, subject=subject, html=body_html)
                return True
            except Exception as exc:  # pragma: no cover
                nonlocal last_error
                last_error = str(exc)[:300]
                return False

        async def _try_in_app() -> bool:  # noqa: ANN202
            try:
                await db.member_inbox.insert_one({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "member_id": member_id,
                    "kind": "churn_rescue",
                    "title": (copy.get("push_title")
                              or copy.get("email_subject") or "We're thinking of you").strip(),
                    "body": (copy.get("in_app_message") or copy.get("push_body")
                             or copy.get("sms_body") or "").replace(
                                 "{{first_name}}", first_name),
                    "rescue_id": r["id"],
                    "read": False,
                    "created_at": now_iso,
                })
                return True
            except Exception as exc:  # pragma: no cover
                nonlocal last_error
                last_error = str(exc)[:300]
                return False

        async def _try_sms() -> bool:  # noqa: ANN202
            # Twilio integration not yet wired — return False so the
            # fallback chain handles delivery via in_app/email.
            return False

        async def _try_push() -> bool:  # noqa: ANN202
            # Web-push/FCM integration not yet wired — fallback chain
            # handles via in_app message which the member sees in the portal.
            return False

        async def _send_via(channel: str) -> bool:  # noqa: ANN202
            ch = (channel or "").lower()
            if ch == "email":
                return await _try_email()
            if ch == "in_app":
                return await _try_in_app()
            if ch == "sms":
                return await _try_sms()
            if ch == "push":
                return await _try_push()
            return False

        # Smart fallback: primary → fallback → guaranteed in_app
        if await _send_via(primary):
            delivered_via.append(primary)
        elif await _send_via(fallback):
            delivered_via.append(fallback)
        # Always also drop an in_app entry as the receipt of record so
        # the member sees the message next time they log in (unless we
        # already used it as the delivery channel).
        if "in_app" not in delivered_via:
            if await _try_in_app():
                delivered_via.append("in_app")

        update: dict = {
            "status": "sent" if delivered_via else "send_failed",
            "sent_at": now_iso, "delivered_via": delivered_via,
        }
        if last_error and not delivered_via:
            update["send_failed_reason"] = last_error
        await db.marketing_churn_rescues.update_one(
            {"id": r["id"]}, {"$set": update},
        )
        if delivered_via:
            sent += 1
    return sent


async def run_autopilot_cycle() -> dict:
    """Single cron tick. Returns a small summary for log lines."""
    sent = await _send_due_campaigns()
    pms = await _auto_post_mortem_sweep()
    rescues = await _send_due_rescues()
    if sent or pms or rescues:
        logger.info(
            "[autopilot] cycle done — scheduled-sends=%d, post-mortems=%d, rescues=%d",
            sent, pms, rescues,
        )
    return {"scheduled_sent": sent, "post_mortems": pms,
            "rescues_sent": rescues}


__all__ = [
    "compute_optimal_send_window",
    "compute_per_recipient_windows",
    "next_window_iso",
    "run_autopilot_cycle",
]
