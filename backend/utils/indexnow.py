"""IndexNow client — instant search-engine notification on publish.

IndexNow (https://www.indexnow.org) lets us tell Bing, Yandex, Seznam,
Naver and other participating engines the moment a URL is published or
updated, instead of waiting for a crawl. Google does not consume IndexNow
directly, but it does pick the new URLs up faster once they're in the
dynamic sitemap (see ``routes/seo_public.py``).

Activation is a hosted **key file**: a plain-text file at
``{SITE}/{key}.txt`` whose contents are exactly the key. We ship that file
in ``frontend/public/`` so it deploys with the marketing site.

Fully best-effort and non-blocking — a notification failure never affects
the publish flow.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# The key is a public verification token (not a secret) — it only has to
# match the hosted key file. Override via env if the file is regenerated.
INDEXNOW_KEY = os.environ.get(
    "INDEXNOW_KEY", "a7f3c9e21b8d4f06a5e7c2d9b4f18e30",
)
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def _site_base() -> str:
    return (os.environ.get("SEO_SITE_URL") or "https://www.pulsefitness.ai").rstrip("/")


def _host() -> str:
    return _site_base().split("://", 1)[-1].split("/", 1)[0]


async def ping_indexnow(urls: list[str]) -> dict:
    """Notify IndexNow that ``urls`` were published/updated.

    Returns ``{ok, submitted, status}``. Never raises — search-engine
    notification must not be able to break a publish."""
    urls = [u for u in (urls or []) if u]
    if not urls:
        return {"ok": False, "submitted": 0, "reason": "no_urls"}
    if os.environ.get("INDEXNOW_DISABLED") == "1":
        return {"ok": False, "submitted": 0, "reason": "disabled"}
    payload = {
        "host": _host(),
        "key": INDEXNOW_KEY,
        "keyLocation": f"{_site_base()}/{INDEXNOW_KEY}.txt",
        "urlList": urls[:10000],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                INDEXNOW_ENDPOINT, json=payload,
                headers={"Content-Type": "application/json"},
            )
        ok = resp.status_code in (200, 202)
        if not ok:
            logger.warning("[indexnow] %s → %s", resp.status_code, resp.text[:200])
        return {"ok": ok, "submitted": len(urls), "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[indexnow] ping failed: %s", exc)
        return {"ok": False, "submitted": 0, "reason": str(exc)[:200]}


async def ping_blog_slug(slug: str) -> dict:
    """Convenience — notify for a single published blog post by slug."""
    if not slug:
        return {"ok": False, "submitted": 0, "reason": "no_slug"}
    return await ping_indexnow([f"{_site_base()}/blog/{slug}"])


__all__ = ["INDEXNOW_KEY", "ping_indexnow", "ping_blog_slug"]
