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


# ── Iter 222 · Template-based imagery (replaces hallucinated AI images) ──
# The old Variant-A path asked Gemini to *draw* a marketing image from a
# free-form brief. Image models invent garbled UIs, wrong logos and blank
# gradients — exactly the off-brand output operators flagged. We now render
# every card deterministically from real brand tokens + the real logo +
# (optionally) a REAL product screenshot. Nothing is ever invented.

_LOGO_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "static", "brand", "gymaxis-full.png"),
    "/app/frontend/public/brand/gymaxis-full-tight.png",
]


def _resolve_logo_path() -> Optional[str]:
    return next((p for p in _LOGO_PATHS if os.path.exists(p)), None)


_SCREENSHOTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "static", "social", "screenshots",
)

# feature_id → real product screenshot filename. Only mapped when a
# screenshot GENUINELY shows that feature — an inaccurate screen erodes
# trust, so features without a true matching screen fall back to the
# feature/stat card instead.
SCREENSHOT_MAP = {
    "service_desk": "servicedesk.png",
    "ai_triage": "faults.png",
    "partner_engineers": "eng_jobs.png",
    "crm_pipeline": "crm_pipeline.png",
    "supplier_capex": "crm_pipeline.png",
    "growth_hub": "reports.png",
    "ppm_scheduler": "schedule.png",
    "sicon_integration": "reports.png",
    "membership_intelligence": "mbr_analytics.png",
    "gym_floor_handover": "eng_diary.png",
    "supplier_qa": "suppliers.png",
    # communications_inbox & gdpr_workflow have no true matching screen —
    # intentionally unmapped so they use the feature card, never a
    # misleading screenshot.
}


def _screenshot_path_for(feature_id: Optional[str]) -> Optional[str]:
    fn = SCREENSHOT_MAP.get(feature_id or "")
    if not fn:
        return None
    p = os.path.join(_SCREENSHOTS_DIR, fn)
    return p if os.path.exists(p) else None


# Curated, NEVER-fabricated stats. Product facts are literally true of
# GymAxis; industry items are clearly tagged "Industry estimate" on the
# card so they're never mistaken for GymAxis customer results.
PRODUCT_STATS = [
    {"value": "6-in-1", "label": "CRM, service desk, PPM, memberships, finance & marketing"},
    {"value": "13", "label": "operational modules — one login, one source of truth"},
    {"value": "4 sec", "label": "AI fault triage before the engineer leaves the depot"},
    {"value": "24/7", "label": "member-reported faults auto-raised as tickets"},
    {"value": "Zero", "label": "double-keying — Sage 200 & Sicon sync natively"},
    {"value": "1 click", "label": "regulator-ready PPM evidence, auto-stamped & filed"},
]
INDUSTRY_STATS = [
    {"value": "5×", "label": "more costly to win a new member than to keep one"},
    {"value": "#1", "label": "member gripe in gyms: broken or unavailable kit"},
    {"value": "Hours", "label": "lost every week chasing engineers across WhatsApp & email"},
    {"value": "1 bad visit", "label": "is all it takes for a member to start cancelling"},
]


def _pick_stat(topic: dict, n: int) -> dict:
    is_feature = topic.get("kind") == "feature"
    pool = PRODUCT_STATS if is_feature else INDUSTRY_STATS
    chosen = pool[n % len(pool)]
    return {**chosen, "kind": "product" if is_feature else "industry"}


# Per-topic layout rotations. ``screenshot`` is only used when a real
# product screenshot exists for the feature (else falls back to feature).
_FEATURE_LAYOUTS = ["screenshot", "feature", "stat", "hook"]
_INDUSTRY_LAYOUTS = ["stat", "punchline", "hook", "feature"]


def pick_layout(channel_id: str, topic: dict, n_existing: int) -> str:
    """Deterministically rotate card layouts so the feed has variety
    without any generative hallucination."""
    rotation = _FEATURE_LAYOUTS if topic.get("kind") == "feature" else _INDUSTRY_LAYOUTS
    layout = rotation[n_existing % len(rotation)]
    if layout == "screenshot" and not _screenshot_path_for(topic.get("feature_id")):
        layout = "feature"
    # LinkedIn stays drier — swap cheeky punchlines for a numbers card.
    if layout == "punchline" and channel_id == "linkedin":
        layout = "stat"
    return layout


def _layout_schema(layout: str, stat: Optional[dict] = None) -> str:
    """Extra JSON keys / guidance appended to the LLM schema for the
    chosen card layout. Numbers are supplied by us (never invented)."""
    if layout == "feature":
        return (
            '  "feature_bullets": string[] (EXACTLY 3 benefit bullets, '
            "≤6 words each, concrete operator outcomes, NO invented "
            "metrics or customer names),\n"
        )
    if layout == "punchline":
        return (
            '  "punchline_setup": string (one short, relatable ops-life '
            "setup line — the everyday pain),\n"
            '  "punchline_payoff": string (the witty on-brand payoff, '
            "dry wit, NO emoji, ≤8 words),\n"
        )
    return ""


