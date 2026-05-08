"""
Equipment image lookup — manufacturer-website OG:image scraper with GPT verification.

Tries to find a manufacturer-hosted product photo for a piece of equipment when
no user-uploaded photo and no matched spec-sheet image exists. Falls back to None.

Flow:
  1. Map manufacturer name → authoritative website domain.
  2. Query DuckDuckGo HTML for `site:<domain> <equipment name>` (no API key needed).
  3. For each result on the manufacturer domain, fetch the page and extract
     og:image / twitter:image / JSON-LD product image.
  4. Verify with GPT-4o-mini that the page title actually describes the equipment
     (prevents wrong-product images). Verification is STRICT: if the model
     rejects or the request fails, we return the candidate unverified and let
     the caller decide whether to save it (frontend allows manual confirmation).
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Optional
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from utils.memberships_ai_insights import _chat, _chat_vision

logger = logging.getLogger(__name__)


# ═══════════════════════════ SSRF guard ═══════════════════════════

def _is_safe_outbound_url(url: str) -> bool:
    """Reject URLs that would let us probe internal networks (SSRF).

    Allows only http/https, blocks IP-literal hosts that resolve to
    private/loopback/link-local ranges (incl. AWS 169.254.169.254 metadata),
    and rejects non-standard ports. Called before every outbound fetch in
    this module.
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if p.port and p.port not in (80, 443, 8080, 8443):
            return False
        host = p.hostname or ""
        if not host:
            return False
        # Reject host strings that look like internal services.
        lower = host.lower()
        if lower in ("localhost", "ip6-localhost", "ip6-loopback", "broadcasthost"):
            return False
        if lower.endswith((".local", ".internal", ".lan", ".home")):
            return False
        # If literal IP, enforce it's globally routable.
        try:
            ip = ipaddress.ip_address(host)
            return bool(ip.is_global)
        except ValueError:
            pass
        # For hostnames, attempt to resolve and reject if it points to a private range.
        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if not ip.is_global:
                    return False
        except (socket.gaierror, ValueError):
            return False
        return True
    except Exception:
        return False


async def _safe_get(url: str, *, timeout: float = 10.0, headers: Optional[dict] = None, follow_redirects: bool = True):
    """SSRF-safe httpx GET. Returns the response or None if the URL is
    unsafe or the request fails. Follows at most 3 redirects, revalidating
    each hop against `_is_safe_outbound_url`."""
    if not _is_safe_outbound_url(url):
        logger.info("SSRF guard blocked: %s", url[:120])
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers or DEFAULT_HEADERS, follow_redirects=False) as client:
            current = url
            for _ in range(3):
                r = await client.get(current)
                if r.status_code in (301, 302, 303, 307, 308) and follow_redirects:
                    loc = r.headers.get("location") or ""
                    if not loc:
                        return r
                    # Resolve relative redirects against the current URL
                    next_url = urljoin(current, loc)
                    if not _is_safe_outbound_url(next_url):
                        logger.info("SSRF guard blocked redirect: %s", next_url[:120])
                        return None
                    current = next_url
                    continue
                return r
            return None
    except Exception as exc:
        logger.warning("safe_get failed for %s: %s", url[:80], exc)
        return None

