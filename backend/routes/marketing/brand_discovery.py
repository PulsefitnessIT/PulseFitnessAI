"""Marketing — Brand Auto-Discovery.

Iter 216h70 — when a tenant enables the Marketing module (or saves
their website URL for the first time), kick off a background crawl
that builds their **brand kit + marketing intelligence pack** from
their existing website:

  Visual:
    • dominant colours (CSS + hero-image palette)
    • Google Fonts + `font-family` declarations
    • logo candidates (header `<img>`, favicon, og:image)
    • 8-12 marketing image candidates

  Intelligence (single Claude Haiku 4.5 call):
    • brand tone-of-voice (3-line summary)
    • audience segments mentioned in copy
    • current promos / campaigns / blog topics
    • timetable cadence if `/timetable` exists
    • social handles

Results land as a *draft* doc that the operator reviews + applies via
`POST /apply`. Images are mirrored to our object storage and PIL-
compressed (quality=85, max-dim 2000 px) so they survive site
re-designs without quality loss.

API:
    POST  /api/marketing/brand-discovery/start        { website_url }
    GET   /api/marketing/brand-discovery/status        → progress + draft
    POST  /api/marketing/brand-discovery/apply        → commit to brand_kit
    POST  /api/marketing/brand-discovery/discard      → drop the draft

The crawl runs in a FastAPI BackgroundTask. Progress + draft are
persisted to `marketing_brand_discovery` (one doc per org).
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, Field, HttpUrl

from routes.marketing.helpers import _now_iso, _org_id
from utils.auth import get_current_user
from utils.database import db, put_object, get_object
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter()

APP_NAME = "gymaxis"

# Crawl tuning (per iter 216h70 brief): homepage + top 8 internal pages
MAX_PAGES = 8
CRAWL_TIMEOUT = 12.0
# Iter 216h71 — many corporate sites block crawler-style User-Agents
# at the WAF (Cloudflare, Akamai) regardless of robots.txt. Identify
# as a real Chrome to land on the public-facing HTML; we keep an
# X-Robot header so good-faith server admins can still see it's us.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 GymAxisBrandDiscovery/1.0"
)
EXTRA_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "X-GymAxis-Crawler": "brand-discovery/1.0 (+https://gymaxisai.com)",
}
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
GOOGLE_FONTS_RE = re.compile(r"family=([A-Za-z0-9+:,_-]+)")
# Common marketing-relevant paths to favour during link discovery
PRIORITY_PATHS = ("/about", "/timetable", "/classes", "/membership", "/pricing", "/offers", "/promotions", "/blog", "/contact")


def _normalise_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _same_domain(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()
    except Exception:
        return False


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=CRAWL_TIMEOUT, follow_redirects=True)
        if r.status_code >= 400:
            return None
        ct = r.headers.get("content-type", "")
        if "html" not in ct.lower():
            return None
        return r.text
    except Exception as exc:
        logger.debug("[brand-discovery] fetch %s failed: %s", url, exc)
        return None


async def _fetch_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        r = await client.get(url, timeout=CRAWL_TIMEOUT, follow_redirects=True)
        if r.status_code >= 400 or len(r.content) > 8 * 1024 * 1024:
            return None
        return r.content
    except Exception:
        return None


def _extract_hex_colours(css_or_html: str) -> list[str]:
    """Pull #RGB / #RRGGBB tokens — counted and normalised to 6 digits."""
    seen: Counter[str] = Counter()
    for m in HEX_RE.findall(css_or_html):
        h = m.lower()
        if len(h) == 4:
            h = "#" + "".join(c * 2 for c in h[1:])
        # Skip greys + near-white / near-black noise.
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        if abs(r - g) < 8 and abs(g - b) < 8 and abs(r - b) < 8:
            continue
        seen[h] += 1
    return [c for c, _ in seen.most_common(6)]


