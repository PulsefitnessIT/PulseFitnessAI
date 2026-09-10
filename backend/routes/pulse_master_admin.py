"""
Pulse Master Admin — provisioning, role management, and Stripe Connect onboarding.

A Pulse Master Admin is a delegated user provisioned by the platform's Master
Admin to manage Pulse-Fitness-side concerns (their orgs, payments, MOD sites,
analytics, integrations) without touching Pulse Fitness-platform internals. They
share the same Master Admin UI but data is filtered to Pulse-relevant
account types.

This module owns:
  • POST /api/master-admin/pulse-admins             — create a new pulse admin (sends temp pwd email)
  • GET  /api/master-admin/pulse-admins             — list provisioned pulse admins
  • DELETE /api/master-admin/pulse-admins/{user_id} — revoke
  • POST /api/auth/force-change-password            — first-login forced password change

  • GET  /api/stripe-connect/status                 — connection state for the calling pulse admin
  • GET  /api/stripe-connect/onboard-url            — build OAuth URL for "Connect with Stripe"
  • GET  /api/stripe-connect/callback               — handle ?code from Stripe OAuth, store account id
  • POST /api/stripe-connect/disconnect             — revoke the connected account
  • GET  /api/stripe-connect/pricing                — read per-customer pricing config
  • PUT  /api/stripe-connect/pricing                — update per-customer pricing config
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import string
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field

from utils.auth import (
    create_token, get_current_user, hash_password, set_auth_cookie, verify_password,
)
from utils.database import db
from utils.security import sanitise_string, validate_password_strength

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Constants ────────────────────────────────────────────────────────────

MASTER_ADMIN_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai")
PULSE_ROLE = "pulse_master_admin"

# Account types a Pulse Master Admin is allowed to see. The platform manages
# Pulse Fitness-internal demo / starter orgs separately — those stay invisible.
PULSE_VISIBLE_ACCOUNT_TYPES = ["pulse_pro", "lite", "mod", "full"]

# Stripe OAuth — Standard Connect platform settings.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_CONNECT_CLIENT_ID = os.environ.get("STRIPE_CONNECT_CLIENT_ID", "")
STRIPE_CONNECT_REDIRECT_URI = os.environ.get("STRIPE_CONNECT_REDIRECT_URI", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


# ── Helpers ──────────────────────────────────────────────────────────────

def _require_gymaxis_master(user: dict) -> None:
    """Only the platform-owner Master Admin can provision Pulse admins."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    raise HTTPException(status_code=403, detail="Master admin access required")


def _require_pulse_or_master(user: dict) -> None:
    """Either the Pulse Fitness Master Admin, a Pulse Master Admin, or a Service
    Desk agent is allowed (service desk needs to import equipment for
    customer onboarding)."""
    if user.get("email") == MASTER_ADMIN_EMAIL or user.get("is_master_admin"):
        return
    if user.get("role") == PULSE_ROLE or user.get("is_pulse_admin"):
        return
    if user.get("is_service_desk"):
        return
    raise HTTPException(status_code=403, detail="Master admin or Service Desk access required")


def _generate_temp_password(length: int = 14) -> str:
    """Cryptographically strong temp password that satisfies our strength rules.

    Always contains: 1 upper, 1 lower, 1 digit, 1 symbol (validate_password_strength
    rejects passwords without each of those buckets).
    """
    alphabet = string.ascii_letters + string.digits
    symbols = "!@#$%^&*-_=+"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        candidate += secrets.choice(string.digits) + secrets.choice(symbols)
        # Shuffle to avoid predictable suffix
        chars = list(candidate)
        secrets.SystemRandom().shuffle(chars)
        candidate = "".join(chars)
        try:
            validate_password_strength(candidate)
            return candidate
        except HTTPException:
            continue  # extremely unlikely; loop until it passes


