"""Service Desk staff management endpoints — governed by Master Admin only.

Promote/demote Service Desk agents. This is intentionally separate from the
Service Desk's own endpoints so the role system cannot self-escalate.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr, Field
import logging
import os
import secrets
import string
import uuid

from utils.auth import get_current_user, hash_password
from utils.database import db
from utils.security import sanitise_string, validate_password_strength
from utils.service_desk_auth import log_desk_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/service-desk", tags=["Service Desk Admin"])
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


def _require_desk_admin(user: dict) -> bool:
    """Who may nominate / revoke Service Desk users.

    Pulse Fitness master admins manage BOTH brands; Pulse Master Admins manage
    only pulse-brand desk users (their own service team). Returns True
    when the caller is Pulse-scoped.
    """
    if user.get("is_master_admin"):
        return False
    if user.get("is_pulse_admin") or user.get("role") == "pulse_master_admin":
        return True
    raise HTTPException(status_code=403, detail="Master admin required")


def _generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    symbols = "!@#$%^&*-_=+"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        candidate += secrets.choice(string.digits) + secrets.choice(symbols)
        chars = list(candidate)
        secrets.SystemRandom().shuffle(chars)
        candidate = "".join(chars)
        try:
            validate_password_strength(candidate)
            return candidate
        except HTTPException:
            continue


async def _send_service_desk_invite(email: str, name: str, temp_password: str, brand: str) -> bool:
    """Send a branded Service Desk welcome email with the temp password.

    `brand` is "gymaxis" or "pulse" — controls header copy + colour."""
    try:
        from utils.email import send_email
    except Exception:
        return False

    is_pulse = (brand or "").lower() == "pulse"
    brand_name = "Pulse Fitness" if is_pulse else "Pulse Fitness AI"
    accent = "#0055FF" if is_pulse else "#19CDFF"
    login_url = f"{FRONTEND_URL.rstrip('/')}/service-desk" if FRONTEND_URL else "/service-desk"

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;">
      <div style="background:#0A0A0A;padding:22px 28px;">
        <h1 style="color:#fff;font-size:18px;margin:0;">Welcome to {brand_name} Service Desk</h1>
        <p style="color:#9ca3af;font-size:12px;margin:4px 0 0;">Service Desk agent access</p>
      </div>
      <div style="padding:28px;color:#111;">
        <p style="font-size:14px;line-height:1.6;">Hi {sanitise_string(name) or 'there'},</p>
        <p style="font-size:14px;line-height:1.6;">
          You've been provisioned as a <strong>Service Desk agent</strong>. Use the
          temporary password below to sign in — you'll be asked to set a new one
          immediately.
        </p>
        <div style="margin:20px 0;padding:18px;background:#F9FAFB;border:1px dashed #D1D5DB;border-radius:8px;text-align:center;">
          <p style="margin:0 0 6px;color:#6B7280;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Temporary password</p>
          <p style="margin:0;font-family:'SFMono-Regular',Menlo,monospace;font-size:18px;font-weight:700;color:{accent};letter-spacing:0.04em;">{temp_password}</p>
        </div>
        <p style="font-size:13px;line-height:1.6;color:#4B5563;">
          This password expires in 7 days. After signing in you'll be asked to set
          a permanent password.
        </p>
        <a href="{login_url}" style="display:inline-block;margin-top:8px;padding:11px 22px;background:{accent};color:#fff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;">
          Sign in to Service Desk
        </a>
        <p style="font-size:11px;color:#9CA3AF;margin-top:24px;border-top:1px solid #F3F4F6;padding-top:14px;">
          Login email: <span style="font-family:monospace;color:#374151;">{email}</span>
        </p>
      </div>
    </div>
    """

    try:
        await send_email(
            to=email,
            subject=f"Your {brand_name} Service Desk temporary password",
            html=html,
            category="support",
        )
        return True
    except Exception as exc:
        logger.warning("Failed to send service desk invite email: %s", exc)
        return False


class ServiceDeskUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    brand: str = Field(default="gymaxis", pattern="^(gymaxis|pulse)$")


