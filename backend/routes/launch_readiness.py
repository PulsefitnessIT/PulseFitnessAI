"""Org-level pre-launch readiness — Iter 216bc.

Three small but launch-critical surfaces grouped here:
  • Email sender branding: per-org "friendly From" + reply-to so a
    customer can read "National Dance Studio <noreply@pulsefitness.ai>"
    instead of generic "Pulse Fitness".
  • Sample-data toggle for new orgs — one click to seed a tiny demo
    membership / class set so operators can play before importing.
  • In-product feedback intake — feeds the existing Sales Insights
    panel as a second data source.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _org(user: dict) -> str:
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "User has no organization")
    return org_id


def _is_owner(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    return user.get("is_master_admin") or role in {"owner", "manager", "master_admin"}


# ═══════════════════ Email sender branding ════════════════════════


class EmailSenderBody(BaseModel):
    friendly_name: str | None = Field(None, max_length=80)
    reply_to: EmailStr | None = None


@router.get("/launch/email-sender")
async def get_email_sender(user: dict = Depends(get_current_user)):
    """Return the org's current sender branding for display."""
    org_id = await _org(user)
    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "name": 1, "email_sender_friendly_name": 1, "email_sender_reply_to": 1, "email_sender_verified_domain": 1},
    ) or {}
    return {
        "friendly_name": org.get("email_sender_friendly_name") or org.get("name") or "",
        "reply_to": org.get("email_sender_reply_to") or "",
        "verified_domain": org.get("email_sender_verified_domain"),
        "preview_from": _build_preview(org),
    }


def _build_preview(org: dict) -> str:
    fn = (org.get("email_sender_friendly_name") or org.get("name") or "Pulse Fitness").strip()
    safe = fn.replace('"', '').replace('<', '').replace('>', '')
    return f"{safe} <noreply@pulsefitness.ai>"


@router.post("/launch/email-sender")
async def set_email_sender(body: EmailSenderBody, user: dict = Depends(get_current_user)):
    if not _is_owner(user):
        raise HTTPException(403, "Owner / manager only")
    org_id = await _org(user)
    update: dict = {}
    if body.friendly_name is not None:
        update["email_sender_friendly_name"] = (body.friendly_name or "").strip()[:80]
    if body.reply_to is not None:
        update["email_sender_reply_to"] = str(body.reply_to)
    if update:
        update["email_sender_updated_at"] = _now_iso()
        await db.organizations.update_one({"id": org_id}, {"$set": update})
    return await get_email_sender(user)


# ═══════════════════ Sample-data toggle ═══════════════════════════


@router.post("/launch/sample-data/load")
async def load_sample_data(user: dict = Depends(get_current_user)):
    """Seed the org with a small but realistic data set so first-touch
    operators can play before they import. Idempotent — re-running
    skips items that already exist."""
    if not _is_owner(user):
        raise HTTPException(403, "Owner / manager only")
    org_id = await _org(user)

    SAMPLE_TAG = "sample_data_v1"
    created = {"members": 0, "plans": 0, "class_templates": 0}

    # Plans
    plans = [
        {"name": "Sample · Adult unlimited", "price_pence": 5900, "billing_period": "monthly"},
        {"name": "Sample · Pay-as-you-go",    "price_pence": 1200, "billing_period": "per_session"},
        {"name": "Sample · Junior 8-pack",    "price_pence": 2400, "billing_period": "pack_of_8"},
    ]
    for p in plans:
        existing = await db.membership_plans.find_one({"organization_id": org_id, "name": p["name"]})
        if existing:
            continue
        await db.membership_plans.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "active": True,
            "tag": SAMPLE_TAG,
            "created_at": _now_iso(),
            "created_by": user.get("email"),
            **p,
        })
        created["plans"] += 1

    # Members
    members = [
        ("Sarah Davies",  "sarah.davies+sample@example.com",  "Sample · Adult unlimited"),
        ("Tom Fielding",  "tom.fielding+sample@example.com",  "Sample · Adult unlimited"),
        ("Mia Patel",     "mia.patel+sample@example.com",     "Sample · Junior 8-pack"),
        ("Alex Roberts",  "alex.roberts+sample@example.com",  "Sample · Pay-as-you-go"),
        ("Jay Okafor",    "jay.okafor+sample@example.com",    "Sample · Adult unlimited"),
    ]
    for full, email, _plan in members:
        existing = await db.members.find_one({"organization_id": org_id, "email": email})
        if existing:
            continue
        first, *rest = full.split()
        await db.members.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "first_name": first,
            "last_name": " ".join(rest),
            "full_name": full,
            "email": email,
            "phone": None,
            "active": True,
            "joined_at": _now_iso(),
            "tag": SAMPLE_TAG,
            "created_at": _now_iso(),
            "created_by": user.get("email"),
        })
        created["members"] += 1

    # Class templates
    templates = [
        {"name": "Sample · Sunrise HIIT",   "duration_min": 45, "capacity": 12, "weekday": 0, "starts_at_hhmm": "06:30"},
        {"name": "Sample · Lunchtime Yoga", "duration_min": 60, "capacity": 18, "weekday": 2, "starts_at_hhmm": "12:30"},
        {"name": "Sample · Saturday Spin",  "duration_min": 50, "capacity": 16, "weekday": 5, "starts_at_hhmm": "09:00"},
    ]
    for t in templates:
        existing = await db.class_templates.find_one({"organization_id": org_id, "name": t["name"]})
        if existing:
            continue
        await db.class_templates.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "active": True,
            "tag": SAMPLE_TAG,
            "created_at": _now_iso(),
            "created_by": user.get("email"),
            **t,
        })
        created["class_templates"] += 1

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"sample_data_loaded_at": _now_iso()}},
    )
    return {"ok": True, "created": created}


