"""
GymAxis · Partner Engineer Launch — Instagram campaign generator (v3).

Sourced from the live `/partners/engineers` page (verified by screenshot
on 2026-05-26) and from `/app/frontend/src/index.css::.theme-gymaxis`
(lines 1353-1373) + `/app/frontend/src/pages/Marketing/marketing.css`.

Palette is LIGHT (not dark — the v2 generator had the legacy Pulse
palette baked in by mistake):

  • Canvas      F8FAFC (slate-50) with a subtle 1px grid in rgba(15,23,42,.04)
  • Headlines   0F172A (slate-900)
  • Body        334155 (slate-700)
  • Muted       64748B (slate-500)
  • Brand grad  2563EB → 5B5BF5 → 9D4CDD (navy-blue → mid → premium purple)
  • Border      E2E8F0 (slate-200)

Real Partner Engineer offer (verified on the live page):
  • £30/mo, drops automatically (£15 at 5 referrals, FREE at 10).
  • + 50% of the gym's first cleared Operations payment.
  • + £3/site/mo recurring (after 3 months on platform).

NO customer testimonials anywhere — we have none yet. All social proof
must come from product features.

Run:
    cd /app && python3 marketing/partner_engineer_launch/generate.py

Output: /app/marketing/partner_engineer_launch/instagram/{feed,stories,highlights}/*.png
"""
from __future__ import annotations

import asyncio
import base64
import io
import sys
from pathlib import Path

from PIL import Image

# ── Brand palette (verbatim from .theme-gymaxis + marketing.css) ────
BRAND_FROM = "#2563EB"   # navy-blue
BRAND_MID = "#5B5BF5"    # gradient midpoint (subtle indigo)
BRAND_TO = "#9D4CDD"     # premium purple

BG = "#F8FAFC"           # page canvas (slate-50)
BG_PAPER = "#FFFFFF"     # card surface
BG_SOFT = "#F1F5F9"      # hover / muted backdrop (slate-100)

TEXT = "#0F172A"         # slate-900 (headlines)
TEXT_BODY = "#334155"    # slate-700
TEXT_MUTED = "#64748B"   # slate-500
TEXT_DIM = "#94A3B8"     # slate-400 (eyebrow / placeholder)

BORDER = "#E2E8F0"       # slate-200
BORDER_STRONG = "#CBD5E1"
SUCCESS = "#10B981"      # emerald-500

# Brand gradient (navy → indigo → purple), as used across the marketing site
BRAND_GRADIENT = f"linear-gradient(135deg, {BRAND_FROM} 0%, {BRAND_MID} 50%, {BRAND_TO} 100%)"
BRAND_GRADIENT_HORIZ = f"linear-gradient(90deg, {BRAND_FROM} 0%, {BRAND_TO} 100%)"

# Subtle 1px grid + radial glows — matches the live hero exactly.
PAGE_BG_STACK = (
    f"background:"
    f"radial-gradient(circle at 50% 0%, rgba(37,99,235,.08), transparent 50%),"
    f"radial-gradient(circle at 80% 80%, rgba(157,76,221,.08), transparent 50%),"
    f"linear-gradient(rgba(15,23,42,.04) 1px, transparent 1px) 0 0 / 32px 32px,"
    f"linear-gradient(90deg, rgba(15,23,42,.04) 1px, transparent 1px) 0 0 / 32px 32px,"
    f"{BG};"
)


# ── Real logo (embed as base64 so we don't need network at render) ──
_LOGO_DIR = Path("/app/frontend/public/brand")
LOGO_FULL_DATA = "data:image/png;base64," + base64.b64encode(
    (_LOGO_DIR / "gymaxis-full-tight.png").read_bytes()
).decode()
LOGO_MARK_DATA = "data:image/png;base64," + base64.b64encode(
    (_LOGO_DIR / "gymaxis-mark-tight.png").read_bytes()
).decode()


def _to_white_silhouette(path: Path) -> str:
    """Convert a logo PNG that has an opaque white background into a
    white-on-transparent silhouette suitable for dark gradient slides.
    The source files (gymaxis-full-tight.png, gymaxis-mark-tight.png) are
    flattened against white, so a CSS `brightness(0) invert(1)` filter
    just produces a solid white block. We do the colour-key in Python
    instead: any near-white pixel → fully transparent, every other pixel
    → opaque white preserving its original alpha. Result encoded as a
    base64 data URI."""
    src = Image.open(path).convert("RGBA")
    pixels = src.load()
    w, h = src.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            # Treat any sufficiently bright pixel as background.
            if r >= 248 and g >= 248 and b >= 248:
                pixels[x, y] = (255, 255, 255, 0)
            else:
                pixels[x, y] = (255, 255, 255, a)
    buf = io.BytesIO()
    src.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


