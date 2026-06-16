"""Manufacturer catalogue ingestor (Iter 226, Strategy 1).

Fetches each manufacturer's sitemap.xml, walks the product URLs, extracts
og:image + page-title for every product, and persists them in a Mongo
collection (`manufacturer_catalogue`). Lookups become a fast DB query
instead of a DDG search + live scrape, which is both flaky (DDG often
returns 0 site-scoped hits for niche UK domains) and slow.

Schema for `manufacturer_catalogue` documents:
    {
        "id": uuid4,
        "domain": "wattbike.com",
        "manufacturer_display": "Wattbike",
        "page_url": "https://wattbike.com/products/atom",
        "page_title": "Wattbike Atom",
        "image_url": "https://cdn.wattbike.com/.../atom-hero.jpg",
        "name_keywords": ["wattbike", "atom"],   # for fuzzy matching
        "ingested_at": "2026-04-29T22:30:00+00:00",
    }

Indexes:
    - (domain, page_url) UNIQUE — one row per product page
    - text index on (page_title, name_keywords) for fuzzy lookup
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import ParseError as XMLParseError

import defusedxml.ElementTree as DET  # parses untrusted sitemap XML safely

from utils.database import db
from utils.equipment_image_lookup import (
    MANUFACTURER_DOMAINS,
    _extract_product_meta,
    _is_safe_outbound_url,
    _safe_get,
    slugify_equipment_name,
)

logger = logging.getLogger(__name__)

# Domains that ship the strongest sitemaps and are highest-priority for
# Pulse Fitness / Pulse Fitness customers. Ingestion can be expanded to all
# `MANUFACTURER_DOMAINS` later — kept tight to start so the first run is
# bounded.
PRIORITY_DOMAINS = (
    "pulsefitness.com",
    "lifefitness.com",
    "technogym.com",
    "matrixfitness.com",
    "precor.com",
    "wattbike.com",
    "concept2.com",
    "originfitness.com",
    "watsongym.com",
    "hoistfitness.com",
)

# Don't waste cycles on these — sitemap entries that are clearly not
# product pages (blog posts, support docs, marketing pages).
SKIP_PATTERNS = re.compile(
    r"(/blog/|/support/|/news/|/case-studi|/about/|/careers/|/jobs/"
    r"|/legal/|/privacy/|/terms/|/contact/|/login|/account|/cart"
    r"|/help/|/faq/|/press/|/press-release/|/investor|/team/|/sitemap|sitemap.xml$"
    # Iter 216e — Pulse Fitness publishes social-media archive pages
    # under their own URL slugs (e.g. /instagram-arm-only-workout/).
    # These polluted the catalogue with 100+ non-product entries.
    # Skip social/promo URL prefixes outright. Also block press
    # releases and after-sales tier pages — these are marketing /
    # service content, not equipment specs.
    r"|/(instagram|linkedin|twitter|facebook|tiktok|youtube)-|/social-"
    r"|/event/|/events/|/exhibition/|/exhibitions/|/show-/|/article/|/articles/"
    r"|/after-sales/|/aftersales/|/maintenance-plan"
    r"|\.pdf$|\.jpg$|\.png$|\.webp$|\.gif$)",
    re.IGNORECASE,
)

# Products live under URLs like /products/, /equipment/, /shop/.
PRODUCT_HINTS = re.compile(r"/(product|equipment|shop|cardio|strength|machine|gear)/", re.IGNORECASE)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


async def _fetch_sitemap_urls(domain: str, max_per_domain: int = 200) -> list[str]:
    """Return up to ``max_per_domain`` likely product-page URLs for the domain.

    Tries the standard `/sitemap.xml` then a couple of common nested
    sitemap paths (sitemap_products_1.xml). Recurses one level into
    sitemap-of-sitemaps. Returns hostname-filtered URLs only.
    """
    candidate_paths = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap_products_1.xml",
        "/sitemap-products.xml",
        "/sitemaps/sitemap.xml",
    ]
    found: list[str] = []
    seen: set[str] = set()

    for path in candidate_paths:
        if len(found) >= max_per_domain:
            break
        sitemap_url = f"https://{domain}{path}"
        if not _is_safe_outbound_url(sitemap_url):
            continue
        urls = await _parse_sitemap(sitemap_url, max_per_domain - len(found))
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            found.append(u)
            if len(found) >= max_per_domain:
                break

    # Filter to hostnames matching the manufacturer's domain to defend
    # against open-redirect-style sitemap hijinks.
    return [u for u in found if domain in _hostname(u)]


async def _parse_sitemap(sitemap_url: str, max_urls: int, depth: int = 0) -> list[str]:
    """Parse a sitemap.xml — recurse one level if it's a sitemap-of-sitemaps."""
    if depth > 2:
        return []
    r = await _safe_get(sitemap_url, timeout=15.0)
    if r is None or r.status_code != 200:
        return []
    try:
        root = DET.fromstring(r.text)
    except XMLParseError:
        return []

    # Strip namespace for easier traversal.
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"

    out: list[str] = []
    # sitemapindex → walk into each <sitemap><loc>…</loc></sitemap>
    if root.tag == f"{ns}sitemapindex":
        for sm in root.findall(f"{ns}sitemap"):
            loc = sm.find(f"{ns}loc")
            if loc is not None and loc.text:
                out.extend(await _parse_sitemap(loc.text.strip(), max_urls - len(out), depth + 1))
                if len(out) >= max_urls:
                    break
        return out

    # urlset → collect <url><loc>
    for url_el in root.findall(f"{ns}url"):
        loc = url_el.find(f"{ns}loc")
        if loc is None or not loc.text:
            continue
        u = loc.text.strip()
        if SKIP_PATTERNS.search(u):
            continue
        out.append(u)
        if len(out) >= max_urls:
            break
    return out