@router.post("/users")
async def create_service_desk_user(
    body: ServiceDeskUserCreate,
    user: dict = Depends(get_current_user),
) -> dict:
    """Create a brand-new Service Desk user from scratch.

    The user does NOT need a pre-existing Pulse / Pulse Fitness account. They're
    created at platform level (no `organization_id`) with `is_service_desk=True`,
    a temporary password, and `must_change_password=True`. They sign in via
    the normal `/api/auth/login` and are routed to `/service-desk`.

    `brand` controls only the welcome-email branding (gymaxis or pulse) and
    is stored as `service_desk_brand` for filtering in the Service Desk UI
    (e.g. so Pulse agents see only Pulse customers' tickets).
    """
    pulse_scoped = _require_desk_admin(user)
    if pulse_scoped:
        # Pulse Master Admins can only nominate into their own brand.
        body.brand = "pulse"
    email = body.email.strip().lower()

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A user with {email} already exists. Use 'Grant existing user' instead.",
        )

    temp_password = _generate_temp_password()
    user_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    user_doc = {
        "id": user_id,
        "email": email,
        "full_name": sanitise_string(body.full_name),
        "password": hash_password(temp_password),
        "role": "service_desk",
        "is_service_desk": True,
        "is_master_admin": False,
        "is_pulse_admin": False,
        "must_change_password": True,
        "temp_password_expires_at": expires_at,
        "service_desk_brand": body.brand,           # "gymaxis" or "pulse"
        "service_desk_granted_at": now_iso,
        "service_desk_granted_by": user["id"],
        "service_desk_granted_by_email": user["email"],
        "provisioned_by": user.get("email"),
        "organization_id": None,
        # Iter 244 — Service-Ops surfaces (cases / scheduler / engineers)
        # scope by organization. Platform-level agents inherit the granting
        # admin's org as their working service org.
        "service_org_id": user.get("organization_id") or user.get("service_org_id"),
        "subscription_tier": "none",
        "company_name": "Pulse Fitness" if body.brand == "pulse" else "Pulse Fitness AI",
        "active": True,
        "created_at": now_iso,
        "last_login": None,
    }
    await db.users.insert_one(user_doc)

    email_sent = await _send_service_desk_invite(email, body.full_name, temp_password, body.brand)

    await log_desk_action(
        user, "desk.create", "user", user_id,
        f"Created {body.brand} Service Desk user {email}",
    )
    logger.info("[service-desk] created user=%s brand=%s email_sent=%s", email, body.brand, email_sent)
    return {
        "success": True,
        "id": user_id,
        "email": email,
        "brand": body.brand,
        "email_sent": email_sent,
        # Echo the temp password so the admin can share it manually if email fails.
        # Frontend should hide unless `email_sent=False`.
        "temp_password": temp_password,
    }


@router.get("/members")
async def list_desk_members(user: dict = Depends(get_current_user)) -> dict:
    """List every user with the Service Desk role (Pulse admins: pulse brand only)."""
    pulse_scoped = _require_desk_admin(user)
    q: dict = {"is_service_desk": True}
    if pulse_scoped:
        q["service_desk_brand"] = "pulse"
    cursor = db.users.find(
        q,
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "is_master_admin": 1,
         "service_desk_granted_at": 1, "service_desk_granted_by_email": 1,
         "service_desk_brand": 1, "must_change_password": 1,
         "disabled": 1, "last_login_at": 1},
    ).sort("service_desk_granted_at", -1)
    members = await cursor.to_list(500)
    return {"members": members, "total": len(members)}


@router.post("/members/grant")
async def grant_service_desk(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Promote an EXISTING user to Service Desk. Body: {email: str, brand?: 'gymaxis'|'pulse'}."""
    pulse_scoped = _require_desk_admin(user)
    email = (body.get("email") or "").strip().lower()
    brand = (body.get("brand") or "gymaxis").lower()
    if brand not in ("gymaxis", "pulse") or pulse_scoped:
        brand = "pulse" if pulse_scoped else "gymaxis"
    if not email:
        raise HTTPException(status_code=400, detail="email required")

    target = await db.users.find_one({"email": email}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    if target.get("is_service_desk"):
        return {"success": True, "already_service_desk": True}

    now = datetime.now(timezone.utc).isoformat()
    set_fields = {
        "is_service_desk": True,
        "service_desk_brand": brand,
        "service_desk_granted_at": now,
        "service_desk_granted_by": user["id"],
        "service_desk_granted_by_email": user["email"],
    }
    # Iter 244 — org-less (platform-level) users need a working service org
    # for the org-scoped Service-Ops surfaces (cases / scheduler / engineers).
    if not target.get("organization_id") and not target.get("service_org_id"):
        svc_org = user.get("organization_id") or user.get("service_org_id")
        if svc_org:
            set_fields["service_org_id"] = svc_org
    await db.users.update_one({"id": target["id"]}, {"$set": set_fields})
    await log_desk_action(
        user, "desk.grant", "user", target["id"],
        f"Granted {brand} Service Desk role to {email}",
    )
    return {"success": True, "email": email, "brand": brand}


@router.post("/members/revoke")
async def revoke_service_desk(
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Remove Service Desk role from a user. Body: {email: str}."""
    pulse_scoped = _require_desk_admin(user)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")

    target = await db.users.find_one(
        {"email": email},
        {"_id": 0, "id": 1, "service_desk_brand": 1, "is_master_admin": 1})
    if not target:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    # Pulse admins manage only their own brand — out-of-brand members are
    # 404 (indistinguishable from non-existent), and master admins are
    # never revocable by a pulse admin.
    if pulse_scoped and (
        (target.get("service_desk_brand") or "") != "pulse" or target.get("is_master_admin")
    ):
        raise HTTPException(status_code=404, detail=f"User {email} not found")

    await db.users.update_one(
        {"id": target["id"]},
        {"$set": {
            "is_service_desk": False,
            "service_desk_revoked_at": datetime.now(timezone.utc).isoformat(),
            "service_desk_revoked_by": user["id"],
        }},
    )
    await log_desk_action(
        user, "desk.revoke", "user", target["id"],
        f"Revoked Service Desk role from {email}",
    )
    return {"success": True, "email": email}