async def _send_pulse_admin_invite(email: str, name: str, temp_password: str) -> bool:
    """Email the new Pulse Master Admin their temporary password.

    Uses the same Resend pipeline as `send_password_reset_email`. Best-effort —
    we still return ``True`` from the create endpoint even if email fails so
    the platform admin can manually share the password if Resend is down.
    """
    try:
        from utils.email import send_email
    except Exception:
        return False

    login_url = f"{FRONTEND_URL.rstrip('/')}/login" if FRONTEND_URL else "https://pulsefitness.com/login"

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;">
      <div style="background:#0A0A0A;padding:22px 28px;">
        <h1 style="color:#fff;font-size:18px;margin:0;">Welcome to Pulse Master Admin</h1>
        <p style="color:#9ca3af;font-size:12px;margin:4px 0 0;">Powered by Pulse Fitness</p>
      </div>
      <div style="padding:28px;color:#111;">
        <p style="font-size:14px;line-height:1.6;">Hi {sanitise_string(name) or 'there'},</p>
        <p style="font-size:14px;line-height:1.6;">
          You've been provisioned as a <strong>Pulse Master Admin</strong>. Use the temporary
          password below to sign in — you'll be asked to set a new one immediately.
        </p>
        <div style="margin:20px 0;padding:18px;background:#F9FAFB;border:1px dashed #D1D5DB;border-radius:8px;text-align:center;">
          <p style="margin:0 0 6px;color:#6B7280;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Temporary password</p>
          <p style="margin:0;font-family:'SFMono-Regular',Menlo,monospace;font-size:18px;font-weight:700;color:#0055FF;letter-spacing:0.04em;">{temp_password}</p>
        </div>
        <p style="font-size:13px;line-height:1.6;color:#4B5563;">
          This password expires in 7 days. If you don't use it, ask the platform admin to reissue.
        </p>
        <a href="{login_url}" style="display:inline-block;margin-top:8px;padding:11px 22px;background:#0055FF;color:#fff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;">
          Sign in to Master Admin
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
            subject="Your Pulse Master Admin temporary password",
            html=html,
            category="support",
        )
        return True
    except Exception as exc:
        logger.warning("Failed to send pulse admin invite email: %s", exc)
        return False


# ── Pulse-admin user provisioning ────────────────────────────────────────

class PulseAdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)


class PulseAdminOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    must_change_password: bool
    created_at: str
    last_login: Optional[str] = None


@router.post("/master-admin/pulse-admins")
async def create_pulse_admin(body: PulseAdminCreate, user: dict = Depends(get_current_user)) -> dict:
    _require_gymaxis_master(user)
    email = body.email.strip().lower()

    # Don't clobber an existing user account — refuse with a clear error.
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A user with this email already exists (role={existing.get('role')}). Use a different email.",
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
        "role": PULSE_ROLE,
        "is_master_admin": False,
        "is_pulse_admin": True,
        # Force-change-on-first-login flag: login still issues a token but the
        # frontend redirects to /change-password until this is cleared.
        "must_change_password": True,
        "temp_password_expires_at": expires_at,
        "provisioned_by": user.get("email"),
        "organization_id": None,  # Pulse admins are platform-level, not org-scoped
        # Iter 244 — working org for Service-Ops surfaces (Service Desk cases,
        # scheduler, engineers). Inherits the provisioning master admin's org.
        "service_org_id": user.get("organization_id") or user.get("service_org_id"),
        "subscription_tier": "none",
        "company_name": "Pulse Fitness",
        "active": True,
        "created_at": now_iso,
        "last_login": None,
    }
    await db.users.insert_one(user_doc)

    email_sent = await _send_pulse_admin_invite(email, body.full_name, temp_password)

    # Audit-log so this provisioning is traceable in the Master Admin activity feed.
    try:
        from routes.master_admin import log_activity
        await log_activity(
            "pulse_admin_provisioned",
            f"Provisioned Pulse Master Admin {email}",
            user.get("email", ""),
            target_type="user",
            target_id=user_id,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "user_id": user_id,
        "email": email,
        "email_sent": email_sent,
        # Surface the temp password to the provisioning admin only when email
        # delivery failed — they can hand it over manually. Don't return it
        # otherwise (no temp-password leakage in audit logs).
        "temp_password": temp_password if not email_sent else None,
    }


