from fastapi import APIRouter, HTTPException, Depends, Request, Response
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import uuid
import asyncio
import secrets
import logging
import re

from utils.database import db
from utils.auth import get_current_user, optional_current_user, hash_password, verify_password, create_token, set_auth_cookie, clear_auth_cookie, purge_legacy_cookie_scopes, record_user_session
from utils.refresh_tokens import issue_refresh_token, clear_refresh_cookie, renew_access_from_refresh, revoke_refresh_cookie
from utils.email import send_welcome_email, send_password_reset_email
from utils.security import (
    rate_limit_login, rate_limit_password_reset, validate_password_strength,
    check_account_lockout, record_failed_login, clear_failed_logins,
    sanitise_string, rate_limit, _client_ip,
)
from models.schemas import UserRegister, UserLogin, InviteStaff

router = APIRouter()
logger = logging.getLogger(__name__)


async def _resolve_org_and_role(user: UserRegister, user_id: str) -> tuple:
    """Resolve organization and role for a registering user. Returns (org_id, role)."""
    if user.company_code:
        org = await db.organizations.find_one({"company_code": user.company_code}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=400, detail="Invalid company code")
        org_id = org["id"]
        invite = await db.invites.find_one({"email": user.email, "organization_id": org_id, "status": "pending"}, {"_id": 0})
        if invite:
            role = invite["role"]
            await db.invites.update_one(
                {"email": user.email, "organization_id": org_id},
                {"$set": {"status": "accepted", "accepted_at": datetime.now(timezone.utc).isoformat()}},
            )
        else:
            role = "staff"
        return org_id, role

    # New org
    org_id = str(uuid.uuid4())
    company_name = user.company_name or f"{user.full_name}'s Gym"
    company_code = str(uuid.uuid4())[:8].upper()
    org_doc = {
        "id": org_id, "name": company_name, "company_code": company_code,
        "owner_id": user_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "subscription_tier": "none",
    }
    # Iter 220p1 — USA readiness. Capture the prospect's market at signup so
    # currency / timezone / tax defaults are right from day one (defaults to
    # United Kingdom when the modal doesn't send a country).
    from utils.localization import resolve_org_fields
    org_doc.update(resolve_org_fields(getattr(user, "country_code", None)))
    # Iter 216h219 — Trial signup org-profile enrichment. The trial
    # modal's step-2 captures Industry / Employees / Website / referral
    # source + silent UTM tags from `window.location.search`. Persist
    # whatever was supplied (all optional — empty strings are ignored).
    enrichment_fields = {
        "website": (user.website or "").strip(),
        "industry": (user.industry or "").strip(),
        "employee_count": (user.employee_count or "").strip(),
        "phone": (user.phone or "").strip(),
        "referral_source": (user.referral_source or "").strip(),
        "utm_source": (user.utm_source or "").strip(),
        "utm_medium": (user.utm_medium or "").strip(),
        "utm_campaign": (user.utm_campaign or "").strip(),
        "utm_term": (user.utm_term or "").strip(),
        "utm_content": (user.utm_content or "").strip(),
        # Iter 216h227 — module-intent capture (see UserRegister docstring).
        "primary_module": (user.primary_module or "").strip().lower(),
    }
    for k, v in enrichment_fields.items():
        if v:
            org_doc[k] = v
    # Trial stamping (landing-page funnel)
    if getattr(user, "is_trial", False):
        # Iter 215bc — default trial dropped from 14 → 3 days. The marketing
        # page explicitly sends `trial_duration_days: 3` but legacy callers
        # without that field still default to 3 here.
        trial_days = max(1, min(90, int(getattr(user, "trial_duration_days", 3) or 3)))
        now_dt = datetime.now(timezone.utc)
        # Iter 215bc — trials now unlock all six modules so prospects can
        # evaluate the entire platform during the (shorter) 3-day window.
        # The flag is opt-in (defaults True in the marketing modal) but
        # legacy bolt-on funnels can pass `trial_unlock_all_modules=False`
        # to keep the old per-module trial behaviour.
        unlock_all = bool(getattr(user, "trial_unlock_all_modules", True))
        from utils.module_access import MODULE_KEYS
        # Iter 220ea·42 — module selector on signup. Resolve which modules
        # the prospect chose to trial. Sanitise against the known keys; an
        # empty/absent selection (legacy CTAs) falls back to "all modules".
        chosen_raw = getattr(user, "trial_modules", None) or []
        chosen = [m for m in (
            str(x).strip().lower() for x in chosen_raw
        ) if m in MODULE_KEYS]
        # De-dupe while preserving order.
        seen: set[str] = set()
        chosen = [m for m in chosen if not (m in seen or seen.add(m))]
        if not chosen:
            chosen = list(MODULE_KEYS)
        chose_all = set(chosen) == set(MODULE_KEYS)
        # Entitlement matrix — only the chosen modules are enabled; the
        # rest are explicitly locked so the trial really is "just what you
        # picked". `org.modules.<key>.enabled` is the canonical gate read
        # by `utils.module_access._org_module_access`.
        org_doc["modules"] = {
            key: {"enabled": key in chosen} for key in MODULE_KEYS
        }
        # Iter 220p1 — CRM audience choice (Gym / Corporate / Both). Sets the
        # leisure & business mode flags so the operator lands on the right CRM.
        if "crm" in chosen:
            cmode = (getattr(user, "crm_mode", None) or "gym").strip().lower()
            if cmode not in ("gym", "corporate", "both"):
                cmode = "gym"
            org_doc["modules"]["crm"]["leisure_enabled"] = cmode in ("gym", "both")
            org_doc["modules"]["crm"]["business_enabled"] = cmode in ("corporate", "both")
            org_doc["crm_mode_choice"] = cmode
        # Landing module for routing: honour an explicit primary_module if
        # it's one of the chosen, else default to the single chosen module
        # (or operations when several were picked / it's in the set).
        explicit_primary = (getattr(user, "primary_module", None) or "").strip().lower()
        if explicit_primary in chosen:
            landing = explicit_primary
        elif len(chosen) == 1:
            landing = chosen[0]
        elif "operations" in chosen:
            landing = "operations"
        else:
            landing = chosen[0]
        org_doc["primary_module"] = landing
        org_doc.update({
            "is_trial": True,
            "trial_started_at": now_dt.isoformat(),
            "trial_ends_at": (now_dt + timedelta(days=trial_days)).isoformat(),
            "trial_suspends_at": (now_dt + timedelta(days=trial_days + 30)).isoformat(),
            "trial_duration_days": trial_days,
            "trial_status": "active",
            "subscription_tier": "pro",  # full feature access during trial
            "trial_source": "landing_signup",
            # Only the chosen modules are enabled for the trial duration.
            "enabled_modules": list(chosen),
            "trial_selected_modules": list(chosen),
            "trial_all_modules_unlocked": chose_all and unlock_all,
        })
    await db.organizations.insert_one(org_doc)
    return org_id, "owner"


