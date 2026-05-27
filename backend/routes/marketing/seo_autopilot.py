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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

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
    "field engineers."
)
TARGET_WORDS = 1500


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
    status: Optional[str] = Field(None, pattern="^(queued|in_use|published|ignored)$")
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
        doc = {
            "id": _id(),
            "term": (it.get("term") or "").strip()[:160],
            "intent": it.get("intent") or "informational",
            "difficulty": it.get("difficulty") or "medium",
            "volume_estimate": it.get("volume_estimate") or "medium",
            "rationale": (it.get("rationale") or "")[:300],
            "seed_topic": payload.seed_topic,
            "audience": payload.audience,
            "status": "queued",
            "target_article_id": None,
            "notes": "",
            "created_at": _now(), "updated_at": _now(),
        }
        if not doc["term"]:
            continue
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
) -> dict:
    """Return a structured article dict {title, excerpt, body_md,
    meta_description, qa_blocks, tags}."""
    sec_block = (
        f"Also weave in these secondary keywords naturally (at most twice each, "
        f"never stuffed): {', '.join(secondary_keywords)}.\n"
        if secondary_keywords else ""
    )
    angle_block = f"Editorial angle: {angle}\n" if angle else ""

    prompt = (
        f"Write a long-form blog article for the GymAxis blog. "
        f"{DEFAULT_BRAND_BLURB}\n\n"
        f"Tone: {DEFAULT_TONE}\n\n"
        f"Primary keyword: {primary_keyword}\n"
        f"{sec_block}{angle_block}"
        f"Target length: {target_words} words (±10%).\n\n"
        "Structural rules:\n"
        "  • H1 must include the primary keyword.\n"
        "  • 5–7 H2 sub-sections; H3 only where genuinely useful.\n"
        "  • Open with a concrete operator-life scenario (not 'In today's…').\n"
        "  • At least one numbered list and one bullet list.\n"
        "  • Close with a single 1-line CTA inviting the reader to book a "
        "GymAxis demo at /demo.\n"
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

    return {
        "title": title, "excerpt": excerpt, "body_md": body_md,
        "meta_description": meta_description, "tags": tags[:6],
        "qa_blocks": qa_blocks[:6],
        "word_count": len((body_md or "").split()),
    }


@router.post("/articles/generate")
async def generate_article(
    payload: ArticleGeneratePayload,
    user: dict = Depends(get_current_user),
):
    """Generate a full draft article from the primary keyword. Returns
    the inserted ``seo_articles`` row."""
    _require_master_admin(user)

    text = await _generate_article_payload(
        payload.primary_keyword, payload.secondary_keywords,
        payload.angle, payload.target_words,
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
        "status": "published" if payload.publish_now else "draft",
        "published_at": now if payload.publish_now else None,
        "scheduled_for": None,
        "metrics": {"views": 0, "organic_visits": 0},
        "created_by": user.get("id"),
        "created_at": now, "updated_at": now,
    }
    await db.seo_articles.insert_one(doc)
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


# ── Daily autopilot ────────────────────────────────────────────────

@router.post("/autopilot/run")
async def run_autopilot(user: dict = Depends(get_current_user)):
    """Pick the next queued keyword and generate + publish an article.
    Designed to be hit by a cron-style scheduler (1 article/day)."""
    _require_master_admin(user)
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
    await db.seo_keywords.update_one(
        {"id": next_kw["id"]},
        {"$set": {"status": "published",
                  "target_article_id": article["id"],
                  "updated_at": _now()}},
    )
    return {"ok": True, "keyword_id": next_kw["id"], "article": article}


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
    return {
        "keywords": {"total": kw_total, "queued": kw_queued, "published": kw_pub},
        "articles": {"total": art_total, "published": art_pub, "draft": art_draft},
        "recent": recent,
    }


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
    except Exception as exc:  # pragma: no cover
        logger.warning("[seo] index init failed: %s", exc)


# ── asyncio.gather alias — keeps the module 1 import lighter ──────
import asyncio  # noqa: E402

async def asyncio_gather(*coros):
    return await asyncio.gather(*coros)


__all__ = ["router", "public_router", "init_seo_indexes"]
