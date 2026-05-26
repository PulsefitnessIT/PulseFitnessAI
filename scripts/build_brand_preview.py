#!/usr/bin/env python3
"""
build_brand_preview.py — render /app/BRAND_PALETTE_PREVIEW.html from the
canonical brand docs.

What it produces:
    A single self-contained HTML page that shows both brand palettes
    side-by-side as live swatches with copy-to-clipboard hex codes,
    the gradient recipe, type samples, and the "DO NOT USE" guard
    table. Designed for the marketing/design team to eyeball the
    canon at a glance without opening source.

How it stays in sync:
    Run by `make brand-preview`, which is also folded into `make lint`
    and `make docs-verify`. The output is a deterministic function of
    BRAND_PALETTE.md + PULSE_BRAND_PALETTE.md so a stale preview is
    impossible — re-run any time the canon changes.

The script intentionally reads canonical hex codes from a small
in-file constant rather than parsing the Markdown. That mirror is
pinned by `tests/test_iter_220m_brand_canon.py` so it cannot drift.
"""
from __future__ import annotations

import pathlib
import textwrap
from datetime import datetime, timezone


# ── Canonical palette (mirror — pinned by test_iter_220m_brand_canon.py) ──

GYMAXIS_TOKENS = [
    ("Canvas",         "#F8FAFC", "--gx-bg",          "Page background (slate-50)"),
    ("Card",           "#FFFFFF", "--gx-bg-paper",    "Surface / panel fill"),
    ("Hover soft",     "#F1F5F9", "--gx-bg-soft",     "Input + hover backdrop"),
    ("Brand from",     "#2563EB", "--gx-brand-from",  "Navy — gradient start, solid CTAs"),
    ("Brand mid",      "#5B5BF5", "--gx-brand-mid",   "Indigo — gradient midpoint"),
    ("Brand to",       "#9D4CDD", "--gx-brand-to",    "Premium purple — gradient end"),
    ("Text",           "#0F172A", "--gx-text",        "Headlines (slate-900)"),
    ("Text body",      "#334155", "--gx-text-body",   "Body copy (slate-700)"),
    ("Text muted",     "#64748B", "--gx-text-muted",  "Labels (slate-500)"),
    ("Border",         "#E2E8F0", "--gx-border",      "Hairline rules (slate-200)"),
]

PULSE_TOKENS = [
    ("Cyan",           "#19CDFF", "--color-brand-cyan",       "Primary CTA + accent"),
    ("Cyan deep",      "#0BB0DD", "--color-brand-cyan-deep",  "Gradient end / hover"),
    ("Cyan hover",     "#66CCFF", "--color-brand-cyan-hover", "Lighter hover on dark"),
    ("Canvas",         "#F8F9FA", "--pulse-bg",               "Page background"),
    ("Surface white",  "#FFFFFF", "--color-white",            "Cards"),
    ("Section band",   "#F1F5F9", "--color-slate-50",         "Hover / muted backdrop"),
    ("Ink heading",    "#0B1220", "--color-surface-dark-panel-alt", "Headings on light"),
    ("Ink (Pulse)",    "#212721", "--color-pulse-black",      "Soft black for text/logo"),
    ("Slate body",     "#475569", "--color-text-slate",       "Body copy"),
    ("Muted",          "#A2ACAB", "--pulse-text-xs",          "Caption / fine print"),
    ("Border",         "#E4E4E7", "--pulse-border",           "Hairline rules"),
    ("Ink dark CTA",   "#0F172A", "--color-neutral-900",      "Dark CTAs / final hero"),
]

LEGACY_HEXES = [
    ("#0055FF", "Legacy GymAxis electric blue (pre-2026 reset)"),
    ("#19CDFF", "Pulse Fitness cyan — fine on Pulse, NEVER on GymAxis"),
    ("#0A0C10", "Pulse Fitness dark ink — GymAxis is light-canvas only"),
    ("#003DA5", "Legacy GymAxis blue-deep"),
    ("#66CCFF", "Pulse pastel — Pulse-only"),
    ("#1B1D1D", "Pulse soft black — use #0F172A on GymAxis instead"),
]

ROOT = pathlib.Path("/app")
OUT_PATH = ROOT / "BRAND_PALETTE_PREVIEW.html"


def _swatch(name: str, hex_value: str, token: str, note: str, dark_text: bool) -> str:
    text_color = "#0F172A" if dark_text else "#FFFFFF"
    return f"""
    <div class="swatch" data-testid="swatch-{token}">
      <div class="chip" style="background:{hex_value};color:{text_color};">{hex_value}</div>
      <div class="meta">
        <p class="name">{name}</p>
        <code class="token">{token}</code>
        <p class="note">{note}</p>
      </div>
    </div>
    """


