"""Public SEO surface — dynamic sitemap + crawler prerender.

Why this exists
---------------
The marketing site is a client-rendered React SPA. Two SEO consequences
this module fixes:

1. **Discovery** — the hand-maintained ``frontend/public/sitemap.xml``
   never listed the blog posts the SEO autopilot publishes, so Google was
   never told they exist. ``GET /api/seo/sitemap.xml`` builds the sitemap
   live from the ``seo_articles`` collection (+ the static marketing pages
   and comparison pages). robots.txt points at it.

2. **Crawlability of dynamic content** — non-JS crawlers (LinkedIn,
   Facebook, WhatsApp, Slack, X) and first-pass Googlebot don't see the
   per-article ``<head>`` the SPA sets after hydration. ``GET
   /api/seo/share/blog/{slug}`` returns a fully server-rendered HTML page
   (title + meta + Open Graph + Article/FAQ/Breadcrumb JSON-LD + the
   article body) and redirects human browsers to the real ``/blog/{slug}``
   SPA route. The SEO autopilot's social share links can point here so
   social cards are always correct; in production an edge rule
   (Cloudflare Worker / nginx ``map $http_user_agent``) can also route
   organic bot traffic for ``/blog/*`` here.

Everything is read-only and unauthenticated except the manual IndexNow
ping (master-admin).
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response

from utils.auth import get_current_user
from utils.database import db
from utils.indexnow import ping_indexnow

router = APIRouter(prefix="/api/seo", tags=["seo-public"])


def _site() -> str:
    return (os.environ.get("SEO_SITE_URL") or "https://www.gymaxisai.com").rstrip("/")


# Static, indexable marketing pages (mirror robots.txt Allow list) with a
# crawl priority. Comparison pages are appended from COMPARE_SLUGS.
STATIC_PAGES: list[tuple[str, str, float]] = [
    ("/", "weekly", 1.0),
    ("/pricing", "monthly", 0.9),
    ("/features", "monthly", 0.8),
    ("/blog", "daily", 0.8),
    ("/compare", "monthly", 0.7),
    ("/contact", "monthly", 0.7),
    ("/about", "monthly", 0.6),
    ("/security", "monthly", 0.5),
    ("/whats-new", "weekly", 0.5),
    ("/privacy", "yearly", 0.3),
    ("/terms", "yearly", 0.3),
    ("/legal/dpa", "yearly", 0.3),
    ("/legal/dpia", "yearly", 0.3),
]
COMPARE_SLUGS = ["clubready", "glofox", "mindbody"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lastmod(value) -> str:
    """Coerce a stored date/datetime/string into a YYYY-MM-DD sitemap stamp."""
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    s = str(value)
    return s[:10]


def _url_node(loc: str, lastmod: str, changefreq: str, priority: float) -> str:
    return (
        "  <url>\n"
        f"    <loc>{html.escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority:.1f}</priority>\n"
        "  </url>"
    )


async def build_sitemap_xml() -> str:
    site = _site()
    nodes: list[str] = [
        _url_node(f"{site}{path}", datetime.now(timezone.utc).date().isoformat(), cf, pr)
        for path, cf, pr in STATIC_PAGES
    ]
    nodes += [
        _url_node(f"{site}/compare/{slug}",
                  datetime.now(timezone.utc).date().isoformat(), "monthly", 0.6)
        for slug in COMPARE_SLUGS
    ]
    # Published blog posts — the whole point of making this dynamic.
    cursor = db.seo_articles.find(
        {"status": "published"},
        {"_id": 0, "slug": 1, "published_at": 1, "updated_at": 1},
    ).sort("published_at", -1).limit(5000)
    async for art in cursor:
        slug = art.get("slug")
        if not slug:
            continue
        lastmod = _lastmod(art.get("updated_at") or art.get("published_at"))
        nodes.append(_url_node(f"{site}/blog/{slug}", lastmod, "monthly", 0.7))

    body = "\n".join(nodes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml():
    """Live sitemap — static pages + comparison pages + every published
    blog post. Referenced from robots.txt; submit to Search Console."""
    xml = await build_sitemap_xml()
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── Crawler prerender for blog posts ──────────────────────────────

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_LINK = re.compile(r"\[(.+?)\]\((.+?)\)")


def _md_to_basic_html(md: str) -> str:
    """Dependency-free, defensive Markdown → minimal HTML for crawlers.

    Handles headings, bullet lists, bold and links — everything is
    HTML-escaped first so stored content can never inject markup."""
    out: list[str] = []
    in_list = False
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        esc = html.escape(line.strip())
        esc = _MD_BOLD.sub(r"<strong>\1</strong>", esc)
        esc = _MD_LINK.sub(r'<a href="\2">\1</a>', esc)
        m = _MD_HEADING.match(esc)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = min(len(m.group(1)) + 1, 5)  # # → h2 (h1 is the title)
            out.append(f"<h{level}>{m.group(2)}</h{level}>")
        elif line.lstrip().startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:].lstrip('-* ').strip()}</li>")
        else:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _safe_image(article: dict) -> str:
    """og:image must be a real HTTP(S) URL. Hero images stored as base64
    ``data:`` URIs are unusable by social crawlers (and bloat the HTML) —
    fall back to the static brand cover for those."""
    hero = (article.get("hero_image_url") or "").strip()
    if hero.startswith("http"):
        return hero
    return f"{_site()}/brand/og-cover.jpg"


def _json_ld(article: dict, url: str) -> str:
    import json
    site = _site()
    image = _safe_image(article)
    blocks: list[dict] = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": (article.get("title") or "")[:110],
            "description": article.get("meta_description") or article.get("excerpt") or "",
            "image": [image],
            "datePublished": article.get("published_at") or article.get("created_at"),
            "dateModified": article.get("updated_at") or article.get("published_at"),
            "author": {"@type": "Organization", "name": "GymAxis AI", "url": site},
            "publisher": {
                "@type": "Organization", "name": "GymAxis AI",
                "logo": {"@type": "ImageObject",
                         "url": f"{site}/brand/gymaxis-logo.svg"},
            },
            "mainEntityOfPage": {"@type": "WebPage", "@id": url},
            "keywords": ", ".join(article.get("tags") or []),
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": site},
                {"@type": "ListItem", "position": 2, "name": "Blog",
                 "item": f"{site}/blog"},
                {"@type": "ListItem", "position": 3,
                 "name": (article.get("title") or "")[:90], "item": url},
            ],
        },
    ]
    qa = article.get("qa_blocks") or []
    faqs = [
        {"@type": "Question", "name": q.get("q") or q.get("question") or "",
         "acceptedAnswer": {"@type": "Answer",
                            "text": q.get("a") or q.get("answer") or ""}}
        for q in qa
        if (q.get("q") or q.get("question")) and (q.get("a") or q.get("answer"))
    ]
    if faqs:
        blocks.append({"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": faqs})
    return "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in blocks
    )


def _render_blog_html(article: dict) -> str:
    site = _site()
    slug = article.get("slug")
    canonical = f"{site}/blog/{slug}"
    title = html.escape((article.get("title") or "GymAxis AI Blog"))
    desc = html.escape((article.get("meta_description") or article.get("excerpt") or "")[:300])
    image = html.escape(_safe_image(article))
    has_real_image = (article.get("hero_image_url") or "").strip().startswith("http")
    tags = html.escape(", ".join(article.get("tags") or []))
    body_html = _md_to_basic_html(article.get("body_md") or "")
    json_ld = _json_ld(article, canonical)
    published = html.escape(str(article.get("published_at") or ""))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} | GymAxis AI</title>
<meta name="description" content="{desc}" />
<meta name="keywords" content="{tags}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<link rel="canonical" href="{canonical}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="GymAxis AI" />
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{desc}" />
<meta property="og:url" content="{canonical}" />
<meta property="og:image" content="{image}" />
<meta property="og:locale" content="en_GB" />
<meta property="article:published_time" content="{published}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title}" />
<meta name="twitter:description" content="{desc}" />
<meta name="twitter:image" content="{image}" />
{json_ld}
<script>
  // Human browsers land on the real SPA route; crawlers (no JS) keep this
  // fully-rendered HTML. Canonical already points at the SPA URL.
  try {{ if (!/bot|crawl|spider|slurp|facebookexternalhit|embedly|quora|whatsapp|slackbot|linkedinbot|twitterbot|telegrambot|discordbot|pinterest|preview/i.test(navigator.userAgent)) {{ window.location.replace({canonical!r}); }} }} catch (e) {{}}
</script>
</head>
<body>
<main>
<article>
<h1>{title}</h1>
{f'<img src="{image}" alt="{title}" />' if has_real_image else ''}
{body_html}
</article>
<p><a href="{canonical}">Read this article on GymAxis AI &rarr;</a></p>
</main>
</body>
</html>
"""