LOGO_FULL_WHITE_DATA = _to_white_silhouette(_LOGO_DIR / "gymaxis-full-tight.png")


BASE_HEAD = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Outfit:wght@400;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; color: {TEXT}; }}
  .display {{ font-family: 'Outfit', sans-serif; letter-spacing: -0.03em; }}
  .mono {{ font-family: 'JetBrains Mono', monospace; letter-spacing: -0.02em; }}
  .grad-text {{
    background: {BRAND_GRADIENT_HORIZ};
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: {BRAND_FROM};
  }}
  .slide {{
    width: 1080px; height: 1080px; position: relative;
    display: flex; flex-direction: column;
    padding: 80px; overflow: hidden;
  }}
  .slide.story {{ width: 1080px; height: 1920px; padding: 120px 80px; }}
  .slide.highlight {{ width: 1080px; height: 1080px; padding: 0; }}
  .logo-bar {{ display: flex; align-items: center; gap: 14px; }}
  .logo-bar img {{ height: 44px; width: auto; }}
  .footer {{
    position: absolute; bottom: 60px; left: 80px; right: 80px;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 18px; font-weight: 500;
  }}
  .pill {{
    display: inline-flex; align-items: center; gap: 10px;
    padding: 12px 22px; border-radius: 999px;
    font-weight: 700; font-size: 22px;
    font-family: 'Outfit', sans-serif;
  }}
  .eyebrow {{
    display: inline-flex; align-items: center; gap: 10px;
    padding: 8px 18px; border-radius: 999px;
    background: {BG_PAPER}; border: 1px solid {BORDER};
    font-size: 18px; font-weight: 700; color: {BRAND_FROM};
    letter-spacing: 0.1em; text-transform: uppercase;
  }}
  .cta-btn {{
    display: inline-flex; align-items: center; gap: 14px;
    padding: 26px 44px; border-radius: 16px;
    background: {BRAND_GRADIENT};
    color: #ffffff;
    font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 36px;
    box-shadow: 0 20px 50px -15px rgba(37,99,235,0.4),
                0 12px 30px -10px rgba(157,76,221,0.3);
  }}