@router.post("/auth/register")
async def register(user: UserRegister, request: Request, response: Response) -> dict:
    # Rate limit (default 5 / 15 min per IP). Override with
    # REGISTER_RATE_LIMIT_MAX / REGISTER_RATE_LIMIT_WINDOW for test envs.
    ip = request.client.host if request.client else "unknown"
    from utils.security import rate_limit
    import os
    # Iter 219e — honour the same `X-RateLimit-Bypass` header that
    # `/auth/login` accepts so the CI / `make regression` suite can
    # legitimately register multiple test users from one IP without
    # tripping the production-tight 5/15min ceiling.
    bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "").strip()
    if not (bypass and request.headers.get("x-ratelimit-bypass", "") == bypass):
        max_req = int(os.environ.get("REGISTER_RATE_LIMIT_MAX", "5"))
        window = int(os.environ.get("REGISTER_RATE_LIMIT_WINDOW", "900"))
        rate_limit(f"register:{ip}", max_requests=max_req, window_seconds=window)

    # Turnstile captcha — required for landing-page trial signups only.
    # Existing CRM / gym-employee registration flows are untouched.
    if getattr(user, "is_trial", False):
        from utils.captcha import verify_captcha
        await verify_captcha(getattr(user, "cf_turnstile_response", None), action="trial_signup")

    # Iter 220ca — competitor blocklist. Trial signups from known
    # competitor domains (Orbit 4, ServiceSport, Mindbody, etc.) are
    # rejected at the door with a "talk to sales" message so they
    # can't casually snoop the dashboard. The list lives in
    # ``utils.competitor_blocklist`` and ships with the same CI gate
    # as the rest of the code.
    if getattr(user, "is_trial", False):
        from utils.competitor_blocklist import competitor_block_reason
        reason = competitor_block_reason(user.email)
        if reason:
            logger.info(
                "[competitor-block] rejected trial signup",
                extra={"email_domain": (user.email or "").split("@", 1)[-1]},
            )
            raise HTTPException(status_code=400, detail=reason)

    # Password strength
    validate_password_strength(user.password)

    existing = await db.users.find_one({"email": user.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    organization_id, role = await _resolve_org_and_role(user, user_id)

    user_doc = {
        "id": user_id, "email": user.email, "password": hash_password(user.password),
        "full_name": sanitise_string(user.full_name), "organization_id": organization_id,
        "role": role, "created_at": datetime.now(timezone.utc).isoformat(),
        "password_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if getattr(user, "phone", None):
        user_doc["phone"] = sanitise_string(user.phone)
    await db.users.insert_one(user_doc)
    asyncio.create_task(send_welcome_email(user.email, user.full_name))

    # Iter 215c2 — fire branded lifecycle welcome email (idempotent: only
    # sends once per organisation).
    try:
        from utils.lifecycle_emails import send_welcome_now
        org = await db.organizations.find_one({"id": organization_id}, {"_id": 0}) or {}
        asyncio.create_task(send_welcome_now(org, user_doc))
    except Exception:
        logger.exception("[lifecycle] welcome dispatch failed")

    # Trial signup — notify the platform owner so they can reach out.
    if getattr(user, "is_trial", False):
        try:
            from utils.email import send_trial_signup_notification
            asyncio.create_task(send_trial_signup_notification({
                "full_name": user.full_name,
                "email": user.email,
                "company_name": user.company_name or f"{user.full_name}'s Gym",
                "phone": getattr(user, "phone", None) or "",
                "trial_duration_days": int(getattr(user, "trial_duration_days", 14) or 14),
                "organization_id": organization_id,
            }))
        except Exception as e:  # pragma: no cover — non-blocking
            logger.warning(f"trial signup notification dispatch failed: {e}")

    org = await db.organizations.find_one({"id": organization_id}, {"_id": 0})
    # Iter 220au · F-03 — role-tiered TTL even for self-registered
    # users. Brand-new accounts are never master admins so this is
    # effectively the 24h default, but keeping the helper aligned
    # avoids drift between login and register paths.
    from utils.auth_guards import access_token_ttl_hours
    _ttl_hours = access_token_ttl_hours({"role": "owner"})
    token = create_token(user_id, expires_hours=_ttl_hours, mfa_verified=False)
    set_auth_cookie(response, token, max_age_hours=_ttl_hours)
    purge_legacy_cookie_scopes(response, request)
    await record_user_session(user_id, token, request)
    # Iter 267 — long-lived refresh cookie for idle-gap session resume.
    await issue_refresh_token(response, user_id, request, mfa_verified=False)

    # Iter 216h75 — Partner Engineer Network referral attribution. The
    # ref_code is bound write-once to the new org so the next cleared
    # Operations invoice automatically accrues commission. Failures here
    # must never block signup.
    try:
        from routes.partners import attach_referral_to_org
        await attach_referral_to_org(organization_id=organization_id, ref_code=getattr(user, "ref_code", None))
    except Exception:
        logger.exception("[partners] referral attribution failed")

    # Iter 219e — claim any pending partner_engineer rows that were
    # waiting for this email. Without this, every engineer approved
    # via the application drawer would stay locked out of the
    # partner dashboard because the `user_id` field on their row
    # stays as `pending:<partner_id>` until first auth.
    try:
        from utils.partner_claim import claim_pending_partner_for_user
        await claim_pending_partner_for_user(user.email, user_id)
    except Exception:
        logger.exception("[partners] pending-claim on register failed")

    return {
        "token": token,
        "user": {
            "id": user_id, "email": user.email, "full_name": user.full_name,
            "company_name": org["name"], "subscription_tier": org.get("subscription_tier", "none"),
            "role": role, "organization_id": organization_id,
            "company_code": org.get("company_code") if role in ["owner", "manager"] else None,
        },
    }


def _build_login_user_payload(user: dict, org: dict | None, trial_state: dict, features: list | dict) -> dict:
    """Assemble the `user` payload returned on successful login."""
    from utils.module_access import resolve_module_access, org_module_access
    is_owner_or_mgr = user.get('role') in ['owner', 'manager']
    return {
        "id": user['id'],
        "email": user['email'],
        "full_name": user['full_name'],
        "company_name": org['name'] if org else user.get('company_name'),
        "subscription_tier": (org.get('subscription_tier', 'none') if org else user.get('subscription_tier', 'none')),
        "role": user.get('role', 'owner'),
        "organization_id": user.get('organization_id'),
        "dealer_id": user.get('dealer_id'),
        "company_code": (org.get('company_code') if org and is_owner_or_mgr else None),
        "is_master_admin": user.get('is_master_admin', False),
        "org_is_operator": bool(org) and (
            (org or {}).get('account_type') in {"full", "pulse_pro", "lite", "mod_site", "mod_branch", "mod_org"}
            or any(isinstance(v, dict) and v.get("enabled") for v in ((org or {}).get("modules") or {}).values())
            or bool((org or {}).get("is_operator_company"))
        ),
        "is_service_desk": user.get('is_service_desk', False),
        "is_pulse_admin": user.get('is_pulse_admin', False) or user.get('role') == 'pulse_master_admin',
        "must_change_password": user.get('must_change_password', False),
        "is_shared_site_login": bool(user.get('is_shared_site_login')) or user.get('role') == 'site_staff',
        "site_id": user.get('site_id'),
        "allowed_site_ids": user.get('allowed_site_ids') or [],
        "account_type": org.get('account_type', 'full') if org else 'full',
        # Iter 253 — self-serve Service Provider setup wizard gate. Non-provider
        # accounts default True so existing flows never see a wizard.
        "service_ops_setup_complete": (org or {}).get('service_ops_setup_complete', True) if org else True,
        # Iter 220ea·32 — partner engineers have NO org, so account_type
        # resolves to 'full' and they were being routed to the Operations
        # dashboard on login. Surface an explicit flag the frontend uses to
        # send them to the Engineer App instead.
        "is_partner_engineer": bool(
            user.get('is_partner_engineer')
            or user.get('role') == 'engineer_partner'
            or user.get('account_type') == 'partner_engineer'
        ),
        # Iter 216h249 — surface `primary_module` so the frontend knows
        # which module the operator declared at signup. Drives:
        #   • TrialSignupModal post-signup navigation (lands on the
        #     module surface, not the generic /dashboard).
        #   • DashboardPage WelcomeHero / GamifiedOnboarding suppression
        #     (no Equipment-wizard prompts for Memberships / CRM /
        #     Marketing trials).
        "primary_module": (org or {}).get('primary_module') or '',
        "trial": trial_state,
        "features": features,
        # Include module-access matrix so the React ModuleSwitcher can light
        # up the correct module pills *immediately* after login — without
        # this the CRM / Marketing / Memberships pills don't appear until
        # the user reloads (which triggers `/auth/me`).
        "module_access": resolve_module_access(user, org),
        # Iter (Jul 2026) — org-level module access IGNORING the master-admin
        # full-access bypass, so the Master Admin operator PREVIEW can mirror
        # exactly what a customer of this org sees (applies account_type
        # defaults + trial windows).
        "org_module_access": org_module_access(org),
        "modules": (org or {}).get("modules") or {},
        "module_overrides": user.get("module_overrides") or {},
        "timetable_view_only": bool(user.get("timetable_view_only", False)),
        # Iter 220bz — drives the ProfileCompletionGate; empty string
        # = profile not yet completed, ISO timestamp = completed.
        "profile_completed_at": (org or {}).get("profile_completed_at") or "",
    }


async def _record_failed_login_with_trust(
    email: str,
    request: Request,
    reason: str = "wrong_password",
    user_id: str = "",
) -> None:
    """Increment lockout counter, write an audit row with the failure
    reason, and emit a trust event if the user is being brute-forced.

    Iter 216h210 — Craig flagged that the audit log showed "3 failed
    logins" with no details. We now record:
      • ``reason`` (one of: ``user_not_found``, ``wrong_password``,
        ``account_disabled``, ``temp_password_expired``,
        ``portal_mismatch``, ``mfa_failed``, ``rate_limited``,
        ``account_locked``).
      • ``user_id`` (if the account existed — empty string otherwise).

    Best-effort: never raises — the auth endpoint already returned 401.
    """
    record_failed_login(email)
    ip = request.client.host if request.client else ""
    ua = request.headers.get("User-Agent", "")[:300]
    # Audit row — Craig's "no details" gap. `details` is human-readable
    # so the timeline doesn't need a join to be useful.
    try:
        from utils.audit import audit_log
        await audit_log(
            "login_failed",
            user_id or "",
            email,
            "user",
            user_id or "",
            f"reason={reason}; ua={ua[:120]}",
            ip,
        )
    except Exception:
        pass
    try:
        from utils.trust_events import record_trust_event
        from utils.security import get_failed_login_count
        attempts = get_failed_login_count(email)
        if attempts >= 3:
            sev = "high" if attempts >= 5 else "med"
            await record_trust_event(
                type="security.brute_force", severity=sev,
                summary=f"{attempts} failed logins for {email}",
                payload={"email": email, "attempts": attempts, "ip": ip, "reason": reason},
                dedupe_key=f"security.brute_force:{email.lower()}",
            )
    except Exception:
        # Trust observability must never block the auth response.
        pass


async def _lookup_user_by_identifier(identifier: str) -> dict | None:
    """Dual-mode lookup. ``identifier`` is already lowercased & stripped.

    Classic email (contains ``@``) → ``users.email``.
    MOD-style site / kiosk username (no ``@``) → ``users.username``.

    Matching is CASE-INSENSITIVE: historic accounts were stored with the
    email/username as-typed (mixed case), but the login input is lowercased
    here — an exact (case-sensitive) Mongo match would then miss them and
    report "unknown user". An anchored case-insensitive regex fixes that.
    """
    pattern = {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}
    if "@" in identifier:
        user = await db.users.find_one({"email": pattern}, {"_id": 0})
        if user:
            return user
        # Iter 279 — cross-collection fallback. Accounts created by Master
        # Admin in a CRM-capable org (e.g. Pulse Fitness) can exist ONLY in
        # `crm_users`. Standard login previously reported "unknown user" for
        # them (the CRM login already does the reverse fallback). Both
        # collections use identical bcrypt hashing, so the password verifies
        # unchanged. Flag the source so login() can self-heal a `users` row.
        crm_user = await db.crm_users.find_one({"email": pattern}, {"_id": 0})
        if crm_user:
            crm_user["_from_crm"] = True
        return crm_user
    return await db.users.find_one({"username": pattern}, {"_id": 0})


async def _mirror_crm_user_to_users(crm_user: dict, plaintext_password: str) -> dict:
    """Iter 279 — promote a CRM-only account into the service-portal `users`
    collection on first standard-portal login, so every downstream operator
    / session / audit flow has a canonical `users` row. Mirrors the reverse
    self-heal that `routes/crm_auth.crm_login` already performs. Idempotent:
    returns the existing `users` row if one is already present."""
    existing = await db.users.find_one({"id": crm_user["id"]}, {"_id": 0})
    if not existing:
        email_lc = (crm_user.get("email") or "").lower()
        existing = await db.users.find_one(
            {"email": {"$regex": f"^{re.escape(email_lc)}$", "$options": "i"}},
            {"_id": 0},
        )
    if existing:
        return existing
    org = await db.organizations.find_one(
        {"id": crm_user.get("organization_id")}, {"_id": 0, "account_type": 1},
    ) or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    mirrored = {
        "id": crm_user["id"],
        "email": (crm_user.get("email") or "").lower(),
        "full_name": crm_user.get("full_name") or crm_user.get("name") or "",
        "password": hash_password(plaintext_password),
        "organization_id": crm_user.get("organization_id"),
        "role": crm_user.get("role") or "staff",
        "account_type": org.get("account_type", "full"),
        "avatar_url": crm_user.get("avatar_url"),
        "created_at": crm_user.get("created_at") or now_iso,
        "password_updated_at": now_iso,
        "cross_login_provisioned": True,
        "mirrored_from_crm_at": now_iso,
    }
    await db.users.insert_one(dict(mirrored))
    return mirrored


def _enforce_account_status(user: dict) -> None:
    """Refuse logins for disabled accounts or expired temp passwords. Raises
    ``HTTPException`` on failure; returns ``None`` when the account is good."""
    if user.get("active") is False:
        # Provisioned-but-revoked accounts (e.g. removed Pulse Master Admins)
        # must not log in even if they still know their password.
        raise HTTPException(status_code=403, detail="Account disabled")
    expires = user.get("temp_password_expires_at")
    if user.get("must_change_password") and expires:
        if expires < datetime.now(timezone.utc).isoformat():
            raise HTTPException(
                status_code=401,
                detail="Temporary password has expired — ask the platform admin to reissue.",
            )


async def _maybe_issue_mfa_step1(user: dict) -> dict | None:
    """Return the MFA step-1 response when the user has MFA enabled.

    The full JWT is withheld; the caller must hit ``/auth/mfa/verify`` with
    the returned ``temp_token`` plus a TOTP code to complete login.

    Iter 216h116 — when the user's role mandates MFA (e.g. MOD HQ) but
    they have NOT enrolled yet, return an ``enrolment_required`` step
    instead. The temp_token then only permits ``/auth/mfa/setup`` and
    ``/auth/mfa/enable`` (gated via ``get_current_user_mfa_enrol``).
    """
    from utils.mfa import user_requires_mfa, user_mfa_state
    requires = user_requires_mfa(user)
    if not requires:
        return None
    state = await user_mfa_state(user["id"])
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    if not state["enabled"]:
        # Iter 216h116 — MFA mandatory but not enrolled. Only force the
        # MOD HQ tier through the in-line enrolment flow (master admins
        # retain the historical opt-in behaviour so as not to break
        # existing dev/test logins).
        if (user.get("account_type") or "").lower() not in ("mod_org", "mod_branch"):
            return None
        enrol_payload = {
            "user_id": user["id"],
            "type": "mfa_enrol",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "iat": datetime.now(timezone.utc),
        }
        return {
            "requires_mfa_enrolment": True,
            "temp_token": _jwt.encode(enrol_payload, JWT_SECRET, algorithm=JWT_ALGORITHM),
            "user": {"email": user["email"], "full_name": user.get("full_name", "")},
            "reason": "Two-factor authentication is mandatory for this account.",
        }
    temp_payload = {
        "user_id": user["id"],
        "type": "mfa_temp",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "iat": datetime.now(timezone.utc),
    }
    return {
        "requires_mfa": True,
        "temp_token": _jwt.encode(temp_payload, JWT_SECRET, algorithm=JWT_ALGORITHM),
        "user": {"email": user["email"], "full_name": user.get("full_name", "")},
    }


async def _finalise_successful_login(user: dict, request: Request, response: Response, *, mfa_verified: bool = False) -> dict:
    """Mint the JWT, set the cookie, write the audit row, refresh
    ``last_login`` and return the public response payload.

    Iter 220au — accepts an ``mfa_verified`` flag (set True after a
    successful TOTP challenge or when the account doesn't require MFA)
    and uses role-tiered TTL via ``utils.auth_guards.access_token_ttl_hours``.
    """
    from utils.auth_guards import access_token_ttl_hours
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    ttl_hours = access_token_ttl_hours(user)
    token = create_token(user["id"], expires_hours=ttl_hours, mfa_verified=mfa_verified)
    set_auth_cookie(response, token, max_age_hours=ttl_hours)
    purge_legacy_cookie_scopes(response, request)
    await record_user_session(user["id"], token, request)
    # Iter 267 — issue a long-lived refresh cookie so the session resumes
    # after the short access token lapses (idle/sleep). Real login only.
    await issue_refresh_token(response, user["id"], request, mfa_verified=mfa_verified)

    ip = request.client.host if request.client else ""
    from utils.audit import audit_log
    await audit_log("login", user["id"], user["email"], "user", user["id"], "Successful login", ip)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}},
    )

    # Activation event — first ever login per organisation. Best-effort.
    if user.get("organization_id"):
        try:
            from routes.activation_events import record_activation_event
            await record_activation_event(
                user["organization_id"], "first_login",
                trigger_user_id=user["id"],
            )
        except Exception:
            pass

    # Iter 219e — claim any pending partner_engineer rows that were
    # waiting for this email. Without this, the 37 already-approved
    # engineers whose user_id sits at `pending:<partner_id>` cannot
    # see any partner UI after login. Idempotent + best-effort.
    try:
        from utils.partner_claim import claim_pending_partner_for_user
        if await claim_pending_partner_for_user(user.get("email"), user["id"]):
            user["is_partner_engineer"] = True
    except Exception:
        logger.exception("[partners] pending-claim on login failed")

    from utils.trial_lifecycle import compute_trial_state
    from utils.feature_guard import get_enabled_features
    trial_state = compute_trial_state(org) if org else {"is_trial": False}
    features = await get_enabled_features(user)
    return {"token": token, "user": _build_login_user_payload(user, org, trial_state, features)}