@router.get("/master-admin/pulse-admins")
async def list_pulse_admins(user: dict = Depends(get_current_user)) -> dict:
    # Read-only list — also powers the SOC-2 Permissions matrix, which a
    # delegated Pulse Master Admin needs to view (Iter 222). Provisioning
    # (create/revoke/purge) stays Pulse Fitness-master-only below.
    _require_pulse_or_master(user)
    rows = await db.users.find(
        {"role": PULSE_ROLE},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1,
         "must_change_password": 1, "created_at": 1, "last_login": 1, "active": 1,
         "organization_memberships": 1},
    ).sort("created_at", -1).to_list(500)
    # Iter 222 — also include CRM-portal staff promoted to Pulse Master
    # Admin via the org user-role dropdown (they live in crm_users and so
    # would otherwise be invisible in this panel).
    crm_rows = await db.crm_users.find(
        {"$or": [{"role": PULSE_ROLE}, {"is_pulse_admin": True}]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1,
         "must_change_password": 1, "created_at": 1, "last_login": 1,
         "active": 1, "organization_id": 1},
    ).sort("created_at", -1).to_list(500)
    for cr in crm_rows:
        if cr.get("organization_id"):
            cr["organization_memberships"] = [cr["organization_id"]]
        cr["promoted_from_existing"] = True
    existing_ids = {r["id"] for r in rows}
    rows = rows + [c for c in crm_rows if c["id"] not in existing_ids]
    # Decorate memberships with org names so the UI can render labels.
    membership_org_ids: set[str] = set()
    for r in rows:
        for oid in r.get("organization_memberships") or []:
            membership_org_ids.add(oid)
    org_lookup: dict[str, str] = {}
    if membership_org_ids:
        async for o in db.organizations.find(
            {"id": {"$in": list(membership_org_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            org_lookup[o["id"]] = o.get("name") or o["id"]
    for r in rows:
        r["membership_org_names"] = [
            {"id": oid, "name": org_lookup.get(oid, oid)}
            for oid in (r.get("organization_memberships") or [])
        ]
    return {"admins": rows}


@router.delete("/master-admin/pulse-admins/{user_id}")
async def revoke_pulse_admin(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_gymaxis_master(user)
    target = await db.users.find_one({"id": user_id, "role": PULSE_ROLE}, {"_id": 0, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Pulse admin not found")
    # Soft-delete: flip active=false so they can no longer log in but historical
    # audit trail entries still resolve to a real user record.
    await db.users.update_one({"id": user_id}, {"$set": {"active": False, "revoked_at": datetime.now(timezone.utc).isoformat()}})
    try:
        from routes.master_admin import log_activity
        await log_activity(
            "pulse_admin_revoked",
            f"Revoked Pulse Master Admin {target.get('email')}",
            user.get("email", ""),
            target_type="user",
            target_id=user_id,
        )
    except Exception:
        pass
    return {"ok": True}


@router.delete("/master-admin/pulse-admins/{user_id}/purge")
async def hard_purge_pulse_admin(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Iter 216h8 — Hard-delete a Pulse Admin row + all related records.

    Use this ONLY when you want to start completely fresh with an email
    address (e.g. after a botched onboarding where the user never logged
    in). Wipes:
      • users row
      • invites for that email
      • signup_drafts for that email
      • signup_journey_jobs for that email
      • tour_bookings for that email
    Logs an audit event before deletion so the trail isn't lost.
    """
    _require_gymaxis_master(user)
    target = await db.users.find_one(
        {"id": user_id, "role": PULSE_ROLE},
        {"_id": 0, "email": 1, "full_name": 1, "active": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Pulse admin not found")
    email = (target.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Cannot purge — user has no email")

    # Audit FIRST so the trail survives the delete.
    try:
        from routes.master_admin import log_activity
        await log_activity(
            "pulse_admin_purged",
            f"Hard-deleted Pulse Master Admin {email} (was '{target.get('full_name')}'); active={target.get('active')}",
            user.get("email", ""),
            target_type="user",
            target_id=user_id,
        )
    except Exception:
        pass

    deleted = {
        "users": (await db.users.delete_many({"id": user_id})).deleted_count,
        "crm_users": (await db.crm_users.delete_many({"email": email})).deleted_count,
        "invites": (await db.invites.delete_many({"email": email})).deleted_count,
        "signup_drafts": (await db.signup_drafts.delete_many({"email": email})).deleted_count,
        "signup_journey_jobs": (await db.signup_journey_jobs.delete_many({"to_email": email})).deleted_count,
        "tour_bookings": (await db.tour_bookings.delete_many({"member_email": email})).deleted_count,
    }
    return {"ok": True, "email": email, "deleted": deleted}


@router.delete("/master-admin/purge-user-by-email")
async def hard_purge_user_by_email(email: str = Query(...), user: dict = Depends(get_current_user)) -> dict:
    """Iter 216h8 — Email-keyed full purge across collections.

    Addressable by EMAIL so you can reset records when a user accidentally
    ended up in multiple places (e.g. as a Pulse Admin AND a regular org
    user with two spellings of the same name). Master-admin only.
    Matches both the exact email and other addresses with the same local
    part on the same domain (handles 'craig@' vs 'craig.henshall@' style
    confusion). All rows are audited before deletion.
    """
    _require_gymaxis_master(user)
    email_clean = (email or "").strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Valid email required")

    local_part = email_clean.split("@")[0]
    domain = email_clean.split("@")[1]
    # Use the FIRST dot-segment as the match prefix so 'craig.henshall' also
    # catches 'craig'. This is the common confusion mode after re-onboarding.
    prefix = local_part.split(".")[0] if "." in local_part else local_part
    email_filter = {"$or": [
        {"email": email_clean},
        {"email": {"$regex": f"^{re.escape(prefix)}(\\.|@)", "$options": "i"}},
    ]}
    # Tighten the regex match to the same domain so we don't accidentally
    # wipe 'craig@other-domain.com'.
    email_filter["$or"][1]["email"] = {
        "$regex": f"^{re.escape(prefix)}(\\..*)?@{re.escape(domain)}$", "$options": "i",
    }

    matched = await db.users.find(
        email_filter, {"_id": 0, "id": 1, "email": 1, "role": 1, "organization_id": 1},
    ).to_list(length=20)
    matched_crm = await db.crm_users.find(
        email_filter, {"_id": 0, "id": 1, "email": 1, "role": 1, "organization_id": 1},
    ).to_list(length=20)
    matched.extend({**m, "_collection": "crm_users"} for m in matched_crm)
    # ── Staffing cascade (Iter 2026-06) ───────────────────────────────
    # The old purge left orphaned staff_members + staffing sub-records
    # behind (keyed by staff_id, not email), which broke the HR/legacy
    # screen and blocked clean re-onboarding. Resolve every staff_members
    # row for this person — by email OR by any matched login id — then
    # cascade all per-staff collections.
    matched_uids = [m["id"] for m in matched if m.get("id")]
    staff_or = [email_filter]
    if matched_uids:
        staff_or.append({"user_id": {"$in": matched_uids}})
    staff_filter = {"$or": staff_or}
    staff_rows = await db.staff_members.find(
        staff_filter, {"_id": 0, "id": 1}).to_list(length=100)
    staff_ids = [s["id"] for s in staff_rows if s.get("id")]
    _STAFF_CHILD_COLLS = [
        "staff_timesheets", "staff_leave_requests", "staff_shifts",
        "staff_swap_requests", "staff_disciplinary", "staff_training",
        "staff_documents", "staff_onboarding_cases", "staff_offboarding_cases",
        "staff_certs", "staff_clock_events", "staff_time_logs", "staff_tasks",
        "staff_form_submissions", "staff_access_provisions",
    ]
    try:
        from routes.master_admin import log_activity
        await log_activity(
            "user_purged_by_email",
            f"Hard-deleted {len(matched)} user row(s) matching '{email_clean}': "
            + ", ".join(f"{m['email']}/{m.get('role')}@{m.get('organization_id') or 'platform'}" for m in matched),
            user.get("email", ""),
            target_type="user_email",
            target_id=email_clean,
        )
    except Exception:
        pass

    deleted = {
        "users": (await db.users.delete_many(email_filter)).deleted_count,
        "crm_users": (await db.crm_users.delete_many(email_filter)).deleted_count,
        "invites": (await db.invites.delete_many(email_filter)).deleted_count,
        "signup_drafts": (await db.signup_drafts.delete_many(email_filter)).deleted_count,
        "signup_journey_jobs": (await db.signup_journey_jobs.delete_many({"to_email": email_clean})).deleted_count,
        "tour_bookings": (await db.tour_bookings.delete_many({"member_email": email_clean})).deleted_count,
        "staff_members": (await db.staff_members.delete_many(staff_filter)).deleted_count,
    }
    if staff_ids:
        for coll in _STAFF_CHILD_COLLS:
            try:
                n = (await getattr(db, coll).delete_many({"staff_id": {"$in": staff_ids}})).deleted_count
                if n:
                    deleted[coll] = n
            except Exception as exc:  # noqa: BLE001
                logger.warning("Purge cascade on %s failed: %s", coll, exc)
        # Org-chart node(s) referencing this staff member.
        try:
            n = (await db.org_chart_nodes.delete_many({"staff_id": {"$in": staff_ids}})).deleted_count
            if n:
                deleted["org_chart_nodes"] = n
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "email": email_clean, "matched_rows": len(matched),
            "staff_rows": len(staff_ids), "deleted": deleted}


@router.put("/master-admin/pulse-admins/{user_id}/org-memberships")
async def set_pulse_admin_org_memberships(user_id: str, body: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Attach a Pulse Platform Admin to one or more orgs as a member.

    The admin keeps their cross-org platform-admin role; this just makes
    them ALSO appear in those orgs' user lists. Pass `organization_ids` as
    a full replacement list (so passing `[]` clears all memberships).
    """
    _require_gymaxis_master(user)
    target = await db.users.find_one(
        {"id": user_id, "role": PULSE_ROLE},
        {"_id": 0, "id": 1, "email": 1, "active": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Pulse admin not found")
    raw_ids = body.get("organization_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="organization_ids must be a list")
    org_ids: list[str] = []
    for oid in raw_ids:
        if not isinstance(oid, str):
            continue
        existing = await db.organizations.find_one({"id": oid}, {"_id": 1})
        if existing:
            org_ids.append(oid)
    org_ids = sorted(set(org_ids))
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "organization_memberships": org_ids,
            "memberships_updated_at": datetime.now(timezone.utc).isoformat(),
            "memberships_updated_by": user.get("email"),
        }},
    )
    try:
        from routes.master_admin import log_activity
        await log_activity(
            "pulse_admin_memberships_updated",
            f"Set org memberships for {target['email']}: {org_ids}",
            user.get("email", ""),
            target_type="user",
            target_id=user_id,
        )
    except Exception:
        pass
    return {"ok": True, "organization_ids": org_ids}


@router.post("/master-admin/pulse-admins/{user_id}/reissue-temp-password")
async def reissue_pulse_admin_temp_password(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Rotate the temp password for an existing Pulse Master Admin.

    Useful when their original 7-day temp expired before first login or they
    lost the original email. Returns the new temp password to the caller iff
    Resend delivery fails so the Pulse Fitness Master can hand-deliver it.
    """
    _require_gymaxis_master(user)
    target = await db.users.find_one(
        {"id": user_id, "role": PULSE_ROLE},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "active": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Pulse admin not found")
    if target.get("active") is False:
        raise HTTPException(status_code=400, detail="This admin has been revoked — provision a fresh one instead.")

    temp_password = _generate_temp_password()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password": hash_password(temp_password),
            "must_change_password": True,
            "temp_password_expires_at": expires_at,
            "password_reissued_at": datetime.now(timezone.utc).isoformat(),
            "password_reissued_by": user.get("email"),
        }},
    )
    email_sent = await _send_pulse_admin_invite(target["email"], target.get("full_name", ""), temp_password)

    try:
        from routes.master_admin import log_activity
        await log_activity(
            "pulse_admin_pwd_reissued",
            f"Re-issued temp password for {target['email']}",
            user.get("email", ""),
            target_type="user",
            target_id=user_id,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "email_sent": email_sent,
        "temp_password": temp_password if not email_sent else None,
        "expires_at": expires_at,
    }


# ── Forced first-login password change ───────────────────────────────────

class ForceChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=120)


@router.post("/auth/force-change-password")
async def force_change_password(
    body: ForceChangePasswordIn,
    request: Request,
    response: Response,
    user: dict = Depends(get_current_user),
) -> dict:
    """Forces a password change on first login. Rotates the JWT cookie so the
    old session (issued for a temp password) is invalidated."""
    if not user.get("must_change_password"):
        raise HTTPException(status_code=400, detail="No password change required for this account")

    if not verify_password(body.current_password, user["password"]):
        raise HTTPException(status_code=401, detail="Current (temporary) password is incorrect")

    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the temporary one")

    validate_password_strength(body.new_password)

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password": hash_password(body.new_password),
            "must_change_password": False,
            "temp_password_expires_at": None,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    # Re-issue a fresh JWT + cookie so the old token (which carries no
    # special claims) is replaced cleanly.
    new_token = create_token(user["id"])
    set_auth_cookie(response, new_token)

    return {"ok": True, "token": new_token}


# ── Stripe Connect (Standard accounts via OAuth) ─────────────────────────

class StripeConnectPricingIn(BaseModel):
    """Per-customer pricing config used to compute the dynamic platform fee.

    The platform fee per charge is ``platform_fee_per_customer`` (flat amount)
    plus optionally ``platform_fee_pct`` (percentage of the charge). Both
    can be tuned by the Pulse Fitness Master Admin.
    """
    price_per_customer: float = Field(ge=0, le=10000)
    platform_fee_per_customer: float = Field(ge=0, le=10000)
    platform_fee_pct: float = Field(ge=0, le=100, default=0)
    currency: str = Field(default="GBP", min_length=3, max_length=3)


def _config_doc_id() -> str:
    """Singleton config document id — only one pricing config exists."""
    return "pulse_stripe_connect"


async def _get_pricing_config() -> dict:
    doc = await db.platform_config.find_one({"id": _config_doc_id()}, {"_id": 0})
    if not doc:
        return {
            "id": _config_doc_id(),
            "price_per_customer": 79.0,
            "platform_fee_per_customer": 12.0,
            "platform_fee_pct": 0.0,
            "currency": "GBP",
            "updated_at": None,
        }
    return doc


@router.get("/stripe-connect/pricing")
async def get_stripe_connect_pricing(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    cfg = await _get_pricing_config()
    return {"pricing": cfg}


@router.put("/stripe-connect/pricing")
async def update_stripe_connect_pricing(
    body: StripeConnectPricingIn, user: dict = Depends(get_current_user),
) -> dict:
    # Only the Pulse Fitness Master Admin can change platform pricing — Pulse admins
    # see it but cannot touch fees that determine our take.
    _require_gymaxis_master(user)
    update = {**body.dict(), "id": _config_doc_id(), "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.get("email")}
    await db.platform_config.update_one(
        {"id": _config_doc_id()}, {"$set": update}, upsert=True,
    )
    return {"ok": True, "pricing": await _get_pricing_config()}


def _connect_account_doc_filter(user: dict) -> dict:
    """Each pulse admin owns at most one connected Stripe account, scoped by
    their user_id. The Pulse Fitness Master Admin can introspect any."""
    if user.get("role") == PULSE_ROLE:
        return {"owner_user_id": user["id"]}
    if user.get("is_master_admin"):
        # When the Pulse Fitness admin asks for status, return the most recent
        # Pulse-side connection (there's expected to be one).
        return {"context": "pulse_fitness"}
    raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/stripe-connect/status")
async def stripe_connect_status(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.stripe_connect_accounts.find_one(_connect_account_doc_filter(user), {"_id": 0})
    if not doc:
        return {
            "connected": False,
            "configured": bool(STRIPE_CONNECT_CLIENT_ID and STRIPE_SECRET_KEY),
        }
    return {
        "connected": True,
        "configured": True,
        "account_id": doc.get("stripe_account_id"),
        "livemode": doc.get("livemode", False),
        "charges_enabled": doc.get("charges_enabled"),
        "payouts_enabled": doc.get("payouts_enabled"),
        "connected_at": doc.get("connected_at"),
        "country": doc.get("country"),
        "default_currency": doc.get("default_currency"),
    }


@router.get("/stripe-connect/onboard-url")
async def stripe_connect_onboard_url(user: dict = Depends(get_current_user)) -> dict:
    """Build the Stripe OAuth authorise URL. The frontend redirects the user
    to this URL; Stripe sends them back to STRIPE_CONNECT_REDIRECT_URI with
    a ``code`` we exchange for a connected account id."""
    _require_pulse_or_master(user)
    if not (STRIPE_CONNECT_CLIENT_ID and STRIPE_CONNECT_REDIRECT_URI):
        raise HTTPException(
            status_code=503,
            detail=(
                "Stripe Connect is not yet configured on the server. The platform admin must "
                "set STRIPE_CONNECT_CLIENT_ID and STRIPE_CONNECT_REDIRECT_URI in the backend "
                ".env, then restart."
            ),
        )

    # CSRF protection: state param tied to the user, stored server-side, with
    # 15-minute expiry. Stripe echoes it back in the callback.
    state = secrets.token_urlsafe(32)
    await db.stripe_connect_oauth_state.insert_one({
        "id": str(uuid.uuid4()),
        "state": state,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
    })

    params = {
        "response_type": "code",
        "client_id": STRIPE_CONNECT_CLIENT_ID,
        "scope": "read_write",
        "redirect_uri": STRIPE_CONNECT_REDIRECT_URI,
        "state": state,
        # `stripe_user[email]` pre-fills the OAuth form for the connected user.
        "stripe_user[email]": user.get("email", ""),
    }
    url = "https://connect.stripe.com/oauth/v2/authorize?" + urllib.parse.urlencode(params)
    return {"url": url, "state": state}


@router.get("/stripe-connect/callback")
async def stripe_connect_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
) -> dict:
    """Stripe OAuth callback. Exchanges ``code`` for the connected account id.

    Note: this is a redirect target — Stripe sends the browser here with
    ``?code=...&state=...``. The endpoint cannot rely on the user's auth
    cookie (different domain) so we identify the user via the persisted
    ``state`` document.
    """
    if error:
        return {"ok": False, "error": error, "description": error_description}
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    state_doc = await db.stripe_connect_oauth_state.find_one({"state": state}, {"_id": 0})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state — please retry the connection")
    if state_doc["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=400, detail="State expired — please retry the connection")
    user_id = state_doc["user_id"]

    # Exchange code for the connected account id.
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://connect.stripe.com/oauth/token",
            data={
                "client_secret": STRIPE_SECRET_KEY,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        logger.warning("Stripe OAuth exchange failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Stripe OAuth exchange failed")
    payload = resp.json()
    stripe_account_id = payload.get("stripe_user_id")
    if not stripe_account_id:
        raise HTTPException(status_code=502, detail="Stripe did not return a connected account id")

    # Pull live account capabilities so the UI can show charges_enabled etc.
    livemode = payload.get("livemode", False)
    capabilities = await _fetch_account_capabilities(stripe_account_id)

    now = datetime.now(timezone.utc).isoformat()
    await db.stripe_connect_accounts.update_one(
        {"owner_user_id": user_id},
        {"$set": {
            "owner_user_id": user_id,
            "context": "pulse_fitness",
            "stripe_account_id": stripe_account_id,
            "livemode": livemode,
            "scope": payload.get("scope"),
            "country": capabilities.get("country"),
            "default_currency": capabilities.get("default_currency"),
            "charges_enabled": capabilities.get("charges_enabled"),
            "payouts_enabled": capabilities.get("payouts_enabled"),
            "connected_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    # One-time use — drop the state.
    await db.stripe_connect_oauth_state.delete_one({"state": state})

    return {
        "ok": True,
        "account_id": stripe_account_id,
        "livemode": livemode,
        "charges_enabled": capabilities.get("charges_enabled"),
        "payouts_enabled": capabilities.get("payouts_enabled"),
    }


async def _fetch_account_capabilities(account_id: str) -> dict:
    """Hit Stripe's /v1/accounts/{id} for capability flags. Best-effort."""
    if not STRIPE_SECRET_KEY:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://api.stripe.com/v1/accounts/{account_id}",
                auth=(STRIPE_SECRET_KEY, ""),
            )
        if r.status_code != 200:
            return {}
        body = r.json()
        return {
            "charges_enabled": body.get("charges_enabled"),
            "payouts_enabled": body.get("payouts_enabled"),
            "country": body.get("country"),
            "default_currency": body.get("default_currency"),
        }
    except Exception as exc:  # pragma: no cover
        logger.info("stripe account capability fetch failed: %s", exc)
        return {}


@router.post("/stripe-connect/disconnect")
async def stripe_connect_disconnect(user: dict = Depends(get_current_user)) -> dict:
    _require_pulse_or_master(user)
    doc = await db.stripe_connect_accounts.find_one(_connect_account_doc_filter(user), {"_id": 0})
    if not doc:
        return {"ok": True}
    account_id = doc.get("stripe_account_id")

    # Deauthorise on Stripe's side. Best-effort — a 403 from Stripe (e.g.
    # already revoked) shouldn't block us from clearing the local doc.
    if account_id and STRIPE_SECRET_KEY and STRIPE_CONNECT_CLIENT_ID:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                await client.post(
                    "https://connect.stripe.com/oauth/deauthorize",
                    data={
                        "client_id": STRIPE_CONNECT_CLIENT_ID,
                        "stripe_user_id": account_id,
                    },
                    auth=(STRIPE_SECRET_KEY, ""),
                )
        except Exception as exc:
            logger.info("stripe deauthorize failed (non-fatal): %s", exc)

    await db.stripe_connect_accounts.delete_many(_connect_account_doc_filter(user))
    return {"ok": True}


# ── Setup-task snapshot ──────────────────────────────────────────────────


@router.get("/master-admin/setup-tasks")
async def setup_tasks_snapshot(user: dict = Depends(get_current_user)) -> dict:
    """Aggregate state used by the Setup Tasks panel on the Master Admin
    Overview. The frontend computes done/not-done from this snapshot — keep
    the shape stable.
    """
    _require_pulse_or_master(user)

    # Stripe state — `configured` mirrors the env-var check from /status.
    stripe_doc = await db.stripe_connect_accounts.find_one(
        _connect_account_doc_filter(user), {"_id": 0},
    )
    stripe = {
        "configured": bool(STRIPE_CONNECT_CLIENT_ID and STRIPE_SECRET_KEY),
        "connected": bool(stripe_doc),
        "charges_enabled": bool(stripe_doc and stripe_doc.get("charges_enabled")),
        "livemode": bool(stripe_doc and stripe_doc.get("livemode")),
    }

    # Integrations — flagged via the platform's integration-config rows so
    # ticking happens automatically as those get configured.
    sicon_cfg = await db.integration_configs.find_one({"id": "sicon"}, {"_id": 0, "configured": 1})
    orbit4_cfg = await db.integration_configs.find_one({"id": "orbit4"}, {"_id": 0, "configured": 1})
    integrations = {
        "sicon_configured": bool(sicon_cfg and sicon_cfg.get("configured")),
        "orbit4_configured": bool(orbit4_cfg and orbit4_cfg.get("configured")),
    }

    # Counts — bulk import progress. We count only non-trial / non-demo data
    # so seeded demo orgs don't trick the panel into thinking the work is
    # done. Customers come from CRM contacts; equipment from the ops side.
    pulse_org_filter = {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}}

    customer_count = 0
    try:
        # CRM contacts marked as customers under any Pulse-visible org.
        customer_count = await db.crm_contacts.count_documents({"is_customer": True})
    except Exception:
        pass
    equipment_count = await db.equipment.count_documents({})
    onboarding_packets_sent = await db.onboarding_packets.count_documents({"status": "sent"}) if "onboarding_packets" in await db.list_collection_names() else 0

    counts = {
        "customers": customer_count,
        "equipment": equipment_count,
        "onboarding_packets_sent": onboarding_packets_sent,
        "pulse_orgs": await db.organizations.count_documents(pulse_org_filter),
    }

    # Trust dashboard acknowledgement — quarterly review tick.
    last_ack = await db.trust_acknowledgements.find_one(
        {"user_id": user["id"]}, {"_id": 0, "acknowledged_at": 1}, sort=[("acknowledged_at", -1)],
    )
    trust = {
        "acknowledged_recently": False,
    }
    if last_ack and last_ack.get("acknowledged_at"):
        from datetime import timedelta as _td
        cutoff = (datetime.now(timezone.utc) - _td(days=90)).isoformat()
        trust["acknowledged_recently"] = last_ack["acknowledged_at"] > cutoff

    return {
        "stripe": stripe,
        "integrations": integrations,
        "counts": counts,
        "trust": trust,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/master-admin/pulse-organizations")
async def list_pulse_organizations(user: dict = Depends(get_current_user)) -> dict:
    """Lightweight org list scoped to Pulse-visible account types.

    Used by the Bulk Imports picker etc. Pulse Master Admins see this without
    triggering the full master-admin/organizations dashboard query (which is
    Pulse Fitness-master-only and quite expensive).
    """
    _require_pulse_or_master(user)
    rows = await db.organizations.find(
        {"account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1, "subscription_tier": 1, "created_at": 1},
    ).sort("name", 1).to_list(500)
    return {"organizations": rows}


__all__ = ["router", "PULSE_ROLE", "PULSE_VISIBLE_ACCOUNT_TYPES"]
