"""Pulse Fitness AI — Comms batch + timezone send dispatcher (Phase 2).

A background worker that turns scheduled campaigns into throttled, timezone
-aware sends. Activation resolves the audience into one queued
``marketing_messages`` row per recipient, each stamped with a
``scheduled_for`` time that bakes in both the batch offset and the timezone
strategy. The loop then drains due rows in capped cycles, sends via Resend
and bumps campaign metrics — so batch size, pacing and per-recipient local
time all fall out of one simple "send when due" query.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from utils.database import db
from utils.email import send_email, PUBLIC_BASE_URL
from routes.comms import render_blocks_to_html, _MODULE_EMAIL_CATEGORY
from routes.marketing.helpers import _new_id

logger = logging.getLogger("comms_dispatch")

_MAX_PER_CYCLE = 50
_DEFAULT_TZ = "Europe/London"

# source → (collection, projection) for resolving recipients
_SEG_SOURCES = {
    "contacts": ("crm_contacts", {"_id": 0, "email": 1, "first_name": 1, "last_name": 1, "company_id": 1, "timezone": 1, "tz": 1, "country": 1}),
    "members": ("members", {"_id": 0, "email": 1, "first_name": 1, "last_name": 1, "timezone": 1, "tz": 1, "country": 1}),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _tz(name):
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def _personalise(text: str, r: dict) -> str:
    fn = (r.get("first_name") or "").strip()
    ln = (r.get("last_name") or "").strip()
    full = (f"{fn} {ln}").strip() or "there"
    base = "https://pulsefitness.ai"
    repl = {
        "{{first_name}}": fn or "there", "{{contact_first_name}}": fn or "there",
        "{{last_name}}": ln, "{{contact_last_name}}": ln, "{{full_name}}": full,
        "{{company_name}}": r.get("company_name") or "",
        "{{unsubscribe_link}}": f"{base}/unsubscribe",
        "{{preferences_link}}": f"{base}/preferences",
        "{{view_in_browser_link}}": f"{base}/c/view",
        "{{forward_to_friend_link}}": f"{base}/c/forward",
    }
    out = text or ""
    for k, v in repl.items():
        out = out.replace(k, v)
    out = re.sub(r"\{\{[^}]+\}\}", "", out)  # blank any remaining tags
    return out


async def _resolve_recipients(camp: dict) -> list[dict]:
    org_id = camp["organization_id"]
    seg_id = camp.get("segment_id")
    inline = camp.get("audience_inline")
    if inline and isinstance(inline, list):
        return [{"email": e, "first_name": "", "last_name": ""} for e in inline if "@" in str(e)]
    if not seg_id:
        return []
    seg = await db.comms_segments.find_one({"id": seg_id, "organization_id": org_id}, {"_id": 0})
    if not seg:
        return []
    from routes.marketing.audiences import _build_filter
    coll_name, proj = _SEG_SOURCES.get(seg.get("source", "contacts"), _SEG_SOURCES["contacts"])
    base = {"organization_id": org_id}
    if coll_name == "crm_contacts":
        base["marketing_consent.email"] = {"$ne": False}
    rule_filter = _build_filter(seg.get("rules") or {}) if seg.get("rules") else {}
    docs = await getattr(db, coll_name).find({**base, **rule_filter}, proj).to_list(length=100000)
    return [d for d in docs if d.get("email") and "@" in d["email"]]


def _scheduled_for(idx: int, base_utc: datetime, sched: dict, recip: dict) -> datetime:
    batch_size = int(sched.get("batch_size") or 0)
    interval = int(sched.get("batch_interval_minutes") or 0)
    offset = timedelta(minutes=(idx // batch_size) * interval) if batch_size > 0 and interval > 0 else timedelta(0)
    if sched.get("timezone_mode") == "recipient_local":
        hour = int(sched.get("local_hour", 9))
        tzname = recip.get("timezone") or recip.get("tz") or sched.get("tz") or _DEFAULT_TZ
        tz = _tz(tzname)
        local_date = base_utc.astimezone(tz)
        target = local_date.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target < local_date:
            target = target + timedelta(days=1)
        return target.astimezone(timezone.utc) + offset
    return base_utc + offset


async def activate_campaign(camp: dict) -> int:
    """Resolve audience → queued messages. Returns recipient count."""
    org_id = camp["organization_id"]
    sched = camp.get("schedule") or {}
    recips = await _resolve_recipients(camp)
    if not recips:
        await db.marketing_campaigns.update_one(
            {"id": camp["id"]},
            {"$set": {"status": "sent", "sent_at": _now().isoformat(),
                      "schedule.dispatch_note": "No recipients matched — nothing to send."}},
        )
        return 0
    base_utc = _parse(sched.get("send_at")) or _now()
    if base_utc < _now():
        base_utc = _now()
    rows = []
    for i, r in enumerate(recips):
        rows.append({
            "id": _new_id(), "organization_id": org_id,
            "campaign_id": camp["id"], "contact_email": r["email"].lower(),
            "contact_name": (f"{r.get('first_name','')} {r.get('last_name','')}").strip(),
            "_recip": {k: r.get(k) for k in ("first_name", "last_name", "company_id")},
            "status": "queued", "scheduled_for": _scheduled_for(i, base_utc, sched, r).isoformat(),
            "sent_at": None, "opened_at": None, "clicked_at": None, "events": [], "created_at": _now().isoformat(),
        })
    # idempotent: clear any prior queue for this campaign first
    await db.marketing_messages.delete_many({"campaign_id": camp["id"], "status": "queued"})
    if rows:
        await db.marketing_messages.insert_many(rows)
    await db.marketing_campaigns.update_one(
        {"id": camp["id"]},
        {"$set": {"status": "sending", "schedule.activated_at": _now().isoformat(),
                  "schedule.total": len(rows), "metrics.queued": len(rows)}},
    )
    logger.info("[comms-dispatch] campaign %s activated — %d recipients", camp["id"], len(rows))
    return len(rows)


def _inject_tracking(html: str, message_id: str) -> str:
    """Rewrite links through the click tracker and append an open pixel."""
    base = (PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return html

    def _rewrite(m):
        url = m.group(2)
        if url.startswith(("#", "mailto:", "tel:", "{{")):
            return m.group(0)
        enc = base64.urlsafe_b64encode(url.encode()).decode()
        return f'{m.group(1)}="{base}/api/comms/t/c/{message_id}?u={enc}"'

    out = re.sub(r'(href)="([^"]+)"', _rewrite, html or "")
    pixel = f'<img src="{base}/api/comms/t/o/{message_id}" width="1" height="1" alt="" style="display:none">'
    return out + pixel


async def _send_due_batch(camp: dict) -> int:
    org_id = camp["organization_id"]
    due = await db.marketing_messages.find(
        {"campaign_id": camp["id"], "status": "queued", "scheduled_for": {"$lte": _now().isoformat()}},
        {"_id": 0},
    ).sort("scheduled_for", 1).limit(_MAX_PER_CYCLE).to_list(length=_MAX_PER_CYCLE)
    if not due:
        return 0
    content = camp.get("content") or {}
    blocks = content.get("blocks") or []
    raw_html = render_blocks_to_html(blocks) if blocks else (content.get("body_html") or "")
    raw_subject = content.get("subject") or camp.get("name") or "Pulse Fitness AI"
    category = _MODULE_EMAIL_CATEGORY.get(camp.get("related_module"), "support")
    sent = bounced = 0
    for m in due:
        r = m.get("_recip") or {}
        html = _inject_tracking(_personalise(raw_html, r), m["id"])
        subject = _personalise(raw_subject, r)
        ok = False
        try:
            ok = await send_email(to=m["contact_email"], subject=subject, html=html,
                                  organization_id=org_id, category=category, kind="campaign")
        except Exception as exc:
            logger.info("[comms-dispatch] send failed %s: %s", m["contact_email"], exc)
        status = "sent" if ok else "bounced"
        sent += 1 if ok else 0
        bounced += 0 if ok else 1
        await db.marketing_messages.update_one(
            {"id": m["id"]}, {"$set": {"status": status, "sent_at": _now().isoformat()}})
    await db.marketing_campaigns.update_one(
        {"id": camp["id"]},
        {"$inc": {"metrics.sent": sent, "metrics.delivered": sent, "metrics.bounced": bounced}},
    )
    return len(due)


async def _cycle():
    now_iso = _now().isoformat()
    # activate scheduled campaigns that are due
    async for camp in db.marketing_campaigns.find(
        {"status": "scheduled", "schedule.send_at": {"$lte": now_iso}}, {"_id": 0},
    ):
        try:
            await activate_campaign(camp)
        except Exception as exc:
            logger.error("[comms-dispatch] activate failed %s: %s", camp.get("id"), exc)
    # drain sending campaigns
    async for camp in db.marketing_campaigns.find({"status": "sending"}, {"_id": 0}):
        try:
            await _send_due_batch(camp)
            remaining = await db.marketing_messages.count_documents(
                {"campaign_id": camp["id"], "status": "queued"})
            if remaining == 0:
                await db.marketing_campaigns.update_one(
                    {"id": camp["id"]},
                    {"$set": {"status": "sent", "sent_at": _now().isoformat()}})
                logger.info("[comms-dispatch] campaign %s fully sent", camp["id"])
        except Exception as exc:
            logger.error("[comms-dispatch] drain failed %s: %s", camp.get("id"), exc)


async def run_comms_dispatch_loop(interval_seconds: float = 30.0):
    logger.info("[comms-dispatch] loop started (interval=%ss)", interval_seconds)
    while True:
        try:
            await _cycle()
        except Exception as exc:  # pragma: no cover
            logger.error("[comms-dispatch] cycle error: %s", exc)
        await asyncio.sleep(interval_seconds)