# Common entry points for sites without a usable sitemap. These are the
# generic landing pages most fitness vendors expose — we crawl them and
# harvest any anchor href that matches PRODUCT_HINTS. Iter 238g
# Strategy 4: now that operators can register new supplier domains via
# the Image Catalogue UI, sites without a sitemap need a fallback so
# their products still flow into the catalogue.
CATEGORY_FALLBACK_PATHS = (
    "/", "/products", "/products/", "/shop", "/shop/",
    "/equipment", "/equipment/", "/range", "/range/",
    "/cardio", "/cardio/", "/strength", "/strength/",
    "/machines", "/machines/", "/categories", "/categories/",
    "/collections", "/collections/all",
)

_HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


async def _fetch_category_page_urls(domain: str, max_per_domain: int = 200) -> list[str]:
    """Strategy 4 — crawl category/landing pages and harvest product
    links when no sitemap is available. Walks each ``CATEGORY_FALLBACK_PATHS``
    candidate, parses anchor `href`s, and returns hostname-filtered,
    product-shaped URLs.

    Caps work to ``max_per_domain`` to keep ingest bounded for sites
    that link to thousands of pages.
    """
    found: list[str] = []
    seen: set[str] = set()

    for path in CATEGORY_FALLBACK_PATHS:
        if len(found) >= max_per_domain:
            break
        page_url = f"https://{domain}{path}"
        if not _is_safe_outbound_url(page_url):
            continue
        r = await _safe_get(page_url, timeout=12.0)
        if r is None or r.status_code != 200 or not r.text:
            continue

        for match in _HREF_PATTERN.finditer(r.text):
            raw = (match.group(1) or "").strip()
            if not raw or raw.startswith(("#", "mailto:", "javascript:", "tel:")):
                continue
            absolute = urljoin(page_url, raw)
            host = _hostname(absolute)
            if not host or domain not in host:
                continue
            if SKIP_PATTERNS.search(absolute):
                continue
            if not PRODUCT_HINTS.search(absolute):
                # If the path looks like /<slug>, accept it: many small
                # vendors host products at the root (e.g. wattbike.com/atom).
                p = urlparse(absolute).path or ""
                segments = [s for s in p.strip("/").split("/") if s]
                if len(segments) != 1 or len(segments[0]) < 3:
                    continue
            absolute = absolute.split("#", 1)[0].split("?", 1)[0]
            if absolute in seen:
                continue
            seen.add(absolute)
            found.append(absolute)
            if len(found) >= max_per_domain:
                break

    return found


def _extract_keywords(title: str | None, page_url: str) -> list[str]:
    """Build a keyword list for fuzzy-match lookups."""
    parts: list[str] = []
    if title:
        parts.extend(re.findall(r"[a-zA-Z0-9]+", title.lower()))
    # Slug from URL is usually the cleanest model identifier.
    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    parts.extend(re.findall(r"[a-zA-Z0-9]+", slug.lower()))
    # Drop generic stop-words that explode false positives.
    stops = {"the", "a", "an", "of", "by", "for", "with", "and", "or",
             "product", "products", "equipment", "shop"}
    return sorted({p for p in parts if p and p not in stops and len(p) >= 2})


