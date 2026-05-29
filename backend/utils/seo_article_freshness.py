"""SEO article freshness & deduplication helpers (Iter 220bj).

The blog auto-pilot was producing near-identical articles whenever two
queued keywords overlapped semantically (e.g. "gym equipment downtime"
vs "gym equipment downtime management software UK"). Both ended up
opening with the same "broken treadmill at 6 am" hook because the LLM
prompt carried zero context about what had already been published.

This module wires up four layers of variety:

1. ``build_recent_articles_context()`` — load the last N published
   articles' title + opener + H2 list so the prompt can explicitly
   forbid reusing them.
2. ``pick_next_archetype()`` — rotate through 8 opening "scenario
   archetypes" so consecutive articles take fundamentally different
   angles (commercial story vs compliance vs data-driven, etc.).
3. ``keyword_similarity()`` / ``find_similar_keywords()`` — Jaccard
   token-overlap to flag near-duplicate keywords at queue time.
4. ``article_similarity_score()`` — post-generation similarity check
   against existing published articles; the caller can regenerate or
   gate to ``needs_review`` when overlap is too high.

All helpers are pure / I/O is via a single injected ``db`` so the unit
tests can mock or use the real Motor client.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence


# ── Layer 2: editorial archetype rotation ─────────────────────────────

ARCHETYPES: list[dict] = [
    {
        "id": "peak_hour_failure",
        "label": "Peak-hour equipment failure scenario",
        "prompt_hint": (
            "Open with a vivid 'peak-hour equipment failure' scene set in "
            "a specific UK city or chain (rotate the city). Lead with the "
            "operational scramble, not the cost. Avoid the cliché 'broken "
            "treadmill at 6 am' opener — pick a different machine and a "
            "different time of day."
        ),
    },
    {
        "id": "member_churn_data",
        "label": "Member-churn data wake-up call",
        "prompt_hint": (
            "Open with a startling membership-retention statistic and "
            "frame the whole piece around the financial cost of "
            "operational gaps to renewals. Numbers-led, not story-led."
        ),
    },
    {
        "id": "compliance_incident",
        "label": "Compliance / RIDDOR / Health-and-Safety angle",
        "prompt_hint": (
            "Lead with a RIDDOR / HSE compliance angle — what regulators "
            "expect, what an inspector will check, what a missed log "
            "could cost. Reference UK-specific bodies (HSE, ukactive, "
            "CIMSPA) by name."
        ),
    },
    {
        "id": "contract_renewal",
        "label": "Contract-renewal commercial story",
        "prompt_hint": (
            "Frame the piece from the perspective of a tender / contract "
            "renewal — what procurement teams demand, what evidence wins "
            "the recompete, how SLA performance shows up in the next bid."
        ),
    },
    {
        "id": "peer_benchmark",
        "label": "Peer-benchmark comparison",
        "prompt_hint": (
            "Position the article as a peer benchmark — what the top-"
            "quartile UK operators do differently, anonymous comparison "
            "tables, gentle FOMO. No 6-am-treadmill opener."
        ),
    },
    {
        "id": "ops_director_letter",
        "label": "First-person letter from an ops director",
        "prompt_hint": (
            "Write in first person as if a long-serving operations "
            "director is sharing hard-won lessons. Conversational, "
            "concrete, slightly self-deprecating. Avoid stat-led openers."
        ),
    },
    {
        "id": "trends_data_led",
        "label": "Data-led industry trends piece",
        "prompt_hint": (
            "Lead with 2-3 specific industry trends (post-COVID member "
            "expectations, hybrid working changing peak hours, "
            "subscription-fatigue, etc.) and connect them to the "
            "keyword. Cite numbers; no operational anecdote opener."
        ),
    },
    {
        "id": "myth_busting",
        "label": "Myth-busting / contrarian take",
        "prompt_hint": (
            "Open by debunking a common belief in the industry "
            "(e.g. 'PPM is enough', 'in-house engineers are always "
            "cheaper', 'members forgive one breakdown'). Contrarian, "
            "evidence-led, no scene-setting opener."
        ),
    },
]


async def pick_next_archetype(db) -> dict:
    """Return the least-recently-used archetype based on
    ``seo_articles.archetype_id``. Falls back to the first archetype
    when the collection is empty (first run)."""
    pipeline = [
        {"$match": {"status": "published", "archetype_id": {"$exists": True, "$ne": None}}},
        {"$sort": {"published_at": -1}},
        {"$limit": 50},
        {"$group": {"_id": "$archetype_id", "last_used_at": {"$first": "$published_at"}}},
    ]
    used: dict[str, str] = {}
    async for row in db.seo_articles.aggregate(pipeline):
        used[row["_id"]] = row.get("last_used_at") or ""

    # Pick the archetype with the oldest (or absent) last_used_at —
    # giving never-used ones priority.
    def _key(a: dict) -> tuple[int, str]:
        last = used.get(a["id"])
        return (0 if last is None else 1, last or "")
    return sorted(ARCHETYPES, key=_key)[0]


# ── Layer 1: recent-articles context for the LLM prompt ───────────────


def _first_paragraph(body_md: str | None, max_chars: int = 220) -> str:
    if not body_md:
        return ""
    # Skip H1 + blank lines to find the first prose paragraph.
    paragraphs = re.split(r"\n\s*\n", body_md.strip())
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith("#"):
            continue
        return re.sub(r"\s+", " ", p)[:max_chars]
    return ""


def _h2_list(body_md: str | None, max_items: int = 6) -> list[str]:
    if not body_md:
        return []
    h2s = re.findall(r"^##\s+(.+?)\s*$", body_md, flags=re.MULTILINE)
    return [h.strip() for h in h2s[:max_items]]


async def build_recent_articles_context(db, *, limit: int = 8) -> list[dict]:
    """Load the last ``limit`` published articles in a compact shape
    suitable for embedding in an LLM prompt."""
    cursor = db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "title": 1, "excerpt": 1, "body_md": 1, "primary_keyword": 1,
         "archetype_id": 1, "published_at": 1},
    ).sort("published_at", -1).limit(limit)
    out: list[dict] = []
    async for row in cursor:
        out.append({
            "title": row.get("title", ""),
            "primary_keyword": row.get("primary_keyword", ""),
            "archetype_id": row.get("archetype_id"),
            "opener": _first_paragraph(row.get("body_md")),
            "h2_list": _h2_list(row.get("body_md")),
        })
    return out


def format_recent_articles_for_prompt(recent: Sequence[dict]) -> str:
    """Format the recent-articles context as a string block to paste
    into the article-generation prompt."""
    if not recent:
        return ""
    lines: list[str] = [
        "You MUST NOT repeat the hook, opening scenario, structural beats, "
        "or sub-section themes of any of the following recently-published "
        "articles. Pick a genuinely different angle, audience, scenario, "
        "and opening sentence:",
        "",
    ]
    for i, r in enumerate(recent, start=1):
        lines.append(f"--- Recent article #{i} ---")
        if r.get("title"):
            lines.append(f"Title: {r['title']}")
        if r.get("primary_keyword"):
            lines.append(f"Keyword: {r['primary_keyword']}")
        if r.get("archetype_id"):
            lines.append(f"Archetype already used: {r['archetype_id']}")
        if r.get("opener"):
            lines.append(f"Opener (DO NOT echo): {r['opener']}")
        if r.get("h2_list"):
            lines.append("Sub-sections (DO NOT reuse the same beats): "
                         + " | ".join(r["h2_list"]))
        lines.append("")
    return "\n".join(lines)


# ── Layer 3: keyword similarity (Jaccard on token sets) ───────────────

_TOKEN_RX = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "and", "the", "for", "to", "of", "in", "on", "with", "your",
    "you", "uk", "british", "best", "how", "guide", "tips", "ways",
}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RX.findall((text or "").lower()) if t not in _STOP and len(t) > 1}


def keyword_similarity(a: str, b: str) -> float:
    """Jaccard similarity on lower-case alphanumeric token sets,
    ignoring stopwords. Returns 0.0–1.0."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


