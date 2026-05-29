"""Social Media Autopilot (Iter 220bl).

Generates beautiful, brand-consistent draft posts for Instagram,
TikTok and LinkedIn every day. Same architecture as the SEO
autopilot, but channel-aware:

* **Instagram** — bold, energetic, emoji-tasteful, visual-led.
  Caption ≤ 2,200 chars, recommended ~125-150, hashtag bundle 15-25.
* **TikTok** — short, punchy, native-feeling, hook in first 7 words.
  Caption ≤ 2,200 chars, recommended ≤ 150, 3-5 broad hashtags.
* **LinkedIn** — executive-grade, decision-maker focused, no emojis
  unless one tasteful bullet marker. Caption 1,200-1,800 chars sweet
  spot, 3-6 hashtags max, no clickbait.

50% feature-promotion posts, 50% industry-insight posts. Topics come
from three streams blended just like SEO discovery:

1. **Feature pillars** — the canonical GymAxis features (each one
   gets fair rotation, 14-day cooldown per channel).
2. **Industry pillars** — the same fitness-industry themes the SEO
   autopilot uses (downtime, retention, PPM, RIDDOR…).
3. **Anonymised platform signals** (k-anonymity 5, no PII) — reused
   from `utils.seo_keyword_discovery` for consistency.

All posts are saved as **drafts** in `social_autopilot_posts`. The
master admin reviews them in Growth → Social Autopilot, taps "Copy
caption" / "Download image", and posts manually.

Image strategy alternates per post:
* `A` (Nano Banana) — AI-generated brand-coloured graphic.
* `B` (Branded card template) — deterministic SVG card baked into a
  PNG: brand-gradient background, headline text, GymAxis logo mark.
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── Channel definitions ───────────────────────────────────────────────


CHANNELS: list[dict] = [
    {
        "id": "instagram",
        "label": "Instagram",
        "tone_brief": (
            "Bold, energetic, visual-first. Use tasteful emoji (max 4 per "
            "caption). Hook in line 1. Caption sweet spot 125-150 chars but "
            "may extend to 600 if the story warrants it. Hashtag bundle "
            "15-25 mixing broad + niche (no spam tags)."
        ),
        "caption_max_chars": 2200,
        "caption_target_chars": 600,
        "hashtag_min": 15,
        "hashtag_max": 25,
        "audience": "UK gym operators, ops managers, multi-site fitness leaders",
        "image_aspect": "1:1",
        "image_size_px": 1080,
    },
    {
        "id": "tiktok",
        "label": "TikTok",
        "tone_brief": (
            "Punchy, native to TikTok. Hook MUST land in the first 7 words. "
            "Conversational, slightly cheeky. Emojis sparingly. Caption ≤ 150 "
            "chars. Output BOTH a static-card caption (for TikTok Photo Mode) "
            "AND a 12-15 second video script with on-screen text cues. "
            "Hashtags: 3-5 broad (#GymTok, #GymOps, #FitnessIndustry, etc.)."
        ),
        "caption_max_chars": 2200,
        "caption_target_chars": 150,
        "hashtag_min": 3,
        "hashtag_max": 5,
        "audience": "UK gym operators and gym staff",
        "image_aspect": "9:16",
        "image_size_px": 1080,
    },
    {
        "id": "linkedin",
        "label": "LinkedIn",
        "tone_brief": (
            "Executive-grade, decision-maker focused. NO emoji unless a "
            "single bullet marker (•). NO clickbait. Open with a contrarian "
            "or data-led insight, not a question. Caption sweet spot "
            "1,200-1,800 chars. Hashtags: 3-6 max, capitalised camel-case "
            "(#FitnessOperations, #GymManagement). Always end with a "
            "single-sentence reflection or open question (no salesy CTA)."
        ),
        "caption_max_chars": 3000,
        "caption_target_chars": 1500,
        "hashtag_min": 3,
        "hashtag_max": 6,
        "audience": "UK gym chain owners, operations directors, multi-site MDs",
        "image_aspect": "1.91:1",
        "image_size_px": 1200,
    },
]


def channel_by_id(cid: str) -> Optional[dict]:
    for c in CHANNELS:
        if c["id"] == cid:
            return c
    return None


# ── Feature pillars (50% of posts) ────────────────────────────────────


FEATURE_PILLARS: list[dict] = [
    {"id": "service_desk", "label": "Service Desk & Fault Triage",
     "hook": "Members tell you when a treadmill breaks — your CRM should already know."},
    {"id": "partner_engineers", "label": "Partner Engineer Network",
     "hook": "Vetted UK engineers, paid by the visit, your SLA — no contracts."},
    {"id": "crm_pipeline", "label": "Fitness CRM with Tender Tracking",
     "hook": "The only CRM that knows your tenders, contracts AND engineers."},
    {"id": "ppm_scheduler", "label": "PPM Scheduler with Compliance Audit",
     "hook": "PPM that auto-stamps the regulator-ready evidence."},
    {"id": "sicon_integration", "label": "Sage 200 + Sicon Service Sync",
     "hook": "Stop double-keying jobs. Sage 200 and Sicon talk to GymAxis natively."},
    {"id": "membership_intelligence", "label": "Membership Intelligence & Churn AI",
     "hook": "Churn-risk scoring 7 days before the cancellation hits."},
    {"id": "gym_floor_handover", "label": "Gym Floor Handover Diary",
     "hook": "Shift-to-shift handover, iMessage-style, with names and avatars."},
    {"id": "supplier_capex", "label": "Supplier Marketplace & CAPEX Tenders",
     "hook": "Run a tender like a procurement pro — without the procurement team."},
    {"id": "growth_hub", "label": "Growth Hub for Multi-site Operators",
     "hook": "One funnel view: trials → CRM → tenders → contracts."},
    {"id": "ai_triage", "label": "AI Fault Triage",
     "hook": "An engineer's first impression in 4 seconds, before they leave the depot."},
    {"id": "gdpr_workflow", "label": "GDPR Article 17 Workflow",
     "hook": "Right-to-erasure done in one click — auditable, compliant, calm."},
    {"id": "communications_inbox", "label": "Unified Communications Inbox",
     "hook": "Every member message, every channel, one inbox, one SLA clock."},
    {"id": "supplier_qa", "label": "Supplier Performance Scoring",
     "hook": "Stop guessing which supplier ghosts you on Fridays."},
]


def feature_pillar_by_id(pid: str) -> Optional[dict]:
    for p in FEATURE_PILLARS:
        if p["id"] == pid:
            return p
    return None


# ── Brand tokens ──────────────────────────────────────────────────────


BRAND = {
    "name": "GymAxis",
    "domain": "gymaxisai.com",
    "tagline": "AI-native operations for UK fitness operators.",
    # Brand palette pulled from /app/frontend/src/index.css :root tokens.
    "color_primary": "#d946ef",   # fuchsia
    "color_accent": "#3b82f6",    # blue
    "color_ink": "#0a0a0a",
    "color_paper": "#ffffff",
    "color_soft": "#f4f4f5",
    "gradient": ["#d946ef", "#3b82f6"],
}


# ── Topic blending (50/50 feature vs industry) ────────────────────────


async def _last_used_topics(db, channel_id: str, *, days: int = 14) -> set[str]:
    """Return the topic-ids used on this channel in the last ``days``
    so the picker can avoid them."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    used: set[str] = set()
    async for row in db.social_autopilot_posts.find(
        {"channel": channel_id, "created_at": {"$gte": cutoff}},
        {"_id": 0, "topic_id": 1},
    ):
        if row.get("topic_id"):
            used.add(row["topic_id"])
    return used


