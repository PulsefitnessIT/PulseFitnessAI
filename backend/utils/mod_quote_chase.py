"""MOD quotation follow-ups: chase the customer 2, 4 and 6 weeks after publication."""
import base64
import logging
import os
import uuid
from datetime import date, timedelta

from utils.database import db

log = logging.getLogger(__name__)

CHASE_WEEKS = (2, 4, 6)
ACTIVE = ("published", "customer_review")


def chase_schedule(published_on: date) -> list[dict]:
    return [{"n": i + 1, "weeks": w, "due": (published_on + timedelta(weeks=w)).isoformat(), "status": "pending"}
            for i, w in enumerate(CHASE_WEEKS)]


async def _process(g: dict, item: dict, live: bool, templates: dict | None = None) -> dict:
    from routes.mod_ops_quotes import _event, _quotes, pdf_filename, quote_pdf_bytes
    from utils.email import send_email
    from utils.mod_quote_followup_emails import DEFAULTS, render
    qs = [q for q in await _quotes(g["id"]) if q.get("customer_visible")]
    owner = await db.users.find_one({"id": g.get("created_by")}, {"_id": 0, "id": 1, "email": 1, "full_name": 1}) or {}
    to = (g.get("notified_to") or g["customer"].get("contact_email") or "").strip()
    outcome = {"customer_email": "not_sent", "to": to or None}
    if not qs:
        outcome["customer_email"] = "no_published_quotes"
    elif "@" not in to:
        outcome["customer_email"] = "no_customer_email"
    elif not live:
        outcome["customer_email"] = "dry_run"
    else:
        atts = [{"filename": pdf_filename(q, g), "content": base64.b64encode(await quote_pdf_bytes(q, g)).decode()} for q in qs]
        subject, body = render((templates or DEFAULTS)[str(item["n"])], g, qs, owner.get("full_name") or g.get("created_by_name"))
        await send_email(to, subject, body, atts, organization_id=g["organization_id"], kind="mod_quote_chase")
        outcome["customer_email"] = "sent"
        outcome["attachments"] = len(atts)
    await db.mod_quote_followups.insert_one({
        "id": str(uuid.uuid4()), "group_id": g["id"], "organization_id": g["organization_id"], "chase_no": item["n"],
        "weeks": item["weeks"], "due": item["due"], "assigned_to": g.get("created_by"),
        "assigned_name": owner.get("full_name") or g.get("created_by_name"), "customer_name": g["customer"]["name"],
        "contact_name": g["customer"].get("contact_name"), "contact_email": to or None,
        "quote_refs": [q.get("sage_quote_number") or q["quote_number"] for q in qs],
        "customer_email": outcome["customer_email"], "status": "open", "created_at": date.today().isoformat()})
    if live and owner.get("email"):
        await send_email(owner["email"], f"Chase due: {g['customer']['name']} quotation (follow-up {item['n']})",
                         f"<p>Follow-up {item['n']} of {len(CHASE_WEEKS)} is due for {g['customer']['name']}.</p>"
                         f"<p>Customer email: {outcome['customer_email'].replace('_', ' ')}. Please call or email the "
                         f"customer and record the outcome in MOD Operations → Quotations → Follow-ups.</p>",
                         [], organization_id=g["organization_id"], kind="mod_quote_chase_internal")
    await _event(g["id"], "follow_up_due", None, version=g.get("revision"),
                 detail={"chase": item["n"], "weeks": item["weeks"], **outcome})
    return outcome


async def run_chases(today: date | None = None) -> dict:
    """Process every chase that is due. Safe to run repeatedly: each chase is claimed atomically."""
    today_s = (today or date.today()).isoformat()
    from utils.mod_quote_followup_emails import get_settings
    wording = await get_settings()
    # Customers are only emailed when the switch is on AND an owner has approved the current wording.
    live = os.environ.get("MOD_QUOTE_NOTIFY_LIVE", "").lower() == "true" and wording["approved"]
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
                                                               "chase_schedule.$.reason": g["status"]}})
                cancelled += 1
                continue
            try:
                out = await _process(g, item, live, wording["templates"])
                await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": item["n"]},
                                                     {"$set": {"chase_schedule.$.status": "done",
                                                               "chase_schedule.$.processed_on": today_s,
                                                               "chase_schedule.$.customer_email": out["customer_email"]}})
                done += 1
            except Exception:
                log.exception("[mod-chase] group %s chase %s failed", g["id"], item["n"])
                await db.mod_quote_groups.update_one({"id": g["id"], "chase_schedule.n": item["n"]},
                                                     {"$set": {"chase_schedule.$.status": "pending"}})
    return {"processed": done, "cancelled": cancelled, "live_email": live, "wording_approved": wording["approved"]}
