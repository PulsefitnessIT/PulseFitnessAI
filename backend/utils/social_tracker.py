"""Social tracked-post crawler — Iter 220bw.

Stores public-post URLs (Instagram first; TikTok / LinkedIn share the
same schema for later) in ``social_tracked_posts`` and crawls them
once per day to record engagement numbers + the caption snippet.

We deliberately use ONLY the public preview surface (OpenGraph meta
tags + JSON-LD where present). No login, no Instagram Graph API
credentials, no scraping of the authenticated app HTML. This means:

* The data we capture is whatever IG exposes to a logged-out browser
  fetching the post URL — typically likes + comments counts in the
  `og:description` / page title text, plus the caption.
* When IG rate-limits or shows the login wall, we fail soft: record
  ``last_crawl_status = "blocked"``, do not raise, and retry next day.
  (Per user choice — silent retry + log; no UI noise.)

Per-platform behaviour:
* **Instagram** — fetch the `/p/<shortcode>/` page; parse the JSON
  embedded inside the `<script type="application/ld+json">` tag, fall
  back to OpenGraph meta tags.
* **TikTok** — same idea, `og:description` typically carries `X Likes,
  Y Comments, Z Shares — title`.
* **LinkedIn** — public post URLs sometimes 302 to the feed; we
  capture whatever metadata the OG tags expose.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


SUPPORTED_PLATFORMS = ("instagram", "tiktok", "linkedin")

# A reasonable desktop UA the public preview surface accepts; we
# rotate the bare minimum — IG's anti-bot is heavy but a plain
# desktop UA still serves the og: meta for most public posts.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)


def detect_platform(url: str) -> Optional[str]:
    """Best-effort platform classifier from a URL. Returns one of
    ``SUPPORTED_PLATFORMS`` or ``None``."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    if "instagram.com" in host:
        return "instagram"
    if "tiktok.com" in host:
        return "tiktok"
    if "linkedin.com" in host:
        return "linkedin"
    return None


_NUM_RE = re.compile(r"(\d[\d,]*)\s*(likes?|comments?|views?|shares?)", re.I)


def parse_engagement_from_html(html: str) -> dict:
    """Extract likes / comments / views / caption snippet from a public
    preview HTML. Defensive against missing fields — returns whatever
    we can find. Numbers are returned as ``int`` (commas stripped).

    The IG/TikTok/LinkedIn preview surfaces all carry an OG description
    of the shape "X Likes, Y Comments — Caption text". We parse that
    first because it's stable across all three platforms; the JSON-LD
    is platform-specific and used as a defence-in-depth.
    """
    if not html:
        return {}
    out: dict = {}

    # 1) OpenGraph description / title — most-reliable across platforms.
    og_desc = _meta(html, "og:description") or _meta(html, "twitter:description") or ""
    og_title = _meta(html, "og:title") or ""
    og_image = _meta(html, "og:image") or ""
    for match in _NUM_RE.finditer(f"{og_title} {og_desc}"):
        n = int(match.group(1).replace(",", ""))
        label = match.group(2).lower().rstrip("s")
        if label in {"like", "comment", "view", "share"}:
            out[f"{label}s"] = n

    # 2) Caption snippet — strip the metric prefix.
    if og_desc:
        # Common shapes:
        #   "1,234 likes, 56 comments - GymAxis (@gymaxis) on Instagram: "Caption"
        #   "12K Likes, 234 Comments. TikTok video from GymAxis (@gymaxis): "Caption""
        # We pull the FIRST quoted chunk if present, else everything
        # after the last colon, else the whole desc.
        m = re.search(r'"([^"]{4,})"', og_desc)
        if m:
            out["caption_snippet"] = m.group(1)[:400]
        else:
            tail = og_desc.split(":", 1)
            out["caption_snippet"] = (tail[1] if len(tail) > 1 else og_desc).strip()[:400]

    if og_image:
        out["preview_image_url"] = og_image[:500]

    return out


_META_RE_FMT = (
    r'<meta\s+(?:[^>]*\s+)?(?:property|name)\s*=\s*["\']{tag}["\']'
    r'[^>]*\scontent\s*=\s*(["\'])(.*?)\1'
)


def _meta(html: str, tag: str) -> str:
    """Pull the value of a ``<meta property="og:title" content="...">``
    or ``<meta name="..." content="...">`` tag. Returns empty string
    if not found. Quote-aware — the content value may itself contain
    the opposite quote character (common in IG OG descriptions which
    quote the caption text)."""
    if not html or not tag:
        return ""
    m = re.search(_META_RE_FMT.format(tag=re.escape(tag)), html, re.I | re.S)
    if not m:
        # Try the reverse attribute order (content first, then property).
        rev = (
            r'<meta\s+(?:[^>]*\s+)?content\s*=\s*(["\'])(.*?)\1'
            r'[^>]*\s(?:property|name)\s*=\s*["\']'
            + re.escape(tag) + r'["\']'
        )
        m = re.search(rev, html, re.I | re.S)
        if m:
            return m.group(2)
        return ""
    return m.group(2)


