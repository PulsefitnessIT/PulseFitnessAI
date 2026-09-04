"""Iter 216h268 — Website-first company recognition.

Pure extraction helpers for the new
`POST /api/crm/v2/companies/recognize-from-website` endpoint. Kept
side-effect-free so they're fast to test — no HTTP, no DB, no
clock-reading.

The endpoint itself (in `routes/crm_website_recognize.py`) wires
these helpers up to httpx + a 24h `crm_website_cache` collection.

Why a separate module:
* The existing `routes/crm_phase3._extract_meta` only grabs og:*
  + favicon, which is enough for logo enrichment but not enough
  to populate a brand-new company record (no phone, no address,
  no name normalisation).
* Sales reps prefer a company's **website URL** as the primary
  source rather than the registered office on Companies House
  (which is usually an accountant's address — the trading address
  + decision-makers live on the website).
"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse


# UK postcode shape — `SW1A 1AA`, `EC1V 9DD`, `M1 1AE` etc. Generous
# enough to catch the common variants without false-positiving on
# normal text.
UK_POSTCODE_RX = re.compile(
    r"\b(GIR ?0AA|[A-Z]{1,2}\d{1,2}[A-Z]? ?\d[A-Z]{2})\b",
    re.IGNORECASE,
)

# Phone shapes accepted: UK (+44 / 0…), generic international +N…,
# North-American ((204) 488-8023 / 204-488-8023 / 204.488.8023),
# parenthesised area codes. We pick the first VALID match.
PHONE_RX = re.compile(
    r"(\+44[\s\d()-]{8,}|\+\d{1,3}[\s\d()-]{6,}|\(?\d{3}\)?[\s.\u2011-]\d{3}[\s.\u2011-]\d{4}|0\d{2,4}[\s\d()-]{6,})",
)

# Titles/site-names that are page labels or bot-challenge text, NOT a
# company name. When we hit one of these we fall back to the domain.
GENERIC_NAME_RX = re.compile(
    r"^(home|welcome|home ?page|contact( us)?|about( us)?|index|loading|"
    r"untitled|default|menu|site|website|one moment(, please)?\.*|"
    r"just a moment\.*|please wait\.*|attention required|"
    r"checking your browser|access denied|error \d+)$",
    re.IGNORECASE,
)

# Markers that the page we fetched is a JS/bot interstitial rather than
# the real site — extracting from it yields garbage, so we skip it.
CHALLENGE_MARKERS = (
    "one moment, please", "just a moment", "attention required",
    "checking your browser", "cf-browser-verification", "cf_chl_",
    "please enable javascript", "please wait while", "ddos protection",
    "enable cookies to continue", "verifying you are human",
)


def normalise_url(url: str) -> str | None:
    """Coerce a user-typed URL into `scheme://netloc` form.

    Accepts:
      "acmegym.co.uk"          → "https://acmegym.co.uk"
      "WWW.AcmeGym.co.uk/contact" → "https://www.acmegym.co.uk"
      "https://acmegym.co.uk/about?x=1" → "https://acmegym.co.uk"

    Returns None for empty / unparseable input. Strips paths and
    query strings so we always hit the homepage as the canonical
    starting point.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _grab(pattern: str, html: str) -> str | None:
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return unescape(m.group(1).strip()) if m else None


def _grab_all(pattern: str, html: str) -> list[str]:
    return [unescape(m.strip()) for m in re.findall(pattern, html, re.IGNORECASE | re.DOTALL)]


def _extract_jsonld_organizations(html: str) -> list[dict]:
    """Pull every `<script type="application/ld+json">` block and
    return the ones whose `@type` is Organization / LocalBusiness /
    Corporation. Robust to:
      - top-level dicts and arrays
      - `@graph` wrappers
    """
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    )
    orgs: list[dict] = []
    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        # normalise into a flat list of dicts
        candidates: list[Any] = []
        if isinstance(data, list):
            candidates.extend(data)
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates.extend(data["@graph"])
            else:
                candidates.append(data)
        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            if isinstance(t, list):
                t = next((x for x in t if isinstance(x, str)), "")
            if isinstance(t, str) and t in (
                "Organization", "LocalBusiness", "Corporation",
                "HealthAndBeautyBusiness", "ExerciseGym", "SportsActivityLocation",
            ):
                orgs.append(c)
    return orgs


