"""
Generic OIDC SSO scaffold (P3+, Feb 2026).

Single-tenant, env-gated. Set these vars to activate::

    SSO_ENABLED=true
    SSO_PROVIDER_URL=https://<tenant>.okta.com            # or Azure/Google/Auth0
    SSO_CLIENT_ID=<registered client id>
    SSO_CLIENT_SECRET=<registered client secret>
    SSO_SCOPES="openid profile email"                     # defaults shown

The implementation is deliberately minimal so a second IdP can be added by
changing env vars — no code changes. For per-org SSO config (different IdP
per customer), extend this module to read a doc out of a ``sso_providers``
collection keyed by org.

Flow::

    GET  /api/auth/sso/start     → 302 to IdP auth endpoint
    GET  /api/auth/sso/callback  → validates code, links / creates user, issues JWT
    GET  /api/auth/sso/status    → public; reports whether SSO is available
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

import httpx
import jwt as pyjwt
from fastapi import HTTPException

from utils.database import db

logger = logging.getLogger(__name__)

_DISCOVERY_CACHE: dict[str, dict[str, Any]] = {}
_JWKS_CACHE: dict[str, tuple[float, dict]] = {}
_DISCOVERY_TTL = 3600
_JWKS_TTL = 3600


def sso_enabled() -> bool:
    return (os.environ.get("SSO_ENABLED", "").strip().lower() in ("1", "true", "yes")
            and bool(os.environ.get("SSO_PROVIDER_URL", "").strip())
            and bool(os.environ.get("SSO_CLIENT_ID", "").strip())
            and bool(os.environ.get("SSO_CLIENT_SECRET", "").strip()))


def sso_public_config() -> dict:
    return {
        "enabled": sso_enabled(),
        "provider_url": os.environ.get("SSO_PROVIDER_URL", ""),
        "scopes": os.environ.get("SSO_SCOPES", "openid profile email"),
    }


async def _fetch_discovery() -> dict:
    """Fetch + cache the /.well-known/openid-configuration doc."""
    base = os.environ.get("SSO_PROVIDER_URL", "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="SSO not configured")
    now = time.time()
    cached = _DISCOVERY_CACHE.get(base)
    if cached and (now - cached.get("_fetched_at", 0)) < _DISCOVERY_TTL:
        return cached
    url = f"{base}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            doc = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[sso] discovery failed at {url}: {exc}")
        raise HTTPException(status_code=503, detail="IdP discovery failed") from exc
    doc["_fetched_at"] = now
    _DISCOVERY_CACHE[base] = doc
    return doc


async def _fetch_jwks(jwks_uri: str) -> dict:
    now = time.time()
    cached = _JWKS_CACHE.get(jwks_uri)
    if cached and (now - cached[0]) < _JWKS_TTL:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            keys = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[sso] jwks fetch failed: {exc}")
        raise HTTPException(status_code=503, detail="IdP JWKS fetch failed") from exc
    _JWKS_CACHE[jwks_uri] = (now, keys)
    return keys


def _redirect_uri() -> str:
    base = os.environ.get("BACKEND_EXTERNAL_URL", "").rstrip("/")
    if not base:
        # Fall back to frontend URL stripped + /api suffix
        base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return f"{base}/api/auth/sso/callback"


# ─── Auth flow ───────────────────────────────────────────────────

async def build_authorization_url() -> tuple[str, str, str]:
    """Return (auth_url, state, nonce). Caller must persist state+nonce."""
    doc = await _fetch_discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    params = {
        "client_id": os.environ.get("SSO_CLIENT_ID", ""),
        "response_type": "code",
        "scope": os.environ.get("SSO_SCOPES", "openid profile email"),
        "redirect_uri": _redirect_uri(),
        "state": state,
        "nonce": nonce,
    }
    from urllib.parse import urlencode
    url = f"{doc['authorization_endpoint']}?{urlencode(params)}"
    await db.sso_state.insert_one({
        "state": state, "nonce": nonce,
        "created_at": time.time(),
    })
    return url, state, nonce


async def _consume_state(state: str) -> dict:
    row = await db.sso_state.find_one_and_delete({"state": state}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or replayed state")
    if time.time() - row.get("created_at", 0) > 600:
        raise HTTPException(status_code=400, detail="State expired — retry login")
    return row


async def exchange_and_verify(code: str, state: str) -> dict:
    """Swap an authorization code for an ID token + profile claims.

    Returns the decoded ID token claims dict. Raises on any validation failure.
    """
    row = await _consume_state(state)
    doc = await _fetch_discovery()
    redirect_uri = _redirect_uri()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": os.environ.get("SSO_CLIENT_ID", ""),
        "client_secret": os.environ.get("SSO_CLIENT_SECRET", ""),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(doc["token_endpoint"], data=data)
            token_resp.raise_for_status()
            tokens = token_resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[sso] token exchange failed: {exc}")
        raise HTTPException(status_code=400, detail="Token exchange failed") from exc

    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="IdP did not return id_token")

    claims = await _verify_id_token(id_token, doc)
    if claims.get("nonce") != row.get("nonce"):
        raise HTTPException(status_code=400, detail="Nonce mismatch")
    return claims


async def _verify_id_token(id_token: str, discovery: dict) -> dict:
    jwks = await _fetch_jwks(discovery["jwks_uri"])
    header = pyjwt.get_unverified_header(id_token)
    kid = header.get("kid")
    key = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            key = pyjwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            break
    if key is None:
        raise HTTPException(status_code=400, detail=f"Unknown key id {kid}")
    try:
        claims = pyjwt.decode(
            id_token, key,
            algorithms=["RS256", "RS384", "RS512"],
            audience=os.environ.get("SSO_CLIENT_ID", ""),
            issuer=discovery["issuer"],
        )
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid id_token: {exc}") from exc
    return claims


# ─── User linking ────────────────────────────────────────────────

async def link_or_create_user(claims: dict) -> dict:
    """Idempotent: link existing email, or create a brand-new SSO user."""
    from datetime import datetime, timezone
    import uuid

    email = (claims.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="IdP did not provide email claim")
    sub = claims.get("sub") or ""
    provider = _provider_from_issuer(claims.get("iss", ""))
    name = claims.get("name") or claims.get("preferred_username") or email.split("@")[0]

    # 1. Existing link by (provider, sub)
    link = await db.sso_links.find_one({"provider": provider, "sub": sub}, {"_id": 0})
    if link:
        user = await db.users.find_one({"id": link["user_id"]}, {"_id": 0})
        if user:
            return user

    # 2. Existing user by email → link
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        await db.sso_links.insert_one({
            "user_id": user["id"], "provider": provider, "sub": sub,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
        return user

    # 3. Create a new SSO user. Org defaults to the master platform org for now;
    # platform operators can migrate the user to a real org after first login.
    user_id = str(uuid.uuid4())
    org_id = os.environ.get("SSO_DEFAULT_ORG_ID", "").strip() or None
    user_doc = {
        "id": user_id, "email": email, "full_name": name,
        "organization_id": org_id, "role": "staff",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "password_updated_at": datetime.now(timezone.utc).isoformat(),
        "sso_only": True,
    }
    await db.users.insert_one(user_doc)
    await db.sso_links.insert_one({
        "user_id": user_id, "provider": provider, "sub": sub,
        "linked_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        from utils.security_plus import audit_required
        await audit_required("security_audit_log", {
            "event": "sso.user.created",
            "user_id": user_id, "email": email, "provider": provider,
        })
    except Exception:
        pass
    return user_doc


def _provider_from_issuer(issuer: str) -> str:
    lower = (issuer or "").lower()
    if "okta" in lower:
        return "okta"
    if "microsoftonline" in lower or "microsoft.com" in lower:
        return "azure"
    if "accounts.google.com" in lower or "googleapis.com" in lower:
        return "google"
    if "auth0.com" in lower:
        return "auth0"
    return "generic"


async def ensure_sso_indexes() -> None:
    try:
        await db.sso_state.create_index("created_at", expireAfterSeconds=900)
        await db.sso_state.create_index("state", unique=True)
        await db.sso_links.create_index([("provider", 1), ("sub", 1)], unique=True)
        await db.sso_links.create_index("user_id")
    except Exception as exc:
        logger.warning(f"[sso] index creation failed: {exc}")
