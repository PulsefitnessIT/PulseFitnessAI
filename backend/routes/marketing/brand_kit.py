"""Marketing Brand Kit — operator-managed logo / colours / fonts / voice.

Backed by the `marketing_brand_kit` collection (one document per org).
Reads/writes are authenticated and module-gated. The Director, Creative
Studio, and any auto-poster pipeline already pull `marketing_brand_kit`
to compose brand-locked outputs — this module exposes the CRUD layer
so operators can set + replace the kit from the UI.

Schema (loose):
  organization_id    : str (primary key)
  primary_color      : str (hex)
  secondary_color    : str (hex)
  primary_logo_asset_id : str | null    -> links to marketing_creative_assets.id
  primary_logo_data_url : str | null    -> inlined data URL for fast Director use
  font_heading       : str | null       e.g. "Inter"
  font_body          : str | null
  voice              : str | null       e.g. "warm, energetic, inclusive"
  banned_phrases     : list[str]
  updated_at         : iso datetime
  updated_by         : user id
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import _now_iso, _org_id

router = APIRouter()


_DEFAULT = {
    "primary_color": "#0055FF",
    "secondary_color": "#66CCFF",
    "primary_logo_asset_id": None,
    "primary_logo_data_url": None,
    "primary_logo_url": None,  # remote URL fallback when no data URL set
    "font_heading": None,
    "font_body": None,
    "voice": None,
    "banned_phrases": [],
}


def _strip(doc: dict | None) -> dict:
    if not doc:
        return {**_DEFAULT}
    return {**_DEFAULT, **{k: v for k, v in doc.items() if k != "_id"}}


async def _backfill_from_org(org_id: str) -> dict:
    """Pull whatever branding the org has set up at the org level (during
    onboarding or via Master Admin) so the Brand Kit tab is pre-filled
    instead of empty when the operator first opens it.

    Field name compatibility: orgs store their primary colour under
    several legacy keys depending on how they were provisioned. We check
    them in order of preference and inline the logo URL as a data URL is
    NOT possible from a remote URL — so we surface the URL itself; the
    Director already supports loading from URL when no inlined data URL
    is present.
    """
    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "logo_url": 1, "brand_color": 1,
         "primary_brand_colour": 1, "primary_color": 1, "branding": 1},
    ) or {}
    branding = org.get("branding") or {}
    primary = (org.get("brand_color") or org.get("primary_brand_colour")
                or org.get("primary_color") or branding.get("primary_color"))
    secondary = branding.get("secondary_color")
    logo = org.get("logo_url") or branding.get("logo_url")
    out: dict = {}
    if primary and isinstance(primary, str) and primary.startswith("#"):
        out["primary_color"] = primary
    if secondary and isinstance(secondary, str) and secondary.startswith("#"):
        out["secondary_color"] = secondary
    if logo:
        out["primary_logo_url"] = logo  # remote URL fallback (NOT data URL)
    return out


@router.get(
    "/marketing/brand-kit",
    dependencies=[Depends(require_module("marketing"))],
)
async def get_brand_kit(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    doc = await db.marketing_brand_kit.find_one({"organization_id": org_id})
    backfill = await _backfill_from_org(org_id)
    kit = _strip(doc)
    # Apply backfill ONLY where the operator hasn't set their own value.
    for k, v in backfill.items():
        if not kit.get(k):
            kit[k] = v
    return {"brand_kit": kit, "configured": bool(doc)}


class BrandKitUpdate(BaseModel):
    primary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    primary_logo_asset_id: Optional[str] = None
    primary_logo_data_url: Optional[str] = None
    font_heading: Optional[str] = Field(default=None, max_length=80)
    font_body: Optional[str] = Field(default=None, max_length=80)
    voice: Optional[str] = Field(default=None, max_length=200)
    banned_phrases: Optional[list[str]] = None


@router.put(
    "/marketing/brand-kit",
    dependencies=[Depends(require_module("marketing"))],
)
async def update_brand_kit(
    body: BrandKitUpdate, user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    update = {"organization_id": org_id, "updated_at": _now_iso(),
              "updated_by": user["id"]}
    for k, v in body.model_dump(exclude_unset=True).items():
        update[k] = v
    if (body.banned_phrases is not None
            and any(len(s) > 60 for s in body.banned_phrases)):
        raise HTTPException(400, "Banned phrases must be ≤60 chars each")
    await db.marketing_brand_kit.update_one(
        {"organization_id": org_id}, {"$set": update}, upsert=True,
    )
    doc = await db.marketing_brand_kit.find_one({"organization_id": org_id})
    return {"ok": True, "brand_kit": _strip(doc), "configured": True}
