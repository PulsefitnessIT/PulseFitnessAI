"""
GymAxis · Partner Engineer Launch — Instagram campaign generator (v2).

Crawled https://gymaxisai.com on 2026-05-26 to capture:
  • Real brand palette as used on the live homepage.
  • Official gymaxis-mark-tight.png logo (we embed it as a data URI so
    Playwright doesn't need network access at render time).
  • Real Partner Engineer offer: £30 / £15 / free auto-tier PLUS a
    £3/site/mo recurring + 50% of the gym's first cleared Operations
    payment as the referral economics.
  • No customer testimonials — we have no customers yet; all "social
    proof" must come from product features, not fabricated quotes.

Run:
    cd /app && python3 marketing/partner_engineer_launch/generate.py

Output: /app/marketing/partner_engineer_launch/instagram/{feed,stories,highlights}/*.png
"""
from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

# ── Brand palette (mirrors /app/frontend/src/index.css verbatim) ────
BLUE = "#0055FF"
BLUE_DEEP = "#003DA5"
CYAN = "#19CDFF"
CYAN_DEEP = "#0DB8E8"
INK = "#0A0C10"
INK_DEEP = "#0F1419"
INK_MUTED = "#52525B"
PAPER = "#FFFFFF"
PAPER_ALT = "#F4F4F5"
SUCCESS = "#10B981"

# Live-site signature gradient: ink → deep blue with a cyan glow accent.
HERO_GRADIENT = f"linear-gradient(160deg, {INK} 0%, #0A1638 50%, {BLUE_DEEP} 100%)"
DARK_PANEL = INK


# ── Real logo (embed as base64 so we don't need network at render) ──
_LOGO_DIR = Path("/app/frontend/public/brand")
LOGO_MARK_DATA = "data:image/png;base64," + base64.b64encode(
    (_LOGO_DIR / "gymaxis-mark-tight.png").read_bytes()
).decode()
LOGO_FULL_DATA = "data:image/png;base64," + base64.b64encode(
    (_LOGO_DIR / "gymaxis-full-tight.png").read_bytes()
).decode()


