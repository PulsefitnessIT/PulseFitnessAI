"""GymAxis Embeddable Widget — Iter 220aa.

Lets Partner Engineers AND Gym Companies drop a "Log a Fault" / "Get a
Quote" iframe on their own website. Submissions land straight in the
owner's GymAxis inbox (engineer → ``svc_job_requests``;
company → ``crm2_contacts`` lead).

Why this matters:
  * Engineers/companies pay GymAxis a tier-fee → giving them more
    inbound lead channels makes the platform sticky.
  * Every embed is a free brand impression on the customer's website.
  * The customer never sees a GymAxis login — pure embedded form.

Public routes (NO auth — token-gated):
  GET  /api/widget/embed/{token}         · config for the iframe
  POST /api/widget/embed/{token}/submit  · submit a fault/enquiry

Owner routes (auth'd):
  GET    /api/widget/my-embeds           · list my embeds + submission counts
  POST   /api/widget/embeds              · create a new embed token
  PATCH  /api/widget/embeds/{id}         · update settings
  DELETE /api/widget/embeds/{id}         · revoke a token (soft, sets is_active=False)

Anti-abuse:
  * Honeypot field ``website`` — bots fill it, humans don't.
  * 5 submissions / hour / IP / token rolling window via
    ``widget_submission_log`` collection.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _mint_token() -> str:
    """Iter 220be (F-21) — 32 bytes ≈ 256 bits entropy ≈ 43 chars. The
    legacy 12-byte tokens minted before Iter 220be remain valid (we
    look up by exact match) but every new token cleared the
    F-21 "32+ random chars" risk-register requirement on creation."""
    return secrets.token_urlsafe(32)


async def _log_widget_access(
    *, token: str, ip: str, ua: str, found: bool, kind: str,
) -> None:
    """Iter 220be (F-21) — Per-attempt audit row so SOC can detect
    brute-force token enumeration. Every public widget hit is logged
    regardless of outcome; failed hits (``found=False``) are the ones
    we alert on if the count exceeds the per-IP threshold.
    """
    try:
        await db.widget_access_log.insert_one({
            "token": token[:64],
            "ip": ip,
            "user_agent": ua[:200],
            "found": bool(found),
            "kind": kind,  # 'config' or 'submit'
            "ts": _now(),
        })
    except Exception as e:  # never let audit break the path
        logger.warning("widget access log failed: %s", e)


async def _check_widget_lookup_rate(ip: str, max_per_minute: int = 60) -> None:
    """Iter 220be (F-21) — Cap GET /embed/{token} hits to 60/min/IP so
    attackers can't enumerate tokens in bulk. The legitimate iframe
    only fetches its own config once on load, so 60/min is generous.
    """
    if not ip or ip == "unknown":
        return  # don't penalise unknown-IP requests (private deploys)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    recent = await db.widget_access_log.count_documents({
        "ip": ip, "kind": "config", "ts": {"$gte": cutoff},
    })
    if recent >= max_per_minute:
        raise HTTPException(429, "Too many widget lookups — slow down.")


# ── Routers ────────────────────────────────────────────────────

public_router = APIRouter(prefix="/api/widget", tags=["widget-public"])
owner_router = APIRouter(prefix="/api/widget", tags=["widget-owner"])


# ── Pydantic models ────────────────────────────────────────────

class WidgetCreatePayload(BaseModel):
    """``owner_type`` decides where submissions land:
    * ``partner_engineer`` → svc_job_requests
    * ``organization``     → crm2_contacts (lead)
    """
    owner_type: str = Field(..., pattern="^(partner_engineer|organization)$")
    label: str = Field("", max_length=80)
    redirect_url: Optional[str] = Field(None, max_length=400)
    show_reviews_badge: bool = True


class WidgetPatchPayload(BaseModel):
    label: Optional[str] = Field(None, max_length=80)
    redirect_url: Optional[str] = Field(None, max_length=400)
    show_reviews_badge: Optional[bool] = None
    is_active: Optional[bool] = None


class WidgetSubmitPayload(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=120)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(None, max_length=40)
    site_name: Optional[str] = Field(None, max_length=120)
    site_postcode: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field(None, max_length=120)
    description: str = Field(..., min_length=1, max_length=4000)
    urgency: Optional[str] = Field(None, pattern="^(low|normal|high|urgent)$")
    # Honeypot — must be empty.
    website: Optional[str] = Field(None, max_length=400)


# ── Owner resolution helpers ───────────────────────────────────

async def _resolve_owner_context(user: dict) -> tuple[str, str, dict]:
    """Return ``(owner_type, owner_id, owner_doc)`` for the calling user.

    Preference order: partner_engineer (if approved) → organization
    (current org id from the user record)."""
    pe = await db.partner_engineers.find_one(
        {"user_id": user["id"], "status": "approved"},
        {"_id": 0},
    )
    if pe:
        return "partner_engineer", pe["id"], pe
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(404, "No partner engineer or organization context.")
    return "organization", org_id, {
        "id": org_id,
        "name": user.get("company_name") or "Your business",
    }


def _scrub(doc: dict) -> dict:
    """Strip Mongo ObjectId before returning to the client."""
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ── Public widget config + submission ──────────────────────────

@public_router.get("/embed/{token}")
async def public_widget_config(token: str, request: Request = None):  # type: ignore[assignment]
    """Public, unauthenticated. Returns the metadata the iframe needs
    to render the form (owner name, photo, review summary, branding).

    Iter 220be (F-21) — Per-IP enumeration guard + audit log. Each
    lookup writes a ``widget_access_log`` row so SOC can detect
    brute-force scanning. ``request`` is auto-injected by FastAPI
    in production; the ``= None`` default keeps the function callable
    by the inline unit-test suite without constructing a Request.
    """
    if request is not None:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent") or ""
        await _check_widget_lookup_rate(ip)
    else:
        ip, ua = "unknown", ""

    embed = await db.widget_embeds.find_one(
        {"token": token, "is_active": True}, {"_id": 0},
    )
    if not embed:
        if request is not None:
            await _log_widget_access(token=token, ip=ip, ua=ua, found=False, kind="config")
        raise HTTPException(404, "Widget not found")
    if request is not None:
        await _log_widget_access(token=token, ip=ip, ua=ua, found=True, kind="config")

    base = {
        "kind": "log_fault" if embed["owner_type"] == "partner_engineer" else "get_quote",
        "label": embed.get("label") or (
            "Log a fault" if embed["owner_type"] == "partner_engineer" else "Get a quote"
        ),
        "owner_type": embed["owner_type"],
        "redirect_url": embed.get("redirect_url"),
        "show_reviews_badge": bool(embed.get("show_reviews_badge", True)),
    }

    if embed["owner_type"] == "partner_engineer":
        pe = await db.partner_engineers.find_one(
            {"id": embed["owner_id"], "status": "approved"},
            {"_id": 0, "id": 1, "full_name": 1, "company_name": 1,
             "level": 1, "profile_photo_url": 1, "public_slug": 1},
        )
        if not pe:
            raise HTTPException(404, "Widget owner not found")

        # Lightweight summary stats for the badge.
        summary = {"average": None, "count": 0}
        if base["show_reviews_badge"]:
            rows = await db.partner_reviews.find(
                {"partner_id": pe["id"], "status": "approved"},
                {"_id": 0, "rating": 1},
            ).to_list(length=500)
            if rows:
                summary = {
                    "average": round(sum(r.get("rating") or 0 for r in rows) / len(rows), 2),
                    "count": len(rows),
                }
        return {
            **base,
            "owner": {
                "id": pe["id"],
                "name": pe.get("full_name"),
                "company_name": pe.get("company_name"),
                "level": pe.get("level"),
                "photo_url": pe.get("profile_photo_url"),
                "public_slug": pe.get("public_slug"),
            },
            "summary": summary,
        }

    # Organization-owned widget.
    org_id = embed["owner_id"]
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1},
    )
    if not org:
        # Some setups don't have a separate organizations doc — synthesise from a user.
        u = await db.users.find_one(
            {"organization_id": org_id}, {"_id": 0, "company_name": 1},
        )
        org = {"id": org_id, "name": (u or {}).get("company_name") or "Get in touch"}
    return {
        **base,
        "owner": {
            "id": org["id"],
            "name": org.get("name"),
            "logo_url": org.get("logo_url"),
        },
        "summary": {"average": None, "count": 0},
    }


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_rate_limit(token: str, ip: str, max_per_hour: int = 5) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = await db.widget_submission_log.count_documents({
        "token": token, "ip": ip, "ts": {"$gte": cutoff},
    })
    if recent >= max_per_hour:
        raise HTTPException(
            429,
            "Too many submissions from this address — please try again later.",
        )


@public_router.post("/embed/{token}/submit")
async def public_widget_submit(
    token: str,
    payload: WidgetSubmitPayload,
    request: Request,
):
    """Anonymous, public submission. Lands in the owner's inbox."""
    # 1. Honeypot — bots fill ``website``; humans don't see it.
    if (payload.website or "").strip():
        # Silent success — give the bot no signal.
        return {"ok": True, "ref": "spam-discarded"}

    embed = await db.widget_embeds.find_one(
        {"token": token, "is_active": True}, {"_id": 0},
    )
    if not embed:
        raise HTTPException(404, "Widget not found")

    ip = _client_ip(request)
    await _check_rate_limit(token, ip)

    submission_id = _id()
    now = _now()
    base_log = {
        "id": submission_id, "token": token,
        "owner_type": embed["owner_type"],
        "owner_id": embed["owner_id"],
        "ip": ip, "ts": now,
        "customer_email": payload.customer_email.lower(),
    }

    # 2. Route to the right inbox.
    if embed["owner_type"] == "partner_engineer":
        pe = await db.partner_engineers.find_one(
            {"id": embed["owner_id"], "status": "approved"},
            {"_id": 0, "id": 1, "full_name": 1, "organization_id": 1},
        )
        if not pe:
            raise HTTPException(404, "Widget owner not found")
        priority = payload.urgency or "normal"
        title = (payload.title or payload.description[:60].strip()).strip() or "Web fault report"
        await db.svc_job_requests.insert_one({
            "id": submission_id,
            "engineer_id": pe["id"],
            "engineer_name": pe.get("full_name"),
            "organization_id": pe.get("organization_id"),
            "intake_channel": "embed_widget",
            "intake_token": token,
            "status": "pending",
            "customer_name": payload.customer_name,
            "customer_email": payload.customer_email,
            "customer_phone": payload.customer_phone,
            "site_name": payload.site_name,
            "site_postcode": payload.site_postcode,
            "title": title,
            "description": payload.description,
            "priority": priority,
            "source": {"type": "embed_widget", "token": token, "ip": ip},
            "created_at": now,
            "updated_at": now,
        })
        try:
            from routes.svc.notifications import create_notification
            await create_notification(
                user_id=pe["id"], organization_id=pe.get("organization_id"),
                kind="job_request", title=f"Web request: {title[:60]}",
                body=f"{payload.customer_name} · {payload.customer_email}",
                link="/svc/engineer/inbox",
                source_type="job_request", source_id=submission_id,
            )
        except Exception:
            logger.exception("widget submit notification failed")

    else:  # organization → CRM lead
        org_id = embed["owner_id"]
        # First/last name split.
        parts = payload.customer_name.split(" ", 1)
        first, last = parts[0], (parts[1] if len(parts) > 1 else "")
        await db.crm2_contacts.insert_one({
            "id": submission_id,
            "organization_id": org_id,
            "first_name": first, "last_name": last,
            "email": payload.customer_email,
            "phone": payload.customer_phone or "",
            "mobile": "",
            "job_title": "",
            "company_id": None,
            "company_name": payload.site_name or "",
            "influence_types": [], "is_decision_maker": False,
            "is_champion": False, "linkedin": "",
            "source": "embed_widget",
            "status": "active",
            "tags": ["web-enquiry", "auto-imported"],
            "lifecycle": "lead",
            "gdpr_consent": True,  # explicit form submission = consent
            "gdpr_consent_date": now,
            "opt_out_email": False, "opt_out_sms": False,
            "opt_out_phone": False, "opt_out_post": False,
            "opt_out_marketing": False,
            "opt_out_updated_at": now,
            "communication_preferences": {},
            "relationship_score": 5,
            "owner_id": None, "owner_name": "",
            "notes": (
                f"Embedded form enquiry via token {token}.\n\n"
                f"Site: {payload.site_name or '—'}\n"
                f"Postcode: {payload.site_postcode or '—'}\n"
                f"Urgency: {payload.urgency or '—'}\n\n"
                f"{payload.description}"
            ),
            "territory_id": None, "postcode": payload.site_postcode or "",
            "county": "", "region": "", "country": "United Kingdom",
            "created_at": now, "updated_at": now,
        })

    await db.widget_submission_log.insert_one(base_log)

    # Increment counter on the embed itself for the dashboard pill.
    await db.widget_embeds.update_one(
        {"token": token},
        {"$inc": {"submission_count": 1},
         "$set": {"last_submission_at": now}},
    )

    return {"ok": True, "ref": submission_id[:8]}


