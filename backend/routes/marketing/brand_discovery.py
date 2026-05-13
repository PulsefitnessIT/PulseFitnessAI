"""Marketing — Brand Auto-Discovery.

Iter 216h70 — when a customer enables the Marketing module (or saves
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
compressed (quality=85, max-dim 2000 px) so they survive customer
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
from utils.database import db, put_object
from utils.module_guard import require_module

logger = logging.getLogger(__name__)
router = APIRouter()

APP_NAME = "gymaxis"

# Crawl tuning (per iter 216h70 brief): homepage + top 8 internal pages
MAX_PAGES = 8
CRAWL_TIMEOUT = 10.0
USER_AGENT = "GymAxisBrandDiscoveryBot/1.0 (+https://gymaxisai.com)"
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
    # font-family declarations
    for m in re.findall(r"font-family\s*:\s*['\"]?([A-Za-z][A-Za-z0-9 _-]+)", html):
        name = m.strip().split(",")[0].replace('"', "").replace("'", "").strip()
        if name and name.lower() not in {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif", "inherit"}:
            fonts[name] += 1
    top = [n for n, _ in fonts.most_common(4)]
    return {"heading": top[0] if top else None, "body": top[1] if len(top) > 1 else top[0] if top else None, "all": top}


def _find_logo_candidates(soup: BeautifulSoup, base_url: str) -> list[str]:
    candidates: list[str] = []
    # 1. <link rel="icon"> / apple-touch-icon
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        if "icon" in rel and link.get("href"):
            candidates.append(urljoin(base_url, link["href"]))
    # 2. og:image
    for meta in soup.find_all("meta"):
        if (meta.get("property") or "").lower() in {"og:image", "twitter:image"}:
            if meta.get("content"):
                candidates.append(urljoin(base_url, meta["content"]))
    # 3. <img> in <header> or top of body with "logo" in class/alt
    for img in soup.find_all("img", limit=30):
        cls = " ".join(img.get("class") or []).lower()
        alt = (img.get("alt") or "").lower()
        src = img.get("src") or ""
        if not src:
            continue
        score = 0
        if "logo" in cls:
            score += 3
        if "logo" in alt:
            score += 2
        if "logo" in src.lower():
            score += 1
        if img.find_parent(["header", "nav"]):
            score += 1
        if score >= 2:
            candidates.append(urljoin(base_url, src))
    # Dedupe preserving order
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:6]


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
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
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
    result = put_object(key, data, content_type)
    return {
        "source_url": url,
        "stored_url": result.get("url") or result.get("path"),
        "path": result.get("path"),
        "size_bytes": len(data),
        "kind": kind,
    }


async def _claude_summarise(text_corpus: str) -> dict:
    """Single Claude Haiku 4.5 call to summarise tone, audiences, campaigns."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key or not text_corpus.strip():
        return {}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=api_key,
            session_id=f"brand-discovery-{datetime.now(timezone.utc).timestamp()}",
            system_message=(
                "You analyse a gym / fitness business website. Reply ONLY with valid JSON, no prose, with these keys:\n"
                "  tone_of_voice: 1-2 sentences capturing the brand's tone\n"
                "  audiences: array of audience segments mentioned (e.g. 'young professionals', 'families', 'PT clients')\n"
                "  current_campaigns: array of any promos/offers/launches mentioned (max 5 items, each 1 line)\n"
                "  has_timetable: boolean — does the site reference a class schedule\n"
                "  keywords: array of 5-10 product/service keywords the brand emphasises (e.g. 'HIIT', 'spa', 'family-friendly')\n"
                "Keep arrays short and concrete. If unsure, leave empty. Output strictly JSON with NO markdown fences."
            ),
        ).with_model("anthropic", "claude-haiku-4-5-20251001")
        # Truncate corpus to ~12k chars — well within Haiku context, keeps cost <$0.01.
        snippet = text_corpus[:12000]
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

        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
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
    website_url: HttpUrl = Field(..., description="Customer's public website URL")


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
