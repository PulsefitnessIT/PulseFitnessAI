# SEO P0 — Crawlability foundation (activation guide)

Iter 220ea·28. This is the foundation that makes everything the SEO
autopilot publishes **discoverable** (sitemap), **indexed fast**
(IndexNow) and **shareable** (crawler prerender). Built backend-side so it
works regardless of the SPA.

## What shipped (live now)

| Capability | Endpoint / asset | Notes |
|---|---|---|
| **Dynamic sitemap** | `GET /api/seo/sitemap.xml` | Static marketing pages + comparison pages + **every published blog post** with real `lastmod`. Referenced from `robots.txt`. |
| **Crawler prerender** | `GET /api/seo/share/blog/{slug}` | Fully server-rendered HTML: title, meta, Open Graph, Twitter card, Article + BreadcrumbList + FAQPage JSON-LD, and the article body. Human browsers are JS-redirected to `/blog/{slug}`. |
| **IndexNow ping** | automatic on publish | Fires when an article is published or re-published (autopilot + manual). Manual: `POST /api/seo/indexnow/ping` (master-admin) `{ "slug": "..." }` or `{ "urls": [...] }`. |
| **OG cover fix** | `/brand/og-cover.jpg` | The homepage `og:image` pointed at a **missing** file — every social share had a broken image. Created a clean 1200×630 branded cover (also the blog OG fallback). |
| **Safe OG images** | — | Hero images stored as base64 `data:` URIs are never emitted as `og:image` (invalid for social crawlers); falls back to the brand cover. |

## Your activation steps (you / ops)

1. **Google Search Console** — verify `https://www.gymaxisai.com`, then
   submit the sitemap URL `https://www.gymaxisai.com/api/seo/sitemap.xml`.
   (We can add a `google-site-verification` meta tag to `index.html` the
   moment you have the token — just send it over.)
2. **Bing Webmaster Tools** — add the site and submit the same sitemap.
   IndexNow already notifies Bing/Yandex on publish via the hosted key file
   `/{INDEXNOW_KEY}.txt`.
3. *(Optional, for full organic bot coverage)* add a production **edge
   rule** so non-JS crawlers hitting `/blog/*` get the prerendered HTML.
   The backend already serves it; the edge just needs to route bots there.

   Cloudflare Worker (sketch):
   ```js
   const BOT = /bot|crawl|spider|slurp|facebookexternalhit|linkedinbot|twitterbot|slackbot|whatsapp|telegrambot|discordbot|embedly|quora|pinterest|preview/i;
   const m = url.pathname.match(/^\/blog\/([^/]+)$/);
   if (m && BOT.test(request.headers.get('user-agent') || '')) {
     return fetch(`${origin}/api/seo/share/blog/${m[1]}`, request);
   }
   ```
   Or, if you'd rather not touch the edge: point the autopilot's social
   share links at `/api/seo/share/blog/{slug}` (humans still get redirected
   to the SPA) — say the word and I'll wire it.

## Config (backend `.env`, optional)
- `SEO_SITE_URL` — canonical site origin (default `https://www.gymaxisai.com`).
- `INDEXNOW_KEY` — must match the hosted `/{key}.txt` file (default ships).
- `INDEXNOW_DISABLED=1` — kill-switch for the ping.

## Programmatic landing pages (P1, iter 220ea·29)

`/solutions/*` and `/maintenance/*` are programmatic SEO pages that
auto-enter the sitemap. Solution content lives in
`frontend/src/pages/Marketing/Landing/solutionsData.js` (keep slugs in sync
with `SOLUTION_SLUGS`). Manufacturer pages are data-driven from the
`manufacturer_catalogue` collection — a manufacturer earns a page once it
has >= 6 quality products (thin/marketing-heavy catalogues are excluded).
New manufacturers appear automatically as the catalogue ingests them.

## Note: canonical host
`index.html` + the sitemap use **`www.gymaxisai.com`**; the autopilot's
brand blurb references the bare `gymaxisai.com`. Pick one canonical host
and 301 the other at the edge to avoid splitting ranking signals (the
sitemap/prerender already standardise on `www`).