def _extract_fonts(html: str) -> dict:
    """Extract Google Fonts families + `font-family` declarations."""
    fonts: Counter[str] = Counter()
    # Google Fonts <link href="https://fonts.googleapis.com/css?family=Inter:400">
    for m in GOOGLE_FONTS_RE.findall(html):
        for fam in m.split("|"):
            name = fam.split(":")[0].replace("+", " ").strip()
            if name:
                fonts[name] += 5  # weight Google Fonts higher
    # font-family declarations — skip CSS custom-property tokens
    # (`var(--foo)`) and the standard generic fallback families. The
    # iter 216h70 build accidentally captured `var` from sites that
    # use design-token CSS variables (e.g. Third Space's WordPress
    # theme) — guard against that here.
    GENERIC = {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif", "inherit", "var", "system", "ui-monospace", "ui-serif"}
    for m in re.findall(r"font-family\s*:\s*['\"]?([A-Za-z][A-Za-z0-9 _-]+)", html):
        name = m.strip().split(",")[0].replace('"', "").replace("'", "").strip()
        # Reject obvious CSS-variable / generic noise.
        if not name or name.lower() in GENERIC or name.lower().startswith("var("):
            continue
        # Reject the literal token "var" left over from `var(--foo)` regex captures.
        if name.lower() == "var":
            continue
        fonts[name] += 1
    top = [n for n, _ in fonts.most_common(4)]
    return {"heading": top[0] if top else None, "body": top[1] if len(top) > 1 else top[0] if top else None, "all": top}


def _find_logo_candidates(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find logo URLs, ranked by likelihood of being the primary brand mark.

    Iter 216h73 — re-ranked. The iter 216h70 version put favicons first
    because they were picked up by the `<link rel=icon>` pass, which
    meant tryholo.ai's primary logo ended up below a 32x32 favicon.
    Now scored: header `<img>` with `logo` in class/alt > og:image >
    apple-touch-icon > favicon.
    """
    candidates: dict[str, int] = {}  # url → score (higher = better)
    # 1. <img> in <header>/<nav>/SVG containers — highest priority.
    for img in soup.find_all("img", limit=40):
        cls = " ".join(img.get("class") or []).lower()
        alt = (img.get("alt") or "").lower()
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        score = 0
        if "logo" in cls:
            score += 10
        if "logo" in alt:
            score += 6
        if "logo" in src.lower():
            score += 4
        if img.find_parent(["header", "nav"]):
            score += 4
        # Wordmark / brand alt hints.
        if any(t in alt for t in ("brand", "wordmark", "company")):
            score += 2
        if score >= 4:
            url = urljoin(base_url, src)
            candidates[url] = max(candidates.get(url, 0), score)
    # 2. og:image (usually a nicely-cropped marketing card) — score 5.
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in {"og:image", "twitter:image"} and meta.get("content"):
            url = urljoin(base_url, meta["content"])
            candidates.setdefault(url, 5)
    # 3. apple-touch-icon — score 3 (decent 180x180 mark).
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        href = link.get("href") or ""
        if not href:
            continue
        url = urljoin(base_url, href)
        if "apple-touch-icon" in rel:
            candidates.setdefault(url, 3)
        elif "icon" in rel:
            # Lowest priority — typically just a 32x32 favicon.
            candidates.setdefault(url, 1)
    # Sort by score desc, preserve insertion order on ties.
    return [u for u, _ in sorted(candidates.items(), key=lambda kv: -kv[1])[:6]]


def _extract_homepage_meta(soup: BeautifulSoup, base_url: str) -> dict:
    """Pull the homepage marketing meta: title, description, OG, twitter card.

    Iter 216h73 — these are the highest-signal copy + sharing assets
    on any marketing site. Captured separately so the operator can
    apply them as the brand's default homepage / social-card defaults.
    """
    out: dict[str, str] = {}
    if soup.title and soup.title.string:
        out["page_title"] = soup.title.string.strip()[:200]
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        content = (meta.get("content") or "").strip()
        if not prop or not content:
            continue
        if prop == "description":
            out["meta_description"] = content[:400]
        elif prop == "keywords":
            out["meta_keywords"] = content[:400]
        elif prop == "og:title":
            out["og_title"] = content[:200]
        elif prop == "og:description":
            out["og_description"] = content[:400]
        elif prop == "og:image":
            out["og_image"] = urljoin(base_url, content)
        elif prop == "twitter:title":
            out.setdefault("twitter_title", content[:200])
        elif prop == "twitter:description":
            out.setdefault("twitter_description", content[:400])
        elif prop in ("theme-color", "msapplication-tilecolor"):
            if HEX_RE.fullmatch(content):
                out["theme_color"] = content.lower()
    return out


def _extract_headlines(soup: BeautifulSoup) -> dict:
    """Pull hero H1 + top H2s as value props.

    Iter 216h73 — operator-facing headlines are the most reusable
    piece of brand copy. We grab the first H1 (typically the hero
    statement) and the first 6 H2s (typically the value props or
    section titles). Cleaned of script residue.
    """
    def _text(el):
        return " ".join(el.get_text(separator=" ").split())[:240]
    h1 = soup.find("h1")
    h2s = [_text(h) for h in soup.find_all("h2", limit=10) if _text(h)]
    h3s = [_text(h) for h in soup.find_all("h3", limit=8) if _text(h)]
    return {
        "h1": _text(h1) if h1 else None,
        "h2s": h2s[:6],
        "h3s": h3s[:6],
    }


def _extract_ctas(soup: BeautifulSoup) -> list[dict]:
    """Pull primary CTA buttons from the homepage.

    Iter 216h73 — we look for `<a>` with button-like styling (class
    contains 'btn', 'button', 'cta') OR a `<button>` element, then
    return the deduped, prioritised list of CTA copy + destination.

    Iter 216h73-b — Framer / Webflow / modern static-site generators
    use opaque hashed class names so the heuristic above misses
    legitimate CTAs. We also accept any `<a>` whose copy matches a
    known CTA verb list, or whose text is 2-5 words and ends in a
    typical CTA word.
    """
    HIGH_SIGNAL_CTAS = {
        "get started", "sign up", "sign up free", "sign up now", "create account",
        "start free", "try free", "try it free", "try for free", "start for free",
        "book a demo", "request a demo", "see a demo", "watch demo",
        "join now", "join", "start now", "free trial", "start trial", "start your free trial",
        "subscribe", "subscribe now", "buy now", "shop now", "order now",
        "download", "download now", "install", "install now",
        "contact us", "contact sales", "get in touch", "learn more",
    }
    CTA_VERB_PREFIXES = ("get ", "start ", "try ", "join ", "book ", "sign up", "buy ", "shop ", "create ", "claim ", "unlock ")
    seen: set[str] = set()
    out: list[dict] = []
    for el in soup.find_all(["a", "button"], limit=120):
        text = " ".join(el.get_text(separator=" ").split())
        if not text or len(text) > 50 or len(text) < 2:
            continue
        cls = " ".join(el.get("class") or []).lower()
        href = (el.get("href") or "").strip()
        lower = text.lower()
        is_button = el.name == "button" or any(t in cls for t in ("btn", "button", "cta", "primary"))
        is_high_signal = lower in HIGH_SIGNAL_CTAS or any(lower.startswith(p) for p in CTA_VERB_PREFIXES)
        if not is_button and not is_high_signal:
            continue
        # Skip nav links and footer junk.
        if any(skip in lower for skip in ("privacy", "terms", "cookie", "sitemap", "menu", "navigation")):
            continue
        # Skip if the link is a fragment anchor with no copy value.
        if href.startswith("#") and len(text.split()) < 2:
            continue
        if lower in seen:
            continue
        # Iter 216h73-b — Framer + similar generators wrap hover-state
        # twins so a CTA renders as "Buy now Buy now". Detect that
        # pattern: a string where the first half equals the second.
        half = len(lower) // 2
        if half >= 4 and lower[:half].strip() == lower[half:].strip():
            text = text[:len(text) // 2].strip()
            lower = text.lower()
            if lower in seen:
                continue
        # Iter 216h73-c — also strip tooltip / modal wrappers like
        # "Join Us Modal Join Us" or "Sign In Open Sign In" where a
        # decorative element sits in the middle of the duplicated copy.
        tokens = lower.split()
        if 4 <= len(tokens) <= 8 and len(tokens) % 2 == 1:
            n = (len(tokens) - 1) // 2
            if tokens[:n] == tokens[n + 1:]:
                text = " ".join(text.split()[:n])
                lower = text.lower()
                if not lower or lower in seen:
                    continue
        seen.add(lower)
        out.append({"label": text, "href": href, "is_button": is_button})
        if len(out) >= 8:
            break
    return out


# Social-proof patterns: numbers + descriptors like "10,000+ customers",
# "trusted by 500 brands", "rated 4.8 stars", "1M downloads".
_SOCIAL_PROOF_PATTERNS = [
    re.compile(r"\b(?:trusted by|used by|loved by|joined by|powering)\s+[\w,+\s]+\b", re.IGNORECASE),
    re.compile(r"\b\d{1,3}(?:[,.]?\d{3})*\+?\s*(?:customers|users|members|brands|companies|teams|gyms|operators)\b", re.IGNORECASE),
    re.compile(r"\b(?:rated|scored)\s+\d(?:\.\d)?\s*(?:stars?|out of|/)\s*\d?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,3}(?:,\d{3})*\+\s*(?:downloads|installs|sign[- ]ups)\b", re.IGNORECASE),
]


def _extract_social_proof(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pat in _SOCIAL_PROOF_PATTERNS:
        for m in pat.findall(text):
            phrase = m.strip()
            if 5 < len(phrase) < 120 and phrase.lower() not in seen:
                seen.add(phrase.lower())
                found.append(phrase)
                if len(found) >= 6:
                    return found
    return found


def _extract_hero_video(soup: BeautifulSoup, base_url: str) -> Optional[dict]:
    """Find a hero `<video>` or embedded YouTube/Vimeo iframe near the top of the page."""
    # Prefer a real <video> in or near the top of <body>.
    video = soup.find("video")
    if video:
        src = video.get("src") or ""
        poster = video.get("poster") or ""
        # If no inline src, look for the first <source>.
        if not src:
            source = video.find("source")
            if source and source.get("src"):
                src = source["src"]
        if src:
            return {
                "kind": "video",
                "src": urljoin(base_url, src),
                "poster": urljoin(base_url, poster) if poster else None,
            }
    # Otherwise, look for a YouTube / Vimeo iframe.
    for iframe in soup.find_all("iframe", limit=12):
        src = iframe.get("src") or ""
        if not src:
            continue
        host = urlparse(src).netloc.lower()
        if "youtube.com" in host or "youtu.be" in host or "vimeo.com" in host or "wistia." in host:
            return {"kind": "iframe", "src": src, "poster": None}
    return None


def _find_marketing_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Pick larger images that look like marketing creatives (heroes, classes, members)."""
    urls: list[str] = []
    for img in soup.find_all("img", limit=80):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        # Skip tiny pixel trackers / icons
        w = int(img.get("width") or 0) if (img.get("width") or "").isdigit() else 0
        h = int(img.get("height") or 0) if (img.get("height") or "").isdigit() else 0
        if (w and w < 200) or (h and h < 200):
            continue
        cls = " ".join(img.get("class") or []).lower()
        if "icon" in cls or "logo" in cls or "avatar" in cls:
            continue
        urls.append(urljoin(base_url, src))
    # Dedupe
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:12]


def _find_social(soup: BeautifulSoup) -> dict:
    socials = {"facebook": None, "instagram": None, "tiktok": None, "twitter": None, "linkedin": None, "youtube": None}
    for a in soup.find_all("a"):
        href = (a.get("href") or "").lower()
        if not href:
            continue
        for k in socials:
            host = k + ".com" if k != "twitter" else "twitter.com"
            if host in href and not socials[k]:
                socials[k] = a["href"]
        if "x.com" in href and not socials["twitter"]:
            socials["twitter"] = a["href"]
    return socials


def _discover_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Return same-domain internal links, prioritising marketing-relevant paths."""
    found: list[str] = []
    priority: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absu = urljoin(base_url, href).split("#")[0].rstrip("/")
        if not _same_domain(absu, base_url):
            continue
        path = urlparse(absu).path.lower()
        if any(path.startswith(p) for p in PRIORITY_PATHS):
            if absu not in priority:
                priority.append(absu)
        elif absu not in found:
            found.append(absu)
    return priority + found


async def _compress_and_store(url: str, kind: str, org_id: str, idx: int) -> Optional[dict]:
    """Download → PIL-compress (quality=85, max 2000px on longest side) → upload to storage."""
    async with httpx.AsyncClient(headers=EXTRA_HEADERS, follow_redirects=True) as client:
        raw = await _fetch_bytes(client, url)
    if not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        # Convert palette / CMYK to RGB / RGBA for JPEG/PNG output.
        if img.mode in {"P", "CMYK"}:
            img = img.convert("RGB")
        # Cap longest side at 2000 px while preserving aspect ratio.
        max_side = max(img.size)
        if max_side > 2000:
            ratio = 2000.0 / max_side
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        # PNG for assets with transparency (logos), JPEG otherwise.
        if img.mode == "RGBA":
            img.save(buf, format="PNG", optimize=True)
            content_type = "image/png"
            ext = "png"
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
            content_type = "image/jpeg"
            ext = "jpg"
        data = buf.getvalue()
    except Exception as exc:
        logger.debug("[brand-discovery] compress failed for %s: %s", url, exc)
        return None
    key = f"{APP_NAME}/brand-discovery/{org_id}/{kind}-{idx}.{ext}"
    put_object(key, data, content_type)
    # Iter 216h71 — surface a routable public URL the frontend can
    # render straight away. Asset bytes are served by the /asset/{path}
    # route below; it streams from object storage with caching headers.
    return {
        "source_url": url,
        "stored_url": f"/api/marketing/brand-discovery/asset/{key}",
        "storage_key": key,
        "size_bytes": len(data),
        "kind": kind,
    }


async def _claude_summarise(text_corpus: str) -> dict:
    """Single Claude Haiku 4.5 call to summarise tone, audiences, campaigns.

    Iter 216h73 — prompt rewritten to be **business-agnostic**. The
    iter 216h70 version was hard-coded to 'gym/fitness business', which
    caused Claude to refuse on AI SaaS / e-commerce / general SMB sites
    (e.g. tryholo.ai — see the operator-reported smoke test). The
    prompt now infers the vertical from the copy and produces the same
    intelligence shape for any vertical.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key or not text_corpus.strip():
        return {}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key,
            session_id=f"brand-discovery-{datetime.now(timezone.utc).timestamp()}",
            system_message=(
                "You analyse a tenant's website copy and extract marketing brand intelligence. "
                "The vertical is unknown — could be a gym, a SaaS, an e-commerce store, a service "
                "business, anything. Infer it from the copy. Reply ONLY with valid JSON (no prose, "
                "no markdown fences) with these keys:\n"
                "  vertical: 1-3 word category (e.g. 'AI marketing SaaS', 'boutique gym', 'fitness equipment manufacturer')\n"
                "  tone_of_voice: 1-2 sentences capturing the brand's voice (style, register, energy)\n"
                "  audiences: array of audience segments the copy clearly targets (3-6 items)\n"
                "  value_propositions: array of 3-6 clear product/service value props as 1-line statements\n"
                "  current_campaigns: array of any active promos/offers/launches mentioned (max 5 items)\n"
                "  pricing_model: 1-2 word summary if pricing is mentioned (e.g. 'free trial + monthly subscription', 'membership tiers', '£40-200/month')\n"
                "  keywords: array of 6-12 product/service keywords the brand emphasises\n"
                "  competitor_mentions: array of any competitors / 'alternatives to X' calls made\n"
                "  has_video: boolean — does the page reference a product video / demo\n"
                "Keep arrays short, concrete, copied as close to the source language as possible. If a field is unknown leave it empty (empty string for strings, [] for arrays, false for booleans). Output strictly JSON with NO markdown fences."
            ),
        ).with_model("anthropic", "claude-haiku-4-5-20251001")
        # Truncate corpus to ~15k chars — Haiku context is plenty, cost <$0.02.
        snippet = text_corpus[:15000]
        answer = await chat.send_message(UserMessage(text=f"Website copy:\n{snippet}"))
        import json
        # Tolerate accidental markdown fences in spite of the system prompt.
        clean = answer.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
        return json.loads(clean)
    except Exception as exc:
        logger.warning("[brand-discovery] claude summarise failed: %s", exc)
        return {}