async def ensure_catalogue_indexes() -> None:
    coll = db.manufacturer_catalogue
    try:
        await coll.create_index([("domain", 1), ("page_url", 1)], unique=True)
        await coll.create_index([("name_keywords", 1)])
        await coll.create_index([("page_title", "text"), ("name_keywords", "text")])
    except Exception as exc:
        logger.info("catalogue index create skipped: %s", exc)


async def ingest_domain(
    domain: str,
    *,
    max_pages: int = 150,
    concurrency: int = 4,
) -> dict:
    """Fetch a domain's sitemap, scrape product metadata, upsert rows.

    Returns a stats dict — used by the master admin progress UI.
    """
    started_at = datetime.now(timezone.utc)
    urls = await _fetch_sitemap_urls(domain, max_per_domain=max_pages)
    fallback_used = False
    if not urls:
        # Strategy 4 — sites without a sitemap (or with a very thin one)
        # fall back to harvesting product links from common category
        # landing pages. This is what unlocks the editable crawl-list
        # UX: an admin pastes a new supplier domain → ingest works
        # without us pre-curating a sitemap path for them.
        urls = await _fetch_category_page_urls(domain, max_per_domain=max_pages)
        fallback_used = bool(urls)
    if not urls:
        return {
            "domain": domain, "examined": 0, "saved": 0, "skipped": 0,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "note": "no sitemap or category-page product links found",
        }

    saved = 0
    skipped = 0
    examined = 0
    sema = asyncio.Semaphore(concurrency)
    coll = db.manufacturer_catalogue

    # Resolve a friendly display label from the manufacturer dict.
    display = next(
        (k.title() for k, v in MANUFACTURER_DOMAINS.items() if v == domain),
        domain.split(".")[0].title(),
    )

    async def _one(url: str) -> None:
        nonlocal saved, skipped, examined
        async with sema:
            examined += 1
            # Heuristic: skip URLs that don't look like product pages.
            if not PRODUCT_HINTS.search(url) and "/products" not in url:
                # Still allow root-level slugs (e.g. /atom on Wattbike).
                pass
            meta = await _extract_product_meta(url)
            if not meta or not meta.get("image_url"):
                skipped += 1
                return
            keywords = _extract_keywords(meta.get("page_title"), url)
            now_iso = datetime.now(timezone.utc).isoformat()
            doc = {
                "domain": domain,
                "manufacturer_display": display,
                "page_url": url,
                "page_title": meta.get("page_title"),
                "image_url": meta["image_url"],
                "name_keywords": keywords,
                "ingested_at": now_iso,
            }
            try:
                await coll.update_one(
                    {"domain": domain, "page_url": url},
                    {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4()), "first_seen": now_iso}},
                    upsert=True,
                )
                saved += 1
            except Exception as exc:
                logger.info("catalogue upsert failed for %s: %s", url, exc)
                skipped += 1

    await asyncio.gather(*[_one(u) for u in urls], return_exceptions=True)

    return {
        "domain": domain,
        "examined": examined,
        "saved": saved,
        "skipped": skipped,
        "fallback_used": fallback_used,
        "discovery": "category_page_fallback" if fallback_used else "sitemap",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


async def ingest_priority_domains() -> list[dict]:
    """Ingest every priority domain in series — used by the master admin trigger."""
    await ensure_catalogue_indexes()
    out = []
    for d in PRIORITY_DOMAINS:
        try:
            stats = await ingest_domain(d)
        except Exception as exc:
            logger.warning("ingest failed for %s: %s", d, exc)
            stats = {"domain": d, "error": str(exc)}
        out.append(stats)
    return out


# ──────────────────────────────────────────────────────────────────
# Lookup helpers — these are what the live image-find flow calls
# ──────────────────────────────────────────────────────────────────

async def lookup_in_catalogue(
    domain: str,
    name: str,
    equipment_type: str | None = None,
) -> Optional[dict]:
    """Try to find a matching product in the cached catalogue.

    Strategy:
      1. Exact-ish match — score docs by overlap of search keywords with
         doc.name_keywords. Best-overlap wins (must score ≥2 to count).
      2. Fall back to Mongo $text search on title/keywords.
    """
    coll = db.manufacturer_catalogue
    cleaned = slugify_equipment_name(name) or name
    needle = re.findall(r"[a-zA-Z0-9]+", cleaned.lower())
    needle = [w for w in needle if len(w) >= 2 and w not in {"the", "and", "of"}]
    if not needle:
        return None

    # Stage 1: keyword-overlap scoring across all docs for the domain.
    cursor = coll.find({"domain": domain}, {"_id": 0})
    rows = await cursor.to_list(length=2000)
    scored: list[tuple[int, dict]] = []
    needle_set = set(needle)
    for row in rows:
        kws = set(row.get("name_keywords", []))
        score = len(needle_set & kws)
        if score >= 2:
            scored.append((score, row))
    scored.sort(key=lambda t: t[0], reverse=True)
    if scored:
        best = scored[0][1]
        return {
            "image_url": best["image_url"],
            "source_url": best["page_url"],
            "page_title": best.get("page_title"),
            "verified": True,  # We trust catalogued products — they came from the manufacturer's own sitemap.
            "source": "catalogue",
        }

    # Stage 2: Mongo $text search as a last resort within this domain.
    try:
        text_q = " ".join(needle)
        text_cursor = coll.find(
            {"domain": domain, "$text": {"$search": text_q}},
            {"_id": 0, "score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})]).limit(1)
        rows2 = await text_cursor.to_list(length=1)
        if rows2:
            best = rows2[0]
            return {
                "image_url": best["image_url"],
                "source_url": best["page_url"],
                "page_title": best.get("page_title"),
                "verified": True,
                "source": "catalogue_text",
            }
    except Exception as exc:
        # Text index missing or other error — non-fatal.
        logger.info("catalogue text search failed: %s", exc)

    return None


# ──────────────────────────────────────────────────────────────────
# Strategy 4 — category-page fallback
# ──────────────────────────────────────────────────────────────────

CATEGORY_PATHS = (
    "/products", "/equipment", "/shop", "/cardio", "/strength",
    "/collections/all", "/collections", "/range",
)


async def lookup_in_category_pages(
    domain: str,
    name: str,
) -> Optional[dict]:
    """Last-ditch fallback when DDG returned nothing useful: visit the
    manufacturer's category index pages directly and try to find an
    `<img>` whose `alt` text matches the equipment name."""
    cleaned = slugify_equipment_name(name) or name
    needle = [w for w in re.findall(r"[a-zA-Z0-9]+", cleaned.lower()) if len(w) >= 3]
    if not needle:
        return None
    needle_set = set(needle)

    for path in CATEGORY_PATHS:
        url = f"https://{domain}{path}"
        if not _is_safe_outbound_url(url):
            continue
        r = await _safe_get(url, timeout=12.0)
        if r is None or r.status_code != 200:
            continue
        ctype = (r.headers.get("content-type") or "").lower()
        if "text/html" not in ctype:
            continue
        # Find every <img alt="...">
        img_matches = re.findall(
            r'<img[^>]+alt=["\']([^"\']+)["\'][^>]+src=["\']([^"\']+)["\']',
            r.text,
            flags=re.IGNORECASE,
        )
        # Also support src-before-alt order.
        img_matches += re.findall(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]+alt=["\']([^"\']+)["\']',
            r.text,
            flags=re.IGNORECASE,
        )
        # Normalise into (alt, src) pairs.
        pairs: list[tuple[str, str]] = []
        for a, b in img_matches:
            # First regex returns alt,src. Second returns src,alt. Disambiguate by URL-ish-ness.
            if a.startswith(("http", "/", "data:")):
                pairs.append((b, a))
            else:
                pairs.append((a, b))
        best_score = 0
        best_pair = None
        for alt, src in pairs:
            tokens = set(re.findall(r"[a-zA-Z0-9]+", alt.lower()))
            score = len(needle_set & tokens)
            if score > best_score:
                best_score = score
                best_pair = (alt, src)
        if best_pair and best_score >= 2:
            alt, src = best_pair
            img_url = urljoin(url, src)
            if not _is_safe_outbound_url(img_url):
                continue
            return {
                "image_url": img_url,
                "source_url": url,
                "page_title": alt,
                "verified": False,  # Category-page hits skip vision verify — caller can re-verify.
                "source": "category_fallback",
            }
    return None
