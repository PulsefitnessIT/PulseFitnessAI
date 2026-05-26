# Partner Engineer Launch — Instagram Campaign

## Iter 220m (Brand canon refresh · May 26, 2026)

The complete soft-launch campaign for the GymAxis Partner Engineer
program: 32 pixel-perfect assets rendered via Playwright in the
canonical GymAxis palette (light slate canvas + navy→purple gradient).

> **Brand colours → [`/app/BRAND_PALETTE.md`](../../BRAND_PALETTE.md).**
> This README does **not** duplicate hex codes. Every hex referenced by
> `generate.py` is sourced from `.theme-gymaxis` in
> `/app/frontend/src/index.css` and from `marketing.css`. If you find a
> stale hex in `generate.py` that doesn't match `BRAND_PALETTE.md`,
> `BRAND_PALETTE.md` wins — fix the script.

## What's here

```
partner_engineer_launch/
  generate.py                  · Playwright renderer (re-run any time)
  CAPTIONS.md                  · Ready-to-publish copy + 4-week schedule
  README.md                    · This file
  instagram/
    feed/                      · 19 feed assets (1080×1080)
    stories/                   · 8 story frames (1080×1920)
    highlights/                · 5 highlight covers (1080×1080)
```

## Regenerate

A single command rebuilds every asset from the HTML templates inside
`generate.py`. Use any time you tweak copy, swap a colour, or change
a stat:

```bash
cd /app && python3 marketing/partner_engineer_launch/generate.py
```

Each render takes ~1 second; the full set rebuilds in under a minute.

## Brand system (live · navy → purple)

| Surface | Token | Hex |
|---|---|---|
| Canvas | `--gx-bg` | `#F8FAFC` (slate-50) |
| Card | `--gx-bg-paper` | `#FFFFFF` |
| Gradient start | `--gx-brand-from` | `#2563EB` (navy) |
| Gradient mid | `--gx-brand-mid` | `#5B5BF5` (indigo) |
| Gradient end | `--gx-brand-to` | `#9D4CDD` (premium purple) |
| Headlines | `--gx-text` | `#0F172A` (slate-900) |
| Body | `--gx-text-body` | `#334155` (slate-700) |
| Muted | `--gx-text-muted` | `#64748B` (slate-500) |

Plus the page-bg "graph paper" recipe in `BRAND_PALETTE.md §1` — a
subtle 1px grid in `rgba(15,23,42,.04)` with two radial wash glows.

**Fonts** (loaded from Google Fonts at render time):

| Use | Font |
|---|---|
| Display / Headlines | Outfit 800/900 (Satoshi-style geometric) |
| Body | Inter 400/500/600 |
| Stats / £-figures | JetBrains Mono 700 |

> **DO NOT** use `#0055FF`, `#19CDFF`, or `#0A0C10` on any tile.
> Those are legacy GymAxis-pre-reset / Pulse Fitness tokens — every
> recurring "your colours are wrong" complaint has come from an agent
> trusting an older note that referenced them. See the full anti-pattern
> table in `BRAND_PALETTE.md §2`.

## Logo footgun (dark slides only)

`gymaxis-full-tight.png` is **flattened against white** (the source PNG
has a 100% opaque white background). CSS `filter: brightness(0)
invert(1);` therefore renders a solid white block on a gradient
background, *not* a readable wordmark.

`generate.py` solves this with `_to_white_silhouette()` — a tiny PIL
helper that colour-keys near-white pixels to transparent at import
time and re-encodes the result as a base64 data URI. Any new slide
that needs the white wordmark must use `LOGO_FULL_WHITE_DATA` (not
the raw `LOGO_FULL_DATA` with a CSS filter).

## No customer testimonials

The Partner Engineer program is **pre-launch** — we have no real
engineer customers yet, so every asset must be carried by product
features (Verified Engineer Card, branded PDFs, Stripe payouts,
real-economics receipt) rather than fabricated quotes. POST 9 in
`CAPTIONS.md` is a *product feature* card, not a testimonial.

## Posting schedule

See [`CAPTIONS.md`](./CAPTIONS.md) for the 4-week rollout with one
ready-to-paste caption + hashtag set per asset, plus suggested UK
post times.

## Adding a new post

Open `generate.py`, write a new `post_NN_slides()` factory that
returns a list of `(slug, html_string)` tuples, and add it to
`all_posts()`. Each tuple becomes one PNG.

The shared `header()`, `header_on_gradient()`, `footer_cta()`,
`wrap()`, and `feature_slide()` helpers plus the CSS in `BASE_HEAD`
keep every tile visually consistent without copy-pasting styling.

Before shipping any new tile run the visual check from
`BRAND_PALETTE.md §4`.

## Related campaigns in this repo

* `/app/marketing/instagram_campaign/` — gym-operator "9 Reasons"
  mosaic (separate audience, separate campaign).
* `/app/marketing/sicon-access/` — Sicon partner access request
  hand-off PDF.
* `/app/marketing/mod-presentation/` — MOD (UK Ministry of Defence)
  briefing deck.