async def _run_discovery(org_id: str, website_url: str) -> None:
    """Background entry point — crawl + extract + claude + persist."""
    started = datetime.now(timezone.utc)
    try:
        await db.marketing_brand_discovery.update_one(
            {"organization_id": org_id},
            {"$set": {
                "organization_id": org_id, "website_url": website_url,
                "status": "running", "started_at": started.isoformat(),
                "error": None, "draft": None,
                "progress": {"visited": 0, "queued": 1, "stage": "fetching homepage"},
            }},
            upsert=True,
        )

        async with httpx.AsyncClient(headers=EXTRA_HEADERS, follow_redirects=True) as client:
            homepage_html = await _fetch(client, website_url)
            if not homepage_html:
                raise RuntimeError(f"Could not load homepage at {website_url}")

            homepage_soup = BeautifulSoup(homepage_html, "html.parser")
            links = _discover_links(homepage_soup, website_url)[: MAX_PAGES - 1]
            queue = [website_url] + links
            visited_pages: list[dict] = []
            combined_text = []
            colours_acc: Counter[str] = Counter()
            for n, url in enumerate(queue, start=1):
                await db.marketing_brand_discovery.update_one(
                    {"organization_id": org_id},
                    {"$set": {"progress": {"visited": n - 1, "queued": len(queue), "stage": f"fetching {url}"}}},
                )
                page_html = homepage_html if n == 1 else await _fetch(client, url)
                if not page_html:
                    continue
                soup = BeautifulSoup(page_html, "html.parser")
                # text corpus for Claude
                for s in soup(["script", "style", "noscript"]):
                    s.extract()
                visible = " ".join(soup.get_text(separator=" ").split())[:4000]
                combined_text.append(f"[{url}]\n{visible}")
                for c in _extract_hex_colours(page_html):
                    colours_acc[c] += 1
                visited_pages.append({"url": url, "title": (soup.title.string if soup.title else "").strip()[:120]})

            # Visual extraction from homepage
            logo_candidates = _find_logo_candidates(homepage_soup, website_url)
            image_candidates = _find_marketing_images(homepage_soup, website_url)
            socials = _find_social(homepage_soup)
            fonts = _extract_fonts(homepage_html)
            # Iter 216h73 — homepage marketing signals: meta tags,
            # hero headline, value-prop H2s, CTA copy, social proof,
            # hero video. These are the highest-value extracted
            # signals for the "homepage brand capture" use case Lee
            # raised against tryholo.ai.
            homepage_meta = _extract_homepage_meta(homepage_soup, website_url)
            headlines = _extract_headlines(homepage_soup)
            ctas = _extract_ctas(homepage_soup)
            hero_video = _extract_hero_video(homepage_soup, website_url)
            # Social proof scraped from the full visible homepage
            # text (heroes + sections), not from individual pages.
            homepage_text = " ".join(BeautifulSoup(homepage_html, "html.parser").get_text(separator=" ").split())
            social_proof = _extract_social_proof(homepage_text)

        # Compress + store top logos (up to 3) + top images (up to 8) in parallel.
        await db.marketing_brand_discovery.update_one(
            {"organization_id": org_id},
            {"$set": {"progress": {"visited": len(visited_pages), "queued": len(queue), "stage": "compressing & storing assets"}}},
        )
        stored_logos_task = asyncio.gather(
            *[_compress_and_store(u, "logo", org_id, i) for i, u in enumerate(logo_candidates[:3])],
            return_exceptions=True,
        )
        stored_images_task = asyncio.gather(
            *[_compress_and_store(u, "image", org_id, i) for i, u in enumerate(image_candidates[:8])],
            return_exceptions=True,
        )
        stored_logos = [x for x in (await stored_logos_task) if isinstance(x, dict)]
        stored_images = [x for x in (await stored_images_task) if isinstance(x, dict)]

        # Claude tone + intelligence pass
        await db.marketing_brand_discovery.update_one(
            {"organization_id": org_id},
            {"$set": {"progress": {"visited": len(visited_pages), "queued": len(queue), "stage": "analysing tone & audiences"}}},
        )
        intel = await _claude_summarise("\n\n".join(combined_text))

        colours = [c for c, _ in colours_acc.most_common(6)]
        # Iter 216h73 — promote the meta theme-color into the palette
        # if the site declared one and we didn't already capture it.
        theme_color = homepage_meta.get("theme_color") if homepage_meta else None
        if theme_color and theme_color not in colours:
            colours = [theme_color] + colours[:5]
        draft = {
            "primary_color": colours[0] if colours else None,
            "secondary_color": colours[1] if len(colours) > 1 else None,
            "colours": colours,
            "fonts": fonts,
            "logos": stored_logos,
            "images": stored_images,
            "socials": {k: v for k, v in socials.items() if v},
            "intelligence": intel,
            "pages_visited": visited_pages,
            # Iter 216h73 — homepage marketing signals
            "homepage_meta": homepage_meta,
            "headlines": headlines,
            "ctas": ctas,
            "hero_video": hero_video,
            "social_proof": social_proof,
        }
        await db.marketing_brand_discovery.update_one(
            {"organization_id": org_id},
            {"$set": {
                "status": "ready",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "draft": draft,
                "error": None,
                "progress": {"visited": len(visited_pages), "queued": len(queue), "stage": "complete"},
            }},
        )
    except Exception as exc:
        logger.exception("[brand-discovery] failed for org=%s: %s", org_id, exc)
        await db.marketing_brand_discovery.update_one(
            {"organization_id": org_id},
            {"$set": {
                "status": "failed",
                "error": str(exc)[:300],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )


# ─── API ────────────────────────────────────────────────────────────


class StartReq(BaseModel):
    website_url: HttpUrl = Field(..., description="Tenant's public website URL")


@router.post("/marketing/brand-discovery/start", dependencies=[Depends(require_module("marketing"))])
async def start(req: StartReq, bg: BackgroundTasks, user: dict = Depends(get_current_user)) -> dict:
    org_id = await _org_id(user)
    if not org_id:
        raise HTTPException(400, "No organization context")
    url = _normalise_url(str(req.website_url))
    # Persist the website URL on the org so the Marketing module can
    # auto-trigger discovery on subsequent module activations.
    await db.organizations.update_one(
        {"id": org_id}, {"$set": {"website_url": url, "updated_at": _now_iso()}},
    )
    bg.add_task(_run_discovery, org_id, url)
    return {"ok": True, "status": "queued", "website_url": url}


@router.get("/marketing/brand-discovery/status", dependencies=[Depends(require_module("marketing"))])
async def status(user: dict = Depends(get_current_user)) -> dict:
    org_id = await _org_id(user)
    doc = await db.marketing_brand_discovery.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    return doc


class ApplyReq(BaseModel):
    apply_colours: bool = True
    apply_fonts: bool = True
    apply_primary_logo: bool = True
    apply_voice: bool = True


@router.post("/marketing/brand-discovery/apply", dependencies=[Depends(require_module("marketing"))])
async def apply(req: ApplyReq, user: dict = Depends(get_current_user)) -> dict:
    org_id = await _org_id(user)
    doc = await db.marketing_brand_discovery.find_one({"organization_id": org_id}, {"_id": 0})
    if not doc or doc.get("status") != "ready":
        raise HTTPException(400, "No ready draft to apply — run discovery first")
    draft = doc.get("draft") or {}
    patch: dict = {"updated_at": _now_iso(), "updated_by": user.get("id")}
    if req.apply_colours and draft.get("primary_color"):
        patch["primary_color"] = draft["primary_color"]
        if draft.get("secondary_color"):
            patch["secondary_color"] = draft["secondary_color"]
    if req.apply_fonts and (draft.get("fonts") or {}).get("heading"):
        patch["font_heading"] = draft["fonts"].get("heading")
        if draft["fonts"].get("body"):
            patch["font_body"] = draft["fonts"]["body"]
    if req.apply_primary_logo and draft.get("logos"):
        first_logo = draft["logos"][0]
        patch["primary_logo_url"] = first_logo.get("stored_url")
    if req.apply_voice and (draft.get("intelligence") or {}).get("tone_of_voice"):
        patch["voice"] = draft["intelligence"].get("tone_of_voice")
    await db.marketing_brand_kit.update_one(
        {"organization_id": org_id}, {"$set": {"organization_id": org_id, **patch}}, upsert=True,
    )
    # Mark draft as applied (keep it for re-reference; user can re-run to refresh).
    await db.marketing_brand_discovery.update_one(
        {"organization_id": org_id},
        {"$set": {"status": "applied", "applied_at": _now_iso(), "applied_by": user.get("id")}},
    )
    return {"ok": True, "applied": list(patch.keys())}


@router.post("/marketing/brand-discovery/discard", dependencies=[Depends(require_module("marketing"))])
async def discard(user: dict = Depends(get_current_user)) -> dict:
    org_id = await _org_id(user)
    await db.marketing_brand_discovery.delete_one({"organization_id": org_id})
    return {"ok": True}


# Iter 216h71 — serve compressed brand-discovery assets back to the
# frontend. Path must start with `{APP_NAME}/brand-discovery/{org}/`
# and resolve to the requester's own org to prevent cross-tenant leaks.
from fastapi.responses import Response  # noqa: E402


@router.get("/marketing/brand-discovery/asset/{full_path:path}")
async def serve_asset(full_path: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    expected_prefix = f"{APP_NAME}/brand-discovery/{org_id}/"
    if not full_path.startswith(expected_prefix):
        raise HTTPException(403, "Cross-tenant asset access denied")
    try:
        data, content_type = get_object(full_path)
    except Exception:
        raise HTTPException(404, "Asset not found")
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )
