"""Iter 216h268 — Website-first company recognition (P2).

User feedback (verbatim): *"Companies — use the company's website
URL as the primary source rather than Companies House addresses,
so the right typing flows through to the rest of the CRM."*

This iter wires up:
* `utils.website_enrichment.extract_company_info()` — pure HTML →
  structured company info (JSON-LD Organization, OG tags, tel:/mailto:
  links, UK postcode regex, social sameAs URLs).
* `POST /api/crm/v2/companies/recognize-from-website` — fetches a
  homepage + opportunistic contact pages, caches results for 24h.
* Frontend "Start from website URL" panel at the top of the
  Create Company dialog — pastes a URL → fills the form fields.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. URL normalisation ───────────────────────────────────────────


def test_normalise_url_adds_https_to_naked_domain():
    from utils.website_enrichment import normalise_url

    assert normalise_url("acmegym.co.uk") == "https://acmegym.co.uk"
    assert normalise_url("  ACMEGYM.co.uk  ") == "https://acmegym.co.uk"


def test_normalise_url_strips_path_and_query():
    from utils.website_enrichment import normalise_url

    assert normalise_url("https://acmegym.co.uk/contact?ref=x") == "https://acmegym.co.uk"
    assert normalise_url("http://Sub.AcmeGym.com/about") == "http://sub.acmegym.com"


def test_normalise_url_rejects_garbage():
    from utils.website_enrichment import normalise_url

    assert normalise_url("") is None
    assert normalise_url("not a url") is None
    assert normalise_url("https://") is None


# ─── 2. HTML extractor ──────────────────────────────────────────────


HTML_RICH = """
<html><head>
<title>Acme Gym Ltd · Personal Training in Manchester</title>
<meta property="og:site_name" content="Acme Gym Ltd">
<meta property="og:description" content="Independent strength &amp; conditioning gym since 2014.">
<meta property="og:image" content="/uploads/og.jpg">
<meta name="description" content="Independent gym in central Manchester.">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Acme Gym",
  "legalName": "Acme Gym Ltd",
  "telephone": "+44 161 555 0100",
  "email": "hello@acmegym.co.uk",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "12 Deansgate",
    "addressLocality": "Manchester",
    "addressRegion": "Greater Manchester",
    "postalCode": "M3 1WS",
    "addressCountry": "GB"
  },
  "sameAs": [
    "https://twitter.com/acmegym",
    "https://www.instagram.com/acmegym",
    "https://www.linkedin.com/company/acmegym"
  ]
}
</script>
</head><body>
<a href="tel:+44 161 555 0100">Call us</a>
<a href="mailto:hello@acmegym.co.uk">Email</a>
<a href="https://www.facebook.com/acmegymuk">FB</a>
</body></html>
"""


def test_extract_company_info_prefers_jsonld_legal_name():
    from utils.website_enrichment import extract_company_info

    info = extract_company_info(HTML_RICH, "https://acmegym.co.uk")
    # legalName beats display name
    assert info["name"] == "Acme Gym Ltd"
    assert info["phone"] == "+44 161 555 0100"
    assert info["email"] == "hello@acmegym.co.uk"
    assert info["address_line1"] == "12 Deansgate"
    assert info["city"] == "Manchester"
    assert info["county"] == "Greater Manchester"
    assert info["postcode"] == "M3 1WS"
    assert info["country"] == "GB"
    assert info["description"]  # picked up from JSON-LD or og:description
    # Social links from JSON-LD sameAs
    assert "https://twitter.com/acmegym" in info["social_links"]
    assert "https://www.instagram.com/acmegym" in info["social_links"]
    # Resolved og:image to absolute
    assert info["logo_url"].startswith("https://acmegym.co.uk/")
    # website is set to the canonical base
    assert info["website"] == "https://acmegym.co.uk"
    # source_url marker
    assert info["source_url"] == "https://acmegym.co.uk"


def test_extract_company_info_falls_back_to_og_then_title():
    from utils.website_enrichment import extract_company_info

    html = """<html><head>
    <title>The Lift Co - Strength Coaching | Liverpool</title>
    <meta name="description" content="Strength coaching for adults.">
    </head><body>
    <a href="tel:0151 555 4400">Call</a>
    <p>L1 4DQ</p>
    </body></html>"""
    info = extract_company_info(html, "https://liftco.co.uk")
    # No JSON-LD, no og:site_name — should clean the title separator
    assert info["name"] == "The Lift Co"
    assert info["phone"].startswith("0151")
    assert info["postcode"] == "L1 4DQ"
    # postcode triggered the UK country default
    assert info["country"] == "United Kingdom"
    assert info["description"] == "Strength coaching for adults."


def test_extract_company_info_picks_social_from_anchors_when_no_jsonld():
    from utils.website_enrichment import extract_company_info

    html = """<html><body>
    <a href="https://www.instagram.com/leanstudio">IG</a>
    <a href="https://twitter.com/leanstudio">TW</a>
    <a href="https://github.com/lean">GH</a>
    </body></html>"""
    info = extract_company_info(html, "https://lean.co.uk")
    assert "https://www.instagram.com/leanstudio" in info["social_links"]
    assert "https://twitter.com/leanstudio" in info["social_links"]
    # GitHub isn't in the social allowlist — should NOT be included
    assert all("github.com" not in s for s in info["social_links"])


def test_extract_company_info_returns_empty_for_empty_html():
    from utils.website_enrichment import extract_company_info

    assert extract_company_info("", "https://x.test") == {}


def test_merge_extractions_first_non_empty_wins():
    from utils.website_enrichment import merge_extractions

    out = merge_extractions(
        {"name": "Acme", "phone": ""},
        {"name": "Acme Trading", "phone": "020 1234"},
        {"email": "info@acme.test", "social_links": ["https://x.com/acme"]},
        {"social_links": ["https://instagram.com/acme"]},
    )
    assert out["name"] == "Acme"          # first non-empty
    assert out["phone"] == "020 1234"     # filled by the second extraction
    assert out["email"] == "info@acme.test"
    assert out["social_links"] == ["https://x.com/acme", "https://instagram.com/acme"]


# ─── 3. Endpoint registration + behaviour ───────────────────────────


def test_recognize_from_website_route_registered():
    from routes.crm_website_recognize import router
    paths = {r.path for r in router.routes}
    assert "/crm/v2/companies/recognize-from-website" in paths


def test_recognize_from_website_rejects_invalid_url():
    from routes.crm_website_recognize import recognize_from_website

    with pytest.raises(HTTPException) as exc:
        _run(recognize_from_website(
            data={"url": ""},
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))
    assert exc.value.status_code == 400


def test_recognize_from_website_returns_cached_when_present():
    """Repeated lookups within 24h must hit the cache, not the network."""
    from routes.crm_website_recognize import recognize_from_website

    cached_payload = {
        "company_info": {"name": "Acme", "phone": "020 1234"},
        "pages_fetched": ["/"],
    }
    fake_db = MagicMock()
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock(return_value=cached_payload)
    fake_db.__getitem__ = MagicMock(return_value=fake_collection)

    with patch("routes.crm_website_recognize.db", fake_db):
        out = _run(recognize_from_website(
            data={"url": "https://acme.test"},
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["cached"] is True
    assert out["source"] == "website"
    assert out["company_info"]["name"] == "Acme"
    assert out["pages_fetched"] == ["/"]
    assert out["url"] == "https://acme.test"


def test_recognize_from_website_scrapes_and_caches_on_miss():
    """Cache miss → live scrape → cache write."""
    from routes.crm_website_recognize import recognize_from_website

    fake_db = MagicMock()
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock(return_value=None)
    fake_collection.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    fake_db.__getitem__ = MagicMock(return_value=fake_collection)

    async def fake_scrape(base):
        return ({"name": "Live Co", "phone": "020 9999", "website": base, "source_url": base}, ["/"])

    with patch("routes.crm_website_recognize.db", fake_db), \
         patch("routes.crm_website_recognize._scrape_url", new=AsyncMock(side_effect=fake_scrape)):
        out = _run(recognize_from_website(
            data={"url": "live.test"},
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))

    assert out["cached"] is False
    assert out["success"] is True
    assert out["company_info"]["name"] == "Live Co"
    assert out["pages_fetched"] == ["/"]
    # Cache was written
    assert fake_collection.update_one.await_count == 1


def test_recognize_from_website_404s_when_no_data_extracted():
    """If nothing comes back from the live scrape, the user must
    see a clear error so they know to fill the form manually."""
    from routes.crm_website_recognize import recognize_from_website

    fake_db = MagicMock()
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock(return_value=None)
    fake_db.__getitem__ = MagicMock(return_value=fake_collection)

    async def empty_scrape(base):
        return ({}, [])

    with patch("routes.crm_website_recognize.db", fake_db), \
         patch("routes.crm_website_recognize._scrape_url", new=AsyncMock(side_effect=empty_scrape)), pytest.raises(HTTPException) as exc:
        _run(recognize_from_website(
            data={"url": "https://blocked.test"},
            user={"id": "u", "organization_id": "org-1", "role": "admin"},
        ))
    assert exc.value.status_code == 404


# ─── 4. Registration in the CRM router bundle ───────────────────────


def test_website_recognize_router_registered_with_crm_bundle():
    """Sanity check that the new router is wired into route_registry/crm.py
    so the endpoint is actually reachable at /api/crm/v2/...."""
    src = pathlib.Path(
        "/app/backend/route_registry/crm.py"
    ).read_text()
    assert "crm_website_recognize" in src
    assert "crm_website_recognize_router" in src


# ─── 5. Frontend wiring ─────────────────────────────────────────────


def test_companies_form_has_website_first_panel():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    assert 'data-testid="company-website-recognise-panel"' in src
    assert 'data-testid="company-website-url-input"' in src
    assert 'data-testid="company-website-lookup-btn"' in src
    # Hits the new endpoint
    assert "/crm/v2/companies/recognize-from-website" in src


def test_companies_form_maps_website_extract_into_form_fields():
    """The frontend extractor handler must spread the extracted
    payload into the form state so the right typing flows through."""
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    # The new handler must map at least these fields
    for fld in ("name", "phone", "email", "website", "city", "postcode", "description"):
        assert f"{fld}: info.{fld}" in src, f"missing setForm mapping for {fld}"


def test_companies_form_keeps_companies_house_path_as_secondary():
    """Companies House autocomplete should still be available but
    framed as a fallback (\"Or type a name to search Companies House\")."""
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text()
    assert 'Or type a name to search Companies House' in src
