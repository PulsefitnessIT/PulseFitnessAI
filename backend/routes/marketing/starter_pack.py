"""Marketing Starter Pack — iter 216h71.

When the operator applies their brand auto-discovery draft to the
brand kit, we offer to auto-draft a starter content pack: 3 emails
(welcome / win-back / promo) + 3 social posts (Instagram caption /
Facebook post / X tweet) baked with their tone-of-voice + audience
segments + current campaigns. Result: blank Marketing module → ready
content in <60 s.

Endpoints:
    POST  /api/marketing/starter-pack/generate   →  generate & persist 6 drafts
    GET   /api/marketing/starter-pack            →  retrieve last pack
    DELETE /api/marketing/starter-pack           →  clear

All endpoints are module-gated. Generation uses Claude Haiku 4.5 via
Emergent LLM key (one call, ~$0.02 total).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from routes.marketing.helpers import _now_iso, _org_id
from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter()


SYSTEM_PROMPT = """You are a fitness-industry marketing copywriter generating a
*starter pack* for a gym operator. Reply with JSON ONLY (no markdown fences),
matching this exact schema:

{
  "emails": [
    {"id": "welcome",   "subject": "...", "preview": "...", "body": "... (180-260 words, plain text, use \\n for paragraph breaks)"},
    {"id": "win_back",  "subject": "...", "preview": "...", "body": "..."},
    {"id": "promo",     "subject": "...", "preview": "...", "body": "..."}
  ],
  "social": [
    {"id": "instagram", "platform": "instagram", "body": "180-300 chars with 3-6 relevant hashtags"},
    {"id": "facebook",  "platform": "facebook",  "body": "1-3 short paragraphs"},
    {"id": "x",         "platform": "x",         "body": "<=270 chars"}
  ]
}

Rules:
- Match the operator's tone_of_voice exactly. If the tone says 'sophisticated and motivational', do NOT write peppy. If it says 'warm and inclusive', do not write austere.
- Speak to the listed audiences specifically — mention them or their goals.
- Reference current_campaigns when relevant (e.g. the promo email).
- Keep copy specific to fitness/wellness — never generic.
- No fluff, no clichés like 'unlock your potential'.
- Emails: subject ≤ 50 chars, preview ≤ 90 chars.
- Output JSON ONLY. Do not wrap in markdown fences."""


async def _generate(brand_kit: dict, intel: dict) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI starter pack unavailable — LLM key not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

    tone = (brand_kit.get("voice") or intel.get("tone_of_voice") or "warm, energetic, professional")
    audiences = intel.get("audiences") or []
    campaigns = intel.get("current_campaigns") or []
    keywords = intel.get("keywords") or []
    business_name = brand_kit.get("business_name") or "the gym"

    user_msg = (
        f"Business: {business_name}\n"
        f"Tone of voice: {tone}\n"
        f"Target audiences: {', '.join(audiences) if audiences else '(general fitness members)'}\n"
        f"Current campaigns / promos to weave in where relevant: "
        f"{'; '.join(campaigns) if campaigns else '(none — write evergreen drafts)'}\n"
        f"Brand keywords / services: {', '.join(keywords) if keywords else '(general fitness)'}\n"
        f"Generate the starter pack now."
    )

    chat = LlmChat(
        api_key=api_key,
        session_id=f"starter-pack-{datetime.now(timezone.utc).timestamp()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("anthropic", "claude-haiku-4-5-20251001")
    answer = await chat.send_message(UserMessage(text=user_msg))

    clean = (answer or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.warning("[starter-pack] claude returned non-JSON: %s", exc)
        raise HTTPException(502, "AI returned malformed JSON — please retry")


@router.post("/marketing/starter-pack/generate", dependencies=[Depends(require_module("marketing"))])
async def generate_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    kit = await db.marketing_brand_kit.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    disc = await db.marketing_brand_discovery.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    intel = (disc.get("draft") or {}).get("intelligence") or {}

    if not (kit.get("voice") or intel.get("tone_of_voice")):
        raise HTTPException(
            400,
            "Brand kit is too sparse — set a voice/tone in Brand Kit or run brand auto-discovery first.",
        )

    pack = await _generate(kit, intel)
    # Validate basic shape so the frontend never renders garbage.
    if not isinstance(pack, dict) or "emails" not in pack or "social" not in pack:
        raise HTTPException(502, "AI returned an unexpected shape — please retry")

    doc = {
        "organization_id": org_id,
        "generated_at": _now_iso(),
        "generated_by": user.get("id"),
        "pack": pack,
        "based_on": {
            "voice": kit.get("voice"),
            "audiences": intel.get("audiences"),
            "campaigns": intel.get("current_campaigns"),
        },
    }
    await db.marketing_starter_pack.update_one(
        {"organization_id": org_id}, {"$set": doc}, upsert=True,
    )
    return {"ok": True, "pack": pack, "generated_at": doc["generated_at"]}


@router.get("/marketing/starter-pack", dependencies=[Depends(require_module("marketing"))])
async def get_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    doc = await db.marketing_starter_pack.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return doc


@router.delete("/marketing/starter-pack", dependencies=[Depends(require_module("marketing"))])
async def delete_pack(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    await db.marketing_starter_pack.delete_one({"organization_id": org_id})
    return {"ok": True}
