# GymAxis · Partner Engineer Instagram Campaign — assets

All campaign assets for the Partner Engineer launch, rendered as
pixel-perfect 1080×1080 (feed) / 1080×1920 (stories) PNGs from
templated HTML so any slide can be re-rendered after a copy tweak.

## What's here

```
marketing/
  generate.py                  · Playwright renderer (re-run any time)
  CAPTIONS.md                  · Ready-to-publish captions + hashtags
  README.md                    · This file
  instagram/
    feed/                      · 19 feed assets (1080×1080)
    stories/                   · 8 story frames (1080×1920)
    highlights/                · 5 highlight covers (1080×1080)
```

## To regenerate

A single command rebuilds every asset from the HTML templates inside
`generate.py`. Use this any time you need to tweak copy, swap a colour
or change a stat:

```bash
cd /app/backend
python3 marketing/generate.py
```

Each render takes ~1 second; the full set rebuilds in under a minute.

## Brand system used (mirrors /app/frontend/src/index.css)

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

See `CAPTIONS.md` for the 4-week rollout with one ready-to-paste
caption + hashtag set per asset, plus suggested post times.

## Adding a new post

Open `generate.py`, write a new `post_NN_slides()` factory that returns
a list of `(slug, html_string)` tuples, and add it to `all_posts()`.
Each tuple becomes one PNG.

The shared `header()` / `footer_cta()` / `wrap()` helpers + the CSS
in `BASE_HEAD` keep every tile visually consistent without any
copy-paste of styling.
