"""Onboarding tour demo data: status, seed, dismiss, clear-demo.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from utils.database import db

from routes.marketing.helpers import (
    _get_entitlement,
    _new_id,
    _now_iso,
    _org_id,
    _require_feature,
    logger,
)

router = APIRouter()


# ════════════════════════════════════════════════════════════════════════
# Marketing Suite Product Tour — first-time UX seeding
# ════════════════════════════════════════════════════════════════════════
#
# When a Pro user first lands on /marketing we show an interactive product
# tour. The tour finishes by offering "Create demo data so I can play" —
# which calls the endpoint below. It seeds:
#   • 1 audience  ("Tour: VIP regulars")
#   • 1 campaign  ("Tour: Weekend spin promo" — draft)
#   • 1 creative  (gpt-image-1 generated poster, or SVG fallback)
#   • 1 journey   ("Tour: Welcome new member")
#
# All marked `is_demo: true` so a single "Clear demo data" call removes
# them cleanly without affecting real audiences/campaigns.


@router.get("/marketing/tour/status")
async def tour_status(user: dict = Depends(get_current_user)):
    """Return whether the user has dismissed the tour AND whether demo data
    currently exists (so the UI can offer a 'Clear demo data' action)."""
    org_id = await _org_id(user)
    seen = bool(await db.marketing_tour_state.find_one({"user_id": user["id"]}))
    demo_count = await db.marketing_audiences.count_documents({
        "organization_id": org_id, "tags": {"$in": ["demo_tour"]},
    })
    return {"tour_seen": seen, "demo_data_exists": demo_count > 0}


@router.post("/marketing/tour/seed")
async def tour_seed(user: dict = Depends(get_current_user)):
    """Create disposable demo audience + campaign + creative + journey so
    the user can see the platform in action without committing real data."""
    org_id = await _org_id(user)
    entitlement = await _get_entitlement(user)
    _require_feature(entitlement, "audiences")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    gym_name = org.get("name") or "your gym"
    now = _now_iso()

    # 1. Demo audience — VIP regulars (LTV >= £500 AND visits last 30d >= 8)
    audience = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": "Tour: VIP regulars",
        "type": "dynamic",
        "rules": {"op": "and", "conditions": [
            {"field": "lifetime_value_gbp", "op": ">=", "value": 500},
            {"field": "attendance_30d", "op": ">=", "value": 8},
        ]},
        "estimated_size": 23,  # plausible demo number
        "computed_at": now, "tags": ["demo_tour"],
        "is_demo": True,
        "created_at": now, "updated_at": now,
    }
    await db.marketing_audiences.insert_one(audience)

    # 2. Demo campaign draft
    campaign = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": "Tour: Weekend spin promo",
        "channel": "email",
        "audience_id": audience["id"],
        "content": {
            "subject": f"🚴 Saturday morning is calling — {gym_name}",
            "body_html": (
                "<h1>Saturday spin · 8:00am</h1>"
                "<p>You're a regular — and we saved your bike. "
                "Tap below to lock it in.</p>"
                "<a href='#'>Reserve my spot</a>"
            ),
            "creative_brief": "High-energy spin class with neon studio lighting",
        },
        "status": "draft",
        "tags": ["demo_tour"],
        "is_demo": True,
        "metrics": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0, "unsubscribed": 0},
        "created_at": now, "updated_at": now,
    }
    await db.marketing_campaigns.insert_one(campaign)

    # 3. Demo creative — try gpt-image-1, fall back to SVG so the demo always works
    creative_url = None
    creative_model = "fallback_svg"
    try:
        from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration  # type: ignore
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if api_key:
            image_gen = OpenAIImageGeneration(api_key=api_key)
            images = await image_gen.generate_images(
                prompt=(
                    "High-energy spin class with neon studio lighting, riders mid-effort, "
                    "dramatic shadow play, vibrant cyan and blue colour palette, "
                    "photographic, professional fitness marketing imagery, no text overlays"
                ),
                model="gpt-image-1",
                number_of_images=1,
            )
            import base64
            if images:
                creative_url = "data:image/png;base64," + base64.b64encode(images[0]).decode()
                creative_model = "gpt-image-1"
    except Exception as exc:  # pragma: no cover
        logger.info("[marketing] tour gpt-image-1 unavailable: %s", exc)

    if not creative_url:
        import base64
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">'
            '<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">'
            '<stop offset="0%" stop-color="#19CDFF"/><stop offset="100%" stop-color="#0055FF"/>'
            '</linearGradient></defs><rect width="800" height="800" fill="url(#g)"/>'
            '<text x="400" y="420" font-family="Inter,sans-serif" font-size="44" font-weight="700" '
            'text-anchor="middle" fill="white">Saturday Spin · 8am</text></svg>'
        )
        creative_url = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

    creative = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "type": "social_post",
        "prompt": "Tour demo: Saturday spin promo",
        "brand_kit_applied": True,
        "source": creative_model if creative_model != "fallback_svg" else "fallback_svg",
        "variants": [{"url": creative_url, "model": creative_model}],
        "used_by_campaign_ids": [campaign["id"]], "used_by_post_ids": [],
        "tags": ["demo_tour"],
        "is_demo": True,
        "created_at": now,
    }
    await db.marketing_creative_assets.insert_one(creative)

    # 4. Demo journey — 3 steps: trigger → wait 1d → send email
    journey = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "name": "Tour: Welcome new member",
        "trigger": {"type": "event", "event": "member_signed_up"},
        "steps": [
            {"id": "step-1", "type": "wait", "config": {"hours": 24}},
            {"id": "step-2", "type": "send_email", "config": {
                "subject": f"Welcome to {gym_name}!",
                "body_html": "<p>Your first session is on us — book any class this week.</p>",
            }},
            {"id": "step-3", "type": "tag_contact", "config": {"tag": "onboarded"}},
        ],
        "status": "draft",
        "tags": ["demo_tour"],
        "is_demo": True,
        "stats": {"entered": 0, "completed": 0, "dropped": 0},
        "created_at": now, "updated_at": now,
    }
    await db.marketing_journeys.insert_one(journey)

    # Mark tour as seen for this user.
    await db.marketing_tour_state.update_one(
        {"user_id": user["id"]},
        {"$set": {"user_id": user["id"], "completed_at": now, "seeded_demo": True}},
        upsert=True,
    )

    return {
        "audience_id": audience["id"],
        "campaign_id": campaign["id"],
        "creative_id": creative["id"],
        "journey_id": journey["id"],
        "creative_used_real_ai": creative_model == "gpt-image-1",
    }


@router.post("/marketing/tour/dismiss")
async def tour_dismiss(user: dict = Depends(get_current_user)):
    """Mark the tour as dismissed without seeding demo data."""
    await db.marketing_tour_state.update_one(
        {"user_id": user["id"]},
        {"$set": {"user_id": user["id"], "completed_at": _now_iso(), "seeded_demo": False}},
        upsert=True,
    )
    return {"ok": True}


@router.delete("/marketing/tour/demo-data")
async def tour_clear_demo(user: dict = Depends(get_current_user)):
    """Remove every record tagged as demo_tour for this org."""
    org_id = await _org_id(user)
    res_a = await db.marketing_audiences.delete_many({"organization_id": org_id, "tags": "demo_tour"})
    res_c = await db.marketing_campaigns.delete_many({"organization_id": org_id, "tags": "demo_tour"})
    res_j = await db.marketing_journeys.delete_many({"organization_id": org_id, "tags": "demo_tour"})
    res_cr = await db.marketing_creative_assets.delete_many({"organization_id": org_id, "tags": "demo_tour"})
    return {
        "audiences_removed": res_a.deleted_count,
        "campaigns_removed": res_c.deleted_count,
        "journeys_removed": res_j.deleted_count,
        "creatives_removed": res_cr.deleted_count,
    }


__all__ = ["router"]