def _flatten_jsonld_org(org: dict) -> dict[str, Any]:
    """Map a schema.org Organization dict onto the CRM company shape."""
    out: dict[str, Any] = {}
    if org.get("name"):
        out["name"] = org["name"]
    if org.get("legalName"):
        out["name"] = org["legalName"]  # legalName beats display name
    if org.get("description"):
        out["description"] = org["description"]
    if org.get("telephone"):
        out["phone"] = str(org["telephone"])
    if org.get("email"):
        out["email"] = str(org["email"])
    if org.get("logo"):
        logo = org["logo"]
        out["logo_url"] = logo["url"] if isinstance(logo, dict) else str(logo)
    addr = org.get("address")
    if isinstance(addr, dict):
        if addr.get("streetAddress"):
            out["address_line1"] = addr["streetAddress"]
        if addr.get("addressLocality"):
            out["city"] = addr["addressLocality"]
        if addr.get("addressRegion"):
            out["county"] = addr["addressRegion"]
        if addr.get("postalCode"):
            out["postcode"] = addr["postalCode"]
        if addr.get("addressCountry"):
            c = addr["addressCountry"]
            out["country"] = c["name"] if isinstance(c, dict) else str(c)
    same_as = org.get("sameAs")
    if isinstance(same_as, list):
        out["social_links"] = [s for s in same_as if isinstance(s, str) and s.startswith("http")]
    return out


def _extract_phone_from_tel_links(html: str) -> str | None:
    m = re.search(r'href=["\']tel:([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        # Strip URL-encoding + cosmetic chars but keep the leading +
        return re.sub(r"%20", " ", m.group(1)).strip()
    return None


def _extract_email_from_mailto(html: str) -> str | None:
    m = re.search(r'href=["\']mailto:([^"\'?]+)["\']', html, re.IGNORECASE)
    if not m:
        return None
    email = m.group(1).strip().lower()
    # Reject obvious placeholders that shipping themes leave in
    if email in {"info@example.com", "hello@example.com", "you@example.com"}:
        return None
    return email


def _clean_title(title: str) -> str:
    """Strip common delimiter suffixes — `Acme Gym | Personal Training`
    → `Acme Gym`. Iteratively applies each delimiter so a title like
    `Acme - Strength Coaching | Liverpool` reduces to `Acme`."""
    cleaned = (title or "").strip()
    for sep in (" | ", " — ", " – ", " - ", " • "):
        if sep in cleaned:
            head = cleaned.split(sep, 1)[0].strip()
            if head:
                cleaned = head
    return cleaned


def _is_generic_name(name: str) -> bool:
    """True for page labels / challenge text that aren't a company name."""
    n = (name or "").strip()
    return not n or bool(GENERIC_NAME_RX.match(n))


def _is_challenge_html(html: str, title: str | None) -> bool:
    """Detect Cloudflare / bot-challenge / 'please enable JS' interstitials —
    extracting from these yields junk (fake title + a nonsense phone)."""
    if title and GENERIC_NAME_RX.match(title.strip()) and title.strip().lower().startswith(("one moment", "just a moment", "please wait", "checking", "attention")):
        return True
    low = (html or "")[:6000].lower()
    return any(m in low for m in CHALLENGE_MARKERS)


def _name_from_domain(base_url: str) -> str | None:
    """Derive a readable company name from the domain — far better than a
    generic page title. `reh-fit.com` → `Reh-Fit`, `cityfitness.co.uk`
    → `Cityfitness`."""
    try:
        host = urlparse(base_url).netloc.lower().split(":")[0]
    except Exception:
        return None
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0] if host else ""
    if not label:
        return None
    return re.sub(r"[A-Za-z0-9]+", lambda m: m.group(0).capitalize(), label)


def _valid_phone(raw: str | None) -> str | None:
    """Keep only plausible phone numbers (10–15 digits). Rejects junk like
    a scraped `013244 15` (8 digits) that the loose regex can catch."""
    if not raw:
        return None
    s = raw.strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10 or len(digits) > 15:
        return None
    return s


