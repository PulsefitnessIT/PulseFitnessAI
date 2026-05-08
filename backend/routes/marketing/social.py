"""Meta (Facebook/Instagram) OAuth wizard scaffold.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _new_id,
    _now_iso,
    _org_id,
)

router = APIRouter()


# ───────────────────────── Social Media (Meta wizard scaffold) ─────────

def _meta_app_configured() -> bool:
    return bool(os.environ.get("META_APP_ID") and os.environ.get("META_APP_SECRET"))


@router.get("/marketing/social/status", dependencies=[Depends(require_module("marketing"))])
async def social_status(user: dict = Depends(get_current_user)):
    """Indicates whether the platform-level Meta App is wired up and lists
    any accounts this org has already connected."""
    org_id = await _org_id(user)
    accounts = await db.marketing_social_accounts.find(
        {"organization_id": org_id, "status": "active"}, {"_id": 0, "access_token_enc": 0},
    ).to_list(length=20)
    return {
        "platform_configured": _meta_app_configured(),
        "accounts": accounts,
        "missing_env_vars": [v for v in ("META_APP_ID", "META_APP_SECRET") if not os.environ.get(v)],
    }


@router.get("/marketing/social/connect-url", dependencies=[Depends(require_module("marketing"))])
async def social_connect_url(network: str = Query("facebook"), user: dict = Depends(get_current_user)):
    """Step 1 of the OAuth wizard — returns Meta's authorise URL with a
    fresh state token. Backend stashes the state with the calling org id so
    the callback can re-link."""
    if not _meta_app_configured():
        raise HTTPException(503, "Meta App not configured — platform admin needs to set META_APP_ID and META_APP_SECRET")
    org_id = await _org_id(user)
    state = secrets.token_urlsafe(32)
    await db.marketing_oauth_states.insert_one({
        "state": state, "organization_id": org_id,
        "user_id": user["id"], "network": network,
        "created_at": _now_iso(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    })
    redirect_uri = (os.environ.get("META_OAUTH_REDIRECT_URI")
                    or f"{os.environ.get('APP_BASE_URL', '')}/api/marketing/social/oauth-callback")
    scopes = ("pages_show_list,pages_manage_posts,pages_read_engagement,"
              "instagram_basic,instagram_content_publish,business_management")
    auth_url = (
        f"https://www.facebook.com/v20.0/dialog/oauth"
        f"?client_id={os.environ['META_APP_ID']}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&scope={scopes}"
        f"&response_type=code"
    )
    return {"authorise_url": auth_url, "state": state}


@router.get("/marketing/social/oauth-callback")
async def social_oauth_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    """Step 2 — receive the code, exchange for long-lived token, store
    encrypted, redirect back to /marketing?social=connected."""
    if not (code and state):
        raise HTTPException(400, "Missing code or state")
    pending = await db.marketing_oauth_states.find_one({"state": state}, {"_id": 0})
    if not pending:
        raise HTTPException(400, "Invalid or expired state")
    if pending["expires_at"] < _now_iso():
        raise HTTPException(400, "OAuth state expired — please retry")

    if not _meta_app_configured():
        raise HTTPException(503, "Meta App not configured")

    import httpx
    redirect_uri = (os.environ.get("META_OAUTH_REDIRECT_URI")
                    or f"{os.environ.get('APP_BASE_URL', '')}/api/marketing/social/oauth-callback")
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Short-lived → long-lived token exchange in two steps.
        r = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "client_id": os.environ["META_APP_ID"],
                "client_secret": os.environ["META_APP_SECRET"],
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        if r.status_code != 200:
            raise HTTPException(400, f"Token exchange failed: {r.text[:200]}")
        short = r.json().get("access_token")
        r = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": os.environ["META_APP_ID"],
                "client_secret": os.environ["META_APP_SECRET"],
                "fb_exchange_token": short,
            },
        )
        long_lived = r.json().get("access_token") or short
        # Fetch the user's pages.
        r = await client.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={"access_token": long_lived},
        )
        pages = (r.json() or {}).get("data", []) if r.status_code == 200 else []

    # Store one row per page (encrypted token using existing Fernet helper).
    try:
        from utils.crypto_helpers import encrypt_value  # type: ignore
    except ImportError:
        try:
            from utils.sicon_client import encrypt_value  # type: ignore
        except ImportError:
            encrypt_value = lambda s: s  # type: ignore  # noqa: E731

    for p in pages:
        await db.marketing_social_accounts.update_one(
            {"organization_id": pending["organization_id"], "meta_page_id": p.get("id")},
            {"$set": {
                "id": _new_id(), "organization_id": pending["organization_id"],
                "network": "facebook_page",
                "meta_page_id": p.get("id"), "page_name": p.get("name"),
                "access_token_enc": encrypt_value(p.get("access_token") or long_lived),
                "status": "active",
                "connected_by": pending["user_id"], "connected_at": _now_iso(),
            }},
            upsert=True,
        )

    await db.marketing_oauth_states.delete_one({"state": state})
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{os.environ.get('APP_BASE_URL', '')}/marketing?social=connected")