async def _pick_feature_topic(db, channel_id: str) -> dict:
    """Pick the longest-not-posted feature pillar for this channel.

    Iter 220bm — channel_id is folded into the index so the same
    feature isn't picked across all three channels on the same day.
    """
    used = await _last_used_topics(db, channel_id, days=14)
    eligible = [p for p in FEATURE_PILLARS if p["id"] not in used]
    if not eligible:
        eligible = FEATURE_PILLARS  # cooldown blocked all — fall back
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    # Stable offset per channel so IG/TikTok/LinkedIn diverge on day 1
    # while still rotating LRU-style across days.
    channel_offset = sum(ord(c) for c in channel_id) % len(eligible)
    chosen = eligible[(today_idx + channel_offset) % len(eligible)]
    return {
        "kind": "feature",
        "topic_id": f"feature:{chosen['id']}",
        "label": chosen["label"],
        "hook": chosen["hook"],
        "feature_id": chosen["id"],
    }


async def _pick_industry_topic(db, channel_id: str) -> dict:
    """Reuse the SEO industry-pillar deck to keep voices consistent
    across SEO articles and social posts. Picks the longest-not-posted
    pillar on this channel.

    Iter 220bm — channel offset added to prevent three-channel
    same-topic collisions on a single day.
    """
    from utils.seo_keyword_discovery import PILLARS as SEO_PILLARS

    used = await _last_used_topics(db, channel_id, days=14)
    eligible = [p for p in SEO_PILLARS if f"industry:{p['id']}" not in used]
    if not eligible:
        eligible = SEO_PILLARS
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    channel_offset = sum(ord(c) for c in channel_id) % len(eligible)
    chosen = eligible[(today_idx + channel_offset + 3) % len(eligible)]
    return {
        "kind": "industry",
        "topic_id": f"industry:{chosen['id']}",
        "label": chosen["label"],
        "hook": chosen["keyword_templates"][0],
        "pillar_id": chosen["id"],
    }


