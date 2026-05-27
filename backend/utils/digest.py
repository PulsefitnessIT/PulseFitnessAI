"""
Weekly / daily / monthly digest email (P4, Feb 2026).

Turns the existing proactive-nudges engine into an opt-in push channel.
Each user (owner/manager) controls their own preferences:

    { enabled, frequency, day_of_week, channels{warranty, ppm, supplier_drift},
      hour_of_day, last_sent_at }

The poller checks once per hour for users whose next digest is due and
dispatches via Resend. No new external dependency — Resend is already wired
for support escalation.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from utils.database import db
from utils.email import send_email

logger = logging.getLogger(__name__)

# Default preferences applied the first time a user opens /api/digest/preferences.
DEFAULT_PREFS: dict[str, Any] = {
    "enabled": False,
    "frequency": "weekly",      # off | daily | weekly | monthly
    "day_of_week": 0,           # 0=Monday ... 6=Sunday
    "hour_of_day": 8,           # 24-h UTC
    "channels": {
        "warranty_expiring": True,
        "ppm_overdue": True,
        "supplier_sla_drift": True,
        # Iter 220x — Health & Safety incidents (RIDDOR-grade accidents,
        # dangerous occurrences, and any incident escalated to "serious+").
        # ON by default — managers always want visibility on safety items.
        "health_safety_incidents": True,
    },
    "teams_enabled": False,
    "teams_webhook_url": "",
    "email_enabled": True,
    "last_sent_at": None,
}


# ─── Preferences CRUD ───────────────────────────────────────────

async def get_preferences(user_id: str) -> dict:
    doc = await db.digest_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return {**DEFAULT_PREFS, "user_id": user_id}
    merged = {**DEFAULT_PREFS, **doc}
    merged["channels"] = {**DEFAULT_PREFS["channels"], **(doc.get("channels") or {})}
    return merged


async def set_preferences(user_id: str, patch: dict) -> dict:
    current = await get_preferences(user_id)
    # Only allow known keys to be patched; preserve unknown ones read-only.
    allowed = {"enabled", "frequency", "day_of_week", "hour_of_day", "channels",
               "teams_enabled", "teams_webhook_url", "email_enabled"}
    for key in list(patch.keys()):
        if key not in allowed:
            patch.pop(key, None)
    if "frequency" in patch and patch["frequency"] not in ("off", "daily", "weekly", "monthly"):
        patch["frequency"] = "weekly"
    if "day_of_week" in patch:
        patch["day_of_week"] = max(0, min(6, int(patch["day_of_week"])))
    if "hour_of_day" in patch:
        patch["hour_of_day"] = max(0, min(23, int(patch["hour_of_day"])))
    if "channels" in patch and isinstance(patch["channels"], dict):
        merged_channels = {**current["channels"], **patch["channels"]}
        patch["channels"] = {k: bool(v) for k, v in merged_channels.items()}
    if "teams_webhook_url" in patch:
        url = (patch["teams_webhook_url"] or "").strip()
        if url:
            from utils.teams_webhook import validate_webhook_url
            validate_webhook_url(url)
        patch["teams_webhook_url"] = url
    patch["user_id"] = user_id
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.digest_preferences.update_one(
        {"user_id": user_id}, {"$set": patch}, upsert=True,
    )
    return await get_preferences(user_id)


# ─── Scheduling ──────────────────────────────────────────────────

def next_due_at(prefs: dict, from_ts: datetime) -> Optional[datetime]:
    """Return the next UTC datetime the digest should be sent for ``prefs``,
    or ``None`` if disabled / never."""
    if not prefs.get("enabled") or prefs.get("frequency") == "off":
        return None
    hour = int(prefs.get("hour_of_day", 8))
    last = prefs.get("last_sent_at")
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
    except (ValueError, TypeError, AttributeError):
        last_dt = None
    base = last_dt or from_ts.replace(hour=hour, minute=0, second=0, microsecond=0)

    freq = prefs["frequency"]
    if freq == "daily":
        nxt = base + timedelta(days=1) if last_dt else base
    elif freq == "weekly":
        dow = int(prefs.get("day_of_week", 0))
        nxt = base + timedelta(days=7) if last_dt else _next_weekday(from_ts, dow, hour)
    elif freq == "monthly":
        nxt = _first_of_next_month(last_dt or from_ts).replace(hour=hour, minute=0, second=0, microsecond=0)
    else:
        return None
    return nxt


def _next_weekday(from_ts: datetime, dow: int, hour: int) -> datetime:
    days_ahead = (dow - from_ts.weekday()) % 7
    target = from_ts + timedelta(days=days_ahead)
    return target.replace(hour=hour, minute=0, second=0, microsecond=0)


def _first_of_next_month(from_ts: datetime) -> datetime:
    year = from_ts.year + (1 if from_ts.month == 12 else 0)
    month = 1 if from_ts.month == 12 else from_ts.month + 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


def is_due(prefs: dict, now: datetime) -> bool:
    due = next_due_at(prefs, now)
    return bool(due and due <= now)


# ─── Digest content assembly ─────────────────────────────────────

async def build_digest_payload(user: dict, prefs: dict) -> Optional[dict]:
    """Return ``{items, summary}`` or ``None`` when the user has no active items."""
    org_id = user.get("organization_id")
    if not org_id:
        return None
    channels = prefs.get("channels") or {}
    enabled_types = [f"nudge.{k}" for k, v in channels.items()
                     if v and k != "health_safety_incidents"]
    hs_enabled = bool(channels.get("health_safety_incidents"))
    if not enabled_types and not hs_enabled:
        return None

    items: list[dict] = []

    # Nudges (warranty / PPM / supplier drift)
    if enabled_types:
        cursor = db.trust_events.find(
            {"org_id": org_id, "type": {"$in": enabled_types}, "state": "open"},
            {"_id": 0, "id": 1, "type": 1, "severity": 1, "summary": 1,
             "customer_safe_message": 1, "payload": 1},
        ).sort("severity", -1)
        items.extend(await cursor.to_list(50))

    # Health & Safety incidents (Iter 220x — fold into the existing digest
    # instead of a dedicated HSE digest report). Window scales with the
    # digest frequency: daily=24h, weekly=7d, monthly=30d. Surfaces only
    # rows that need eyeballs from a manager — open accidents / dangerous
    # occurrences, RIDDOR-flagged items, or anything auto-escalated.
    if hs_enabled:
        freq = prefs.get("frequency") or "weekly"
        window_days = {"daily": 1, "weekly": 7, "monthly": 30}.get(freq, 7)
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        hs_query = {
            "organization_id": org_id,
            "created_at": {"$gte": since},
            "$or": [
                {"kind": {"$in": ["accident", "dangerous_occurrence"]}},
                {"riddor.status": {"$in": ["potential", "confirmed"]}},
                {"severity": {"$in": ["serious", "major", "fatal"]}},
                {"auto_escalated": True},
            ],
        }
        hs_docs = await db.incidents.find(
            hs_query,
            {"_id": 0, "id": 1, "reference": 1, "kind": 1, "severity": 1,
             "status": 1, "description": 1, "riddor": 1, "fatality": 1,
             "auto_escalated": 1, "created_at": 1},
        ).sort("created_at", -1).to_list(20)
        for doc in hs_docs:
            riddor_state = (doc.get("riddor") or {}).get("status") or "not_assessed"
            sev = doc.get("severity") or "moderate"
            if doc.get("fatality") or riddor_state == "confirmed":
                tone = "high"
            elif sev in ("serious", "major") or riddor_state == "potential":
                tone = "med"
            else:
                tone = "low"
            type_key = "incident.riddor" if riddor_state in ("potential", "confirmed") else \
                       f"incident.{doc.get('kind', 'accident')}"
            short = (doc.get("description") or "").strip()
            if len(short) > 180:
                short = short[:177].rstrip() + "…"
            items.append({
                "id": doc.get("id"),
                "type": type_key,
                "severity": tone,
                "summary": doc.get("reference") or "Incident",
                "customer_safe_message": (
                    f"[{doc.get('reference')}] {short}" if doc.get("reference") else short
                ),
            })

    if not items:
        return None

    summary = f"{len(items)} item(s) need your attention at " + (
        user.get("company_name") or "your organisation"
    )
    return {"items": items, "summary": summary}


def render_digest_html(user: dict, payload: dict, freq_label: str) -> str:
    """Return a compact transactional-email HTML for the digest."""
    first_name = (user.get("full_name") or user.get("email", "").split("@")[0]).split(" ")[0]
    rows = []
    for item in payload["items"]:
        tone = {"high": "#ef4444", "med": "#f59e0b", "low": "#3b82f6"}.get(item.get("severity"), "#64748b")
        title = _humanise_type(item.get("type"))
        body = item.get("customer_safe_message") or item.get("summary") or ""
        rows.append(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #e5e7eb;">'
            f'<div style="display:flex;align-items:flex-start;gap:12px;">'
            f'<div style="width:6px;height:40px;background:{tone};border-radius:3px;"></div>'
            f'<div><div style="font-weight:600;color:#111827;">{title}</div>'
            f'<div style="color:#4b5563;font-size:14px;margin-top:4px;">{body}</div>'
            f'</div></div></td></tr>'
        )
    rows_html = "\n".join(rows)
    app_url = os.environ.get("FRONTEND_URL", "https://app.gymaxis.ai")
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Arial,sans-serif;">
<div style="max-width:600px;margin:24px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
  <div style="background:linear-gradient(90deg,#0055FF,#6366F1);padding:28px;color:#fff;">
    <div style="font-size:14px;opacity:0.85;">Your {freq_label} digest</div>
    <div style="font-size:22px;font-weight:700;margin-top:4px;">Hi {first_name},</div>
    <div style="margin-top:10px;font-size:15px;line-height:1.5;">{payload["summary"]}.</div>
  </div>
  <div style="padding:20px 24px;">
    <table width="100%" cellspacing="0" cellpadding="0">{rows_html}</table>
  </div>
  <div style="padding:20px 24px;background:#f9fafb;text-align:center;">
    <a href="{app_url}/dashboard" style="display:inline-block;background:#0055FF;color:#fff;padding:10px 22px;border-radius:6px;font-weight:600;text-decoration:none;">Open dashboard</a>
    <div style="margin-top:16px;font-size:12px;color:#6b7280;">
      You're receiving this because the {freq_label} digest is on.
      <a href="{app_url}/dashboard" style="color:#0055FF;">Change frequency</a>.
    </div>
  </div>
</div></body></html>"""


