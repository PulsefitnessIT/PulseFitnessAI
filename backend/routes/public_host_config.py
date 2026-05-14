"""Public host-config resolver — drives the custom-domain routing.

When a visitor lands on a custom tenant hostname (e.g.
``join.acmegym.com``), the SPA boots and immediately calls
``GET /api/public/host-config?host=...`` with the live
``window.location.host``. This endpoint returns:

    {
        "matched":          bool,
        "host":             str   (echoed back),
        "org_slug":         str   (the tenant's public member-app slug),
        "org_name":         str,
        "primary_route":    str   ("join" | "app" | "brag" | "timetable"),
        "redirect_path":    str   (the SPA route to push the user onto),
        "branding": {
            "company_name":     str,
            "primary_color":    str | None,
            "logo_url":         str | None,
        }
    }

If the hostname is not a verified custom domain the response is
``{"matched": false, "host": ...}`` so the SPA can fall back to the
default marketing/login experience without crashing.

This endpoint is intentionally:
    * **Public** (no auth) — needed before the visitor exists in the
      system at all.
    * **Read-only** — never writes / never echoes verification tokens.
    * **PII-safe** — only returns the org's public-marketing fields
      (slug, name, primary colour, logo URL).
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Query

from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public-host-config"])


_ROUTE_TO_PATH = {
    # All paths are SPA paths — they DO need the slug filled in.
    "join": "/m/{slug}/join",
    "app": "/m/{slug}",
    "brag": "/m/{slug}/brag",
    "timetable": "/m/{slug}",
}


_HOST_CLEAN_RX = re.compile(r"^[a-z0-9.\-]+$")


def _normalise_host(raw: str) -> str:
    if not raw:
        return ""
    host = raw.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split(":", 1)[0]
    if not _HOST_CLEAN_RX.match(host):
        return ""
    return host


def _branding(org: dict) -> dict:
    overrides = org.get("theme_overrides") or {}
    branding = org.get("branding") or {}
    return {
        "company_name": branding.get("company_name") or org.get("name") or "",
        "primary_color": overrides.get("primary")
        or branding.get("primary_color")
        or None,
        "logo_url": branding.get("logo_url") or None,
    }


@router.get("/host-config")
async def host_config(host: str = Query(..., max_length=253)):
    """Resolve a custom hostname → tenant routing decision."""
    h = _normalise_host(host)
    if not h:
        return {"matched": False, "host": host, "reason": "invalid_host"}

    org = await db.organizations.find_one(
        {
            "custom_domains.hostname": h,
            "custom_domains.verified": True,
        },
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "slug": 1,
            "branding": 1,
            "theme_overrides": 1,
            "custom_domains": 1,
        },
    )
    if not org:
        return {"matched": False, "host": h}

    # Find the matching domain row (an org may have multiple custom
    # domains routing to different surfaces).
    matched = next(
        (
            d for d in (org.get("custom_domains") or [])
            if d.get("hostname") == h and d.get("verified")
        ),
        None,
    )
    if not matched:
        return {"matched": False, "host": h}

    slug = org.get("slug") or org.get("id")
    if not slug:
        # Defensive: a tenant without a public slug cannot host a
        # branded member surface. Surface the failure rather than
        # 500-ing in the SPA.
        return {"matched": False, "host": h, "reason": "no_slug"}

    primary_route = (matched.get("primary_route") or "join").lower()
    tpl = _ROUTE_TO_PATH.get(primary_route) or _ROUTE_TO_PATH["join"]
    redirect_path = tpl.format(slug=slug)

    return {
        "matched": True,
        "host": h,
        "org_id": org.get("id"),
        "org_slug": slug,
        "org_name": org.get("name"),
        "primary_route": primary_route,
        "redirect_path": redirect_path,
        "branding": _branding(org),
    }
