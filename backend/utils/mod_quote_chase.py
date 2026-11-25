"""MOD quotation follow-ups: chase the customer 2, 4 and 6 weeks after publication."""
import base64
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from utils.database import db

log = logging.getLogger(__name__)

CHASE_WEEKS = (2, 4, 6)
ACTIVE = ("published", "customer_review")


def chase_schedule(published_on: date) -> list[dict]:
    return [{"n": i + 1, "weeks": w, "due": (published_on + timedelta(weeks=w)).isoformat(), "status": "pending"}
            for i, w in enumerate(CHASE_WEEKS)]


# Customer-email state machine (kept separate from the internal task `status`: open → done):
#   awaiting_approval  due while sending is off / wording unapproved — never auto-sent later;
#                      a manager reviews and releases it (backlog)          → ready | cancelled
#   ready              cleared to send                                       → sending
#   sending            claimed by exactly one dispatcher (durable lease)     → sent | failed
#   failed             provider refused; retried up to MAX_ATTEMPTS          → ready (retry) | cancelled
#   sent               provider confirmed (message id recorded)              (final)
#   not_applicable     no published quote / no customer address / quote closed or revised (final)
#   cancelled          manager decision                                      (final)
EMAIL_STATES = ("awaiting_approval", "ready", "sending", "sent", "failed", "not_applicable", "cancelled")
MAX_ATTEMPTS = 3
LEASE_MINUTES = 15


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_indexes():
    await db.mod_quote_followups.create_index([("group_id", 1), ("chase_no", 1), ("revision", 1)], unique=True,
                                              name="uniq_group_chase_revision")


async def _migrate_legacy():
    """Old records only had `customer_email` (dry_run/sent/...). Dry runs were NOT sent → backlog for review."""
    legacy = {"email_status": {"$exists": False}}
    await db.mod_quote_followups.update_many({**legacy, "customer_email": "sent"}, {"$set": {"email_status": "sent"}})
    await db.mod_quote_followups.update_many({**legacy, "customer_email": "dry_run"}, {"$set": {"email_status": "awaiting_approval", "backlog": True}})
    await db.mod_quote_followups.update_many(legacy, {"$set": {"email_status": "not_applicable"}})


async def _create_task(g: dict, item: dict, live: bool) -> dict:
    from routes.mod_ops_quotes import _event, _quotes
    qs = [q for q in await _quotes(g["id"]) if q.get("customer_visible")]
    owner = await db.users.find_one({"id": g.get("created_by")}, {"_id": 0, "id": 1, "email": 1, "full_name": 1}) or {}
    to = (g.get("notified_to") or g["customer"].get("contact_email") or "").strip()
    email_status, reason = ("ready", None) if live else ("awaiting_approval", "Customer emails are switched off or the wording is not approved")
    if not qs:
        email_status, reason = "not_applicable", "No published quotation"
    elif "@" not in to:
        email_status, reason = "not_applicable", "No customer email address"
    doc = {
        "id": str(uuid.uuid4()), "group_id": g["id"], "organization_id": g["organization_id"], "chase_no": item["n"],
        "revision": g.get("revision") or 1, "weeks": item["weeks"], "due": item["due"], "assigned_to": g.get("created_by"),
        "assigned_name": owner.get("full_name") or g.get("created_by_name"), "customer_name": g["customer"]["name"],
        "contact_name": g["customer"].get("contact_name"), "contact_email": to or None,
        "quote_refs": [q.get("sage_quote_number") or q["quote_number"] for q in qs],
        "status": "open", "email_status": email_status, "email_reason": reason, "email_attempts": 0,
        "created_at": date.today().isoformat()}
    try:
        await db.mod_quote_followups.insert_one(doc)
    except DuplicateKeyError:
        return {"duplicate": True}
    if live and owner.get("email"):
        from utils.email import send_email
        await send_email(owner["email"], f"Chase due: {g['customer']['name']} quotation (follow-up {item['n']})",
                         f"<p>Follow-up {item['n']} of {len(CHASE_WEEKS)} is due for {g['customer']['name']}.</p>"
                         "<p>Please call or email the customer and record the outcome in MOD Operations → Quotations → Follow-ups.</p>",
                         [], organization_id=g["organization_id"], kind="mod_quote_chase_internal")
    await _event(g["id"], "follow_up_due", None, version=g.get("revision"),
                 detail={"chase": item["n"], "weeks": item["weeks"], "email_status": email_status})
    return {"email_status": email_status}


