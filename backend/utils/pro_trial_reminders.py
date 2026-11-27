"""Pulse Pro trial lifecycle emails.

* "Trial ends tomorrow" — sent once per trial to the org's owner(s) ~24h
  before the earliest bolt-on trial expires, with counts of what the team
  did in each module during the trial.
* "Trial request" — a Lite owner whose trial is used asks for another; the
  Pulse team address (PRO_TRIAL_REQUEST_EMAIL) is alerted.
"""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)

USAGE = {
    "memberships": ("Memberships", [("members", "members added"), ("membership_plans", "membership plans created"),
                                     ("class_bookings", "class bookings")]),
    "marketing": ("Marketing", [("marketing_campaigns", "campaigns created"), ("marketing_journeys", "journeys built")]),
    "crm": ("CRM", [("crm2_companies", "companies added"), ("crm_deals", "deals logged"), ("crm2_quotes", "quotes created")]),
}


def _parse(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


async def trial_usage(org_id: str, since: str) -> list:
    out = []
    for key, (label, items) in USAGE.items():
        counts = []
        for coll, what in items:
            n = await db[coll].count_documents({"organization_id": org_id, "created_at": {"$gte": since}})
            if n:
                counts.append((n, what))
        out.append({"module": key, "label": label, "counts": counts, "total": sum(c[0] for c in counts)})
    return sorted(out, key=lambda m: -m["total"])


def _usage_html(usage: list) -> str:
    rows = []
    for m in usage:
        if m["counts"]:
            body = ", ".join(f"<b>{n}</b> {html.escape(w)}" for n, w in m["counts"])
        else:
            body = "<span style='color:#6E7476'>Not tried yet — worth a look before the trial ends.</span>"
        rows.append(f"<tr><td style='padding:8px 12px;font-weight:700;vertical-align:top'>{m['label']}</td>"
                    f"<td style='padding:8px 12px'>{body}</td></tr>")
    return "<table style='border-collapse:collapse;width:100%;background:#F0F0F0;border-radius:8px'>" + "".join(rows) + "</table>"


async def send_trial_ending_email(org: dict, ends_at: datetime) -> int:
    from utils.email import send_email
    since = org.get("pro_trial_used_at") or (ends_at - timedelta(days=3)).isoformat()
    usage = await trial_usage(org["id"], since)
    top = next((m for m in usage if m["total"]), None)
    owners = await db.users.find({"organization_id": org["id"], "role": "owner", "is_active": {"$ne": False}},
                                 {"_id": 0, "email": 1, "full_name": 1}).to_list(5)
    app_url = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    sent = 0
    for o in owners:
        if not o.get("email"):
            continue
        first = html.escape((o.get("full_name") or "there").split(" ")[0])
        lead = (f"Your team got the most out of <b>{top['label']}</b>." if top
                else "Your team hasn't tried the Pro modules yet — there's still time.")
        body = f"""<div style="font-family:Arial,sans-serif;max-width:600px;color:#1B1C1D">
<h2 style="margin:0 0 8px">Your Pulse Pro trial ends tomorrow</h2>
<p>Hi {first},</p>
<p>The free Pulse Pro trial for <b>{html.escape(org.get('name') or 'your organisation')}</b> ends on
<b>{ends_at.strftime('%A %d %B, %H:%M')} UTC</b>. {lead}</p>
<p style="margin:16px 0 6px;font-weight:700">What you did during the trial</p>
{_usage_html(usage)}
<p style="margin-top:16px">Keep the modules you use: open <b>Account settings → Plan &amp; Billing</b> to choose what stays on.
Your data is kept either way.</p>
{f'<p><a href="{app_url}/pulse" style="background:#f59e0b;color:#1B1C1D;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:700">Open Pulse</a></p>' if app_url else ''}
<p style="color:#6E7476;font-size:12px">Pulse Fitness</p></div>"""
        try:
            await send_email(o["email"], "Your Pulse Pro trial ends tomorrow — here's what you used", body)
            sent += 1
        except Exception:
            logger.warning("[pro-trial] reminder email failed for org %s", org["id"], exc_info=True)
    return sent


async def sweep_trial_reminders(now: datetime | None = None) -> dict:
    """Idempotent: each trial gets one reminder (pro_trial_reminder_sent_at)."""
    now = now or datetime.now(timezone.utc)
    stats = {"checked": 0, "reminded": 0}
    async for org in db.organizations.find(
            {"pro_trial_used_at": {"$exists": True}, "pro_trial_reminder_sent_at": None},
            {"_id": 0, "id": 1, "name": 1, "module_trials": 1, "pro_trial_used_at": 1, "pro_trial_reminder_attempts": 1}):
        stats["checked"] += 1
        ends = [_parse(t.get("expires_at")) for t in (org.get("module_trials") or {}).values() if isinstance(t, dict)]
        ends = [e for e in ends if e]
        if not ends:
            continue
        ends_at = min(ends)
        if not (ends_at - timedelta(hours=24) <= now < ends_at):
            continue
        claimed = await db.organizations.update_one(
            {"id": org["id"], "pro_trial_reminder_sent_at": None},
            {"$set": {"pro_trial_reminder_sent_at": now.isoformat()}})
        if not claimed.modified_count:
            continue
        from utils import email_claims
        key = email_claims.trial_ending_key(org["id"], ends_at.isoformat())
        if not await email_claims.claim(key, sender="pro_trial"):
            continue  # the trial-ending email already went from another sender
        if await send_trial_ending_email(org, ends_at):
            stats["reminded"] += 1
        elif (org.get("pro_trial_reminder_attempts") or 0) < 2:
            # Failed send: allow at most 3 attempts in total, then stop (no endless 5-minute retries).
            await email_claims.release(key)
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"pro_trial_reminder_sent_at": None},
                                                                  "$inc": {"pro_trial_reminder_attempts": 1}})
    logger.info("[pro-trial] reminder sweep %s", stats)
    return stats


async def send_trial_request_alert(org: dict, user: dict, note: str) -> bool:
    from utils.email import send_email
    to = os.environ.get("PRO_TRIAL_REQUEST_EMAIL")
    if not to:
        logger.warning("[pro-trial] PRO_TRIAL_REQUEST_EMAIL not set — request alert not emailed")
        return False
    body = f"""<div style="font-family:Arial,sans-serif;max-width:600px;color:#1B1C1D">
<h2 style="margin:0 0 8px">Another Pulse Pro trial requested</h2>
<p><b>{html.escape(org.get('name') or org['id'])}</b> has already used its free trial and is asking for another.</p>
<table style="border-collapse:collapse">
<tr><td style="padding:4px 12px 4px 0;color:#6E7476">Requested by</td><td>{html.escape(user.get('full_name') or '')} &lt;{html.escape(user.get('email') or '')}&gt;</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#6E7476">Previous trial</td><td>{html.escape(str(org.get('pro_trial_used_at') or '—'))}</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#6E7476">Message</td><td>{html.escape(note) or '—'}</td></tr>
</table>
<p>To allow it: Master Admin → Organisations → {html.escape(org.get('name') or '')} → Billing → <b>Allocate another trial</b>.</p></div>"""
    try:
        await send_email(to, f"Trial request — {org.get('name') or org['id']}", body)
        return True
    except Exception:
        logger.warning("[pro-trial] request alert email failed", exc_info=True)
        return False
