"""
GymAxis Service Operations — Engineer Notifications & Web Push.

Iter 216h142 (Phase 4 / Slice 2).

In-app notification centre + Web Push for the Engineer App.
Fed by the diary dispatcher (job_assigned / job_rescheduled) and by
generic platform events.

Collections:
  svc_notifications      — one document per delivery (read/unread state)
  svc_push_subscriptions — Web Push subscription per device

Endpoints (engineer-side, gated by `require_engineer_app_access`):
  GET    /api/svc/engineer/notifications              — list (optional ?unread=true)
  GET    /api/svc/engineer/notifications/unread-count
  POST   /api/svc/engineer/notifications/{id}/read
  POST   /api/svc/engineer/notifications/read-all
  DELETE /api/svc/engineer/notifications/{id}
  POST   /api/svc/engineer/push/subscribe             — store Web Push subscription
  DELETE /api/svc/engineer/push/subscriptions/{hash}  — remove subscription
  GET    /api/svc/engineer/push/vapid-key             — public key for client subscribe
  POST   /api/svc/engineer/push/test                  — fire a test push (self)

Public helpers (used by diary, ppm, etc):
  await create_notification(user_id, org_id, kind, title, body, link=, source=)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.partners import require_engineer_app_access

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/svc/engineer",
    tags=["Service Ops · Engineer Notifications"],
    dependencies=[Depends(require_engineer_app_access)],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


# ── VAPID key management ─────────────────────────────────────────

def _get_or_create_vapid_keys() -> dict:
    """VAPID keys are stable across restarts. We persist them on first
    boot if they're not already in .env, by writing into a Mongo
    singleton document (`svc_vapid_keys`)."""
    pub = os.environ.get("VAPID_PUBLIC_KEY")
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    if pub and priv:
        return {"public": pub, "private": priv,
                "subject": os.environ.get("VAPID_SUBJECT", "mailto:ops@gymaxis.com")}
    return {"public": None, "private": None,
            "subject": "mailto:ops@gymaxis.com"}


async def _ensure_vapid_in_mongo() -> dict:
    """Persist a VAPID keypair in Mongo if env doesn't supply one."""
    env_keys = _get_or_create_vapid_keys()
    if env_keys["public"] and env_keys["private"]:
        return env_keys
    doc = await db.svc_vapid_keys.find_one({"id": "singleton"}, {"_id": 0})
    if doc and doc.get("public") and doc.get("private"):
        return {"public": doc["public"], "private": doc["private"],
                "subject": doc.get("subject") or env_keys["subject"]}
    # Generate a fresh ES256 keypair (P-256). py-vapid exposes `Vapid.from_pem`,
    # so the cleanest portable path is to generate via `cryptography` and
    # export both as base64url for the browser API.
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    import base64
    privkey = ec.generate_private_key(ec.SECP256R1())
    priv_pem = privkey.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_numbers = privkey.public_key().public_numbers()
    raw = b"\x04" + pub_numbers.x.to_bytes(32, "big") + pub_numbers.y.to_bytes(32, "big")
    pub_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    await db.svc_vapid_keys.update_one(
        {"id": "singleton"},
        {"$set": {"id": "singleton", "public": pub_b64, "private": priv_pem,
                   "subject": env_keys["subject"], "created_at": _now()}},
        upsert=True,
    )
    return {"public": pub_b64, "private": priv_pem, "subject": env_keys["subject"]}


# ── Public helper used by diary / ppm / etc ──────────────────────

async def create_notification(
    user_id: str,
    organization_id: str,
    kind: str,
    title: str,
    body: str,
    link: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    fire_push: bool = True,
) -> dict:
    """Create a notification doc + (best-effort) fire a Web Push.
    Never raises — notifications are observability, not business logic."""
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "organization_id": organization_id,
        "kind": kind,
        "title": title[:200],
        "body": body[:500],
        "link": link,
        "source_type": source_type,
        "source_id": source_id,
        "read_at": None,
        "created_at": _now(),
    }
    try:
        await db.svc_notifications.insert_one(doc)
        doc.pop("_id", None)
    except Exception as e:
        logger.warning("notif insert failed: %s", e)
        return {}
    if fire_push:
        try:
            await _dispatch_push(user_id, organization_id, title, body, link, kind)
        except Exception as e:
            logger.warning("push dispatch failed: %s", e)
    return doc