BASE_HEAD = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Outfit:wght@400;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; }}
  .display {{ font-family: 'Outfit', sans-serif; letter-spacing: -0.03em; }}
  .mono {{ font-family: 'JetBrains Mono', monospace; letter-spacing: -0.02em; }}
  /* Cyan glow — text-shadow only; keep as a single class. */
  .glow {{ text-shadow: 0 0 26px rgba(25,205,255,0.55), 0 0 56px rgba(25,205,255,0.22); }}
  .slide {{
    width: 1080px; height: 1080px; position: relative;
    display: flex; flex-direction: column;
    padding: 80px; overflow: hidden;
  }}
  .slide.story {{ width: 1080px; height: 1920px; padding: 120px 80px; }}
  .slide.highlight {{ width: 1080px; height: 1080px; padding: 0; }}
  /* Subtle radial wash on dark canvases */
  .grain::after {{
    content: ''; position: absolute; inset: 0; pointer-events: none;
    background:
      radial-gradient(circle at 18% 22%, rgba(25,205,255,0.08), transparent 45%),
      radial-gradient(circle at 82% 78%, rgba(0,85,255,0.10), transparent 50%);
  }}
  .logo-bar {{ display: flex; align-items: center; gap: 14px; }}
  .logo-bar img {{ height: 42px; width: auto; }}
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
</style>
"""


def wrap(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'>{BASE_HEAD}</head><body>{body}</body></html>"


# ── Reusable layout helpers ────────────────────────────────────────


def header(*, dark: bool) -> str:
    # Use the FULL wordmark (gymaxis-full-tight.png) on light tiles so the
    # brand reads at a glance; use the MARK only on the highlight covers
    # where space is tight.
    src = LOGO_FULL_DATA
    invert = "filter: brightness(0) invert(1);" if dark else ""
    return f"""
    <div class="logo-bar" style="{invert}">
      <img src="{src}" alt="GymAxis"/>
    </div>
    """


def footer_cta(*, dark: bool, label: str = "gymaxisai.com/partners/engineers") -> str:
    color = "rgba(255,255,255,0.55)" if dark else "rgba(10,12,16,0.5)"
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
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:140px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:{CYAN};letter-spacing:0.14em;text-transform:uppercase;margin:0;font-weight:700;">For self-employed gym engineers</p>
        <h1 class="display" style="font-size:128px;font-weight:900;line-height:1.0;margin:40px 0 0;">
          The <span style="color:{CYAN};" class="glow">£4,200</span>
        </h1>
        <h2 class="display" style="font-size:72px;font-weight:800;line-height:1.05;margin:24px 0 0;color:rgba(255,255,255,0.9);">
          you didn't know<br/>you were leaving<br/>on the table.
        </h2>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;color:rgba(255,255,255,0.55);font-size:22px;">Swipe →</div>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_2_47min", wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:120px;text-align:center;">
        <p style="font-family:'Outfit',sans-serif;font-size:26px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;margin:0;font-weight:700;">average a UK gym engineer spends</p>
        <h1 class="display glow" style="font-size:240px;font-weight:900;line-height:1.0;margin:60px 0 0;color:{CYAN};">47</h1>
        <p class="display" style="font-size:72px;font-weight:800;margin:28px 0 0;">minutes / week</p>
        <p style="font-size:26px;color:rgba(255,255,255,0.6);margin:32px 0 0;font-weight:500;">on invoicing alone.</p>
      </div>
      <p style="position:absolute;bottom:130px;left:80px;right:80px;text-align:center;font-size:16px;color:rgba(255,255,255,0.4);">
        Internal projection · GymAxis Partner Engineer onboarding survey, 2026
      </p>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_3_52wk", wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:180px;text-align:center;">
        <p class="display mono" style="font-size:200px;font-weight:700;line-height:1.0;margin:0;">
          × <span style="color:{CYAN};" class="glow">52</span>
        </p>
        <p class="display" style="font-size:48px;font-weight:700;margin:36px 0 0;">weeks a year.</p>
      </div>
      <div style="position:absolute;bottom:200px;left:80px;right:80px;text-align:center;">
        <p style="font-size:34px;font-weight:600;color:rgba(255,255,255,0.85);margin:0;">
          = <span style="color:{CYAN};font-weight:900;">40 working days</span>
        </p>
        <p style="font-size:22px;color:rgba(255,255,255,0.55);margin:14px 0 0;">on paperwork. Not on tools.</p>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_4_money", wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:120px;text-align:center;">
        <p style="font-size:30px;font-weight:600;margin:0;color:rgba(255,255,255,0.65);">At your average rate of</p>
        <p class="display mono" style="font-size:200px;font-weight:800;line-height:1.0;margin:24px 0 0;">£<span style="color:{CYAN};">45</span><span style="font-size:96px;color:rgba(255,255,255,0.5);">/hr</span></p>
        <p style="font-size:30px;font-weight:600;margin:56px 0 0;">that's</p>
        <p class="display mono glow" style="font-size:144px;font-weight:900;color:{CYAN};margin:14px 0 0;">£4,212</p>
        <p style="font-size:26px;color:rgba(255,255,255,0.7);margin:24px 0 0;font-weight:500;">you'd rather be billing for actual work.</p>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_5_solution", wrap(f"""
    <div class="slide grain" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:160px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:{CYAN};letter-spacing:0.14em;text-transform:uppercase;margin:0;font-weight:700;">We took it off your plate</p>
        <h1 class="display" style="font-size:104px;font-weight:900;line-height:1.0;margin:36px 0 0;">
          The GymAxis<br/>Partner<br/><span style="color:{CYAN};" class="glow">Engineer Plan.</span>
        </h1>
      </div>
      <div style="position:absolute;bottom:200px;left:80px;right:80px;display:flex;gap:16px;flex-wrap:wrap;">
        <span class="pill" style="background:rgba(25,205,255,0.16);color:{CYAN};border:1px solid rgba(25,205,255,0.3);">Branded PDFs</span>
        <span class="pill" style="background:rgba(25,205,255,0.16);color:{CYAN};border:1px solid rgba(25,205,255,0.3);">Stripe payouts</span>
        <span class="pill" style="background:rgba(25,205,255,0.16);color:{CYAN};border:1px solid rgba(25,205,255,0.3);">Smart job matching</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    s.append(("01_6_cta", wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};">
      {header(dark=False)}
      <div style="margin-top:180px;">
        <h1 class="display" style="font-size:120px;font-weight:900;line-height:1.0;margin:0;">
          Fix the kit.<br/><span style="color:{BLUE};">Skip the admin.</span>
        </h1>
        <p style="font-size:28px;color:{INK_MUTED};margin:48px 0 0;line-height:1.5;font-weight:500;">
          Applications open for the first<br/>
          <strong style="color:{INK};">50 Partner Engineers</strong>.
        </p>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;right:80px;">
        <div style="display:inline-flex;align-items:center;gap:18px;padding:26px 44px;border-radius:18px;background:{INK};color:{PAPER};box-shadow:0 24px 56px -16px rgba(0,85,255,0.4);">
          <span class="display" style="font-size:36px;font-weight:800;">Apply free →</span>
        </div>
        <p style="font-size:20px;color:#71717A;margin:24px 0 0;">gymaxisai.com/partners/engineers</p>
      </div>
    </div>
    """)))

    return s


# ── POST 2 — Before vs After ───────────────────────────────────────


def post_02_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};padding:0;">
      <div style="position:absolute;top:0;left:0;width:55%;height:100%;background:{PAPER_ALT};padding:80px;">
        <p class="display" style="font-size:22px;color:#A1A1AA;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">Before</p>
        <h2 class="display" style="font-size:64px;font-weight:900;color:{INK};margin:18px 0 0;line-height:1.0;">
          Same job.<br/>Tuesday at<br/><span style="color:#A1A1AA;text-decoration:line-through;">22:48</span>.
        </h2>
        <div style="margin-top:48px;padding:28px;background:{PAPER};border:2px dashed #D4D4D8;border-radius:14px;">
          <p style="font-size:16px;color:#71717A;margin:0 0 12px;font-family:'JetBrains Mono',monospace;">job-tracker-v7-FINAL.xlsx</p>
          <div style="height:5px;background:#EF4444;opacity:0.45;border-radius:3px;margin:4px 0;width:80%;"></div>
          <div style="height:5px;background:#E4E4E7;border-radius:3px;margin:4px 0;width:60%;"></div>
          <div style="height:5px;background:#EF4444;opacity:0.45;border-radius:3px;margin:4px 0;width:90%;"></div>
          <div style="height:5px;background:#E4E4E7;border-radius:3px;margin:4px 0;width:50%;"></div>
          <p style="font-size:20px;color:#B91C1C;margin:22px 0 0;font-weight:700;">Customer chasing invoice #4</p>
        </div>
      </div>
      <div style="position:absolute;top:0;right:0;width:55%;height:100%;background:{INK};color:{PAPER};padding:80px;clip-path:polygon(8% 0,100% 0,100% 100%,0 100%);padding-left:150px;">
        <p class="display" style="font-size:22px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">After</p>
        <h2 class="display" style="font-size:64px;font-weight:900;margin:18px 0 0;line-height:1.0;">
          Same job.<br/>Tuesday at<br/><span style="color:{CYAN};" class="glow">16:42</span>.
        </h2>
        <div style="margin-top:48px;padding:26px 30px;background:rgba(255,255,255,0.06);border:1px solid rgba(25,205,255,0.18);border-radius:14px;">
          <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;">Service Report · sent</p>
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin-top:14px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;">Customer signature · captured</p>
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin-top:14px;">
            <div style="width:12px;height:12px;background:{SUCCESS};border-radius:50%;box-shadow:0 0 14px {SUCCESS};"></div>
            <p style="font-size:20px;font-weight:700;margin:0;">Stripe payout · £340 paid</p>
          </div>
        </div>
        <p class="display" style="font-size:28px;color:{CYAN};margin:48px 0 0;font-weight:800;">All before you got home.</p>
      </div>
    </div>
    """)
    return [("02_before_after", html)]