# ── Owner-side CRUD ────────────────────────────────────────────

@owner_router.get("/my-embeds")
async def list_my_embeds(user: dict = Depends(get_current_user)):
    owner_type, owner_id, _ = await _resolve_owner_context(user)
    rows = await db.widget_embeds.find(
        {"owner_type": owner_type, "owner_id": owner_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(length=100)
    return {"embeds": [_scrub(r) for r in rows]}


@owner_router.post("/embeds")
async def create_embed(
    payload: WidgetCreatePayload,
    user: dict = Depends(get_current_user),
):
    # Don't let a partner engineer create an "organization" widget for
    # someone else's org — strictly own-context.
    owner_type, owner_id, _ = await _resolve_owner_context(user)
    if payload.owner_type != owner_type:
        # A user with BOTH a partner record AND an org can still create
        # the second flavour — fall back to letting the explicit choice
        # win as long as they actually have that context.
        if payload.owner_type == "organization":
            if not user.get("organization_id"):
                raise HTTPException(403, "No organization context.")
            owner_type, owner_id = "organization", user["organization_id"]
        elif payload.owner_type == "partner_engineer":
            pe = await db.partner_engineers.find_one(
                {"user_id": user["id"], "status": "approved"},
                {"_id": 0, "id": 1},
            )
            if not pe:
                raise HTTPException(403, "Not an approved partner engineer.")
            owner_type, owner_id = "partner_engineer", pe["id"]

    doc = {
        "id": _id(),
        "token": _mint_token(),
        "owner_type": owner_type,
        "owner_id": owner_id,
        "created_by_user_id": user["id"],
        "label": payload.label or None,
        "redirect_url": payload.redirect_url or None,
        "show_reviews_badge": payload.show_reviews_badge,
        "is_active": True,
        "submission_count": 0,
        "last_submission_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.widget_embeds.insert_one(doc)
    return _scrub(dict(doc))


@owner_router.patch("/embeds/{embed_id}")
async def update_embed(
    embed_id: str,
    payload: WidgetPatchPayload,
    user: dict = Depends(get_current_user),
):
    owner_type, owner_id, _ = await _resolve_owner_context(user)
    existing = await db.widget_embeds.find_one(
        {"id": embed_id, "owner_type": owner_type, "owner_id": owner_id},
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(404, "Widget not found")

    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not updates:
        return _scrub(existing)
    updates["updated_at"] = _now()
    await db.widget_embeds.update_one({"id": embed_id}, {"$set": updates})
    refreshed = await db.widget_embeds.find_one({"id": embed_id}, {"_id": 0})
    return _scrub(refreshed)


@owner_router.delete("/embeds/{embed_id}")
async def revoke_embed(
    embed_id: str,
    user: dict = Depends(get_current_user),
):
    """Soft-revoke — keeps historical submissions intact, just turns
    the token off so future iframe submissions 404."""
    owner_type, owner_id, _ = await _resolve_owner_context(user)
    res = await db.widget_embeds.update_one(
        {"id": embed_id, "owner_type": owner_type, "owner_id": owner_id},
        {"$set": {"is_active": False, "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Widget not found")
    return {"ok": True}


async def init_widget_embed_indexes() -> None:
    try:
        await db.widget_embeds.create_index("token", unique=True)
        await db.widget_embeds.create_index([("owner_type", 1), ("owner_id", 1)])
        await db.widget_submission_log.create_index([("token", 1), ("ip", 1), ("ts", 1)])
    except Exception as exc:  # pragma: no cover — index ops are best-effort
        logger.warning(f"[widget_embed] index init failed: {exc}")


__all__ = [
    "public_router", "owner_router",
    "init_widget_embed_indexes",
]