def _layout_guidance(layout: str, channel_id: str, stat: Optional[dict]) -> str:
    """A short instruction added to the prompt body so the CAPTION
    matches the chosen visual."""
    humour = (
        "Keep any humour dry and executive-safe — wit, not jokes."
        if channel_id == "linkedin"
        else "A light, cheeky, knowing tone is welcome (no cringe, no emoji spam)."
    )
    if layout == "stat" and stat:
        framing = (
            "This is a widely-cited INDUSTRY estimate — frame it as an "
            "industry reality, never as a GymAxis customer result."
            if stat.get("kind") == "industry"
            else "This is a true GymAxis product fact."
        )
        return (
            f"\nThe image is a NUMBERS card showing: "
            f"'{stat['value']} — {stat['label']}'. {framing} Write the caption "
            f"to land that figure. Do NOT invent other specific numbers.\n"
        )
    if layout == "punchline":
        return f"\nThe image is a humour card (setup → payoff). {humour}\n"
    if layout == "screenshot":
        return (
            "\nThe image is a REAL screenshot of the GymAxis product, framed "
            "in a browser window. Write the caption to point at what the "
            "screen shows.\n"
        )
    if layout == "feature":
        return "\nThe image is a feature card with 3 benefit bullets.\n"
    return ""



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


def build_prompt(channel: dict, topic: dict, layout: Optional[str] = None,
                 stat: Optional[dict] = None) -> str:
    """Channel-aware prompt for the LLM. Returns a single string.

    ``layout``/``stat`` (Iter 222) bias the caption to match the chosen
    deterministic card and inject layout-specific JSON keys."""
    intro = (
        f"You are a senior social-media editor for GymAxis "
        f"({BRAND['domain']}). {BRAND['tagline']}\n\n"
        f"Write ONE post for {channel['label']} aimed at this audience: "
        f"{channel['audience']}.\n\n"
        f"Tone: {channel['tone_brief']}\n\n"
    )
    if topic["kind"] == "feature":
        focus = (
            f"This post is a FEATURE-PROMOTION post for GymAxis.\n"
            f"FEATURE YOU ARE WRITING ABOUT — do not change it:\n"
            f"  • Name (use this EXACT feature): {topic['label']}\n"
            f"  • What it is: {topic['hook']}\n"
            f"Write the headline AND caption about THIS feature only. "
            f"NEVER invent, rename or substitute a different product (e.g. "
            f"do not call it a 'Rota Builder', 'Smart Scheduling' or 'Ops "
            f"Dashboard' unless that is the exact feature above). Show, "
            f"don't tell — describe one concrete operator outcome, but DO "
            f"NOT invent specific customer names or numbers. Close with a "
            f"soft pull to {BRAND['domain']}.\n\n"
        )
    else:
        focus = (
            f"This post is an INDUSTRY-INSIGHT post (do NOT pitch GymAxis "
            f"hard). Cover '{topic['label']}'. Lead with this angle: "
            f"\"{topic['hook']}\". Add one practical takeaway the reader "
            f"can use even if they never become a GymAxis customer. "
            f"Mention GymAxis only as a one-line signature at the end.\n\n"
        )
    if layout:
        focus += _layout_guidance(layout, channel["id"], stat) + "\n"
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
        "(a clear, COMPLETE 3-5 word headline that reads as a "
        "standalone thought — NOT a teaser, NOT a truncation, NOT "
        "starting mid-sentence. Title-case. No emoji. No quotes. "
        "Examples that work: 'Cut Engineer Dispatch Time', 'Stop "
        "Chasing PPMs Manually'. Examples that DON'T work: 'How "
        "to...', 'The 5 things you...', 'Why we built...'),\n"
    )
    if layout:
        schema += _layout_schema(layout, stat)
    if channel["id"] == "tiktok":
        schema += (
            '  "video_script": string (12-15 second script with explicit '
            'ON-SCREEN TEXT cues in [brackets])\n'
        )
    else:
        schema += '  "video_script": null\n'
    schema += "}\n"
    return intro + focus + schema


# ── Iter 220bw · Launch campaigns ─────────────────────────────────────


# Launch-campaign archetypes. The campaign generator picks ONE per
# post, cycling through evenly. Each archetype gives the LLM a very
# different shape so the launch feed doesn't feel monotonous after
# 5 posts.
LAUNCH_ARCHETYPES: list[dict] = [
    {
        "id": "feature_reveal",
        "instruction": (
            "This is a FEATURE-REVEAL launch post. Lead with the "
            "feature name, then 1 sentence on WHY we built it (the "
            "operator pain), then 1 sentence on what it unlocks. End "
            "with 'Out now in beta — DM for early access.' Tone: "
            "confident but grounded, no hype emojis."
        ),
        "card_headline_hint": "Just launched: {feature}",
    },
    {
        "id": "problem_solution_story",
        "instruction": (
            "This is a PROBLEM → SOLUTION launch post. Open with the "
            "ugly truth (e.g. 'Most multi-site operators still chase "
            "engineers by WhatsApp'). Then pivot — 'We built {feature} "
            "for exactly this.' One sentence on what changes for the "
            "ops manager. Close with: 'GymAxis is launching this "
            "month. Comment LAUNCH to get on the early-access list.'"
        ),
        "card_headline_hint": "The problem we just solved",
    },
    {
        "id": "built_by_ops",
        "instruction": (
            "This is a 'BUILT BY OPS PEOPLE FOR OPS PEOPLE' launch "
            "post. Lead with: 'Most fitness SaaS is built by tech "
            "people. GymAxis isn't.' One paragraph on how we shadowed "
            "real ops managers / engineers / GMs to design {feature}. "
            "End with: 'Launching in [month]. Want in? Comment LAUNCH.'"
        ),
        "card_headline_hint": "Built by ops, for ops",
    },
]