@router.get("/share/blog/{slug}", response_class=HTMLResponse)
async def prerender_blog(slug: str):
    """Crawler-facing, fully server-rendered HTML for a published blog
    post (correct meta + Open Graph + JSON-LD + body). Humans are
    redirected to the SPA route ``/blog/{slug}``."""
    article = await db.seo_articles.find_one(
        {"slug": slug, "status": "published"}, {"_id": 0},
    )
    if not article:
        raise HTTPException(404, "Post not found")
    return HTMLResponse(
        content=_render_blog_html(article),
        headers={"Cache-Control": "public, max-age=1800"},
    )


# ── Manual IndexNow ping (master-admin) ───────────────────────────

def _is_master_admin(user: dict) -> bool:
    return bool(user.get("is_master_admin") or user.get("account_type") == "gymaxis_admin")


@router.post("/indexnow/ping")
async def manual_indexnow_ping(body: dict, user=Depends(get_current_user)):
    """Manually notify IndexNow of one or more URLs (master-admin).
    Body: {urls: [...]} (absolute or site-relative) or {slug: '...'}."""
    if not _is_master_admin(user):
        raise HTTPException(403, "Master admin only")
    site = _site()
    urls = body.get("urls") or []
    if body.get("slug"):
        urls.append(f"/blog/{body['slug']}")
    urls = [u if u.startswith("http") else f"{site}{u if u.startswith('/') else '/' + u}"
            for u in urls]
    return await ping_indexnow(urls)


__all__ = ["router", "build_sitemap_xml", "ping_indexnow"]
