"""Member-facing authentication — register, login, current member.

Extracted from the legacy single-file routes/memberships.py during the
Pass 2 split (CODE_REVIEW.md P3). Endpoints, models, and helpers in this
module retain their original behaviour and tests.
"""
from __future__ import annotations


import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from utils.database import db
from utils.security import sanitise_string

from routes.memberships.helpers import (
    _gen_referral_code,
    _member_token,
    _now_iso,
    _public_member,
    _require_current_member,
    _uuid,
    pwd_ctx,
)

router = APIRouter(tags=["memberships"])


# ═════════════════════ Member auth ═════════════════════

class MemberRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str
    last_name: str
    phone: str | None = None
    dob: str | None = None
    organization_id: str | None = None
    organization_slug: str | None = None
    site_id: str | None = None
    referral_code: str | None = None


class MemberLogin(BaseModel):
    email: EmailStr
    password: str


@router.post("/member-auth/register")
async def member_register(body: MemberRegister, request: Request):
    # Iter 215af — IP-based rate limit to block mass account farming.
    from utils.security_plus import rate_limit_async
    ip = (request.client.host if request.client else "unknown")
    await rate_limit_async(f"member_register_ip:{ip}", max_requests=10, window_seconds=600)
    email = body.email.lower().strip()
    if await db.members.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
    # Resolve organization_id from slug if provided (public white-label app)
    org_id = body.organization_id
    if not org_id and body.organization_slug:
        org = await db.organizations.find_one(
            {"slug": body.organization_slug}, {"_id": 0, "id": 1})
        if not org:
            raise HTTPException(404, "Studio not found")
        org_id = org["id"]
    if not org_id:
        raise HTTPException(400, "organization_id or organization_slug required")
    # Resolve optional referral code → referrer id
    referred_by: str | None = None
    if body.referral_code:
        code = body.referral_code.strip().upper()
        referrer = await db.members.find_one(
            {"referral_code": code, "organization_id": org_id},
            {"_id": 0, "id": 1},
        )
        if referrer:
            referred_by = referrer["id"]
    member = {
        "id": _uuid(),
        "email": email,
        "password": pwd_ctx.hash(body.password),
        "first_name": sanitise_string(body.first_name),
        "last_name": sanitise_string(body.last_name),
        "phone": (body.phone or "").strip() or None,
        "dob": body.dob,
        "organization_id": org_id,
        "site_id": body.site_id,
        "account_type": "member",
        "status": "active",
        "tags": [],
        "no_show_count": 0,
        "lifetime_value_pence": 0,
        "promo_credit_pence": 0,
        "referral_code": _gen_referral_code(body.first_name),
        "referred_by": referred_by,
        "created_at": _now_iso(),
    }
    await db.members.insert_one(member)
    # Materialise TOTP secret for QR
    await db.qr_rotation_secret.insert_one({
        "member_id": member["id"],
        "secret_b32": pyotp.random_base32(),
        "created_at": _now_iso(),
    })
    # Record the referral as pending — converts on first paid checkout
    if referred_by:
        await db.referrals.insert_one({
            "id": _uuid(),
            "referrer_id": referred_by,
            "referee_id": member["id"],
            "referee_email": email,
            "organization_id": org_id,
            "status": "pending",
            "credit_pence": 500,  # £5 when referee first pays
            "created_at": _now_iso(),
        })
    token = _member_token(member)
    return {"token": token, "member": _public_member(member)}


@router.post("/member-auth/login")
async def member_login(body: MemberLogin, request: Request):
    # Iter 215af — brute-force guard on member login (mirrors the main
    # operator /api/auth/login rate limit from utils.security).
    from utils.security_plus import rate_limit_async
    ip = (request.client.host if request.client else "unknown")
    await rate_limit_async(f"member_login_ip:{ip}", max_requests=8, window_seconds=300)
    email = body.email.lower().strip()
    m = await db.members.find_one({"email": email})
    if not m or not pwd_ctx.verify(body.password, m.get("password", "")):
        raise HTTPException(401, "Invalid credentials")
    await db.members.update_one({"id": m["id"]}, {"$set": {"last_seen_at": _now_iso()}})
    return {"token": _member_token(m), "member": _public_member(m)}


@router.get("/member-auth/me")
async def member_me(member: dict = Depends(_require_current_member)):
    return {"member": _public_member(member)}



# ═════════════ Portal invite claim (iter 216ak · Sprint B · G5) ═════════════


class MemberClaimInvite(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    password: str = Field(min_length=8, max_length=200)


@router.post("/member-auth/claim-invite")
async def member_claim_invite(body: MemberClaimInvite):
    """Operator sent the member a magic link (see
    `POST /memberships/members/{id}/invite-portal`). The link lands on
    `/m/{slug}/claim?t=<token>` in the frontend; the frontend posts here
    to finalise: verify the token hash, set the member's password, and
    return a normal member bearer.
    """
    import hashlib
    from datetime import datetime, timezone

    h = hashlib.sha256(body.token.strip().encode("utf-8")).hexdigest()
    m = await db.members.find_one(
        {"portal_invite_token_hash": h, "portal_access_enabled": True},
        {"_id": 0},
    )
    if not m:
        raise HTTPException(400, "Invite is invalid or has been revoked")
    exp = m.get("portal_invite_expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                raise HTTPException(400, "Invite has expired — ask your studio to resend")
        except ValueError:
            pass  # malformed stamp — allow, but don't fail closed

    await db.members.update_one(
        {"id": m["id"]},
        {
            "$set": {
                "password": pwd_ctx.hash(body.password),
                "portal_claimed_at": _now_iso(),
                "last_seen_at": _now_iso(),
            },
            # Burn the token so the link can't be replayed.
            "$unset": {"portal_invite_token_hash": "", "portal_invite_expires_at": ""},
        },
    )
    # Refresh the doc so the JWT + profile echo the claimed state.
    m2 = await db.members.find_one({"id": m["id"]}, {"_id": 0})
    return {"token": _member_token(m2), "member": _public_member(m2)}