async def pick_topic_for(db, channel_id: str) -> dict:
    """50/50 alternate between feature and industry on a per-channel
    basis. We key off the count of posts already on this channel so
    each channel keeps its own balance."""
    n_posts = await db.social_autopilot_posts.count_documents({"channel": channel_id})
    if n_posts % 2 == 0:
        return await _pick_feature_topic(db, channel_id)
    return await _pick_industry_topic(db, channel_id)


# ── LLM prompt assembly ───────────────────────────────────────────────


def build_prompt(channel: dict, topic: dict) -> str:
    """Channel-aware prompt for the LLM. Returns a single string."""
    intro = (
        f"You are a senior social-media editor for GymAxis "
        f"({BRAND['domain']}). {BRAND['tagline']}\n\n"
        f"Write ONE post for {channel['label']} aimed at this audience: "
        f"{channel['audience']}.\n\n"
        f"Tone: {channel['tone_brief']}\n\n"
    )
    if topic["kind"] == "feature":
        focus = (
            f"This post is a FEATURE-PROMOTION post for GymAxis. "
            f"Showcase the feature: '{topic['label']}'. Lead with this "
            f"angle: \"{topic['hook']}\". Show, don't tell — describe one "
            f"concrete operator outcome (e.g. saved 4 hours/week, cut "
            f"engineer dispatch by 30%) but DO NOT invent specific "
            f"customer names or numbers. Close with a soft pull to "
            f"{BRAND['domain']}.\n\n"
        )
    else:
        focus = (
            f"This post is an INDUSTRY-INSIGHT post (do NOT pitch GymAxis "
            f"hard). Cover '{topic['label']}'. Lead with this angle: "
            f"\"{topic['hook']}\". Add one practical takeaway the reader "
            f"can use even if they never become a GymAxis customer. "
            f"Mention GymAxis only as a one-line signature at the end.\n\n"
        )
    schema = (
        "Return STRICT JSON only (no prose, no fences) with this shape:\n"
        "{\n"
        '  "caption": string (the post body, ≤'
        f"{channel['caption_max_chars']} chars),\n"
        '  "hashtags": string[] '
        f"({channel['hashtag_min']}-{channel['hashtag_max']} items, each starting with #),\n"
        '  "image_brief": string '
        "(2-3 sentence visual direction for a brand-coloured image — "
        f"aspect {channel['image_aspect']}),\n"
        '  "card_headline": string '
        "(≤6 words, suitable for an over-image headline),\n"
    )
    if channel["id"] == "tiktok":
        schema += (
            '  "video_script": string (12-15 second script with explicit '
            'ON-SCREEN TEXT cues in [brackets])\n'
        )
    else:
        schema += '  "video_script": null\n'
    schema += "}\n"
    return intro + focus + schema


# ── Image generation ──────────────────────────────────────────────────