def extract_company_info(html: str, base_url: str) -> dict[str, Any]:
    """Run the full extractor pipeline on a homepage's HTML.

    Order of precedence per field:
      1. JSON-LD Organization block (most trustworthy — the site
         owner explicitly declared this info to crawlers).
      2. OpenGraph + meta tags.
      3. Fallback regex over visible text (tel:/mailto: links,
         postcode regex, phone regex).
    """
    if not html:
        return {}

    info: dict[str, Any] = {"source_url": base_url}

    title = _grab(r"<title[^>]*>([^<]+)</title>", html)

    # Bot-challenge / JS interstitial? Don't scrape garbage from it — just
    # anchor the record on the domain-derived name + website so the form is
    # still usefully pre-filled.
    if _is_challenge_html(html, title):
        dom = _name_from_domain(base_url)
        if dom:
            info["name"] = dom
        info["website"] = base_url
        info["blocked"] = True
        return info

    # ── 1. JSON-LD ────────────────────────────────────────────────
    for org in _extract_jsonld_organizations(html):
        flat = _flatten_jsonld_org(org)
        for k, v in flat.items():
            info.setdefault(k, v)

    # ── 2. OpenGraph / meta tags ──────────────────────────────────
    og_site_name = _grab(
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    og_title = _grab(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    og_desc = _grab(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    og_image = _grab(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    meta_desc = _grab(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )

    # Name precedence: JSON-LD name > og:site_name > cleaned <title>/og:title
    # (only when it's not a generic page label) > domain-derived fallback.
    if _is_generic_name(info.get("name")):
        info.pop("name", None)
    if not info.get("name"):
        candidate = ""
        if og_site_name and not _is_generic_name(og_site_name):
            candidate = og_site_name.strip()
        else:
            cleaned = _clean_title(og_title or title or "")
            if cleaned and not _is_generic_name(cleaned):
                candidate = cleaned
        if not candidate:
            candidate = _name_from_domain(base_url) or ""
        if candidate:
            info["name"] = candidate
    if not info.get("description"):
        d = og_desc or meta_desc
        if d:
            info["description"] = d
    if not info.get("logo_url") and og_image:
        info["logo_url"] = urljoin(base_url, og_image)

    # ── 3. Contact info fallbacks ─────────────────────────────────
    if not _valid_phone(info.get("phone")):
        info.pop("phone", None)
        tel = _extract_phone_from_tel_links(html)
        if _valid_phone(tel):
            info["phone"] = tel.strip()
        else:
            for m in PHONE_RX.finditer(html):
                cand = _valid_phone(m.group(1))
                if cand:
                    info["phone"] = cand
                    break
    if not info.get("email"):
        em = _extract_email_from_mailto(html)
        if em:
            info["email"] = em
    if not info.get("postcode"):
        m = UK_POSTCODE_RX.search(html)
        if m:
            info["postcode"] = m.group(1).upper().strip()

    # ── 4. Social links (sameAs in JSON-LD takes priority, but
    #       still sweep up homepage social anchors as a backup).
    if not info.get("social_links"):
        socials: list[str] = []
        for href in _grab_all(r'href=["\'](https?://[^"\']+)["\']', html):
            low = href.lower()
            if any(s in low for s in (
                "twitter.com/", "x.com/", "facebook.com/", "instagram.com/",
                "linkedin.com/", "youtube.com/", "tiktok.com/",
            )) and href not in socials:
                socials.append(href)
        if socials:
            info["social_links"] = socials[:6]

    # ── 5. Default country to UK only when the postcode is genuinely a
    #       UK shape — Pulse trades globally, so we must not mislabel a
    #       non-UK prospect (e.g. a Canadian JSON-LD postal code).
    pc = (info.get("postcode") or "").strip()
    if pc and not info.get("country") and UK_POSTCODE_RX.match(pc):
        info["country"] = "United Kingdom"

    info["website"] = base_url
    return info


# ── Common contact-page paths ────────────────────────────────────


CONTACT_PATHS: tuple[str, ...] = (
    "/contact", "/contact-us", "/contactus",
    "/about", "/about-us",
    "/get-in-touch",
)


def merge_extractions(*infos: dict[str, Any]) -> dict[str, Any]:
    """Merge several extractions in priority order — first non-empty
    value wins, except for `social_links` which de-duplicate."""
    merged: dict[str, Any] = {}
    for info in infos:
        if not info:
            continue
        for k, v in info.items():
            if v in (None, "", []):
                continue
            if k == "social_links":
                existing = merged.get("social_links") or []
                merged["social_links"] = list(dict.fromkeys(existing + list(v)))
                continue
            merged.setdefault(k, v)
    return merged
