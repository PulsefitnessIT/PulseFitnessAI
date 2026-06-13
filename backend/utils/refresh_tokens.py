"""Iter 267 — long-lived REFRESH token (idle-gap session resume).

The main session's access token is short-lived (1h for master/pulse admins,
24h others) and rotates frequently. If it fully lapses — e.g. a laptop sleeps
or a tab is frozen past the access-token TTL — the user previously had to log
in again ("Your session has expired").

This module adds a separate, long-lived **refresh token** in its own HttpOnly
cookie (`ga_refresh`), scoped to `/api/auth` so it's only ever sent to the auth
endpoints (least privilege). `/api/auth/refresh` can mint a brand-new access
token from a valid refresh cookie even when the access token has fully expired,
so an active user resumes seamlessly for up to `REFRESH_TOKEN_TTL_DAYS`.

Design choices (kept deliberately conservative for a production auth system):
  • Additive & backward-compatible — existing access-token-only sessions keep
    working untouched; the refresh cookie is a pure fallback.
  • Issued ONLY on real password login / register (NOT impersonation or CRM
    cross-login, which must stay short-lived and scoped).
  • Revocable: killed on logout, and invalidated by the existing per-user
    `tokens_revoked_before` cutoff (password change / sign-out-everywhere).
  • NON-rotating for now — avoids refresh-rotation concurrency races (a bursty
    dashboard firing parallel refreshes). Rotation + reuse/theft detection is a
    documented future hardening.
"""
import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import jwt as _jwt
from fastapi import Request, Response

from utils.database import db, JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)

REFRESH_COOKIE_NAME = "ga_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
REFRESH_TOKEN_TTL_DAYS = int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "30"))
_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")

_indexes_ready = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db.refresh_tokens.create_index("jti", unique=True)
        await db.refresh_tokens.create_index("user_id")
        # TTL index so revoked/expired rows self-purge.
        await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        pass
    _indexes_ready = True


async def issue_refresh_token(
    response: Response, user_id: str, request: Optional[Request], *, mfa_verified: bool = False,
) -> Optional[str]:
    """Mint a refresh token, persist its jti for revocation, and set the
    HttpOnly `ga_refresh` cookie. Call this ONLY on a real login/register.

    NON-FATAL by design: the refresh cookie is an enhancement, so ANY failure
    here (DB perms, index build, write error) is swallowed and logged — the
    login/registration it's attached to must still succeed. Returns the token,
    or None if issuance failed (the session then simply has no refresh cookie
    and relies on the access token + proactive refresh as before)."""
    try:
        await _ensure_indexes()
        jti = secrets.token_urlsafe(24)
        now = _now()
        exp = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
        token = _jwt.encode(
            {
                "user_id": user_id,
                "jti": jti,
                "type": "refresh",
                "mfa": bool(mfa_verified),
                "iat": int(now.timestamp()),
                "exp": int(exp.timestamp()),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        await db.refresh_tokens.insert_one({
            "jti": jti,
            "user_id": user_id,
            "mfa": bool(mfa_verified),
            "created_at": now,
            "expires_at": exp,
            "revoked": False,
            "ip": (request.client.host if request and request.client else None),
        })
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=_COOKIE_SECURE,
            samesite="lax",
            max_age=REFRESH_TOKEN_TTL_DAYS * 86400,
            path=REFRESH_COOKIE_PATH,
        )
        return token
    except Exception:
        logger.exception("[refresh] issue_refresh_token failed — login proceeds without a refresh cookie")
        return None


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _decode_refresh(request: Request) -> Optional[dict]:
    tok = request.cookies.get(REFRESH_COOKIE_NAME)
    if not tok:
        return None
    try:
        payload = _jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    if payload.get("type") != "refresh" or not payload.get("jti"):
        return None
    return payload


async def _valid_refresh_payload(request: Request) -> Optional[dict]:
    """Return the decoded refresh payload IFF the cookie is present, well-formed,
    not expired, its jti row exists + is not revoked, and it post-dates any
    per-user global revocation cutoff. Else None."""
    payload = _decode_refresh(request)
    if not payload:
        return None
    row = await db.refresh_tokens.find_one({"jti": payload["jti"]}, {"_id": 0, "revoked": 1})
    if not row or row.get("revoked"):
        return None
    return payload


async def renew_access_from_refresh(
    request: Request, response: Response,
) -> Optional[Tuple[str, dict]]:
    """Recovery path: validate the refresh cookie and mint a NEW access token
    (rotating the `ga_session` cookie). Returns (access_token, user) or None.

    Does NOT rotate the refresh token — it stays valid for its full TTL, which
    makes concurrent recovery refreshes safe (no reuse false-positives)."""
    try:
        payload = await _valid_refresh_payload(request)
        if not payload:
            return None
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            return None
        # Honour the global per-user revocation cutoff (password change /
        # sign-out-everywhere stamp `tokens_revoked_before` as an epoch).
        cutoff = user.get("tokens_revoked_before")
        if cutoff and int(payload.get("iat", 0)) < int(cutoff):
            return None
        from utils.auth import create_token, set_auth_cookie, purge_legacy_cookie_scopes, record_user_session
        from utils.auth_guards import access_token_ttl_hours
        ttl_hours = access_token_ttl_hours(user)
        access = create_token(user["id"], expires_hours=ttl_hours, mfa_verified=bool(payload.get("mfa")))
        set_auth_cookie(response, access, max_age_hours=ttl_hours)
        purge_legacy_cookie_scopes(response, request)
        await record_user_session(user["id"], access, request)
        return access, user
    except Exception:
        logger.exception("[refresh] renew_access_from_refresh failed")
        return None


async def revoke_refresh_cookie(request: Request) -> None:
    """Mark the presented refresh token revoked (best-effort) — used on logout."""
    payload = _decode_refresh(request)
    if not payload:
        return
    try:
        await db.refresh_tokens.update_one(
            {"jti": payload["jti"]}, {"$set": {"revoked": True, "revoked_at": _now()}},
        )
    except Exception:
        pass


async def revoke_all_refresh_tokens(user_id: str) -> None:
    """Revoke every refresh token for a user (sign-out-everywhere helper)."""
    try:
        await db.refresh_tokens.update_many(
            {"user_id": user_id, "revoked": False},
            {"$set": {"revoked": True, "revoked_at": _now()}},
        )
    except Exception:
        pass


__all__ = [
    "REFRESH_COOKIE_NAME",
    "issue_refresh_token",
    "clear_refresh_cookie",
    "renew_access_from_refresh",
    "revoke_refresh_cookie",
    "revoke_all_refresh_tokens",
]