def _branded_card_svg(headline: str, channel: dict, *, subtitle: str = "") -> str:
    """Deterministic SVG card for variant B — brand gradient + bold
    headline + GymAxis mark in the bottom-right. Renders to PNG via
    Pillow further down."""
    w, h = _card_dimensions(channel["image_aspect"], channel["image_size_px"])
    safe_head = (headline or "").replace("<", "&lt;").replace(">", "&gt;")[:80]
    safe_sub = (subtitle or "").replace("<", "&lt;").replace(">", "&gt;")[:120]
    # Naïve word-wrap for headline (split at ~18 chars/line, max 3 lines).
    words = safe_head.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(cur) + len(word) + 1 > 18 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    lines = lines[:3]
    line_height = int(h * 0.10)
    font_size = int(h * 0.085)
    text_x = int(w * 0.07)
    text_y_start = int(h * 0.42) - (len(lines) - 1) * line_height // 2
    text_blocks = "\n".join(
        f'<text x="{text_x}" y="{text_y_start + i * line_height}" '
        f'fill="#ffffff" font-size="{font_size}" font-weight="800" '
        f'font-family="Inter,Helvetica,Arial,sans-serif">{ln}</text>'
        for i, ln in enumerate(lines)
    )
    sub_block = (
        f'<text x="{text_x}" y="{text_y_start + len(lines) * line_height + 20}" '
        f'fill="rgba(255,255,255,0.85)" font-size="{int(h * 0.028)}" '
        f'font-weight="500" font-family="Inter,Helvetica,Arial,sans-serif">'
        f"{safe_sub}</text>"
    ) if safe_sub else ""
    return f"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{BRAND['color_primary']}"/>
      <stop offset="100%" stop-color="{BRAND['color_accent']}"/>
    </linearGradient>
    <radialGradient id="noise" cx="20%" cy="20%" r="80%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.12)"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
    </radialGradient>
  </defs>
  <rect width="{w}" height="{h}" fill="url(#g)"/>
  <rect width="{w}" height="{h}" fill="url(#noise)"/>
  <circle cx="{int(w*0.85)}" cy="{int(h*0.18)}" r="{int(h*0.10)}" fill="rgba(255,255,255,0.10)"/>
  <circle cx="{int(w*0.12)}" cy="{int(h*0.88)}" r="{int(h*0.08)}" fill="rgba(255,255,255,0.08)"/>
  {text_blocks}
  {sub_block}
  <g transform="translate({int(w*0.07)}, {int(h*0.88)})">
    <text fill="rgba(255,255,255,0.95)" font-size="{int(h*0.028)}"
          font-weight="800" font-family="Inter,Helvetica,Arial,sans-serif"
          letter-spacing="2">{BRAND['name'].upper()}</text>
    <text y="{int(h*0.032)}" fill="rgba(255,255,255,0.6)" font-size="{int(h*0.020)}"
          font-family="Inter,Helvetica,Arial,sans-serif">{BRAND['domain']}</text>
  </g>
