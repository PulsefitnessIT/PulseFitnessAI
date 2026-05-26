# Pulse Fitness Brand Palette — canonical single source of truth

## Iter 220m (Brand canon · May 26, 2026) ✅

> **This doc covers the Pulse Fitness portal brand only.** For the
> primary GymAxis brand, see [`/app/BRAND_PALETTE.md`](BRAND_PALETTE.md).
> The two brands intentionally do NOT share tokens — every Pulse
> surface lives under `data-brand="pulse"` / `data-portal="pulse"` and
> every GymAxis surface lives under `.theme-gymaxis`. **Crossing the
> streams is a bug**, not an aesthetic choice.

---

## 1. The real Pulse Fitness palette (live, verified 2026-05-26)

Sourced verbatim from the authoritative in-app design reference at
[`/app/frontend/src/pages/MasterAdmin/PulseDesignTab.js`](frontend/src/pages/MasterAdmin/PulseDesignTab.js)
lines 10-19. Tokens also defined in
[`/app/frontend/src/index.css`](frontend/src/index.css) `:root` block.

### Brand accent (the signature)

| Token                       | Hex       | Use                                |
|-----------------------------|-----------|------------------------------------|
| `--color-brand-cyan`        | `#19CDFF` | **Primary CTA + accent** (Pulse's signature cyan) |
| `--color-brand-cyan-deep`   | `#0BB0DD` | Cyan gradient end / hover         |
| `--color-brand-cyan-hover`  | `#66CCFF` | Lighter hover tint on dark surfaces |
| `--pulse-primary`           | `#66ccff` | App-wide CTA token (alias used by Lite portal) |
| `--pulse-primary-deep`      | `#33b8ff` | Darker hover-shadow shade          |

Standard CTA pattern:

```css
.pulse-cta {
  background: #19CDFF;
  color: #0B1220;     /* dark ink, not white — cyan needs dark text for contrast */
  font-weight: 700;
}
.pulse-cta:hover { background: #0BB0DD; }
```

### Surfaces (Pulse is LIGHT-canvas, never dark)

| Token                       | Hex       | Use                                |
|-----------------------------|-----------|------------------------------------|
| `--color-white`             | `#FFFFFF` | Cards / panels                     |
| `--pulse-bg`                | `#F8F9FA` | Page canvas (warmer than GymAxis's slate-50) |
| `--color-slate-50`          | `#F1F5F9` | Section bands / hover backdrop     |
| `--pulse-border`            | `#E4E4E7` | Hairline rules                     |
| `--color-neutral-900`       | `#0F172A` | Dark CTAs / final hero panels      |

### Type

| Token                          | Hex       | Use                                |
|--------------------------------|-----------|------------------------------------|
| `--color-surface-dark-panel-alt` | `#0B1220` | Pulse ink — headings on light surface |
| `--color-text-slate`           | `#475569` | Body copy (slate-600)             |
| `--pulse-text-muted`           | `#505759` | Pulse-branded labels              |
| `--pulse-text-xs`              | `#A2ACAB` | Caption / fine print              |
| `--pulse-grey-light`           | `#A2ACAB` | (Same as above — alias)            |

### Semantic states (shared with GymAxis but Pulse-toned)

| Token            | Hex       | Use                       |
|------------------|-----------|---------------------------|
| `--color-success` | `#10B981` | Positive state            |
| `--color-warning` | `#F59E0B` | Cautionary state          |
| `--color-danger`  | `#EF4444` | Destructive / errors      |

### Typography

| Use                     | Font (with fallback chain)                        |
|-------------------------|---------------------------------------------------|
| H1 / Display headlines  | `"Proxima Nova", "Maax Rounded", "Inter", sans-serif` |
| Body                    | `"Proxima Nova", "Inter", system-ui, sans-serif` |
| Eyebrow / labels        | `font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase;` |

Proxima Nova is declared via `@font-face` in
`/app/frontend/public/index.html` (OTF files in
`/app/frontend/public/fonts/`). It is **Pulse only** — GymAxis uses
Satoshi + Inter.

### Logo

* **Component**: [`/app/frontend/src/components/shared/PulseFitnessLogo.js`](frontend/src/components/shared/PulseFitnessLogo.js)
* **Shape**: circular "blip" with a polyline heartbeat inside.
* **Primary variant**: cyan-filled circle on dark backgrounds
  (`circleColor = #66CCFF`).
* **Secondary variant**: Pulse-black-filled circle on light backgrounds
  (`circleColor = #212721`).
* **Inner line**: always white (`#FFFFFF`).
* **Wordmark**: not bundled as a single asset — render with `Proxima
  Nova 800` in the Pulse ink (`#0B1220` or `#212721` depending on
  context).

---

## 2. Scope guardrails — DO NOT cross-pollinate

| Scenario | Verdict |
|---|---|
| Pulse cyan `#19CDFF` on a GymAxis page | ❌ NEVER — see `BRAND_PALETTE.md §2` |
| GymAxis navy→purple gradient on a Pulse page | ❌ NEVER — breaks Pulse's customer recognition |
| Pulse dark-canvas variant | ❌ Doesn't exist — Pulse is always light-canvas |
| Pulse logo on a GymAxis surface | ❌ NEVER — different brand, different audience |
| Proxima Nova font outside `data-brand="pulse"` | ❌ NEVER — leaks Pulse identity into GymAxis |
| Cyan `#19CDFF` inside `.theme-gymaxis` | ❌ NEVER — even though the CSS remaps it to navy `#2563EB` for safety, hard-coding the literal hex sidesteps the remap and produces inconsistent surfaces. |

If a route serves both Pulse customers AND GymAxis customers (e.g.
shared marketing pages), the brand attribute on `<html>` /
`<body>` decides which palette applies. Read the active brand at
runtime — never hard-code.

---

## 3. Where the canon lives in code

| Surface                | Source of truth                                            |
|------------------------|------------------------------------------------------------|
| Authenticated Pulse portal | `:root` block in `/app/frontend/src/index.css` (lines 47-61) |
| Pulse Design Tab (in-app reference) | `/app/frontend/src/pages/MasterAdmin/PulseDesignTab.js` |
| Pulse logo             | `/app/frontend/src/components/shared/PulseFitnessLogo.js`  |
| Pulse Lite dashboard   | `/app/frontend/src/pages/LiteDashboardPage.js` + `data-portal="pulse"` |
| Pulse marketing pages  | `PulseLanding*.js`, `PulsePricing*.js` (and anything under `data-brand="pulse"`) |

When any of the above files change, this document **must** be updated
in the same commit. The `make docs-verify` quality gate keeps the iter
banner honest. The brand-canon regression test (`test_iter_220m_brand_canon.py`)
pins the Pulse hex codes too — silent drift fails CI.

---

## 4. Quick visual check for new Pulse surfaces

A correct Pulse Fitness surface satisfies *all* of:

* [ ] Background is **light** (`#FFFFFF` or `#F8F9FA`), never dark.
* [ ] Accent is **cyan `#19CDFF`** (never navy `#2563EB` — that's GymAxis).
* [ ] Headlines use **Proxima Nova** (or its fallback) in Pulse ink (`#0B1220` or `#212721`).
* [ ] CTAs use **dark text on cyan** (not white-on-cyan — fails contrast).
* [ ] Pulse Fitness logo is the **circular blip with internal heartbeat**, not the GymAxis GA glyph.
* [ ] No navy→purple gradient anywhere — that's GymAxis territory.

If any of those fail, the surface has drifted into the GymAxis
palette by mistake — fix before shipping.
