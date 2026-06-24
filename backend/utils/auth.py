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
        # SameSite=None (with Secure) is required so the cookie is sent on
        # cross-site subrequests — e.g. when the app is embedded in the
        # Emergent App Preview iframe. Falls back to Lax in non-secure dev.
        samesite="none" if _COOKIE_SECURE else "lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie on logout."""
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_token(
    user_id: str,
    expires_hours: int = 24,
    *,
    mfa_verified: bool = False,
    extra_claims: Optional[dict] = None,
) -> str:
    # P1+.11 — include jti so tokens can be revoked on logout/compromise
    from utils.security_plus import new_jti
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': user_id,
        'jti': new_jti(),
        'exp': now + timedelta(hours=expires_hours),
        'iat': now,
        # Iter 220au · F-17 — pin the MFA-verification state into the
        # access token so high-privilege endpoints can decide whether
        # the session is sufficiently authenticated without re-checking
        # against the DB on every request.
        'mfa_verified': bool(mfa_verified),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Return the JWT from either the Authorization header or the
    HttpOnly session cookie. Header wins if present (lets impersonation /
    CRM / member tokens override the cookie session for that request).

    Iter 227 — a literal ``Bearer null`` / ``Bearer undefined`` / empty
    header (sent by legacy call-sites that read a now-absent
    ``localStorage['token']`` after the cookie migration) is treated as
    *no header* so we fall through to the HttpOnly cookie instead of
    trying to verify the string ``"null"`` and 401-ing the main session.
    """
    if credentials and credentials.credentials:
        val = credentials.credentials.strip()
        if val and val.lower() not in ("null", "undefined", "cookie"):
            return val
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    return cookie if cookie else None


def _cookie_token_candidates(request: Request) -> list:
    """All ``ga_session`` values from the RAW Cookie header, in order.

    Iter 231 — browsers can hold MULTIPLE same-named cookies with
    different scopes (e.g. a legacy ``Domain=.pulsefitness.ai`` cookie
    next to the current host-only one). ``request.cookies`` collapses
    them to the FIRST occurrence, which lets a stale token shadow the
    fresh session and brick every call right after a successful login.
    Parsing the raw header lets the auth layer try every candidate.
    """
    raw = request.headers.get("cookie") or ""
    vals = []
    for part in raw.split(";"):
        name, _, val = part.strip().partition("=")
        if name == AUTH_COOKIE_NAME and val and val not in vals:
            vals.append(val)
    return vals


def purge_legacy_cookie_scopes(response: Response, request: Request) -> None:
    """Emit a delete for the domain-wide variant of the session cookie.

    Iter 231 — if any historic deploy (or proxy) ever set ``ga_session``
    with ``Domain=.example.com``, that cookie lives independently of the
    host-only one we set and, being older, is serialised FIRST by the
    browser — shadowing the fresh session. Killing the domain-scoped
    variant on every login/refresh keeps exactly one session cookie.
    """
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    if not host or "." not in host:
        return  # localhost / bare hostnames have no domain-scoped variant
    if host.replace(".", "").isdigit():
        return  # IP addresses can't carry Domain cookies
    try:
        response.delete_cookie(key=AUTH_COOKIE_NAME, path="/", domain=f".{host}")
    except Exception:
        pass


# ════════════════ Iter 232 — active-session registry ════════════════

def _device_label(user_agent: str) -> str:
    """Coarse, human-friendly "Chrome · Windows" label from a UA string."""
    ua = (user_agent or "").lower()
    if "edg/" in ua or "edge" in ua:
        browser = "Edge"
    elif "opr/" in ua or "opera" in ua:
        browser = "Opera"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "chrome" in ua or "crios" in ua:
        browser = "Chrome"
    elif "safari" in ua:
        browser = "Safari"
    elif "python-requests" in ua or "curl" in ua:
        browser = "API client"
    else:
        browser = "Browser"
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"
    return f"{browser} · {os_name}"


async def record_user_session(user_id: str, token: str, request: Request,
                              *, replaces_jti: Optional[str] = None) -> None:
    """Track a device session in ``user_sessions`` (powering the
    "Active sessions / sign out everywhere" panel).

    On login a new row is inserted; on refresh the rotated jti REPLACES
    the old one in-place so the device keeps one row with its original
    ``created_at``. Best-effort — session tracking must never block auth.
    """
    try:
        payload = verify_token(token) or {}
        jti = payload.get("jti")
        if not jti:
            return
        exp = payload.get("exp")
        exp_ts = int(exp) if exp else int(datetime.now(timezone.utc).timestamp()) + 86400
        now_iso = datetime.now(timezone.utc).isoformat()
        ua = request.headers.get("user-agent", "")
        try:
            from utils.security import _client_ip
            ip = _client_ip(request)
        except Exception:
            ip = request.client.host if request.client else ""
        fields = {
            "user_id": user_id,
            "jti": jti,
            "last_seen_at": now_iso,
            "ip": ip,
            "user_agent": ua[:300],
            "device": _device_label(ua),
            "exp_ts": exp_ts,
            "expires_at": datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat(),
        }
        if replaces_jti:
            res = await db.user_sessions.update_one(
                {"jti": replaces_jti, "user_id": user_id}, {"$set": fields},
            )
            if res.matched_count:
                return
        import uuid as _uuid
        await db.user_sessions.insert_one(
            {"id": str(_uuid.uuid4()), "created_at": now_iso, **fields},
        )
    except Exception:
        pass


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    from utils.security_plus import is_jwt_revoked
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(token)
    primary_revoked = False
    if payload and await is_jwt_revoked(payload.get("jti")):
        primary_revoked, payload = True, None
    if not payload:
        # Iter 231 self-heal — a stale Authorization header or a
        # duplicate-scope stale cookie must not shadow a HEALTHY session
        # cookie. Try every other ga_session value before giving up.
        for cand in _cookie_token_candidates(request):
            if cand == token:
                continue
            p = verify_token(cand)
            if not p:
                continue
            if await is_jwt_revoked(p.get("jti")):
                continue
            token, payload = cand, p
            break
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Session revoked" if primary_revoked else "Invalid token",
        )
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
    # Iter 220au · F-19 — server-side bulk session invalidation. Any
    # mutation that touches role / permissions / status writes a
    # ``tokens_revoked_before`` epoch to the user doc; reject any
    # JWT minted before that cutoff.
    revoked_before = user.get("tokens_revoked_before")
    iat_claim = payload.get("iat")
    if revoked_before and iat_claim:
        try:
            # JWT iat may be int (epoch) or datetime depending on
            # encoder version; coerce both into seconds-since-epoch.
            if isinstance(iat_claim, datetime):
                iat_epoch = int(iat_claim.timestamp())
            else:
                iat_epoch = int(iat_claim)
            if iat_epoch < int(revoked_before):
                raise HTTPException(status_code=401, detail="Session revoked by admin")
        except (TypeError, ValueError):
            pass
    # Stash jti on the user dict so routes can revoke the active token
    user["_jwt_jti"] = payload.get("jti")
    user["_jwt_exp"] = payload.get("exp")
    user["_jwt_iat"] = payload.get("iat")
    # Iter 220au · F-17 — surface the MFA-verified claim so
    # ``require_mfa_verified`` / ``enforce_master_admin_mfa`` can
    # short-circuit without re-reading the JWT.
    user["_jwt_mfa_verified"] = bool(payload.get("mfa_verified"))
    # Iter 216h124 — MOD HQ users see their entire estate by default.
    # Stash the child mod_site org ids on the user dict so the
    # synchronous `get_organization_filter` can fan out queries
    # without every route having to call mod_scope.resolve_…
    # explicitly. The HQ's own org id is included so audit/staff
    # records owned by HQ are still visible.
    at = (user.get("account_type") or "").lower()
    if at in ("mod_org", "mod_branch") and user.get("organization_id"):
        hq = await db.organizations.find_one(
            {"id": user["organization_id"]},
            {"_id": 0, "mod_branch": 1, "mod_root_id": 1, "id": 1},
        ) or {}
        mod_root_id = hq.get("mod_root_id") or hq.get("id") or user["organization_id"]
        cq: dict = {
            "account_type": "mod_site", "is_mod": True,
            "status": {"$ne": "archived"}, "mod_root_id": mod_root_id,
        }
        if at == "mod_branch" and hq.get("mod_branch"):
            cq["mod_branch"] = hq["mod_branch"]
        child_ids: list[str] = []
        async for c in db.organizations.find(cq, {"_id": 0, "id": 1}):
            if c.get("id"):
                child_ids.append(c["id"])
        user["_mod_child_org_ids"] = child_ids
        user["_mod_scope_ids"] = [user["organization_id"], *child_ids]
    # Multi-site isolation — stamp the per-request site scope for the
    # Memberships/CRM/Marketing isolation engine. Owners/admins are
    # unrestricted; managers/staff with a non-empty allowed_site_ids
    # are narrowed to their sites. Must run on EVERY auth path that can
    # reach an isolated module's data (see utils/site_scope.py).
    try:
        from utils.site_scope import set_request_site_scope, set_requested_site
        set_request_site_scope(user)
        set_requested_site(request.headers.get("x-site-id"))
    except Exception:
        pass
    return user


async def optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Iter 267 — like ``get_current_user`` but returns ``None`` instead of
    raising when there's no valid access token. Preserves all of
    ``get_current_user``'s enrichment (`_jwt_jti`, MFA claim, mod-scope) on the
    happy path, so endpoints can fall back to the refresh cookie when the
    access token has expired."""
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None