async def find_similar_keywords(
    db, term: str, *, threshold: float = 0.7,
) -> list[dict]:
    """Return queued/published keywords + published article titles that
    share a Jaccard score >= ``threshold`` with ``term``."""
    hits: list[dict] = []
    async for kw in db.seo_keywords.find(
        {"status": {"$in": ["queued", "published", "in_use"]}},
        {"_id": 0, "id": 1, "term": 1, "status": 1},
    ):
        score = keyword_similarity(term, kw.get("term", ""))
        if score >= threshold:
            hits.append({**kw, "kind": "keyword", "similarity": round(score, 2)})
    async for art in db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "id": 1, "title": 1, "primary_keyword": 1},
    ):
        for cand in (art.get("title"), art.get("primary_keyword")):
            score = keyword_similarity(term, cand or "")
            if score >= threshold:
                hits.append({
                    "kind": "article", "id": art.get("id"),
                    "title": art.get("title"), "similarity": round(score, 2),
                })
                break
    # Highest similarity first, dedupe by (kind,id)
    seen: set[tuple] = set()
    out: list[dict] = []
    for h in sorted(hits, key=lambda x: -x["similarity"]):
        key = (h.get("kind"), h.get("id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


# ── Layer 4: post-generation similarity gate ──────────────────────────


def _normalise(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _word_set(text: str | None, *, take_first: int = 400) -> set[str]:
    body = _normalise(text)[:take_first]
    return {t for t in _TOKEN_RX.findall(body) if t not in _STOP and len(t) > 2}


def article_similarity_score(a_title: str, a_opener: str,
                             b_title: str, b_opener: str) -> float:
    """Composite similarity between two articles. 0.6 weight on opener
    word-set Jaccard, 0.4 weight on title token-set Jaccard."""
    title_sim = keyword_similarity(a_title, b_title)
    a_set, b_set = _word_set(a_opener), _word_set(b_opener)
    if a_set and b_set:
        opener_sim = len(a_set & b_set) / max(1, len(a_set | b_set))
    else:
        opener_sim = 0.0
    return round(0.4 * title_sim + 0.6 * opener_sim, 3)


async def check_article_uniqueness(
    db, *, title: str, body_md: str, exclude_id: str | None = None,
    threshold: float = 0.6,
) -> dict:
    """Compare a newly-generated article against every published one.
    Returns ``{ok, best_match, best_score}``."""
    opener = _first_paragraph(body_md, max_chars=600)
    best: dict | None = None
    best_score = 0.0
    cursor = db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "id": 1, "title": 1, "body_md": 1, "slug": 1},
    )
    async for art in cursor:
        if exclude_id and art.get("id") == exclude_id:
            continue
        score = article_similarity_score(
            title, opener,
            art.get("title", ""), _first_paragraph(art.get("body_md"), max_chars=600),
        )
        if score > best_score:
            best_score = score
            best = {"id": art.get("id"), "title": art.get("title"),
                    "slug": art.get("slug"), "score": score}
    return {
        "ok": best_score < threshold,
        "best_match": best,
        "best_score": best_score,
        "threshold": threshold,
    }


__all__: list[str] = [
    "ARCHETYPES",
    "pick_next_archetype",
    "build_recent_articles_context",
    "format_recent_articles_for_prompt",
    "keyword_similarity",
    "find_similar_keywords",
    "article_similarity_score",
    "check_article_uniqueness",
    "_first_paragraph",
]


# Convenience for external callers that want the archetype index by id.
def archetype_by_id(archetype_id: str | None) -> dict | None:
    if not archetype_id:
        return None
    for a in ARCHETYPES:
        if a["id"] == archetype_id:
            return a
    return None


def collect_token_overlaps(items: Iterable[str], target: str,
                            threshold: float = 0.7) -> list[tuple[str, float]]:
    """Helper used by tests and the keyword-research route to surface
    near-duplicate strings."""
    out: list[tuple[str, float]] = []
    for item in items:
        s = keyword_similarity(item, target)
        if s >= threshold:
            out.append((item, round(s, 2)))
    return sorted(out, key=lambda x: -x[1])