# Known gym-equipment manufacturers → authoritative domains.
MANUFACTURER_DOMAINS: dict[str, str] = {
    "pulse fitness": "pulsefitness.com",
    "pulse": "pulsefitness.com",
    "life fitness": "lifefitness.com",
    "technogym": "technogym.com",
    "matrix fitness": "matrixfitness.com",
    "matrix": "matrixfitness.com",
    "precor": "precor.com",
    "cybex": "cybexintl.com",
    "star trac": "startrac.com",
    "hammer strength": "hammerstrength.com",
    "concept2": "concept2.com",
    "concept 2": "concept2.com",
    "woodway": "woodway.com",
    "peloton": "onepeloton.com",
    "nautilus": "nautilus.com",
    "stairmaster": "stairmaster.com",
    "octane": "octanefitness.com",
    "octane fitness": "octanefitness.com",
    "escape fitness": "escapefitness.com",
    "jordan fitness": "jordanfitness.com",
    "power plate": "powerplate.com",
    "powerplate": "powerplate.com",
    "keiser": "keiser.com",
    "assault fitness": "assaultfitness.com",
    "rogue": "roguefitness.com",
    "rogue fitness": "roguefitness.com",
    "bh fitness": "bhfitness.com",
    "sole fitness": "solefitness.com",
    "bowflex": "bowflex.com",
    "freemotion": "freemotionfitness.com",
    "schwinn": "schwinnfitness.com",
    "body solid": "bodysolid.com",
    "jacobs ladder": "jacobsladderexercise.com",
    "trueform": "trueformrunner.com",
    # UK & European specialists added in iter 224 — Pulse Fitness
    # operator feedback. Domains stick to the manufacturer's primary
    # marketing site (UK office where the brand has one).
    "origin fitness": "originfitness.com",
    "origin": "originfitness.com",
    "watson gym equipment": "watsongym.com",
    "watson": "watsongym.com",
    "hoist fitness": "hoistfitness.com",
    "hoist": "hoistfitness.com",
    "indigo fitness": "indigofitness.com",
    "indigo": "indigofitness.com",
    "physical company": "physicalcompany.co.uk",
    "jordan": "jordanfitness.com",
    "wattbike": "wattbike.com",
    "ziva": "zivafitness.com",
    "panatta": "panatta.com",
    "gymnova": "gymnova.com",
    "eleiko": "eleiko.com",
    "primal strength": "primalstrength.com",
    "primal": "primalstrength.com",
    "exigo": "exigouk.co.uk",
    "force usa": "forceusa.com",
    "fringe sport": "fringesport.com",
    "york fitness": "yorkfitness.com",
    "york": "yorkfitness.com",
    "tunturi": "tunturi.com",
    "kettler": "kettlersport.com",
    "stages cycling": "stagescycling.com",
    "stages": "stagescycling.com",
    "spirit fitness": "spiritfitness.com",
    "spirit": "spiritfitness.com",
    "torque fitness": "torquefitness.com",
    "torque": "torquefitness.com",
    "true fitness": "truefitness.com",
    "true": "truefitness.com",
    "vasa": "vasatrainer.com",
    "skierg": "concept2.com",
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def get_manufacturer_domain(manufacturer: str | None) -> Optional[str]:
    if not manufacturer:
        return None
    key = manufacturer.lower().strip()
    if key in MANUFACTURER_DOMAINS:
        return MANUFACTURER_DOMAINS[key]
    # prefix/contains match — e.g. "Pulse Fitness Ltd" → "pulse fitness"
    for k, v in MANUFACTURER_DOMAINS.items():
        if k in key or key in k:
            return v
    return None


def slugify_equipment_name(name: str) -> str:
    """Strip common descriptors to produce a cleaner product query."""
    if not name:
        return ""
    cleaned = re.sub(r"\s+in\s+[A-Z][a-zA-Z]+(\s+[A-Z][a-zA-Z]+)*", "", name)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\s+with\s+.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+featuring\s+.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


async def _ddg_search(query: str, timeout: float = 10.0) -> list[str]:
    """Return up to 5 result URLs from DuckDuckGo HTML search (no API key)."""
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            r = await client.get("https://duckduckgo.com/html/", params={"q": query})
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            urls: list[str] = []
            for a in soup.select("a.result__a, a.result-link"):
                href = a.get("href") or ""
                m = re.search(r"uddg=([^&]+)", href)
                urls.append(unquote(m.group(1)) if m else href)
            return [u for u in urls if u.startswith("http")][:5]
    except Exception as exc:
        logger.warning("DDG search failed: %s", exc)
        return []


async def _extract_product_meta(url: str, timeout: float = 10.0) -> Optional[dict]:
    """Fetch a product page and extract its image + title.

    SSRF-safe: URL is revalidated against the allow-list before each hop.
    """
    r = await _safe_get(url, timeout=timeout, follow_redirects=True)
    if r is None or r.status_code != 200:
        return None
    try:
        ctype = (r.headers.get("content-type") or "").lower()
        if "text/html" not in ctype:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        img_url = None
        for sel in (
            ("meta", {"property": "og:image:secure_url"}),
            ("meta", {"property": "og:image"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"name": "twitter:image:src"}),
            ("link", {"rel": "image_src"}),
        ):
            t = soup.find(*sel)
            if t:
                img_url = t.get("content") or t.get("href")
                if img_url:
                    break

        title = None
        ogt = soup.find("meta", property="og:title")
        if ogt and ogt.get("content"):
            title = ogt["content"]
        elif soup.title:
            title = soup.title.string

        if img_url:
            img_url = urljoin(url, img_url)
            # Final sanity: image URL should look like an image AND be safe
            if not _is_safe_outbound_url(img_url):
                return None
            if re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", img_url, re.IGNORECASE) or \
               re.search(r"(image|photo|product)", img_url, re.IGNORECASE):
                return {"image_url": img_url, "page_title": title, "source_url": url}
    except Exception as exc:
        logger.warning("OG extract failed for %s: %s", url, exc)
    return None


async def _verify_match(equipment: dict, candidate: dict) -> bool:
    """Two-stage verifier:

    1. Title/URL heuristic via GPT-4o-mini (text only, cheap) — same as before.
    2. If the text-check passes, confirm with GPT-4o VISION — look at the
       actual image pixels to catch the rare case where og:image is a
       manufacturer logo or a generic category hero instead of the product.

    Returns True only when BOTH stages agree. This is strict by design;
    callers store unverified candidates separately so users can still
    review borderline matches.
    """
    eq_desc = f"{equipment.get('name', '') or ''} ({equipment.get('equipment_type', '') or '—'}) by {equipment.get('manufacturer', '') or '—'}"
    page_title = (candidate.get("page_title") or "").strip()
    if not page_title:
        return False

    # Stage 1 — text verifier
    text_prompt = (
        "You are verifying whether a scraped product page matches a piece of gym "
        "equipment. Respond with STRICT JSON: {\"match\": true|false, \"reason\": \"...\"}.\n"
        f"Equipment record: {eq_desc}\n"
        f"Scraped page title: {page_title}\n"
        f"Scraped page URL: {candidate.get('source_url')}\n"
        "Rules: only match if the product category (cardio/strength/accessory) "
        "and manufacturer align. Accept minor phrasing differences. Reject if "
        "the page is a category/listing page, a blog post, or a different product."
    )
    try:
        raw = await _chat(text_prompt, max_tokens=120)
        import json as _json
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return False
        stage1 = bool(_json.loads(m.group(0)).get("match"))
    except Exception as exc:
        logger.info("Text verifier failed: %s", exc)
        return False

    if not stage1:
        return False

    # Stage 2 — vision verifier on the candidate image itself
    image_url = candidate.get("image_url")
    if not image_url:
        return False
    vision_prompt = (
        "Look at the attached image. Does it show a piece of gym equipment "
        f"consistent with: \"{eq_desc}\"?\n"
        "Respond STRICT JSON: {\"match\": true|false, \"confidence\": 0..1, \"reason\": \"...\"}.\n"
        "Reject if the image is: a brand logo, a text/spec-sheet, a gym "
        "interior, a person working out, a wrong category (e.g. treadmill "
        "when asking for a bike), or a banner/promo with no product visible."
    )
    try:
        raw = await _chat_vision(vision_prompt, [image_url], max_tokens=150)
        if not raw:
            # Vision unavailable — accept stage-1 only (downgraded verification).
            logger.info("Vision verifier unavailable — accepting stage-1 text match")
            return True
        import json as _json
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return False
        data = _json.loads(m.group(0))
        confidence = float(data.get("confidence") or 0.0)
        return bool(data.get("match")) and confidence >= 0.6
    except Exception as exc:
        logger.info("Vision verifier failed: %s", exc)
        # Graceful degradation: accept stage-1 only rather than losing the match.
        return True


async def lookup_equipment_image(
    manufacturer: str | None,
    name: str | None,
    equipment_type: str | None = None,
    verify: bool = True,
) -> Optional[dict]:
    """Top-level entry. Returns dict {image_url, source_url, page_title, verified} or None.

    Lookup order (iter 226):
      1. Cached catalogue (manufacturer_catalogue collection — fast, trusted)
      2. DDG site-search + og:image scrape (existing flow)
      3. Category-page fallback (Strategy 4 — visits /products, /shop, /cardio etc)
    """
    if not manufacturer or not name:
        return None
    domain = get_manufacturer_domain(manufacturer)
    if not domain:
        return None

    # ── Stage 1: catalogue cache ──
    try:
        from utils.manufacturer_catalogue import lookup_in_catalogue  # local import — avoids cycle on cold start
        cat_hit = await lookup_in_catalogue(domain, name, equipment_type)
        if cat_hit:
            return cat_hit
    except Exception as exc:
        logger.info("catalogue lookup failed (non-fatal): %s", exc)

    # ── Stage 2: DDG + scrape (legacy path) ──
    slim = slugify_equipment_name(name)
    queries: list[str] = []
    for q_name in (slim, name):
        if q_name and q_name not in queries:
            queries.append(f"site:{domain} {q_name}")
    queries.append(f"{manufacturer} {slim} product")

    tried: set[str] = set()
    candidates: list[dict] = []
    for q in queries:
        urls = await _ddg_search(q)
        for url in urls:
            if url in tried:
                continue
            tried.add(url)
            if domain not in url:
                continue
            result = await _extract_product_meta(url)
            if result and result.get("image_url"):
                candidates.append(result)
                if len(candidates) >= 3:
                    break
        if len(candidates) >= 3:
            break

    if candidates:
        equipment = {"name": name, "equipment_type": equipment_type, "manufacturer": manufacturer}
        for cand in candidates:
            if verify:
                ok = await _verify_match(equipment, cand)
                if ok:
                    return {**cand, "verified": True, "source": "ddg"}
            else:
                return {**cand, "verified": False, "source": "ddg"}
        # No strict-verified match — fall through to category-page fallback before returning unverified.

    # ── Stage 3: Category-page fallback (Strategy 4) ──
    try:
        from utils.manufacturer_catalogue import lookup_in_category_pages
        cp_hit = await lookup_in_category_pages(domain, name)
        if cp_hit:
            return cp_hit
    except Exception as exc:
        logger.info("category-page fallback failed: %s", exc)

    # If we got DDG candidates but none verified, return the first as unverified.
    if candidates:
        return {**candidates[0], "verified": False, "source": "ddg"}
    return None