async def try_get_current_user(request) -> Optional[dict]:
    """Return the authenticated user if the request carries a valid JWT, else None.

    Accepts either the Authorization header or the HttpOnly session cookie.
    Never raises — absent/invalid tokens simply return None.
    """
    from utils.security_plus import is_jwt_revoked
    token: Optional[str] = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        candidate = auth.split(" ", 1)[1].strip()
        # Iter 227 — ignore a literal `Bearer null`/`undefined`/`cookie`
        # sentinel (legacy call-sites post cookie-migration) so we fall
        # through to the HttpOnly cookie.
        if candidate and candidate.lower() not in ("null", "undefined", "cookie"):
            token = candidate
    if not token:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    payload = verify_token(token)
    if payload:
        try:
            if await is_jwt_revoked(payload.get("jti")):
                payload = None
        except Exception:
            return None
    if not payload:
        # Iter 231 self-heal — try other ga_session candidates (see
        # get_current_user) before treating the request as anonymous.
        for cand in _cookie_token_candidates(request):
            if cand == token:
                continue
            p = verify_token(cand)
            if not p:
                continue
            try:
                if await is_jwt_revoked(p.get("jti")):
                    continue
            except Exception:
                continue
            payload = p
            break
    if not payload:
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
    """Get filter for organization-scoped queries.

    Iter 216h124 — MOD HQ users (mod_org / mod_branch) have a
    pre-loaded estate scope on the user dict (`_mod_scope_ids`,
    populated by `get_current_user`). When present we expand the
    filter to include every child mod_site so HQ queries see the
    whole estate by default. Single-site drilldown is handled by
    `apply_site_lock` which rebinds the filter to the chosen child
    org id.
    """
    if user.get('_mod_scope_ids'):
        return {"organization_id": {"$in": user['_mod_scope_ids']}}
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

    # Iter 216h124 — MOD HQ users (mod_org / mod_branch) treat each
    # child site as its own organisation (no `site_id` field on
    # equipment / issues). Drilling into a specific child must REBIND
    # the organization_id filter to that child, not add a `site_id`.
    mod_scope_ids = user.get("_mod_scope_ids")
    if mod_scope_ids and requested_site_id:
        if requested_site_id not in mod_scope_ids:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to that site",
            )
        out["organization_id"] = requested_site_id
        return out

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