async def _dispatch_push(
    user_id: str, organization_id: str, title: str, body: str,
    link: Optional[str], kind: str,
) -> None:
    """Send a Web Push to every active subscription for this user."""
    keys = await _ensure_vapid_in_mongo()
    if not keys.get("private"):
        return
    subs = await db.svc_push_subscriptions.find(
        {"user_id": user_id, "organization_id": organization_id,
         "active": {"$ne": False}}, {"_id": 0},
    ).to_list(50)
    if not subs:
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — skipping push")
        return
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": "/icons/pwa-192.png",
        "badge": "/icons/pwa-badge.png",
        "tag": kind,
        "data": {"url": link or "/svc/engineer/notifications"},
    })
    for sub in subs:
        info = sub.get("subscription")
        if not info or not info.get("endpoint"):
            continue
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=keys["private"],
                vapid_claims={"sub": keys["subject"]},
                timeout=10,
            )
        except WebPushException as e:  # type: ignore[name-defined]
            code = getattr(getattr(e, "response", None), "status_code", None)
            logger.info("push %s expired (status=%s) — deactivating", info["endpoint"][-20:], code)
            if code in (404, 410):
                await db.svc_push_subscriptions.update_one(
                    {"id": sub["id"]}, {"$set": {"active": False, "deactivated_at": _now()}},
                )
        except Exception as e:
            logger.warning("webpush send failed: %s", e)


# ── Engineer-side endpoints ──────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    of = _of(user)
    q = {**of, "user_id": user["id"]}
    if unread:
        q["read_at"] = None
    rows = await db.svc_notifications.find(q, {"_id": 0}) \
        .sort("created_at", -1).limit(limit).to_list(limit)
    return {"notifications": rows, "count": len(rows)}


@router.get("/notifications/unread-count")
async def unread_count(user=Depends(get_current_user)):
    of = _of(user)
    n = await db.svc_notifications.count_documents(
        {**of, "user_id": user["id"], "read_at": None},
    )
    return {"unread": n}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_notifications.update_one(
        {"id": notif_id, **of, "user_id": user["id"], "read_at": None},
        {"$set": {"read_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_read_all(user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_notifications.update_many(
        {**of, "user_id": user["id"], "read_at": None},
        {"$set": {"read_at": _now()}},
    )
    return {"ok": True, "updated": res.modified_count}


@router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_notifications.delete_one(
        {"id": notif_id, **of, "user_id": user["id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


# ── Web Push ─────────────────────────────────────────────────────

class PushSubIn(BaseModel):
    subscription: dict = Field(..., description="raw PushSubscription JSON")
    user_agent: Optional[str] = Field(None, max_length=400)


@router.get("/push/vapid-key")
async def get_vapid_key(user=Depends(get_current_user)):  # noqa: ARG001
    keys = await _ensure_vapid_in_mongo()
    return {"public_key": keys["public"]}


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:24]


@router.post("/push/subscribe")
async def push_subscribe(body: PushSubIn, user=Depends(get_current_user)):
    of = _of(user)
    sub = body.subscription
    endpoint = (sub or {}).get("endpoint")
    if not endpoint:
        raise HTTPException(400, "subscription.endpoint missing")
    h = _endpoint_hash(endpoint)
    doc = {
        "id": h,
        "user_id": user["id"],
        **of,
        "subscription": sub,
        "user_agent": body.user_agent,
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_push_subscriptions.update_one(
        {"id": h, "user_id": user["id"], **of},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True, "endpoint_hash": h}


@router.delete("/push/subscriptions/{endpoint_hash}")
async def push_unsubscribe(endpoint_hash: str, user=Depends(get_current_user)):
    of = _of(user)
    res = await db.svc_push_subscriptions.delete_one(
        {"id": endpoint_hash, **of, "user_id": user["id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Subscription not found")
    return {"ok": True}


@router.post("/push/test")
async def push_test(user=Depends(get_current_user)):
    """Fire a self-test notification — proves wiring end-to-end."""
    of = _of(user)
    n = await create_notification(
        user_id=user["id"],
        organization_id=of["organization_id"],
        kind="test",
        title="GymAxis push test",
        body="If you see this on your phone or browser, push is working.",
        link="/svc/engineer/notifications",
        source_type="test",
    )
    return {"ok": True, "notification_id": n.get("id")}


# ── Index setup ──────────────────────────────────────────────────

async def ensure_notification_indexes() -> None:
    try:
        await db.svc_notifications.create_index(
            [("organization_id", 1), ("user_id", 1), ("created_at", -1)],
        )
        await db.svc_notifications.create_index(
            [("organization_id", 1), ("user_id", 1), ("read_at", 1)],
        )
        await db.svc_notifications.create_index([("id", 1)], unique=True)
        await db.svc_push_subscriptions.create_index(
            [("organization_id", 1), ("user_id", 1)],
        )
        await db.svc_push_subscriptions.create_index([("id", 1)], unique=True)
    except Exception as e:
        logger.warning("notification index warning: %s", e)


__all__ = ["router", "create_notification", "ensure_notification_indexes"]
