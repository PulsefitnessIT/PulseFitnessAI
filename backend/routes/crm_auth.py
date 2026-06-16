from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import uuid
import secrets
import logging

from utils.database import db, JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm/auth", tags=["CRM Auth"])
security = HTTPBearer()
# Iter 279b — the cross-login must also accept the httpOnly session cookie
# when the localStorage bearer is stale/absent, so this optional variant
# never 403s on a missing Authorization header.
optional_security = HTTPBearer(auto_error=False)


def crm_hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def crm_verify_password(password: str, hashed: str) -> bool:
    # Iter 216h197 — be defensive: bcrypt raises ``ValueError("Invalid
    # salt")`` for non-bcrypt strings. We want a clean False return so
    # the cross-login-provisioned fallback path in /login can take over.
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def crm_create_token(user_id: str) -> str:
    payload = {
        'user_id': user_id,
        'crm': True,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def crm_verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get('crm'):
            return None
        return payload
    except Exception:
        return None


async def get_crm_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = crm_verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid CRM token")
    user = await db.crm_users.find_one({"id": payload['user_id']}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="CRM user not found")
    return user


CRM_PLANS = {
    "starter": {
        "name": "Starter", "base_price": 9.99, "per_user_price": 4.99,
        "features": [
            "Contact & Company Management",
            "Basic Deal Pipeline",
            "Email Integration",
            "Activity Tracking",
            "Mobile Access",
        ],
    },
    "professional": {
        "name": "Professional", "base_price": 19.99, "per_user_price": 9.99,
        "features": [
            "Everything in Starter",
            "AI-Powered Insights",
            "Custom Pipelines",
            "Workflow Automation",
            "Quote & Proposal Builder",
            "Advanced Reporting",
            "Team Collaboration",
        ],
    },
    "enterprise": {
        "name": "Enterprise", "base_price": 29.99, "per_user_price": 14.99,
        "features": [
            "Everything in Professional",
            "Custom Integrations (API)",
            "White-Label Branding",
            "Advanced Security & SSO",
            "Unlimited Workflows",
            "Priority Support",
            "Data Import/Export Tools",
        ],
    },
}


@router.get("/plans")
async def get_crm_plans():
    """Return CRM plan definitions for the pricing page."""
    return {"plans": CRM_PLANS}


@router.post("/register")
async def crm_register(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")
    full_name = data.get("full_name", "")
    company_name = data.get("company_name", "").strip()
    plan = data.get("plan", "starter")
    team_size = int(data.get("team_size", 1))
    role = "admin"

    if not email or not password or not full_name:
        raise HTTPException(status_code=400, detail="Email, password and full name required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if plan not in CRM_PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    existing = await db.crm_users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create CRM organisation
    org_id = str(uuid.uuid4())
    org_doc = {
        "id": org_id, "name": company_name or f"{full_name}'s CRM",
        "portal_type": "crm", "subscription_tier": plan,
        "crm_plan": plan, "crm_team_size": team_size,
        "status": "trial", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.organizations.insert_one(org_doc)

    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id, "email": email, "full_name": full_name,
        "password": crm_hash_password(password), "role": role,
        "organization_id": org_id, "avatar_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_users.insert_one(user_doc)

    plan_info = CRM_PLANS[plan]
    monthly_cost = plan_info["base_price"] + (plan_info["per_user_price"] * team_size)

    token = crm_create_token(user_id)
    return {
        "token": token,
        "user": {
            "id": user_id, "email": email, "full_name": full_name,
            "role": role, "avatar_url": None, "organization_id": org_id,
        },
        "plan": plan, "monthly_cost": round(monthly_cost, 2),
    }


@router.post("/login")
async def crm_login(data: dict):
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = await db.crm_users.find_one({"email": email}, {"_id": 0})
    # Iter 216h197 — Craig's "Invalid credentials" bug. CRM users that
    # were auto-created by the cross-login flow have a random uuid hex
    # stored as their crm password (they don't know it). When such a
    # user lands on /crm without a main session and types their actual
    # Pulse Fitness password, the standalone /crm/auth/login rejected them.
    #
    # Fall back: if the user record is flagged ``cross_login_provisioned``
    # (or simply no crm_users row exists), validate the password against
    # the main `users` collection's hash. On success, we mint the CRM
    # token exactly as before and auto-provision a crm_users row.
    cross_provisioned = bool(user and user.get("cross_login_provisioned"))
    crm_password_match = user and crm_verify_password(password, user.get("password", ""))
    if not user or (not crm_password_match and cross_provisioned):
        platform_user = await db.users.find_one({"email": email}, {"_id": 0})
        if not platform_user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        # Validate against the main platform's bcrypt hash.
        from utils.auth import verify_password as platform_verify_password
        platform_hash = platform_user.get("password_hash") or platform_user.get("password") or ""
        if not platform_verify_password(password, platform_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        # Reuse / create a crm_users row for this account so subsequent
        # CRM flows have something to attach to.
        if not user:
            user = {
                "id": platform_user.get("id"),
                "email": email,
                "full_name": platform_user.get("full_name") or platform_user.get("name") or email.split("@")[0],
                "role": "admin" if platform_user.get("is_master_admin") else "manager",
                "organization_id": platform_user.get("organization_id"),
                "avatar_url": platform_user.get("avatar_url", ""),
                "password": crm_hash_password(secrets.token_hex(32)),
                "cross_login_provisioned": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.crm_users.insert_one(dict(user))
        # Flag that this CRM record now also matches the platform pwd so
        # future logins don't have to re-verify cross-platform.
        await db.crm_users.update_one(
            {"id": user["id"]},
            {"$set": {"cross_login_provisioned": True, "last_platform_login": datetime.now(timezone.utc).isoformat()}},
        )
    elif not crm_password_match:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    org_name = ""
    if user.get("organization_id"):
        org = await db.organizations.find_one({"id": user["organization_id"]}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name", "")

    # Iter 215ax — resolve crm_brand + is_pulse_internal so the frontend
    # can preserve Pulse-customer branding (cyan/black) instead of falling
    # back to Pulse Fitness (navy → purple gradient). Pulse-branded users
    # (account_type pulse_pro/lite OR org name = "Pulse Fitness") see
    # Pulse branding; everyone else sees Pulse Fitness.
    is_admin_user = _is_master_admin_user(user)
    crm_brand, is_pulse_internal, features, modules = await _resolve_crm_brand_flags(user, is_admin_user)

    # Check if 2FA is enabled
    if user.get("totp_enabled"):
        # Issue a short-lived temp token for 2FA verification
        temp_payload = {
            'user_id': user["id"],
            'crm': True,
            'pending_2fa': True,
            'exp': datetime.now(timezone.utc) + timedelta(minutes=5)
        }
        temp_token = jwt.encode(temp_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "user": {"email": user["email"], "full_name": user["full_name"]},
        }

    token = crm_create_token(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"], "email": user["email"],
            "full_name": user["full_name"], "role": user["role"],
            "avatar_url": user.get("avatar_url"),
            "organization_id": user.get("organization_id"),
            "organization_name": org_name,
            "totp_enabled": False,
            "crm_brand": crm_brand,
            "is_pulse_internal": is_pulse_internal,
            "is_master_admin": is_admin_user,
            "features": features,
            "modules": modules,
        }
    }


@router.get("/me")
async def crm_me(user=Depends(get_crm_user)):
    org_name = ""
    if user.get("organization_id"):
        org = await db.organizations.find_one({"id": user["organization_id"]}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name", "")
    # Iter 215ax — same brand resolution as the /login endpoint so a
    # remount (page refresh, new tab) re-hydrates the user with the
    # correct crm_brand. Without this, the CRMApp component would lose
    # its branding signal on /me-driven boots and Pulse customers would
    # briefly see Pulse Fitness chrome.
    is_admin_user = _is_master_admin_user(user)
    crm_brand, is_pulse_internal, features, modules = await _resolve_crm_brand_flags(user, is_admin_user)
    return {
        **user,
        "organization_name": org_name,
        "crm_brand": crm_brand,
        "is_pulse_internal": is_pulse_internal,
        "is_master_admin": is_admin_user,
        "is_org_owner": bool(user.get("is_org_owner") or is_admin_user),
        "features": features,
        "modules": modules,
    }


@router.post("/me")
async def crm_me_post(user=Depends(get_crm_user)):
    """POST alias for /me — some clients prefer POST for session refresh."""
    return await crm_me(user)


# ── Cross-login — exchange a main Pulse Fitness JWT for a CRM-domain token ─────
#
# The CRM console lives under /crm with its own JWT (payload flag `crm: True`)
# backed by a separate `crm_users` collection. When an operator clicks the CRM
# pill in the shared ModuleSwitcher while already authenticated on the main
# platform, the frontend calls this endpoint to mint a CRM token without
# prompting for a second password. Without it the user sees the CRM login
# screen even though they're already signed in (iter 215d3 fix).

@router.post("/cross-login")
async def crm_cross_login(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
):
    """Exchange a valid main-platform session for a CRM-scoped token.

    - 401 if there is no valid session at all (header AND cookie).
    - 400 if the only credential presented is already a CRM token.
    - 403 if the resolved user's org has the CRM module disabled
      (platform / Pulse master admins bypass).

    Iter 279b — authenticate against the CURRENT session, not just the
    localStorage bearer. Long-lived accounts (Lee/Craig) carry a STALE
    ``localStorage['token']`` left over from an earlier registration whose
    ``user_id`` points at an old/deleted record, while their httpOnly
    ``ga_session`` cookie reflects the real, current pulse_master_admin
    login. The cross-login historically trusted ONLY the bearer header, so
    it kept resolving the WRONG user → 401/403 → the recurring "CRM is not
    enabled" lock-out, no matter how the entitlement resolver was fixed.
    We now collect EVERY candidate token (bearer + all ``ga_session``
    cookie values — the iter-231 multi-cookie shadowing fix) and pick the
    identity that actually yields CRM access.
    """
    import jwt as _jwt
    import os as _os
    import re as _re
    from utils.security_plus import is_jwt_revoked
    from utils.auth import _cookie_token_candidates

    master_email = (_os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai") or "").lower()

    def _is_priv(u: dict) -> bool:
        if not u:
            return False
        return bool(
            u.get("is_master_admin")
            or u.get("is_pulse_admin")
            or (u.get("role") or "").lower() == "pulse_master_admin"
            or (u.get("email") or "").lower() == master_email
        )

    # ── Collect candidate tokens: bearer header first, then every
    #    ga_session cookie value present on the request. ───────────────
    candidate_tokens: list[str] = []
    if credentials and credentials.credentials:
        bv = credentials.credentials.strip()
        if bv and bv.lower() not in ("null", "undefined", "cookie"):
            candidate_tokens.append(bv)
    for cv in _cookie_token_candidates(request):
        if cv and cv not in candidate_tokens:
            candidate_tokens.append(cv)

    if not candidate_tokens:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # ── Decode each candidate → resolve to a live user. Skip CRM/member
    #    tokens and revoked sessions. ─────────────────────────────────
    resolved_users: list[dict] = []
    saw_crm_token = False
    saw_member_token = False
    for tok in candidate_tokens:
        try:
            p = _jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            continue
        if p.get("crm") is True:
            saw_crm_token = True
            continue
        if p.get("kind") == "member":
            saw_member_token = True
            continue
        if await is_jwt_revoked(p.get("jti")):
            continue
        uid = p.get("user_id")
        if not uid:
            continue
        u = await db.users.find_one({"id": uid}, {"_id": 0})
        if u and not any(x.get("id") == u.get("id") for x in resolved_users):
            resolved_users.append(u)

    if not resolved_users:
        if saw_crm_token:
            raise HTTPException(status_code=400, detail="Already a CRM token")
        if saw_member_token:
            raise HTTPException(status_code=403, detail="Member accounts cannot access CRM")
        raise HTTPException(status_code=401, detail="Not authenticated")

    # ── Pick the CRM-capable identity. Prefer a privileged admin, then
    #    any record with CRM entitlement; fall back to the first resolved
    #    user so a genuine "no access" case still produces a clean 403. ─
    from utils.module_access import has_module

    async def _crm_ok(u: dict) -> bool:
        if _is_priv(u):
            return True
        if (u.get("account_type") or "") in ("mod_site", "mod_branch", "mod_org"):
            return False
        org_id = u.get("organization_id")
        org_doc = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None
        return bool(has_module(u, org_doc, "crm"))

    main_user = None
    is_master = False
    # 1) a privileged admin among the sessions wins outright.
    for u in resolved_users:
        if _is_priv(u):
            main_user, is_master = u, True
            break
    # 2) else the first CRM-entitled identity.
    if main_user is None:
        for u in resolved_users:
            if await _crm_ok(u):
                main_user = u
                break
    # 3) else fall back to the first resolved user (will hit the 403 gate).
    if main_user is None:
        main_user = resolved_users[0]

    # ── Final entitlement gate for non-admins. ───────────────────────
    if not is_master:
        account_type = main_user.get("account_type") or ""
        if account_type in ("mod_site", "mod_branch", "mod_org"):
            raise HTTPException(status_code=403, detail="CRM not available for this account")

        org_id = main_user.get("organization_id")
        org_doc = await db.organizations.find_one(
            {"id": org_id}, {"_id": 0},
        ) if org_id else None

        allowed = has_module(main_user, org_doc, "crm")

        # Duplicate/mismatched-record safety net: a single person can hold
        # several `users` rows under one email (legacy re-registration,
        # cross-portal provisioning). If the chosen row can't reach CRM but
        # another row for the same email is a privileged admin or sits in a
        # CRM-enabled org, adopt that identity.
        if not allowed:
            email_lc = (main_user.get("email") or "").lower().strip()
            if email_lc:
                siblings = await db.users.find(
                    {"email": {"$regex": f"^{_re.escape(email_lc)}$", "$options": "i"}},
                    {"_id": 0},
                ).to_list(length=25)
                for sib in siblings:
                    if sib.get("id") == main_user.get("id"):
                        continue
                    if _is_priv(sib):
                        allowed, is_master, main_user = True, True, sib
                        break
                    sib_org = await db.organizations.find_one(
                        {"id": sib.get("organization_id")}, {"_id": 0},
                    ) if sib.get("organization_id") else None
                    if has_module(sib, sib_org, "crm"):
                        allowed, main_user = True, sib
                        break

        if not allowed:
            raise HTTPException(status_code=403, detail="CRM module not enabled for your organisation")

    # Find or create a matching CRM user (deduped by email). Reuse the main
    # org id so brand/tenant resolution stays consistent across modules.
    email = (main_user.get("email") or "").lower().strip()
    full_name = main_user.get("full_name") or main_user.get("name") or email
    main_org_id = main_user.get("organization_id")

    # Preserve the platform OWNER signal across the CRM identity bridge.
    # The bridge stores delegated cross-login users as role "manager", which
    # would otherwise hide owner-only actions (e.g. Clear price list) from the
    # actual org owner. Carry an explicit `is_org_owner` flag instead.
    is_org_owner = (main_user.get("role") or "").lower() == "owner"
    if not is_org_owner and main_org_id:
        _owner_org = await db.organizations.find_one(
            {"id": main_org_id}, {"_id": 0, "owner_id": 1})
        if _owner_org and _owner_org.get("owner_id") == main_user.get("id"):
            is_org_owner = True

    crm_user = await db.crm_users.find_one({"email": email}, {"_id": 0})
    if not crm_user:
        crm_user_id = str(uuid.uuid4())
        crm_user = {
            "id": crm_user_id,
            "email": email,
            "full_name": full_name,
            # No usable password for cross-login-only accounts — store a
            # non-verifiable bcrypt hash so /login keeps working for users
            # who also know their main password.
            "password": crm_hash_password(uuid.uuid4().hex),
            "role": "admin" if is_master else "manager",
            "organization_id": main_org_id,
            "avatar_url": main_user.get("avatar_url"),
            "is_org_owner": is_org_owner,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cross_login_provisioned": True,
        }
        await db.crm_users.insert_one(dict(crm_user))
        crm_user.pop("_id", None)
    else:
        # Keep the CRM user's org / name in sync with the main record so
        # subsequent /me calls reflect the current tenant.
        updates = {}
        if main_org_id and crm_user.get("organization_id") != main_org_id:
            updates["organization_id"] = main_org_id
        if full_name and crm_user.get("full_name") != full_name:
            updates["full_name"] = full_name
        # Promote to admin if the user is now a master admin.
        if is_master and crm_user.get("role") != "admin":
            updates["role"] = "admin"
        # Keep the org-owner signal current (backfills pre-existing docs).
        if bool(crm_user.get("is_org_owner")) != is_org_owner:
            updates["is_org_owner"] = is_org_owner
        if updates:
            await db.crm_users.update_one({"email": email}, {"$set": updates})
            crm_user.update(updates)

    crm_brand, is_pulse_internal, features, modules = await _resolve_crm_brand_flags(main_user, is_master)

    # Resolve org name for the response.
    org_name = ""
    if crm_user.get("organization_id"):
        org = await db.organizations.find_one({"id": crm_user["organization_id"]}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name", "")

    crm_token = crm_create_token(crm_user["id"])
    return {
        "token": crm_token,
        "user": {
            "id": crm_user["id"],
            "email": crm_user["email"],
            "full_name": crm_user.get("full_name", ""),
            "role": crm_user.get("role", "manager"),
            "avatar_url": crm_user.get("avatar_url"),
            "organization_id": crm_user.get("organization_id"),
            "organization_name": org_name,
            "totp_enabled": bool(crm_user.get("totp_enabled")),
            "crm_brand": crm_brand,
            "is_pulse_internal": is_pulse_internal,
            "is_master_admin": is_master,
            "is_org_owner": bool(is_org_owner or is_master),
            "features": features,
            "modules": modules,
        },
    }


def _is_master_admin_user(user: dict) -> bool:
    import os
    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai")
    return user.get("email") == master_email or bool(user.get("is_master_admin"))


async def _resolve_crm_brand_flags(main_user: dict, is_admin: bool):
    """Resolve crm_brand + is_pulse_internal + module/feature signals
    from the user's home org. Returns:
       (crm_brand, is_pulse_internal, features, modules)

    Iter 216h275 — added `features` + `modules` so the CRM nav can
    gate tabs (e.g. Tenders) by the master-admin module toggle
    rather than by `is_pulse_internal`. Previously the Tenders tab
    only rendered when the org name was literally "Pulse Fitness"
    (the "Pulse Fitness Limited" tenant was excluded). Now any
    org with `features.crm_tenders=true` (or the `crm_tenders`
    module enabled) sees the tab — exactly what the master admin
    toggle promises.
    """
    main_org = {}
    if main_user.get("organization_id"):
        main_org = await db.organizations.find_one(
            {"id": main_user["organization_id"]},
            {"_id": 0, "name": 1, "account_type": 1, "portal_type": 1, "is_pulse_internal": 1,
             "features": 1, "modules": 1, "enabled_modules": 1},
        ) or {}
    pulse_branded_account_types = {"pulse_pro", "lite"}
    name_lower = (main_org.get("name") or "").strip().lower()
    is_pulse_branded = (
        main_org.get("account_type") in pulse_branded_account_types
        or name_lower.startswith("pulse fitness")  # h275 — was strict ==, missed "Pulse Fitness Limited"
    )
    is_pulse_internal = bool(
        main_org.get("is_pulse_internal")
        or name_lower.startswith("pulse fitness")  # h275 — same fix
    ) or is_admin
    crm_brand = "pulse" if is_pulse_branded else "gymaxis"
    features = main_org.get("features") or {}
    modules = main_org.get("modules") or {}
    return crm_brand, is_pulse_internal, features, modules


async def _seed_crm_user(email: str, password: str, full_name: str, role: str = "admin", organization_id: str = None) -> None:
    """Seed a CRM user — creates if missing, ALWAYS resets password to ensure login works.

    Fail-closed: if ``password`` is empty (env var unset) we SKIP seeding
    rather than fall back to a well-known default. This prevents shipping a
    guessable admin password to any deployment that forgot to configure it.
    """
    if not (password or "").strip():
        logger.warning(
            "[crm_seed] skipping seed for %s — password env var not set (fail-closed)", email,
        )
        return
    hashed = crm_hash_password(password)
    existing = await db.crm_users.find_one({"email": email})
    if not existing:
        doc = {
            "id": str(uuid.uuid4()), "email": email, "full_name": full_name,
            "password": hashed, "role": role,
            "avatar_url": None, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if organization_id:
            doc["organization_id"] = organization_id
        await db.crm_users.insert_one(doc)
    else:
        update = {"password": hashed}
        if organization_id:
            update["organization_id"] = organization_id
        await db.crm_users.update_one({"email": email}, {"$set": update})


_DEFAULT_PIPELINE_STAGES = [
    {"id": "lead", "name": "New Lead", "order": 0, "color": "#007AFF"},
    {"id": "qualified", "name": "Qualified", "order": 1, "color": "#AF52DE"},
    {"id": "proposal", "name": "Proposal Sent", "order": 2, "color": "#FFCC00"},
    {"id": "negotiation", "name": "Negotiation", "order": 3, "color": "#FF9500"},
    {"id": "won", "name": "Won", "order": 4, "color": "#34C759"},
    {"id": "lost", "name": "Lost", "order": 5, "color": "#FF3B30"},
]


async def seed_crm_admin():
    """Seed CRM users, orgs, and pipeline on every startup. Always resets passwords.

    Iter 216h273 — gated by `CRM_SEED_DEMO_ORGS` env flag (defaults
    to ON to preserve existing dev-env behaviour). Set to "0" on
    previews where the customer has scoped down to a specific keep
    list — otherwise this seeder re-creates "Pulse Fitness AI" + "Pulse
    Fitness" CRM orgs on every boot, blowing the scoped wipe.
    """
    import os

    # Master admin CRM access is the ONLY thing that must always
    # be seeded — we attach it to the existing master admin home
    # org instead of creating a new one when demo seeding is off.
    seed_demo = os.environ.get("CRM_SEED_DEMO_ORGS", "1").lower() not in ("0", "false", "no")

    if not seed_demo:
        # Minimal seed: ensure the master admin has a CRM user record
        # bound to their existing master home org.
        master_user = await db.users.find_one(
            {"email": os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai")},
            {"_id": 0, "organization_id": 1},
        )
        master_org_id = (master_user or {}).get("organization_id")
        if master_org_id:
            await _seed_crm_user(
                os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai"),
                os.environ.get("MASTER_ADMIN_PASSWORD", ""),
                "Master Admin", organization_id=master_org_id,
            )
        return

    # 1. Create Pulse Fitness Admin CRM org
    admin_crm_org = await db.organizations.find_one({"name": "Pulse Fitness AI", "portal_type": "crm"}, {"_id": 0, "id": 1})
    if not admin_crm_org:
        admin_crm_org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": admin_crm_org_id, "name": "Pulse Fitness AI",
            "portal_type": "crm", "subscription_tier": "enterprise",
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        admin_crm_org_id = admin_crm_org["id"]

    # 2. Seed admin CRM users (passwords always reset on deploy)
    await _seed_crm_user(
        os.environ.get("CRM_ADMIN_EMAIL", "crm@pulsefitness.ai"),
        os.environ.get("CRM_ADMIN_PASSWORD", ""),
        "CRM Admin", organization_id=admin_crm_org_id,
    )
    await _seed_crm_user(
        os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai"),
        os.environ.get("MASTER_ADMIN_PASSWORD", ""),
        "Master Admin", organization_id=admin_crm_org_id,
    )

    # 3. Create Pulse Fitness CRM org + Craig
    pulse_crm_org = await db.organizations.find_one({"name": "Pulse Fitness", "portal_type": "crm"}, {"_id": 0, "id": 1})
    if not pulse_crm_org:
        pulse_crm_org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": pulse_crm_org_id, "name": "Pulse Fitness",
            "portal_type": "crm", "subscription_tier": "professional",
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        pulse_crm_org_id = pulse_crm_org["id"]

    await _seed_crm_user(
        "craig.henshall@pulsefitness.com", "Test123!",
        "Craig Henshall", role="manager", organization_id=pulse_crm_org_id,
    )

    # SEC-008: pipelines are org-scoped — migrate any legacy global pipeline
    # and ensure every CRM org has its own default pipeline.
    from utils.crm_pipeline import backfill_org_pipelines
    await backfill_org_pipelines()



# ═══════════════════════════════════════════
# TWO-FACTOR AUTHENTICATION (TOTP)
# ═══════════════════════════════════════════

import pyotp
import qrcode
import io
import base64


@router.post("/2fa/setup")
async def setup_2fa(user=Depends(get_crm_user)):
    """Generate a TOTP secret and QR code for 2FA setup."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.get("email", ""),
        issuer_name="Pulse Fitness CRM"
    )

    # Generate QR code as base64
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Generate backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]

    # Store pending setup (not yet verified)
    await db.crm_users.update_one(
        {"id": user["id"]},
        {"$set": {
            "totp_secret_pending": secret,
            "backup_codes_pending": backup_codes,
        }}
    )

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "provisioning_uri": provisioning_uri,
        "backup_codes": backup_codes,
    }


@router.post("/2fa/verify-setup")
async def verify_2fa_setup(data: dict, user=Depends(get_crm_user)):
    """Verify TOTP code to confirm 2FA setup."""
    code = data.get("code", "").strip()
    if not code:
        raise HTTPException(400, "Verification code required")

    db_user = await db.crm_users.find_one({"id": user["id"]}, {"_id": 0})
    secret = db_user.get("totp_secret_pending")
    if not secret:
        raise HTTPException(400, "No pending 2FA setup found")

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(400, "Invalid verification code")

    # Activate 2FA
    await db.crm_users.update_one(
        {"id": user["id"]},
        {"$set": {
            "totp_enabled": True,
            "totp_secret": secret,
            "backup_codes": db_user.get("backup_codes_pending", []),
        },
         "$unset": {"totp_secret_pending": "", "backup_codes_pending": ""}}
    )

    return {"success": True, "message": "2FA enabled successfully"}


@router.post("/2fa/disable")
async def disable_2fa(data: dict, user=Depends(get_crm_user)):
    """Disable 2FA (requires current password)."""
    password = data.get("password", "")
    db_user = await db.crm_users.find_one({"id": user["id"]}, {"_id": 0})
    if not db_user or not crm_verify_password(password, db_user.get("password", "")):
        raise HTTPException(401, "Invalid password")

    await db.crm_users.update_one(
        {"id": user["id"]},
        {"$set": {"totp_enabled": False},
         "$unset": {"totp_secret": "", "backup_codes": "", "totp_secret_pending": "", "backup_codes_pending": ""}}
    )
    return {"success": True, "message": "2FA disabled"}


@router.get("/2fa/status")
async def get_2fa_status(user=Depends(get_crm_user)):
    """Check if 2FA is enabled for current user."""
    db_user = await db.crm_users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "enabled": db_user.get("totp_enabled", False),
        "has_backup_codes": len(db_user.get("backup_codes", [])) > 0,
    }


async def _build_auth_response(user_doc: dict) -> dict:
    """Build the standard user auth response with org name lookup."""
    org_name = ""
    if user_doc.get("organization_id"):
        org = await db.organizations.find_one({"id": user_doc["organization_id"]}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name", "")
    return {
        "id": user_doc["id"], "email": user_doc["email"],
        "full_name": user_doc["full_name"], "role": user_doc["role"],
        "avatar_url": user_doc.get("avatar_url"),
        "organization_id": user_doc.get("organization_id"),
        "organization_name": org_name,
        "totp_enabled": bool(user_doc.get("totp_secret")),
    }


@router.post("/2fa/validate")
async def validate_2fa(data: dict):
    """Validate 2FA code during login (called after password check)."""
    temp_token = data.get("temp_token", "")
    code = data.get("code", "").strip()
    if not temp_token or not code:
        raise HTTPException(400, "Token and code required")

    payload = crm_verify_token(temp_token)
    if not payload or not payload.get("pending_2fa"):
        raise HTTPException(401, "Invalid or expired token")

    user = await db.crm_users.find_one({"id": payload["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")

    # Try TOTP code
    totp = pyotp.TOTP(user.get("totp_secret", ""))
    if totp.verify(code, valid_window=1):
        return {"token": crm_create_token(user["id"]), "user": await _build_auth_response(user)}

    # Try backup code
    backup_codes = user.get("backup_codes", [])
    code_upper = code.upper()
    if code_upper in backup_codes:
        new_codes = [c for c in backup_codes if c != code_upper]
        await db.crm_users.update_one({"id": user["id"]}, {"$set": {"backup_codes": new_codes}})
        return {
            "token": crm_create_token(user["id"]),
            "user": await _build_auth_response(user),
            "backup_code_used": True,
            "backup_codes_remaining": len(new_codes),
        }

    raise HTTPException(401, "Invalid 2FA code")
