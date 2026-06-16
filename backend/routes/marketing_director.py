"""Pulse Fitness Marketing Suite — AI Creative Director (Phase 1+2).

Replaces the "single-asset generator" mental model with a true Creative
Director pipeline:

  user prompt + goal + tone + (optional) audience hint
        │
        ▼
  Claude Sonnet 4.5  →  full campaign strategy + multi-format copy pack
  (email subject/body, IG caption, FB post, SMS, push, headline, CTAs,
   suggested audience, suggested channels, suggested send-window,
   3 alternate tones for A/B grid)
        │
        ▼
  Gemini Nano Banana (gemini-3.1-flash-image-preview)
  → branded poster image (multi-reference: brand logo + uploaded refs +
    equipment shot, all pixel-composited)
        │
        ▼
  persist as a marketing_director_brief document
  return strategy + copy + image data-url

Endpoints
─────────
POST /api/marketing/creative/director/build       — full Director run
POST /api/marketing/creative/director/refine      — "make it better" iterator
GET  /api/marketing/creative/director/briefs      — list recent briefs
GET  /api/marketing/creative/director/briefs/{id} — single brief
POST /api/marketing/creative/director/briefs/{id}/launch — convert to campaign

This file is intentionally separate from `marketing.py` so the Director
flow can evolve without rewriting the older single-asset endpoints.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.churn_signals import (
    SIGNAL_LABELS as CHURN_SIGNAL_LABELS,
    detect_churn_signals,
)
from utils.database import db
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────── Helpers ─────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# Tones the Director offers — gym/leisure-relevant defaults.
TONE_PRESETS: dict[str, str] = {
    "high_energy": "high-energy, motivating, gym-floor hype",
    "motivational": "motivational, empowering, growth-mindset",
    "premium": "premium, aspirational, boutique-club polish",
    "community": "warm, community-driven, inclusive",
    "urgent": "urgent, limited-time, FOMO-leaning (used sparingly)",
    "friendly": "friendly, casual, approachable",
    "wellness": "calm, wellness-focused, balance-oriented",
    "expert_coach": "expert coach voice, technical credibility",
    "family": "family-friendly, multi-generational, accessible",
    "mod_military": "MOD/military precision, mission-language, no-nonsense",
    "corporate": "corporate B2B, partnership-grade",
}


GOAL_PRESETS: dict[str, str] = {
    "promote_class":      "Promote a specific class to drive bookings",
    "winback_lapsed":     "Win back lapsed members who haven't attended in 30+ days",
    "upgrade_pt":         "Upsell members to personal training",
    "new_member_welcome": "Welcome new members and drive first visit",
    "open_day":           "Promote an open day / community event",
    "referral":           "Drive member referrals",
    "renewal":            "Drive contract renewals before expiry",
    "off_peak":           "Fill off-peak slots with attractive offers",
    "challenge":          "Launch a fitness challenge",
    "newsletter":         "Send a regular newsletter / community update",
}


# Channels the Director generates copy for. Order matters — UI renders
# them as preview cards in this order.
CHANNELS = [
    "email", "instagram", "facebook", "sms", "push", "poster",
]


# Strict JSON schema we ask Claude to return so the frontend can render
# without parsing free-form prose.
DIRECTOR_SCHEMA = {
    "strategy": {
        "summary": "1-2 sentence campaign strategy",
        "goal": "the clarified marketing goal",
        "audience": {
            "name": "human-friendly audience label",
            "rationale": "why this audience",
            "segment_filter_hint": (
                "matches one of: lapsed_30d, active_regulars, new_members, "
                "pt_eligible, off_peak_visitors, all_members, custom"
            ),
        },
        "channels": ["channel keys to use"],
        "schedule": {"send_window": "best send window", "frequency": "send cadence"},
        "tone": "selected tone preset key",
    },
    "copy": {
        "email":     {"subject": "...", "preheader": "...", "body_html": "..."},
        "instagram": {"caption": "...", "hashtags": ["#tag", "..."]},
        "facebook":  {"post": "..."},
        "sms":       {"body": "max 160 chars"},
        "push":      {"title": "...", "body": "max 90 chars"},
        "poster":    {"headline": "...", "subheadline": "...", "cta": "..."},
    },
    "alt_tones": [
        {"tone": "tone_key", "headline": "...", "email_subject": "...", "sms": "..."},
        {"tone": "tone_key", "headline": "...", "email_subject": "...", "sms": "..."},
    ],
}


def _system_prompt(brand_kit: dict, brand_lock: bool) -> str:
    palette = (
        f"primary {brand_kit.get('primary_color', '#0055FF')}, "
        f"secondary {brand_kit.get('secondary_color', '#66CCFF')}"
    )
    if brand_kit.get("accent_color"):
        palette += f", accent {brand_kit['accent_color']}"
    fonts = ""
    if brand_kit.get("font_heading") or brand_kit.get("font_body"):
        fh = brand_kit.get("font_heading") or "the brand's display face"
        fb = brand_kit.get("font_body") or "the brand's body face"
        fonts = f"Headings should reference '{fh}' and body copy '{fb}'.  "
    voice_guard = brand_kit.get("voice") or "professional, energetic, gym-friendly"
    banned = brand_kit.get("banned_phrases") or []
    banned_str = (
        "Never use these phrases: " + ", ".join(f'"{p}"' for p in banned) + "."
        if banned else ""
    )
    lock_str = (
        "BRAND LOCK is on — copy must use the brand voice, never invent competitor "
        "names, and the poster fields must reference the brand palette."
        if brand_lock else ""
    )
    return (
        "You are Pulse Fitness AI Creative Director — a senior marketer, copywriter "
        "and creative strategist for fitness/leisure brands. You think like a "
        "marketer, designer, and strategist combined.\n\n"
        f"Brand voice: {voice_guard}.  Brand palette: {palette}.  {fonts}{lock_str}  "
        f"{banned_str}\n\n"
        "When asked to plan a campaign you ALWAYS reply with a single JSON "
        "object that exactly matches this schema (no markdown fences, no "
        "preamble, no trailing commentary):\n"
        f"{json.dumps(DIRECTOR_SCHEMA)}\n\n"
        "Rules:\n"
        " • Use only the schema keys above.\n"
        " • email.body_html must be inline-styled, mobile-friendly, max ~250 words.\n"
        " • sms.body must be ≤160 chars and include the gym name.\n"
        " • push.body must be ≤90 chars.\n"
        " • Provide exactly 2 alt_tones picked from the user's allowed tone list.\n"
        " • If urgency is unwarranted, do not fake scarcity.\n"
        " • All copy must be UK English.\n"
    )


def _user_prompt(
    *, prompt: str, goal_key: str, tone_key: str, allowed_tones: list[str],
    audience_hint: str, org_name: str, learnings: list[str] | None = None,
) -> str:
    goal = GOAL_PRESETS.get(goal_key, goal_key) or "Drive engagement and conversions."
    tone = TONE_PRESETS.get(tone_key, tone_key) or "high-energy, motivating"
    allowed = ", ".join(allowed_tones) if allowed_tones else ", ".join(TONE_PRESETS.keys())
    learnings_block = ""
    if learnings:
        learnings_block = (
            "\nIMPORTANT — apply these learnings from this org's recent "
            "campaign post-mortems (avoid repeating past mistakes):\n"
            + "\n".join(f"  • {x}" for x in learnings) + "\n"
        )
    return (
        f"Gym/club: {org_name}\n"
        f"Marketing goal: {goal}\n"
        f"Primary tone: {tone_key} ({tone})\n"
        f"User brief: {prompt}\n"
        f"Audience hint (optional): {audience_hint or 'pick the most likely match'}\n"
        f"Allowed alt_tones to choose 2 from: {allowed}\n"
        f"{learnings_block}\n"
        "Return ONLY the JSON object."
    )


async def _fetch_recent_learnings(org_id: str, limit: int = 5) -> list[str]:
    """Pull the most recent post-mortem `next_time_actions` for this org so
    new Director briefs avoid repeating past mistakes (closed-loop learning)."""
    learnings: list[str] = []
    try:
        cursor = db.marketing_campaigns.find(
            {"organization_id": org_id, "post_mortem.report.next_time_actions":
                {"$exists": True, "$ne": []}},
            {"_id": 0, "post_mortem.report.next_time_actions": 1,
             "post_mortem.generated_at": 1},
        ).sort("post_mortem.generated_at", -1).limit(limit)
        async for row in cursor:
            actions = (((row.get("post_mortem") or {}).get("report") or {})
                       .get("next_time_actions") or [])
            for a in actions[:2]:  # at most 2 per past campaign to keep prompt tight
                if isinstance(a, str) and a.strip():
                    learnings.append(a.strip())
                if len(learnings) >= limit * 2:
                    break
            if len(learnings) >= limit * 2:
                break
    except Exception as exc:  # pragma: no cover
        logger.info("[director] learnings lookup skipped: %s", exc)
    # Dedupe while preserving order, cap at limit
    seen: set[str] = set()
    out: list[str] = []
    for item in learnings:
        k = item.lower()[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _strip_to_json(text: str) -> dict:
    """Claude is reliable about returning bare JSON, but defensively pull
    the first {...} block if it sneaks in a fence."""
    t = (text or "").strip()
    if t.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, flags=re.DOTALL)
        if m:
            t = m.group(1)
    # last-resort: find outermost braces
    if not t.startswith("{"):
        i = t.find("{")
        j = t.rfind("}")
        if i >= 0 and j > i:
            t = t[i : j + 1]
    return json.loads(t)


async def _call_claude_director(*, system: str, user: str, session_id: str) -> dict:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI Director unavailable — LLM key not configured")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=session_id, system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        answer = await chat.send_message(UserMessage(text=user))
    except Exception as exc:
        logger.warning("[director] claude call failed: %s", exc)
        raise HTTPException(503, f"AI Director temporarily unavailable: {exc}") from exc
    try:
        return _strip_to_json(answer)
    except Exception as exc:
        logger.warning("[director] JSON parse failed; raw=%s", (answer or "")[:400])
        raise HTTPException(502, f"AI Director returned invalid JSON: {exc}") from exc


async def _call_gemini_poster(
    *,
    prompt_text: str,
    reference_image_b64: list[str],
    width: int,
    height: int,
    session_id: str,
) -> Optional[str]:
    """Generate a branded poster via Gemini Nano Banana with up to 8 refs.
    Returns a data URL or None on any failure (so the caller can fall back)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return None
    try:
        from emergentintegrations.llm.chat import (  # type: ignore
            ImageContent,
            LlmChat,
            UserMessage,
        )
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message="You are a professional fitness/leisure poster artist.",
        ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"],
        )
        msg = UserMessage(
            text=prompt_text + (
                f"\nTarget aspect ratio is {width}:{height}. "
                f"Render text crisply with high contrast."
            ),
            file_contents=[ImageContent(b) for b in reference_image_b64[:8]] or None,
        )
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            return None
        first = images[0]
        return f"data:{first.get('mime_type', 'image/png')};base64,{first['data']}"
    except Exception as exc:  # pragma: no cover
        logger.info("[director] gemini poster gen failed: %s", exc)
        return None