@router.post("/launch/sample-data/clear")
async def clear_sample_data(user: dict = Depends(get_current_user)):
    """Remove anything tagged sample_data_v1 — idempotent; safe to call
    after a successful real import."""
    if not _is_owner(user):
        raise HTTPException(403, "Owner / manager only")
    org_id = await _org(user)
    SAMPLE_TAG = "sample_data_v1"
    res = {
        "members":          (await db.members.delete_many({"organization_id": org_id, "tag": SAMPLE_TAG})).deleted_count,
        "plans":            (await db.membership_plans.delete_many({"organization_id": org_id, "tag": SAMPLE_TAG})).deleted_count,
        "class_templates":  (await db.class_templates.delete_many({"organization_id": org_id, "tag": SAMPLE_TAG})).deleted_count,
    }
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"sample_data_cleared_at": _now_iso()}, "$unset": {"sample_data_loaded_at": ""}},
    )
    return {"ok": True, "removed": res}


# ═══════════════════ In-product feedback ══════════════════════════


_FEEDBACK_RL: dict[str, list[float]] = {}


def _check_feedback_rate(ip: str):
    import time
    now = time.time()
    bucket = [t for t in _FEEDBACK_RL.get(ip, []) if now - t < 300]
    if len(bucket) >= 5:
        raise HTTPException(429, "Too much feedback. Try again in a few minutes.")
    bucket.append(now)
    _FEEDBACK_RL[ip] = bucket


class FeedbackBody(BaseModel):
    sentiment: str = Field(..., pattern=r"^(up|down|neutral)$")
    comment: str | None = Field(None, max_length=1000)
    page_path: str | None = Field(None, max_length=200)


@router.post("/feedback/in-product")
async def submit_feedback(
    body: FeedbackBody,
    request: Request,
    user: dict = Depends(get_current_user),
):
    ip = request.client.host if request.client else "unknown"
    _check_feedback_rate(ip)

    await db.in_product_feedback.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": user.get("organization_id"),
        "user_email": user.get("email"),
        "sentiment": body.sentiment,
        "comment": (body.comment or "").strip()[:1000],
        "page_path": (body.page_path or "")[:200],
        "user_role": user.get("role"),
        "at": _now_iso(),
    })
    return {"ok": True}


@router.get("/master-admin/feedback/recent")
async def list_recent_feedback(user: dict = Depends(get_current_user)):
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")
    rows = await db.in_product_feedback.find(
        {}, {"_id": 0},
    ).sort("at", -1).to_list(200)
    counts = {"up": 0, "down": 0, "neutral": 0}
    by_path: dict[str, dict] = {}
    for r in rows:
        s = r.get("sentiment") or "neutral"
        counts[s] = counts.get(s, 0) + 1
        path = r.get("page_path") or "/"
        by_path.setdefault(path, {"up": 0, "down": 0, "neutral": 0, "total": 0})
        by_path[path][s] += 1
        by_path[path]["total"] += 1
    return {
        "rows": rows[:60],
        "counts": counts,
        "total": len(rows),
        "by_path": [{"path": p, **v} for p, v in sorted(by_path.items(), key=lambda kv: -kv[1]["total"])][:15],
    }
