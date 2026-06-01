"""Iter 220ea·28 — public SEO surface: dynamic sitemap, crawler prerender,
IndexNow ping, and the broken-OG-image fix.

These guard the P0 SEO foundation that makes the autopilot's content
discoverable and shareable:

  • the sitemap is valid XML and includes published blog posts + static
    marketing pages (the static file never did),
  • the crawler prerender emits correct meta / Open Graph / canonical /
    JSON-LD and converts the Markdown body defensively (escaped),
  • ``og:image`` never leaks a base64 ``data:`` URI to social crawlers,
  • IndexNow is best-effort and safely no-ops without URLs / when disabled,
  • robots.txt points at the dynamic sitemap and the OG cover exists.
"""
import os
import re
import uuid
import xml.etree.ElementTree as ET

from tests.shared_loop import run_async
from utils.database import db
from utils.indexnow import _host, _site_base, ping_indexnow
from routes.seo_public import (
    STATIC_PAGES,
    _md_to_basic_html,
    _render_blog_html,
    _safe_image,
    build_sitemap_xml,
)


# ───────────────────────── Sitemap ───────────────────────────────

def test_sitemap_is_valid_xml_with_static_and_blog_urls():
    slug = "i28-test-" + uuid.uuid4().hex[:8]

    async def scenario():
        await db.seo_articles.insert_one({
            "id": str(uuid.uuid4()), "slug": slug, "status": "published",
            "title": "Test", "published_at": "2026-01-15T00:00:00+00:00",
            "updated_at": "2026-01-20T00:00:00+00:00",
        })
        xml = await build_sitemap_xml()
        await db.seo_articles.delete_one({"slug": slug})
        return xml

    xml = run_async(scenario())
    root = ET.fromstring(xml)  # raises if malformed
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [el.text for el in root.iter(f"{ns}loc")]
    assert any(loc.endswith("/pricing") for loc in locs)       # static page
    assert any(loc.endswith(f"/blog/{slug}") for loc in locs)  # dynamic post
    assert any(loc.endswith("/compare/glofox") for loc in locs)
    # the new post's lastmod uses updated_at, not "now"
    assert "2026-01-20" in xml


def test_homepage_has_top_priority():
    home = [p for p in STATIC_PAGES if p[0] == "/"][0]
    assert home[2] == 1.0


# ──────────────────── Markdown → safe HTML ────────────────────────

def test_md_to_html_escapes_and_converts():
    md = "# Heading\n\nSome **bold** text.\n\n- item one\n- item two"
    html = _md_to_basic_html(md)
    assert "<h2>Heading</h2>" in html          # # → h2 (h1 is the title)
    assert "<strong>bold</strong>" in html
    assert html.count("<li>") == 2
    # injection is neutralised
    assert "<script>" not in _md_to_basic_html("<script>alert(1)</script>")


def test_safe_image_rejects_data_uri():
    assert _safe_image({"hero_image_url": "data:image/jpeg;base64,AAAA"}).startswith("http")
    assert _safe_image({"hero_image_url": "https://cdn.x/img.jpg"}) == "https://cdn.x/img.jpg"
    assert _safe_image({}).endswith("/brand/og-cover.jpg")


# ───────────────────── Prerender HTML ─────────────────────────────

def test_prerender_html_has_seo_essentials():
    article = {
        "slug": "downtime-guide", "title": "Cutting Equipment Downtime",
        "meta_description": "How to cut gym equipment downtime.",
        "tags": ["maintenance", "ppm"],
        "hero_image_url": "data:image/jpeg;base64,SHOULD_NOT_LEAK",
        "published_at": "2026-01-10T00:00:00+00:00",
        "body_md": "# Intro\n\nKeep machines **running**.",
        "qa_blocks": [{"q": "Why?", "a": "Compliance and revenue."}],
    }
    html = _render_blog_html(article)
    assert "<title>Cutting Equipment Downtime | GymAxis AI</title>" in html
    assert 'rel="canonical" href="https://www.gymaxisai.com/blog/downtime-guide"' in html
    assert 'property="og:type" content="article"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    # data: URI must never reach og:image
    assert "SHOULD_NOT_LEAK" not in html
    assert "/brand/og-cover.jpg" in html
    # structured data present
    assert html.count("application/ld+json") == 3  # Article + Breadcrumb + FAQ
    assert '"@type": "FAQPage"' in html
    # human redirect + body for crawlers
    assert "window.location.replace" in html
    assert "<h1>Cutting Equipment Downtime</h1>" in html


# ───────────────────────── IndexNow ──────────────────────────────

def test_indexnow_site_and_host_parsing():
    assert _site_base().startswith("http")
    assert "." in _host() and "://" not in _host()


def test_indexnow_noops_safely():
    # no urls
    assert run_async(ping_indexnow([]))["submitted"] == 0
    # disabled via env — never touches the network
    os.environ["INDEXNOW_DISABLED"] = "1"
    try:
        res = run_async(ping_indexnow(["https://www.gymaxisai.com/blog/x"]))
        assert res["ok"] is False and res["reason"] == "disabled"
    finally:
        os.environ.pop("INDEXNOW_DISABLED", None)


# ─────────────── Static assets / robots wiring ────────────────────

def test_robots_points_to_dynamic_sitemap_and_allows_seo():
    with open("/app/frontend/public/robots.txt", encoding="utf-8") as f:
        robots = f.read()
    assert "Sitemap: https://www.gymaxisai.com/api/seo/sitemap.xml" in robots
    assert "Allow: /api/seo/" in robots
    # the Allow must appear before the broad Disallow: /api/ to take effect
    assert robots.index("Allow: /api/seo/") < robots.index("Disallow: /api/")


def test_indexnow_key_file_matches_configured_key():
    from utils.indexnow import INDEXNOW_KEY
    path = f"/app/frontend/public/{INDEXNOW_KEY}.txt"
    assert os.path.exists(path), "IndexNow key file missing"
    with open(path, encoding="utf-8") as f:
        assert f.read().strip() == INDEXNOW_KEY


def test_og_cover_image_exists():
    assert os.path.exists("/app/frontend/public/brand/og-cover.jpg")


def test_seo_router_registered_under_api():
    from routes.seo_public import router
    paths = {r.path for r in router.routes}
    assert "/api/seo/sitemap.xml" in paths
    assert any(re.match(r"/api/seo/share/blog/", p) for p in paths)