</svg>"""


def _card_dimensions(aspect: str, base: int) -> tuple[int, int]:
    if aspect == "1:1":
        return base, base
    if aspect == "9:16":
        return base, int(base * 16 / 9)
    if aspect == "1.91:1":
        return int(base * 1.91), base
    if aspect == "16:9":
        return base, int(base * 9 / 16)
    return base, base


def _pillow_branded_card_png(headline: str, channel: dict,
                              subtitle: str = "") -> Optional[bytes]:
    """Render a brand-coloured PNG card via Pillow. Returns PNG bytes
    or ``None`` if Pillow / fonts are unavailable."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.info("[social] Pillow unavailable: %s", exc)
        return None
    w, h = _card_dimensions(channel["image_aspect"], channel["image_size_px"])
    # Build a vertical gradient via per-row interpolation between the
    # brand fuchsia and brand blue.
    img = Image.new("RGB", (w, h), BRAND["color_primary"])
    draw = ImageDraw.Draw(img)

    def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        s = hex_str.lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

    c1 = _hex_to_rgb(BRAND["color_primary"])
    c2 = _hex_to_rgb(BRAND["color_accent"])
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Decorative soft circles for depth.
    draw.ellipse(
        [int(w * 0.78), int(h * 0.06), int(w * 0.98), int(h * 0.26)],
        fill=None, outline=(255, 255, 255, 30), width=int(h * 0.005),
    )
    # Headline — fall back to default font if no TrueType is installed.
    try:
        from PIL import ImageFont  # type: ignore
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
        font_path = next((p for p in candidates if os.path.exists(p)), None)
        font_size = int(h * 0.085)
        sub_size = int(h * 0.028)
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        sub_font = ImageFont.truetype(font_path, sub_size) if font_path else ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = sub_font = None

    # Word-wrap (≤18 chars/line, max 3 lines).
    words = (headline or "").split()
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(cur) + len(word) + 1 > 18 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    lines = lines[:3]
    text_x = int(w * 0.07)
    line_height = int(h * 0.10)
    y0 = int(h * 0.40) - (len(lines) - 1) * line_height // 2
    for i, ln in enumerate(lines):
        draw.text((text_x, y0 + i * line_height), ln,
                  fill=(255, 255, 255), font=font)
    if subtitle:
        draw.text((text_x, y0 + len(lines) * line_height + 20),
                  subtitle[:120], fill=(255, 255, 255, 200), font=sub_font)
    # Brand mark bottom-left.
    draw.text((text_x, int(h * 0.88)), BRAND["name"].upper(),
              fill=(255, 255, 255), font=font)
    draw.text((text_x, int(h * 0.94)), BRAND["domain"],
              fill=(255, 255, 255, 170), font=sub_font)

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_branded_card_to_data_url(headline: str, channel: dict,
                                     subtitle: str = "") -> str:
    """SVG/PNG → data: URL. Tries Pillow PNG first (downloadable as a
    real PNG by the operator); falls back to inline SVG."""
    png = _pillow_branded_card_png(headline, channel, subtitle=subtitle)
    if png:
        return "data:image/png;base64," + base64.b64encode(png).decode()
    svg = _branded_card_svg(headline, channel, subtitle=subtitle)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