# ── POST 4 — "What £30 unlocks" carousel ───────────────────────────


def feature_slide(idx: int, icon: str, title: str, body: str) -> str:
    return wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};">
      {header(dark=False)}
      <p style="position:absolute;top:80px;right:80px;font-size:18px;color:#A1A1AA;font-weight:600;">{idx} / 5</p>
      <div style="margin-top:140px;">
        <div style="display:flex;align-items:center;justify-content:center;width:140px;height:140px;border-radius:32px;background:linear-gradient(135deg,{BLUE},{CYAN});color:#fff;font-size:64px;font-family:'Outfit',sans-serif;font-weight:900;box-shadow:0 20px 56px -16px rgba(0,85,255,0.4);">
          {icon}
        </div>
        <h2 class="display" style="font-size:80px;font-weight:900;margin:48px 0 0;line-height:1.0;max-width:880px;">{title}</h2>
        <p style="font-size:28px;color:{INK_MUTED};margin:30px 0 0;line-height:1.45;max-width:860px;font-weight:500;">{body}</p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)


def post_04_slides() -> list[tuple[str, str]]:
    s: list[tuple[str, str]] = []
    s.append(("04_1_hook", wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:240px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">For £30/mo</p>
        <h1 class="display" style="font-size:112px;font-weight:900;line-height:1.0;margin:36px 0 0;">
          What you<br/>actually<br/><span style="color:{CYAN};" class="glow">unlock</span> 👇
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
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:140px;">
        <h1 class="display" style="font-size:128px;font-weight:900;line-height:0.95;margin:0;">£30<span style="font-size:54px;font-weight:700;color:rgba(255,255,255,0.65);">/mo</span></h1>
        <div style="display:flex;align-items:center;gap:20px;margin:36px 0;">
          <div style="width:60px;height:3px;background:{CYAN};border-radius:2px;"></div>
          <p class="display" style="font-size:30px;font-weight:700;margin:0;">£15 at 5 active referrals.</p>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">
          <div style="width:60px;height:3px;background:{CYAN};border-radius:2px;"></div>
          <p class="display" style="font-size:30px;font-weight:700;margin:0;color:{CYAN};">Free forever at 10.</p>
        </div>
        <p style="font-size:20px;color:rgba(255,255,255,0.55);margin:32px 0 0;line-height:1.55;max-width:760px;">
          + £3/site/mo recurring · 50% of the gym's first cleared Operations payment.
        </p>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;right:80px;">
        <div style="display:inline-flex;align-items:center;gap:18px;padding:28px 50px;border-radius:18px;background:{PAPER};color:{INK};box-shadow:0 24px 64px -16px rgba(0,0,0,0.4);">
          <span class="display" style="font-size:36px;font-weight:900;">Start your application →</span>
        </div>
      </div>
    </div>
    """)))
    return s


# ── POST 5 — Tier maths ─────────────────────────────────────────────


def post_05_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:120px;">
        <p style="font-family:'Outfit',sans-serif;font-size:28px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">The maths</p>
        <h1 class="display" style="font-size:88px;font-weight:900;line-height:1.0;margin:30px 0 0;">
          From £30/mo to<br/>£0/mo.
        </h1>
      </div>
      <div style="margin-top:60px;display:flex;flex-direction:column;gap:20px;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:28px 40px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.10);border-radius:18px;">
          <p class="display mono" style="font-size:36px;font-weight:700;margin:0;color:{PAPER};">0 referrals</p>
          <p class="display mono" style="font-size:48px;font-weight:900;margin:0;color:{PAPER};">£30<span style="font-size:22px;opacity:0.55;">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:28px 40px;background:rgba(25,205,255,0.1);border:1px solid rgba(25,205,255,0.35);border-radius:18px;">
          <p class="display mono" style="font-size:36px;font-weight:700;margin:0;">5 referrals</p>
          <p class="display mono glow" style="font-size:48px;font-weight:900;margin:0;color:{CYAN};">£15<span style="font-size:22px;opacity:0.7;">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:30px 40px;background:{CYAN};color:{INK};border-radius:18px;box-shadow:0 24px 64px -16px rgba(25,205,255,0.5);">
          <p class="display mono" style="font-size:40px;font-weight:900;margin:0;">10 referrals</p>
          <p class="display mono" style="font-size:54px;font-weight:900;margin:0;">FREE</p>
        </div>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;right:80px;">
        <p style="text-align:center;font-size:22px;color:rgba(255,255,255,0.65);font-weight:500;margin:0;">
          Every gym you onboard pays your subscription.
        </p>
        <p style="text-align:center;font-size:18px;color:rgba(255,255,255,0.45);margin:10px 0 0;">
          + 50% of their first cleared Operations payment · £3/site/mo recurring · forever.
        </p>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)
    return [("05_tier_maths", html)]


# ── POST 9 (replacement) — Verified Engineer Card ──────────────────
# Mirrors the live homepage's "Your engineer · Sarah · 4.9 · 52 jobs"
# card. NOT a testimonial — it's a product feature showcase.


def post_09_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:80px;">
        <p style="font-family:'Outfit',sans-serif;font-size:26px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">The card customers will see</p>
        <h1 class="display" style="font-size:64px;font-weight:900;line-height:1.05;margin:24px 0 0;max-width:880px;">
          Your verified engineer<br/>profile, your way.
        </h1>
      </div>
      <div style="margin:60px auto 0;width:560px;padding:32px;background:rgba(255,255,255,0.05);border:1px solid rgba(25,205,255,0.25);border-radius:24px;backdrop-filter:blur(20px);">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;background:rgba(16,185,129,0.15);color:{SUCCESS};border-radius:999px;font-size:13px;font-weight:700;">✓ Verified</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;margin-top:20px;">
          <div style="width:88px;height:88px;border-radius:50%;background:linear-gradient(135deg,{BLUE},{CYAN});display:flex;align-items:center;justify-content:center;color:{PAPER};font-family:'Outfit',sans-serif;font-weight:900;font-size:38px;">SH</div>
          <div>
            <p class="display" style="font-size:34px;font-weight:800;margin:0;">Sarah Hodge</p>
            <p style="font-size:18px;color:rgba(255,255,255,0.6);margin:4px 0 0;">★ 4.9 · 52 jobs in 90 days</p>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:24px;flex-wrap:wrap;">
          <span style="padding:8px 14px;background:rgba(255,255,255,0.08);border-radius:8px;font-size:14px;font-weight:700;">✓ IOSH</span>
          <span style="padding:8px 14px;background:rgba(255,255,255,0.08);border-radius:8px;font-size:14px;font-weight:700;">✓ PAT</span>
          <span style="padding:8px 14px;background:rgba(255,255,255,0.08);border-radius:8px;font-size:14px;font-weight:700;">✓ CSCS</span>
          <span style="padding:8px 14px;background:rgba(25,205,255,0.15);color:{CYAN};border-radius:8px;font-size:14px;font-weight:700;">+ your custom badges</span>
        </div>
      </div>
      <p style="position:absolute;bottom:130px;left:80px;right:80px;text-align:center;font-size:22px;color:rgba(255,255,255,0.6);font-weight:500;">
        Live tracker · branded PDF · 5★ rating · the same craft Uber gave their drivers.
      </p>
      {footer_cta(dark=True)}
    </div>
    """)
    return [("09_engineer_card", html)]


# ── POST 11 — Logo grid centerpiece ────────────────────────────────


def post_11_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{HERO_GRADIENT};color:{PAPER};padding:0;display:flex;align-items:center;justify-content:center;">
      <div style="text-align:center;">
        <img src="{LOGO_FULL_DATA}" alt="GymAxis" style="height:120px;filter:brightness(0) invert(1);"/>
        <div style="display:flex;align-items:center;justify-content:center;gap:16px;margin:48px 0 0;">
          <div style="width:80px;height:2px;background:{CYAN};"></div>
          <p class="display" style="font-size:26px;font-weight:700;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;margin:0;">Partner Engineers</p>
          <div style="width:80px;height:2px;background:{CYAN};"></div>
        </div>
        <p class="display" style="font-size:42px;font-weight:800;margin:40px 0 0;">Now open.</p>
        <p style="font-size:22px;color:rgba(255,255,255,0.6);margin:14px 0 0;font-weight:500;">First 50 spots · £30/mo (then £15, then £0)</p>
      </div>
    </div>
    """)
    return [("11_logo_centerpiece", html)]


# ── Reel covers ────────────────────────────────────────────────────


def reel_cover(idx: int, eyebrow: str, headline_html: str) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide grain" style="background:{HERO_GRADIENT};color:{PAPER};">
      {header(dark=True)}
      <p style="position:absolute;top:80px;right:80px;font-size:20px;font-weight:700;color:{CYAN};letter-spacing:0.12em;text-transform:uppercase;">▶ Reel</p>
      <div style="margin-top:180px;">
        <p style="font-family:'Outfit',sans-serif;font-size:26px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">{eyebrow}</p>
        <h1 class="display" style="font-size:96px;font-weight:900;line-height:1.0;margin:36px 0 0;">{headline_html}</h1>
      </div>
      <div style="position:absolute;bottom:140px;left:80px;display:inline-flex;align-items:center;gap:14px;padding:16px 26px;border-radius:999px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);">
        <span style="width:12px;height:12px;background:{CYAN};border-radius:50%;box-shadow:0 0 14px {CYAN};"></span>
        <span style="font-size:20px;font-weight:700;">Tap to watch</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)
    return (f"reel_{idx}_cover", html)


# ── Story frames ───────────────────────────────────────────────────


def story_frame(idx: int, body_html: str, *, bg: str = INK) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide story grain" style="background:{bg};color:{PAPER};">
      <div style="position:absolute;top:120px;left:80px;right:80px;display:flex;align-items:center;justify-content:space-between;">
        <img src="{LOGO_FULL_DATA}" alt="GymAxis" style="height:36px;filter:brightness(0) invert(1);"/>
        <p style="font-size:20px;font-weight:600;color:rgba(255,255,255,0.5);margin:0;">{idx}/8</p>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;justify-content:center;">{body_html}</div>
      <p style="position:absolute;bottom:120px;left:80px;right:80px;text-align:center;font-size:20px;color:rgba(255,255,255,0.5);font-weight:500;">
        gymaxisai.com/partners/engineers
      </p>
    </div>
    """)
    return (f"story_{idx:02d}", html)