async def _resolve_brand_assets_b64(org_id: str, brand_lock: bool) -> list[str]:
    """Pull the org's brand-kit logo (as base64) when brand_lock is on so
    Gemini can pixel-composite it onto the poster."""
    if not brand_lock:
        return []
    out: list[str] = []
    try:
        # ➤ logo first (from marketing_brand_kit.primary_logo_data_url, if any)
        bk = await db.marketing_brand_kit.find_one(
            {"organization_id": org_id}, {"_id": 0, "primary_logo_data_url": 1},
        ) or {}
        durl = bk.get("primary_logo_data_url") or ""
        if durl.startswith("data:") and "," in durl:
            out.append(durl.split(",", 1)[1])
        else:
            # ➤ fallback: org.logo_url uploaded during onboarding — fetch + base64.
            # This means brand-locked posters auto-use the operator's onboarding
            # logo even before they touch the Brand Kit tab.
            org_doc = await db.organizations.find_one(
                {"id": org_id},
                {"_id": 0, "logo_url": 1, "branding": 1},
            ) or {}
            url = org_doc.get("logo_url") or (org_doc.get("branding") or {}).get("logo_url")
            if url and isinstance(url, str) and url.startswith(("http://", "https://")):
                try:
                    import httpx
                    import base64 as _b64
                    async with httpx.AsyncClient(timeout=8.0) as cx:
                        r = await cx.get(url)
                        if r.status_code == 200 and r.content:
                            out.append(_b64.b64encode(r.content).decode("ascii"))
                except Exception as exc:
                    logger.info("[director] org logo_url fetch skipped: %s", exc)
        # ➤ then up to 2 most-recent user-uploaded brand assets
        async for asset in db.marketing_creative_assets.find(
            {"organization_id": org_id, "type": "user_upload",
             "category": {"$in": ["logo", "brand", "campaign_face"]}},
            {"_id": 0, "data_url": 1},
        ).sort("created_at", -1).limit(2):
            d = asset.get("data_url") or ""
            if d.startswith("data:") and "," in d:
                out.append(d.split(",", 1)[1])
    except Exception as exc:  # pragma: no cover
        logger.info("[director] brand assets lookup skipped: %s", exc)
    return out[:8]


# ───────────────────────── Endpoints ─────────────────────────