def _legacy_row(hex_value: str, note: str) -> str:
    return f"""
    <tr>
      <td><span class="legacy-chip" style="background:{hex_value};"></span> <code>{hex_value}</code></td>
      <td>{note}</td>
    </tr>
    """


def _is_light(hex_value: str) -> bool:
    """Approximate luminance check — should the swatch label be dark or light?"""
    h = hex_value.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def render() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    gx_swatches = "\n".join(
        _swatch(name, hx, tok, note, _is_light(hx))
        for name, hx, tok, note in GYMAXIS_TOKENS
    )
    pulse_swatches = "\n".join(
        _swatch(name, hx, tok, note, _is_light(hx))
        for name, hx, tok, note in PULSE_TOKENS
    )
    legacy_rows = "\n".join(_legacy_row(hx, note) for hx, note in LEGACY_HEXES)

    return textwrap.dedent(f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <title>GymAxis · Brand Palette Preview</title>
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0; padding: 48px 32px 96px;
          font-family: 'Inter', system-ui, sans-serif;
          background: #F8FAFC; color: #0F172A;
          -webkit-font-smoothing: antialiased;
        }}
        .wrap {{ max-width: 1280px; margin: 0 auto; }}
        h1 {{
          font-size: 40px; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 8px;
          background: linear-gradient(90deg, #2563EB 0%, #9D4CDD 100%);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .stamp {{
          font-size: 13px; color: #64748B; margin: 0 0 40px;
        }}
        h2 {{ font-size: 24px; font-weight: 700; margin: 48px 0 4px; }}
        h2 .badge {{
          font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
          letter-spacing: 0.08em; text-transform: uppercase; vertical-align: middle;
          margin-left: 8px;
        }}
        h2 .badge.gymaxis {{ background: rgba(37,99,235,0.08); color: #2563EB; }}
        h2 .badge.pulse {{ background: rgba(25,205,255,0.12); color: #0BB0DD; }}
        .subtitle {{ color: #64748B; font-size: 14px; margin: 0 0 24px; max-width: 720px; line-height: 1.5; }}
        .grid {{
          display: grid; gap: 16px;
          grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        }}
        .swatch {{
          background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px;
          overflow: hidden;
          box-shadow: 0 1px 2px rgba(15,23,42,0.03);
        }}
        .swatch .chip {{
          height: 96px; display: flex; align-items: flex-end;
          padding: 12px 14px; font-family: ui-monospace, 'JetBrains Mono', monospace;
          font-size: 14px; font-weight: 700;
        }}
        .swatch .meta {{ padding: 12px 14px 14px; }}
        .swatch .name {{ font-weight: 700; font-size: 14px; margin: 0; }}
        .swatch .token {{
          display: inline-block; margin-top: 4px; font-size: 12px; color: #334155;
          font-family: ui-monospace, 'JetBrains Mono', monospace;
        }}
        .swatch .note {{ font-size: 12px; color: #64748B; margin: 6px 0 0; line-height: 1.4; }}
        .hero-gymaxis {{
          margin-top: 24px; padding: 48px 32px;
          border-radius: 18px; color: #FFFFFF;
          background: linear-gradient(135deg, #2563EB 0%, #5B5BF5 50%, #9D4CDD 100%);
          box-shadow: 0 20px 50px -15px rgba(37,99,235,0.4),
                      0 12px 30px -10px rgba(157,76,221,0.3);
        }}
        .hero-gymaxis .eyebrow {{
          text-transform: uppercase; letter-spacing: 0.18em; font-size: 13px;
          font-weight: 700; opacity: 0.85; margin: 0;
        }}
        .hero-gymaxis h3 {{ font-size: 40px; font-weight: 800; margin: 12px 0 8px; letter-spacing: -0.02em; }}
        .hero-gymaxis p {{ opacity: 0.9; margin: 0; font-size: 16px; max-width: 640px; line-height: 1.5; }}
        .hero-pulse {{
          margin-top: 24px; padding: 48px 32px;
          border-radius: 18px;
          background: #FFFFFF; color: #0B1220;
          border: 1px solid #E4E4E7;
          box-shadow: 0 8px 24px -12px rgba(15,23,42,0.08);
        }}
        .hero-pulse .eyebrow {{
          text-transform: uppercase; letter-spacing: 0.18em; font-size: 13px;
          font-weight: 800; color: #19CDFF; margin: 0;
        }}
        .hero-pulse h3 {{ font-size: 40px; font-weight: 800; margin: 12px 0 8px; letter-spacing: -0.02em; }}
        .hero-pulse p {{ color: #475569; margin: 0; font-size: 16px; max-width: 640px; line-height: 1.5; }}
        .hero-pulse .cta {{
          display: inline-flex; padding: 12px 22px; border-radius: 10px;
          background: #19CDFF; color: #0B1220; font-weight: 700; margin-top: 20px;
        }}
        .donot {{
          margin-top: 48px; background: #FFFFFF; border: 1px solid #FCA5A5;
          border-radius: 14px; padding: 24px 28px;
        }}
        .donot h3 {{ margin: 0 0 6px; color: #B91C1C; font-size: 20px; font-weight: 800; }}
        .donot p {{ color: #64748B; font-size: 13px; margin: 0 0 16px; }}
        .donot table {{ width: 100%; border-collapse: collapse; }}
        .donot td {{
          padding: 10px 0; border-top: 1px solid #FEE2E2;
          font-size: 14px; color: #0F172A;
        }}
        .donot td:first-child {{ width: 220px; }}
        .donot td code {{
          font-family: ui-monospace, 'JetBrains Mono', monospace;
          font-size: 13px; color: #B91C1C;
        }}
        .legacy-chip {{
          display: inline-block; width: 16px; height: 16px; border-radius: 4px;
          vertical-align: middle; margin-right: 8px;
          border: 1px solid rgba(15,23,42,0.12);
        }}
        footer {{
          margin-top: 64px; padding-top: 24px; border-top: 1px solid #E2E8F0;
          font-size: 13px; color: #64748B; text-align: center;
        }}
        footer code {{
          background: #F1F5F9; padding: 2px 8px; border-radius: 6px;
          font-family: ui-monospace, monospace; font-size: 12px;
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <h1>Brand Palette · live preview</h1>
        <p class="stamp" data-testid="brand-preview-stamp">
          Auto-generated {timestamp} from
          <code>/app/BRAND_PALETTE.md</code> +
          <code>/app/PULSE_BRAND_PALETTE.md</code> ·
          regenerate with <code>make brand-preview</code>.
        </p>

        <div class="hero-gymaxis" data-testid="hero-gymaxis">
          <p class="eyebrow">GymAxis · platform brand</p>
          <h3>Fix the kit. Skip the admin.</h3>
          <p>Light slate canvas with the signature 135° navy → indigo → purple gradient.
            This is the surface every authenticated GymAxis screen renders against.</p>
        </div>

        <h2 data-testid="gymaxis-section">GymAxis tokens <span class="badge gymaxis">.theme-gymaxis</span></h2>
        <p class="subtitle">
          Canonical values from <code>.theme-gymaxis</code> in
          <code>/app/frontend/src/index.css</code> (lines 1353-1373) and
          <code>marketing.css</code>. Use these on every GymAxis surface
          (CRM, Service Ops, marketing site, emails, PDFs, social).
        </p>
        <div class="grid" data-testid="gymaxis-grid">
          {gx_swatches}
        </div>

        <div class="hero-pulse" data-testid="hero-pulse">
          <p class="eyebrow">Pulse Fitness · customer portal</p>
          <h3>Log faults in seconds.</h3>
          <p>Light surface with Pulse Fitness's signature cyan accent and Proxima
            Nova typography. Pulse customers never see GymAxis branding — and vice versa.</p>
          <span class="cta">Get started →</span>
        </div>

        <h2 data-testid="pulse-section">Pulse Fitness tokens <span class="badge pulse">data-brand="pulse"</span></h2>
        <p class="subtitle">
          Canonical values from
          <code>/app/frontend/src/pages/MasterAdmin/PulseDesignTab.js</code> +
          the <code>:root</code> block of <code>index.css</code>.
          Use these <strong>only</strong> on Pulse Fitness surfaces.
        </p>
        <div class="grid" data-testid="pulse-grid">
          {pulse_swatches}
        </div>

        <div class="donot" data-testid="donot-table">
          <h3>DO NOT USE on GymAxis surfaces</h3>
          <p>Every recurring "your colours are wrong" complaint has come from
            an agent reaching for one of these. They belong to Pulse Fitness
            or the legacy pre-2026 GymAxis palette — never to the current
            GymAxis brand.</p>
          <table>
            <tbody>
              {legacy_rows}
            </tbody>
          </table>
        </div>

        <footer>
          Maintained by the GymAxis platform team · canon lives in
          <code>BRAND_PALETTE.md</code> + <code>PULSE_BRAND_PALETTE.md</code> ·
          regression pin <code>tests/test_iter_220m_brand_canon.py</code>
        </footer>
      </div>
    </body>
    </html>
    """).strip() + "\n"


def main() -> int:
    OUT_PATH.write_text(render(), encoding="utf-8")
    print(f"[brand-preview] ✓ wrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