@router.post("/auth/login")
async def login(credentials: UserLogin, request: Request, response: Response) -> dict:
    """Login orchestrator — see helpers above for each phase."""
    # Iter 279 — the single master-admin account must never be blocked by the
    # strict 5-per-5-min IP gate or the account-lockout counter (Craig: "a
    # master admin shouldn't have to wait to log in"). We still record failed
    # attempts for audit and still require the correct password / MFA, and we
    # keep a GENEROUS ceiling so the privileged account isn't a free
    # brute-force target.
    import os
    _master_email = (os.environ.get("MASTER_ADMIN_EMAIL", "") or "").strip().lower()
    is_master_login = bool(_master_email) and (credentials.email or "").strip().lower() == _master_email

    # 1. Anti-abuse gates. Wrap both so a thrown lockout/rate-limit is
    # itself an auditable event (Iter 216h210 — Craig saw "3 failed
    # logins" but no rows when the account had hit the lockout).
    try:
        if is_master_login:
            rate_limit(f"login-master:{_client_ip(request)}", max_requests=60, window_seconds=300)
        else:
            rate_limit_login(request)
    except HTTPException:
        await _record_failed_login_with_trust(
            credentials.email, request, reason="rate_limited",
        )
        raise
    if not is_master_login:
        try:
            check_account_lockout(credentials.email)
        except HTTPException:
            await _record_failed_login_with_trust(
                credentials.email, request, reason="account_locked",
            )
            raise
    from utils.captcha import verify_captcha
    await verify_captcha(request.headers.get("x-captcha-token"), action="login")

    # 2. Identify + authenticate.
    identifier = credentials.email.strip().lower()
    user = await _lookup_user_by_identifier(identifier)
    if not user:
        # Iter 216h210 — record the attempt even when the account
        # doesn't exist. Operators investigating "3 failed logins"
        # need to know if the username was wrong vs the password.
        await _record_failed_login_with_trust(
            credentials.email, request,
            reason="user_not_found",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(credentials.password, user["password"]):
        await _record_failed_login_with_trust(
            credentials.email, request,
            reason="wrong_password",
            user_id=user.get("id", ""),
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Iter 279 — self-heal a CRM-only account into the service-portal
    # `users` collection on first standard-portal login (password already
    # verified above). Downstream flows then operate on a canonical row.
    if user.get("_from_crm"):
        user = await _mirror_crm_user_to_users(user, credentials.password)

    # 3. Account-state checks.
    try:
        _enforce_account_status(user)
    except HTTPException as exc:
        # Surface the *reason* (disabled vs temp-expired) into the audit
        # trail so the security team can answer "why is Craig locked out?"
        # in one glance.
        sub_reason = (
            "account_disabled" if exc.status_code == 403
            else "temp_password_expired"
        )
        await _record_failed_login_with_trust(
            credentials.email, request,
            reason=sub_reason,
            user_id=user.get("id", ""),
        )
        raise

    # 3b. Portal-scope enforcement (Iter 216h113f).
    # MODService is its own entity — visitors signing in on
    # /MODService MUST have a MOD account_type, and conversely MOD
    # users cannot sign in via the standard Pulse Fitness login
    # (preventing the cross-tenant leak where a `*@mod.gov.uk` user
    # who happens to be a Third Space team member ends up on the
    # MOD-branded shell of Third Space's tenant).
    requested_portal = (credentials.portal or "").lower().strip()
    user_at = (user.get("account_type") or "").lower()
    is_mod_user = user_at.startswith("mod_")
    if requested_portal == "mod" and not is_mod_user:
        await _record_failed_login_with_trust(
            credentials.email, request,
            reason="portal_mismatch_not_mod",
            user_id=user.get("id", ""),
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "This account is not registered for the MOD Service Portal. "
                "Please sign in via your unit's standard Pulse Fitness URL."
            ),
        )
    if requested_portal in ("", "pulse", "standard") and is_mod_user:
        await _record_failed_login_with_trust(
            credentials.email, request,
            reason="portal_mismatch_mod_user_on_pulse",
            user_id=user.get("id", ""),
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "MOD personnel accounts must sign in via the MOD Service "
                "Portal at /MODService."
            ),
        )

    # 4. Successful login — clear lockout counter & honour MFA if configured.
    clear_failed_logins(credentials.email)
    mfa_response = await _maybe_issue_mfa_step1(user)
    if mfa_response is not None:
        return mfa_response

    # 5. Mint full session.
    return await _finalise_successful_login(user, request, response)