@router.post(
    "/marketing/creative/director/build",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_build(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Single prompt → full campaign brief.

    Body:
      {
        prompt: str,                 # natural-language brief
        goal: str?,                  # one of GOAL_PRESETS keys
        tone: str?,                  # one of TONE_PRESETS keys
        allowed_tones: [str]?,       # subset to draw alt_tones from
        audience_hint: str?,         # free-text hint
        brand_lock: bool?,           # default true
        resolution: {w, h}?,         # default 1080x1350 (IG portrait)
        skip_image: bool?,           # debug — skip Gemini call
        segment_keys: [str]?,        # Phase 3 — generate per-segment variants
                                     # any of: lapsed_30d, active_regulars,
                                     # new_members_30d, pt_eligible,
                                     # off_peak_visitors, frozen_members
        seed_brief_id: str?,         # Phase 4 — seed from an existing asset
      }

    Response:
      { brief_id, strategy{}, copy{}, alt_tones[], poster_url,
        segment_variants[]?, segment_counts{}? }
    """
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "User has no organization context")

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")

    goal_key = (body.get("goal") or "").strip()
    tone_key = (body.get("tone") or "high_energy").strip()
    allowed = body.get("allowed_tones") or list(TONE_PRESETS.keys())
    audience_hint = (body.get("audience_hint") or "").strip()
    brand_lock = bool(body.get("brand_lock", True))
    res = body.get("resolution") or {}
    width = int(res.get("w") or 1080)
    height = int(res.get("h") or 1350)
    skip_image = bool(body.get("skip_image"))

    # Resolve org name + brand kit for the system prompt
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    brand_kit = await db.marketing_brand_kit.find_one({"organization_id": org_id}, {"_id": 0}) or {}

    session_id = f"director-{org_id}-{_new_id()[:8]}"
    learnings = await _fetch_recent_learnings(org_id)
    plan = await _call_claude_director(
        system=_system_prompt(brand_kit, brand_lock),
        user=_user_prompt(
            prompt=prompt, goal_key=goal_key, tone_key=tone_key,
            allowed_tones=allowed, audience_hint=audience_hint,
            org_name=org.get("name") or "your gym",
            learnings=learnings,
        ),
        session_id=session_id,
    )

    poster_url: Optional[str] = None
    if not skip_image:
        copy = (plan.get("copy") or {}).get("poster") or {}
        head = copy.get("headline") or plan.get("strategy", {}).get("summary", "")[:60]
        sub = copy.get("subheadline") or ""
        cta = copy.get("cta") or ""
        palette = (
            f"primary {brand_kit.get('primary_color', '#0055FF')}, "
            f"secondary {brand_kit.get('secondary_color', '#66CCFF')}"
        )
        accent = brand_kit.get('accent_color')
        if accent:
            palette += f", accent {accent}"
        # Iter 216h113i — feed the brand kit's fonts into the
        # poster prompt so Gemini renders headline/body type in the
        # customer's brand identity rather than a generic sans-serif.
        font_heading = brand_kit.get('font_heading')
        font_body = brand_kit.get('font_body')
        type_hint = ""
        if font_heading:
            type_hint = (
                f"Render the headline in '{font_heading}' (or a similar "
                f"display face if not available). "
            )
        if font_body:
            type_hint += (
                f"Render body / supporting copy in '{font_body}' (or a "
                f"similar neutral sans-serif if not available). "
            )
        poster_prompt = (
            f"Design a high-impact gym/leisure marketing poster for: {prompt}. "
            f"Render the headline '{head}' at the top in bold display type, "
            f"subheadline '{sub}' below, and CTA button text '{cta}'. "
            f"{type_hint}"
            f"Use the brand palette ({palette}) for accents and overlays. "
            f"Cinematic lighting, sharp focus, premium fitness aesthetic. "
            f"{'Composite the supplied brand logo prominently in the bottom-right corner with a soft shadow.' if brand_lock else ''}"
        )
        ref_b64 = await _resolve_brand_assets_b64(org_id, brand_lock)
        poster_url = await _call_gemini_poster(
            prompt_text=poster_prompt,
            reference_image_b64=ref_b64,
            width=width, height=height,
            session_id=session_id + "-img",
        )

    brief_id = _new_id()
    doc = {
        "id": brief_id,
        "organization_id": org_id,
        "created_by": user["id"],
        "prompt": prompt,
        "goal": goal_key,
        "tone": tone_key,
        "audience_hint": audience_hint,
        "brand_lock": brand_lock,
        "resolution": {"w": width, "h": height},
        "strategy": plan.get("strategy") or {},
        "copy": plan.get("copy") or {},
        "alt_tones": plan.get("alt_tones") or [],
        "poster_data_url": poster_url,
        "poster_model": "gemini-3.1-flash-image-preview" if poster_url else None,
        "campaign_id": None,
        "created_at": _now_iso(),
        "refined_count": 0,
        "learnings_applied": learnings,
    }

    # ── Phase 3: Behaviour-driven per-segment variants ──────────────
    segment_keys = [k for k in (body.get("segment_keys") or [])
                    if k in SEGMENT_DESCRIPTORS]
    if segment_keys:
        segment_counts = await _resolve_segment_counts(org_id, segment_keys)
        variants = await _generate_segment_variants(
            prompt=prompt, base_brief=plan, org_name=org.get("name") or "your gym",
            brand_kit=brand_kit, brand_lock=brand_lock,
            segment_keys=segment_keys, session_id=session_id + "-seg",
        )
        # Attach friendly labels + counts for the UI
        labelled: list[dict] = []
        for v in variants:
            sk = v.get("segment_key")
            desc = SEGMENT_DESCRIPTORS.get(sk) or {}
            labelled.append({
                **v,
                "segment_label": desc.get("label", sk),
                "audience_count": segment_counts.get(sk, 0),
                "behaviour": desc.get("behaviour", ""),
            })
        doc["segment_variants"] = labelled
        doc["segment_counts"] = segment_counts

    await db.marketing_director_briefs.insert_one(doc)

    # Don't return the full base64 poster in this response if the data URL
    # is huge — but for now the frontend wants it. Strip the _id only.
    return {k: v for k, v in doc.items() if k != "_id"}


@router.post(
    "/marketing/creative/director/refine",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_refine(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """One-click "make it better" refinement.

    Body: { brief_id, instruction, channel?, regenerate_image?: bool }
      instruction examples:
        "make it punchier"  "add urgency"  "less salesy"
        "shorten the email" "more premium tone" "highlight the offer"
    """
    org_id = user.get("organization_id")
    brief_id = (body.get("brief_id") or "").strip()
    instruction = (body.get("instruction") or "").strip()
    channel = (body.get("channel") or "").strip().lower() or None
    regen_image = bool(body.get("regenerate_image"))
    if not brief_id or not instruction:
        raise HTTPException(400, "brief_id and instruction are required")

    brief = await db.marketing_director_briefs.find_one(
        {"id": brief_id, "organization_id": org_id}, {"_id": 0},
    )
    if not brief:
        raise HTTPException(404, "Brief not found")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    brand_kit = await db.marketing_brand_kit.find_one({"organization_id": org_id}, {"_id": 0}) or {}

    # Ask Claude to mutate the existing brief.
    system = _system_prompt(brand_kit, bool(brief.get("brand_lock", True)))
    target = (
        f"the {channel} copy block only" if channel else "every channel where it makes sense"
    )
    user_msg = (
        f"Here is the existing brief JSON for {org.get('name') or 'this gym'}:\n"
        f"{json.dumps({'strategy': brief['strategy'], 'copy': brief['copy'], 'alt_tones': brief['alt_tones']})}\n\n"
        f"Refinement instruction: {instruction}\n"
        f"Apply the refinement to {target}. Keep all unchanged fields exactly the same. "
        "Return the FULL JSON in the same schema."
    )
    new_plan = await _call_claude_director(
        system=system, user=user_msg, session_id=f"refine-{brief_id}",
    )

    poster_url = brief.get("poster_data_url")
    if regen_image:
        copy = (new_plan.get("copy") or {}).get("poster") or {}
        head = copy.get("headline") or ""
        sub = copy.get("subheadline") or ""
        cta = copy.get("cta") or ""
        poster_prompt = (
            f"Refine the previous fitness poster for: {brief['prompt']}. "
            f"New headline '{head}', subheadline '{sub}', CTA '{cta}'. "
            f"{instruction.capitalize()}. "
            "Premium fitness aesthetic, sharp typography, cinematic."
        )
        ref_b64 = await _resolve_brand_assets_b64(org_id, bool(brief.get("brand_lock")))
        regenerated = await _call_gemini_poster(
            prompt_text=poster_prompt,
            reference_image_b64=ref_b64,
            width=int(brief.get("resolution", {}).get("w") or 1080),
            height=int(brief.get("resolution", {}).get("h") or 1350),
            session_id=f"refine-img-{brief_id}-{_new_id()[:6]}",
        )
        if regenerated:
            poster_url = regenerated

    update = {
        "strategy": new_plan.get("strategy") or brief["strategy"],
        "copy": new_plan.get("copy") or brief["copy"],
        "alt_tones": new_plan.get("alt_tones") or brief["alt_tones"],
        "poster_data_url": poster_url,
        "refined_count": int(brief.get("refined_count", 0)) + 1,
        "last_refined_at": _now_iso(),
        "last_refinement": instruction,
    }
    await db.marketing_director_briefs.update_one({"id": brief_id}, {"$set": update})
    brief.update(update)
    return {k: v for k, v in brief.items() if k != "_id"}


@router.get(
    "/marketing/creative/director/briefs",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_briefs_list(user: dict = Depends(get_current_user)):
    org_id = user.get("organization_id")
    rows = await db.marketing_director_briefs.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "prompt": 1, "goal": 1, "tone": 1, "strategy": 1,
         "campaign_id": 1, "created_at": 1, "refined_count": 1},
    ).sort("created_at", -1).to_list(50)
    return {"briefs": rows}


@router.get(
    "/marketing/creative/director/briefs/{brief_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_brief_get(brief_id: str, user: dict = Depends(get_current_user)):
    org_id = user.get("organization_id")
    doc = await db.marketing_director_briefs.find_one(
        {"id": brief_id, "organization_id": org_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Brief not found")
    return doc


@router.delete(
    "/marketing/creative/director/briefs/{brief_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_brief_delete(brief_id: str, user: dict = Depends(get_current_user)):
    """Delete an old Director brief from history. Spent LLM cost is not
    refunded — this is purely a tidy-up. Linked campaigns are left intact
    (they continue to live in the campaigns list and can be deleted from
    there if no longer wanted)."""
    org_id = user.get("organization_id")
    res = await db.marketing_director_briefs.delete_one(
        {"id": brief_id, "organization_id": org_id},
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Brief not found")
    return {"ok": True, "deleted": brief_id}


@router.post(
    "/marketing/creative/director/briefs/{brief_id}/launch",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_brief_launch(
    brief_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user),
):
    """Convert a Director brief into an editable Campaign + Creative asset.
    Wires the brief's email block + poster into a real campaign that the
    user can review and send via the existing /marketing/campaigns flow.

    Body (optional):
      auto_pilot: bool                — schedule the send for the optimal
                                        window + run an auto post-mortem
                                        72h after send
      auto_post_mortem: bool          — opt into the 72h post-mortem run
                                        even when not full autopilot
      audience_id: str                — link to a saved audience
    """
    org_id = user.get("organization_id")
    doc = await db.marketing_director_briefs.find_one(
        {"id": brief_id, "organization_id": org_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Brief not found")
    if doc.get("campaign_id"):
        return {"campaign_id": doc["campaign_id"], "already_launched": True}

    email = (doc.get("copy") or {}).get("email") or {}
    audience_id = (body.get("audience_id") or "").strip() or None
    auto_pilot = bool(body.get("auto_pilot"))
    auto_post_mortem = bool(body.get("auto_post_mortem", auto_pilot))
    per_recipient = bool(body.get("per_recipient_timing"))

    # ── Autopilot scheduling ────────────────────────────────────────
    status = "draft"
    scheduled_for: Optional[str] = None
    optimal: Optional[dict] = None
    if auto_pilot:
        from utils.marketing_autopilot import (
            compute_optimal_send_window, next_window_iso,
        )
        optimal = await compute_optimal_send_window(org_id)
        scheduled_for = next_window_iso(optimal["weekday"], optimal["hour"])
        status = "scheduled"

    campaign_id = _new_id()
    await db.marketing_campaigns.insert_one({
        "id": campaign_id,
        "organization_id": org_id,
        "name": (doc.get("strategy") or {}).get("summary", "AI Director Campaign")[:80],
        "status": status,
        "channel": "email",
        "subject": email.get("subject") or "",
        "preheader": email.get("preheader") or "",
        "body_html": email.get("body_html") or "",
        "audience_id": audience_id,
        "from_brief_id": brief_id,
        "scheduled_for": scheduled_for,
        "auto_pilot": {
            "enabled": auto_pilot,
            "auto_post_mortem": auto_post_mortem,
            "per_recipient_timing": per_recipient,
            "optimal_window": optimal,
        } if auto_pilot or auto_post_mortem or per_recipient else None,
        "created_by": user["id"],
        "created_at": _now_iso(),
    })

    # Persist the poster as a marketing_creative_asset so it shows in the
    # asset library too.
    poster_asset_id = None
    if doc.get("poster_data_url"):
        poster_asset_id = _new_id()
        poster = (doc.get("copy") or {}).get("poster") or {}
        await db.marketing_creative_assets.insert_one({
            "id": poster_asset_id,
            "organization_id": org_id,
            "created_by": user["id"],
            "type": "poster",
            "prompt": doc.get("prompt"),
            "headline": poster.get("headline"),
            "subheadline": poster.get("subheadline"),
            "call_to_action": poster.get("cta"),
            "brand_lock": bool(doc.get("brand_lock")),
            "brand_kit_applied": True,
            "source": doc.get("poster_model") or "gemini-3.1-flash-image-preview",
            "variants": [{"url": doc["poster_data_url"], "model": doc.get("poster_model")}],
            "from_brief_id": brief_id,
            "created_at": _now_iso(),
        })

    await db.marketing_director_briefs.update_one(
        {"id": brief_id},
        {"$set": {"campaign_id": campaign_id, "poster_asset_id": poster_asset_id,
                  "launched_at": _now_iso()}},
    )
    return {"campaign_id": campaign_id, "poster_asset_id": poster_asset_id,
            "status": status, "scheduled_for": scheduled_for,
            "optimal_window": optimal}


@router.get(
    "/marketing/creative/director/presets",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_presets(_user: dict = Depends(get_current_user)):
    """Tones + goal presets for the UI."""
    return {
        "tones": [{"key": k, "label": k.replace("_", " ").title(), "hint": v}
                  for k, v in TONE_PRESETS.items()],
        "goals": [{"key": k, "label": v} for k, v in GOAL_PRESETS.items()],
        "channels": CHANNELS,
    }


@router.get(
    "/marketing/creative/director/optimal-window",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_optimal_window(user: dict = Depends(get_current_user)):
    """Best send day + hour for this org based on the last 90 days of
    open-rate-per-bucket history. Falls back to "Tuesday 18:00" when
    there's not enough data yet."""
    org_id = user.get("organization_id")
    from utils.marketing_autopilot import compute_optimal_send_window
    return await compute_optimal_send_window(org_id)


@router.get(
    "/marketing/creative/director/per-recipient-coverage",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_per_recipient_coverage(user: dict = Depends(get_current_user)):
    """Returns how many of this org's members have enough personal email-open
    history (≥3 opens in the last 180 days) to be sent at their personal best
    hour, vs how many will fall back to the org-level optimal window."""
    org_id = user.get("organization_id")
    try:
        emails = await db.members.distinct("email", {"organization_id": org_id})
    except Exception:
        emails = []
    emails = [e for e in emails if e]
    from utils.marketing_autopilot import compute_per_recipient_windows
    if not emails:
        return {"total_members": 0, "personal": 0, "fallback": 0}
    coverage = await compute_per_recipient_windows(org_id, emails)
    personal = sum(1 for v in coverage.values() if v.get("source") == "personal")
    return {
        "total_members": len(emails),
        "personal": personal,
        "fallback": len(emails) - personal,
        "coverage_pct": round(personal / len(emails) * 100, 1) if emails else 0,
    }


# ───────────────────────── Phase 3: Segments ─────────────────────────


SEGMENT_DESCRIPTORS: dict[str, dict] = {
    "lapsed_30d": {
        "label": "Lapsed members (30+ days)",
        "behaviour": "Hasn't visited in 30+ days, plan still active",
        "tone_hint": "warm, missed-you, low-pressure invite",
        "lever": "remove friction; remind them what they loved",
    },
    "active_regulars": {
        "label": "Active regulars",
        "behaviour": "Visits 3+ times per week, plan active",
        "tone_hint": "challenge-mindset, level-up, insider",
        "lever": "raise the bar; offer the next thing (PT, advanced class)",
    },
    "new_members_30d": {
        "label": "New members (joined 30 days ago)",
        "behaviour": "Joined 14-30 days ago, learning the ropes",
        "tone_hint": "encouraging, coaching, congratulatory",
        "lever": "celebrate momentum; remove first-month wobble",
    },
    "pt_eligible": {
        "label": "PT-eligible members",
        "behaviour": "Visits regularly but no PT bookings yet",
        "tone_hint": "expert-coach, results-focused, premium",
        "lever": "show the upgrade path; first-session try-out",
    },
    "off_peak_visitors": {
        "label": "Off-peak attendees",
        "behaviour": "Most visits before 10am or after 7pm",
        "tone_hint": "exclusive, quiet-hours, focused",
        "lever": "lean into the calm-vibe & no-queue advantage",
    },
    "frozen_members": {
        "label": "Frozen memberships",
        "behaviour": "On a freeze right now, paying nothing or partial",
        "tone_hint": "gentle, no-pressure return, ready-when-you-are",
        "lever": "make unfreezing trivial; offer one-click reactivation",
    },
}


async def _resolve_segment_counts(org_id: str, segment_keys: list[str]) -> dict[str, int]:
    """Best-effort live counts. Falls back to 0 when fields aren't populated."""
    out: dict[str, int] = {}
    if not segment_keys:
        return out
    now = datetime.now(timezone.utc)
    thirty_ago = now - timedelta(days=30)
    fourteen_ago = now - timedelta(days=14)
    try:
        for key in segment_keys:
            q: dict
            if key == "lapsed_30d":
                q = {"organization_id": org_id, "status": "active",
                     "$or": [{"last_visit_at": {"$lt": thirty_ago.isoformat()}},
                             {"last_visit_at": {"$exists": False}}]}
            elif key == "active_regulars":
                q = {"organization_id": org_id, "status": "active",
                     "visits_30d": {"$gte": 12}}
            elif key == "new_members_30d":
                q = {"organization_id": org_id, "status": "active",
                     "joined_at": {"$gte": thirty_ago.isoformat(),
                                   "$lt": fourteen_ago.isoformat()}}
            elif key == "pt_eligible":
                q = {"organization_id": org_id, "status": "active",
                     "pt_eligible": True}
            elif key == "off_peak_visitors":
                q = {"organization_id": org_id, "status": "active",
                     "off_peak_share": {"$gte": 0.6}}
            elif key == "frozen_members":
                q = {"organization_id": org_id, "status": "frozen"}
            else:
                continue
            out[key] = await db.members.count_documents(q)
    except Exception as exc:  # pragma: no cover
        logger.info("[director] segment count failed: %s", exc)
    return out


SEGMENT_VARIANT_SCHEMA = [{
    "segment_key": "key from list",
    "headline": "...", "email_subject": "...", "email_body_html": "...",
    "sms": "≤160 chars", "push_title": "...", "push_body": "≤90 chars",
    "instagram_caption": "...", "lever_used": "1-line reasoning",
}]


async def _generate_segment_variants(
    *, prompt: str, base_brief: dict, org_name: str, brand_kit: dict,
    brand_lock: bool, segment_keys: list[str], session_id: str,
) -> list[dict]:
    """Ask Claude to produce per-segment copy variants in one shot."""
    selected = [{**SEGMENT_DESCRIPTORS[k], "key": k}
                for k in segment_keys if k in SEGMENT_DESCRIPTORS]
    if not selected:
        return []
    sys = _system_prompt(brand_kit, brand_lock)
    user = (
        f"Gym/club: {org_name}\n"
        f"Original brief: {prompt}\n"
        f"Master strategy: {json.dumps(base_brief.get('strategy') or {})}\n\n"
        "For each of the segments below, produce a tailored copy variant "
        "that uses the segment's specific behaviour as the hook. Return "
        f"a single JSON array matching this schema:\n{json.dumps(SEGMENT_VARIANT_SCHEMA)}\n\n"
        "Segments:\n" + "\n".join(
            f"- {s['key']}: {s['label']} — {s['behaviour']}. "
            f"Tone: {s['tone_hint']}. Lever: {s['lever']}." for s in selected
        ) + "\n\nReturn ONLY the JSON array."
    )
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return []
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(api_key=api_key, session_id=session_id, system_message=sys
                       ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text=user))
        # Pull the JSON array
        t = (resp or "").strip()
        if t.startswith("```"):
            m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", t, flags=re.DOTALL)
            if m:
                t = m.group(1)
        if not t.startswith("["):
            i = t.find("[")
            j = t.rfind("]")
            if i >= 0 and j > i:
                t = t[i : j + 1]
        return json.loads(t)
    except Exception as exc:  # pragma: no cover
        logger.warning("[director] segment variant gen failed: %s", exc)
        return []


# ───────────────────────── Phase 4: Content → Campaign ─────────────────────────


@router.post(
    "/marketing/creative/director/expand-from-asset/{asset_id}",
    dependencies=[Depends(require_module("marketing"))],
)
async def director_expand_from_asset(
    asset_id: str, body: dict = Body(default={}), user: dict = Depends(get_current_user),
):
    """Take an existing creative asset (poster/social_post/email_hero) and
    expand it into a full Director brief — multi-format copy + strategy +
    optionally regenerate the poster. The asset's headline / sub-headline /
    CTA / prompt / category are used as the seed."""
    org_id = user.get("organization_id")
    asset = await db.marketing_creative_assets.find_one(
        {"id": asset_id, "organization_id": org_id}, {"_id": 0},
    )
    if not asset:
        raise HTTPException(404, "Asset not found")

    seed_prompt = (
        asset.get("prompt")
        or asset.get("headline")
        or asset.get("label")
        or "Promote this campaign"
    )
    if asset.get("headline"):
        seed_prompt = (
            f"{seed_prompt}. Headline: '{asset['headline']}'"
            f"{' Sub-headline: ' + asset['subheadline'] if asset.get('subheadline') else ''}"
            f"{'. CTA: ' + asset['call_to_action'] if asset.get('call_to_action') else ''}"
        )

    new_body = {
        "prompt": seed_prompt,
        "goal": body.get("goal") or "promote_class",
        "tone": body.get("tone") or "high_energy",
        "brand_lock": bool(asset.get("brand_lock", True)),
        "skip_image": True,  # use the existing asset's image as the poster
        "segment_keys": body.get("segment_keys") or [],
    }
    # Reuse the build flow
    result = await director_build(body=new_body, user=user)

    # Stitch the existing poster into the brief
    poster_url = None
    variants = asset.get("variants") or []
    if variants:
        poster_url = variants[0].get("url")
    if poster_url:
        await db.marketing_director_briefs.update_one(
            {"id": result["id"]},
            {"$set": {"poster_data_url": poster_url,
                      "poster_model": asset.get("source") or "user_upload",
                      "from_asset_id": asset_id}},
        )
        result["poster_data_url"] = poster_url
        result["poster_model"] = asset.get("source") or "user_upload"
        result["from_asset_id"] = asset_id
    return result


# ───────────────────────── Phase 5: AI Post-mortem ─────────────────────────


@router.get(
    "/marketing/campaigns/{campaign_id}/post-mortem",
    dependencies=[Depends(require_module("marketing"))],
)
async def campaign_post_mortem(
    campaign_id: str, user: dict = Depends(get_current_user),
):
    """Read campaign metrics + 90-day org baseline + recent winners → ask
    Claude for a concrete next-time critique. Cached on the campaign doc."""
    org_id = user.get("organization_id")
    camp = await db.marketing_campaigns.find_one(
        {"id": campaign_id, "organization_id": org_id}, {"_id": 0},
    )
    if not camp:
        raise HTTPException(404, "Campaign not found")

    metrics = camp.get("metrics") or {}
    sent = int(metrics.get("sent") or 0)
    if sent <= 0:
        raise HTTPException(
            400, "Campaign hasn't been sent yet — post-mortem is unavailable",
        )

    # 90-day baseline across this org's sent campaigns
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    baseline_pipe = [
        {"$match": {"organization_id": org_id, "status": "sent",
                    "sent_at": {"$gte": cutoff.isoformat()}}},
        {"$group": {
            "_id": None,
            "n": {"$sum": 1},
            "avg_open": {"$avg": {"$cond": [
                {"$gt": ["$metrics.sent", 0]},
                {"$divide": ["$metrics.opened", "$metrics.sent"]},
                0,
            ]}},
            "avg_click": {"$avg": {"$cond": [
                {"$gt": ["$metrics.opened", 0]},
                {"$divide": ["$metrics.clicked", "$metrics.opened"]},
                0,
            ]}},
        }},
    ]
    baseline = {"avg_open": None, "avg_click": None, "n": 0}
    async for row in db.marketing_campaigns.aggregate(baseline_pipe):
        baseline = {"avg_open": row.get("avg_open"),
                    "avg_click": row.get("avg_click"),
                    "n": int(row.get("n") or 0)}

    # 3 best-performing campaigns of last 90 days for "winner pattern" context
    winners_cursor = db.marketing_campaigns.find(
        {"organization_id": org_id, "status": "sent",
         "sent_at": {"$gte": cutoff.isoformat()}, "metrics.opened": {"$gt": 0}},
        {"_id": 0, "subject": 1, "metrics": 1, "sent_at": 1},
    ).sort("metrics.opened", -1).limit(3)
    winners: list[dict] = await winners_cursor.to_list(3)

    open_rate = (metrics.get("opened") or 0) / sent if sent else 0
    click_rate = ((metrics.get("clicked") or 0) / metrics["opened"]
                  if metrics.get("opened") else 0)

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Post-mortem unavailable — LLM key not configured")

    sys = (
        "You are Pulse Fitness AI Creative Director performing a campaign "
        "post-mortem. Be specific, concrete, and actionable. Use UK English. "
        "Always respond as a single JSON object with this schema:\n"
        "{ headline_score: 'A|B|C|D|F', summary: '1-2 sentences', "
        "open_rate_critique: '...', click_rate_critique: '...', "
        "subject_line_critique: '...', timing_critique: '...', "
        "next_time_actions: [ '...', '...', '...' ], "
        "winning_pattern_match: 'is this campaign aligned with recent "
        "winners? brief reasoning' }"
    )
    user_msg = (
        f"Campaign subject: {camp.get('subject') or '(none)'}\n"
        f"Sent: {camp.get('sent_at') or 'unknown'} · Recipients: {sent}\n"
        f"Open rate: {open_rate*100:.1f}% (delivered {metrics.get('delivered',0)})\n"
        f"Click rate (of opens): {click_rate*100:.1f}% "
        f"({metrics.get('clicked', 0)} clicks)\n"
        f"Bounces: {metrics.get('bounced', 0)} · "
        f"Unsubscribes: {metrics.get('unsubscribed', 0)}\n\n"
        f"Org 90-day baseline (n={baseline['n']}): "
        f"open {((baseline['avg_open'] or 0)*100):.1f}% · "
        f"click {((baseline['avg_click'] or 0)*100):.1f}%\n\n"
        f"Top 3 recent winners by opens:\n"
        + "\n".join(
            f"- '{w.get('subject')}' opened {w.get('metrics',{}).get('opened',0)} "
            f"of {w.get('metrics',{}).get('sent',0)}"
            for w in winners
        )
        + "\n\nReturn ONLY the JSON object."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=f"postmortem-{campaign_id}",
            system_message=sys,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_msg))
        report = _strip_to_json(raw)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[postmortem] claude failed: %s", exc)
        raise HTTPException(503, f"Post-mortem temporarily unavailable: {exc}") from exc

    payload = {
        "campaign_id": campaign_id,
        "subject": camp.get("subject"),
        "sent_at": camp.get("sent_at"),
        "metrics": {**metrics, "open_rate": open_rate, "click_rate": click_rate},
        "baseline": baseline,
        "winners": winners,
        "report": report,
        "generated_at": _now_iso(),
    }
    # Cache on the campaign doc so re-opens are instant
    await db.marketing_campaigns.update_one(
        {"id": campaign_id, "organization_id": org_id},
        {"$set": {"post_mortem": payload}},
    )
    return payload


# ───────────────────────── Phase 6: True 1:1 Churn-risk Rescue ─────────────────────────


CHURN_RESCUE_SCHEMA = {
    "email_subject":   "Specific subject line referencing the member's exact signal",
    "email_preheader": "Inbox preview line — empathetic, not salesy",
    "email_body_html": ("Inline-styled, mobile-friendly HTML using {{first_name}} "
                        "merge token. Max ~180 words. Reference the SPECIFIC "
                        "behaviour signal naturally."),
    "sms_body":        "≤160 chars; mention the specific signal in human language",
    "push_title":      "≤40 chars",
    "push_body":       "≤90 chars",
    "in_app_message":  "≤180 chars warm note for the member portal",
    "primary_channel": "one of: email, sms, push, in_app",
    "fallback_channel":"second-best channel if primary not deliverable",
    "expected_lever":  "One-line summary of why this should win them back",
}


async def _generate_personal_rescue_copy(
    *, target: dict, org_name: str, brand_kit: dict, brand_lock: bool,
    session_id: str,
) -> dict:
    """One Claude call → per-member rescue copy across email/sms/push/in_app
    that references the member's exact exit signal."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Churn rescue unavailable — LLM key not configured")

    sys = (
        "You are Pulse Fitness AI Creative Director writing a HYPER-personalised "
        "win-back message to a single specific member. Be empathetic, "
        "specific, and never salesy. Use UK English. ALWAYS reply with a "
        "single JSON object that exactly matches this schema (no markdown, "
        "no preamble):\n"
        f"{json.dumps(CHURN_RESCUE_SCHEMA)}\n\n"
        "Hard rules:\n"
        " • The email body MUST reference the exact signal evidence given — "
        "name the class by name when provided, name the day count when "
        "provided. Do NOT invent details.\n"
        " • Tone: warm, low-pressure, member-first. We're not selling, we're "
        "reaching out because we noticed.\n"
        " • Never mention 'churn', 'risk', 'lapsed', 'win-back' — these are "
        "internal labels.\n"
        " • Use the {{first_name}} merge token in copy that needs the name; "
        "do not hard-code the name.\n"
        " • email_body_html ≤180 words, mobile-friendly inline styles only.\n"
        " • sms_body ≤160 chars; push_body ≤90 chars; push_title ≤40 chars.\n"
        " • Never offer a discount unless the signal warrants it (payment_failure "
        "or frozen_membership only); for everything else, offer a moment of "
        "human connection or a flexible reschedule.\n"
    )
    voice_guard = brand_kit.get("voice") or "professional, energetic, gym-friendly"
    palette = (
        f"primary {brand_kit.get('primary_color', '#0055FF')}, "
        f"secondary {brand_kit.get('secondary_color', '#66CCFF')}"
    )

    user_msg = (
        f"Gym/club: {org_name}\n"
        f"Brand voice: {voice_guard}. Palette: {palette}.\n"
        f"{'BRAND LOCK on — keep voice consistent.' if brand_lock else ''}\n\n"
        f"Member context:\n"
        f"  • Name (use as merge token): {target.get('first_name') or 'there'}\n"
        f"  • Tenure: {target.get('tenure_days', 0)} days as a member\n"
        f"  • Lifetime value: £{target.get('lifetime_value_gbp', 0):.2f}\n"
        f"  • Days since last visit: {target.get('days_since_last_visit', 'unknown')}\n"
        f"  • Visits last 14d: {target.get('visits_14d', 0)}\n"
        f"  • Visits in days 14-28: {target.get('visits_14_28d', 0)}\n"
        f"  • Favourite class (if any): {target.get('last_class_name') or 'unknown'}\n\n"
        f"DETECTED EXIT SIGNAL: {target.get('signal_label')}\n"
        f"EVIDENCE TO REFERENCE: {target.get('signal_evidence')}\n"
        f"RECOMMENDED LEVER: {target.get('primary_recommendation')}\n\n"
        "Write the rescue copy now. The email body must reference the "
        "evidence specifically — the goal is for the member to feel SEEN. "
        "Return ONLY the JSON object."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=session_id, system_message=sys,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_msg))
        return _strip_to_json(raw)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.warning("[churn-rescue] claude failed for %s: %s",
                       target.get("member_id"), exc)
        raise HTTPException(503, f"Rescue copy temporarily unavailable: {exc}") from exc


@router.get(
    "/marketing/creative/director/churn-risk/scan",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_scan(
    limit: int = 50, user: dict = Depends(get_current_user),
):
    """Scan the org's active members for behavioural exit signals. Returns
    the top `limit` at-risk members with the EXACT signal that triggered,
    not just a generic risk score. Drives the AI Director's 1:1 rescue
    queue — one row per member, ready to be turned into bespoke copy."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "User has no organization context")
    limit = max(1, min(int(limit or 50), 200))
    targets = await detect_churn_signals(org_id, limit=limit)

    # Mark those who already have a pending rescue queued so the UI can
    # disable re-generation and show a status chip.
    if targets:
        existing_ids = {t["member_id"] for t in targets}
        async for r in db.marketing_churn_rescues.find(
            {"organization_id": org_id, "member_id": {"$in": list(existing_ids)},
             "status": {"$in": ["pending_approval", "approved", "scheduled"]}},
            {"_id": 0, "member_id": 1, "id": 1, "status": 1},
        ):
            for t in targets:
                if t["member_id"] == r["member_id"]:
                    t["existing_rescue_id"] = r["id"]
                    t["existing_rescue_status"] = r["status"]
                    break

    return {
        "targets": targets,
        "count": len(targets),
        "signal_labels": CHURN_SIGNAL_LABELS,
        "scanned_at": _now_iso(),
    }


@router.post(
    "/marketing/creative/director/churn-risk/generate",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_generate(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Generate per-member 1:1 rescue copy via Claude for the supplied
    member_ids. Each row goes to the queue with status `pending_approval`
    awaiting staff sign-off (per user choice 2b — Queue for staff approval).

    Body:
      { member_ids: [str, ...], brand_lock?: bool }

    Response:
      { rescues: [...], count: int, failed: [...] }
    """
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "User has no organization context")
    member_ids = [m for m in (body.get("member_ids") or []) if isinstance(m, str)]
    if not member_ids:
        raise HTTPException(400, "member_ids is required")
    if len(member_ids) > 50:
        raise HTTPException(400, "Generate at most 50 rescues at a time")
    brand_lock = bool(body.get("brand_lock", True))

    # Re-scan and filter to the supplied members so the signals reflect
    # the *current* member state at generation time.
    all_targets = await detect_churn_signals(org_id, limit=500)
    by_id = {t["member_id"]: t for t in all_targets}
    selected = [by_id[mid] for mid in member_ids if mid in by_id]
    if not selected:
        raise HTTPException(
            400,
            "None of the supplied member_ids currently match a churn signal",
        )

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "name": 1},
    ) or {}
    brand_kit = await db.marketing_brand_kit.find_one(
        {"organization_id": org_id}, {"_id": 0},
    ) or {}

    rescues_created: list[dict] = []
    failed: list[dict] = []
    for target in selected:
        # Skip if member already has an active rescue in the queue
        existing = await db.marketing_churn_rescues.find_one(
            {"organization_id": org_id, "member_id": target["member_id"],
             "status": {"$in": ["pending_approval", "approved", "scheduled"]}},
            {"_id": 0, "id": 1, "status": 1},
        )
        if existing:
            failed.append({
                "member_id": target["member_id"],
                "reason": f"Already has a {existing['status']} rescue ({existing['id']})",
            })
            continue
        try:
            copy = await _generate_personal_rescue_copy(
                target=target,
                org_name=org.get("name") or "your gym",
                brand_kit=brand_kit, brand_lock=brand_lock,
                session_id=f"churn-{target['member_id']}-{_new_id()[:6]}",
            )
        except HTTPException as exc:
            failed.append({"member_id": target["member_id"], "reason": exc.detail})
            continue

        rescue_id = _new_id()
        doc = {
            "id": rescue_id,
            "organization_id": org_id,
            "member_id": target["member_id"],
            "member_email": target.get("email"),
            "member_name": target.get("full_name"),
            "first_name": target.get("first_name"),
            "signal": target.get("signal"),
            "signal_label": target.get("signal_label"),
            "signal_evidence": target.get("signal_evidence"),
            "signal_severity": target.get("signal_severity"),
            "primary_recommendation": target.get("primary_recommendation"),
            "last_class_name": target.get("last_class_name"),
            "days_since_last_visit": target.get("days_since_last_visit"),
            "tenure_days": target.get("tenure_days"),
            "lifetime_value_gbp": target.get("lifetime_value_gbp"),
            "copy": copy,
            "primary_channel": (copy.get("primary_channel") or "email").lower(),
            "fallback_channel": (copy.get("fallback_channel") or "in_app").lower(),
            "status": "pending_approval",
            "brand_lock": brand_lock,
            "created_by": user["id"],
            "created_at": _now_iso(),
            "approved_at": None,
            "scheduled_for": None,
            "sent_at": None,
        }
        await db.marketing_churn_rescues.insert_one(doc)
        rescues_created.append({k: v for k, v in doc.items() if k != "_id"})

    return {
        "rescues": rescues_created,
        "count": len(rescues_created),
        "failed": failed,
    }


@router.get(
    "/marketing/creative/director/churn-risk/queue",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_queue(
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """List rescues for this org. Filterable by status — defaults to
    everything *except* sent/rejected so the staff approval inbox is
    naturally focused on actionable items."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "User has no organization context")
    limit = max(1, min(int(limit or 100), 500))
    q: dict = {"organization_id": org_id}
    if status:
        q["status"] = status
    else:
        q["status"] = {"$in": ["pending_approval", "approved", "scheduled"]}
    rows = await db.marketing_churn_rescues.find(
        q, {"_id": 0},
    ).sort("created_at", -1).to_list(limit)
    return {"rescues": rows, "count": len(rows)}


@router.post(
    "/marketing/creative/director/churn-risk/{rescue_id}/approve",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_approve(
    rescue_id: str, body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Approve a rescue → schedule the send at the member's personal best
    window (per user choice 3d — multi-channel with smart fallback).

    Body (optional):
      send_now: bool                 — bypass the optimal window and
                                       schedule immediately (next minute)
    """
    org_id = user.get("organization_id")
    rescue = await db.marketing_churn_rescues.find_one(
        {"id": rescue_id, "organization_id": org_id}, {"_id": 0},
    )
    if not rescue:
        raise HTTPException(404, "Rescue not found")
    if rescue["status"] not in ("pending_approval",):
        raise HTTPException(
            400, f"Cannot approve a rescue in status '{rescue['status']}'",
        )

    send_now = bool(body.get("send_now"))
    from utils.marketing_autopilot import (
        compute_optimal_send_window, compute_per_recipient_windows,
        next_window_iso,
    )
    if send_now:
        scheduled_for = (datetime.now(timezone.utc)
                         + timedelta(minutes=1)).isoformat()
        window_source = "send_now"
    else:
        # Personal hour if we have ≥3 opens, otherwise org-best window
        windows = await compute_per_recipient_windows(
            org_id, [rescue.get("member_email") or ""],
        )
        win = windows.get((rescue.get("member_email") or "").lower())
        if not win:
            win = await compute_optimal_send_window(org_id)
        scheduled_for = next_window_iso(win["weekday"], win["hour"])
        window_source = win.get("source", "fallback")

    await db.marketing_churn_rescues.update_one(
        {"id": rescue_id},
        {"$set": {
            "status": "scheduled",
            "approved_at": _now_iso(),
            "approved_by": user["id"],
            "scheduled_for": scheduled_for,
            "window_source": window_source,
        }},
    )
    return {
        "rescue_id": rescue_id, "status": "scheduled",
        "scheduled_for": scheduled_for, "window_source": window_source,
    }


@router.post(
    "/marketing/creative/director/churn-risk/approve-bulk",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_approve_bulk(
    body: dict = Body(...), user: dict = Depends(get_current_user),
):
    """Approve multiple rescues in one call. Body: { rescue_ids: [str, ...] }."""
    if not user.get("organization_id"):
        raise HTTPException(400, "User has no organization context")
    rescue_ids = [r for r in (body.get("rescue_ids") or []) if isinstance(r, str)]
    if not rescue_ids:
        raise HTTPException(400, "rescue_ids is required")

    approved: list[dict] = []
    failed: list[dict] = []
    for rid in rescue_ids:
        try:
            result = await churn_risk_approve(
                rescue_id=rid, body={}, user=user,
            )
            approved.append(result)
        except HTTPException as exc:
            failed.append({"rescue_id": rid, "reason": exc.detail})
    return {"approved": approved, "failed": failed,
            "approved_count": len(approved)}


@router.post(
    "/marketing/creative/director/churn-risk/{rescue_id}/reject",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_reject(
    rescue_id: str, body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Reject a rescue (staff felt the copy missed the mark or the member
    isn't actually at risk). Body (optional): { reason: str }."""
    org_id = user.get("organization_id")
    reason = (body.get("reason") or "").strip() or None
    res = await db.marketing_churn_rescues.update_one(
        {"id": rescue_id, "organization_id": org_id,
         "status": "pending_approval"},
        {"$set": {"status": "rejected", "rejected_at": _now_iso(),
                  "rejected_by": user["id"], "reject_reason": reason}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Rescue not found or not in pending_approval state")
    return {"rescue_id": rescue_id, "status": "rejected"}


@router.post(
    "/marketing/creative/director/churn-risk/{rescue_id}/refine",
    dependencies=[Depends(require_module("marketing"))],
)
async def churn_risk_refine(
    rescue_id: str, body: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    """Iterate on a rescue copy with a free-text instruction. Stays in
    pending_approval; bumps a refined_count. Body: { instruction: str }."""
    org_id = user.get("organization_id")
    instruction = (body.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(400, "instruction is required")
    rescue = await db.marketing_churn_rescues.find_one(
        {"id": rescue_id, "organization_id": org_id, "status": "pending_approval"},
        {"_id": 0},
    )
    if not rescue:
        raise HTTPException(404, "Rescue not found or not pending approval")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Refine unavailable — LLM key not configured")

    sys = (
        "You are Pulse Fitness AI Creative Director refining an existing 1:1 "
        "win-back message. Apply the user's refinement instruction while "
        f"keeping the schema EXACTLY:\n{json.dumps(CHURN_RESCUE_SCHEMA)}\n\n"
        "Return ONLY the JSON object — no preamble, no markdown."
    )
    user_msg = (
        f"Member's exit signal: {rescue.get('signal_label')}\n"
        f"Signal evidence (must still be referenced): {rescue.get('signal_evidence')}\n"
        f"Existing copy:\n{json.dumps(rescue.get('copy') or {})}\n\n"
        f"Refinement instruction: {instruction}\n"
        "Return the FULL JSON in the same schema."
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key, session_id=f"churn-refine-{rescue_id}",
            system_message=sys,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_msg))
        new_copy = _strip_to_json(raw)
    except Exception as exc:
        raise HTTPException(503, f"Refine failed: {exc}") from exc

    await db.marketing_churn_rescues.update_one(
        {"id": rescue_id},
        {"$set": {
            "copy": new_copy,
            "primary_channel": (new_copy.get("primary_channel") or
                                rescue.get("primary_channel") or "email").lower(),
            "fallback_channel": (new_copy.get("fallback_channel") or
                                 rescue.get("fallback_channel") or "in_app").lower(),
            "last_refined_at": _now_iso(),
            "last_refinement": instruction,
        }, "$inc": {"refined_count": 1}},
    )
    rescue.update({"copy": new_copy})
    return {k: v for k, v in rescue.items() if k != "_id"}


__all__ = ["router"]