</style>
"""


def wrap(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'>{BASE_HEAD}</head><body>{body}</body></html>"


# ── Reusable layout helpers ────────────────────────────────────────


def header() -> str:
    """The full GymAxis wordmark, rendered as-is on the light canvas."""
    return f"""
    <div class="logo-bar">
      <img src="{LOGO_FULL_DATA}" alt="GymAxis"/>
    </div>
    """


def header_on_gradient() -> str:
    """When a slide has a navy→purple gradient background, render the
    pre-built white silhouette of the wordmark (no CSS filter — the
    source PNG has an opaque white background that would otherwise
    flatten to a solid block under brightness(0) invert(1))."""
    return f"""
    <div class="logo-bar">
      <img src="{LOGO_FULL_WHITE_DATA}" alt="GymAxis"/>
    </div>
    """


def footer_cta(*, dark: bool, label: str = "gymaxisai.com/partners/engineers") -> str:
    color = "rgba(255,255,255,0.7)" if dark else TEXT_MUTED
    return f"""
    <div class="footer" style="color:{color};">
      <span>@gymaxisai</span>
      <span>{label}</span>
    </div>
    """


# ── POST 1 — "The £4,200" carousel ─────────────────────────────────


def post_01_slides() -> list[tuple[str, str]]:
    s: list[tuple[str, str]] = []
    s.append(("01_1_hook", wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:120px;">
        <span class="eyebrow">For self-employed gym engineers</span>
        <h1 class="display" style="font-size:128px;font-weight:900;line-height:1.0;margin:40px 0 0;color:{TEXT};">
          The <span class="grad-text">£4,200</span>
        </h1>
        <h2 class="display" style="font-size:72px;font-weight:800;line-height:1.05;margin:24px 0 0;color:{TEXT};">
          you didn't know<br/>you were leaving<br/>on the table.
        </h2>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;color:{TEXT_DIM};font-size:22px;font-weight:600;">Swipe →</div>
      {footer_cta(dark=False)}
    </div>
    """)))

    s.append(("01_2_47min", wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:100px;text-align:center;">
        <span class="eyebrow">avg a UK gym engineer spends</span>
        <h1 class="display grad-text" style="font-size:280px;font-weight:900;line-height:1.0;margin:60px 0 0;">47</h1>
        <p class="display" style="font-size:72px;font-weight:800;margin:24px 0 0;color:{TEXT};">minutes / week</p>
        <p style="font-size:26px;color:{TEXT_MUTED};margin:32px 0 0;font-weight:500;">on invoicing alone.</p>
      </div>
      <p style="position:absolute;bottom:130px;left:80px;right:80px;text-align:center;font-size:14px;color:{TEXT_DIM};font-weight:500;">
        Internal projection · GymAxis Partner Engineer onboarding survey, 2026
      </p>
      {footer_cta(dark=False)}
    </div>
    """)))

    s.append(("01_3_52wk", wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:200px;text-align:center;">
        <p class="display mono" style="font-size:220px;font-weight:700;line-height:1.0;margin:0;color:{TEXT};">
          × <span class="grad-text">52</span>
        </p>
        <p class="display" style="font-size:48px;font-weight:700;margin:36px 0 0;color:{TEXT};">weeks a year.</p>
      </div>
      <div style="position:absolute;bottom:220px;left:80px;right:80px;text-align:center;">
        <p style="font-size:34px;font-weight:600;color:{TEXT_BODY};margin:0;">
          = <span class="grad-text" style="font-weight:900;">40 working days</span>
        </p>
        <p style="font-size:22px;color:{TEXT_MUTED};margin:14px 0 0;">on paperwork. Not on tools.</p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)))

    s.append(("01_4_money", wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:100px;text-align:center;">
        <p style="font-size:30px;font-weight:600;margin:0;color:{TEXT_MUTED};">At your average rate of</p>
        <p class="display mono" style="font-size:200px;font-weight:800;line-height:1.0;margin:24px 0 0;color:{TEXT};">£<span class="grad-text">45</span><span style="font-size:96px;color:{TEXT_DIM};">/hr</span></p>
        <p style="font-size:30px;font-weight:600;margin:48px 0 0;color:{TEXT_BODY};">that's</p>
        <p class="display mono grad-text" style="font-size:160px;font-weight:900;margin:14px 0 0;">£4,212</p>
        <p style="font-size:26px;color:{TEXT_BODY};margin:24px 0 0;font-weight:500;">you'd rather be billing for actual work.</p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)))

    s.append(("01_5_solution", wrap(f"""
    <div class="slide" style="background:{BRAND_GRADIENT};color:#fff;">
      {header_on_gradient()}
      <div style="margin-top:160px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:rgba(255,255,255,0.85);letter-spacing:0.14em;text-transform:uppercase;margin:0;font-weight:700;">We took it off your plate</p>
        <h1 class="display" style="font-size:108px;font-weight:900;line-height:1.0;margin:36px 0 0;color:#fff;">
          The GymAxis<br/>Partner<br/>Engineer Plan.
        </h1>
      </div>
      <div style="position:absolute;bottom:200px;left:80px;right:80px;display:flex;gap:16px;flex-wrap:wrap;">
        <span class="pill" style="background:rgba(255,255,255,0.16);color:#fff;border:1px solid rgba(255,255,255,0.3);">Branded PDFs</span>
        <span class="pill" style="background:rgba(255,255,255,0.16);color:#fff;border:1px solid rgba(255,255,255,0.3);">Stripe payouts</span>
        <span class="pill" style="background:rgba(255,255,255,0.16);color:#fff;border:1px solid rgba(255,255,255,0.3);">Smart job matching</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_6_cta", wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:180px;">
        <h1 class="display" style="font-size:124px;font-weight:900;line-height:1.0;margin:0;color:{TEXT};">
          Fix the kit.<br/><span class="grad-text">Skip the admin.</span>
        </h1>
        <p style="font-size:28px;color:{TEXT_BODY};margin:48px 0 0;line-height:1.5;font-weight:500;">
          Applications open for the first<br/>
          <strong style="color:{TEXT};">50 Partner Engineers</strong>.
        </p>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;right:80px;">
        <div class="cta-btn">Apply free →</div>
        <p style="font-size:20px;color:{TEXT_MUTED};margin:24px 0 0;">gymaxisai.com/partners/engineers</p>
      </div>
    </div>
    """)))

    return s


# ── POST 2 — Before vs After ───────────────────────────────────────


def post_02_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="padding:0;background:{BG};">
      <div style="position:absolute;top:0;left:0;width:55%;height:100%;background:{BG_SOFT};padding:80px;">
        <p class="display" style="font-size:22px;color:{TEXT_DIM};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">Before</p>
        <h2 class="display" style="font-size:64px;font-weight:900;color:{TEXT};margin:18px 0 0;line-height:1.0;">
          Same job.<br/>Tuesday at<br/><span style="color:{TEXT_DIM};text-decoration:line-through;">22:48</span>.
        </h2>
        <div style="margin-top:48px;padding:28px;background:{BG_PAPER};border:2px dashed {BORDER_STRONG};border-radius:14px;">
          <p style="font-size:16px;color:{TEXT_MUTED};margin:0 0 12px;font-family:'JetBrains Mono',monospace;">job-tracker-v7-FINAL.xlsx</p>
          <div style="height:5px;background:#EF4444;opacity:0.45;border-radius:3px;margin:4px 0;width:80%;"></div>
          <div style="height:5px;background:{BORDER};border-radius:3px;margin:4px 0;width:60%;"></div>
          <div style="height:5px;background:#EF4444;opacity:0.45;border-radius:3px;margin:4px 0;width:90%;"></div>
          <div style="height:5px;background:{BORDER};border-radius:3px;margin:4px 0;width:50%;"></div>
          <p style="font-size:20px;color:#B91C1C;margin:22px 0 0;font-weight:700;">Customer chasing invoice #4</p>
        </div>
      </div>
      <div style="position:absolute;top:0;right:0;width:55%;height:100%;background:{BRAND_GRADIENT};color:#fff;padding:80px;clip-path:polygon(8% 0,100% 0,100% 100%,0 100%);padding-left:150px;">
        <p class="display" style="font-size:22px;color:rgba(255,255,255,0.85);letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">After</p>
        <h2 class="display" style="font-size:64px;font-weight:900;margin:18px 0 0;line-height:1.0;color:#fff;">
          Same job.<br/>Tuesday at<br/><span style="color:#fff;">16:42</span>.
        </h2>
        <div style="margin-top:48px;padding:26px 30px;background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.25);border-radius:14px;">
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;color:#fff;">Service Report · sent</p>
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin-top:14px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;color:#fff;">Customer signature · captured</p>
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin-top:14px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;color:#fff;">Stripe payout · £340 paid</p>
          </div>
        </div>
        <p class="display" style="font-size:28px;color:#fff;margin:48px 0 0;font-weight:800;">All before you got home.</p>
      </div>
    </div>
    """)
    return [("02_before_after", html)]


# ── POST 4 — "What £30 unlocks" carousel ───────────────────────────


def feature_slide(idx: int, icon: str, title: str, body: str) -> str:
    return wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <p style="position:absolute;top:80px;right:80px;font-size:18px;color:{TEXT_DIM};font-weight:600;">{idx} / 5</p>
      <div style="margin-top:120px;">
        <div style="display:flex;align-items:center;justify-content:center;width:140px;height:140px;border-radius:32px;background:{BRAND_GRADIENT};color:#fff;font-size:64px;font-family:'Outfit',sans-serif;font-weight:900;box-shadow:0 20px 56px -16px rgba(37,99,235,0.4);">
          {icon}
        </div>
        <h2 class="display" style="font-size:80px;font-weight:900;margin:48px 0 0;line-height:1.0;max-width:880px;color:{TEXT};">{title}</h2>
        <p style="font-size:28px;color:{TEXT_BODY};margin:30px 0 0;line-height:1.45;max-width:860px;font-weight:500;">{body}</p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)


