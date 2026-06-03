"""Member-App Builder — Stage 1: card registry + layout persistence.

Goal
====
Let gym owners customise *what their members see in the mobile member
app* without writing any code. They drag-drop cards onto a layout, save,
and the live member portal renders that layout instead of the default.

This module ships the **foundations only** — the data layer:

  • A canonical registry of card types (12 cards covering every member-
    facing feature the platform exposes).
  • Per-card schema describing which settings the operator can tweak.
  • Persistence in ``member_app_layouts`` (one row per organisation +
    optional per-site override).
  • Read + write endpoints that the drag-drop UI (Stage 2) and live
    member portal (Stage 3) will consume.

The actual drag-drop UI and the rendering layer come in subsequent
passes. This module deliberately exposes a stable JSON contract so the
UI work can proceed independently.

Schema (member_app_layouts)
---------------------------
::

    {
        "id":              str,            # uuid
        "organization_id": str,
        "site_id":         str | None,     # null = org-wide default
        "name":            str,            # "Default", "Kids site", …
        "is_default":      bool,           # exactly one per (org, site)
        "cards": [
            {
                "type":     str,           # one of CARD_REGISTRY keys
                "position": int,           # 0-indexed render order
                "enabled":  bool,
                "settings": dict,          # validated against card schema
            }, …
        ],
        "updated_by":  str,
        "updated_at":  ISO timestamp,
    }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


# ── Card Registry ───────────────────────────────────────────────────
#
# Single source of truth for every card the member app can render.
# The drag-drop UI iterates this list to populate its sidebar; the
# member portal iterates a saved layout and looks up each card type
# here to know which component to render.
#
# Each entry's keys
#   id              stable slug, used in the saved layout
#   title           operator-facing label (drag handle)
#   description     one-liner shown in the picker
#   icon            Lucide icon name — kept as a string so the backend
#                   can serve this list to a non-React client too
#   category        one of: bookings, social, services, status, rewards
#   settings_schema list of {key,label,type,default,options?} tuples
#                   describing per-card customisation
#   default_enabled whether this card appears in the out-of-the-box
#                   layout for a brand-new org
#   pulse_only      gate cards behind brand (Pulse Pro members only)
CARD_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "class_booking",
        "title": "Book a class",
        "description": "Live timetable with one-tap booking, waitlist, and recurring auto-enrol.",
        "icon": "CalendarDays",
        "category": "bookings",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "show_instructors",  "label": "Show instructor photos",   "type": "bool",   "default": True},
            {"key": "show_waitlist",     "label": "Show waitlist count",      "type": "bool",   "default": True},
            {"key": "default_view",      "label": "Default calendar view",    "type": "select",
             "default": "week", "options": ["day", "week", "list"]},
        ],
    },
    {
        "id": "my_bookings",
        "title": "My bookings",
        "description": "Upcoming sessions for the member with one-tap cancel / swap.",
        "icon": "ClipboardList",
        "category": "bookings",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "show_swap_button",  "label": "Allow shift-swap",         "type": "bool",   "default": True},
            {"key": "lookahead_days",    "label": "How many days to show",    "type": "number", "default": 14},
        ],
    },
    {
        "id": "pt_enquiry",
        "title": "Personal training enquiry",
        "description": "One-tap form for members to request a PT session — routes to your CRM.",
        "icon": "Dumbbell",
        "category": "services",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "headline",          "label": "Headline copy",            "type": "text",
             "default": "Train smarter with a PT"},
            {"key": "auto_assign_to",    "label": "Auto-assign new leads to", "type": "select",
             "default": "round_robin", "options": ["round_robin", "site_manager", "first_available"]},
        ],
    },
    {
        "id": "equipment_status",
        "title": "Equipment status",
        "description": "Live 'in service / out of service' for every machine on the floor.",
        "icon": "Wrench",
        "category": "status",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "show_categories",   "label": "Show category filters",    "type": "bool",   "default": True},
            {"key": "show_eta_back",     "label": "Show 'back in service' ETA","type": "bool",  "default": True},
        ],
    },
    {
        "id": "loyalty_points",
        "title": "Loyalty & rewards",
        "description": "Points balance, tier, redeemable rewards.",
        "icon": "Trophy",
        "category": "rewards",
        "default_enabled": False,
        "pulse_only": False,
        "settings_schema": [
            {"key": "tier_naming",       "label": "Tier naming style",        "type": "select",
             "default": "metals", "options": ["metals", "athletic", "elements"]},
        ],
    },
    {
        "id": "social_pulse",
        "title": "Social pulse",
        "description": "Streaks, friend activity, leaderboard for the member's site.",
        "icon": "Activity",
        "category": "social",
        "default_enabled": False,
        "pulse_only": False,
        "settings_schema": [
            {"key": "leaderboard_size",  "label": "Leaderboard length",       "type": "number", "default": 10},
            {"key": "show_streaks",      "label": "Show streaks",             "type": "bool",   "default": True},
        ],
    },
    {
        "id": "shop",
        "title": "Pro shop",
        "description": "In-app store: drinks, merch, supplements with member pricing.",
        "icon": "ShoppingBag",
        "category": "services",
        "default_enabled": False,
        "pulse_only": False,
        "settings_schema": [
            {"key": "currency_symbol",   "label": "Currency",                  "type": "select",
             "default": "GBP", "options": ["GBP", "EUR", "USD"]},
        ],
    },
    {
        "id": "weekly_digest",
        "title": "Weekly digest",
        "description": "Member's last-7-day stats: visits, classes, PRs, points.",
        "icon": "BarChart3",
        "category": "social",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [],
    },
    {
        "id": "announcements",
        "title": "Announcements",
        "description": "Site-wide messages from staff (closures, new classes, events).",
        "icon": "Megaphone",
        "category": "social",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "max_visible",       "label": "How many to show",         "type": "number", "default": 3},
        ],
    },
    {
        "id": "membership_card",
        "title": "Digital membership card",
        "description": "QR code + member ID for kiosk check-in. Replaces the plastic card.",
        "icon": "QrCode",
        "category": "status",
        "default_enabled": True,
        "pulse_only": False,
        "settings_schema": [
            {"key": "show_expiry",       "label": "Show expiry date",         "type": "bool",   "default": True},
        ],
    },
    {
        "id": "refer_a_friend",
        "title": "Refer a friend",
        "description": "Share-link with attribution baked in. Configurable reward + landing page.",
        "icon": "Share2",
        "category": "rewards",
        "default_enabled": False,
        "pulse_only": False,
        "settings_schema": [
            {"key": "reward_pence",      "label": "Reward (pence)",            "type": "number", "default": 1000},
            {"key": "applies_to",        "label": "Reward applies to",         "type": "select",
             "default": "both", "options": ["both", "referrer_only", "friend_only"]},
        ],
    },
    {
        "id": "pulse_brag_share",
        "title": "Pulse brag share",
        "description": "Auto-generated branded image of the member's milestone, ready to share.",
        "icon": "Sparkles",
        "category": "social",
        "default_enabled": False,
        "pulse_only": True,   # Pulse Fitness only
        "settings_schema": [],
    },
]


def _is_pulse(account_type: str | None) -> bool:
    return bool(account_type) and str(account_type).lower().startswith("pulse")


def _registry_for(account_type: str | None) -> list[dict[str, Any]]:
    """Filter the registry to cards available for this brand."""
    if _is_pulse(account_type):
        return CARD_REGISTRY
    return [c for c in CARD_REGISTRY if not c.get("pulse_only")]


def _default_layout_cards(account_type: str | None) -> list[dict[str, Any]]:
    """Out-of-the-box layout for a brand-new org. Cards in the order we
    think makes sense for the average gym; operator can re-order."""
    cards = []
    pos = 0
    for c in _registry_for(account_type):
        if not c["default_enabled"]:
            continue
        # Settings start at the schema's defaults — operator customises later.
        defaults = {s["key"]: s["default"] for s in c["settings_schema"]}
        cards.append({
            "type": c["id"],
            "position": pos,
            "enabled": True,
            "settings": defaults,
        })
        pos += 1
    return cards


def _validate_layout(payload: dict, account_type: str | None) -> list[dict[str, Any]]:
    """Validate + normalise a layout's ``cards`` list.

    Rejects unknown card types, deduplicates, fills in missing settings
    with defaults, and normalises position to 0..N-1 in the order the
    operator submitted them. Returns the cleaned cards list — never
    mutates the input.
    """
    cards_in = payload.get("cards") or []
    if not isinstance(cards_in, list):
        raise HTTPException(400, "`cards` must be a list")
    registry = {c["id"]: c for c in _registry_for(account_type)}

    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for idx, card in enumerate(cards_in):
        if not isinstance(card, dict):
            raise HTTPException(400, f"Card at index {idx} is not an object")
        ctype = (card.get("type") or "").strip()
        if ctype not in registry:
            raise HTTPException(400, f"Unknown card type: {ctype!r}")
        if ctype in seen:
            # Skip duplicates rather than reject — friendlier UX from
            # the drag-drop builder, where a stale render could double-add.
            continue
        seen.add(ctype)
        spec = registry[ctype]
        # Merge submitted settings on top of schema defaults so missing
        # keys get safe values.
        defaults = {s["key"]: s["default"] for s in spec["settings_schema"]}
        merged_settings = {**defaults, **(card.get("settings") or {})}
        cleaned.append({
            "type": ctype,
            "position": idx,
            "enabled": bool(card.get("enabled", True)),
            "settings": merged_settings,
        })
    return cleaned


async def _resolve_org(user: dict) -> tuple[str, str | None]:
    """Return (organization_id, account_type) for the calling user.

    Uses the org doc as the source of truth for account_type because
    the JWT can be stale across plan upgrades.
    """
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "User has no organization")
    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "account_type": 1}
    ) or {}
    return org_id, org.get("account_type")


def _require_owner_or_manager(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role not in ("owner", "manager", "master_admin") and not user.get("is_master_admin"):
        raise HTTPException(403, "Only owners and managers can edit the member-app layout")


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/member-app/cards")
async def list_available_cards(user: dict = Depends(get_current_user)) -> dict:
    """Return the card registry filtered for this org's brand.

    The Stage 2 drag-drop UI calls this once on mount to populate its
    "available cards" sidebar.
    """
    _, account_type = await _resolve_org(user)
    return {"cards": _registry_for(account_type)}


@router.get("/member-app/layout")
async def get_layout(
    site_id: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the saved layout for an org (optionally a specific site).

    Falls back to a sensible default layout if nothing is saved yet —
    so brand-new orgs see a working member app on day one.
    """
    org_id, account_type = await _resolve_org(user)
    org_doc = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "membership_app_slug": 1, "slug": 1,
         "primary_brand_colour": 1, "logo_url": 1, "member_app_hero_url": 1},
    ) or {}
    app_slug = org_doc.get("membership_app_slug") or org_doc.get("slug") or None
    branding = {
        "primary_brand_colour": org_doc.get("primary_brand_colour") or "#19CDFF",
        "logo_url": org_doc.get("logo_url") or None,
        "hero_image_url": org_doc.get("member_app_hero_url") or None,
    }
    query: dict[str, Any] = {"organization_id": org_id, "is_default": True}
    if site_id:
        query["site_id"] = site_id
    layout = await db.member_app_layouts.find_one(query, {"_id": 0})
    if not layout:
        layout = {
            "id": None,
            "organization_id": org_id,
            "site_id": site_id,
            "name": "Default",
            "is_default": True,
            "cards": _default_layout_cards(account_type),
            "updated_by": None,
            "updated_at": None,
        }
    return {"layout": layout, "account_type": account_type, "app_slug": app_slug, "branding": branding}


