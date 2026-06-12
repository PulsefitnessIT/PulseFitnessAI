"""
Self-serve Service Provider signup + setup wizard (Iter 253).

Lets a field-service supplier sign themselves up for the Service Desk +
Engineer App package — no master-admin involvement — and complete a
guided setup before landing in their own Service Desk.

Flow:
    POST /api/service-provider/signup        → creates provider org +
                                                desk-owner user, seeds
                                                working defaults, issues
                                                the session (same auth
                                                machinery as /auth/register).
    GET  /api/service-provider/setup         → wizard status + values
    PUT  /api/service-provider/setup/branding
    PUT  /api/service-provider/setup/sla
    POST /api/service-provider/setup/engineer (invite first engineer)
    POST /api/service-provider/setup/complete → unlock the desk

The provider's org IS their service org: `organization_id == service_org_id`,
`is_service_desk=True`, `role=owner`. Every existing svc surface therefore
scopes to them automatically (see `routes/svc/cases._of`). ERP (Sicon/Sage)
stays OFF by default and is offered later — the desk works standalone.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from utils.auth import (
    get_current_user, hash_password, create_token, set_auth_cookie,
    purge_legacy_cookie_scopes, record_user_session,
)
from utils.auth_guards import access_token_ttl_hours
from utils.database import db
from utils.security import rate_limit, validate_password_strength

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service-provider", tags=["Service Provider · Self-serve"])

# Default SLA matrix (hours) seeded so the desk is usable from minute one;
# editable in the wizard's SLA step. Mirrors routes.svc.cases._DEFAULT_SLA.
_DEFAULT_SLA = {
    "p1": {"response_h": 1, "resolve_h": 4},
    "p2": {"response_h": 4, "resolve_h": 24},
    "p3": {"response_h": 8, "resolve_h": 72},
    "p4": {"response_h": 24, "resolve_h": 168},
}

_PRIORITIES = ("p1", "p2", "p3", "p4")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brand_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "provider"


class ProviderSignup(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    phone: str | None = Field(default=None, max_length=40)


def _require_provider_owner(user: dict) -> str:
    """Caller must own a service_provider org. Returns the org id."""
    org_id = user.get("organization_id") or user.get("service_org_id")
    if not org_id or not user.get("is_service_desk"):
        raise HTTPException(status_code=403, detail="Service provider owner only")
    return org_id


# ─────────────────────────────────────────────────────────────────
# Signup
# ─────────────────────────────────────────────────────────────────

@router.post("/signup")
async def signup(body: ProviderSignup, request: Request, response: Response) -> dict:
    # Rate limit (honour the CI bypass header like /auth/register).
    bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "").strip()
    if not (bypass and request.headers.get("x-ratelimit-bypass", "") == bypass):
        ip = request.client.host if request.client else "unknown"
        rate_limit(
            f"sp_signup:{ip}",
            max_requests=int(os.environ.get("REGISTER_RATE_LIMIT_MAX", "5")),
            window_seconds=int(os.environ.get("REGISTER_RATE_LIMIT_WINDOW", "900")),
        )

    validate_password_strength(body.password)
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="Email already registered")

    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    # 14-day B2B trial. Without a real trial window the org computes as
    # instantly expired and the desk renders the upgrade paywall (iter 253).
    trial_days = int(os.environ.get("SP_TRIAL_DAYS", "14"))
    await db.organizations.insert_one({
        "id": org_id,
        "name": body.company_name.strip(),
        "account_type": "service_provider",
        "subscription_tier": "pro",
        "is_trial": True,
        "trial_started_at": now,
        "trial_ends_at": (now_dt + timedelta(days=trial_days)).isoformat(),
        "trial_suspends_at": (now_dt + timedelta(days=trial_days + 30)).isoformat(),
        "trial_duration_days": trial_days,
        "trial_status": "active",
        "trial_source": "service_provider_signup",
        "service_ops": True,
        "service_ops_setup_complete": False,
        "service_desk_brand": _brand_slug(body.company_name),
        "branding": {"primary_color": "#0EA5E9", "accent_color": "#7C3AED"},
        "created_at": now,
        "updated_at": now,
    })

    user_doc = {
        "id": user_id,
        "email": email,
        "password": hash_password(body.password),
        "full_name": body.full_name.strip(),
        "role": "owner",
        "organization_id": org_id,
        # This owner runs their own Service Desk for their own org.
        "is_service_desk": True,
        "service_org_id": org_id,
        "service_desk_brand": _brand_slug(body.company_name),
        "is_master_admin": False,
        "active": True,
        "must_change_password": False,
        "created_at": now,
        "password_updated_at": now,
    }
    if body.phone:
        user_doc["phone"] = body.phone.strip()
    await db.users.insert_one(user_doc)

    # Seed an editable SLA matrix so cases get sensible targets immediately.
    await db.svc_sla_policies.insert_many([
        {"id": str(uuid.uuid4()), "organization_id": org_id, "priority": p,
         "cover_type": "", "response_h": _DEFAULT_SLA[p]["response_h"],
         "resolve_h": _DEFAULT_SLA[p]["resolve_h"], "created_at": now}
        for p in _PRIORITIES
    ])
    # Seed built-in case types (idempotent helper from the case-types module).
    try:
        from routes.svc.case_types import _seed_builtins
        await _seed_builtins(org_id)
    except Exception:
        logger.exception("[sp-signup] case-type seed failed (non-blocking)")

    ttl = access_token_ttl_hours({"role": "owner"})
    token = create_token(user_id, expires_hours=ttl, mfa_verified=False)
    set_auth_cookie(response, token, max_age_hours=ttl)
    purge_legacy_cookie_scopes(response, request)
    await record_user_session(user_id, token, request)

    logger.info("[sp-signup] new service provider org=%s email=%s", org_id, email)
    return {
        "token": token,
        "user": {
            "id": user_id, "email": email, "full_name": user_doc["full_name"],
            "company_name": body.company_name.strip(), "role": "owner",
            "organization_id": org_id, "account_type": "service_provider",
            "is_service_desk": True, "is_master_admin": False,
            "service_ops_setup_complete": False,
        },
        "next": "/service-desk/setup",
    }


# ─────────────────────────────────────────────────────────────────
# Setup wizard
# ─────────────────────────────────────────────────────────────────

@router.get("/setup")
async def get_setup(user: dict = Depends(get_current_user)) -> dict:
    org_id = _require_provider_owner(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
    sla = await db.svc_sla_policies.find(
        {"organization_id": org_id, "cover_type": ""}, {"_id": 0, "priority": 1, "response_h": 1, "resolve_h": 1},
    ).to_list(20)
    sla_map = {r["priority"]: {"response_h": r["response_h"], "resolve_h": r["resolve_h"]} for r in sla}
    engineer_count = await db.svc_engineers.count_documents({"organization_id": org_id, "active": True})
    branding = org.get("branding") or {}
    steps = {
        "branding": bool(org.get("branding_confirmed")),
        "sla": bool(org.get("sla_confirmed")),
        "engineer": engineer_count > 0,
    }
    return {
        "company_name": org.get("name") or "",
        "branding": {
            "logo_url": branding.get("logo_url") or "",
            "primary_color": branding.get("primary_color") or "#0EA5E9",
            "accent_color": branding.get("accent_color") or "#7C3AED",
        },
        "sla": {p: sla_map.get(p, _DEFAULT_SLA[p]) for p in _PRIORITIES},
        "engineer_count": engineer_count,
        "steps": steps,
        "setup_complete": bool(org.get("service_ops_setup_complete")),
        "all_steps_done": all(steps.values()),
    }


@router.put("/setup/branding")
async def save_branding(body: dict, user: dict = Depends(get_current_user)) -> dict:
    org_id = _require_provider_owner(user)
    hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
    primary = (body.get("primary_color") or "#0EA5E9").strip()
    accent = (body.get("accent_color") or "#7C3AED").strip()
    if not hex_re.match(primary) or not hex_re.match(accent):
        raise HTTPException(status_code=400, detail="Colours must be 6-digit hex (e.g. #0EA5E9)")
    set_fields = {
        "branding.primary_color": primary,
        "branding.accent_color": accent,
        "branding.logo_url": (body.get("logo_url") or "").strip(),
        "branding_confirmed": True,
        "updated_at": _now(),
    }
    name = (body.get("company_name") or "").strip()
    if name:
        set_fields["name"] = name
    await db.organizations.update_one({"id": org_id}, {"$set": set_fields})
    return {"ok": True}


@router.put("/setup/sla")
async def save_sla(body: dict, user: dict = Depends(get_current_user)) -> dict:
    org_id = _require_provider_owner(user)
    matrix = body.get("sla") or {}
    now = _now()
    for p in _PRIORITIES:
        row = matrix.get(p) or {}
        try:
            resp = max(0, int(row.get("response_h", _DEFAULT_SLA[p]["response_h"])))
            resolve = max(1, int(row.get("resolve_h", _DEFAULT_SLA[p]["resolve_h"])))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"SLA hours for {p} must be whole numbers")
        await db.svc_sla_policies.update_one(
            {"organization_id": org_id, "priority": p, "cover_type": ""},
            {"$set": {"response_h": resp, "resolve_h": resolve, "updated_at": now},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
            upsert=True,
        )
    await db.organizations.update_one({"id": org_id}, {"$set": {"sla_confirmed": True, "updated_at": now}})
    return {"ok": True}


@router.post("/setup/engineer")
async def add_first_engineer(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Create the provider's first engineer: a user (temp password) + an
    `svc_engineers` profile in one step, so the wizard isn't a two-hop."""
    org_id = _require_provider_owner(user)
    email = (body.get("email") or "").strip().lower()
    full_name = (body.get("full_name") or "").strip()
    if not email or not full_name:
        raise HTTPException(status_code=400, detail="Engineer name and email are required")

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "organization_id": 1})
    if existing and existing.get("organization_id") not in (None, org_id):
        raise HTTPException(status_code=400, detail=f"{email} already belongs to another organisation")

    now = _now()
    temp_password = uuid.uuid4().hex[:10] + "A1!"
    if existing:
        eng_user_id = existing["id"]
        await db.users.update_one({"id": eng_user_id}, {"$set": {
            "organization_id": org_id, "role": "engineer", "active": True, "updated_at": now,
        }})
    else:
        eng_user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": eng_user_id, "email": email, "full_name": full_name,
            "password": hash_password(temp_password),
            "role": "engineer", "organization_id": org_id,
            "active": True, "must_change_password": True,
            "created_at": now, "password_updated_at": now,
        })

    if not await db.svc_engineers.find_one({"id": eng_user_id}, {"_id": 0, "id": 1}):
        await db.svc_engineers.insert_one({
            "id": eng_user_id, "organization_id": org_id,
            "full_name": full_name, "email": email,
            "mobile": (body.get("mobile") or "").strip(),
            "skills": [], "working_hours": {},
            "verified": False, "active": True,
            "created_at": now, "updated_at": now,
        })

    return {
        "ok": True, "engineer_id": eng_user_id, "email": email,
        "temp_password": None if existing else temp_password,
        "invited": not existing,
    }


@router.post("/setup/complete")
async def complete_setup(user: dict = Depends(get_current_user)) -> dict:
    org_id = _require_provider_owner(user)
    engineer_count = await db.svc_engineers.count_documents({"organization_id": org_id, "active": True})
    if engineer_count < 1:
        raise HTTPException(status_code=400, detail="Add at least one engineer before finishing setup")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"service_ops_setup_complete": True, "service_ops_setup_completed_at": _now(),
                  "branding_confirmed": True, "sla_confirmed": True}},
    )
    return {"ok": True, "redirect": "/service-desk"}


__all__ = ["router"]
