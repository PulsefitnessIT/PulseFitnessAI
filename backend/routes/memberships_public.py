"""Pulse Fitness Memberships — Phase 2 public class detail + embed widget.

Two public, auth-free routes that gyms can share / embed anywhere:

  GET /api/m/{slug}/c/{occurrence_id}    — class detail JSON for the
                                           branded share page (book CTA,
                                           instructor, capacity, image).

  GET /api/m/{slug}/timetable/embed       — public timetable JSON used by
                                           the embeddable widget. Same
                                           data the member portal sees,
                                           but no member-specific flags.

  GET /api/m/{slug}/embed-snippet         — operator-only, returns the
                                           ready-to-paste <iframe> snippet
                                           for their website.

Frontend renders three matching routes (see frontend changelog):
  /m/:slug/c/:occId        — branded share page
  /embed/:slug/timetable    — chrome-less embed view
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from routes.memberships import _require_operator_org
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-public"])


def _strip(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


async def _resolve_org_by_slug(slug: str) -> dict:
    """Slug is `membership_app_slug` on the org doc. Hard 404 on miss so
    we don't leak which slugs exist."""
    org = await db.organizations.find_one(
        {"membership_app_slug": slug.lower()},
        {"_id": 0, "id": 1, "name": 1, "logo_url": 1, "primary_color": 1,
         "secondary_color": 1, "membership_app_slug": 1, "modules": 1},
    )
    if not org:
        raise HTTPException(404, "Studio not found")
    if not (org.get("modules") or {}).get("memberships"):
        raise HTTPException(404, "Studio not found")
    return org


# ───────────────────────── Public class detail (share link) ─────────────────────────