# ── Master Admin Recovery (deploy lifeline) ─────────────────────────────
# Single-purpose, env-gated endpoint to (re)create or repair the master
# admin without needing access to the running container. The endpoint
# accepts ONLY the recovery token configured at deploy-time via the
# `ADMIN_RECOVERY_TOKEN` env var. If the env var is unset/empty, the
# endpoint refuses every request — keeping it inert when not needed.
#
# Use case: prod deployed, `_seed_master_admin` failed silently or DB was
# replaced and the admin no longer exists / has a stale password. Hit:
#   curl -X POST $URL/api/auth/admin-recovery \
#     -H "Content-Type: application/json" \
#     -d '{"recovery_token":"…","email":"admin@pulsefitness.ai","password":"NewPass123!"}'
# Then unset / rotate ADMIN_RECOVERY_TOKEN once you're back in.

@router.post("/auth/admin-recovery")
async def admin_recovery(body: dict, request: Request) -> dict:
    import os
    expected = os.environ.get("ADMIN_RECOVERY_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Recovery is disabled on this deployment")
    provided = (body.get("recovery_token") or "").strip()
    # Constant-time compare so we don't leak token via timing.
    if not secrets.compare_digest(expected, provided):
        # Tiny sleep to slow down brute-force attempts.
        await asyncio.sleep(1.5)
        raise HTTPException(status_code=403, detail="Invalid recovery token")

    email = (body.get("email") or "").strip().lower()
    new_password = body.get("password") or ""
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 chars")

    now_iso = datetime.now(timezone.utc).isoformat()
    set_doc = {
        "email": email,
        "password": hash_password(new_password),
        "is_master_admin": True,
        "active": True,
        "must_change_password": False,
        "temp_password_expires_at": None,
        "password_changed_at": now_iso,
        "role": "owner",
    }

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "organization_id": 1})
    if existing:
        await db.users.update_one(
            {"email": email},
            {"$set": set_doc, "$unset": {"lockout_until": ""}},
        )
        admin_id = existing["id"]
        org_id = existing.get("organization_id")
    else:
        # Need an org for the master admin record.
        org = await db.organizations.find_one({"name": "Pulse Fitness AI Admin"}, {"_id": 0, "id": 1})
        if org:
            org_id = org["id"]
        else:
            org_id = str(uuid.uuid4())
            await db.organizations.insert_one({
                "id": org_id, "name": "Pulse Fitness AI Admin",
                "subscription_tier": "premium",
                "created_at": now_iso,
            })
        admin_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": admin_id,
            "full_name": "Master Admin",
            "organization_id": org_id,
            "created_at": now_iso,
            **set_doc,
        })

    clear_failed_logins(email)
    ip = request.client.host if request.client else ""
    logger.warning("[admin-recovery] master admin %s recovered/reset from %s", email, ip)
    try:
        from utils.audit import audit_log
        await audit_log("admin_recovery", admin_id, email, "user", admin_id,
                        f"Master admin password recovered via recovery token from {ip}", ip)
    except Exception:
        pass
    return {"success": True, "email": email, "message": "Master admin password reset. Please sign in."}


# ── Forgot / Reset Password ──────────────────────────────────────

@router.post("/auth/forgot-password")
async def forgot_password(body: dict, request: Request) -> dict:
    rate_limit_password_reset(request)
    from utils.captcha import verify_captcha
    await verify_captcha(request.headers.get("x-captcha-token"), action="forgot_password")
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "email": 1, "full_name": 1, "organization_id": 1})
    # Iter 279 — a Master-Admin-created account in a CRM-capable org can
    # live ONLY in `crm_users`. Without this fallback the reset link was
    # never issued for them (silent success → "set password link didn't
    # work"). Match case-insensitively to be safe.
    if not user:
        pattern = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        user = await db.crm_users.find_one(
            {"email": pattern},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "organization_id": 1},
        )

    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If an account exists with that email, a reset link has been sent."}

    token = secrets.token_urlsafe(32)
    # Iter 220au · F-02 — tighten password-reset TTL from 1 h to 15 min.
    # ``utils.auth_guards.PASSWORD_RESET_TTL_MINUTES`` is env-tunable.
    from utils.auth_guards import PASSWORD_RESET_TTL_MINUTES
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)).isoformat()
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": user["id"],
        "email": email,
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Iter 216h192 — password-reset links must use the brand-aware app URL
    # so production emails point at pulsefitness.ai / pulsefitness.ai instead
    # of the preview deployment (which was the cause of "Invalid Reset Link"
    # in production: clicking the preview-domain link hit a different DB
    # than the one that issued the token).
    from utils.brand_urls import app_url_for_org
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0, "account_type": 1}) if user.get("organization_id") else None
    frontend_url = app_url_for_org(org)
    reset_url = f"{frontend_url}/reset-password?token={token}"
    logger.info(f"[PASSWORD RESET] Reset link for {email}: {reset_url}")

    email_sent = await send_password_reset_email(email, user.get("full_name", ""), reset_url)
    if not email_sent:
        logger.warning(f"[PASSWORD RESET] Email delivery failed for {email}. Token logged above for manual use.")

    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password(body: dict, request: Request) -> dict:
    # Per-IP rate limit (3 / 15 min) — same limiter as forgot-password, so a
    # leaked/guessed reset token can't be paired with high-volume submissions.
    rate_limit_password_reset(request)
    token = body.get("token", "")
    new_password = body.get("password", "")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and password are required")

    # Enforce password strength on reset too
    validate_password_strength(new_password)

    reset_doc = await db.password_reset_tokens.find_one({"token": token, "used": False}, {"_id": 0})
    if not reset_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    expires_at = datetime.fromisoformat(reset_doc["expires_at"]) if isinstance(reset_doc["expires_at"], str) else reset_doc["expires_at"].replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Reset token has expired")

    hashed = hash_password(new_password)
    now_iso = datetime.now(timezone.utc).isoformat()
    # Iter 279 — update the password in BOTH collections keyed by user_id.
    # CRM-only accounts (created by Master Admin in a CRM-capable org) have
    # no `users` row until first login, so a `users`-only update silently
    # did nothing — which is exactly why the emailed reset link "didn't
    # work" for them. Both collections use identical bcrypt hashing.
    users_res = await db.users.update_one(
        {"id": reset_doc["user_id"]},
        {"$set": {
            "password": hashed,
            "password_updated_at": now_iso,
        }},
    )
    crm_res = await db.crm_users.update_one(
        {"id": reset_doc["user_id"]},
        {"$set": {
            "password": hashed,
            "password_updated_at": now_iso,
            "cross_login_provisioned": True,
        }},
    )
    if users_res.matched_count == 0 and crm_res.matched_count == 0:
        logger.warning(
            "[PASSWORD RESET] Token valid but no user row found for user_id=%s",
            reset_doc.get("user_id"),
        )
    await db.password_reset_tokens.update_one({"token": token}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}})

    # Iter 216h29 — auto-archive every other still-unused invite token
    # for this user. Operators who re-issued an invite while the first
    # was still valid sometimes left two live links in the wild; from
    # here on, the moment one is redeemed the rest become inert.
    archived = await db.password_reset_tokens.update_many(
        {
            "user_id": reset_doc["user_id"],
            "token": {"$ne": token},
            "used": False,
        },
        {"$set": {
            "used": True,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_reason": "auto_archived_after_sibling_redeemed",
        }},
    )
    if archived.modified_count:
        logger.info(f"[INVITE] Auto-archived {archived.modified_count} sibling invite tokens for user {reset_doc['user_id']}")

    # Iter 215ar — clear the org-level "initial password" reveal once the
    # primary contact has rotated their password (so master-admin no longer
    # sees a stale plaintext credential in the panel).
    user_doc = await db.users.find_one({"id": reset_doc["user_id"]}, {"_id": 0, "organization_id": 1, "email": 1})
    if user_doc and user_doc.get("organization_id"):
        await db.organizations.update_one(
            {
                "id": user_doc["organization_id"],
                "primary_contact_email": (user_doc.get("email") or "").strip().lower(),
            },
            {"$set": {"primary_contact_password_changed": True},
             "$unset": {"primary_contact_initial_password": ""}},
        )

    logger.info(f"[PASSWORD RESET] Password reset successful for user {reset_doc['user_id']}")
    return {"message": "Password has been reset successfully. You can now log in."}



@router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0})

    from utils.trial_lifecycle import compute_trial_state
    from utils.feature_guard import get_enabled_features
    from utils.hardening import password_needs_rotation, PASSWORD_MAX_AGE_DAYS
    from utils.module_access import resolve_module_access, org_module_access
    trial_state = compute_trial_state(org) if org else {"is_trial": False}
    features = await get_enabled_features(user)
    module_access = resolve_module_access(user, org)

    # Iter — operator-vs-system org discriminator. A master admin whose OWN
    # org is a real operator company (Pulse Fitness Ltd — has a real account
    # type or enabled modules, or is the pinned operator) lands on the
    # operator platform on login; the global admin (system org with no
    # modules) keeps landing on /master-admin. Computed from the RAW org doc
    # so the account_type fallback above can't mask a system org.
    _OPERATOR_ACCOUNT_TYPES = {"full", "pulse_pro", "lite", "mod_site", "mod_branch", "mod_org"}
    _raw_at = (org or {}).get("account_type")
    _raw_modules = (org or {}).get("modules") or {}
    org_is_operator = bool(org) and (
        _raw_at in _OPERATOR_ACCOUNT_TYPES
        or any(isinstance(v, dict) and v.get("enabled") for v in _raw_modules.values())
        or bool((org or {}).get("is_operator_company"))
    )

    return {
        "id": user['id'],
        "email": user['email'],
        "full_name": user['full_name'],
        "company_name": org['name'] if org else user.get('company_name'),
        "subscription_tier": org.get('subscription_tier', 'none') if org else user.get('subscription_tier', 'none'),
        "role": user.get('role', 'owner'),
        "organization_id": user.get('organization_id'),
        "company_code": org.get('company_code') if org and user.get('role') in ['owner', 'manager'] else None,
        "is_master_admin": user.get('is_master_admin', False),
        "org_is_operator": org_is_operator,
        "is_pulse_admin": user.get('is_pulse_admin', False) or user.get('role') == 'pulse_master_admin',
        "is_service_desk": user.get('is_service_desk', False),
        # Site Staff Shared Login — flags the shared kiosk account so the
        # Operations fault flow enforces the mandatory "who is logging
        # this fault?" staff dropdown and the UI hides management areas.
        "is_shared_site_login": bool(user.get('is_shared_site_login')) or user.get('role') == 'site_staff',
        "site_id": user.get('site_id'),
        "allowed_site_ids": user.get('allowed_site_ids') or [],
        "account_type": org.get('account_type', 'full') if org else 'full',
        # Iter 253 — self-serve Service Providers: the frontend routes
        # incomplete setups to /service-desk/setup on login/refresh.
        "service_ops_setup_complete": (org or {}).get('service_ops_setup_complete', True) if org else True,
        # Iter 220ea·32 — see /auth/login: partner engineers (no org) must
        # route to the Engineer App, not the Operations dashboard.
        "is_partner_engineer": bool(
            user.get('is_partner_engineer')
            or user.get('role') == 'engineer_partner'
            or user.get('account_type') == 'partner_engineer'
        ),
        # Iter 216h249 — see /auth/login docstring for context.
        "primary_module": (org or {}).get('primary_module') or '',
        "avatar_url": user.get('avatar_url'),
        "phone": user.get('phone'),
        # Iter 239 — per-user UI language (en/fr/de); the frontend applies
        # it via i18n.changeLanguage on boot so it follows across devices.
        "language": user.get('language'),
        "trial": trial_state,
        "features": features,
        "module_access": module_access,
        "org_module_access": org_module_access(org),
        "modules": (org or {}).get("modules") or {},
        "module_overrides": user.get("module_overrides") or {},
        "timetable_view_only": bool(user.get("timetable_view_only", False)),
        "password_needs_rotation": password_needs_rotation(user),
        "password_max_age_days": PASSWORD_MAX_AGE_DAYS,
        # Iter 220bz — drives the ProfileCompletionGate. Empty string
        # = profile not yet completed; ISO timestamp = completed.
        "profile_completed_at": (org or {}).get("profile_completed_at") or "",
    }


@router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response, user: Optional[dict] = Depends(optional_current_user)) -> dict:
    """Issue a fresh JWT token + revoke the old one (rotation).

    Iter 216h54 — the old jti is revoked with a 60-second grace window
    so any in-flight requests that already captured the old token
    (App.js loadSites / loadBranding / freshly-mounted dashboards)
    can complete cleanly before the deny list kicks in.

    Iter 220au · F-03 / F-17 — refresh now preserves the
    ``mfa_verified`` claim and uses role-tier TTL so master admins
    always rotate into a fresh 1-hour token.

    Iter 227 — also rotates the HttpOnly ``ga_session`` cookie so a
    cookie-only main session (no localStorage token) stays alive past
    the original cookie's max-age.

    Iter 267 — if the access token has FULLY EXPIRED (no valid `user`),
    fall back to the long-lived ``ga_refresh`` cookie to mint a brand-new
    access token, so an idle/slept session resumes without re-login.
    """
    from utils.security_plus import revoke_jwt
    from utils.auth_guards import access_token_ttl_hours
    if user is None:
        # Recovery path — access token absent/expired; try the refresh cookie.
        recovered = await renew_access_from_refresh(request, response)
        if not recovered:
            raise HTTPException(status_code=401, detail="Not authenticated")
        new_token, _ = recovered
        return {"token": new_token}
    old_jti = user.get("_jwt_jti")
    old_exp = user.get("_jwt_exp") or int(datetime.now(timezone.utc).timestamp()) + 86400
    ttl_hours = access_token_ttl_hours(user)
    new_token = create_token(
        user['id'],
        expires_hours=ttl_hours,
        mfa_verified=bool(user.get("_jwt_mfa_verified")),
    )
    if old_jti:
        await revoke_jwt(old_jti, int(old_exp), reason="refresh", grace_seconds=60)
    # Iter 227 — only rotate the HttpOnly cookie for COOKIE-based (main)
    # sessions. A header-based session (impersonation / API token) must NOT
    # overwrite the admin's `ga_session` cookie, or ending impersonation
    # would strand the operator as the impersonated user.
    auth_hdr = request.headers.get("authorization", "")
    header_token = ""
    if auth_hdr.lower().startswith("bearer "):
        cand = auth_hdr.split(" ", 1)[1].strip()
        if cand and cand.lower() not in ("null", "undefined", "cookie"):
            header_token = cand
    if not header_token:
        set_auth_cookie(response, new_token, max_age_hours=ttl_hours)
        purge_legacy_cookie_scopes(response, request)
        # Iter 232 — keep the device's session-registry row alive across
        # rotation (same row, new jti, original created_at).
        await record_user_session(user["id"], new_token, request, replaces_jti=old_jti)
    return {"token": new_token}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: Optional[dict] = Depends(optional_current_user)) -> dict:
    """P1+.11 — kill the current JWT so it can't be reused if stolen later.

    Also clears the HttpOnly session cookie so the browser no longer
    re-authenticates automatically.

    Iter 267 — additionally revoke + clear the long-lived ``ga_refresh``
    cookie, and tolerate an expired access token (idempotent logout) so a
    user whose access token has lapsed can still fully sign out.
    """
    from utils.security_plus import revoke_jwt, audit_required
    if user is not None:
        jti = user.get("_jwt_jti")
        exp = user.get("_jwt_exp") or int(datetime.now(timezone.utc).timestamp()) + 86400
        if jti:
            await revoke_jwt(jti, int(exp), reason="logout")
            await audit_required("security_audit_log", {
                "event": "auth.logout", "actor_id": user["id"], "actor_email": user.get("email"),
                "jti": jti,
            })
            try:
                await db.user_sessions.delete_one({"jti": jti, "user_id": user["id"]})
            except Exception:
                pass
    await revoke_refresh_cookie(request)
    clear_auth_cookie(response)
    clear_refresh_cookie(response)
    return {"success": True}


# ════════════════ Iter 232 — active sessions panel ════════════════

@router.get("/auth/sessions")
async def list_active_sessions(user: dict = Depends(get_current_user)) -> dict:
    """Devices with a live session for the signed-in user.

    Powers the account-settings "Active sessions" panel. The row whose
    jti matches the calling token is flagged ``current``.
    """
    now = datetime.now(timezone.utc)
    cur_jti = user.get("_jwt_jti")
    rows = await db.user_sessions.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("last_seen_at", -1).to_list(50)
    out = []
    stale_ids = []
    for r in rows:
        exp_ts = r.get("exp_ts") or 0
        if exp_ts and exp_ts < int(now.timestamp()):
            stale_ids.append(r.get("id"))
            continue
        out.append({
            "id": r.get("id"),
            "device": r.get("device") or "Unknown device",
            "ip": r.get("ip") or "",
            "created_at": r.get("created_at"),
            "last_seen_at": r.get("last_seen_at"),
            "expires_at": r.get("expires_at"),
            "current": bool(cur_jti) and r.get("jti") == cur_jti,
        })
    if stale_ids:
        await db.user_sessions.delete_many({"id": {"$in": stale_ids}})
    return {"sessions": out}