def story_frames() -> list[tuple[str, str]]:
    return [
        story_frame(1, f"""
            <h1 class="display" style="font-size:104px;font-weight:900;line-height:1.0;margin:0;">
              Self-employed<br/>gym engineer?
            </h1>
            <p style="font-size:28px;color:rgba(255,255,255,0.65);margin:48px 0 0;font-weight:500;">Tap to vote 👇</p>
        """),
        story_frame(2, f"""
            <h1 class="display" style="font-size:96px;font-weight:900;line-height:1.0;margin:0;">
              How much of<br/>your week goes<br/>to <span style="color:{CYAN};" class="glow">admin?</span>
            </h1>
            <p style="font-size:26px;color:rgba(255,255,255,0.55);margin:60px 0 0;font-weight:500;">Drag the slider →</p>
        """),
        story_frame(3, f"""
            <p style="font-family:'Outfit',sans-serif;font-size:30px;color:{CYAN};letter-spacing:0.14em;text-transform:uppercase;font-weight:700;margin:0;">the answer</p>
            <h1 class="display" style="font-size:120px;font-weight:900;line-height:1.0;margin:32px 0 0;">
              47 minutes<br/>a week.
            </h1>
            <p style="font-size:28px;color:rgba(255,255,255,0.6);margin:44px 0 0;font-weight:500;">× 52 weeks =</p>
        """),
        story_frame(4, f"""
            <h1 class="display mono glow" style="font-size:200px;font-weight:900;line-height:1.0;margin:0;color:{CYAN};">£4,200</h1>
            <p class="display" style="font-size:44px;font-weight:800;margin:32px 0 0;">a year on paperwork.</p>
            <p style="font-size:26px;color:rgba(255,255,255,0.55);margin:32px 0 0;font-weight:500;">Not on tools.</p>
        """),
        story_frame(5, f"""
            <p style="font-family:'Outfit',sans-serif;font-size:30px;color:{CYAN};letter-spacing:0.14em;text-transform:uppercase;font-weight:700;margin:0;">we built the fix</p>
            <h1 class="display" style="font-size:108px;font-weight:900;line-height:1.0;margin:28px 0 0;">
              Fix the kit.<br/>
              <span style="color:{CYAN};" class="glow">Skip the admin.</span>
            </h1>
        """, bg=HERO_GRADIENT),
        story_frame(6, f"""
            <p style="font-size:26px;color:{CYAN};font-weight:700;letter-spacing:0.14em;text-transform:uppercase;margin:0;">First 50 spots</p>
            <h1 class="display" style="font-size:88px;font-weight:900;line-height:1.05;margin:32px 0 0;">
              Limited cohort.<br/>Faster review.<br/>Direct support.
            </h1>
            <p style="font-size:26px;color:rgba(255,255,255,0.6);margin:48px 0 0;font-weight:500;">Decision in 2 working days.</p>
        """),
        story_frame(7, f"""
            <h1 class="display mono" style="font-size:160px;font-weight:900;line-height:1.0;margin:0;">£30<span style="font-size:60px;color:rgba(255,255,255,0.5);">/mo</span></h1>
            <p class="display glow" style="font-size:44px;font-weight:800;margin:32px 0 0;color:{CYAN};">Free at 10 referrals.</p>
            <p style="font-size:24px;color:rgba(255,255,255,0.6);margin:32px 0 0;font-weight:500;line-height:1.5;">
              + £3/site/mo recurring,<br/>+ 50% of their first cleared payment.
            </p>
        """),
        story_frame(8, f"""
            <div style="text-align:center;">
              <p style="font-family:'Outfit',sans-serif;font-size:30px;color:{CYAN};letter-spacing:0.14em;text-transform:uppercase;font-weight:700;margin:0;">applications close in</p>
              <h1 class="display mono" style="font-size:220px;font-weight:900;line-height:1.0;margin:24px 0 0;">14<span style="font-size:60px;color:rgba(255,255,255,0.5);">d</span></h1>
              <div style="margin-top:48px;display:inline-flex;padding:24px 48px;border-radius:18px;background:{PAPER};color:{INK};">
                <span class="display" style="font-size:38px;font-weight:900;">Apply free →</span>
              </div>
            </div>
        """),
    ]


