# GymAxis Brand Palette — canonical single source of truth

## Iter 220m (Brand canon · May 26, 2026) ✅

> **Read this file before touching ANY marketing asset, PDF template, email
> template, or `.theme-gymaxis` stylesheet.** It is the *only* doc you
> should trust for hex codes. Every other doc in this repo defers to this
> one and is regenerated against it.
>
> **For Pulse Fitness branding** (Pulse Lite portal, `data-brand="pulse"`
> surfaces), see [`/app/PULSE_BRAND_PALETTE.md`](PULSE_BRAND_PALETTE.md).
> The two brands intentionally do NOT share tokens.

---

## 1. The real GymAxis palette (live site, verified 2026-05-26)

These tokens come verbatim from
[`/app/frontend/src/index.css`](frontend/src/index.css) lines **1353-1373**
(`.theme-gymaxis` block) and
[`/app/frontend/src/pages/Marketing/marketing.css`](frontend/src/pages/Marketing/marketing.css)
— the two files that the live `gymaxisai.com` site actually loads.

### Surfaces

| Token             | Hex       | Use                                         |
|-------------------|-----------|---------------------------------------------|
| `--gx-bg`         | `#F8FAFC` | Page canvas (slate-50). **Light, never dark.** |
| `--gx-bg-paper`   | `#FFFFFF` | Card / panel surface                        |
| `--gx-bg-soft`    | `#F1F5F9` | Hover backdrop, input fills (slate-100)     |
| `--gx-border`     | `#E2E8F0` | Hairline rules (slate-200)                  |
| `--gx-border-strong` | `#CBD5E1` | Focused / divider (slate-300)             |

### Brand gradient (the signature element)

| Token             | Hex       | Use                                         |
|-------------------|-----------|---------------------------------------------|
| `--gx-brand-from` | `#2563EB` | **Navy-blue** — start of gradient, solid CTAs |
| `--gx-brand-mid`  | `#5B5BF5` | Mid (indigo) — only used for 3-stop gradients |
| `--gx-brand-to`   | `#9D4CDD` | **Premium purple** — end of gradient         |

Standard gradient declarations used across marketing/PDF/email surfaces:

```css
/* The hero "fitness engineers." heading + every primary CTA */
background: linear-gradient(135deg, #2563EB 0%, #5B5BF5 50%, #9D4CDD 100%);

/* Text-fill variant used on light backgrounds for accent words */
background: linear-gradient(90deg, #2563EB 0%, #9D4CDD 100%);
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
```

### Type

| Token              | Hex       | Use                                |
|--------------------|-----------|------------------------------------|
| `--gx-text`        | `#0F172A` | Headlines (slate-900)              |
| `--gx-text-body`   | `#334155` | Body copy (slate-700)              |
| `--gx-text-muted`  | `#64748B` | Labels, meta (slate-500)           |
| `--gx-text-dim`    | `#94A3B8` | Eyebrow, placeholder (slate-400)   |

### Page-background recipe (the subtle "graph paper" hero)

Mirrors `marketing.css` lines 184-187. Layer order matters:

```css
background:
  radial-gradient(circle at 50% 0%,  rgba(37,99,235,.08), transparent 50%),
  radial-gradient(circle at 80% 80%, rgba(157,76,221,.08), transparent 50%),
  linear-gradient(rgba(15,23,42,.04) 1px, transparent 1px) 0 0 / 32px 32px,
  linear-gradient(90deg, rgba(15,23,42,.04) 1px, transparent 1px) 0 0 / 32px 32px,
  #F8FAFC;
```

### Logo files

* **`/app/frontend/public/brand/gymaxis-full-tight.png`** — wordmark + GA glyph + "SMARTER FITNESS. STRONGER BUSINESS." tagline. **Opaque white background** (use directly on light slides).
* **`/app/frontend/public/brand/gymaxis-mark-tight.png`** — GA glyph only, opaque white background.

> **Footgun: rendering the logo on a dark surface.** The two files above
> are flattened against white, so `filter: brightness(0) invert(1);`
> produces a solid white block instead of a readable wordmark. If you
> need a white silhouette (e.g. for a dark gradient slide), generate one
> in code by colour-keying near-white pixels to transparent (see
> `_to_white_silhouette()` in `/app/marketing/partner_engineer_launch/generate.py`).

---

## 2. DO NOT USE — legacy tokens that get mistaken for GymAxis

The codebase still contains older brand systems, scoped to the **Pulse
Fitness** routes (`data-brand="pulse"`, `data-portal="pulse"`). Their
tokens live at `:root` and inside the `Pulse*` components. Every
recurring "your colours are wrong" complaint has come from an agent
crawling these by mistake and assuming they were GymAxis.

| Hex       | What it actually is                          | NEVER use it for                |
|-----------|----------------------------------------------|---------------------------------|
| `#0055FF` | Legacy GymAxis "electric blue" (pre-2026 reset) | Any 2026+ GymAxis surface       |
| `#19CDFF` | **Pulse Fitness** core cyan                  | Anything GymAxis-branded        |
| `#0A0C10` | **Pulse Fitness** ink / dark canvas          | GymAxis is **light-canvas** — never dark |
| `#003DA5` | Legacy GymAxis "blue deep"                   | Any 2026+ GymAxis surface       |
| `#66CCFF` | Pulse pastel cyan                            | Any GymAxis tile                |
| `#1B1D1D` | Pulse soft black                             | GymAxis headlines (use `#0F172A`) |
| `Outfit` (only, no fallback to brand sans) | Used by some marketing tiles but **brand sans is `Inter`** for body, `Satoshi` for h1-h4 inside `.theme-gymaxis`. |

If you find yourself reaching for any of these on a GymAxis surface,
stop and re-read **section 1** above.

---

## 3. Where the canon lives in code

| Surface          | Source of truth                                                 |
|------------------|-----------------------------------------------------------------|
| Authenticated app | `/app/frontend/src/index.css` — `.theme-gymaxis` block (1353-1373) |
| Marketing site   | `/app/frontend/src/pages/Marketing/marketing.css`               |
| Email templates  | `utils/email.py::wrap_branded()` — inlined for Gmail/Outlook    |
| PDF reports      | `utils/engineer_invoice_pdf.py`, `routes/svc/service_report.py` |
| Marketing assets | `/app/marketing/*/generate.py` (must import tokens from section 1) |

When any of the above files change, this document **must** be updated
in the same commit. The `make docs-verify` quality gate keeps the iter
banner honest, but it cannot detect a silently-drifted hex code — that
is on us.

---

## 4. Quick visual check for new agents

A correct GymAxis surface satisfies *all* of:

* [ ] Background is **light** (`#F8FAFC` or `#FFFFFF`), not dark.
* [ ] Subtle 1px grid in `rgba(15,23,42,.04)` is visible on hero panels.
* [ ] Accent colour is **navy → purple gradient** (`#2563EB → #9D4CDD`), never cyan.
* [ ] Logo wordmark reads "GYMAXIS · SMARTER FITNESS. STRONGER BUSINESS." in dark navy on light slides, or as a clean white silhouette on dark gradient slides.
* [ ] Primary CTA uses the 135° navy→purple gradient with a soft blue+purple shadow.
* [ ] No `#19CDFF` cyan glow text-shadow anywhere.

If any of those fail, the surface is on the **Pulse Fitness** palette
by mistake — fix before shipping.