def _humanise_type(t: str) -> str:
    return {
        "nudge.warranty_expiring": "Warranty expiring",
        "nudge.ppm_overdue": "Planned maintenance overdue",
        "nudge.supplier_sla_drift": "Supplier performance drift",
        "nudge.password_rotation": "Password rotation due",
        # Iter 220x — H&S incident folds in the same digest
        "incident.accident": "Accident reported",
        "incident.near_miss": "Near miss logged",
        "incident.hazard": "Hazard logged",
        "incident.dangerous_occurrence": "Dangerous occurrence",
        "incident.riddor": "RIDDOR reportable incident",
    }.get(t or "", (t or "Nudge").replace("nudge.", "").replace("incident.", "").replace("_", " ").title())


# ─── Dispatcher ──────────────────────────────────────────────────

async def send_for_user(user: dict, prefs: dict) -> dict:
    """Dispatch the digest across every enabled channel (email + Teams).

    Returns a dict with booleans per channel so the API can distinguish
    "email landed but Teams failed" from "nothing to send".
    """
    payload = await build_digest_payload(user, prefs)
    if not payload:
        return {"email": False, "teams": False, "reason": "no_open_items"}
    freq_label = prefs.get("frequency", "weekly")
    result = {"email": False, "teams": False}

    # Email channel (on by default, unless explicitly disabled).
    if prefs.get("email_enabled", True):
        html = render_digest_html(user, payload, freq_label)
        subject = f"{payload['items'][0].get('severity', 'med').upper()} · " \
                  f"{len(payload['items'])} item(s) need your attention"
        result["email"] = bool(await send_email(user["email"], subject, html))

    # Teams channel (opt-in; requires a validated webhook URL).
    teams_url = (prefs.get("teams_webhook_url") or "").strip()
    if prefs.get("teams_enabled") and teams_url:
        from utils.teams_webhook import render_adaptive_card, post_to_teams
        card = render_adaptive_card(user, payload, freq_label)
        result["teams"] = bool(await post_to_teams(teams_url, card))

    if result["email"] or result["teams"]:
        await db.digest_preferences.update_one(
            {"user_id": user["id"]},
            {"$set": {"last_sent_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    return result


async def dispatch_due_digests() -> dict:
    """Find every user whose digest is due and send it. Never raises."""
    now = datetime.now(timezone.utc)
    totals = {"considered": 0, "sent": 0, "skipped_empty": 0, "errors": 0}
    cursor = db.digest_preferences.find({"enabled": True, "frequency": {"$ne": "off"}}, {"_id": 0})
    prefs_list = await cursor.to_list(2000)
    for prefs in prefs_list:
        totals["considered"] += 1
        if not is_due(prefs, now):
            continue
        try:
            user = await db.users.find_one({"id": prefs["user_id"]}, {"_id": 0})
            if not user:
                continue
            if user.get("role") not in ("owner", "manager"):
                continue
            sent = await send_for_user(user, prefs)
            if sent.get("email") or sent.get("teams"):
                totals["sent"] += 1
            else:
                totals["skipped_empty"] += 1
        except Exception as exc:
            totals["errors"] += 1
            logger.warning(f"[digest] dispatch for {prefs.get('user_id')} failed: {exc}")
    if totals["sent"]:
        logger.info(f"[digest] cycle complete {totals}")
    return totals


async def ensure_digest_indexes() -> None:
    try:
        await db.digest_preferences.create_index("user_id", unique=True)
    except Exception as exc:
        logger.warning(f"[digest] index creation failed: {exc}")
