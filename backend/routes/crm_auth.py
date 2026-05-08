from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import uuid

from utils.database import db, JWT_SECRET, JWT_ALGORITHM

router = APIRouter(prefix="/crm/auth", tags=["CRM Auth"])
security = HTTPBearer()


def crm_hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def crm_verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


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
    if not user or not crm_verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    org_name = ""
    if user.get("organization_id"):
        org = await db.organizations.find_one({"id": user["organization_id"]}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name", "")

    # Iter 215ax — resolve crm_brand + is_pulse_internal so the frontend
    # can preserve Pulse-customer branding (cyan/black) instead of falling
    # back to GymAxis (navy → purple gradient). Pulse-branded users
    # (account_type pulse_pro/lite OR org name = "Pulse Fitness") see
    # Pulse branding; everyone else sees GymAxis.
    is_admin_user = _is_master_admin_user(user)
    crm_brand, is_pulse_internal = await _resolve_crm_brand_flags(user, is_admin_user)

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
    # briefly see GymAxis chrome.
    is_admin_user = _is_master_admin_user(user)
    crm_brand, is_pulse_internal = await _resolve_crm_brand_flags(user, is_admin_user)
    return {
        **user,
        "organization_name": org_name,
        "crm_brand": crm_brand,
        "is_pulse_internal": is_pulse_internal,
        "is_master_admin": is_admin_user,
    }


@router.post("/me")
async def crm_me_post(user=Depends(get_crm_user)):
    """POST alias for /me — some clients prefer POST for session refresh."""
    return await crm_me(user)


# ── Cross-login — exchange a main GymAxis JWT for a CRM-domain token ─────
#
# The CRM console lives under /crm with its own JWT (payload flag `crm: True`)
# backed by a separate `crm_users` collection. When an operator clicks the CRM
# pill in the shared ModuleSwitcher while already authenticated on the main
# platform, the frontend calls this endpoint to mint a CRM token without
# prompting for a second password. Without it the user sees the CRM login
# screen even though they're already signed in (iter 215d3 fix).

@router.post("/cross-login")
async def crm_cross_login(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Exchange a valid main-platform JWT for a CRM-scoped token.

    - 401 if the token is missing / invalid / revoked.
    - 400 if the caller already holds a CRM-domain token.
    - 403 if the user's org has the CRM module disabled (master admins bypass).
    """
    import jwt as _jwt
    import os as _os
    from utils.security_plus import is_jwt_revoked

    token = credentials.credentials if credentials else ""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Decode the main token. `crm: True` in the payload means the caller
    # already has a CRM token and is trying to re-exchange it — reject.
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("crm") is True:
        raise HTTPException(status_code=400, detail="Already a CRM token")

    # Reject member-portal tokens (they have `kind: member` and no user_id).
    if payload.get("kind") == "member":
        raise HTTPException(status_code=403, detail="Member accounts cannot access CRM")

    if await is_jwt_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Session revoked")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    main_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not main_user:
        raise HTTPException(status_code=401, detail="User not found")

    # Is this user a platform master admin?
    master_email = _os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
    is_master = bool(main_user.get("is_master_admin")) or main_user.get("email") == master_email

    # CRM module access check — master admins bypass.
    if not is_master:
        account_type = main_user.get("account_type") or ""
        # MOD accounts never get CRM.
        if account_type in ("mod_site", "mod_branch", "mod_org"):
            raise HTTPException(status_code=403, detail="CRM not available for this account")

        org_id = main_user.get("organization_id")
        org_doc = {}
        if org_id:
            org_doc = await db.organizations.find_one(
                {"id": org_id},
                {"_id": 0, "enabled_modules": 1, "portal_type": 1, "account_type": 1},
            ) or {}
        enabled = org_doc.get("enabled_modules") or []
        # Legacy orgs with `account_type: full` get CRM by default.
        legacy_full = (org_doc.get("account_type") == "full" or main_user.get("account_type") == "full")
        if "crm" not in enabled and not legacy_full:
            raise HTTPException(status_code=403, detail="CRM module not enabled for your organisation")

    # Find or create a matching CRM user (deduped by email). Reuse the main
    # org id so brand/tenant resolution stays consistent across modules.
    email = (main_user.get("email") or "").lower().strip()
    full_name = main_user.get("full_name") or main_user.get("name") or email
    main_org_id = main_user.get("organization_id")

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
        if updates:
            await db.crm_users.update_one({"email": email}, {"$set": updates})
            crm_user.update(updates)

    crm_brand, is_pulse_internal = await _resolve_crm_brand_flags(main_user, is_master)

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
        },
    }


def _is_master_admin_user(user: dict) -> bool:
    import os
    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
    return user.get("email") == master_email or bool(user.get("is_master_admin"))


async def _resolve_crm_brand_flags(main_user: dict, is_admin: bool) -> tuple[str, bool]:
    """Decide which brand the CRM should wear (`gymaxis` vs `pulse`) and
    whether the user is a Pulse Fitness *internal* operator (gets to see
    Tender Engine + Contracts) vs a Pulse customer.
    """
    main_org = {}
    if main_user.get("organization_id"):
        main_org = await db.organizations.find_one(
            {"id": main_user["organization_id"]},
            {"_id": 0, "name": 1, "account_type": 1, "portal_type": 1, "is_pulse_internal": 1},
        ) or {}
    pulse_branded_account_types = {"pulse_pro", "lite"}
    is_pulse_branded = (
        main_org.get("account_type") in pulse_branded_account_types
        or (main_org.get("name") or "").strip().lower() == "pulse fitness"
    )
    is_pulse_internal = bool(
        main_org.get("is_pulse_internal")
        or (main_org.get("name") or "").strip().lower() == "pulse fitness"
    ) or is_admin
    crm_brand = "pulse" if is_pulse_branded else "gymaxis"
    return crm_brand, is_pulse_internal


async def _seed_crm_user(email: str, password: str, full_name: str, role: str = "admin", organization_id: str = None) -> None:
    """Seed a CRM user — creates if missing, ALWAYS resets password to ensure login works."""
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
    """Seed CRM users, orgs, and pipeline on every startup. Always resets passwords."""
    import os

    # 1. Create GymAxis Admin CRM org
    admin_crm_org = await db.organizations.find_one({"name": "GymAxis AI", "portal_type": "crm"}, {"_id": 0, "id": 1})
    if not admin_crm_org:
        admin_crm_org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": admin_crm_org_id, "name": "GymAxis AI",
            "portal_type": "crm", "subscription_tier": "enterprise",
            "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        admin_crm_org_id = admin_crm_org["id"]

    # 2. Seed admin CRM users (passwords always reset on deploy)
    await _seed_crm_user(
        os.environ.get("CRM_ADMIN_EMAIL", "crm@gymaxisai.com"),
        os.environ.get("CRM_ADMIN_PASSWORD", "CRMAdmin123!"),
        "CRM Admin", organization_id=admin_crm_org_id,
    )
    await _seed_crm_user(
        os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com"),
        os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!"),
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

    existing_pipeline = await db.crm_pipelines.find_one({"is_default": True})
    if not existing_pipeline:
        await db.crm_pipelines.insert_one({
            "id": str(uuid.uuid4()), "name": "Sales Pipeline", "is_default": True,
            "stages": _DEFAULT_PIPELINE_STAGES, "created_at": datetime.now(timezone.utc).isoformat(),
        })



# ═══════════════════════════════════════════
# TWO-FACTOR AUTHENTICATION (TOTP)
# ═══════════════════════════════════════════

import pyotp
import qrcode
import io
import base64
import secrets


@router.post("/2fa/setup")
async def setup_2fa(user=Depends(get_crm_user)):
    """Generate a TOTP secret and QR code for 2FA setup."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.get("email", ""),
        issuer_name="GymAxis CRM"
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