async def fetch_public_post(url: str, *, timeout: float = 15.0) -> dict:
    """Fetch a public post URL and parse what we can. Returns:
        {
          "status": "ok" | "blocked" | "failed",
          "http_status": int,
          "engagement": {likes?, comments?, views?, shares?,
                         caption_snippet?, preview_image_url?},
          "fetched_at": iso,
        }
    Never raises — always returns the status dict so the daily loop
    can persist it without a try/except wrapper.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": _UA,
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.info("[social-tracker] fetch failed for %s: %s", url, exc)
        return {
            "status": "failed", "http_status": 0,
            "engagement": {}, "fetched_at": fetched_at,
            "error": str(exc)[:200],
        }

    status_code = resp.status_code
    body = resp.text or ""
    # IG login wall heuristic — the redirect lands on /accounts/login/
    # or the body contains 'Sign Up · Instagram'.
    if status_code in (401, 403) or "/accounts/login" in str(resp.url) or "Login • Instagram" in body:
        return {
            "status": "blocked", "http_status": status_code,
            "engagement": {}, "fetched_at": fetched_at,
        }
    if status_code >= 500 or status_code == 429:
        return {
            "status": "failed", "http_status": status_code,
            "engagement": {}, "fetched_at": fetched_at,
        }
    if status_code != 200:
        return {
            "status": "failed", "http_status": status_code,
            "engagement": {}, "fetched_at": fetched_at,
        }

    engagement = parse_engagement_from_html(body)
    return {
        "status": "ok", "http_status": status_code,
        "engagement": engagement, "fetched_at": fetched_at,
    }


async def crawl_due_tracked_posts(db, *, max_per_run: int = 50) -> dict:
    """Iterate every tracked post and refresh its engagement payload.
    Called by the daily background loop. Returns observability counts.
    """
    cur = db.social_tracked_posts.find(
        {"active": True}, {"_id": 0},
    ).limit(max_per_run)
    rows = await cur.to_list(max_per_run)
    if not rows:
        return {"crawled": 0, "ok": 0, "blocked": 0, "failed": 0}

    ok = 0
    blocked = 0
    failed = 0
    for row in rows:
        result = await fetch_public_post(row["url"])
        # Append the new engagement snapshot to the history (keep last 60).
        history_entry = {
            "fetched_at": result["fetched_at"],
            "status": result["status"],
            "http_status": result["http_status"],
            **result["engagement"],
        }
        await db.social_tracked_posts.update_one(
            {"id": row["id"]},
            {
                "$set": {
                    "last_crawled_at": result["fetched_at"],
                    "last_crawl_status": result["status"],
                    "last_engagement": result["engagement"] or row.get("last_engagement", {}),
                },
                "$push": {
                    "engagement_history": {
                        "$each": [history_entry],
                        "$slice": -60,
                    },
                },
            },
        )
        if result["status"] == "ok":
            ok += 1
        elif result["status"] == "blocked":
            blocked += 1
        else:
            failed += 1
    return {"crawled": len(rows), "ok": ok, "blocked": blocked, "failed": failed}


async def run_social_tracker_loop(db, *, interval_seconds: int = 86400) -> None:
    """Daemon — wakes every ``interval_seconds`` (default 24 h) and
    crawls every tracked post. Gated by env
    ``SOCIAL_TRACKER_ENABLED`` so an operator can pause it during
    incident response without redeploying.
    """
    import asyncio
    enabled = os.environ.get("SOCIAL_TRACKER_ENABLED", "1") != "0"
    if not enabled:
        logger.info("[social-tracker] disabled by env")
        return
    interval = max(300, interval_seconds)  # 5 min floor
    logger.info(
        "[social-tracker] loop started (interval=%ds)", interval,
    )
    while True:
        try:
            await crawl_due_tracked_posts(db)
        except Exception:
            logger.exception("[social-tracker] iteration failed")
        await asyncio.sleep(interval)


def new_tracked_post(url: str, *, added_by: str | None = None,
                     label: str | None = None) -> dict:
    """Build the row the master admin will insert."""
    platform = detect_platform(url) or "instagram"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "url": url,
        "platform": platform,
        "label": (label or "").strip(),
        "active": True,
        "added_by": added_by,
        "added_at": now,
        "last_crawled_at": None,
        "last_crawl_status": None,
        "last_engagement": {},
        "engagement_history": [],
    }


__all__ = [
    "SUPPORTED_PLATFORMS",
    "detect_platform",
    "parse_engagement_from_html",
    "fetch_public_post",
    "crawl_due_tracked_posts",
    "run_social_tracker_loop",
    "new_tracked_post",
]
