"""Step-up (re-)authentication for high-impact actions (security §18).

A valid session is NOT enough to perform an especially destructive or
security-sensitive action (deleting companies, rotating integration secrets,
disabling MFA, creating admins, bulk exports). The caller must prove a FRESH
authentication within a short window — a TOTP/backup code if MFA is enrolled,
otherwise their account password.

Flow
----
1. FE calls the sensitive endpoint. If a fresh step-up is missing the backend
   returns HTTP 403 ``{"error":"step_up_required", ...}``.
2. FE prompts the user, then POSTs ``/api/auth/step-up`` with ``{code}`` or
   ``{password}``. On success we record a short-lived step-up for that identity.
3. FE retries the sensitive action; ``require_step_up`` now passes.

Step-up state is keyed by the account EMAIL (lower-cased) in
``security_step_ups`` so it works across the operator token (``users``) and the
CRM token (``crm_users``), which can carry different ids for the same person.

Enforcement is gated by ``STEP_UP_ENFORCED`` (default OFF) so the capability
can be shipped and wired without breaking existing flows until the FE prompt is
in place — the same deliberate-enablement pattern as ``ENFORCE_MASTER_ADMIN_MFA``.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from utils.database import db

STEP_UP_TTL_SECONDS = int(os.environ.get("STEP_UP_TTL_SECONDS", "300"))
STEP_UP_ENFORCED = os.environ.get("STEP_UP_ENFORCED", "false").lower() in ("1", "true", "yes")
_COLLECTION = "security_step_ups"


def _email_key(user: dict) -> Optional[str]:
    e = (user or {}).get("email")
    return e.strip().lower() if e else None


async def record_step_up(user: dict, method: str) -> None:
    """Persist a fresh step-up for the caller's identity (email-keyed)."""
    key = _email_key(user)
    if not key:
        return
    now = datetime.now(timezone.utc)
    await db[_COLLECTION].update_one(
        {"id": key},
        {"$set": {
            "id": key,
            "stepped_up_at": now.isoformat(),
            "method": method,
            "user_id": user.get("id"),
            "ts": now,   # BSON date for the TTL sweep
        }},
        upsert=True,
    )


async def _fresh_step_up_at(user: dict) -> Optional[datetime]:
    key = _email_key(user)
    if not key:
        return None
    doc = await db[_COLLECTION].find_one({"id": key}, {"_id": 0, "stepped_up_at": 1})
    ts = (doc or {}).get("stepped_up_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


async def is_step_up_fresh(user: dict) -> bool:
    at = await _fresh_step_up_at(user)
    if not at:
        return False
    age = (datetime.now(timezone.utc) - at).total_seconds()
    return 0 <= age <= STEP_UP_TTL_SECONDS


async def step_up_status(user: dict) -> dict:
    """State for the FE step-up dialog."""
    from utils.mfa import user_mfa_state
    st = await user_mfa_state(user.get("id")) if user.get("id") else {"enabled": False}
    at = await _fresh_step_up_at(user)
    valid = bool(at) and (datetime.now(timezone.utc) - at).total_seconds() <= STEP_UP_TTL_SECONDS
    return {
        "enforced": STEP_UP_ENFORCED,
        "valid": valid,
        "valid_until": (at.isoformat() if (at and valid) else None),
        "ttl_seconds": STEP_UP_TTL_SECONDS,
        "mfa_enabled": bool(st.get("enabled")),
    }


async def verify_step_up_challenge(user: dict, *, code: Optional[str] = None,
                                   password: Optional[str] = None) -> str:
    """Verify a fresh-auth challenge. Returns the method used ('mfa'|'password')
    or raises 400. TOTP/backup code is required when MFA is enrolled; otherwise
    the account password is accepted."""
    from utils.mfa import user_mfa_state, verify_login_code
    from utils.auth import verify_password

    uid = user.get("id")
    mfa = await user_mfa_state(uid) if uid else {"enabled": False}

    if mfa.get("enabled"):
        if not code:
            raise HTTPException(status_code=400, detail="Authenticator code required")
        ok = await verify_login_code(uid, code.strip())
        if not ok:
            raise HTTPException(status_code=400, detail="Invalid authenticator code")
        return "mfa"

    # No MFA enrolled → fall back to the account password.
    if not password:
        raise HTTPException(status_code=400, detail="Password required to confirm this action")
    fresh = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 1, "password": 1})
    stored = (fresh or {}).get("password_hash") or (fresh or {}).get("password")
    if not stored or not verify_password(password, stored):
        raise HTTPException(status_code=400, detail="Incorrect password")
    return "password"


async def require_step_up(user: dict, *, request=None, action: Optional[str] = None) -> None:
    """Raise 403 ``step_up_required`` unless the caller has a fresh step-up.

    No-op when ``STEP_UP_ENFORCED`` is off (capability shipped, enablement is
    a deliberate ops decision once the FE prompt is live)."""
    if not STEP_UP_ENFORCED:
        return
    if await is_step_up_fresh(user):
        return
    from utils.mfa import user_mfa_state
    mfa = await user_mfa_state(user.get("id")) if user.get("id") else {"enabled": False}
    try:
        from utils.security_events import log_security_event, SEV_WARNING
        await log_security_event(
            "step_up_required", user=user, request=request, severity=SEV_WARNING,
            action=action, result="denied", detail="fresh re-authentication required",
        )
    except Exception:
        pass
    raise HTTPException(
        status_code=403,
        detail={
            "error": "step_up_required",
            "action": action,
            "ttl_seconds": STEP_UP_TTL_SECONDS,
            "mfa_enabled": bool(mfa.get("enabled")),
            "message": "Please re-confirm your identity to perform this action.",
        },
    )


async def ensure_indexes() -> None:
    try:
        # Cleanup sweep — docs older than 1h are useless (TTL is 5 min).
        await db[_COLLECTION].create_index("ts", expireAfterSeconds=3600)
    except Exception:
        pass


__all__ = [
    "STEP_UP_TTL_SECONDS", "STEP_UP_ENFORCED",
    "record_step_up", "is_step_up_fresh", "step_up_status",
    "verify_step_up_challenge", "require_step_up", "ensure_indexes",
]
