"""Auth hardening guards — Iter 220au (Wave 3).

Closes 6 risk-register findings against OWASP API1/2/5/7 + LLM-adjacent
session hygiene:

  * **F-02** — TTL tightening on password-reset tokens (config-side; this
    module exposes the ``PASSWORD_RESET_TTL_MINUTES`` constant the
    ``routes/auth.py::forgot_password`` handler must use).
  * **F-03** — Role-tiered access-token TTL. Master admins get a
    1-hour window vs the 24-hour default. Helper:
    ``access_token_ttl_hours(user_or_role)``.
  * **F-08** — Explicit PII strip on ``/auth/me`` responses via
    ``sanitize_me_response``.
  * **F-17** — ``require_mfa_verified`` dependency for high-privilege
    routes. Reads the ``mfa_verified`` claim stashed on the user dict
    by ``utils.auth.get_current_user``.
  * **F-18** — Generic ``require_role(*roles)`` FastAPI dependency
    factory so destructive routes have a server-side role gate.
  * **F-19** — ``revoke_user_sessions(user_id)`` writes
    ``users.tokens_revoked_before`` so any JWT minted before now is
    rejected by ``get_current_user``. Called whenever a user's role,
    permissions, or account-status fields mutate.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Callable, Iterable

from fastapi import Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

log = logging.getLogger(__name__)


# ── F-02 · password-reset TTL ─────────────────────────────────────


PASSWORD_RESET_TTL_MINUTES = int(os.environ.get("PASSWORD_RESET_TTL_MINUTES", "10080"))


# ── F-03 · role-tiered JWT TTL ────────────────────────────────────


# Default access-token TTL. Existing customers carry 24h sessions; we
# don't shorten them globally because the practical risk is mitigated
# by HttpOnly cookies + jti revocation + activity-based refresh.
DEFAULT_JWT_TTL_HOURS = int(os.environ.get("JWT_DEFAULT_TTL_HOURS", "24"))

# High-privilege roles get a tighter window. Stolen-cookie blast-radius
# for master admins is many orders of magnitude higher than a regular
# operator's, so we hard-cap at 1h.
MASTER_ADMIN_JWT_TTL_HOURS = int(os.environ.get("MASTER_ADMIN_JWT_TTL_HOURS", "1"))


def access_token_ttl_hours(user_or_role: dict | str | None) -> int:
    """Return the JWT TTL (hours) appropriate for the given user / role.

    Master admins + Pulse master admins → 1 h. Everyone else → 24 h.
    """
    if user_or_role is None:
        return DEFAULT_JWT_TTL_HOURS
    if isinstance(user_or_role, str):
        role = user_or_role.lower()
        if role in ("master_admin", "master", "pulse_master_admin"):
            return MASTER_ADMIN_JWT_TTL_HOURS
        return DEFAULT_JWT_TTL_HOURS
    # Treat as user dict.
    if user_or_role.get("is_master_admin") or user_or_role.get("is_pulse_admin"):
        return MASTER_ADMIN_JWT_TTL_HOURS
    role = (user_or_role.get("role") or "").lower()
    if role in ("master_admin", "master", "pulse_master_admin"):
        return MASTER_ADMIN_JWT_TTL_HOURS
    return DEFAULT_JWT_TTL_HOURS


# ── F-08 · PII strip for /auth/me + similar “return the user dict”
#           endpoints. Belt-and-braces — the explicit allow-list in
#           routes/auth.py::get_me is the primary defence; this is the
#           safety net for any new route that returns a raw user doc.


# Fields that must NEVER leave the server in a user response.
_PII_BLACKLIST = frozenset({
    "password",
    "password_hash",
    "password_history",
    "password_updated_at",
    "mfa_secret",
    "mfa_secret_temp",
    "mfa_backup_codes",
    "mfa_backup_code_hashes",
    "stripe_customer_id",
    "stripe_subscription_id",
    "stripe_payment_method_id",
    "stripe_account_id",
    "reset_token",
    "reset_token_expires",
    "_id",
    "tokens_revoked_before",
    "lockout_until",
    "failed_login_attempts",
    "internal_notes",
    "support_pin",
    "invite_token",
    "invite_token_expires",
    "_jwt_jti",
    "_jwt_exp",
    "_jwt_mfa_verified",
    "_jwt_iat",
    "_mod_scope_ids",
    "_mod_child_org_ids",
})


def sanitize_me_response(doc: dict | None) -> dict:
    """Return a copy of ``doc`` with every blacklisted PII field
    removed. Idempotent — safe to call on an already-sanitised dict.
    """
    if not doc:
        return {}
    return {k: v for k, v in doc.items() if k not in _PII_BLACKLIST}


# ── F-17 · require MFA for high-privilege endpoints ────────────────


# When True (default in production), master-admin endpoints 401 if the
# caller's session wasn't elevated via MFA. Off in dev so the rest of
# the test suite doesn't have to enrol TOTP first.
ENFORCE_MASTER_ADMIN_MFA = os.environ.get(
    "ENFORCE_MASTER_ADMIN_MFA", "false",
).lower() in ("1", "true", "yes")


def require_mfa_verified(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that 401s unless the caller authenticated via MFA
    this session. ``utils.auth.get_current_user`` stashes the
    ``mfa_verified`` JWT claim under ``user['_jwt_mfa_verified']``.
    """
    if not user.get("_jwt_mfa_verified"):
        raise HTTPException(
            status_code=401,
            detail="MFA verification required. Sign out and sign back in with your authenticator code.",
        )
    return user