def pick_launch_archetype(post_count_for_channel: int) -> dict:
    """Round-robin through the launch archetypes by counting prior
    posts in this channel. Deterministic so a fresh test environment
    always gets the same first archetype."""
    return LAUNCH_ARCHETYPES[post_count_for_channel % len(LAUNCH_ARCHETYPES)]


async def get_active_launch_campaign(db) -> Optional[dict]:
    """Return the single active ``social_autopilot_campaigns`` row of
    type ``launch`` (only one is active at a time). ``None`` if no
    active campaign — generator falls back to the established mix.

    The collection schema (lazily created via insert_one in the route):
      ``id``, ``name``, ``type`` ("launch"|"feature"|"established"),
      ``status`` ("active"|"paused"|"finished"), ``keywords`` (list[str]),
      ``blend_ratio`` (float 0..1 — % of generations using campaign tone),
      ``starts_at``, ``ends_at`` (ISO 8601), ``created_at``, ``created_by``.
    """
    return await db.social_autopilot_campaigns.find_one(
        {"status": "active", "type": "launch"}, {"_id": 0},
    )


def build_launch_prompt(channel: dict, topic: dict, campaign: dict,
                        archetype: dict, layout: Optional[str] = None,
                        stat: Optional[dict] = None) -> str:
    """Launch-campaign-specific prompt. Replaces the established
    `build_prompt` when the picker decides this generation should be
    on-campaign.

    Pulls in:
    * The launch archetype instruction (one of feature_reveal,
      problem_solution_story, built_by_ops).
    * The campaign keywords (user-supplied — biases the LLM towards
      the operator's launch narrative).
    * The chosen feature from the topic.
    """
    feature_name = topic.get("label", "GymAxis")
    keywords = ", ".join(campaign.get("keywords", []) or [])
    archetype_instruction = archetype["instruction"].format(feature=feature_name)
    intro = (
        f"You are a senior social-media editor for GymAxis "
        f"({BRAND['domain']}). {BRAND['tagline']}\n\n"
        f"GymAxis is in its LAUNCH WEEK — the platform is BRAND NEW. "
        f"DO NOT write as if it has existing customers, case studies, "
        f"or established usage. DO NOT invent metrics like '4 hours "
        f"saved per week' or 'cut dispatch by 30%' — we have no track "
        f"record yet. Lean on the ASPIRATION, not the proof.\n\n"
        f"Write ONE launch post for {channel['label']} aimed at this "
        f"audience: {channel['audience']}.\n\n"
        f"Tone: {channel['tone_brief']}\n\n"
    )
    campaign_section = (
        f"This post is part of the '{campaign.get('name', 'Launch')}' "
        f"campaign. Campaign keywords to weave in tastefully (do not "
        f"force all of them — pick 2-3): {keywords or 'no extra keywords'}.\n\n"
    )
    focus = archetype_instruction + "\n\n"
    # Iter 222 — HARD feature binding. The LLM was drifting to invented
    # products (a CRM topic produced a "Smart Rota Builder" headline),
    # which then mismatched the feature-keyed screenshot. Pin it down.
    feature_brief = (
        "FEATURE YOU ARE WRITING ABOUT — do not change it:\n"
        f"  • Name (use this EXACT feature): {feature_name}\n"
        f"  • What it is: {topic.get('hook', '')}\n"
        "Write the headline AND caption about THIS feature only. NEVER "
        "invent, rename or substitute a different product — e.g. do not "
        "call it a 'Rota Builder', 'Smart Scheduling', 'Staff Scheduling' "
        "or 'Ops Dashboard' unless that is the exact feature named above. "
        "You may shorten the name for a catchy headline, but it must stay "
        "the SAME feature.\n\n"
    )
    focus = feature_brief + focus
    if layout:
        focus += _layout_guidance(layout, channel["id"], stat) + "\n"
    schema = (
        "Return STRICT JSON only (no prose, no fences) with this shape:\n"
        "{\n"
        '  "caption": string (≤'
        f"{channel['caption_max_chars']} chars),\n"
        '  "hashtags": string[] '
        f"({channel['hashtag_min']}-{channel['hashtag_max']} items, each starting with #),\n"
        '  "image_brief": string '
        "(2-3 sentence visual direction for a brand-coloured image — "
        f"aspect {channel['image_aspect']}),\n"
        '  "card_headline": string '
        f"(≤6 words — hint: \"{archetype['card_headline_hint'].format(feature=feature_name)}\"),\n"
    )
    if layout:
        schema += _layout_schema(layout, stat)
    if channel["id"] == "tiktok":
        schema += (
            '  "video_script": string (12-15 second script with explicit '
            'ON-SCREEN TEXT cues in [brackets], launch-energy tone)\n'
        )
    else:
        schema += '  "video_script": null\n'
    schema += "}\n"
    return intro + campaign_section + focus + schema