@router.post("/auth/sessions/{session_id}/revoke")
async def revoke_one_session(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Sign out a SINGLE other device (revokes that session's jti)."""
    from utils.security_plus import revoke_jwt, audit_required
    row = await db.user_sessions.find_one(
        {"id": session_id, "user_id": user["id"]}, {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if row.get("jti") == user.get("_jwt_jti"):
        raise HTTPException(status_code=400, detail="Use /auth/logout to end the current session")
    exp_ts = row.get("exp_ts") or int(datetime.now(timezone.utc).timestamp()) + 86400
    await revoke_jwt(row["jti"], int(exp_ts), reason="user_revoked_device")
    await db.user_sessions.delete_one({"id": session_id})
    await audit_required("security_audit_log", {
        "event": "auth.session_revoked", "actor_id": user["id"],
        "actor_email": user.get("email"), "session_id": session_id,
        "device": row.get("device"), "ip": row.get("ip"),
    })
    return {"success": True}


@router.post("/auth/sessions/revoke-others")
async def revoke_other_sessions(user: dict = Depends(get_current_user)) -> dict:
    """"Sign out everywhere else" — kills every session except this one.

    Belt and braces: each REGISTERED other session's jti goes on the
    deny list, and ``tokens_revoked_before`` is stamped with the current
    token's iat so even UNREGISTERED legacy tokens (minted before this
    feature shipped) die too — while the calling token (iat == cutoff)
    survives.
    """
    from utils.security_plus import revoke_jwt, audit_required
    cur_jti = user.get("_jwt_jti")
    rows = await db.user_sessions.find(
        {"user_id": user["id"]}, {"_id": 0, "id": 1, "jti": 1, "exp_ts": 1},
    ).to_list(100)
    revoked = 0
    for r in rows:
        if r.get("jti") and r["jti"] != cur_jti:
            exp_ts = r.get("exp_ts") or int(datetime.now(timezone.utc).timestamp()) + 86400
            await revoke_jwt(r["jti"], int(exp_ts), reason="sign_out_everywhere")
            await db.user_sessions.delete_one({"id": r.get("id")})
            revoked += 1
    iat = user.get("_jwt_iat")
    try:
        iat_epoch = int(iat.timestamp()) if isinstance(iat, datetime) else int(iat or 0)
    except (TypeError, ValueError):
        iat_epoch = 0
    if iat_epoch:
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {
                "tokens_revoked_before": iat_epoch,
                "tokens_revoked_reason": "sign_out_everywhere",
                "tokens_revoked_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    await audit_required("security_audit_log", {
        "event": "auth.sign_out_everywhere", "actor_id": user["id"],
        "actor_email": user.get("email"), "revoked_sessions": revoked,
    })
    return {"success": True, "revoked": revoked}


@router.get("/captcha/config")
async def captcha_config() -> dict:
    """Public endpoint — frontend uses this to decide whether to render the
    captcha widget and which provider/site-key to load."""
    from utils.captcha import captcha_public_config
    return captcha_public_config()


# ── MFA (TOTP) endpoints ─────────────────────────────────────────

from fastapi.responses import Response as _FastResponse


@router.get("/auth/mfa/status")
async def mfa_status(user: dict = Depends(get_current_user)) -> dict:
    from utils.mfa import user_mfa_state, user_requires_mfa
    state = await user_mfa_state(user["id"])
    state["required"] = user_requires_mfa(user)
    return state


@router.post("/auth/mfa/setup")
async def mfa_setup(user: dict = Depends(get_current_user)) -> dict:
    """Begin enrolment: returns the provisioning URI + secret for QR rendering.
    Does NOT enable MFA until /auth/mfa/enable confirms the first code."""
    from utils.mfa import begin_enrollment
    return await begin_enrollment(user["id"], user["email"])


@router.get("/auth/mfa/qrcode")
async def mfa_qrcode(uri: str, user: dict = Depends(get_current_user)):
    from utils.mfa import qrcode_png_bytes
    if not uri.startswith("otpauth://"):
        raise HTTPException(status_code=400, detail="Invalid provisioning URI")
    return _FastResponse(content=qrcode_png_bytes(uri), media_type="image/png")


@router.post("/auth/mfa/enable")
async def mfa_enable(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Verify first code; on success, flip MFA on and return backup codes (once)."""
    from utils.mfa import confirm_enrollment
    from utils.security_plus import audit_required
    code = (body or {}).get("code", "")
    codes = await confirm_enrollment(user["id"], code)
    await audit_required("security_audit_log", {
        "event": "mfa.enabled", "actor_id": user["id"], "actor_email": user.get("email"),
    })
    return {"success": True, "backup_codes": codes}


# Iter 216h116 — login-flow endpoints used when MFA is MANDATORY and
# the user hasn't enrolled yet. The frontend hits these with the
# ``mfa_enrol`` temp token returned by /auth/login.

@router.post("/auth/mfa/enrol/setup")
async def mfa_enrol_setup(body: dict) -> dict:
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    from utils.mfa import begin_enrollment
    temp = (body or {}).get("temp_token", "")
    try:
        payload = _jwt.decode(temp, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired enrolment token")
    if payload.get("type") != "mfa_enrol":
        raise HTTPException(status_code=401, detail="Invalid enrolment token")
    user_id = payload.get("user_id")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return await begin_enrollment(user_id, user.get("email", ""))


@router.post("/auth/mfa/enrol/complete")
async def mfa_enrol_complete(body: dict, request: Request, response: Response) -> dict:
    """Step 2 of mandatory enrolment — confirm the first TOTP code and
    issue the full JWT in one go (the user is mid-login). Returns the
    backup codes ONCE so the user can print/save them."""
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    from utils.mfa import confirm_enrollment
    from utils.security_plus import audit_required
    temp = (body or {}).get("temp_token", "")
    code = (body or {}).get("code", "")
    try:
        payload = _jwt.decode(temp, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired enrolment token")
    if payload.get("type") != "mfa_enrol":
        raise HTTPException(status_code=401, detail="Invalid enrolment token")
    user_id = payload.get("user_id")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    codes = await confirm_enrollment(user_id, code)
    await audit_required("security_audit_log", {
        "event": "mfa.enrolled_during_login",
        "actor_id": user_id, "actor_email": user.get("email"),
    })
    finalised = await _finalise_successful_login(user, request, response, mfa_verified=True)
    finalised["backup_codes"] = codes
    finalised["enrolment_complete"] = True
    return finalised


@router.post("/auth/mfa/verify")
async def mfa_verify(body: dict, request: Request, response: Response) -> dict:
    """Step 2 of login: accept temp_token + 6-digit code → issue full JWT."""
    import jwt as _jwt
    from utils.database import JWT_SECRET, JWT_ALGORITHM
    from utils.mfa import verify_login_code
    from utils.security_plus import audit_required
    temp = (body or {}).get("temp_token", "")
    code = (body or {}).get("code", "")
    try:
        payload = _jwt.decode(temp, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired temp token")
    if payload.get("type") != "mfa_temp":
        raise HTTPException(status_code=401, detail="Invalid temp token")
    user_id = payload.get("user_id")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # IP-scoped rate limit: 10 attempts / 5 min — harder than the login gate.
    ip = request.client.host if request.client else "unknown"
    from utils.security_plus import rate_limit_async
    await rate_limit_async(f"mfa:{ip}:{user_id}", max_requests=10, window_seconds=300)

    ok = await verify_login_code(user_id, code)
    if not ok:
        await audit_required("security_audit_log", {
            "event": "mfa.verify.fail", "actor_id": user_id, "actor_email": user.get("email"),
            "ip": ip,
        })
        raise HTTPException(status_code=401, detail="Invalid code")

    await audit_required("security_audit_log", {
        "event": "mfa.verify.success", "actor_id": user_id, "actor_email": user.get("email"),
        "ip": ip,
    })
    # Issue the real JWT + build the full login payload (same shape as /auth/login)
    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0})
    from utils.trial_lifecycle import compute_trial_state
    from utils.feature_guard import get_enabled_features
    from utils.auth_guards import access_token_ttl_hours
    trial_state = compute_trial_state(org) if org else {"is_trial": False}
    features = await get_enabled_features(user)
    # Iter 220au · F-03 + F-17 — role-tiered TTL + mfa_verified claim.
    ttl_hours = access_token_ttl_hours(user)
    token = create_token(user["id"], expires_hours=ttl_hours, mfa_verified=True)
    set_auth_cookie(response, token, max_age_hours=ttl_hours)
    purge_legacy_cookie_scopes(response, request)
    await record_user_session(user["id"], token, request)
    return {"token": token, "user": _build_login_user_payload(user, org, trial_state, features)}


@router.post("/auth/mfa/disable")
async def mfa_disable(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Disable MFA. Requires the caller to supply a valid code (prevents
    session-hijack disables). Master admins cannot self-disable."""
    from utils.mfa import verify_login_code, disable_mfa
    from utils.security_plus import audit_required
    if user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admins cannot disable MFA")
    code = (body or {}).get("code", "")
    if not await verify_login_code(user["id"], code):
        raise HTTPException(status_code=401, detail="Invalid code")
    await disable_mfa(user["id"])
    await audit_required("security_audit_log", {
        "event": "mfa.disabled", "actor_id": user["id"], "actor_email": user.get("email"),
    })
    return {"success": True}


@router.get("/organization")
async def get_organization(user: dict = Depends(get_current_user)) -> dict:
    if not user.get('organization_id'):
        raise HTTPException(status_code=404, detail="No organization found")
    org = await db.organizations.find_one({"id": user['organization_id']}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Iter 216c — `organizations.name` is the canonical org identity (Master
    # Admin, billing, audit logs all read it). `branding.company_name` is a
    # separate display label that operators edit in Settings → Branding.
    # Pre-216c versions of `update_branding` only wrote to `branding.company_name`,
    # so test seeds + early users (e.g. Bob @ Strong Fitness) ended up with
    # drift — the dashboard header showed a stale "Test Org Name" while
    # Master Admin showed the real "Strong Fitness". Self-heal on read so
    # the dashboard never lies about the gym's identity. Going forward,
    # `update_branding` writes both fields atomically.
    canonical = (org.get("name") or "").strip()
    branding = org.get("branding") or {}
    if canonical and branding.get("company_name") != canonical:
        branding = {**branding, "company_name": canonical}
        org["branding"] = branding
    return org


@router.patch("/organization/branding")
async def update_branding(data: Dict[str, Any], user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Only owners and managers can update branding")
    if not user.get('organization_id'):
        raise HTTPException(status_code=404, detail="No organization found")
    branding = {
        "primary_color": data.get("primary_color", "#0055FF"),
        "company_name": data.get("company_name", ""),
        "logo_url": data.get("logo_url", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Iter 216c — keep `organizations.name` in sync with the user-facing
    # branding name. Operators edit ONE "Gym name" field in Settings; we
    # write it to both fields so Master Admin / billing / dashboard header
    # never disagree (see iter-216c PRD entry).
    update_doc: Dict[str, Any] = {"branding": branding}
    new_company_name = (data.get("company_name") or "").strip()
    if new_company_name:
        update_doc["name"] = new_company_name
    await db.organizations.update_one(
        {"id": user['organization_id']},
        {"$set": update_doc}
    )
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "org.branding.updated", "actor_id": user["id"], "actor_email": user.get("email"),
        "org_id": user["organization_id"], "changes": list(data.keys()),
    })
    return {"success": True, "branding": branding}


@router.get("/organization/staff")
async def list_staff(user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    staff = await db.users.find(
        {"organization_id": user['organization_id']},
        {"_id": 0, "password": 0}
    ).to_list(100)
    return {"staff": staff, "count": len(staff)}


@router.post("/organization/invite")
async def invite_staff(invite: InviteStaff, user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Only owners and managers can invite staff")
    if invite.role not in ['manager', 'staff']:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'manager' or 'staff'")

    existing = await db.users.find_one({"email": invite.email, "organization_id": user['organization_id']}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists in organization")

    existing_invite = await db.invites.find_one({"email": invite.email, "organization_id": user['organization_id'], "status": "pending"}, {"_id": 0})
    if existing_invite:
        raise HTTPException(status_code=400, detail="Invite already sent")

    org = await db.organizations.find_one({"id": user['organization_id']}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Legacy orgs created before the company_code rollout may not have one.
    # Lazily generate + persist so the invite flow keeps working everywhere.
    company_code = org.get('company_code')
    if not company_code:
        company_code = str(uuid.uuid4())[:8].upper()
        await db.organizations.update_one(
            {"id": user['organization_id']},
            {"$set": {"company_code": company_code}},
        )

    invite_doc = {
        "id": str(uuid.uuid4()),
        "email": invite.email,
        "full_name": invite.full_name,
        "role": invite.role,
        "organization_id": user['organization_id'],
        "organization_name": org.get('name', ''),
        "invited_by": user['id'],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.invites.insert_one(invite_doc)

    # Iter 215d4 — activation funnel event (first staff invited). Best-effort.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            user['organization_id'], "first_staff_invited",
            trigger_user_id=user.get("id"),
            payload={"invite_id": invite_doc["id"], "role": invite.role},
        )
    except Exception:
        pass

    return {
        "invite_id": invite_doc['id'],
        "company_code": company_code,
        "message": f"Share this company code with {invite.email}: {company_code}"
    }


@router.get("/organization/invites")
async def list_invites(user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    invites = await db.invites.find(
        {"organization_id": user['organization_id']},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"invites": invites, "count": len(invites)}


@router.delete("/organization/invite/{invite_id}")
async def cancel_invite(invite_id: str, user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await db.invites.delete_one({"id": invite_id, "organization_id": user['organization_id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"success": True}


@router.patch("/organization/staff/{staff_id}/role")
async def update_staff_role(staff_id: str, role: str, user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') != 'owner':
        raise HTTPException(status_code=403, detail="Only owners can change roles")
    if role not in ['owner', 'manager', 'staff']:
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await db.users.update_one(
        {"id": staff_id, "organization_id": user['organization_id']},
        {"$set": {"role": role}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Staff member not found")
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "staff.role.changed", "actor_id": user["id"], "actor_email": user.get("email"),
        "org_id": user["organization_id"], "target_id": staff_id, "new_role": role,
    })
    return {"success": True}


@router.patch("/organization/staff/{staff_id}/permissions")
async def update_staff_permissions(staff_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Owner/Manager grants per-staff feature access.

    Body shape (all optional):
      {
        "module_overrides": {"memberships": bool, "marketing": bool, "crm": bool},
        "timetable_view_only": bool,
        "allowed_site_ids": ["site-uuid-1", "site-uuid-2"]   // empty/absent = unrestricted
      }

    `module_overrides` only restrict — they cannot grant access the org
    itself doesn't have. Owners and master admins ignore overrides.
    `allowed_site_ids` (Iter 216bk) locks the staff member to a subset
    of the org's sites — they will only see those in the site switcher
    and the legacy fallback (empty list) preserves existing behaviour.
    """
    if user.get('role') not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Only owners and managers can manage staff permissions")

    target = await db.users.find_one(
        {"id": staff_id, "organization_id": user['organization_id']},
        {"_id": 0, "id": 1, "role": 1, "email": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot restrict an owner")

    update: dict = {}

    if "module_overrides" in body and isinstance(body["module_overrides"], dict):
        cleaned: dict = {}
        for key in ("memberships", "marketing", "crm"):
            if key in body["module_overrides"]:
                cleaned[key] = bool(body["module_overrides"][key])
        update["module_overrides"] = cleaned

    if "timetable_view_only" in body:
        update["timetable_view_only"] = bool(body["timetable_view_only"])

    if "allowed_site_ids" in body:
        raw = body["allowed_site_ids"] or []
        if not isinstance(raw, list):
            raise HTTPException(400, "allowed_site_ids must be an array")
        update["allowed_site_ids"] = [str(x) for x in raw if x]

    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")

    await db.users.update_one(
        {"id": staff_id, "organization_id": user['organization_id']},
        {"$set": {**update, "permissions_updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "staff.permissions.changed", "actor_id": user["id"], "actor_email": user.get("email"),
        "org_id": user["organization_id"], "target_id": staff_id, "changes": update,
    })
    return {"success": True, "permissions": update}


@router.delete("/organization/staff/{staff_id}")
async def remove_staff(staff_id: str, user: dict = Depends(get_current_user)) -> dict:
    if user.get('role') != 'owner':
        raise HTTPException(status_code=403, detail="Only owners can remove staff")
    if staff_id == user['id']:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    result = await db.users.delete_one({"id": staff_id, "organization_id": user['organization_id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Staff member not found")
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "staff.removed", "actor_id": user["id"], "actor_email": user.get("email"),
        "org_id": user["organization_id"], "target_id": staff_id,
    })
    return {"success": True}


@router.get("/organization/logo")
async def get_org_logo(user: dict = Depends(get_current_user)) -> dict:
    if not user.get('organization_id'):
        return {"logo_url": None}
    org = await db.organizations.find_one({"id": user['organization_id']}, {"_id": 0, "logo_url": 1, "branding": 1})
    if not org:
        return {"logo_url": None}
    # Try branding logo first, then org logo
    logo_path = (org.get('branding') or {}).get('logo_url') or org.get('logo_url')
    if not logo_path:
        return {"logo_url": None}
    # If it's already a full URL (starts with http), return as-is
    if logo_path.startswith('http'):
        return {"logo_url": logo_path}
    # Iter 216n — if it's already a canonical /api/public/files/{id} URL, return as-is
    # (the POST /organization/logo endpoint now stores this format directly)
    if logo_path.startswith('/api/public/files/'):
        return {"logo_url": logo_path}
    # Iter 216h59 — also accept the iter 216h57 `/api/account/logo/{org_id}`
    # proxy URL (returned by POST /api/account/logo). Either format works
    # interchangeably — the Navbar fetches via this endpoint and renders
    # whichever proxy URL was stored.
    if logo_path.startswith('/api/account/logo/'):
        return {"logo_url": logo_path}
    # data: URIs (object-store outage fallback) pass through unchanged.
    if logo_path.startswith('data:'):
        return {"logo_url": logo_path}
    # Otherwise, find the file by storage_path and return public URL
    file_doc = await db.files.find_one({"storage_path": logo_path}, {"_id": 0, "id": 1})
    if file_doc:
        return {"logo_url": f"/api/public/files/{file_doc['id']}"}
    return {"logo_url": None}


@router.get("/account/billing")
async def get_billing_info(user: dict = Depends(get_current_user)) -> dict:
    org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0}) if user.get('organization_id') else None

    tier = (org or user).get('subscription_tier', 'none')
    package_names = {"none": "Free Tier", "basic": "Basic", "pro": "Pro", "premium": "Premium"}
    package_prices = {"none": 0, "basic": 49, "pro": 99, "premium": 149}

    payments = await db.payment_transactions.find(
        {"user_id": user['id']}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    from utils.trial_lifecycle import compute_trial_state
    trial_state = compute_trial_state(org) if org else {"is_trial": False}

    return {
        "current_plan": tier,
        "plan_name": package_names.get(tier, tier.capitalize()),
        "plan_price": package_prices.get(tier, 0),
        "trial": trial_state,
        "is_trial": bool(trial_state.get("is_trial")),
        "organization": org.get('name') if org else None,
        "organization_code": org.get('company_code') if org else None,
        "member_since": user.get('created_at', ''),
        "email": user.get('email', ''),
        "full_name": user.get('full_name', ''),
        "role": user.get('role', 'staff'),
        "payment_history": payments,
    }
