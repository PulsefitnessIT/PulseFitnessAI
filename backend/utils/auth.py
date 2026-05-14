# Auth utilities: password hashing, JWT, user resolution, org filter
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from datetime import datetime, timezone, timedelta
from typing import Optional
import jwt
import bcrypt
import os

from utils.database import db, JWT_SECRET, JWT_ALGORITHM

# `auto_error=False` so FastAPI doesn't 401 when only a cookie is present.
# We fall through to the cookie path inside `get_current_user` below.
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# HttpOnly cookie name for the JWT session. Set on /auth/login and cleared
# on /auth/logout. Never read from JavaScript.
AUTH_COOKIE_NAME = "ga_session"
# Secure cookies on in any non-dev environment. Tests override this via env.
_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")


def set_auth_cookie(response: Response, token: str, *, max_age_hours: int = 24) -> None:
    """Set the HttpOnly session cookie so the browser can re-auth without
    the frontend ever handling the raw JWT. Backward-compatible: the token
    is also returned in the response body for API clients & legacy FE code.
    """
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=max_age_hours * 3600,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",  # "strict" breaks OAuth redirects; "lax" still blocks CSRF POST
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie on logout."""
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_token(user_id: str, expires_hours: int = 24) -> str:
    # P1+.11 — include jti so tokens can be revoked on logout/compromise
    from utils.security_plus import new_jti
    payload = {
        'user_id': user_id,
        'jti': new_jti(),
        'exp': datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Return the JWT from either the Authorization header or the
    HttpOnly session cookie. Header wins if both are present (useful for
    forcing a specific identity during tests or API calls)."""
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    return cookie if cookie else None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    from utils.security_plus import is_jwt_revoked
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    if await is_jwt_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Session revoked")
    # Member-portal tokens (`kind=member`) are for /member/* endpoints only —
    # they lack a user_id and should never hit operator-side routes.
    if payload.get("kind") == "member":
        raise HTTPException(status_code=403, detail="Member accounts cannot access operator endpoints")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # Stash jti on the user dict so routes can revoke the active token
    user["_jwt_jti"] = payload.get("jti")
    user["_jwt_exp"] = payload.get("exp")
    return user


async def try_get_current_user(request) -> Optional[dict]:
    """Return the authenticated user if the request carries a valid JWT, else None.

    Accepts either the Authorization header or the HttpOnly session cookie.
    Never raises — absent/invalid tokens simply return None.
    """
    from utils.security_plus import is_jwt_revoked
    token: Optional[str] = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    try:
        if await is_jwt_revoked(payload.get("jti")):
            return None
    except Exception:
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    return user



def require_same_org(doc: Optional[dict], user: dict, resource: str = "resource") -> None:
    """P1.7 — defensive org-scope guard used by routes that accept /{id}."""
    if not doc:
        raise HTTPException(status_code=404, detail=f"{resource} not found")
    if user.get("is_master_admin"):
        return
    if doc.get("organization_id") and doc["organization_id"] != user.get("organization_id"):
        raise HTTPException(status_code=403, detail=f"Cross-tenant {resource} access denied")


def get_organization_filter(user: dict) -> dict:
    """Get filter for organization-scoped queries"""
    if user.get('organization_id'):
        return {"organization_id": user['organization_id']}
    else:
        return {"user_id": user['id']}


def apply_site_lock(user: dict, requested_site_id: str | None, base_filter: dict) -> dict:
    """Iter 216bl — clamp a Mongo filter to the user's allowed sites.

    Owners, managers, and master-admins always bypass — they see every
    site in the org. Non-privileged staff are filtered by their
    `users.allowed_site_ids` list when set + non-empty:

      • requested_site_id is None  →  filter `site_id ∈ allowed`
        (records with no site_id are always included so legacy data
         the staff member could already see in the UI doesn't disappear)
      • requested_site_id ∈ allowed →  filter narrowed to that site
      • requested_site_id ∉ allowed →  raise 403

    Empty / absent allowed_site_ids = unrestricted (legacy default).
    Mutates a copy of `base_filter` and returns it.
    """
    role = (user.get("role") or "").lower()
    is_privileged = (
        role in ("owner", "manager", "master_admin", "master")
        or bool(user.get("is_master_admin"))
    )
    out = dict(base_filter)
    allowed = user.get("allowed_site_ids") or []
    if is_privileged or not allowed:
        # Privileged or unrestricted — caller's existing site_id handling stands.
        # Iter 216h113i — when a specific site is requested, scope
        # STRICTLY to that site. Previously we also matched records
        # with no `site_id` (legacy data) which leaked aggregate
        # numbers into per-site views. Multi-site orgs (Third Space,
        # etc.) need clean per-site reporting; "All Operations Sites"
        # is reached by clearing the requested_site_id, not by
        # accidentally bleeding null-scope rows into one site's view.
        if requested_site_id:
            out["site_id"] = requested_site_id
        return out

    # Non-privileged + locked. Validate the requested site if any.
    if requested_site_id and requested_site_id not in allowed:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to that site",
        )
    if requested_site_id:
        # Same strict scoping for locked-down staff users.
        out["site_id"] = requested_site_id
        return out
    # No specific site requested — show all allowed sites + any
    # legacy null-scoped records the user could previously see.
    out["$or"] = [
        {"site_id": {"$in": list(allowed)}},
        {"site_id": {"$exists": False}},
        {"site_id": None},
        {"site_id": ""},
    ]
    return out


async def verify_api_key(api_key: str = Depends(api_key_header)) -> dict:
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    key_doc = await db.api_keys.find_one({"key": api_key, "active": True}, {"_id": 0})
    if not key_doc:
        raise HTTPException(status_code=401, detail="Invalid API key")
    await db.api_keys.update_one(
        {"key": api_key},
        {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}}
    )
    return key_doc
