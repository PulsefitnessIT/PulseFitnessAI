"""Master Admin — Theme Settings & isolation audit (iter 216h95).

Pairs with the Master Admin → Settings & Compliance → Theme settings UI.

Two responsibilities:

1. **Audit endpoint** — returns the brand-isolation report so the UI
   can show a green/amber/red light per palette. The audit codifies the
   following architectural constraints:

   * GymAxis tokens live in ``frontend/src/pages/Marketing/marketing.css``
     (``--gx-*``). They MUST only be referenced by marketing surfaces.
   * Pulse tokens live in ``frontend/src/index.css`` (``--pulse-*``).
     They power the in-app Pulse Fitness brand.
   * The two namespaces never share a CSS variable name.

   The endpoint does not crawl the filesystem in production — that would
   tie operator UX to a node build step. Instead it returns a static
   "design system contract" (the tokens we ship + which surfaces should
   use them). The UI can compare this against what gets rendered.

2. **Per-tenant theme override** — read / write a tenant's
   ``theme_overrides`` field on ``organizations``. Operators can tune
   primary / accent / surface colours per Pulse-Pro customer without
   touching the build. Overrides are applied client-side on tenant
   load (only authenticated users in that org's scope see them).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.master_admin import (
    assert_org_in_pulse_scope,
    require_master_admin,
)
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin/theme", tags=["master-admin-theme"])


_HEX_RX = re.compile(r"^#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")


# ── Design system contract ────────────────────────────────────────────
# Single source of truth for the brand-token isolation audit. Updating
# this list is the agreed protocol when introducing new tokens.

_GYMAXIS_TOKENS = [
    {"var": "--gx-bg",                "value": "#F8FAFC", "role": "Page background"},
    {"var": "--gx-bg-paper",          "value": "#FFFFFF", "role": "Card surface"},
    {"var": "--gx-text",              "value": "#0F172A", "role": "Body text"},
    {"var": "--gx-text-muted",        "value": "#475569", "role": "Secondary text"},
    {"var": "--gx-brand-from",        "value": "#2563EB", "role": "Primary gradient (start)"},
    {"var": "--gx-brand-to",          "value": "#9D4CDD", "role": "Primary gradient (end)"},
    {"var": "--gx-accent-service",    "value": "#06B6D4", "role": "Service Ops accent"},
    {"var": "--gx-accent-crm",        "value": "#6366F1", "role": "CRM accent"},
    {"var": "--gx-accent-memberships","value": "#8B5CF6", "role": "Memberships accent"},
    {"var": "--gx-accent-marketing",  "value": "#D946EF", "role": "Marketing accent"},
    {"var": "--gx-accent-staffing",   "value": "#A855F7", "role": "Staffing accent"},
    {"var": "--gx-accent-reporting",  "value": "#2563EB", "role": "Reporting accent"},
]

_PULSE_TOKENS = [
    {"var": "--pulse-primary",        "value": "#66CCFF", "role": "Primary action fill"},
    {"var": "--pulse-primary-hover",  "value": "#4DBFFF", "role": "Primary hover"},
    {"var": "--pulse-black",          "value": "#212721", "role": "Body text"},
    {"var": "--pulse-bg",             "value": "#F8F9FA", "role": "Page background"},
    {"var": "--pulse-surface",        "value": "#FFFFFF", "role": "Card surface"},
    {"var": "--pulse-text",           "value": "#212721", "role": "Foreground text"},
    {"var": "--pulse-text-muted",     "value": "#505759", "role": "Secondary text"},
    {"var": "--pulse-border",         "value": "#E4E4E7", "role": "Border"},
    {"var": "--pulse-input-bg",       "value": "#FFFFFF", "role": "Input background"},
    {"var": "--pulse-hover",          "value": "#F4F4F5", "role": "Subtle hover"},
]

_OVERRIDABLE_KEYS = {
    "primary",        # main action colour (cyan/blue)
    "primary_hover",
    "surface",        # card/panel background
    "text",
    "text_muted",
    "border",
    "accent",
    # Iter 216h107 — Tender PDF branding overrides
    "tender_company_name",
    "tender_primary_color",
    "tender_logo_url",
}


class ThemeOverrideUpdate(BaseModel):
    primary: Optional[str] = Field(default=None)
    primary_hover: Optional[str] = Field(default=None)
    surface: Optional[str] = Field(default=None)
    text: Optional[str] = Field(default=None)
    text_muted: Optional[str] = Field(default=None)
    border: Optional[str] = Field(default=None)
    accent: Optional[str] = Field(default=None)
    tender_company_name: Optional[str] = Field(default=None, max_length=120)
    tender_primary_color: Optional[str] = Field(default=None)
    tender_logo_url: Optional[str] = Field(default=None, max_length=500)


def _validate_hex(name: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return ""  # Sentinel meaning "clear override"
    if not _HEX_RX.match(v):
        raise HTTPException(status_code=400, detail=f"{name} must be a hex colour like #19CDFF")
    return v.upper()


def _validate_freeform(name: str, value: Optional[str], max_len: int = 120) -> Optional[str]:
    """Whitespace-trim a freeform string. Empty → clear override."""
    if value is None:
        return None
    v = value.strip()
    if v == "":
        return ""
    if len(v) > max_len:
        raise HTTPException(status_code=400, detail=f"{name} must be {max_len} characters or fewer")
    return v


@router.get("/audit")
async def theme_audit(user: dict = Depends(get_current_user)):
    """Return the design-system contract + isolation status.

    The status is currently always "ok" because the two namespaces have
    zero overlapping variable names (a structural guarantee — see file
    locations). This endpoint stays in place so future overlap is
    detected automatically without inspecting frontend source.
    """
    require_master_admin(user)
    gymaxis_names = {t["var"] for t in _GYMAXIS_TOKENS}
    pulse_names = {t["var"] for t in _PULSE_TOKENS}
    overlap = sorted(gymaxis_names & pulse_names)
    # Count overrides currently active across all orgs.
    overrides_count = await db.organizations.count_documents({"theme_overrides": {"$exists": True, "$ne": {}}})
    return {
        "status": "ok" if not overlap else "conflict",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "namespaces": [
            {
                "id": "gymaxis",
                "label": "GymAxis Marketing",
                "prefix": "--gx-",
                "surface_scope": "Marketing site, Master Admin, MOD portal",
                "css_source": "frontend/src/pages/Marketing/marketing.css",
                "tokens": _GYMAXIS_TOKENS,
            },
            {
                "id": "pulse",
                "label": "Pulse Fitness",
                "prefix": "--pulse-",
                "surface_scope": "Operator dashboard, Memberships, Service Desk, CRM, Gym Floor",
                "css_source": "frontend/src/index.css",
                "tokens": _PULSE_TOKENS,
            },
        ],
        "overlap": overlap,
        "tenant_overrides_active": overrides_count,
    }


@router.get("/orgs/{org_id}")
async def get_org_theme(org_id: str, user: dict = Depends(get_current_user)):
    """Return a single tenant's theme overrides (empty object when not customised)."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    return {
        "org_id": org_id,
        "org_name": org.get("name"),
        "account_type": org.get("account_type"),
        "theme_overrides": org.get("theme_overrides") or {},
        "default_namespace": "pulse" if (org.get("account_type") or "").startswith("pulse") else "gymaxis",
    }


