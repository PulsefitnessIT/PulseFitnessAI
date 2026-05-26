"""
GymAxis Service Operations — Branding (logo + colours).

Iter 220i — Engineers asked for their portal + work-report PDFs to
carry their own brand. Two layers:

    1. **Organisation branding** (`organizations.branding`)
       Set by a master admin. Used as the default for everyone.

    2. **Engineer override** (`users.branding`)
       Individual partner engineers (especially solo operators using
       their own brand) can override the org defaults. Falls back to
       the org value when unset.

Fields:
    {
      "logo_url": "https://…",             # served from /api/files
      "primary_color":   "#7C3AED",         # hex with leading hash
      "accent_color":    "#0EA5E9",
      "updated_at": "iso",
      "updated_by_id": "user-id"
    }

Endpoints (under `/api`):
    GET    /svc/branding            → effective branding for the caller
    PUT    /svc/branding/me         → engineer override
    DELETE /svc/branding/me         → revert to org defaults
    PUT    /svc/branding/organization (master admin only)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/svc", tags=["Service Ops · Branding (iter 220i)"])

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _norm_hex(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip()
    m = _HEX_RE.match(raw)
    if not m:
        raise HTTPException(400, f"Invalid hex colour: {value!r}")
    body = m.group(1)
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    return f"#{body.upper()}"


class BrandingIn(BaseModel):
    logo_url: Optional[str] = Field(default=None, max_length=1024)
    primary_color: Optional[str] = Field(default=None, max_length=10)
    accent_color: Optional[str] = Field(default=None, max_length=10)


def _payload(b: BrandingIn, user_id: str) -> dict:
    out: dict = {"updated_at": _now(), "updated_by_id": user_id}
    if b.logo_url is not None:
        out["logo_url"] = (b.logo_url or "").strip() or None
    if b.primary_color is not None:
        out["primary_color"] = _norm_hex(b.primary_color)
    if b.accent_color is not None:
        out["accent_color"] = _norm_hex(b.accent_color)
    return out


async def _resolve_effective(user: dict) -> dict:
    """Resolve effective branding for the caller. Engineer override
    wins for non-null fields; org defaults fill the rest."""
    of = _of(user)
    org_doc = await db.organizations.find_one({"id": of["organization_id"]}, {"_id": 0, "branding": 1})
    org_b = (org_doc or {}).get("branding") or {}
    user_doc = await db.users.find_one({"id": user.get("id")}, {"_id": 0, "branding": 1})
    me_b = (user_doc or {}).get("branding") or {}
    # Merge with engineer override winning when present.
    merged = {
        "logo_url": me_b.get("logo_url") or org_b.get("logo_url"),
        "primary_color": me_b.get("primary_color") or org_b.get("primary_color"),
        "accent_color": me_b.get("accent_color") or org_b.get("accent_color"),
    }
    return {
        "effective": merged,
        "organization": org_b,
        "engineer": me_b,
        "has_engineer_override": bool(me_b),
    }


@router.get("/branding")
async def get_branding(user=Depends(get_current_user)):
    return await _resolve_effective(user)


@router.put("/branding/me")
async def upsert_engineer_branding(
    payload: BrandingIn,
    user=Depends(get_current_user),
):
    """Engineer-level override. Any field set to null/empty by the
    caller is unset, falling back to org defaults."""
    if user.get("id") is None:
        raise HTTPException(403, "Auth required")
    body = _payload(payload, user["id"])
    # Strip Nones so $set doesn't blank out fields the caller didn't pass.
    set_fields = {f"branding.{k}": v for k, v in body.items() if v is not None}
    unset_fields = {f"branding.{k}": "" for k, v in body.items() if v is None and k in ("logo_url", "primary_color", "accent_color")}
    ops: dict = {}
    if set_fields:
        ops["$set"] = set_fields
    if unset_fields:
        ops["$unset"] = unset_fields
    if not ops:
        raise HTTPException(400, "No branding fields supplied")
    await db.users.update_one({"id": user["id"]}, ops)
    return await _resolve_effective(user)


@router.delete("/branding/me")
async def clear_engineer_branding(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$unset": {"branding": ""}})
    return await _resolve_effective(user)


@router.put("/branding/organization")
async def upsert_org_branding(
    payload: BrandingIn,
    user=Depends(get_current_user),
):
    """Master-admin only. Sets the org-wide default branding."""
    roles = user.get("roles") or []
    role = user.get("role") or ""
    if "master_admin" not in roles and role != "master_admin":
        raise HTTPException(403, "Master admin only")
    of = _of(user)
    body = _payload(payload, user.get("id") or "")
    set_fields = {f"branding.{k}": v for k, v in body.items() if v is not None}
    unset_fields = {f"branding.{k}": "" for k, v in body.items() if v is None and k in ("logo_url", "primary_color", "accent_color")}
    ops: dict = {}
    if set_fields:
        ops["$set"] = set_fields
    if unset_fields:
        ops["$unset"] = unset_fields
    if not ops:
        raise HTTPException(400, "No branding fields supplied")
    await db.organizations.update_one({"id": of["organization_id"]}, ops)
    return await _resolve_effective(user)


__all__ = ["router"]
