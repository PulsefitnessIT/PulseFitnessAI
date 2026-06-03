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
        {"id": org_id}, {"_id": 0, "membership_app_slug": 1},
    ) or {}
    app_slug = org_doc.get("membership_app_slug") or None
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
    return {"layout": layout, "account_type": account_type, "app_slug": app_slug}


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