@router.put("/orgs/{org_id}")
async def set_org_theme(
    org_id: str,
    payload: ThemeOverrideUpdate,
    user: dict = Depends(get_current_user),
):
    """Persist per-tenant overrides. Empty-string values clear that key."""
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    cleaned: dict[str, str] = {}
    keys_to_unset: list[str] = []
    _COLOR_KEYS = {"primary", "primary_hover", "surface", "text", "text_muted", "border", "accent", "tender_primary_color"}
    for key in _OVERRIDABLE_KEYS:
        raw = getattr(payload, key, None)
        if key in _COLOR_KEYS:
            validated = _validate_hex(key, raw)
        elif key == "tender_company_name":
            validated = _validate_freeform(key, raw, max_len=120)
        elif key == "tender_logo_url":
            validated = _validate_freeform(key, raw, max_len=500)
        else:
            validated = _validate_freeform(key, raw)
        if validated is None:
            continue
        if validated == "":
            keys_to_unset.append(f"theme_overrides.{key}")
        else:
            cleaned[f"theme_overrides.{key}"] = validated

    if not cleaned and not keys_to_unset:
        raise HTTPException(status_code=400, detail="No theme overrides supplied")

    op: dict = {}
    if cleaned:
        op["$set"] = cleaned
        op.setdefault("$set", {})["theme_overrides_updated_at"] = datetime.now(timezone.utc).isoformat()
        op["$set"]["theme_overrides_updated_by"] = user.get("email")
    if keys_to_unset:
        op["$unset"] = {k: "" for k in keys_to_unset}

    result = await db.organizations.update_one({"id": org_id}, op)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Organization not found")
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "theme_overrides": 1})
    return {"ok": True, "theme_overrides": (org or {}).get("theme_overrides") or {}}