def should_use_launch_tone(blend_ratio: float, post_count: int) -> bool:
    """Deterministic 70/30 blend without using random() — we want
    reproducible behaviour in tests.

    For blend_ratio=0.7: 7 of every 10 posts (positions 0,1,2,3,4,5,6
    in each cycle of 10) are on-campaign; positions 7,8,9 are
    established voice. The deterministic schedule is also easier for
    the master admin to predict.
    """
    if blend_ratio <= 0:
        return False
    if blend_ratio >= 1:
        return True
    # Convert 0.7 → 7. Compare position-in-cycle of 10 against the
    # threshold.
    threshold = int(round(blend_ratio * 10))
    return (post_count % 10) < threshold


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

    # Decorative soft circles for depth — render via alpha blending on
    # an RGBA overlay so they're actually subtle (RGB mode silently
    # ignores alpha, which is why operators were seeing a stark white
    # ring in the top-right corner).
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse(
        [int(w * 0.78), int(h * 0.06), int(w * 0.98), int(h * 0.26)],
        fill=(255, 255, 255, 18),
    )
    overlay_draw.ellipse(
        [int(w * 0.04), int(h * 0.80), int(w * 0.18), int(h * 0.94)],
        fill=(255, 255, 255, 12),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    # Headline — fall back to default font if no TrueType is installed.
    try:
        from PIL import ImageFont  # type: ignore
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            # Iter 220ce — installed in slim Debian images by default
            # via `fonts-freefont-ttf` / `fonts-liberation`. Add them
            # so the headline renders at the intended pixel size
            # instead of falling back to the 10px bitmap.
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
        font_path = next((p for p in candidates if os.path.exists(p)), None)
        # Pick the matching regular-weight font for the subtitle.
        sub_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        sub_font_path = next((p for p in sub_candidates if os.path.exists(p)), None) or font_path
        font_size = int(h * 0.085)
        sub_size = int(h * 0.028)
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        sub_font = ImageFont.truetype(sub_font_path, sub_size) if sub_font_path else ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = sub_font = None
        font_path = sub_font_path = None  # type: ignore[assignment]
        font_size = int(h * 0.085)
        sub_size = int(h * 0.028)

    # Iter 220cg — pixel-aware word-wrap.
    # The previous wrapper used a fixed 18-char budget. With TrueType
    # rendering on portrait (9:16) channels the per-char pixel width
    # can easily push lines past the safe right margin → "text falls
    # off the edge". Now we:
    #   1. Measure each candidate line with the selected font.
    #   2. Wrap when the next word would exceed the safe width.
    #   3. If the headline still doesn't fit in 3 lines OR any single
    #      line is wider than the safe width, shrink the font size
    #      and retry (down to 50% of original).
    text_x = int(w * 0.07)
    safe_width = w - 2 * text_x  # left + right margins symmetrical
    max_lines = 3

    def _text_width(_font, _text: str) -> int:
        if _font is None:
            return len(_text) * 6  # crude fallback for bitmap font
        try:
            return int(_font.getlength(_text))  # type: ignore[attr-defined]
        except Exception:
            try:
                bbox = _font.getbbox(_text)
                return int(bbox[2] - bbox[0])
            except Exception:
                return len(_text) * 6

    def _wrap(_font, _text: str) -> list[str]:
        words_ = (_text or "").split()
        out: list[str] = []
        cur = ""
        for word in words_:
            candidate = (cur + " " + word).strip()
            if _text_width(_font, candidate) <= safe_width:
                cur = candidate
            else:
                if cur:
                    out.append(cur)
                # Single word longer than safe_width — hard-truncate so
                # it doesn't run off the card. Better than overflow.
                if _text_width(_font, word) > safe_width:
                    # Cut character-by-character until it fits, leaving
                    # room for a trailing ellipsis.
                    while word and _text_width(_font, word + "…") > safe_width:
                        word = word[:-1]
                    word = word + "…" if word else word
                cur = word
        if cur:
            out.append(cur)
        return out

    # Try the original font size; shrink down to 50% if it doesn't fit.
    headline_text = (headline or "").strip()
    cur_size = font_size
    min_size = max(int(font_size * 0.5), 14)
    lines: list[str] = []
    while cur_size >= min_size:
        try_font = font
        if font_path:
            try:
                from PIL import ImageFont  # type: ignore
                try_font = ImageFont.truetype(font_path, cur_size)
            except Exception:
                try_font = font
        wrapped = _wrap(try_font, headline_text)
        fits = (
            len(wrapped) <= max_lines
            and all(_text_width(try_font, ln) <= safe_width for ln in wrapped)
        )
        if fits:
            font = try_font
            font_size = cur_size
            lines = wrapped
            break
        cur_size = int(cur_size * 0.9)
    if not lines:
        # Final fallback — hard-cap to ``max_lines`` even if oversized.
        # Each line gets character-truncated so nothing reaches the edge.
        wrapped = _wrap(font, headline_text)[:max_lines]
        if wrapped:
            # Drop the last word with an ellipsis if more text remains.
            last = wrapped[-1]
            while last and _text_width(font, last + "…") > safe_width:
                # Trim the last word until it fits.
                parts = last.rsplit(" ", 1)
                if len(parts) == 1:
                    last = last[:-1]
                else:
                    last = parts[0]
            wrapped[-1] = (last + "…") if last else last
        lines = wrapped

    line_height = int(font_size * 1.15)
    y0 = int(h * 0.42) - (len(lines) - 1) * line_height // 2
    for i, ln in enumerate(lines):
        draw.text((text_x, y0 + i * line_height), ln,
                  fill=(255, 255, 255), font=font)
    if subtitle:
        # Subtitle is also pixel-aware: truncate at word boundary with
        # an ellipsis if it would exceed safe_width.
        sub_text = subtitle.strip()
        while sub_text and _text_width(sub_font, sub_text) > safe_width:
            parts = sub_text.rsplit(" ", 1)
            if len(parts) == 1:
                sub_text = sub_text[:-1]
            else:
                sub_text = parts[0]
        if sub_text and sub_text != subtitle.strip():
            sub_text = sub_text + "…"
        draw.text((text_x, y0 + len(lines) * line_height + 20),
                  sub_text[:120], fill=(255, 255, 255, 200), font=sub_font)

    # ── Brand mark (bottom-left) ───────────────────────────────────
    # Iter 220ce — the logo PNGs ship with a white background baked
    # in (no real alpha), so just pasting them onto a coloured
    # gradient produced a hard white box that looked like a bug.
    # Instead we render the full horizontal logo onto a rounded
    # white "badge" — looks intentional, reads clearly on any brand
    # colour, and matches how professional B2B Instagram cards do it.
    brand_block_y = int(h * 0.84)
    logo_paths = [
        os.path.join(os.path.dirname(__file__), "..", "static", "brand", "gymaxis-full.png"),
        "/app/frontend/public/brand/gymaxis-full-tight.png",
    ]
    logo_path = next((p for p in logo_paths if os.path.exists(p)), None)
    if logo_path:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            target_h = int(h * 0.07)
            scale = target_h / logo.height
            target_w = int(logo.width * scale)
            logo = logo.resize((target_w, target_h), Image.LANCZOS)

            # Build a rounded-corner white badge that wraps the logo.
            pad_x = int(target_h * 0.55)
            pad_y = int(target_h * 0.25)
            badge_w = target_w + pad_x * 2
            badge_h = target_h + pad_y * 2
            badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
            bdraw = ImageDraw.Draw(badge)
            radius = int(badge_h * 0.3)
            bdraw.rounded_rectangle(
                [0, 0, badge_w, badge_h], radius=radius,
                fill=(255, 255, 255, 245),
            )
            badge.paste(logo, (pad_x, pad_y), logo)

            rgba = img.convert("RGBA")
            rgba.paste(badge, (text_x, brand_block_y), badge)
            img = rgba.convert("RGB")
            draw = ImageDraw.Draw(img)
            url_y = brand_block_y + badge_h + int(h * 0.012)
            draw.text((text_x, url_y), BRAND["domain"],
                      fill=(255, 255, 255), font=sub_font)
        except Exception as exc:  # pragma: no cover
            logger.info("[social] logo paste failed, falling back to text: %s", exc)
            logo_path = None
    if not logo_path:
        # Text fallback — use the small font (not the headline font!)
        # so the brand mark doesn't overlap the URL below.
        draw.text((text_x, brand_block_y), BRAND["name"].upper(),
                  fill=(255, 255, 255), font=sub_font)
        draw.text((text_x, brand_block_y + int(h * 0.04)), BRAND["domain"],
                  fill=(255, 255, 255), font=sub_font)

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


def clean_card_headline(raw: str, *, fallback: str = "") -> str:
    """Iter 220cg — Normalise the LLM-supplied ``card_headline`` so the
    over-image text always reads as a clean, complete thought.

    The LLM occasionally returns:
      • Leading/trailing quotes ("Cut downtime in half.")
      • Trailing punctuation that looks weird on a hero card
      • Truncation markers ("How to cut downtime...")
      • Sentences starting mid-thought ("...the silent killer")
      • All-caps shouting

    We strip those, title-case, and clip to 6 words. If after cleaning
    the headline is empty (or starts with a connector word like 'and'
    / 'the' that suggests truncation), we fall back to ``fallback``.
    """
    s = (raw or "").strip()
    # Strip wrapping quotes (straight + curly).
    for q in ('"', "'", "“", "”", "‘", "’", "«", "»"):
        if s.startswith(q):
            s = s[1:]
        if s.endswith(q):
            s = s[:-1]
    s = s.strip()
    # Iter 220cg — detect mid-thought truncation BEFORE stripping. The
    # LLM occasionally returns "How to cut downtime..." which is a
    # classic clickbait teaser; we reject those wholesale.
    had_ellipsis = s.endswith("...") or s.endswith("…")
    # Trim trailing punctuation that looks bad on a hero card.
    while s and s[-1] in ".,;:!?…-—–":
        s = s[:-1].rstrip()
    # Cap to 6 words.
    words = s.split()
    if len(words) > 6:
        words = words[:6]
    s = " ".join(words).strip()
    # Detect truncation / mid-thought starts.
    bad_starters = {
        "and", "but", "or", "so", "the", "a", "an", "to", "of", "in",
        "on", "for", "with", "that", "this", "these", "those", "you",
        "your", "we", "our", "if", "when", "while", "because",
    }
    teaser_phrases = ("how to ", "why we ", "what is ", "what are ",
                      "5 ways ", "3 ways ", "the 5 ", "the 3 ")
    first = (words[0].lower() if words else "")
    starts_teaser = any(s.lower().startswith(p) for p in teaser_phrases)
    if not s or first in bad_starters or (had_ellipsis and starts_teaser):
        return (fallback or "").strip()[:80]
    # Title-case (preserve brand-style acronyms like PPM, RIDDOR, GymAxis).
    def _smart_case(w: str) -> str:
        if w.isupper() and len(w) <= 6:
            return w  # likely an acronym
        if w.lower() == "gymaxis":
            return "GymAxis"
        # Acronym with plural / suffix (PPMs, KPIs, MDs) — preserve
        # if the leading run of uppercase letters is 2+.
        upper_prefix = 0
        for ch in w:
            if ch.isupper():
                upper_prefix += 1
            else:
                break
        if upper_prefix >= 2:
            return w
        return w[:1].upper() + w[1:].lower()
    return " ".join(_smart_case(w) for w in s.split())[:80]


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
    saved doc.

    Iter 220bw — if an active launch campaign exists, blends 70%
    launch-toned posts with 30% established-tone posts deterministically
    (see ``should_use_launch_tone``)."""
    channel = channel_by_id(channel_id)
    if not channel:
        raise ValueError(f"Unknown channel: {channel_id}")

    # Iter 220bw — campaign blend.
    n_existing = await db.social_autopilot_posts.count_documents({"channel": channel_id})
    campaign = await get_active_launch_campaign(db)
    is_on_campaign = False
    archetype = None
    if campaign:
        blend = float(campaign.get("blend_ratio") or 0.7)
        is_on_campaign = should_use_launch_tone(blend, n_existing)
        if is_on_campaign:
            archetype = pick_launch_archetype(n_existing)

    topic = await pick_topic_for(db, channel_id)
    if is_on_campaign:
        # Launch posts always anchor on a feature pillar — the
        # campaign is feature-heavy by design.
        if topic.get("kind") != "feature":
            # Re-pick a feature pillar (skip 14-day cooldown — launch
            # week, anything goes).
            feature = FEATURE_PILLARS[n_existing % len(FEATURE_PILLARS)]
            topic = {
                "topic_id": f"feature:{feature['id']}", "kind": "feature",
                "label": feature["label"], "hook": feature["hook"],
                "feature_id": feature["id"],
            }

    # Iter 222 — pick a deterministic, brand-accurate card layout +
    # (for stat cards) a curated, never-fabricated figure.
    layout = pick_layout(channel_id, topic, n_existing)
    stat = _pick_stat(topic, n_existing) if layout == "stat" else None

    if is_on_campaign:
        prompt = build_launch_prompt(channel, topic, campaign, archetype,
                                     layout=layout, stat=stat)
    else:
        prompt = build_prompt(channel, topic, layout=layout, stat=stat)
    text = await _llm_chat(prompt)

    # Iter 220cg — normalise the over-image headline ONCE so both the
    # rendered branded card AND the stored `card_headline` field agree
    # (the UI shows this string under "Caption headline").
    normalised_headline = clean_card_headline(
        text.get("card_headline") or "",
        fallback=topic["label"],
    )

    # Iter 222 — render the chosen layout DETERMINISTICALLY. We no longer
    # use generative AI for imagery: it hallucinated fake dashboards,
    # wrong logos and blank gradients. Every card is now real brand
    # tokens + the real logo + (optionally) a real product screenshot.
    from utils.social_templates import render_social_card
    w, h = _card_dimensions(channel["image_aspect"], channel["image_size_px"])
    fields: dict = {
        "headline": normalised_headline or topic["label"],
        "subtitle": BRAND["tagline"],
    }
    if layout == "stat" and stat:
        fields.update({"stat_value": stat["value"], "stat_label": stat["label"],
                       "stat_kind": stat["kind"]})
    elif layout == "feature":
        bullets = [b for b in (text.get("feature_bullets") or [])
                   if isinstance(b, str) and b.strip()][:3]
        fields["bullets"] = bullets or [
            topic["label"], "Built for multi-site UK operators",
            "One platform — no spreadsheets",
        ]
    elif layout == "punchline":
        fields["setup"] = (text.get("punchline_setup") or "").strip()
        fields["payoff"] = (text.get("punchline_payoff")
                            or normalised_headline or topic["label"]).strip()
    elif layout == "screenshot":
        fields["screenshot_path"] = _screenshot_path_for(topic.get("feature_id"))
        # Iter 222 — GUARANTEE the on-image headline matches the screenshot.
        # The LLM headline can drift to an unrelated feature (e.g. a CRM
        # screenshot under a "Smart Rota Builder" headline). The screenshot
        # is keyed to the feature, so the headline must be too. If, despite
        # the hard binding in the prompt, no real screenshot resolved, drop
        # to a feature card rather than show a mismatched image.
        feat = feature_pillar_by_id(topic.get("feature_id"))
        if not fields["screenshot_path"]:
            layout = "feature"
            bullets = [b for b in (text.get("feature_bullets") or [])
                       if isinstance(b, str) and b.strip()][:3]
            fields["bullets"] = bullets or [
                topic["label"], "Built for multi-site UK operators",
                "One platform — no spreadsheets",
            ]
        elif feat:
            normalised_headline = feat["label"]
            fields["headline"] = feat["label"]

    image_variant = layout
    image_model = f"template:{layout}"
    png = render_social_card(
        layout, w=w, h=h, brand=BRAND, fields=fields,
        logo_path=_resolve_logo_path(),
    )
    if png:
        image_url = "data:image/png;base64," + base64.b64encode(png).decode()
    else:
        # Last-resort fallback to the legacy branded card.
        image_url = render_branded_card_to_data_url(
            headline=normalised_headline, channel=channel,
            subtitle=BRAND["tagline"],
        )
        image_model = "branded_card"
        image_variant = "B"

    hashtags = [h for h in (text.get("hashtags") or [])
                if isinstance(h, str) and h.startswith("#")][:channel["hashtag_max"]]
    caption = (text.get("caption") or "")[:channel["caption_max_chars"]]

    # Iter 220bx — pre-publish tone check. Runs the heuristic launch
    # rulebook against the caption + hashtags so the UI can warn the
    # operator about metric claims / social proof / established voice
    # leakage BEFORE they hit Publish.
    from utils.social_tone_check import check_draft_tone
    tone_check = check_draft_tone(
        caption, hashtags=hashtags, on_campaign=bool(is_on_campaign),
    )

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
        "card_headline": normalised_headline or topic["label"],
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
            # Iter 220bw — campaign tagging for analytics + UI badge.
            "campaign_id": (campaign or {}).get("id"),
            "campaign_name": (campaign or {}).get("name"),
            "campaign_archetype": (archetype or {}).get("id"),
            "on_campaign": bool(is_on_campaign),
        },
        # Iter 220bx — pre-publish tone check result.
        "tone_check": tone_check,
    }
    await db.social_autopilot_posts.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ── Iter 222 · Prompt → on-brand poster (manual AI Poster Assistant) ──
# The operator types what they want; Claude picks the best deterministic
# layout and fills the fields; we render with the real logo/brand (never
# a generative image). No screenshots in this flow (operator's choice).

_COMPOSE_LAYOUTS = {"hook", "stat", "feature", "punchline"}


def build_compose_prompt(channel: dict, user_prompt: str,
                         headline: Optional[str] = None,
                         layout: Optional[str] = None) -> str:
    stats_block = (
        "Product facts (true of GymAxis — stat_kind 'product'):\n"
        + "\n".join(f"- {s['value']} | {s['label']}" for s in PRODUCT_STATS)
        + "\nIndustry estimates (stat_kind 'industry'):\n"
        + "\n".join(f"- {s['value']} | {s['label']}" for s in INDUSTRY_STATS)
    )
    if layout:
        layout_line = f"Use the '{layout}' layout for the image."
    else:
        layout_line = (
            "Choose the BEST image layout for this request:\n"
            "  • hook — a bold one-line statement (default for a strong claim)\n"
            "  • stat — a big NUMBER + label (use when the request is numbers-led)\n"
            "  • feature — a feature title + 3 benefit bullets\n"
            "  • punchline — relatable ops humour (setup → payoff)"
        )
    tone = channel.get("tone_brief", "")
    return (
        f"You are composing ONE {channel['label']} post for {BRAND['name']} "
        f"({BRAND['tagline']}), a UK B2B fitness-operations SaaS. Audience: "
        f"{channel['audience']}. Tone: {tone}.\n\n"
        f"The operator's request: \"{user_prompt.strip()}\"\n"
        + (f"They want this headline: \"{headline.strip()}\"\n" if headline else "")
        + f"\n{layout_line}\n\n"
        "NUMBERS RULE — never invent a statistic. If you choose the 'stat' "
        "layout, EITHER use a figure that appears literally in the operator's "
        "request, OR pick the most relevant item from this approved list and "
        "copy its value + label verbatim:\n"
        f"{stats_block}\n"
        "Industry items must be framed as an estimate, never as a GymAxis "
        "customer result.\n\n"
        "Return STRICT JSON only (no prose, no fences):\n"
        "{\n"
        '  "layout": one of "hook" | "stat" | "feature" | "punchline",\n'
        f'  "caption": string (the post body, ≤{channel["caption_max_chars"]} chars),\n'
        f'  "hashtags": string[] ({channel["hashtag_min"]}-{channel["hashtag_max"]} items, each starting with #),\n'
        '  "card_headline": string (a COMPLETE 3-5 word headline, Title Case, '
        "no emoji, no trailing ellipsis),\n"
        '  "stat_value": string (ONLY for stat layout),\n'
        '  "stat_label": string (ONLY for stat layout),\n'
        '  "stat_kind": "product" | "industry" (ONLY for stat layout),\n'
        '  "feature_bullets": string[] (EXACTLY 3 items, ≤6 words each, '
        "concrete operator outcomes, ONLY for feature layout),\n"
        '  "punchline_setup": string (ONLY for punchline layout),\n'
        '  "punchline_payoff": string (≤8 words, dry wit, no emoji, ONLY for punchline)\n'
        "}\n"
    )


async def compose_post_from_prompt(db, *, channel_id: str, prompt: str,
                                   headline: Optional[str] = None,
                                   layout: Optional[str] = None) -> dict:
    """Render an on-brand poster from a free-form operator prompt and
    save it as a draft. Always uses the deterministic template engine —
    never a generative image."""
    channel = channel_by_id(channel_id)
    if not channel:
        raise ValueError(f"Unknown channel: {channel_id}")
    user_prompt = (prompt or "").strip()
    if not user_prompt and not (headline or "").strip():
        raise ValueError("Add a prompt or a headline")
    req_layout = (layout or "").strip().lower() or None
    if req_layout and req_layout not in _COMPOSE_LAYOUTS:
        req_layout = None

    text = await _llm_chat(
        build_compose_prompt(channel, user_prompt, headline=headline, layout=req_layout)
    )

    chosen = req_layout or (text.get("layout") or "hook").strip().lower()
    if chosen not in _COMPOSE_LAYOUTS:
        chosen = "hook"

    normalised_headline = clean_card_headline(
        text.get("card_headline") or headline or "",
        fallback=(headline or user_prompt[:40] or BRAND["name"]),
    )

    fields: dict = {
        "headline": normalised_headline or BRAND["name"],
        "subtitle": BRAND["tagline"],
    }
    if chosen == "stat":
        sv = (text.get("stat_value") or "").strip()
        sl = (text.get("stat_label") or "").strip()
        sk = "industry" if (text.get("stat_kind") == "industry") else "product"
        if not sv or not sl:  # safety net — never render an empty/invented stat
            s = PRODUCT_STATS[0]
            sv, sl, sk = s["value"], s["label"], "product"
        fields.update({"stat_value": sv, "stat_label": sl, "stat_kind": sk})
    elif chosen == "feature":
        bullets = [b for b in (text.get("feature_bullets") or [])
                   if isinstance(b, str) and b.strip()][:3]
        fields["bullets"] = bullets or [
            normalised_headline or "Built for operators",
            "Built for multi-site UK operators", "One platform — no spreadsheets",
        ]
    elif chosen == "punchline":
        fields["setup"] = (text.get("punchline_setup") or "").strip()
        fields["payoff"] = (text.get("punchline_payoff")
                            or normalised_headline or BRAND["name"]).strip()

    from utils.social_templates import render_social_card
    w, h = _card_dimensions(channel["image_aspect"], channel["image_size_px"])
    png = render_social_card(chosen, w=w, h=h, brand=BRAND, fields=fields,
                             logo_path=_resolve_logo_path())
    if png:
        image_url = "data:image/png;base64," + base64.b64encode(png).decode()
        image_model = f"prompt:{chosen}"
    else:
        image_url = render_branded_card_to_data_url(
            headline=normalised_headline, channel=channel, subtitle=BRAND["tagline"])
        image_model = "branded_card"

    hashtags = [h2 for h2 in (text.get("hashtags") or [])
                if isinstance(h2, str) and h2.startswith("#")][:channel["hashtag_max"]]
    caption = (text.get("caption") or "")[:channel["caption_max_chars"]]

    from utils.social_tone_check import check_draft_tone
    tone_check = check_draft_tone(caption, hashtags=hashtags, on_campaign=False)

    doc = {
        "id": _id(),
        "channel": channel_id,
        "status": "draft",
        "topic_id": "manual:prompt",
        "topic_kind": "manual",
        "topic_label": (user_prompt[:60] or normalised_headline or "Custom poster"),
        "caption": caption,
        "hashtags": hashtags,
        "video_script": None,
        "card_headline": normalised_headline or BRAND["name"],
        "image_brief": user_prompt,
        "image_url": image_url,
        "image_variant": chosen,
        "image_model": image_model,
        "audience": channel["audience"],
        "created_at": _now(),
        "updated_at": _now(),
        "generation_meta": {
            "model_text": "claude-sonnet-4-6",
            "source": "manual_prompt",
            "user_prompt": user_prompt,
            "requested_layout": req_layout,
            "on_campaign": False,
        },
        "tone_check": tone_check,
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
    "LAUNCH_ARCHETYPES",
    "channel_by_id",
    "feature_pillar_by_id",
    "pick_topic_for",
    "build_prompt",
    "build_launch_prompt",
    "pick_launch_archetype",
    "should_use_launch_tone",
    "get_active_launch_campaign",
    "render_branded_card_to_data_url",
    "render_nano_banana_image",
    "generate_post_for_channel",
    "compose_post_from_prompt",
    "build_compose_prompt",
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