async def render_nano_banana_image(*, prompt: str, channel: dict) -> Optional[dict]:
    """Try Gemini Nano Banana for an AI-generated brand-coloured image.
    Returns ``{url, model}`` on success, ``None`` on failure (caller
    falls back to the branded card)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
    if not api_key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.info("[social] nano banana unavailable: %s", exc)
        return None
    aspect = channel["image_aspect"]
    enriched = (
        f"{prompt}\n\nStyle: high-end, brand-aware, professional. Use a "
        f"gradient based on these GymAxis brand colours: "
        f"{BRAND['color_primary']} (fuchsia) → {BRAND['color_accent']} "
        f"(blue). Do NOT include any text, logos, or watermarks — the "
        f"caller will overlay them. Aspect ratio: {aspect}. Sleek, "
        f"editorial, suitable for a UK fitness operator audience."
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"social-{uuid.uuid4()}",
            system_message="You are a senior fitness brand art director.",
        )
        chat.with_model("gemini", "gemini-3.1-flash-image-preview")
        chat.with_params(modalities=["image", "text"])
        msg = UserMessage(text=enriched)
        _text, images = await chat.send_message_multimodal_response(msg)
        for img in (images or []):
            b64_data = img.get("data") if isinstance(img, dict) else None
            if not b64_data:
                continue
            mime = (img.get("mime_type") if isinstance(img, dict) else None) or "image/png"
            return {
                "url": f"data:{mime};base64,{b64_data}",
                "model": "gemini-3.1-flash-image-preview",
            }
    except Exception as exc:
        logger.info("[social] nano banana generation failed: %s", exc)
    return None


# ── Orchestrator ──────────────────────────────────────────────────────


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _llm_chat(prompt: str) -> dict:
    """Call Claude Sonnet via the Emergent LLM key and parse strict
    JSON. Returns the parsed dict, raising on failure."""
    import json
    import re

    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY missing")
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    chat = LlmChat(
        api_key=api_key,
        session_id=f"social-{_id()}",
        system_message=(
            "You are a senior social-media editor for B2B fitness SaaS. "
            "Always return STRICT JSON only — no prose, no markdown "
            "fences. Do not invent customer names or specific numbers."
        ),
    )
    chat.with_model("anthropic", "claude-sonnet-4-6")
    raw = await chat.send_message(UserMessage(text=prompt))
    if isinstance(raw, dict):
        text = raw.get("content") or raw.get("text") or ""
    else:
        text = str(raw or "")
    # Strip accidental ```json fences.
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        # Pull out the first {...} block as a defensive fallback.
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


async def generate_post_for_channel(db, channel_id: str) -> dict:
    """Generate ONE draft post for the given channel. Persists to
    ``social_autopilot_posts`` with ``status='draft'`` and returns the
    saved doc."""
    channel = channel_by_id(channel_id)
    if not channel:
        raise ValueError(f"Unknown channel: {channel_id}")

    topic = await pick_topic_for(db, channel_id)
    prompt = build_prompt(channel, topic)
    text = await _llm_chat(prompt)

    # Alternate image variants A/B per post (count parity on the
    # channel determines which one we use).
    n_existing = await db.social_autopilot_posts.count_documents({"channel": channel_id})
    image_variant = "A" if n_existing % 2 == 0 else "B"

    image_url: Optional[str] = None
    image_model = "branded_card"
    if image_variant == "A":
        nb = await render_nano_banana_image(
            prompt=text.get("image_brief", topic["label"]),
            channel=channel,
        )
        if nb:
            image_url = nb["url"]
            image_model = nb["model"]
    if not image_url:
        image_url = render_branded_card_to_data_url(
            headline=(text.get("card_headline") or topic["label"])[:80],
            channel=channel,
            subtitle=BRAND["tagline"],
        )
        image_variant = "B"

    hashtags = [h for h in (text.get("hashtags") or [])
                if isinstance(h, str) and h.startswith("#")][:channel["hashtag_max"]]
    caption = (text.get("caption") or "")[:channel["caption_max_chars"]]

    doc = {
        "id": _id(),
        "channel": channel_id,
        "status": "draft",
        "topic_id": topic["topic_id"],
        "topic_kind": topic["kind"],
        "topic_label": topic["label"],
        "caption": caption,
        "hashtags": hashtags,
        "video_script": text.get("video_script") or None,
        "card_headline": text.get("card_headline") or topic["label"],
        "image_brief": text.get("image_brief") or "",
        "image_url": image_url,
        "image_variant": image_variant,
        "image_model": image_model,
        "audience": channel["audience"],
        "created_at": _now(),
        "updated_at": _now(),
        "generation_meta": {
            "model_text": "claude-sonnet-4-6",
            "prompt_length": len(prompt),
        },
    }
    await db.social_autopilot_posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def generate_daily_drafts(db, *, channels: Optional[list[str]] = None) -> list[dict]:
    """One post per channel per day — the daily scheduler entry point."""
    channels = channels or [c["id"] for c in CHANNELS]
    results: list[dict] = []
    for ch in channels:
        try:
            results.append(await generate_post_for_channel(db, ch))
        except Exception as exc:  # pragma: no cover — never break the cron
            logger.warning(f"[social] {ch} draft failed: {exc}")
            results.append({"channel": ch, "error": str(exc)})
    return results


__all__ = [
    "BRAND",
    "CHANNELS",
    "FEATURE_PILLARS",
    "channel_by_id",
    "feature_pillar_by_id",
    "pick_topic_for",
    "build_prompt",
    "render_branded_card_to_data_url",
    "render_nano_banana_image",
    "generate_post_for_channel",
    "generate_daily_drafts",
    "VIDEO_DIR",
    "video_path_for_post",
    "generate_tiktok_video_for_post",
]


# ── Sora 2 video generation (TikTok only, Iter 220bm) ────────────────


VIDEO_DIR = "/app/backend/uploads/social_videos"


def video_path_for_post(post_id: str) -> str:
    """Where a generated MP4 lives on disk. Single-tenant; we don't
    namespace per-org because Social Autopilot is master-admin only."""
    os.makedirs(VIDEO_DIR, exist_ok=True)
    return os.path.join(VIDEO_DIR, f"{post_id}.mp4")


def _build_sora_prompt(post: dict) -> str:
    """Translate the saved TikTok post into a Sora 2 video prompt.

    We deliberately keep the description ABSTRACT and BRAND-AWARE — no
    text overlays (Sora 2 is poor at text), no specific people, no
    customer names. We focus on operator scenes, kit, and atmosphere
    that match the GymAxis brand."""
    headline = post.get("card_headline") or post.get("topic_label") or "GymAxis"
    script = (post.get("video_script") or "")[:400]
    brief = (post.get("image_brief") or "")[:200]
    return (
        f"Cinematic 9:16 vertical short for GymAxis ({BRAND['domain']}), "
        f"a UK B2B fitness SaaS brand. Subject: {headline}. "
        f"{brief}\n\n"
        f"Visual treatment: editorial, modern UK commercial gym setting "
        f"(treadmills, free weights, members in motion), warm late-"
        f"afternoon natural light, occasional motion blur, slow "
        f"hand-held camera. Use the GymAxis brand palette accents "
        f"(fuchsia {BRAND['color_primary']} and blue {BRAND['color_accent']}) "
        f"in lighting and equipment highlights — gels, screens, "
        f"reflections, NOT in any visible logos or text.\n\n"
        f"NO text overlays, NO captions, NO logos in frame — the "
        f"caller will overlay branding in post. NO recognisable "
        f"people from any specific brand or chain. Pace: contemplative "
        f"yet energetic. Hook moment in the first second.\n\n"
        f"Script context (for mood only, not to render as text): "
        f"{script}"
    )


async def generate_tiktok_video_for_post(
    db, post_id: str, *, model: str = "sora-2", duration: int = 8,
) -> dict:
    """Background-task entry point. Generates a 1024x1792 Sora 2 clip
    for the saved TikTok post, persists to disk, and stamps the doc
    with ``video_status='ready'`` + ``video_url`` (the API route
    that streams the bytes back).

    Designed to be invoked via ``BackgroundTasks`` from the route
    handler — Sora 2 can take 2-5 minutes which exceeds proxy
    timeouts."""
    post = await db.social_autopilot_posts.find_one({"id": post_id}, {"_id": 0})
    if not post:
        return {"ok": False, "error": "post not found"}
    if post.get("channel") != "tiktok":
        return {"ok": False, "error": "video generation is TikTok-only"}

    await db.social_autopilot_posts.update_one(
        {"id": post_id},
        {"$set": {
            "video_status": "generating",
            "video_started_at": _now(),
            "video_error": None,
            "updated_at": _now(),
        }},
    )

    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("EMERGENT_MODEL_API_KEY")
    if not api_key:
        await db.social_autopilot_posts.update_one(
            {"id": post_id},
            {"$set": {"video_status": "failed",
                      "video_error": "EMERGENT_LLM_KEY missing",
                      "updated_at": _now()}},
        )
        return {"ok": False, "error": "EMERGENT_LLM_KEY missing"}

    sora_prompt = _build_sora_prompt(post)
    output_path = video_path_for_post(post_id)

    def _do_generate() -> Optional[str]:
        """Run the blocking Sora 2 call in a worker thread."""
        try:
            from emergentintegrations.llm.openai.video_generation import (  # type: ignore
                OpenAIVideoGeneration,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[social] Sora 2 import failed: {exc}")
            return None
        try:
            gen = OpenAIVideoGeneration(api_key=api_key)
            video_bytes = gen.text_to_video(
                prompt=sora_prompt,
                model=model,
                size="1024x1792",   # 9:16 vertical, TikTok-native
                duration=duration,
                max_wait_time=600,
            )
            if not video_bytes:
                return None
            gen.save_video(video_bytes, output_path)
            return output_path
        except Exception as exc:
            logger.warning(f"[social] Sora 2 generation failed: {exc}")
            return None

    try:
        import asyncio
        result = await asyncio.to_thread(_do_generate)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[social] Sora 2 thread failure: {exc}")
        result = None

    if not result or not os.path.exists(output_path):
        await db.social_autopilot_posts.update_one(
            {"id": post_id},
            {"$set": {
                "video_status": "failed",
                "video_error": "Sora 2 returned no bytes",
                "updated_at": _now(),
            }},
        )
        return {"ok": False, "error": "Sora 2 returned no bytes"}

    size_bytes = os.path.getsize(output_path)
    await db.social_autopilot_posts.update_one(
        {"id": post_id},
        {"$set": {
            "video_status": "ready",
            "video_url": f"/api/marketing/social-autopilot/posts/{post_id}/video",
            "video_model": model,
            "video_duration": duration,
            "video_size_bytes": size_bytes,
            "video_completed_at": _now(),
            "updated_at": _now(),
        }},
    )
    return {"ok": True, "size_bytes": size_bytes, "path": output_path}
