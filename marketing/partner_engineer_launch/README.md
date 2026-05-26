# Partner Engineer Launch — Instagram Campaign

The complete soft-launch campaign for the GymAxis Partner Engineer
program: 32 pixel-perfect assets rendered via Playwright in the live
brand palette (`#0055FF` electric blue · `#19CDFF` cyan · `#0A0C10`
ink · Outfit headlines · Inter body · JetBrains Mono for stats).

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

## Brand system (mirrors `/app/frontend/src/index.css`)

| Token | Hex |
|---|---|
| Brand Blue | `#0055FF` |
| Brand Blue Dark | `#003DA5` |
| Cyan Accent | `#19CDFF` |
| Ink (dark BG) | `#0A0C10` |
| Paper | `#FFFFFF` |
| Paper Alt | `#F4F4F5` |
| Cream | `#FAF8F2` |

**Fonts** (loaded from Google Fonts at render time):

| Use | Font |
|---|---|
| Display / Headlines | Outfit 800/900 (Satoshi-style geometric) |
| Body | Inter 400/500/600 |
| Stats / £-figures | JetBrains Mono 700 |

## Posting schedule

See [`CAPTIONS.md`](./CAPTIONS.md) for the 4-week rollout with one
ready-to-paste caption + hashtag set per asset, plus suggested UK
post times.

## Adding a new post

Open `generate.py`, write a new `post_NN_slides()` factory that
returns a list of `(slug, html_string)` tuples, and add it to
`all_posts()`. Each tuple becomes one PNG.

The shared `header()`, `footer_cta()`, `wrap()`, and `feature_slide()`
helpers plus the CSS in `BASE_HEAD` keep every tile visually
consistent without copy-pasting styling.

## Related campaigns in this repo

* `/app/marketing/instagram_campaign/` — gym-operator "9 Reasons"
  mosaic (separate audience, separate campaign).
* `/app/marketing/sicon-access/` — Sicon partner access request
  hand-off PDF.
* `/app/marketing/mod-presentation/` — MOD (UK Ministry of Defence)
  briefing deck.