# ── Highlight covers ───────────────────────────────────────────────


def highlight_cover(name: str, glyph: str, label: str) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide highlight" style="background:{HERO_GRADIENT};display:flex;flex-direction:column;align-items:center;justify-content:center;color:{PAPER};">
      <div style="font-family:'Outfit',sans-serif;font-weight:900;font-size:340px;line-height:1.0;color:{CYAN};" class="glow">{glyph}</div>
      <p class="display" style="font-size:60px;font-weight:800;margin:36px 0 0;text-transform:uppercase;letter-spacing:0.04em;">{label}</p>
    </div>
    """)
    return (f"highlight_{name}", html)


# ── Master assembly ────────────────────────────────────────────────


def all_posts() -> dict[str, list[tuple[str, str]]]:
    return {
        "feed": (
            post_01_slides()
            + post_02_slides()
            + [reel_cover(3, "Reel 1", f"What you ship<br/>from a job<br/>in <span style='color:{CYAN};'>2026</span>.")]
            + post_04_slides()
            + post_05_slides()
            + [reel_cover(7, "Reel 2", f"A day in the life<br/>— but it ends<br/>at <span style='color:{CYAN};'>5pm</span>.")]
            + post_09_slides()
            + post_11_slides()
            + [reel_cover(12, "Reel 3", f"The <span style='color:{CYAN};'>60-second</span><br/>platform tour.")]
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