@router.get("/m/{slug}/c/{occurrence_id}")
async def public_class_detail(slug: str, occurrence_id: str):
    """Branded class detail for a sharable URL. No auth — a guest pastes
    the link on Instagram, the recipient lands on the gym's branded page
    showing the class + a 'Book a spot' CTA that opens the auth modal."""
    org = await _resolve_org_by_slug(slug)
    occ = await db.class_occurrences.find_one(
        {"id": occurrence_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    tpl = await db.class_templates.find_one(
        {"id": occ.get("template_id"), "archived": {"$ne": True}}, {"_id": 0},
    ) or {}
    # We expose enough to render a beautiful share card but NOTHING about
    # who's booked — that's private even if it's "just" attendance count.
    capacity = int(occ.get("capacity") or 0)
    booked = int(occ.get("bookings_count") or 0)
    spots_left = max(capacity - booked, 0)
    fill_pct = round(100.0 * booked / capacity, 0) if capacity else 0
    return {
        "organization": {
            "name": org.get("name"),
            "logo_url": org.get("logo_url"),
            "primary_color": org.get("primary_color") or "#0055FF",
            "secondary_color": org.get("secondary_color") or "#19CDFF",
            "slug": slug,
        },
        "class": {
            "id": occ["id"],
            "name": tpl.get("name") or "Class",
            "description": tpl.get("description"),
            "image_url": tpl.get("image_url"),
            "instructor_name": tpl.get("instructor_name"),
            "duration_min": tpl.get("duration_min") or 45,
            "starts_at": occ.get("starts_at"),
            "ends_at": occ.get("ends_at"),
            "location": tpl.get("room_name") or tpl.get("site_name"),
            "credits_to_book": int(tpl.get("credits_to_book") or 1),
            "capacity": capacity,
            "spots_left": spots_left,
            "fill_pct": fill_pct,
            "is_full": spots_left == 0,
            "is_course_session": bool(occ.get("is_course_session")),
            "course_session_index": occ.get("course_session_index"),
            "course_session_total": occ.get("course_session_total"),
        },
    }


# ───────────────────────── Public embed timetable ─────────────────────────


@router.get("/m/{slug}/timetable/embed")
async def public_embed_timetable(
    slug: str,
    days_ahead: int = Query(default=14, ge=1, le=60),
):
    """Public timetable for embedding. Returns next `days_ahead` days of
    scheduled occurrences with capacity but no member-specific data."""
    org = await _resolve_org_by_slug(slug)
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=int(days_ahead))
    occs = await db.class_occurrences.find(
        {"organization_id": org["id"], "status": "scheduled",
         "starts_at": {"$gte": now.isoformat(), "$lte": until.isoformat()}},
        {"_id": 0},
    ).sort("starts_at", 1).to_list(500)
    if not occs:
        return {"organization": _public_brand(org), "occurrences": []}
    tpl_ids = list({o.get("template_id") for o in occs if o.get("template_id")})
    tpls = {t["id"]: t for t in await db.class_templates.find(
        {"id": {"$in": tpl_ids}}, {"_id": 0},
    ).to_list(500)} if tpl_ids else {}
    enriched: list[dict] = []
    for o in occs:
        tpl = tpls.get(o.get("template_id")) or {}
        capacity = int(o.get("capacity") or 0)
        booked = int(o.get("bookings_count") or 0)
        enriched.append({
            "id": o["id"],
            "name": tpl.get("name") or "Class",
            "starts_at": o.get("starts_at"),
            "ends_at": o.get("ends_at"),
            "instructor_name": tpl.get("instructor_name"),
            "location": tpl.get("room_name") or tpl.get("site_name"),
            "duration_min": tpl.get("duration_min") or 45,
            "image_url": tpl.get("image_url"),
            "capacity": capacity,
            "spots_left": max(capacity - booked, 0),
            "is_full": booked >= capacity if capacity else False,
            "share_path": f"/m/{slug}/c/{o['id']}",
        })
    return {"organization": _public_brand(org), "occurrences": enriched}


def _public_brand(org: dict) -> dict:
    return {
        "name": org.get("name"),
        "logo_url": org.get("logo_url"),
        "primary_color": org.get("primary_color") or "#0055FF",
        "secondary_color": org.get("secondary_color") or "#19CDFF",
        "slug": org.get("membership_app_slug"),
    }


# ───────────────────────── Operator: get embed snippet ─────────────────────────


@router.get(
    "/memberships/embed-snippet",
    dependencies=[Depends(require_module("memberships"))],
)
async def operator_embed_snippet(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Operator-only — returns the iframe + JS snippet they paste on
    their website. Includes their org slug + a tested embed URL."""
    org_id = await _require_operator_org(user)
    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "membership_app_slug": 1, "name": 1, "primary_color": 1},
    ) or {}
    slug = (org.get("membership_app_slug") or "").lower()
    if not slug:
        raise HTTPException(
            400,
            "Set up your studio's app slug first (Memberships → Setup → "
            "App URL).",
        )
    base = str(request.base_url).rstrip("/")
    embed_url = f"{base}/embed/{slug}/timetable"
    iframe_snippet = (
        f'<iframe src="{embed_url}" '
        f'width="100%" height="640" frameborder="0" '
        f'style="border:0;border-radius:12px;max-width:960px;" '
        f'title="{org.get("name", "Class timetable")} — book a class"></iframe>'
    )
    script_snippet = (
        f'<script src="{base}/embed/loader.js" '
        f'data-gymaxis-slug="{slug}" data-gymaxis-height="640" '
        f'async></script>\n'
        f'<div id="gymaxis-timetable"></div>'
    )
    return {
        "embed_url": embed_url,
        "share_base_url": f"{base}/m/{slug}",
        "iframe_snippet": iframe_snippet,
        "script_snippet": script_snippet,
        "instructions": (
            "Paste the iframe snippet anywhere HTML is supported (Wix, "
            "Squarespace, WordPress, custom). For more control use the "
            "<script> snippet which auto-resizes to its container."
        ),
    }


__all__ = ["router"]
