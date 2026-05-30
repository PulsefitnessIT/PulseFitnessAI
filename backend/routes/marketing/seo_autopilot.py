"""SEO Autopilot — Iter 220ad / Phase 2.

Soro-style ($200/mo) toolkit, built inside GymAxis so the master admin
can promote the product without paying the agency tax. Four moving
parts:

  1. Keyword research      → ``POST /api/marketing/seo/keywords/research``
  2. AI article writer     → ``POST /api/marketing/seo/articles/generate``
  3. Daily auto-publish    → ``POST /api/marketing/seo/autopilot/run``
  4. Rank / pipeline view  → ``GET  /api/marketing/seo/dashboard``

Articles are stored in the new ``seo_articles`` collection and rendered
publicly by ``frontend/.../Marketing/Blog/BlogPost.js`` falling back to
DB lookup when the slug isn't in the file-based registry.

Quality bar:
  • UK English, 1500 words, fitness-industry tone (matches Brand Kit).
  • H1 + 5-7 H2/H3, bullet lists, primary keyword in title + first
    paragraph + URL.
  • Q&A block at the end (3-5 pairs) → renders as FAQPage JSON-LD
    so ChatGPT / Perplexity / Google AI overviews can cite us.
  • Hero image via Gemini Nano Banana when the key is configured.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.ai_guardrails import (
    enforce_token_budget,
    record_ai_action,
    record_token_usage,
    sanitize_llm_markdown,
    sanitize_prompt,
)
from utils.web_security import sanitize_rich_text
from utils.seo_article_freshness import (
    build_recent_articles_context,
    check_article_uniqueness,
    find_similar_keywords,
    format_recent_articles_for_prompt,
    pick_next_archetype,
)
from utils.seo_keyword_discovery import autodiscover_top_up_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/seo", tags=["marketing-seo"])

# ── Defaults ───────────────────────────────────────────────────────

DEFAULT_TONE = (
    "Plain UK English, no buzzwords, no exclamation marks. "
    "Use short paragraphs, sentence-case headlines, and concrete "
    "operator examples (treadmills, free weights, peak hours, "
    "membership churn). Address the reader as 'you' — never 'we' as "
    "the gym."
)
DEFAULT_BRAND_BLURB = (
    "GymAxis is an operations + CRM platform for gyms and fitness "
    "operators — service-desk, equipment downtime tracking, member "
    "lifecycle CRM, and a Partner Engineer network of vetted "
    "field engineers. The canonical brand URL is "
    "https://gymaxisai.com — NEVER use any other domain (in particular "
    "do not invent 'gymaxis.io', 'gym-axis.com', 'gymaxis.co.uk' or "
    "similar). The marketing site lives at https://gymaxisai.com, "
    "the app at https://app.gymaxisai.com, and the demo-request "
    "landing page at https://gymaxisai.com/demo-request."
)
GYMAXIS_DOMAIN = "gymaxisai.com"
GYMAXIS_BASE_URL = "https://gymaxisai.com"
TARGET_WORDS = 1500


# Iter 220aq — domain-scrub safety net. Even with strong prompt
# constraints the LLM occasionally hallucinates "gymaxis.io" /
# "gym-axis.com" / "gymaxis.co.uk". Rewrite any such mention to the
# canonical ``gymaxisai.com``. Operates on Markdown + plain text;
# preserves the path / fragment portion of the URL where present.
_BAD_DOMAINS = (
    "gymaxis.io",
    "gym-axis.io",
    "gym-axis.com",
    "gymaxis.co.uk",
    "gymaxis.co",
    "gymaxis.net",
    "gymaxis.app",
)


def _scrub_brand_domain(text: str | None) -> str:
    if not text:
        return text or ""
    out = text
    for bad in _BAD_DOMAINS:
        # Case-insensitive replace while preserving the rest of the URL.
        # We rebuild via a regex to catch ``www.<bad>`` too.
        import re as _re
        pattern = _re.compile(
            r"(?:https?://)?(?:www\.)?" + _re.escape(bad),
            flags=_re.IGNORECASE,
        )
        out = pattern.sub(GYMAXIS_BASE_URL, out)
    # Collapse accidental double protocols left after the rewrite.
    out = out.replace("https://https://", "https://").replace("http://https://", "https://")
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _slugify(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or _id()[:8]


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(403, "SEO Autopilot is for the GymAxis master admin only.")


def _scrub(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ── Pydantic models ────────────────────────────────────────────────

class KeywordResearchPayload(BaseModel):
    seed_topic: str = Field(..., min_length=2, max_length=200)
    audience: Optional[str] = Field(None, max_length=120)
    competitor_urls: list[str] = Field(default_factory=list, max_length=8)
    count: int = Field(15, ge=1, le=40)


class KeywordPatch(BaseModel):
    status: Optional[str] = Field(None, pattern="^(queued|in_use|published|ignored|needs_review)$")
    notes: Optional[str] = Field(None, max_length=600)


class ArticleGeneratePayload(BaseModel):
    primary_keyword: str = Field(..., min_length=2, max_length=120)
    secondary_keywords: list[str] = Field(default_factory=list, max_length=8)
    angle: Optional[str] = Field(None, max_length=300)
    target_words: int = Field(TARGET_WORDS, ge=400, le=3000)
    publish_now: bool = False
    generate_hero_image: bool = True


class ArticlePatch(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    excerpt: Optional[str] = Field(None, max_length=600)
    body_md: Optional[str] = Field(None, max_length=80000)
    hero_image_url: Optional[str] = Field(None, max_length=2000)
    meta_description: Optional[str] = Field(None, max_length=300)
    status: Optional[str] = Field(None, pattern="^(draft|scheduled|published|archived)$")
    scheduled_for: Optional[str] = Field(None, max_length=40)
    qa_blocks: Optional[list[dict]] = None


# ── LLM helpers (Emergent LLM key + emergentintegrations) ──────────

def _emergent_key() -> Optional[str]:
    return os.environ.get("EMERGENT_LLM_KEY") or None


def _safe_json_extract(text: str) -> Optional[dict | list]:
    """Pull JSON out of LLM output. Models sometimes wrap in ```json … ```."""
    import json as _json
    if not text:
        return None
    try:
        return _json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"([\[{].*[\]}])", text, re.DOTALL)
    if m:
        try:
            return _json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    return None


async def _llm_text(system: str, prompt: str, *, session_id: str) -> Optional[str]:
    key = _emergent_key()
    if not key:
        logger.warning("[seo] EMERGENT_LLM_KEY missing")
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=key, session_id=session_id, system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        if isinstance(resp, str):
            return resp
        return getattr(resp, "text", str(resp))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[seo] llm_text failed: %s", exc)
        return None


async def _generate_hero_image(prompt: str, *, session_id: str) -> Optional[str]:
    """Returns a data: URL (PNG base64) or None."""
    key = _emergent_key()
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import (  # type: ignore
            LlmChat,
            UserMessage,
        )
        chat = LlmChat(
            api_key=key, session_id=session_id,
            system_message="You are a marketing art director for a fitness operations SaaS.",
        ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"],
        )
        msg = UserMessage(
            text=(
                f"{prompt}\n\n"
                "Create a 16:9 photographic editorial-style hero image. "
                "Modern gym setting, well-lit, professional and credible. "
                "No text overlays. No watermarks. No logos. "
                "Clean composition with negative space top-left for a headline overlay."
            ),
        )
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            return None
        first = images[0]
        return f"data:{first.get('mime_type', 'image/png')};base64,{first['data']}"
    except Exception as exc:  # noqa: BLE001
        logger.info("[seo] hero image gen failed: %s", exc)
        return None


# ── Public-ish: keyword research ───────────────────────────────────

@router.post("/keywords/research")
async def research_keywords(
    payload: KeywordResearchPayload,
    user: dict = Depends(get_current_user),
):
    """Use Claude to brainstorm SEO keywords for a topic. Returns the
    suggestions AND persists each one to ``seo_keywords`` so they show
    up in the Keywords tab ready to be promoted to articles."""
    _require_master_admin(user)

    prompt = (
        f"You are an experienced SEO strategist for the UK fitness "
        f"industry. Brand: {DEFAULT_BRAND_BLURB}\n\n"
        f"Seed topic: {payload.seed_topic}\n"
        f"Audience: {payload.audience or 'Gym owners, multi-site operators, fitness service managers'}\n"
        + (
            "Competitor URLs to consider:\n  - "
            + "\n  - ".join(payload.competitor_urls[:8])
            + "\n\n" if payload.competitor_urls else "\n"
        )
        + f"Produce exactly {payload.count} keyword targets with HIGH commercial "
        f"intent or HIGH informational intent (no low-volume head terms, no "
        f"generic 'best gym equipment' bait). Return STRICT JSON only — no prose, "
        f"no fences — as a list of objects with exactly these keys:\n"
        f"  - term: string\n"
        f"  - intent: one of 'informational'|'transactional'|'navigational'\n"
        f"  - difficulty: one of 'low'|'medium'|'high'\n"
        f"  - volume_estimate: one of 'low'|'medium'|'high'\n"
        f"  - rationale: 1 short sentence (<25 words)\n"
        f"Prioritise long-tail 4-7 word phrases — they convert better and rank faster."
    )

    raw = await _llm_text(
        "You are a senior SEO strategist. You output ONLY valid JSON.",
        prompt, session_id=f"seo-kw-{_id()}",
    )
    data = _safe_json_extract(raw or "")
    items: list[dict]
    if isinstance(data, list):
        items = [x for x in data if isinstance(x, dict) and x.get("term")]
    else:
        items = []

    # Fallback: if the LLM is unavailable, seed a useful but obvious set
    # so the UI is never empty during local dev / key outages.
    if not items:
        items = [
            {"term": f"{payload.seed_topic} for gyms",
             "intent": "informational", "difficulty": "medium",
             "volume_estimate": "medium",
             "rationale": "Direct match for the seed; classic top-of-funnel."},
        ]

    saved: list[dict] = []
    for it in items[: payload.count]:
        term = (it.get("term") or "").strip()[:160]
        if not term:
            continue
        # Iter 220bj — Layer 3: flag near-duplicate keywords at queue
        # time. We still save them (so the admin can see the dup), but
        # mark `near_duplicate_of` so the UI can warn before publish.
        similar = await find_similar_keywords(db, term, threshold=0.7)
        doc = {
            "id": _id(),
            "term": term,
            "intent": it.get("intent") or "informational",
            "difficulty": it.get("difficulty") or "medium",
            "volume_estimate": it.get("volume_estimate") or "medium",
            "rationale": (it.get("rationale") or "")[:300],
            "seed_topic": payload.seed_topic,
            "audience": payload.audience,
            "status": "needs_review" if similar else "queued",
            "target_article_id": None,
            "notes": "",
            "near_duplicates": similar[:5] if similar else [],
            "created_at": _now(), "updated_at": _now(),
        }
        await db.seo_keywords.insert_one(doc)
        saved.append(_scrub(dict(doc)))
    return {"keywords": saved, "count": len(saved)}


@router.get("/keywords")
async def list_keywords(
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    q: dict = {}
    if status:
        q["status"] = status
    rows = await db.seo_keywords.find(q, {"_id": 0}).sort(
        "created_at", -1).limit(min(max(limit, 1), 300)).to_list(300)
    return {"keywords": rows}


@router.patch("/keywords/{keyword_id}")
async def patch_keyword(
    keyword_id: str,
    payload: KeywordPatch,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not updates:
        existing = await db.seo_keywords.find_one({"id": keyword_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Keyword not found")
        return _scrub(existing)
    updates["updated_at"] = _now()
    res = await db.seo_keywords.update_one({"id": keyword_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Keyword not found")
    return _scrub(await db.seo_keywords.find_one({"id": keyword_id}, {"_id": 0}))


@router.delete("/keywords/{keyword_id}")
async def delete_keyword(
    keyword_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    res = await db.seo_keywords.delete_one({"id": keyword_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Keyword not found")
    return {"ok": True}


# ── AI article generation ──────────────────────────────────────────

async def _generate_article_payload(
    primary_keyword: str,
    secondary_keywords: list[str],
    angle: Optional[str],
    target_words: int,
    *,
    recent_context: str = "",
    archetype: Optional[dict] = None,
) -> dict:
    """Return a structured article dict {title, excerpt, body_md,
    meta_description, qa_blocks, tags}."""
    # Iter 220at / F-11 — sanitise free-form caller input even though
    # it's master-admin-only. Strips control chars, clamps length so
    # a smuggled "ignore previous instructions" payload at least can't
    # be 60 KB long.
    primary_keyword = sanitize_prompt(primary_keyword, max_chars=200)
    angle = sanitize_prompt(angle, max_chars=400) if angle else angle
    secondary_keywords = [sanitize_prompt(s, max_chars=160) for s in (secondary_keywords or [])]
    sec_block = (
        f"Also weave in these secondary keywords naturally (at most twice each, "
        f"never stuffed): {', '.join(secondary_keywords)}.\n"
        if secondary_keywords else ""
    )
    angle_block = f"Editorial angle: {angle}\n" if angle else ""

    # Iter 220bj — Layer 1+2: feed the LLM (a) the last published
    # articles so it can't echo them and (b) a least-recently-used
    # editorial archetype so every article opens with a different
    # scenario.
    archetype_block = ""
    if archetype:
        archetype_block = (
            f"Editorial archetype for THIS article (you MUST follow it): "
            f"{archetype.get('label', '')}.\n"
            f"Archetype guidance: {archetype.get('prompt_hint', '')}\n\n"
        )
    recent_block = (recent_context + "\n") if recent_context else ""

    prompt = (
        f"Write a long-form blog article for the GymAxis blog. "
        f"{DEFAULT_BRAND_BLURB}\n\n"
        f"Tone: {DEFAULT_TONE}\n\n"
        f"Primary keyword: {primary_keyword}\n"
        f"{sec_block}{angle_block}"
        f"Target length: {target_words} words (±10%).\n\n"
        f"{archetype_block}"
        f"{recent_block}"
        "Structural rules:\n"
        "  • H1 must include the primary keyword.\n"
        "  • 5–7 H2 sub-sections; H3 only where genuinely useful.\n"
        "  • Open with a concrete operator-life scenario (not 'In today's…') "
        "    AND do not reuse the openers of the recent articles above.\n"
        "  • At least one numbered list and one bullet list.\n"
        "  • Close with a single 1-line CTA inviting the reader to book a "
        f"GymAxis demo at {GYMAXIS_BASE_URL}/demo-request.\n"
        "  • Never use any domain other than gymaxisai.com — in "
        "particular do NOT write gymaxis.io, gymaxis.com, or any other "
        "variation. The only valid URLs are under gymaxisai.com.\n"
        "  • End with 4 FAQ Q&A pairs — concise, scannable, optimised for "
        "ChatGPT / Perplexity citation.\n\n"
        "Return STRICT JSON only (no prose, no fences) with this shape:\n"
        "{\n"
        '  "title": string (≤70 chars, primary keyword present),\n'
        '  "excerpt": string (≤180 chars, hook the reader),\n'
        '  "meta_description": string (≤160 chars, primary keyword present),\n'
        '  "tags": string[] (3-5 short tags),\n'
        '  "body_md": string (full article in Markdown),\n'
        '  "qa_blocks": [ { "question": string, "answer": string } ] (4 pairs)\n'
        "}\n"
    )

    raw = await _llm_text(
        "You are a senior fitness-industry SEO copywriter who outputs ONLY valid JSON.",
        prompt, session_id=f"seo-article-{_id()}",
    )
    data = _safe_json_extract(raw or "") or {}
    if not isinstance(data, dict):
        data = {}

    # Reasonable fallbacks for any missing field — never let the UI break.
    title = (data.get("title") or primary_keyword.title())[:200]
    excerpt = (data.get("excerpt") or
               f"What we've learned about {primary_keyword} from the gym ops trenches.")[:600]
    body_md = data.get("body_md") or (
        f"# {title}\n\n"
        f"Article generation is temporarily unavailable. Please regenerate "
        f"once the AI service is back online.\n"
    )
    meta_description = (data.get("meta_description") or excerpt)[:300]
    tags = data.get("tags") or [primary_keyword, "operations", "gym"]
    qa_blocks = data.get("qa_blocks") or []
    if not isinstance(qa_blocks, list):
        qa_blocks = []

    # Iter 220aq — domain-scrub safety net. The LLM occasionally invents
    # ``gymaxis.io`` / ``gym-axis.com`` even when the prompt forbids it.
    # Rewrite any such mention to the canonical ``gymaxisai.com``.
    title = _scrub_brand_domain(title)
    excerpt = _scrub_brand_domain(excerpt)
    body_md = _scrub_brand_domain(body_md)
    meta_description = _scrub_brand_domain(meta_description)
    qa_blocks = [
        {"question": _scrub_brand_domain(str(q.get("question", ""))),
         "answer": _scrub_brand_domain(str(q.get("answer", "")))}
        for q in qa_blocks if isinstance(q, dict)
    ]

    # Iter 220at / F-14 — strip dangerous tags (<script>, <iframe>,
    # on*= handlers, javascript: URLs) from LLM-generated markdown so
    # the blog renderer, PDF export, and email digests can't be used
    # to ship XSS even if the model gets jailbroken into emitting HTML.
    title = sanitize_llm_markdown(title)
    excerpt = sanitize_llm_markdown(excerpt)
    body_md = sanitize_llm_markdown(body_md)
    meta_description = sanitize_llm_markdown(meta_description)
    qa_blocks = [
        {"question": sanitize_llm_markdown(q.get("question", "")),
         "answer": sanitize_llm_markdown(q.get("answer", ""))}
        for q in qa_blocks if isinstance(q, dict)
    ]

    # Iter 220av / F-04 — second-pass bleach allow-list. Even after the
    # regex scrub above, run the bleach allow-list against any HTML the
    # LLM tried to slip in via Markdown's inline-HTML feature. Bleach
    # is the canonical OWASP-recommended sanitiser and gives us a
    # belt-and-braces guarantee for the blog renderer.
    title = sanitize_rich_text(title)
    excerpt = sanitize_rich_text(excerpt)
    body_md = sanitize_rich_text(body_md)
    meta_description = sanitize_rich_text(meta_description)
    qa_blocks = [
        {"question": sanitize_rich_text(q.get("question", "")),
         "answer": sanitize_rich_text(q.get("answer", ""))}
        for q in qa_blocks if isinstance(q, dict)
    ]

    return {
        "title": title, "excerpt": excerpt, "body_md": body_md,
        "meta_description": meta_description, "tags": tags[:6],
        "qa_blocks": qa_blocks[:6],
        "word_count": len((body_md or "").split()),
    }


# ── Distribution Engine — Iter 220ae ────────────────────────────────
#
# Given a published article, generate ready-to-post snippets for each
# channel. We store everything in ``seo_distributions`` so the operator
# can copy/edit/republish without re-spending LLM tokens. Channels:
#
#   * linkedin   — 5 hooks-first posts, 1 per "angle" we ask Claude
#                  to riff on (problem framing, contrarian take,
#                  data point, mini case-study, direct CTA).
#   * x_thread   — 1 X thread of 6-9 tweets, each ≤270 chars,
#                  punchy and scroll-stopping.
#   * reddit     — 1 long-form summary written in a "you-tone" suitable
#                  for r/gymsnark, r/personaltraining, r/smallbusiness;
#                  includes subreddit suggestions.


class DistributePayload(BaseModel):
    channels: list[str] = Field(
        default_factory=lambda: ["linkedin", "x_thread", "reddit"],
        max_length=3,
    )


async def _spin_distributions(article: dict, channels: list[str]) -> dict:
    """Ask Claude to spin a single article into channel-tailored posts.
    Returns ``{linkedin: [str,...], x_thread: [str,...], reddit: {...}}``
    with safe fallbacks when the LLM is unreachable."""
    title = article.get("title") or "Untitled"
    excerpt = article.get("excerpt") or ""
    body_excerpt = (article.get("body_md") or "")[:6000]
    primary = article.get("primary_keyword") or ""
    blog_url = f"https://www.gymaxisai.com/blog/{article.get('slug')}"

    prompt = (
        f"You are spinning a published GymAxis blog article into channel-"
        f"native social posts to drive readers back to it. "
        f"{DEFAULT_BRAND_BLURB}\n\n"
        f"Tone: {DEFAULT_TONE}\n\n"
        f"Article title: {title}\n"
        f"Excerpt: {excerpt}\n"
        f"Primary keyword: {primary}\n"
        f"Link to use at the end of each post: {blog_url}\n\n"
        f"Article body (excerpt):\n{body_excerpt}\n\n"
        "Produce STRICT JSON only — no prose, no fences — with this shape:\n"
        "{\n"
        '  "linkedin": [ string, string, string, string, string ],\n'
        '  "x_thread": [ string, ... ] (6-9 tweets, each ≤270 chars),\n'
        '  "reddit": { "title": string (≤95 chars), '
        '"body": string (350-600 words), "subreddits": [string,...] }\n'
        "}\n\n"
        "LinkedIn rules:\n"
        "  • Each post is independent — same article, different angle.\n"
        "  • Start with a 1-line hook on its own line.\n"
        "  • 120-300 words.\n"
        "  • End with the link on its own line.\n"
        "  • 3-5 hashtags max, last line, lower-case if possible.\n"
        "X rules:\n"
        "  • Tweet 1 = bold hook.\n"
        "  • Last tweet = link + 1-line CTA.\n"
        "  • No tweet exceeds 270 characters.\n"
        "Reddit rules:\n"
        "  • Title is a sincere question or insight, never clickbait.\n"
        "  • Body has 2-3 sub-headlines (use ## markdown).\n"
        "  • Reference the article naturally, never spam-shilling.\n"
        "  • Include 3-5 subreddit names without the 'r/' prefix."
    )

    raw = await _llm_text(
        "You are a social-media copywriter that outputs ONLY valid JSON.",
        prompt, session_id=f"seo-dist-{_id()}",
    )
    data = _safe_json_extract(raw or "")
    if not isinstance(data, dict):
        data = {}

    out: dict = {}
    if "linkedin" in channels:
        linkedin = data.get("linkedin") if isinstance(data.get("linkedin"), list) else []
        # Always 5 — pad with a basic templated post if Claude under-delivers.
        while len(linkedin) < 5:
            linkedin.append(
                f"{title}\n\n"
                f"We just published a deep-dive on {primary or 'gym operations'}. "
                f"If you're tackling this in 2026, this is worth 7 minutes:\n\n"
                f"{blog_url}\n\n#gymoperations #fitnesstech"
            )
        out["linkedin"] = [str(x)[:3000] for x in linkedin[:5]]

    if "x_thread" in channels:
        thread = data.get("x_thread") if isinstance(data.get("x_thread"), list) else []
        if not thread:
            thread = [
                f"{title} — the playbook 🧵",
                f"1/ Most gym operators we talk to are losing 6-8 hours/week to "
                f"{primary or 'this exact problem'}.",
                "2/ The fix isn't more software. It's clearer ownership.",
                f"3/ Full write-up here → {blog_url}",
            ]
        out["x_thread"] = [str(x)[:280] for x in thread[:9]]

    if "reddit" in channels:
        reddit = data.get("reddit") if isinstance(data.get("reddit"), dict) else {}
        out["reddit"] = {
            "title": (reddit.get("title") or title)[:120],
            "body": (reddit.get("body") or
                     f"We just published a deep-dive on this. Curious what others think.\n\n{blog_url}")[:8000],
            "subreddits": (reddit.get("subreddits") if isinstance(reddit.get("subreddits"), list)
                           else ["gymsnark", "personaltraining", "smallbusiness"])[:6],
        }

    # Iter 220aq — scrub any hallucinated domain across every channel
    # so the public-facing post never leaks ``gymaxis.io`` etc.
    if "linkedin" in out:
        out["linkedin"] = [_scrub_brand_domain(s) for s in out["linkedin"]]
    if "x_thread" in out:
        out["x_thread"] = [_scrub_brand_domain(s) for s in out["x_thread"]]
    if "reddit" in out and isinstance(out["reddit"], dict):
        out["reddit"]["title"] = _scrub_brand_domain(out["reddit"].get("title"))
        out["reddit"]["body"] = _scrub_brand_domain(out["reddit"].get("body"))
    return out


@router.post("/articles/{article_id}/distribute")
async def distribute_article(
    article_id: str,
    payload: DistributePayload,
    user: dict = Depends(get_current_user),
):
    """Spin a published article into channel-native social posts.

    Idempotent on (article_id) — re-running OVERWRITES the existing
    distribution document so operators can re-spin if they don't like
    Claude's first take."""
    _require_master_admin(user)

    article = await db.seo_articles.find_one({"id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(404, "Article not found")
    if article.get("status") not in ("published", "draft"):
        raise HTTPException(400, "Only draft or published articles can be distributed.")

    channels = list({c for c in payload.channels
                     if c in ("linkedin", "x_thread", "reddit")})
    if not channels:
        raise HTTPException(400, "Pick at least one channel.")

    content = await _spin_distributions(article, channels)

    now = _now()
    doc = {
        "id": _id(),
        "article_id": article_id,
        "article_slug": article.get("slug"),
        "article_title": article.get("title"),
        "channels": channels,
        "content": content,
        "created_by": user.get("id"),
        "created_at": now, "updated_at": now,
    }
    # Idempotent — overwrite previous spin for this article.
    await db.seo_distributions.delete_many({"article_id": article_id})
    await db.seo_distributions.insert_one(doc)
    return _scrub(dict(doc))


@router.get("/articles/{article_id}/distributions")
async def get_article_distribution(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    doc = await db.seo_distributions.find_one({"article_id": article_id}, {"_id": 0})
    if not doc:
        return {"distribution": None}
    return {"distribution": doc}


# ── Iter 220af — 1-click publish share-URLs ──────────────────────────
#
# We don't store LinkedIn / X OAuth tokens (those are user-specific,
# need consent flows, and would require us to host the public-blog URL
# behind a real domain). Instead we generate the canonical platform
# share-intent URLs and record a "posted" stamp the moment the master
# admin opens them. The browser-side window.open() takes 1 click;
# clicking "Share" inside LinkedIn / X is the 2nd. Net = 2-click post.

class PublishSharePayload(BaseModel):
    channel: str = Field(..., pattern="^(linkedin|x)$")
    index: int = Field(0, ge=0, le=8)


def _linkedin_share_url(text: str, blog_url: str) -> str:
    import urllib.parse as _u
    params = {"url": blog_url, "summary": text[:1200]}
    return "https://www.linkedin.com/sharing/share-offsite/?" + _u.urlencode(params)


def _x_share_url(text: str, blog_url: str) -> str:
    import urllib.parse as _u
    # X (Twitter) intent: 280 chars incl. URL, give 25 char headroom for URL.
    snippet = text[:240]
    params = {"text": snippet, "url": blog_url}
    return "https://twitter.com/intent/tweet?" + _u.urlencode(params)


@router.post("/articles/{article_id}/publish-share")
async def publish_share(
    article_id: str,
    payload: PublishSharePayload,
    user: dict = Depends(get_current_user),
):
    """Return a platform-native share-intent URL for the given channel +
    post index AND stamp it as 'posted' in ``seo_distributions``. The
    caller (browser) opens the returned URL in a new tab — the master
    admin then taps the platform's own Share/Post button to publish."""
    _require_master_admin(user)

    article = await db.seo_articles.find_one({"id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(404, "Article not found")

    dist = await db.seo_distributions.find_one({"article_id": article_id}, {"_id": 0})
    if not dist:
        raise HTTPException(400, "Spin posts first — no distribution found.")

    blog_url = f"https://www.gymaxisai.com/blog/{article.get('slug')}"

    if payload.channel == "linkedin":
        posts = (dist.get("content") or {}).get("linkedin") or []
        if not posts:
            raise HTTPException(400, "No LinkedIn posts to publish.")
        idx = min(payload.index, len(posts) - 1)
        text = str(posts[idx])
        share_url = _linkedin_share_url(text, blog_url)
        stamp_key = f"published.linkedin.{idx}"
    else:  # x
        thread = (dist.get("content") or {}).get("x_thread") or []
        if not thread:
            raise HTTPException(400, "No X thread to publish.")
        # For X we always post tweet 1 (the hook). The thread is best
        # posted manually as a reply chain on X — link goes in the last
        # tweet, which we still expose via the Copy buttons.
        idx = 0
        text = str(thread[0])
        share_url = _x_share_url(text, blog_url)
        stamp_key = "published.x.0"

    now = _now()
    await db.seo_distributions.update_one(
        {"article_id": article_id},
        {"$set": {
            stamp_key: {"posted_at": now, "posted_by": user.get("id"),
                        "share_url": share_url},
            "updated_at": now,
        }},
    )
    return {"share_url": share_url, "channel": payload.channel,
            "index": idx, "posted_at": now}


# ── End Iter 220ae/af distribution block ────────────────────────────


@router.post("/articles/generate")
async def generate_article(
    payload: ArticleGeneratePayload,
    user: dict = Depends(get_current_user),
):
    """Generate a full draft article from the primary keyword. Returns
    the inserted ``seo_articles`` row."""
    _require_master_admin(user)

    # Iter 220at / F-16 — per-tenant daily token budget. Long-form
    # articles burn ~4 k tokens each; guard against runaway costs.
    await enforce_token_budget(user.get("organization_id"), est_tokens=4000)

    # Iter 220bj — Layers 1 + 2: feed recent-articles context + a
    # least-recently-used archetype so consecutive articles open with
    # genuinely different scenarios.
    recent_articles = await build_recent_articles_context(db, limit=8)
    recent_context = format_recent_articles_for_prompt(recent_articles)
    archetype = await pick_next_archetype(db)

    text = await _generate_article_payload(
        payload.primary_keyword, payload.secondary_keywords,
        payload.angle, payload.target_words,
        recent_context=recent_context, archetype=archetype,
    )

    # Iter 220bj — Layer 4: post-generation uniqueness gate. If the
    # draft is too close to an existing published article, regenerate
    # ONCE with a hardened "must be different" instruction. If still
    # too similar, mark needs_review instead of auto-publishing.
    uniq = await check_article_uniqueness(
        db, title=text["title"], body_md=text["body_md"], threshold=0.6,
    )
    regenerated = False
    if not uniq["ok"] and uniq.get("best_match"):
        regenerated = True
        match = uniq["best_match"]
        harden_angle = (
            f"{payload.angle or ''}\n\n"
            "IMPORTANT: a previous draft was rejected for being too "
            f"similar to '{match.get('title', '')}'. Take a FUNDAMENTALLY "
            "different angle, audience, opener, and structural beats. "
            "Do not echo that article in any way."
        ).strip()
        text = await _generate_article_payload(
            payload.primary_keyword, payload.secondary_keywords,
            harden_angle, payload.target_words,
            recent_context=recent_context, archetype=archetype,
        )
        uniq = await check_article_uniqueness(
            db, title=text["title"], body_md=text["body_md"], threshold=0.6,
        )

    hero_url: Optional[str] = None
    if payload.generate_hero_image:
        hero_url = await _generate_hero_image(
            prompt=f"Hero image illustrating: {text['title']}. {payload.primary_keyword}.",
            session_id=f"seo-hero-{_id()}",
        )

    now = _now()
    slug = _slugify(text["title"])
    # Uniqueness — append short id if slug exists.
    if await db.seo_articles.find_one({"slug": slug}, {"_id": 0, "id": 1}):
        slug = f"{slug}-{_id()[:6]}"

    # Iter 220bj — when the post-generation uniqueness check still
    # fails after a regenerate, downgrade to needs_review so master
    # admin can decide rather than auto-publishing a near-duplicate.
    publish_now = bool(payload.publish_now)
    final_status: str
    if publish_now and not uniq["ok"]:
        final_status = "needs_review"
    elif publish_now:
        final_status = "published"
    else:
        final_status = "draft"

    doc = {
        "id": _id(),
        "slug": slug,
        "title": text["title"],
        "excerpt": text["excerpt"],
        "body_md": text["body_md"],
        "meta_description": text["meta_description"],
        "tags": text["tags"],
        "qa_blocks": text["qa_blocks"],
        "word_count": text["word_count"],
        "read_time_min": max(1, round(text["word_count"] / 220)),
        "primary_keyword": payload.primary_keyword,
        "secondary_keywords": payload.secondary_keywords,
        "hero_image_url": hero_url,
        "hero_image_alt": text["title"],
        "status": final_status,
        "published_at": now if final_status == "published" else None,
        "scheduled_for": None,
        "metrics": {"views": 0, "organic_visits": 0},
        # Iter 220bj — freshness telemetry
        "archetype_id": (archetype or {}).get("id"),
        "regenerated_for_freshness": regenerated,
        "uniqueness_score": uniq.get("best_score"),
        "uniqueness_best_match_id": (uniq.get("best_match") or {}).get("id"),
        "created_by": user.get("id"),
        "created_at": now, "updated_at": now,
    }
    await db.seo_articles.insert_one(doc)
    # Iter 220at — token-spend telemetry + AI action audit.
    await record_token_usage(
        user.get("organization_id"),
        tokens=max(2000, (text.get("word_count") or 0) * 4),
        surface="seo.generate_article",
    )
    await record_ai_action(
        user, action="seo.generate_article",
        payload={"primary_keyword": payload.primary_keyword,
                 "article_id": doc["id"], "slug": slug,
                 "publish_now": bool(payload.publish_now)},
    )
    return _scrub(dict(doc))


# ── Article CRUD ───────────────────────────────────────────────────

@router.get("/articles")
async def list_articles(
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    q: dict = {}
    if status:
        q["status"] = status
    rows = await db.seo_articles.find(q, {"_id": 0, "body_md": 0}).sort(
        "updated_at", -1).limit(min(max(limit, 1), 300)).to_list(300)
    return {"articles": rows}


@router.get("/articles/{article_id}")
async def get_article(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    doc = await db.seo_articles.find_one(
        {"$or": [{"id": article_id}, {"slug": article_id}]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Article not found")
    return doc


@router.patch("/articles/{article_id}")
async def patch_article(
    article_id: str,
    payload: ArticlePatch,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not updates:
        existing = await db.seo_articles.find_one({"id": article_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Article not found")
        return _scrub(existing)
    # Side-effects when transitioning to "published".
    if updates.get("status") == "published":
        existing = await db.seo_articles.find_one(
            {"id": article_id}, {"_id": 0, "published_at": 1},
        )
        if existing and not existing.get("published_at"):
            updates["published_at"] = _now()
    if updates.get("body_md"):
        wc = len(updates["body_md"].split())
        updates["word_count"] = wc
        updates["read_time_min"] = max(1, round(wc / 220))
    updates["updated_at"] = _now()
    res = await db.seo_articles.update_one({"id": article_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Article not found")
    return _scrub(await db.seo_articles.find_one({"id": article_id}, {"_id": 0}))


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    _require_master_admin(user)
    res = await db.seo_articles.update_one(
        {"id": article_id},
        {"$set": {"status": "archived", "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Article not found")
    return {"ok": True}


@router.post("/autopilot/run")
async def run_autopilot(user: dict = Depends(get_current_user)):
    """Pick the next queued keyword and generate + publish an article.
    Designed to be hit by a cron-style scheduler (1 article/day).

    Iter 220bk — before pulling the next keyword we top up the queue
    via the GDPR-safe auto-discovery feeder, so the master admin no
    longer has to keep manually researching seed topics."""
    _require_master_admin(user)

    cfg = await _load_config()
    auto_disc_enabled = cfg.get("auto_discovery_enabled", True)
    if auto_disc_enabled:
        try:
            await autodiscover_top_up_queue(
                db,
                queue_min=int(cfg.get("queue_min_threshold", 3)),
                queue_target=int(cfg.get("queue_target_size", 8)),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[autopilot] auto-discovery top-up failed: {exc}")

    next_kw = await db.seo_keywords.find_one(
        {"status": "queued"},
        {"_id": 0},
        sort=[("created_at", 1)],
    )
    if not next_kw:
        return {"ok": False, "reason": "no queued keywords"}

    payload = ArticleGeneratePayload(
        primary_keyword=next_kw["term"],
        secondary_keywords=[],
        angle=next_kw.get("rationale"),
        publish_now=True,
        generate_hero_image=True,
    )
    article = await generate_article(payload, user)
    # Iter 220bk — propagate discovery provenance onto the article so
    # gap-analysis & dashboards can attribute auto-discovered articles.
    article_updates: dict = {}
    if next_kw.get("discovery_pillar_id"):
        article_updates["discovery_pillar_id"] = next_kw["discovery_pillar_id"]
    if next_kw.get("source"):
        article_updates["discovery_source"] = next_kw["source"]
    if next_kw.get("discovery_signal"):
        article_updates["discovery_signal"] = next_kw["discovery_signal"]
    if article_updates:
        await db.seo_articles.update_one(
            {"id": article["id"]}, {"$set": article_updates},
        )
    await db.seo_keywords.update_one(
        {"id": next_kw["id"]},
        {"$set": {"status": "published",
                  "target_article_id": article["id"],
                  "updated_at": _now()}},
    )
    return {"ok": True, "keyword_id": next_kw["id"], "article": article}


# ── Daily autopilot status (Iter 220af) + config (Iter 220ai) ─────


def _config_collection():
    return db.seo_autopilot_config


async def _load_config() -> dict:
    """Return the live autopilot config. DB-backed so the master admin
    can flip enabled / change hour without redeploying. Falls back to
    env vars on first run so existing installs upgrade cleanly."""
    doc = await _config_collection().find_one({"id": "singleton"}, {"_id": 0})
    if doc:
        return doc
    # Seed from env on first read so the toggle UI shows the current
    # deployment behaviour.
    hour_env = os.environ.get("SEO_AUTOPILOT_HOUR", "9")
    try:
        hour = int(hour_env)
    except ValueError:
        hour = 9
    return {
        "id": "singleton",
        "enabled": os.environ.get("SEO_AUTOPILOT_ENABLED", "1") != "0",
        "hour_uk": max(0, min(23, hour)),
        # Iter 220bk — auto-discovery feeder defaults
        "auto_discovery_enabled": True,
        "queue_min_threshold": 3,
        "queue_target_size": 8,
        "updated_at": None,
        "updated_by": None,
    }


class AutopilotConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    hour_uk: Optional[int] = Field(None, ge=0, le=23)
    auto_discovery_enabled: Optional[bool] = None
    queue_min_threshold: Optional[int] = Field(None, ge=0, le=50)
    queue_target_size: Optional[int] = Field(None, ge=1, le=50)


@router.get("/autopilot/status")
async def autopilot_status(user: dict = Depends(get_current_user)):
    """Return the configured scheduler hour, today's London date, and
    whether the daily job has already fired today."""
    _require_master_admin(user)
    cfg = await _load_config()
    london = _london_now()
    today = london.date().isoformat()
    last = await db.seo_autopilot_runs.find_one(
        {}, {"_id": 0}, sort=[("date", -1)],
    )
    ran_today = bool(last and last.get("date") == today)
    return {
        "enabled": bool(cfg.get("enabled")),
        "hour_uk": int(cfg.get("hour_uk", 9)),
        "auto_discovery_enabled": bool(cfg.get("auto_discovery_enabled", True)),
        "queue_min_threshold": int(cfg.get("queue_min_threshold", 3)),
        "queue_target_size": int(cfg.get("queue_target_size", 8)),
        "london_now": london.isoformat(),
        "ran_today": ran_today,
        "last_run": last or None,
        "config_updated_at": cfg.get("updated_at"),
        "config_updated_by": cfg.get("updated_by"),
    }


@router.put("/autopilot/config")
async def update_autopilot_config(
    payload: AutopilotConfigPayload,
    user: dict = Depends(get_current_user),
):
    """Update the daily-autopilot schedule from the UI. Persists to
    ``seo_autopilot_config`` (read by the background loop on every
    iteration). Setting ``enabled = false`` cleanly pauses the loop
    without restarting the backend."""
    _require_master_admin(user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
               if v is not None}
    if not updates:
        return await _load_config()
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("id")
    await _config_collection().update_one(
        {"id": "singleton"},
        {"$set": updates, "$setOnInsert": {"id": "singleton"}},
        upsert=True,
    )
    return await _load_config()


# ── Iter 220bk — Auto-discovery feeder (GDPR-safe) ───────────────────


@router.post("/keywords/auto-discover")
async def run_keyword_auto_discovery(user: dict = Depends(get_current_user)):
    """Manually trigger the auto-discovery feeder. Used by master admin
    when they want to top up the queue without waiting for the next
    scheduled article run.

    Honours the same ``queue_min_threshold`` + ``queue_target_size``
    config the daily scheduler uses. All platform-data signals enforce
    k-anonymity (k=5) and number bucketing before any aggregate leaves
    the database."""
    _require_master_admin(user)
    cfg = await _load_config()
    if not cfg.get("auto_discovery_enabled", True):
        return {"ok": False, "reason": "auto_discovery_disabled"}
    result = await autodiscover_top_up_queue(
        db,
        queue_min=int(cfg.get("queue_min_threshold", 3)),
        queue_target=int(cfg.get("queue_target_size", 8)),
    )
    await record_ai_action(
        user, action="seo.auto_discover",
        payload={"added_count": result.get("added_count", 0),
                 "skipped": result.get("skipped", False)},
    )
    return result


@router.get("/keywords/discovery-feed")
async def discovery_feed(
    limit: int = 30,
    user: dict = Depends(get_current_user),
):
    """List the most recent auto-discovered keywords so the admin can
    see what Claude has been feeding the queue + the GDPR-safe
    metadata behind each."""
    _require_master_admin(user)
    rows = await db.seo_keywords.find(
        {"source": {"$in": ["auto_pillar", "auto_signal", "auto_gap"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(min(max(limit, 1), 100)).to_list(100)
    return {"keywords": rows, "count": len(rows)}


# ── Iter 220bj — Duplicate-content audit / archive ────────────────────


@router.get("/articles/duplicates")
async def list_duplicate_articles(
    threshold: float = 0.6,
    user: dict = Depends(get_current_user),
):
    """Scan all published articles and return pairs whose
    title+opener overlap exceeds ``threshold`` (0.6 by default). Used
    by master admin to find historical duplicates so they can be
    archived or rewritten."""
    _require_master_admin(user)
    from utils.seo_article_freshness import article_similarity_score, _first_paragraph

    cursor = db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "id": 1, "title": 1, "slug": 1, "body_md": 1, "published_at": 1},
    )
    articles = [a async for a in cursor]
    pairs: list[dict] = []
    for i, a in enumerate(articles):
        a_open = _first_paragraph(a.get("body_md"), max_chars=600)
        for b in articles[i + 1:]:
            b_open = _first_paragraph(b.get("body_md"), max_chars=600)
            score = article_similarity_score(
                a.get("title", ""), a_open,
                b.get("title", ""), b_open,
            )
            if score >= threshold:
                pairs.append({
                    "score": score,
                    "a": {"id": a.get("id"), "slug": a.get("slug"),
                          "title": a.get("title"),
                          "published_at": a.get("published_at")},
                    "b": {"id": b.get("id"), "slug": b.get("slug"),
                          "title": b.get("title"),
                          "published_at": b.get("published_at")},
                })
    pairs.sort(key=lambda p: -p["score"])
    return {"pairs": pairs, "threshold": threshold, "scanned": len(articles)}


@router.post("/articles/{article_id}/archive")
async def archive_article(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    """Hard-archive an article — public blog & list endpoints already
    filter ``status=archived`` so the post disappears immediately."""
    _require_master_admin(user)
    res = await db.seo_articles.update_one(
        {"id": article_id},
        {"$set": {"status": "archived", "updated_at": _now(),
                  "archived_by": user.get("id")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Article not found")
    return {"ok": True, "id": article_id, "status": "archived"}


# ── Manual "Run now" trigger (Iter 220ai) ─────────────────────────


@router.post("/autopilot/run-now")
async def run_autopilot_now(user: dict = Depends(get_current_user)):
    """Manually trigger today's autopilot run. Same logic as the daily
    loop — but stamps ``seo_autopilot_runs`` with ``manual=true`` so the
    daily loop's idempotency check prevents a double-fire later today."""
    _require_master_admin(user)
    london = _london_now()
    today = london.date().isoformat()
    if await _autopilot_already_ran_today(today):
        return {"ok": False, "reason": "already ran today", "date": today}
    result = await run_autopilot(user)
    stamp = {"manual": True, "ran_at": _now(), "result": result}
    await db.seo_autopilot_runs.update_one(
        {"date": today},
        {"$set": {"date": today, **stamp}},
        upsert=True,
    )
    return {"ok": True, "date": today, "result": result}


# ── Dashboard ──────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    _require_master_admin(user)
    [kw_total, kw_queued, kw_pub, art_total, art_pub, art_draft] = await asyncio_gather(
        db.seo_keywords.count_documents({}),
        db.seo_keywords.count_documents({"status": "queued"}),
        db.seo_keywords.count_documents({"status": "published"}),
        db.seo_articles.count_documents({"status": {"$ne": "archived"}}),
        db.seo_articles.count_documents({"status": "published"}),
        db.seo_articles.count_documents({"status": "draft"}),
    )
    recent = await db.seo_articles.find(
        {"status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "slug": 1, "title": 1, "status": 1,
         "published_at": 1, "updated_at": 1, "primary_keyword": 1,
         "metrics": 1, "word_count": 1, "read_time_min": 1,
         "hero_image_url": 1},
    ).sort("updated_at", -1).limit(10).to_list(10)
    # Iter 220ai — top 5 published articles by view count, for the
    # Dashboard "Top performers" tile.
    top_performers = await db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "id": 1, "slug": 1, "title": 1,
         "metrics": 1, "primary_keyword": 1, "published_at": 1,
         "read_time_min": 1},
    ).sort("metrics.views", -1).limit(5).to_list(5)
    # Sum total views across all published articles — useful headline
    # tile separate from per-article performance.
    total_views = 0
    # Iter 220am — snapshot each published article's running view
    # total once per day so we can show "+47% this week" on the
    # dashboard. Two cheap ops per published article (find_one +
    # update_one) — fine at our scale.
    today_iso = _london_now().date().isoformat()
    views_today: dict[str, int] = {}
    async for doc in db.seo_articles.find(
        {"status": "published"}, {"_id": 0, "id": 1, "metrics": 1},
    ):
        v = int((doc.get("metrics") or {}).get("views") or 0)
        total_views += v
        views_today[doc["id"]] = v

    # Bulk-write today's snapshot rows (idempotent upsert).
    for aid, v in views_today.items():
        try:
            await db.seo_article_view_snapshots.update_one(
                {"article_id": aid, "date": today_iso},
                {"$set": {"article_id": aid, "date": today_iso,
                          "views": v, "captured_at": _now()}},
                upsert=True,
            )
        except Exception:  # pragma: no cover — diagnostics only
            pass

    # Decorate each top performer with last-7-day delta. We compare
    # today's running total to the snapshot taken 7 days ago — if no
    # snapshot exists (article published <7d ago), we treat its baseline
    # as 0 so the delta correctly shows "all views in last 7d".
    week_cutoff = (_london_now().date() - timedelta(days=7)).isoformat()
    decorated = []
    for a in top_performers:
        snap = await db.seo_article_view_snapshots.find_one(
            {"article_id": a["id"], "date": {"$lte": week_cutoff}},
            {"_id": 0, "views": 1, "date": 1},
            sort=[("date", -1)],
        )
        baseline = int((snap or {}).get("views") or 0)
        current = int((a.get("metrics") or {}).get("views") or 0)
        delta_abs = current - baseline
        # Percent change (None when baseline=0 *and* current=0; otherwise
        # `None` for "brand new article, no prior data").
        if baseline == 0:
            delta_pct = None
        else:
            delta_pct = round((delta_abs / baseline) * 100, 1)
        decorated.append({
            **a,
            "trend": {
                "views_7d_ago": baseline,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "is_new": snap is None,
            },
        })

    return {
        "keywords": {"total": kw_total, "queued": kw_queued, "published": kw_pub},
        "articles": {"total": art_total, "published": art_pub, "draft": art_draft},
        "performance": {
            "total_views": total_views,
            "top": decorated,
        },
        "recent": recent,
    }


# ── Iter 220am — per-article view trend ──────────────────────────


@router.get("/articles/{article_id}/view-trend")
async def article_view_trend(
    article_id: str, days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Return the daily view series for a single article over the
    last ``days`` (default 30). Days without a snapshot inherit the
    previous known value so the line stays continuous."""
    _require_master_admin(user)
    n = max(1, min(int(days), 90))
    article = await db.seo_articles.find_one(
        {"id": article_id}, {"_id": 0, "id": 1, "metrics": 1},
    )
    if not article:
        raise HTTPException(404, "Article not found")
    today = _london_now().date()
    dates = [(today - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    rows = await db.seo_article_view_snapshots.find(
        {"article_id": article_id, "date": {"$in": dates}},
        {"_id": 0, "date": 1, "views": 1},
    ).to_list(n)
    by_date = {r["date"]: int(r.get("views") or 0) for r in rows}
    series: list[dict] = []
    last = 0
    for d in dates:
        if d in by_date:
            last = by_date[d]
        series.append({"date": d, "views": last})
    # Tail-snap today's running total so the very last point is live
    # (the dashboard refresh writes today's row, but the article-detail
    # page may load before that runs today).
    current_views = int((article.get("metrics") or {}).get("views") or 0)
    if series:
        series[-1] = {"date": series[-1]["date"], "views": current_views}
    return {"article_id": article_id, "days": n, "series": series}


# ── Public blog endpoint (no auth) — used by /blog/<slug> ─────────

public_router = APIRouter(prefix="/api/blog", tags=["blog-public"])


@public_router.get("/posts")
async def public_list_posts(limit: int = 50):
    """List published SEO articles for the public blog index."""
    rows = await db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "id": 1, "slug": 1, "title": 1, "excerpt": 1,
         "tags": 1, "hero_image_url": 1, "published_at": 1,
         "read_time_min": 1},
    ).sort("published_at", -1).limit(min(max(limit, 1), 200)).to_list(200)
    return {"posts": rows}


@public_router.get("/posts/{slug}")
async def public_get_post(slug: str):
    doc = await db.seo_articles.find_one(
        {"slug": slug, "status": "published"}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Post not found")
    # Best-effort view counter — non-blocking on race conditions.
    try:
        await db.seo_articles.update_one(
            {"id": doc["id"]},
            {"$inc": {"metrics.views": 1}},
        )
    except Exception:  # noqa: BLE001
        pass
    return doc


# ── Index init ────────────────────────────────────────────────────

async def init_seo_indexes() -> None:
    try:
        await db.seo_articles.create_index("slug", unique=True, sparse=True)
        await db.seo_articles.create_index("status")
        await db.seo_keywords.create_index("status")
        # Iter 220ae — distributions are 1-per-article, store + retrieve fast
        await db.seo_distributions.create_index("article_id", unique=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("[seo] index init failed: %s", exc)


# ── asyncio.gather alias — keeps the module 1 import lighter ──────
import asyncio  # noqa: E402

async def asyncio_gather(*coros):
    return await asyncio.gather(*coros)


# ── Daily autopilot scheduler — Iter 220af ────────────────────────
#
# Fires ``run_autopilot`` once a day at 09:00 Europe/London. Uses a
# bare asyncio loop (matches the existing partner_compliance /
# reputation / welcome-back patterns — no new APScheduler dependency
# needed). The loop is idempotent: a "last fired on YYYY-MM-DD" stamp
# in the ``seo_autopilot_runs`` collection prevents double-fires if
# the process restarts mid-day.


def _london_now() -> "datetime":
    """Wall clock in Europe/London, used for the 09:00 trigger."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return _dt.now(ZoneInfo("Europe/London"))
    except Exception:  # pragma: no cover — fallback to UTC
        return _dt.now(timezone.utc)


async def _autopilot_already_ran_today(date_str: str) -> bool:
    doc = await db.seo_autopilot_runs.find_one(
        {"date": date_str}, {"_id": 0, "date": 1},
    )
    return bool(doc)


async def _stamp_autopilot_run(date_str: str, result: dict) -> None:
    await db.seo_autopilot_runs.update_one(
        {"date": date_str},
        {"$set": {"date": date_str, "result": result, "ran_at": _now()}},
        upsert=True,
    )


async def _autopilot_run_as_master_admin() -> dict:
    """Server-side wrapper that bypasses the HTTP auth dep + finds the
    GymAxis master admin to use as `created_by` on generated articles."""
    user = await db.users.find_one(
        {"is_master_admin": True},
        {"_id": 0, "id": 1, "email": 1, "is_master_admin": 1},
        sort=[("created_at", 1)],
    )
    if not user:
        return {"ok": False, "reason": "no master admin found"}
    try:
        return await run_autopilot(user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[seo-autopilot] daily run failed: %s", exc)
        return {"ok": False, "reason": str(exc)[:200]}


async def run_daily_autopilot_loop(*, hour: int = 9) -> None:
    """Background loop — checks every 15 minutes whether it's the
    configured London-time hour AND we haven't yet fired today. When
    both are true, calls ``run_autopilot``. Cron-quality without the
    cron daemon.

    Iter 220ai — reads ``seo_autopilot_config`` on every iteration so
    the UI's "Enabled" toggle + hour picker take effect without a
    backend restart. The ``hour`` kwarg is the env-var fallback used
    on cold boots before the master admin saves a config row.

    Iter 220cf — fires when ``london.hour >= cfg_hour`` (not ``==``)
    so a 15-min wake-up cadence that skips past the exact hour due
    to a backend restart, slow iteration, or even a one-off
    monitoring stall still catches the day. Combined with
    ``_autopilot_already_ran_today`` this remains idempotent — at
    most one run per London-calendar-day."""
    while True:
        try:
            cfg = await _load_config()
            cfg_enabled = bool(cfg.get("enabled", True))
            cfg_hour = int(cfg.get("hour_uk") or hour)
            london = _london_now()
            today = london.date().isoformat()
            if (
                cfg_enabled
                and london.hour >= cfg_hour
                and not await _autopilot_already_ran_today(today)
            ):
                logger.info(
                    "[seo-autopilot] firing daily run for %s @ %02d:00 Europe/London",
                    today, cfg_hour,
                )
                result = await _autopilot_run_as_master_admin()
                await _stamp_autopilot_run(today, result)
                logger.info("[seo-autopilot] daily result: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seo-autopilot] loop iteration error: %s", exc)
        await asyncio.sleep(15 * 60)  # 15 min cadence


__all__ = [
    "router", "public_router", "init_seo_indexes",
    "run_daily_autopilot_loop", "_london_now",
]