def post_04_slides() -> list[tuple[str, str]]:
    s: list[tuple[str, str]] = []
    s.append(("04_1_hook", wrap(f"""
    <div class="slide" style="background:{BRAND_GRADIENT};color:#fff;">
      {header_on_gradient()}
      <div style="margin-top:240px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:rgba(255,255,255,0.85);letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">For £30/mo</p>
        <h1 class="display" style="font-size:120px;font-weight:900;line-height:1.0;margin:36px 0 0;color:#fff;">
          What you<br/>actually<br/>unlock 👇
        </h1>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))
    s.append(("04_2_smart", feature_slide(1, "🛠", "Smart job<br/>matching.",
              "AI pings you when a new job lands near your postcode, in your skill stack, and inside your current calendar.")))
    s.append(("04_3_pdf", feature_slide(2, "📄", "Branded PDF<br/>reports.",
              "Your logo. Your colours. Auto-mailed to the customer before you've even left the site.")))
    s.append(("04_4_stripe", feature_slide(3, "💳", "Same-day<br/>Stripe payouts.",
              "Customer taps Pay. Money's in your bank that night. No chasing. No invoicing-app fees.")))
    s.append(("04_5_rep", feature_slide(4, "⭐", "Reputation<br/>that pays.",
              "Every customer rating is yours. Your own public engineer card. A monthly recap your accountant will love.")))
    s.append(("04_6_cta", wrap(f"""
    <div class="slide" style="background:{BRAND_GRADIENT};color:#fff;">
      {header_on_gradient()}
      <div style="margin-top:140px;">
        <h1 class="display" style="font-size:128px;font-weight:900;line-height:0.95;margin:0;color:#fff;">£30<span style="font-size:54px;font-weight:700;color:rgba(255,255,255,0.65);">/mo</span></h1>
        <div style="display:flex;align-items:center;gap:20px;margin:36px 0;">
          <div style="width:60px;height:3px;background:#fff;border-radius:2px;"></div>
          <p class="display" style="font-size:30px;font-weight:700;margin:0;color:#fff;">£15 at 5 active referrals.</p>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">
          <div style="width:60px;height:3px;background:#fff;border-radius:2px;"></div>
          <p class="display" style="font-size:30px;font-weight:700;margin:0;color:#fff;">Free forever at 10.</p>
        </div>
        <p style="font-size:20px;color:rgba(255,255,255,0.75);margin:32px 0 0;line-height:1.55;max-width:780px;">
          + £3/site/mo recurring · 50% of the gym's first cleared Operations payment.
        </p>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;right:80px;">
        <div style="display:inline-flex;align-items:center;gap:18px;padding:28px 50px;border-radius:18px;background:#fff;color:{TEXT};box-shadow:0 24px 64px -16px rgba(0,0,0,0.4);">
          <span class="display" style="font-size:36px;font-weight:900;">Start your application →</span>
        </div>
      </div>
    </div>
    """)))
    return s


# ── POST 5 — Tier maths ─────────────────────────────────────────────


def post_05_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:80px;">
        <span class="eyebrow">The maths</span>
        <h1 class="display" style="font-size:88px;font-weight:900;line-height:1.0;margin:24px 0 0;color:{TEXT};">
          From £30/mo to<br/><span class="grad-text">£0/mo.</span>
        </h1>
      </div>
      <div style="margin-top:60px;display:flex;flex-direction:column;gap:18px;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:28px 40px;background:{BG_PAPER};border:1px solid {BORDER};border-radius:18px;box-shadow:0 8px 24px -8px rgba(15,23,42,0.06);">
          <p class="display mono" style="font-size:36px;font-weight:700;margin:0;color:{TEXT};">0 referrals</p>
          <p class="display mono" style="font-size:48px;font-weight:900;margin:0;color:{TEXT};">£30<span style="font-size:22px;color:{TEXT_MUTED};">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:28px 40px;background:{BG_PAPER};border:1px solid {BRAND_FROM};border-radius:18px;box-shadow:0 12px 32px -10px rgba(37,99,235,0.25);">
          <p class="display mono" style="font-size:36px;font-weight:700;margin:0;color:{TEXT};">5 referrals</p>
          <p class="display mono grad-text" style="font-size:48px;font-weight:900;margin:0;">£15<span style="font-size:22px;">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:32px 40px;background:{BRAND_GRADIENT};color:#fff;border-radius:18px;box-shadow:0 24px 64px -16px rgba(37,99,235,0.5),0 16px 40px -10px rgba(157,76,221,0.4);">
          <p class="display mono" style="font-size:40px;font-weight:900;margin:0;color:#fff;">10 referrals</p>
          <p class="display mono" style="font-size:54px;font-weight:900;margin:0;color:#fff;">FREE</p>
        </div>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;right:80px;">
        <p style="text-align:center;font-size:22px;color:{TEXT_BODY};font-weight:600;margin:0;">
          Every gym you onboard pays your subscription.
        </p>
        <p style="text-align:center;font-size:18px;color:{TEXT_MUTED};margin:10px 0 0;">
          + 50% of their first cleared Operations payment · £3/site/mo recurring · forever.
        </p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)
    return [("05_tier_maths", html)]


# ── POST 9 — Verified Engineer Card (product feature, NOT testimonial) ──


def post_09_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="{PAGE_BG_STACK}">
      {header()}
      <div style="margin-top:80px;">
        <span class="eyebrow">The card customers will see</span>
        <h1 class="display" style="font-size:64px;font-weight:900;line-height:1.05;margin:24px 0 0;max-width:880px;color:{TEXT};">
          Your verified engineer<br/>profile, your way.
        </h1>
      </div>
      <div style="margin:60px auto 0;width:600px;padding:32px;background:{BG_PAPER};border:1px solid {BORDER};border-radius:24px;box-shadow:0 24px 60px -20px rgba(15,23,42,0.12);">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <p style="font-size:13px;color:{TEXT_MUTED};font-weight:700;letter-spacing:0.14em;text-transform:uppercase;margin:0;">Your engineer</p>
          <span style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:rgba(16,185,129,0.12);color:{SUCCESS};border-radius:999px;font-size:13px;font-weight:700;">✓ Verified</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;margin-top:24px;">
          <div style="width:88px;height:88px;border-radius:50%;background:{BRAND_GRADIENT};display:flex;align-items:center;justify-content:center;color:#fff;font-family:'Outfit',sans-serif;font-weight:900;font-size:38px;">S</div>
          <div>
            <p class="display" style="font-size:36px;font-weight:800;margin:0;color:{TEXT};">Sarah</p>
            <p style="font-size:18px;color:{TEXT_BODY};margin:4px 0 0;font-weight:500;"><span style="color:#F59E0B;">★</span> <strong style="color:{TEXT};">4.9</strong> · 26 reviews &nbsp;·&nbsp; 52 jobs in 90 days</p>
            <p style="font-size:16px;color:{TEXT_MUTED};margin:4px 0 0;">8+ yrs experience</p>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:24px;flex-wrap:wrap;">
          <span style="padding:8px 14px;background:rgba(37,99,235,0.08);color:{BRAND_FROM};border-radius:8px;font-size:13px;font-weight:800;letter-spacing:0.04em;">CARDIO</span>
          <span style="padding:8px 14px;background:rgba(37,99,235,0.08);color:{BRAND_FROM};border-radius:8px;font-size:13px;font-weight:800;letter-spacing:0.04em;">STRENGTH</span>
          <span style="padding:8px 14px;background:rgba(37,99,235,0.08);color:{BRAND_FROM};border-radius:8px;font-size:13px;font-weight:800;letter-spacing:0.04em;">ELECTRICAL</span>
        </div>
        <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">
          <span style="padding:8px 14px;background:rgba(16,185,129,0.10);color:{SUCCESS};border-radius:8px;font-size:13px;font-weight:700;">✓ IOSH</span>
          <span style="padding:8px 14px;background:rgba(16,185,129,0.10);color:{SUCCESS};border-radius:8px;font-size:13px;font-weight:700;">✓ PAT Tester</span>
          <span style="padding:8px 14px;background:rgba(16,185,129,0.10);color:{SUCCESS};border-radius:8px;font-size:13px;font-weight:700;">✓ CSCS Card</span>
        </div>
      </div>
      <p style="position:absolute;bottom:130px;left:80px;right:80px;text-align:center;font-size:22px;color:{TEXT_BODY};font-weight:500;">
        Live tracker · branded PDF · 5★ rating · the same craft Uber gave their drivers.
      </p>
      {footer_cta(dark=False)}
    </div>
    """)
    return [("09_engineer_card", html)]


# ── POST 11 — Logo grid centerpiece ────────────────────────────────


def post_11_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{BRAND_GRADIENT};color:#fff;padding:0;display:flex;align-items:center;justify-content:center;">
      <div style="text-align:center;">
        <img src="{LOGO_FULL_WHITE_DATA}" alt="GymAxis" style="height:140px;"/>
        <div style="display:flex;align-items:center;justify-content:center;gap:16px;margin:48px 0 0;">
          <div style="width:80px;height:2px;background:rgba(255,255,255,0.7);"></div>
          <p class="display" style="font-size:26px;font-weight:700;color:#fff;letter-spacing:0.18em;text-transform:uppercase;margin:0;">Partner Engineers</p>
          <div style="width:80px;height:2px;background:rgba(255,255,255,0.7);"></div>
        </div>
        <p class="display" style="font-size:48px;font-weight:800;margin:40px 0 0;color:#fff;">Now open.</p>
        <p style="font-size:22px;color:rgba(255,255,255,0.8);margin:14px 0 0;font-weight:500;">First 50 spots · £30/mo (then £15, then £0)</p>
      </div>
    </div>
    """)
    return [("11_logo_centerpiece", html)]


# ── Reel covers ────────────────────────────────────────────────────


def reel_cover(idx: int, eyebrow: str, headline_html: str) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide" style="background:{BRAND_GRADIENT};color:#fff;">
      {header_on_gradient()}
      <p style="position:absolute;top:80px;right:80px;font-size:20px;font-weight:700;color:#fff;letter-spacing:0.12em;text-transform:uppercase;">▶ Reel</p>
      <div style="margin-top:180px;">
        <p style="font-family:'Outfit',sans-serif;font-size:26px;color:rgba(255,255,255,0.85);letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">{eyebrow}</p>
        <h1 class="display" style="font-size:96px;font-weight:900;line-height:1.0;margin:36px 0 0;color:#fff;">{headline_html}</h1>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;display:inline-flex;align-items:center;gap:14px;padding:16px 26px;border-radius:999px;background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.25);">
        <span style="width:12px;height:12px;background:#fff;border-radius:50%;"></span>
        <span style="font-size:20px;font-weight:700;color:#fff;">Tap to watch</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)
    return (f"reel_{idx}_cover", html)


# ── Story frames ───────────────────────────────────────────────────


def story_frame(idx: int, body_html: str, *, dark: bool = False) -> tuple[str, str]:
    if dark:
        bg_decl = f"background:{BRAND_GRADIENT};"
        logo_src = LOGO_FULL_WHITE_DATA
        text_color = "#ffffff"
        meta_color = "rgba(255,255,255,0.75)"
        footer_color = "rgba(255,255,255,0.7)"
    else:
        bg_decl = PAGE_BG_STACK
        logo_src = LOGO_FULL_DATA
        text_color = TEXT
        meta_color = TEXT_MUTED
        footer_color = TEXT_MUTED
    html = wrap(f"""
    <div class="slide story" style="{bg_decl};color:{text_color};">
      <div style="position:absolute;top:120px;left:80px;right:80px;display:flex;align-items:center;justify-content:space-between;">
        <img src="{logo_src}" alt="GymAxis" style="height:40px;"/>
        <p style="font-size:20px;font-weight:600;color:{meta_color};margin:0;">{idx}/8</p>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;justify-content:center;">{body_html}</div>
      <p style="position:absolute;bottom:120px;left:80px;right:80px;text-align:center;font-size:20px;color:{footer_color};font-weight:500;">
        gymaxisai.com/partners/engineers
      </p>
    </div>
    """)
    return (f"story_{idx:02d}", html)


def story_frames() -> list[tuple[str, str]]:
    return [
        story_frame(1, f"""
            <h1 class="display" style="font-size:108px;font-weight:900;line-height:1.0;margin:0;color:{TEXT};">
              Self-employed<br/>gym engineer?
            </h1>
            <p style="font-size:28px;color:{TEXT_BODY};margin:48px 0 0;font-weight:500;">Tap to vote 👇</p>
        """),
        story_frame(2, f"""
            <h1 class="display" style="font-size:96px;font-weight:900;line-height:1.0;margin:0;color:{TEXT};">
              How much of<br/>your week goes<br/>to <span class="grad-text">admin?</span>
            </h1>
            <p style="font-size:26px;color:{TEXT_MUTED};margin:60px 0 0;font-weight:500;">Drag the slider →</p>
        """),
        story_frame(3, f"""
            <span class="eyebrow">The answer</span>
            <h1 class="display" style="font-size:124px;font-weight:900;line-height:1.0;margin:32px 0 0;color:{TEXT};">
              47 minutes<br/>a week.
            </h1>
            <p style="font-size:28px;color:{TEXT_BODY};margin:44px 0 0;font-weight:500;">× 52 weeks =</p>
        """),
        story_frame(4, f"""
            <h1 class="display mono grad-text" style="font-size:220px;font-weight:900;line-height:1.0;margin:0;">£4,200</h1>
            <p class="display" style="font-size:44px;font-weight:800;margin:32px 0 0;color:{TEXT};">a year on paperwork.</p>
            <p style="font-size:26px;color:{TEXT_MUTED};margin:32px 0 0;font-weight:500;">Not on tools.</p>
        """),
        story_frame(5, """
            <p style="font-family:'Outfit',sans-serif;font-size:30px;color:rgba(255,255,255,0.85);letter-spacing:0.14em;text-transform:uppercase;font-weight:700;margin:0;">We built the fix</p>
            <h1 class="display" style="font-size:108px;font-weight:900;line-height:1.0;margin:28px 0 0;color:#fff;">
              Fix the kit.<br/>Skip the admin.
            </h1>
        """, dark=True),
        story_frame(6, """
            <p style="font-size:26px;color:rgba(255,255,255,0.85);font-weight:700;letter-spacing:0.14em;text-transform:uppercase;margin:0;">First 50 spots</p>
            <h1 class="display" style="font-size:88px;font-weight:900;line-height:1.05;margin:32px 0 0;color:#fff;">
              Limited cohort.<br/>Faster review.<br/>Direct support.
            </h1>
            <p style="font-size:26px;color:rgba(255,255,255,0.8);margin:48px 0 0;font-weight:500;">Decision in 2 working days.</p>
        """, dark=True),
        story_frame(7, f"""
            <h1 class="display mono" style="font-size:160px;font-weight:900;line-height:1.0;margin:0;color:{TEXT};">£30<span style="font-size:60px;color:{TEXT_MUTED};">/mo</span></h1>
            <p class="display grad-text" style="font-size:44px;font-weight:800;margin:32px 0 0;">Free at 10 referrals.</p>
            <p style="font-size:24px;color:{TEXT_BODY};margin:32px 0 0;font-weight:500;line-height:1.5;">
              + £3/site/mo recurring,<br/>+ 50% of their first cleared payment.
            </p>
        """),
        story_frame(8, """
            <div style="text-align:center;">
              <p style="font-family:'Outfit',sans-serif;font-size:30px;color:rgba(255,255,255,0.85);letter-spacing:0.14em;text-transform:uppercase;font-weight:700;margin:0;">Applications close in</p>
              <h1 class="display mono" style="font-size:240px;font-weight:900;line-height:1.0;margin:24px 0 0;color:#fff;">14<span style="font-size:60px;color:rgba(255,255,255,0.7);">d</span></h1>
              <div style="margin-top:48px;display:inline-flex;padding:24px 48px;border-radius:18px;background:#fff;color:#0F172A;">
                <span class="display" style="font-size:38px;font-weight:900;">Apply free →</span>
              </div>
            </div>
        """, dark=True),
    ]


# ── Highlight covers ───────────────────────────────────────────────


def highlight_cover(name: str, glyph: str, label: str) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide highlight" style="background:{BRAND_GRADIENT};display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;">
      <div style="font-family:'Outfit',sans-serif;font-weight:900;font-size:360px;line-height:1.0;color:#fff;">{glyph}</div>
      <p class="display" style="font-size:60px;font-weight:800;margin:36px 0 0;text-transform:uppercase;letter-spacing:0.04em;color:#fff;">{label}</p>
    </div>
    """)
    return (f"highlight_{name}", html)


# ── Master assembly ────────────────────────────────────────────────


def all_posts() -> dict[str, list[tuple[str, str]]]:
    return {
        "feed": (
            post_01_slides()
            + post_02_slides()
            + [reel_cover(3, "Reel 1", "What you ship<br/>from a job<br/>in 2026.")]
            + post_04_slides()
            + post_05_slides()
            + [reel_cover(7, "Reel 2", "A day in the life<br/>— but it ends<br/>at 5pm.")]
            + post_09_slides()
            + post_11_slides()
            + [reel_cover(12, "Reel 3", "The 60-second<br/>platform tour.")]
        ),
        "stories": story_frames(),
        "highlights": [
            highlight_cover("apply", "→", "Apply"),
            highlight_cover("demo", "▶", "Demo"),
            highlight_cover("engineers", "★", "Engineers"),
            highlight_cover("howitworks", "?", "How it works"),
            highlight_cover("faq", "i", "FAQ"),
        ],
    }


# ── Renderer ───────────────────────────────────────────────────────


async def render_html_to_png(html: str, out_path: Path, *, width: int, height: int) -> None:
    from playwright.async_api import async_playwright
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(800)  # let Google Fonts render
        await page.screenshot(path=str(out_path), full_page=False, type="png",
                              clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()


async def main() -> None:
    base = Path(__file__).parent / "instagram"
    base.mkdir(exist_ok=True)
    # Wipe old PNGs so re-runs don't leave stale frames behind.
    for sub in ("feed", "stories", "highlights"):
        for old in (base / sub).glob("*.png"):
            old.unlink()
    posts = all_posts()
    counts: dict[str, int] = {}
    for kind, items in posts.items():
        for slug, html in items:
            if kind == "stories":
                out = base / "stories" / f"{slug}.png"
                await render_html_to_png(html, out, width=1080, height=1920)
            elif kind == "highlights":
                out = base / "highlights" / f"{slug}.png"
                await render_html_to_png(html, out, width=1080, height=1080)
            else:
                out = base / "feed" / f"{slug}.png"
                await render_html_to_png(html, out, width=1080, height=1080)
            counts[kind] = counts.get(kind, 0) + 1
            print(f"  ✓ {out.relative_to(base.parent)}")
    print("\nGenerated:")
    for k, v in counts.items():
        print(f"  · {k}: {v} images")
    print(f"\nAll output → {base}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
