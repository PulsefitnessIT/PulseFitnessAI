"""Pulse Fitness AI — Comms Phase 4: ESP migration, webhooks & public API.

Three capabilities, all self-hosted (no external ESP dependency):

  • Migration/import — upload a CSV export from any ESP (Mailchimp, Klaviyo,
    generic), auto-detect + map columns, create/update contacts AND carry over
    subscription status (unsubscribed/cleaned rows seed ``comms_optouts``).

  • Webhooks — register endpoint URLs subscribed to comms events
    (campaign.sent, email.opened/clicked/unsubscribed/bounced,
    conversion.recorded), delivered with an HMAC ``X-Signature``.

  • Public REST API (/api/v1/comms, X-API-Key) — manage contacts, suppression
    and trigger sends programmatically. Plus an inbound Resend webhook that
    updates delivery metrics and auto-suppresses hard bounces / complaints.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile

from utils.auth import get_current_user, verify_api_key
from utils.database import db
from utils.module_guard import require_module
from routes.marketing.helpers import _new_id, _now_iso, _org_id
from routes.comms import _ANY_COMMS_MODULE, PREF_CATEGORIES

logger = logging.getLogger("comms_growth")

router = APIRouter(prefix="/comms")              # authenticated management
public_router = APIRouter(prefix="/v1/comms")    # X-API-Key public API
webhook_router = APIRouter(prefix="/webhooks")   # inbound provider webhooks

COMMS_EVENTS = [
    "campaign.sent", "email.opened", "email.clicked",
    "email.unsubscribed", "email.bounced", "conversion.recorded",
]
_PREF_IDS = {c["id"] for c in PREF_CATEGORIES}


# ════════════════════════ Webhook delivery (shared) ════════════════════════

async def _deliver(hook: dict, event: str, data: dict) -> None:
    body = json.dumps({"event": event, "data": data, "ts": _now_iso()}, separators=(",", ":"))
    sig = hmac.new((hook.get("secret") or "").encode(), body.encode(), hashlib.sha256).hexdigest()
    status, error = 0, ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(hook["url"], content=body, headers={
                "Content-Type": "application/json",
                "X-Pulse-Event": event,
                "X-Signature": f"sha256={sig}",
            })
            status = r.status_code
    except Exception as exc:  # pragma: no cover — never break the caller
        error = str(exc)[:200]
    await db.comms_webhook_deliveries.insert_one({
        "id": _new_id(), "organization_id": hook["organization_id"], "webhook_id": hook["id"],
        "event": event, "status_code": status, "error": error, "at": _now_iso(),
    })
    await db.comms_webhooks.update_one(
        {"id": hook["id"]},
        {"$set": {"last_delivery": {"event": event, "status_code": status, "at": _now_iso()}}},
    )


async def fire_comms_webhook(org_id: str, event: str, data: dict) -> None:
    """Fire-and-forget: deliver an event to every active subscribed webhook."""
    try:
        hooks = await db.comms_webhooks.find(
            {"organization_id": org_id, "active": True, "events": event}, {"_id": 0},
        ).to_list(length=100)
        for h in hooks:
            asyncio.create_task(_deliver(h, event, data))
    except Exception:
        logger.exception("fire_comms_webhook failed (non-fatal)")


# ════════════════════════ Migration / CSV import ════════════════════════

_EMAIL_HINTS = ("email", "e-mail", "email address", "email_address")
_FIRST_HINTS = ("first", "first name", "first_name", "fname", "given")
_LAST_HINTS = ("last", "last name", "last_name", "lname", "surname", "family")
_COMPANY_HINTS = ("company", "organisation", "organization", "business", "company name")
_STATUS_HINTS = ("status", "subscription", "subscribed", "consent", "email marketing consent",
                 "member rating", "suppressed", "unsubscribed", "opt")
_SUPPRESSED_VALUES = ("unsub", "cleaned", "suppress", "false", "no", "0", "declined", "opted out",
                      "opt_out", "complained", "bounced", "never")


def _guess(headers: list[str], hints: tuple) -> str | None:
    for h in headers:
        hl = h.strip().lower()
        if hl in hints:
            return h
    for h in headers:
        hl = h.strip().lower()
        if any(k in hl for k in hints):
            return h
    return None


def _parse_csv(content: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(content))
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    rows = list(reader)
    return headers, rows


@router.post("/import/preview", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def import_preview(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    headers, rows = _parse_csv(raw)
    if not headers:
        raise HTTPException(400, "Could not read any columns from that file.")
    mapping = {
        "email": _guess(headers, _EMAIL_HINTS),
        "first_name": _guess(headers, _FIRST_HINTS),
        "last_name": _guess(headers, _LAST_HINTS),
        "company": _guess(headers, _COMPANY_HINTS),
        "status": _guess(headers, _STATUS_HINTS),
    }
    return {"columns": headers, "sample_rows": rows[:5], "total_rows": len(rows), "suggested_mapping": mapping}


@router.post("/import/commit", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def import_commit(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    try:
        m = json.loads(mapping)
    except Exception:
        raise HTTPException(400, "Invalid mapping.")
    email_col = m.get("email")
    if not email_col:
        raise HTTPException(400, "An email column mapping is required.")
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    _, rows = _parse_csv(raw)
    created = updated = suppressed = skipped = 0
    for row in rows:
        email = (row.get(email_col) or "").strip().lower()
        if not email or "@" not in email:
            skipped += 1
            continue
        is_suppressed = False
        if m.get("status"):
            val = (row.get(m["status"]) or "").strip().lower()
            if val and any(s in val for s in _SUPPRESSED_VALUES):
                is_suppressed = True
        doc = {
            "first_name": (row.get(m.get("first_name") or "") or "").strip(),
            "last_name": (row.get(m.get("last_name") or "") or "").strip(),
            "company_name": (row.get(m.get("company") or "") or "").strip(),
        }
        existing = await db.crm_contacts.find_one({"organization_id": org_id, "email": email}, {"_id": 1})
        if existing:
            await db.crm_contacts.update_one(
                {"organization_id": org_id, "email": email},
                {"$set": {**{k: v for k, v in doc.items() if v}, "updated_at": _now_iso()}},
            )
            updated += 1
        else:
            await db.crm_contacts.insert_one({
                "id": _new_id(), "organization_id": org_id, "email": email, **doc,
                "lifecycle": "Lead", "source": "esp_import",
                "marketing_consent": {"email": not is_suppressed, "sms": False},
                "created_at": _now_iso(), "updated_at": _now_iso(),
            })
            created += 1
        if is_suppressed:
            await db.comms_optouts.update_one(
                {"organization_id": org_id, "email": email},
                {"$set": {"organization_id": org_id, "email": email, "unsubscribed_all": True,
                          "source": "esp_import", "updated_at": _now_iso()}},
                upsert=True,
            )
            suppressed += 1
    return {"ok": True, "created": created, "updated": updated, "suppressed": suppressed,
            "skipped": skipped, "total": len(rows)}


# ════════════════════════ Webhooks CRUD ════════════════════════

@router.get("/webhooks", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def list_webhooks(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    rows = await db.comms_webhooks.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"webhooks": rows, "events": COMMS_EVENTS}


@router.post("/webhooks", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def create_webhook(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    url = (body.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "A valid https URL is required.")
    events = [e for e in (body.get("events") or []) if e in COMMS_EVENTS] or COMMS_EVENTS
    doc = {
        "id": _new_id(), "organization_id": org_id, "url": url, "events": events,
        "secret": f"whsec_{secrets.token_urlsafe(24)}", "active": True,
        "created_at": _now_iso(), "last_delivery": None,
    }
    await db.comms_webhooks.insert_one(doc)
    doc.pop("_id", None)
    return {"webhook": doc}


@router.put("/webhooks/{webhook_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def update_webhook(webhook_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    upd = {}
    if "active" in body:
        upd["active"] = bool(body["active"])
    if "events" in body:
        upd["events"] = [e for e in (body.get("events") or []) if e in COMMS_EVENTS]
    if "url" in body and str(body["url"]).startswith("http"):
        upd["url"] = body["url"].strip()
    if not upd:
        raise HTTPException(400, "Nothing to update.")
    res = await db.comms_webhooks.update_one({"id": webhook_id, "organization_id": org_id}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Webhook not found")
    return {"ok": True}


@router.delete("/webhooks/{webhook_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def delete_webhook(webhook_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    await db.comms_webhooks.delete_one({"id": webhook_id, "organization_id": org_id})
    return {"ok": True}


@router.post("/webhooks/{webhook_id}/test", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def test_webhook(webhook_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    hook = await db.comms_webhooks.find_one({"id": webhook_id, "organization_id": org_id}, {"_id": 0})
    if not hook:
        raise HTTPException(404, "Webhook not found")
    await _deliver(hook, "ping", {"message": "Test event from Pulse Fitness AI Comms."})
    return {"ok": True}


@router.get("/webhooks/{webhook_id}/deliveries", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def webhook_deliveries(webhook_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    rows = await db.comms_webhook_deliveries.find(
        {"organization_id": org_id, "webhook_id": webhook_id}, {"_id": 0},
    ).sort("at", -1).limit(50).to_list(50)
    return {"deliveries": rows}


# ════════════════════════ API keys CRUD ════════════════════════

@router.get("/api-keys", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def list_api_keys(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    rows = await db.api_keys.find(
        {"organization_id": org_id, "scope": "comms"}, {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    # mask the key — only show last 4
    for r in rows:
        k = r.get("key", "")
        r["key_masked"] = f"pfa_…{k[-4:]}" if len(k) > 4 else "pfa_…"
        r.pop("key", None)
    return {"api_keys": rows}


@router.post("/api-keys", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def create_api_key(body: dict = Body(default_factory=dict), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    key = f"pfa_{secrets.token_urlsafe(32)}"
    doc = {
        "id": _new_id(), "organization_id": org_id, "scope": "comms",
        "name": (body.get("name") or "API key").strip()[:80], "key": key,
        "active": True, "created_at": _now_iso(), "last_used": None,
        "created_by": user.get("email"),
    }
    await db.api_keys.insert_one(doc)
    # return the full key ONCE
    return {"id": doc["id"], "name": doc["name"], "key": key}


@router.delete("/api-keys/{key_id}", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    await db.api_keys.update_one(
        {"id": key_id, "organization_id": org_id, "scope": "comms"}, {"$set": {"active": False}})
    return {"ok": True}


# ════════════════════════ Public REST API (X-API-Key) ════════════════════════

def _api_org(key_doc: dict) -> str:
    org_id = key_doc.get("organization_id")
    if not org_id:
        raise HTTPException(400, "API key has no organisation context.")
    return org_id


@public_router.get("/contacts")
async def api_list_contacts(key: dict = Depends(verify_api_key), limit: int = 100):
    org_id = _api_org(key)
    rows = await db.crm_contacts.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "email": 1, "first_name": 1, "last_name": 1, "company_name": 1},
    ).sort("created_at", -1).limit(min(limit, 500)).to_list(500)
    return {"contacts": rows}


@public_router.post("/contacts")
async def api_upsert_contact(body: dict = Body(...), key: dict = Depends(verify_api_key)):
    org_id = _api_org(key)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email is required.")
    fields = {k: body.get(k) for k in ("first_name", "last_name", "company_name") if body.get(k)}
    existing = await db.crm_contacts.find_one({"organization_id": org_id, "email": email}, {"_id": 0, "id": 1})
    if existing:
        await db.crm_contacts.update_one(
            {"organization_id": org_id, "email": email}, {"$set": {**fields, "updated_at": _now_iso()}})
        return {"ok": True, "id": existing["id"], "created": False}
    cid = _new_id()
    await db.crm_contacts.insert_one({
        "id": cid, "organization_id": org_id, "email": email, **fields,
        "lifecycle": "Lead", "source": "api", "marketing_consent": {"email": True, "sms": False},
        "created_at": _now_iso(), "updated_at": _now_iso(),
    })
    return {"ok": True, "id": cid, "created": True}


@public_router.post("/suppression")
async def api_suppression(body: dict = Body(...), key: dict = Depends(verify_api_key)):
    """Unsubscribe or resubscribe an email. body: {email, action:'unsubscribe'|'resubscribe'}."""
    org_id = _api_org(key)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email is required.")
    action = (body.get("action") or "unsubscribe").lower()
    if action == "resubscribe":
        await db.comms_optouts.update_one(
            {"organization_id": org_id, "email": email},
            {"$set": {"unsubscribed_all": False, "opted_out_categories": [], "updated_at": _now_iso()}}, upsert=True)
    else:
        await db.comms_optouts.update_one(
            {"organization_id": org_id, "email": email},
            {"$set": {"organization_id": org_id, "email": email, "unsubscribed_all": True,
                      "source": "api", "updated_at": _now_iso()}}, upsert=True)
    return {"ok": True, "email": email, "action": action}


@public_router.post("/send")
async def api_send_transactional(body: dict = Body(...), key: dict = Depends(verify_api_key)):
    """Send a one-off transactional email. body: {to, subject, html}.
    Respects the suppression list (won't send to unsubscribed addresses)."""
    org_id = _api_org(key)
    to = (body.get("to") or "").strip().lower()
    subject = (body.get("subject") or "").strip()
    html = body.get("html") or ""
    if not to or "@" not in to or not subject:
        raise HTTPException(400, "to, subject and html are required.")
    opt = await db.comms_optouts.find_one({"organization_id": org_id, "email": to}, {"_id": 0, "unsubscribed_all": 1})
    if opt and opt.get("unsubscribed_all"):
        return {"ok": False, "suppressed": True}
    from utils.email import send_email
    ok = await send_email(to=to, subject=subject, html=html, organization_id=org_id,
                          category="support", kind="transactional")
    return {"ok": bool(ok)}


# ════════════════════════ Inbound Resend webhook ════════════════════════

_HARD_BOUNCE_TYPES = ("email.bounced", "email.complained")


@webhook_router.post("/resend")
async def resend_inbound(request: Request):
    """Inbound Resend events → update campaign metrics + auto-suppress hard
    bounces / complaints. Signature verified when RESEND_WEBHOOK_SECRET is set."""
    raw = await request.body()
    import os
    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    if secret:
        sig = request.headers.get("svix-signature") or request.headers.get("x-signature") or ""
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if expected not in sig:
            raise HTTPException(401, "Invalid signature")
    try:
        evt = json.loads(raw)
    except Exception:
        raise HTTPException(400, "Invalid payload")
    etype = (evt.get("type") or "").lower()
    data = evt.get("data") or {}
    to = data.get("to")
    if isinstance(to, list):
        to = to[0] if to else None
    to = (to or "").strip().lower()
    if not to:
        return {"ok": True}
    # find the most recent message to this recipient to attribute the event
    msg = await db.marketing_messages.find_one(
        {"contact_email": to}, {"_id": 0, "campaign_id": 1, "organization_id": 1}, sort=[("sent_at", -1)])
    org_id = msg.get("organization_id") if msg else None
    if etype == "email.delivered" and msg:
        await db.marketing_campaigns.update_one({"id": msg["campaign_id"]}, {"$inc": {"metrics.delivered": 1}})
    elif etype in _HARD_BOUNCE_TYPES:
        if msg:
            await db.marketing_campaigns.update_one({"id": msg["campaign_id"]}, {"$inc": {"metrics.bounced": 1}})
        if org_id:
            await db.comms_optouts.update_one(
                {"organization_id": org_id, "email": to},
                {"$set": {"organization_id": org_id, "email": to, "unsubscribed_all": True,
                          "source": f"resend:{etype}", "updated_at": _now_iso()}}, upsert=True)
            await fire_comms_webhook(org_id, "email.bounced", {"email": to, "type": etype})
    return {"ok": True}