@router.put("/member-app/layout")
async def save_layout(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Persist a layout. Owner/manager only.

    Body::

        {
            "site_id": "<uuid> or null",
            "cards": [{"type": "class_booking", "settings": {...}}, …]
        }
    """
    _require_owner_or_manager(user)
    org_id, account_type = await _resolve_org(user)
    cards = _validate_layout(payload, account_type)

    site_id = payload.get("site_id")
    now = datetime.now(timezone.utc).isoformat()
    update_filter = {"organization_id": org_id, "site_id": site_id, "is_default": True}
    update_doc = {
        "$set": {
            "cards": cards,
            "updated_by": user.get("id"),
            "updated_at": now,
            "name": payload.get("name") or "Default",
        },
        "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "site_id": site_id,
            "is_default": True,
        },
    }
    await db.member_app_layouts.update_one(update_filter, update_doc, upsert=True)
    saved = await db.member_app_layouts.find_one(update_filter, {"_id": 0})
    return {"layout": saved}


@router.post("/member-app/layout/reset")
async def reset_layout(
    payload: dict = Body(default={}),
    user: dict = Depends(get_current_user),
) -> dict:
    """Reset the org's layout back to the platform default.

    Useful when an operator has misconfigured the app and wants a clean
    slate. Owner/manager only.
    """
    _require_owner_or_manager(user)
    org_id, account_type = await _resolve_org(user)
    site_id = payload.get("site_id")
    cards = _default_layout_cards(account_type)
    now = datetime.now(timezone.utc).isoformat()
    await db.member_app_layouts.update_one(
        {"organization_id": org_id, "site_id": site_id, "is_default": True},
        {
            "$set": {
                "cards": cards,
                "updated_by": user.get("id"),
                "updated_at": now,
                "name": "Default",
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "site_id": site_id,
                "is_default": True,
            },
        },
        upsert=True,
    )
    return {"layout": {"cards": cards, "is_default": True}, "reset": True}


# ── Member-app branding & theme (Iter 220q) ─────────────────────────
#
# Lets operators personalise the public member app (colour + logo +
# hero/cover banner) straight from the App Builder, with the changes
# reflected in the live preview and the real /m/{slug} app.

import base64  # noqa: E402
import io  # noqa: E402

from fastapi import File, Response, UploadFile  # noqa: E402
from PIL import Image  # noqa: E402

from utils.database import APP_NAME, put_object, get_object  # noqa: E402


def _normalise_hex(value: str | None) -> str | None:
    """Accept #RGB / #RRGGBB (case-insensitive); return #RRGGBB or None."""
    if not value:
        return None
    v = str(value).strip()
    if not v.startswith("#"):
        v = "#" + v
    body = v[1:]
    if len(body) == 3 and all(c in "0123456789abcdefABCDEF" for c in body):
        body = "".join(c * 2 for c in body)
    if len(body) != 6 or any(c not in "0123456789abcdefABCDEF" for c in body):
        return None
    return "#" + body.upper()


@router.put("/member-app/branding")
async def save_branding(
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Persist member-app branding (brand colour). Owner/manager only.

    The hero image + logo are uploaded via their own multipart endpoints;
    this saves the brand colour (and keeps `branding.primary_color` in sync
    so every reader of org branding picks it up).
    """
    _require_owner_or_manager(user)
    org_id, _ = await _resolve_org(user)
    updates: dict[str, Any] = {}
    if "primary_brand_colour" in payload:
        colour = _normalise_hex(payload.get("primary_brand_colour"))
        if not colour:
            raise HTTPException(400, "Invalid brand colour — use a hex value like #19CDFF")
        updates["primary_brand_colour"] = colour
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "branding": 1}) or {}
        branding = dict(org.get("branding") or {})
        branding["primary_color"] = colour
        updates["branding"] = branding
    if updates:
        await db.organizations.update_one({"id": org_id}, {"$set": updates})
    org_doc = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "primary_brand_colour": 1, "logo_url": 1, "member_app_hero_url": 1},
    ) or {}
    return {
        "branding": {
            "primary_brand_colour": org_doc.get("primary_brand_colour") or "#19CDFF",
            "logo_url": org_doc.get("logo_url") or None,
            "hero_image_url": org_doc.get("member_app_hero_url") or None,
        }
    }


@router.post("/member-app/hero-image")
async def upload_hero_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload the member-app hero/cover banner (PNG/JPEG/WEBP). Owner/manager only."""
    _require_owner_or_manager(user)
    org_id, _ = await _resolve_org(user)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Image must be 8 MB or smaller")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise HTTPException(400, "Could not parse image") from exc
    # Banner: fit within 1600×900, JPEG for size (no transparency needed).
    img = img.convert("RGB")
    img.thumbnail((1600, 900), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=86, optimize=True)
    compressed = buf.getvalue()
    content_type = "image/jpeg"
    path = f"{APP_NAME}/member_hero/{org_id}/{uuid.uuid4()}.jpg"
    hero_path: str | None = None
    try:
        put_object(path, compressed, content_type)
        hero_path = path
        hero_url = f"/api/member-app/hero-image/{org_id}?v={uuid.uuid4().hex[:8]}"
    except Exception as exc:
        logger.warning(f"[member-app] hero object-store put failed, embedding inline: {exc}")
        hero_url = f"data:{content_type};base64," + base64.b64encode(compressed).decode("ascii")
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "member_app_hero_url": hero_url,
            "member_app_hero_path": hero_path,
            "member_app_hero_content_type": content_type,
        }},
    )
    return {"hero_image_url": hero_url}


@router.delete("/member-app/hero-image")
async def delete_hero_image(user: dict = Depends(get_current_user)) -> dict:
    _require_owner_or_manager(user)
    org_id, _ = await _resolve_org(user)
    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"member_app_hero_url": None, "member_app_hero_path": None}},
    )
    return {"hero_image_url": None}


@router.get("/member-app/hero-image/{org_id}")
async def serve_hero_image(org_id: str) -> Response:
    """Public proxy for the member-app hero banner (used by /m/{slug})."""
    rec = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "member_app_hero_path": 1, "member_app_hero_url": 1,
         "member_app_hero_content_type": 1},
    )
    if not rec:
        raise HTTPException(404, "Organisation not found")
    path = rec.get("member_app_hero_path")
    if not path:
        raise HTTPException(404, "No hero image")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        raise HTTPException(404, "Hero image not available") from exc
    return Response(
        content=data,
        media_type=rec.get("member_app_hero_content_type") or content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=300"},
    )