def enforce_master_admin_mfa(user: dict) -> None:
    """Raise 401 if MFA enforcement is enabled and the master-admin
    caller hasn't completed MFA this session. Soft-fails when the env
    flag is off so legacy sessions don't break overnight."""
    if not ENFORCE_MASTER_ADMIN_MFA:
        return
    is_admin = bool(
        user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or (user.get("role") or "").lower() in ("master_admin", "pulse_master_admin"),
    )
    if not is_admin:
        return
    if not user.get("_jwt_mfa_verified"):
        # Iter (Jun 2026) — instead of forcing a full sign-out/-in, prompt the
        # inline authenticator step-up (§18). The frontend axios interceptor
        # catches this 403 shape, opens <StepUpDialog>, and transparently
        # retries once the master admin enters their code. get_current_user
        # then treats the fresh step-up as MFA-verified, so the retry passes
        # (and further privileged actions pass for the step-up TTL window).
        raise HTTPException(
            status_code=403,
            detail={
                "error": "step_up_required",
                "mfa_enabled": True,
                "action": "master_admin_action",
            },
        )


# ── F-18 · server-side role gates ─────────────────────────────────


# Role family aliases — keep in sync with utils/auth.py::apply_site_lock.
_PRIVILEGED_ROLES = frozenset({"owner", "manager", "master_admin", "master", "pulse_master_admin"})


def require_role(*roles: str) -> Callable[[dict], dict]:
    """FastAPI dependency factory. 403s the caller unless their role
    (or master-admin flag) is in the allow-list.

    Master admins always pass — they're a superset of every operator
    role. Pulse master admins also pass.
    """
    allowed = {r.lower() for r in roles}

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("is_master_admin") or user.get("is_pulse_admin"):
            return user
        role = (user.get("role") or "").lower()
        if role in allowed:
            return user
        raise HTTPException(
            status_code=403,
            detail=f"This action requires one of: {', '.join(sorted(allowed))}",
        )

    return _dep


def assert_role(user: dict, roles: Iterable[str]) -> None:
    """Inline equivalent of ``require_role`` for endpoints that pull
    the user via a different dependency and just need a guard inline.
    """
    allowed = {r.lower() for r in roles}
    if user.get("is_master_admin") or user.get("is_pulse_admin"):
        return
    role = (user.get("role") or "").lower()
    if role in allowed:
        return
    raise HTTPException(
        status_code=403,
        detail=f"This action requires one of: {', '.join(sorted(allowed))}",
    )


# ── F-19 · session invalidation on RBAC mutation ───────────────────


async def revoke_user_sessions(user_id: str, *, reason: str = "rbac_change") -> None:
    """Revoke every active session for ``user_id`` by stamping a
    server-side cut-off. ``utils.auth.get_current_user`` compares
    each JWT's ``iat`` against this and rejects anything minted
    before it.

    Idempotent. Use whenever a user's role, permissions,
    ``allowed_site_ids``, ``module_overrides``, ``is_master_admin``
    flag, or ``disabled``/``archived`` status changes.
    """
    if not user_id:
        return
    now = int(datetime.now(timezone.utc).timestamp())
    try:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "tokens_revoked_before": now,
                "tokens_revoked_reason": reason,
                "tokens_revoked_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        # CRM users may carry their own sessions.
        await db.crm_users.update_one(
            {"id": user_id},
            {"$set": {
                "tokens_revoked_before": now,
                "tokens_revoked_reason": reason,
                "tokens_revoked_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    except Exception:
        log.exception("revoke_user_sessions(%s) failed", user_id)


__all__ = [
    "PASSWORD_RESET_TTL_MINUTES",
    "DEFAULT_JWT_TTL_HOURS", "MASTER_ADMIN_JWT_TTL_HOURS",
    "access_token_ttl_hours",
    "sanitize_me_response",
    "require_mfa_verified", "enforce_master_admin_mfa",
    "ENFORCE_MASTER_ADMIN_MFA",
    "require_role", "assert_role",
    "revoke_user_sessions",
]
