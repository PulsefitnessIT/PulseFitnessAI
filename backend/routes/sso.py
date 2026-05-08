"""
SSO API routes — /api/auth/sso/*.

Thin wiring over ``utils.sso``. Guarded by the ``SSO_ENABLED`` env flag so
this is a true zero-cost no-op when the feature is off.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from utils.auth import create_token
from utils.sso import (
    build_authorization_url,
    exchange_and_verify,
    link_or_create_user,
    sso_enabled,
    sso_public_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/auth/sso/status")
async def sso_status() -> dict:
    """Public — frontend uses this to render / hide the 'Sign in with SSO' button."""
    return sso_public_config()


@router.get("/auth/sso/start")
async def sso_start() -> RedirectResponse:
    if not sso_enabled():
        raise HTTPException(status_code=503, detail="SSO is not enabled")
    url, _state, _nonce = await build_authorization_url()
    return RedirectResponse(url=url, status_code=302)


@router.get("/auth/sso/callback")
async def sso_callback(request: Request):
    if not sso_enabled():
        raise HTTPException(status_code=503, detail="SSO is not enabled")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    claims = await exchange_and_verify(code, state)
    user = await link_or_create_user(claims)
    try:
        from utils.security_plus import audit_required
        await audit_required("security_audit_log", {
            "event": "sso.login.success",
            "user_id": user["id"], "email": user.get("email"),
            "provider": claims.get("iss"),
        })
    except Exception:
        pass
    token = create_token(user["id"])
    # Bounce back to the frontend with a short-lived handoff token in the hash
    # fragment so it doesn't hit server logs or the referrer header. Derive
    # the origin from the current request so SSO works across every domain
    # the app is served from (preview, production, custom domains). Fall back
    # to FRONTEND_URL only if we somehow can't read the origin/referer.
    import os
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        referer = request.headers.get("referer", "") or ""
        if referer:
            parts = referer.split("/")
            if len(parts) >= 3:
                origin = "/".join(parts[:3])
    if not origin:
        origin = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    return RedirectResponse(url=f"{origin}/sso-complete#token={token}", status_code=302)