async def dispatch_ready(live: bool, templates: dict) -> dict:
    """Send every `ready` customer email exactly once. Claim is atomic + leased, so concurrent runs can't double-send."""
    from routes.mod_ops_quotes import _event, _quotes, pdf_filename, quote_pdf_bytes
    from utils.email import send_email
    from utils.mod_quote_followup_emails import render
    sent = failed = 0
    if not live:
        return {"sent": 0, "failed": 0}
    stale = (datetime.now(timezone.utc) - timedelta(minutes=LEASE_MINUTES)).isoformat()
    # A crashed dispatcher's lease expires; the email may or may not have gone, so a human decides.
    await db.mod_quote_followups.update_many({"email_status": "sending", "email_claimed_at": {"$lt": stale}},
                                             {"$set": {"email_status": "failed", "email_reason": "Send interrupted — check before retrying",
                                                       "email_attempts": MAX_ATTEMPTS}})
    while True:
        f = await db.mod_quote_followups.find_one_and_update(
            {"email_status": "ready"}, {"$set": {"email_status": "sending", "email_claimed_at": _iso_now()}, "$inc": {"email_attempts": 1}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not f:
            break
        g = await db.mod_quote_groups.find_one({"id": f["group_id"]}, {"_id": 0})
        if not g or g["status"] not in ACTIVE or (g.get("revision") or 1) != f.get("revision", 1):
            await db.mod_quote_followups.update_one({"id": f["id"]}, {"$set": {"email_status": "not_applicable",
                                                    "email_reason": "Quotation closed or revised before sending"}})
            continue
        qs = [q for q in await _quotes(g["id"]) if q.get("customer_visible")]
        today_s = date.today().isoformat()
        current = [q for q in qs if (q.get("valid_until") or "9999") >= today_s]
        to_now = (g.get("notified_to") or g["customer"].get("contact_email") or "").strip()
        why = ("No published quotation" if not qs else "Quotation has expired" if not current
               else "Customer email address changed or missing" if to_now != (f.get("contact_email") or "") else None)
        if why:
            await db.mod_quote_followups.update_one({"id": f["id"]}, {"$set": {"email_status": "not_applicable", "email_reason": why}})
            continue
        qs = current
        owner = await db.users.find_one({"id": g.get("created_by")}, {"_id": 0, "full_name": 1}) or {}
        result: dict = {}
        ok = False
        try:
            atts = [{"filename": pdf_filename(q, g), "content": base64.b64encode(await quote_pdf_bytes(q, g)).decode()} for q in qs]
            subject, body = render(templates[str(f["chase_no"])], g, qs, owner.get("full_name") or g.get("created_by_name"))
            ok = bool(await send_email(f["contact_email"], subject, body, atts, organization_id=g["organization_id"],
                                       kind="mod_quote_chase", result_out=result))
        except Exception:
            log.exception("[mod-chase] send failed for follow-up %s", f["id"])
        if ok:
            await db.mod_quote_followups.update_one({"id": f["id"]}, {"$set": {
                "email_status": "sent", "email_sent_at": _iso_now(), "email_message_id": result.get("message_id"),
                "email_attachments": len(qs), "email_reason": None}})
            await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": f["chase_no"]},
                                                 {"$set": {"chase_schedule.$.email_status": "sent"}})
            await _event(g["id"], "follow_up_emailed", None, version=g.get("revision"),
                         detail={"chase": f["chase_no"], "to": f["contact_email"], "attachments": len(qs)})
            sent += 1
        else:
            retry = f["email_attempts"] < MAX_ATTEMPTS
            await db.mod_quote_followups.update_one({"id": f["id"]}, {"$set": {
                "email_status": "failed", "email_reason": "Email provider did not accept the message",
                "email_retry": retry}})
            failed += 1
    return {"sent": sent, "failed": failed}


async def run_chases(today: date | None = None) -> dict:
    """Raise due follow-ups (idempotent) then dispatch any cleared customer emails."""
    today_s = (today or date.today()).isoformat()
    from utils.mod_quote_followup_emails import get_settings
    await _ensure_indexes()
    await _migrate_legacy()
    wording = await get_settings()
    # Customers are only emailed when the switch is on AND an owner has approved the current wording.
    live = os.environ.get("MOD_QUOTE_NOTIFY_LIVE", "").lower() == "true" and wording["approved"]
    # Automatic retry of failed sends that still have attempts left.
    if live:
        await db.mod_quote_followups.update_many({"email_status": "failed", "email_retry": True,
                                                  "email_attempts": {"$lt": MAX_ATTEMPTS}},
                                                 {"$set": {"email_status": "ready", "email_retry": False}})
    done, cancelled = 0, 0
    async for g in db.mod_quote_groups.find({"chase_schedule": {"$elemMatch": {"status": "pending", "due": {"$lte": today_s}}}},
                                            {"_id": 0}):
        for item in g["chase_schedule"]:
            if item["status"] != "pending" or item["due"] > today_s:
                continue
            claim = await db.mod_quote_groups.update_one(
                {"id": g["id"], "chase_schedule": {"$elemMatch": {"n": item["n"], "status": "pending"}}},
                {"$set": {"chase_schedule.$.status": "processing"}})
            if not claim.modified_count:
                continue
            visible = await db.crm2_quotes.find({"mod_group_id": g["id"], "customer_visible": True},
                                                {"_id": 0, "valid_until": 1}).to_list(10)
            expired = bool(visible) and all((q.get("valid_until") or "9999") < today_s for q in visible)
            if g["status"] not in ACTIVE or expired:
                await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": item["n"]},
                                                     {"$set": {"chase_schedule.$.status": "cancelled",
                                                               "chase_schedule.$.reason": "expired" if expired else g["status"]}})
                cancelled += 1
                continue
            try:
                out = await _create_task(g, item, live)
                await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": item["n"]},
                                                     {"$set": {"chase_schedule.$.status": "task_created",
                                                               "chase_schedule.$.processed_on": today_s,
                                                               "chase_schedule.$.email_status": out.get("email_status")}})
                done += 0 if out.get("duplicate") else 1
            except Exception:
                log.exception("[mod-chase] group %s chase %s failed", g["id"], item["n"])
                await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": item["n"]},
                                                     {"$set": {"chase_schedule.$.status": "pending"}})
    dispatched = await dispatch_ready(live, wording["templates"])
    backlog = await db.mod_quote_followups.count_documents({"email_status": "awaiting_approval"})
    return {"processed": done, "cancelled": cancelled, "live_email": live, "wording_approved": wording["approved"],
            "emails_sent": dispatched["sent"], "emails_failed": dispatched["failed"], "awaiting_release": backlog}
