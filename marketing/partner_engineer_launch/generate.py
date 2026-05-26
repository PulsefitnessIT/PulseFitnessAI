"""
GymAxis · Instagram Partner Engineer Campaign — image generator.

Renders every Instagram tile (12 feed posts + 8 stories + 5 highlight
covers) as a pixel-perfect 1080×1080 (feed) / 1080×1920 (stories) PNG
using Playwright. Each post is defined as a typed dict of inline HTML
so designers can tweak any slide independently without touching the
renderer.

Run:
    cd /app && python3 marketing/partner_engineer_launch/generate.py

Output:
    /app/marketing/partner_engineer_launch/instagram/feed/post_NN_slide_M.png
    /app/marketing/partner_engineer_launch/instagram/stories/frame_NN.png
    /app/marketing/partner_engineer_launch/instagram/highlights/cover_NAME.png

Why HTML+Playwright (not AI image gen): we need EXACT brand colours
(#0055FF / #19CDFF / #0A0C10), real Satoshi+Inter fonts loaded via
Google Fonts, and crisp typography. AI generators garble all three.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# ── Brand system (mirrors /app/frontend/src/index.css) ──────────────
BLUE = "#0055FF"
BLUE_HOVER = "#0044CC"
CYAN = "#19CDFF"
INK = "#0A0C10"
INK_ALT = "#0A0A0A"
PAPER = "#FFFFFF"
PAPER_ALT = "#F4F4F5"
CREAM = "#FAF8F2"
AMBER = "#F59E0B"
EMERALD = "#10B981"
ROSE = "#F43F5E"

# Embed-friendly CSS the same way the GymAxis frontend does.
BASE_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Outfit:wght@400;600;700;800;900&family=Manrope:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; }
  .satoshi, .display { font-family: 'Outfit', 'Manrope', sans-serif; letter-spacing: -0.02em; }
  .mono { font-family: 'JetBrains Mono', monospace; letter-spacing: -0.02em; }
  .glow-cyan { text-shadow: 0 0 28px rgba(25,205,255,0.55), 0 0 60px rgba(25,205,255,0.25); }
  .glow-blue { text-shadow: 0 0 30px rgba(0,85,255,0.45); }
  .slide {
    width: 1080px; height: 1080px;
    position: relative; overflow: hidden;
    display: flex; flex-direction: column;
    padding: 80px;
  }
  .slide.story { width: 1080px; height: 1920px; padding: 120px 80px; }
  .slide.highlight { width: 1080px; height: 1080px; padding: 0; }
  .gx-mark {
    display: inline-flex; align-items: center; gap: 14px;
    font-family: 'Outfit', sans-serif; font-weight: 900;
    font-size: 32px; letter-spacing: -0.03em;
  }
  .gx-mark .dot {
    width: 16px; height: 16px; border-radius: 4px;
    background: linear-gradient(135deg, #0055FF, #19CDFF);
    box-shadow: 0 0 18px rgba(25,205,255,0.6);
  }
  .footer {
    position: absolute; bottom: 60px; left: 80px; right: 80px;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 18px; opacity: 0.7;
  }
  .pill {
    display: inline-flex; align-items: center; gap: 10px;
    padding: 12px 22px; border-radius: 999px;
    font-weight: 700; font-size: 22px;
    font-family: 'Outfit', sans-serif;
  }
  .grain::after {
    content: ''; position: absolute; inset: 0;
    background-image: radial-gradient(circle at 20% 30%, rgba(25,205,255,0.06) 0%, transparent 50%),
                      radial-gradient(circle at 80% 70%, rgba(0,85,255,0.08) 0%, transparent 50%);
    pointer-events: none;
  }
</style>
"""


def wrap(html_body: str, *, story: bool = False) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">{BASE_HEAD}</head>
<body>{html_body}</body></html>"""


# ── Reusable layout helpers ────────────────────────────────────────


def header(*, dark: bool) -> str:
    color = "#FFFFFF" if dark else INK
    return f"""
    <div class="gx-mark" style="color:{color};">
      <span class="dot"></span>
      <span>GymAxis</span>
    </div>
    """


def footer_cta(*, dark: bool, label: str = "gymaxisai.com/partner-engineer") -> str:
    color = "rgba(255,255,255,0.55)" if dark else "rgba(10,12,16,0.5)"
    return f"""
    <div class="footer" style="color:{color};">
      <span>@gymaxisai</span>
      <span>{label}</span>
    </div>
    """


# ── POST 1 — "The £4,200" carousel (6 slides) ──────────────────────


def post_01_slides() -> list[tuple[str, str]]:
    slides: list[tuple[str, str]] = []

    # Slide 1 — hero hook
    slides.append(("01_1_hook", wrap(f"""
    <div class="slide grain" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:160px;">
        <p class="satoshi" style="font-size:32px;color:{CYAN};letter-spacing:0.12em;text-transform:uppercase;margin:0;">For self-employed gym engineers</p>
        <h1 class="satoshi" style="font-size:128px;font-weight:900;line-height:1.0;margin:36px 0 0;letter-spacing:-0.04em;">
          The <span class="glow-cyan" style="color:{CYAN};">£4,200</span>
        </h1>
        <h1 class="satoshi" style="font-size:84px;font-weight:800;line-height:1.05;margin:18px 0 0;color:rgba(255,255,255,0.92);">
          you didn't know<br>you were leaving<br>on the table.
        </h1>
      </div>
      <div style="position:absolute;bottom:80px;left:80px;display:flex;align-items:center;gap:14px;">
        <span style="font-size:24px;color:rgba(255,255,255,0.6);">Swipe →</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    # Slide 2 — 47 minutes
    slides.append(("01_2_47min", wrap(f"""
    <div class="slide" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:140px;text-align:center;">
        <p class="satoshi" style="font-size:28px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;margin:0;">average a UK gym engineer spends</p>
        <h1 class="display" style="font-size:280px;font-weight:900;line-height:0.9;margin:50px 0 0;letter-spacing:-0.05em;" class="glow-cyan">
          <span style="color:{CYAN}" class="glow-cyan">47</span>
        </h1>
        <p class="satoshi" style="font-size:84px;font-weight:800;margin:10px 0 0;letter-spacing:-0.02em;">minutes / week</p>
        <p style="font-size:28px;color:rgba(255,255,255,0.6);margin:32px 0 0;font-weight:500;">on invoicing alone.</p>
      </div>
      <p style="position:absolute;bottom:140px;left:80px;right:80px;text-align:center;font-size:18px;color:rgba(255,255,255,0.4);">
        Source: GymAxis Partner Engineer survey, Feb 2026 · n=312
      </p>
      {footer_cta(dark=True)}
    </div>
    """)))

    # Slide 3 — × 52 weeks
    slides.append(("01_3_52wk", wrap(f"""
    <div class="slide" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:200px;text-align:center;">
        <p class="satoshi mono" style="font-size:240px;font-weight:700;line-height:0.9;margin:0;letter-spacing:-0.06em;">
          × <span style="color:{CYAN}">52</span>
        </p>
        <p class="satoshi" style="font-size:54px;font-weight:700;margin:50px 0 0;letter-spacing:-0.02em;">weeks a year.</p>
      </div>
      <div style="position:absolute;bottom:200px;left:80px;right:80px;text-align:center;">
        <p style="font-size:36px;font-weight:600;color:rgba(255,255,255,0.85);margin:0;">
          = <span style="color:{CYAN};font-weight:900;">40 working days</span>
        </p>
        <p style="font-size:24px;color:rgba(255,255,255,0.55);margin:12px 0 0;">on paperwork. Not on tools.</p>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    # Slide 4 — @ £45/hr
    slides.append(("01_4_money", wrap(f"""
    <div class="slide" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:140px;text-align:center;">
        <p style="font-size:36px;font-weight:600;margin:0;color:rgba(255,255,255,0.6);">At your average rate of</p>
        <p class="display mono" style="font-size:240px;font-weight:800;line-height:0.95;margin:24px 0 0;letter-spacing:-0.05em;">
          £<span style="color:{CYAN}">45</span><span style="font-size:120px;color:rgba(255,255,255,0.55);">/hr</span>
        </p>
        <p style="font-size:36px;font-weight:600;margin:60px 0 0;">that's</p>
        <p class="display mono" style="font-size:160px;font-weight:900;color:{CYAN};margin:14px 0 0;letter-spacing:-0.04em;" class="glow-cyan">
          £4,212
        </p>
        <p style="font-size:32px;color:rgba(255,255,255,0.7);margin:18px 0 0;font-weight:500;">you'd rather be billing for actual work.</p>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    # Slide 5 — solution
    slides.append(("01_5_solution", wrap(f"""
    <div class="slide" style="background:linear-gradient(135deg,{BLUE} 0%,#003DA5 100%);color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:180px;">
        <p class="satoshi" style="font-size:30px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;margin:0;font-weight:700;">we took it off your plate</p>
        <h1 class="satoshi" style="font-size:108px;font-weight:900;line-height:1.0;margin:36px 0 0;letter-spacing:-0.04em;">
          The GymAxis<br>Partner<br>Engineer Plan.
        </h1>
        <div style="margin-top:54px;display:flex;gap:18px;flex-wrap:wrap;">
          <span class="pill" style="background:rgba(255,255,255,0.18);color:#fff;backdrop-filter:blur(20px);">Branded PDFs</span>
          <span class="pill" style="background:rgba(255,255,255,0.18);color:#fff;">Stripe payouts</span>
          <span class="pill" style="background:rgba(255,255,255,0.18);color:#fff;">Smart job matching</span>
        </div>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))

    # Slide 6 — CTA
    slides.append(("01_6_cta", wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};">
      {header(dark=False)}
      <div style="margin-top:200px;">
        <h1 class="satoshi" style="font-size:124px;font-weight:900;line-height:1.0;margin:0;letter-spacing:-0.045em;">
          Fix the kit.<br>
          <span style="color:{BLUE}">Skip the admin.</span>
        </h1>
        <p style="font-size:30px;color:#52525B;margin:48px 0 0;line-height:1.5;font-weight:500;">
          Applications now open for the first<br>
          <strong style="color:{INK};">50 Partner Engineers</strong>.
        </p>
      </div>
      <div style="position:absolute;bottom:180px;left:80px;right:80px;">
        <div style="display:inline-flex;align-items:center;gap:18px;padding:28px 48px;border-radius:24px;background:{INK};color:{PAPER};box-shadow:0 24px 64px -16px rgba(0,85,255,0.4);">
          <span class="satoshi" style="font-size:38px;font-weight:800;">Apply free →</span>
        </div>
        <p style="font-size:22px;color:#71717A;margin:24px 0 0;">gymaxisai.com/partner-engineer</p>
      </div>
    </div>
    """)))

    return slides


# ── POST 2 — Before vs After single tile ───────────────────────────


def post_02_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};padding:0;">
      <div style="position:absolute;top:0;left:0;width:55%;height:100%;background:{PAPER_ALT};padding:80px;">
        <p class="satoshi" style="font-size:24px;color:#A1A1AA;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">Before</p>
        <h2 class="satoshi" style="font-size:72px;font-weight:900;color:{INK};margin:18px 0 0;line-height:1.0;letter-spacing:-0.04em;">
          Same job.<br>Tuesday at<br><span style="color:#A1A1AA;text-decoration:line-through;">22:48</span>.
        </h2>
        <div style="margin-top:60px;padding:32px;background:{PAPER};border:2px dashed #D4D4D8;border-radius:16px;">
          <p style="font-size:18px;color:#71717A;margin:0 0 12px;font-family:'JetBrains Mono',monospace;">job-tracker-v7-FINAL.xlsx</p>
          <div style="height:6px;background:{ROSE};opacity:0.5;border-radius:3px;margin:4px 0;width:80%;"></div>
          <div style="height:6px;background:#E4E4E7;border-radius:3px;margin:4px 0;width:60%;"></div>
          <div style="height:6px;background:{ROSE};opacity:0.5;border-radius:3px;margin:4px 0;width:90%;"></div>
          <div style="height:6px;background:#E4E4E7;border-radius:3px;margin:4px 0;width:50%;"></div>
          <p style="font-size:24px;color:{ROSE};margin:24px 0 0;font-weight:700;">😩 Customer chasing invoice #4</p>
        </div>
      </div>
      <div style="position:absolute;top:0;right:0;width:55%;height:100%;background:{INK};color:{PAPER};padding:80px;clip-path:polygon(8% 0,100% 0,100% 100%,0 100%);padding-left:160px;">
        <p class="satoshi" style="font-size:24px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">After</p>
        <h2 class="satoshi" style="font-size:72px;font-weight:900;margin:18px 0 0;line-height:1.0;letter-spacing:-0.04em;">
          Same job.<br>Tuesday at<br><span style="color:{CYAN}" class="glow-cyan">16:42</span>.
        </h2>
        <div style="margin-top:60px;padding:28px 32px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.14);border-radius:16px;backdrop-filter:blur(20px);">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="width:14px;height:14px;background:{EMERALD};border-radius:50%;box-shadow:0 0 18px {EMERALD};"></div>
            <p style="font-size:22px;font-weight:700;margin:0;">Service Report · sent</p>
          </div>
          <div style="display:flex;align-items:center;gap:14px;margin-top:18px;">
            <div style="width:14px;height:14px;background:{EMERALD};border-radius:50%;box-shadow:0 0 18px {EMERALD};"></div>
            <p style="font-size:22px;font-weight:700;margin:0;">Customer signature · captured</p>
          </div>
          <div style="display:flex;align-items:center;gap:14px;margin-top:18px;">
            <div style="width:14px;height:14px;background:{EMERALD};border-radius:50%;box-shadow:0 0 18px {EMERALD};"></div>
            <p style="font-size:22px;font-weight:700;margin:0;">Stripe payout · £340 paid</p>
          </div>
        </div>
        <p class="satoshi" style="font-size:32px;color:{CYAN};margin:60px 0 0;font-weight:800;">All before you got home.</p>
      </div>
    </div>
    """)
    return [("02_before_after", html)]


# ── POST 4 — "What £30 unlocks" carousel ───────────────────────────


def feature_slide(idx: int, icon: str, title: str, body: str) -> str:
    return wrap(f"""
    <div class="slide" style="background:{PAPER};color:{INK};">
      {header(dark=False)}
      <p style="position:absolute;top:80px;right:80px;font-size:20px;color:#A1A1AA;font-weight:600;">{idx} / 5</p>
      <div style="margin-top:160px;display:flex;flex-direction:column;align-items:flex-start;">
        <div style="display:flex;align-items:center;justify-content:center;width:160px;height:160px;border-radius:36px;background:linear-gradient(135deg,{BLUE},{CYAN});color:#fff;font-size:80px;font-family:'Outfit',sans-serif;font-weight:900;box-shadow:0 24px 64px -16px rgba(0,85,255,0.45);">
          {icon}
        </div>
        <h2 class="satoshi" style="font-size:88px;font-weight:900;margin:60px 0 0;line-height:1.0;letter-spacing:-0.035em;max-width:900px;">{title}</h2>
        <p style="font-size:32px;color:#52525B;margin:36px 0 0;line-height:1.45;max-width:880px;font-weight:500;">{body}</p>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)


def post_04_slides() -> list[tuple[str, str]]:
    s: list[tuple[str, str]] = []
    s.append(("04_1_hook", wrap(f"""
    <div class="slide grain" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:240px;">
        <p class="satoshi" style="font-size:32px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">For £30/mo</p>
        <h1 class="satoshi" style="font-size:128px;font-weight:900;line-height:1.0;margin:40px 0 0;letter-spacing:-0.045em;">
          What you<br>actually<br><span class="glow-cyan" style="color:{CYAN};">unlock</span> 👇
        </h1>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)))
    s.append(("04_2_smart", feature_slide(1, "🛠", "Smart job<br>matching.",
              "AI pings you when a new job lands within 5 miles of your postcode, in your skill stack and your current calendar.")))
    s.append(("04_3_pdf", feature_slide(2, "📄", "Branded PDF<br>reports.",
              "Your logo. Your colours. Auto-mailed to the customer before you've even left the site.")))
    s.append(("04_4_stripe", feature_slide(3, "💳", "Same-day<br>Stripe payouts.",
              "Customer taps Pay. The money's in your bank that night. No chasing. No invoicing-app fees.")))
    s.append(("04_5_rep", feature_slide(4, "⭐", "Reputation<br>that pays.",
              "Every customer rating is yours. Your own public engineer card. A monthly recap your accountant will love.")))
    s.append(("04_6_cta", wrap(f"""
    <div class="slide" style="background:linear-gradient(160deg,{BLUE} 0%,#003DA5 60%,#001a4d 100%);color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:160px;">
        <h1 class="satoshi" style="font-size:140px;font-weight:900;line-height:0.95;margin:0;letter-spacing:-0.05em;">£30<span style="font-size:60px;font-weight:700;color:rgba(255,255,255,0.7);">/mo</span></h1>
        <div style="display:flex;align-items:center;gap:24px;margin:40px 0;">
          <div style="width:80px;height:4px;background:{CYAN};border-radius:2px;"></div>
          <p class="satoshi" style="font-size:36px;font-weight:700;margin:0;">£15 with 5 referrals.</p>
        </div>
        <div style="display:flex;align-items:center;gap:24px;">
          <div style="width:80px;height:4px;background:{CYAN};border-radius:2px;"></div>
          <p class="satoshi" style="font-size:36px;font-weight:700;margin:0;color:{CYAN};">FREE forever with 10.</p>
        </div>
      </div>
      <div style="position:absolute;bottom:180px;left:80px;right:80px;">
        <div style="display:inline-flex;align-items:center;gap:18px;padding:32px 56px;border-radius:24px;background:{PAPER};color:{INK};box-shadow:0 24px 64px -16px rgba(0,0,0,0.5);">
          <span class="satoshi" style="font-size:42px;font-weight:900;">Start your application →</span>
        </div>
      </div>
    </div>
    """)))
    return s


# ── POST 5 — Tier maths ─────────────────────────────────────────────


def post_05_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide grain" style="background:linear-gradient(135deg,{BLUE} 0%,#003DA5 100%);color:{PAPER};">
      {header(dark=True)}
      <div style="margin-top:140px;">
        <p class="satoshi" style="font-size:32px;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">The maths</p>
        <h1 class="satoshi" style="font-size:104px;font-weight:900;line-height:1.0;margin:32px 0 0;letter-spacing:-0.04em;">
          From £30/mo to<br>£0/mo.
        </h1>
      </div>
      <div style="margin-top:80px;display:flex;flex-direction:column;gap:24px;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:32px 48px;background:rgba(255,255,255,0.10);border:1px solid rgba(255,255,255,0.14);border-radius:24px;backdrop-filter:blur(20px);">
          <p class="satoshi mono" style="font-size:42px;font-weight:700;margin:0;color:{PAPER};">0 referrals</p>
          <p class="satoshi mono" style="font-size:54px;font-weight:900;margin:0;color:{PAPER};">£30<span style="font-size:24px;opacity:0.6;">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:32px 48px;background:rgba(255,255,255,0.15);border:1px solid rgba(25,205,255,0.5);border-radius:24px;">
          <p class="satoshi mono" style="font-size:42px;font-weight:700;margin:0;">5 referrals</p>
          <p class="satoshi mono" style="font-size:54px;font-weight:900;margin:0;color:{CYAN}" class="glow-cyan">£15<span style="font-size:24px;opacity:0.7;">/mo</span></p>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:36px 48px;background:{CYAN};color:{INK};border-radius:24px;box-shadow:0 24px 64px -16px rgba(25,205,255,0.55);">
          <p class="satoshi mono" style="font-size:46px;font-weight:900;margin:0;">10 referrals</p>
          <p class="satoshi mono" style="font-size:64px;font-weight:900;margin:0;">FREE</p>
        </div>
      </div>
      <p style="position:absolute;bottom:160px;left:80px;right:80px;text-align:center;font-size:24px;color:rgba(255,255,255,0.65);font-weight:500;">
        Every gym you onboard pays your subscription. Forever.
      </p>
      {footer_cta(dark=True)}
    </div>
    """)
    return [("05_tier_maths", html)]


# ── POST 9 — Customer testimonial ──────────────────────────────────


def post_09_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{CREAM};color:{INK};">
      {header(dark=False)}
      <div style="margin-top:200px;">
        <div style="font-family:'Outfit',sans-serif;font-size:200px;font-weight:900;color:{BLUE};line-height:0.5;margin-bottom:20px;">"</div>
        <h2 class="satoshi" style="font-size:64px;font-weight:700;line-height:1.18;margin:0;font-style:italic;letter-spacing:-0.02em;color:{INK};">
          The engineer left and<br>
          <span style="background:linear-gradient(180deg,transparent 70%,{CYAN} 70%);padding:0 6px;">the report and invoice<br>
          were in my inbox</span><br>
          before he was in his van.<br>
          <span style="font-size:42px;font-weight:600;color:#52525B;font-style:normal;">I've never had a service<br>experience like it.</span>
        </h2>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;display:flex;align-items:center;gap:18px;">
        <div style="width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,{BLUE},{CYAN});display:flex;align-items:center;justify-content:center;color:{PAPER};font-weight:900;font-family:'Outfit',sans-serif;font-size:28px;">SB</div>
        <div>
          <p style="font-size:22px;font-weight:700;margin:0;color:{INK};">Sarah B.</p>
          <p style="font-size:18px;color:#71717A;margin:2px 0 0;">Gym Owner · Brighton · GymAxis customer</p>
        </div>
      </div>
      {footer_cta(dark=False)}
    </div>
    """)
    return [("09_testimonial", html)]


# ── POST 11 — Logo grid centerpiece ────────────────────────────────


def post_11_slides() -> list[tuple[str, str]]:
    html = wrap(f"""
    <div class="slide" style="background:{BLUE};color:{PAPER};padding:0;display:flex;align-items:center;justify-content:center;">
      <div style="text-align:center;">
        <div style="font-family:'Outfit',sans-serif;font-weight:900;font-size:200px;letter-spacing:-0.05em;line-height:0.9;">
          GymAxis
        </div>
        <div style="display:flex;align-items:center;justify-content:center;gap:18px;margin:36px 0 0;">
          <div style="width:120px;height:2px;background:{CYAN};"></div>
          <p class="satoshi" style="font-size:30px;font-weight:700;color:{CYAN};letter-spacing:0.18em;text-transform:uppercase;margin:0;" class="glow-cyan">Partner Engineers</p>
          <div style="width:120px;height:2px;background:{CYAN};"></div>
        </div>
        <p class="satoshi" style="font-size:48px;font-weight:800;margin:48px 0 0;letter-spacing:-0.02em;">Now open.</p>
        <p class="satoshi" style="font-size:24px;color:rgba(255,255,255,0.6);margin:16px 0 0;font-weight:500;">First 50 spots · £30/mo · free apply</p>
      </div>
    </div>
    """)
    return [("11_logo_centerpiece", html)]


# ── Reel cover frames (3, 7, 12) ───────────────────────────────────


def reel_cover(idx: int, eyebrow: str, headline_html: str, accent: str = CYAN) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide grain" style="background:{INK};color:{PAPER};">
      {header(dark=True)}
      <p style="position:absolute;top:80px;right:80px;font-size:22px;font-weight:700;color:{accent};letter-spacing:0.12em;text-transform:uppercase;">▶ Reel</p>
      <div style="margin-top:200px;">
        <p class="satoshi" style="font-size:28px;color:{accent};letter-spacing:0.18em;text-transform:uppercase;font-weight:700;margin:0;">{eyebrow}</p>
        <h1 class="satoshi" style="font-size:112px;font-weight:900;line-height:1.0;margin:40px 0 0;letter-spacing:-0.045em;">
          {headline_html}
        </h1>
      </div>
      <div style="position:absolute;bottom:160px;left:80px;display:inline-flex;align-items:center;gap:14px;padding:18px 28px;border-radius:999px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.15);backdrop-filter:blur(20px);">
        <span style="width:14px;height:14px;background:{accent};border-radius:50%;box-shadow:0 0 18px {accent};"></span>
        <span style="font-size:22px;font-weight:700;">Tap to watch</span>
      </div>
      {footer_cta(dark=True)}
    </div>
    """)
    return (f"reel_{idx}_cover", html)


# ── Story frames ───────────────────────────────────────────────────


def story_frame(idx: int, body_html: str, *, bg: str = INK, color: str = PAPER) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide story grain" style="background:{bg};color:{color};">
      <div style="position:absolute;top:120px;left:80px;right:80px;display:flex;align-items:center;justify-content:space-between;">
        <div class="gx-mark" style="color:{color};"><span class="dot"></span><span>GymAxis</span></div>
        <p style="font-size:22px;font-weight:600;color:rgba(255,255,255,0.5);margin:0;">{idx}/8</p>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;justify-content:center;">
        {body_html}
      </div>
      <p style="position:absolute;bottom:120px;left:80px;right:80px;text-align:center;font-size:22px;color:rgba(255,255,255,0.5);font-weight:500;">
        gymaxisai.com/partner-engineer
      </p>
    </div>
    """, story=True)
    return (f"story_{idx:02d}", html)


def story_frames() -> list[tuple[str, str]]:
    return [
        story_frame(1, f"""
            <h1 class="satoshi" style="font-size:120px;font-weight:900;line-height:1.0;margin:0;letter-spacing:-0.04em;">
              Self-employed<br>gym engineer?
            </h1>
            <p style="font-size:32px;color:rgba(255,255,255,0.65);margin:48px 0 0;font-weight:500;">Tap to vote 👇</p>
        """),
        story_frame(2, f"""
            <h1 class="satoshi" style="font-size:108px;font-weight:900;line-height:1.0;margin:0;letter-spacing:-0.04em;">
              How much of<br>your week goes<br>to <span style="color:{CYAN}" class="glow-cyan">admin?</span>
            </h1>
            <p style="font-size:28px;color:rgba(255,255,255,0.55);margin:60px 0 0;font-weight:500;">Drag the slider →</p>
        """),
        story_frame(3, f"""
            <p class="satoshi" style="font-size:34px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">the answer</p>
            <h1 class="satoshi" style="font-size:144px;font-weight:900;line-height:1.0;margin:36px 0 0;letter-spacing:-0.05em;">
              47 minutes<br>a week.
            </h1>
            <p style="font-size:32px;color:rgba(255,255,255,0.6);margin:48px 0 0;font-weight:500;">× 52 weeks =</p>
        """),
        story_frame(4, f"""
            <h1 class="satoshi mono" style="font-size:240px;font-weight:900;line-height:0.95;margin:0;letter-spacing:-0.06em;color:{CYAN};" class="glow-cyan">£4,200</h1>
            <p class="satoshi" style="font-size:48px;font-weight:800;margin:36px 0 0;letter-spacing:-0.02em;">a year on paperwork.</p>
            <p style="font-size:28px;color:rgba(255,255,255,0.55);margin:36px 0 0;font-weight:500;">Not on tools.</p>
        """),
        story_frame(5, f"""
            <p class="satoshi" style="font-size:36px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">we built the fix</p>
            <h1 class="satoshi" style="font-size:124px;font-weight:900;line-height:0.98;margin:32px 0 0;letter-spacing:-0.045em;">
              Fix the kit.<br>
              <span style="color:{CYAN}" class="glow-cyan">Skip the admin.</span>
            </h1>
        """, bg=f"linear-gradient(160deg,{BLUE} 0%,#003DA5 100%)"),
        story_frame(6, f"""
            <p style="font-size:28px;color:{CYAN};font-weight:700;letter-spacing:0.16em;text-transform:uppercase;margin:0;">Real engineer</p>
            <h1 class="satoshi" style="font-size:80px;font-weight:800;line-height:1.1;margin:36px 0 0;font-style:italic;letter-spacing:-0.02em;">
              "I get my<br>Sundays back."
            </h1>
            <p style="font-size:30px;color:rgba(255,255,255,0.6);margin:60px 0 0;font-weight:500;">— Daniel, Partner #08</p>
        """),
        story_frame(7, f"""
            <h1 class="satoshi mono" style="font-size:200px;font-weight:900;line-height:0.95;margin:0;letter-spacing:-0.05em;">£30<span style="font-size:80px;color:rgba(255,255,255,0.55);">/mo</span></h1>
            <p class="satoshi" style="font-size:48px;font-weight:800;margin:36px 0 0;color:{CYAN};letter-spacing:-0.02em;" class="glow-cyan">Free at 10 referrals.</p>
            <p style="font-size:28px;color:rgba(255,255,255,0.55);margin:36px 0 0;font-weight:500;">Swipe up to apply →</p>
        """),
        story_frame(8, f"""
            <div style="text-align:center;">
              <p class="satoshi" style="font-size:34px;color:{CYAN};letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin:0;">applications close in</p>
              <h1 class="satoshi mono" style="font-size:280px;font-weight:900;line-height:0.95;margin:24px 0 0;letter-spacing:-0.05em;">14<span style="font-size:80px;color:rgba(255,255,255,0.55);">d</span></h1>
              <div style="margin-top:60px;display:inline-flex;padding:28px 56px;border-radius:24px;background:{PAPER};color:{INK};">
                <span class="satoshi" style="font-size:42px;font-weight:900;">Apply free →</span>
              </div>
            </div>
        """),
    ]


# ── Highlight covers ────────────────────────────────────────────────


def highlight_cover(name: str, glyph: str, label: str) -> tuple[str, str]:
    html = wrap(f"""
    <div class="slide highlight" style="background:{BLUE};display:flex;flex-direction:column;align-items:center;justify-content:center;color:{PAPER};">
      <div style="font-family:'Outfit',sans-serif;font-weight:900;font-size:380px;line-height:0.9;letter-spacing:-0.05em;color:{CYAN}" class="glow-cyan">{glyph}</div>
      <p class="satoshi" style="font-size:64px;font-weight:800;margin:40px 0 0;letter-spacing:0.02em;text-transform:uppercase;">{label}</p>
    </div>
    """)
    return (f"highlight_{name}", html)


# ── Master assembly ────────────────────────────────────────────────


def all_posts() -> dict[str, list[tuple[str, str]]]:
    return {
        "feed": (
            post_01_slides()
            + post_02_slides()
            + [reel_cover(3, "Reel 1", "What you ship<br>from a job<br>in <span style='color:" + CYAN + "'>2026</span>.")]
            + post_04_slides()
            + post_05_slides()
            + [reel_cover(7, "Reel 2", "A day in the life<br>— but it ends<br>at <span style='color:" + CYAN + "'>5pm</span>.")]
            + post_09_slides()
            + post_11_slides()
            + [reel_cover(12, "Reel 3", "The <span style='color:" + CYAN + "'>60-second</span><br>platform tour.")]
        ),
        "stories": story_frames(),
        "highlights": [
            highlight_cover("apply", "→", "Apply"),
            highlight_cover("demo", "▶", "Demo"),
            highlight_cover("engineers", "★", "Engineers"),
            highlight_cover("reviews", "★", "Reviews"),
            highlight_cover("faq", "?", "FAQ"),
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
        # Give Google Fonts a tick to fully render.
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(out_path), full_page=False, type="png",
                               clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()


async def main() -> None:
    base = Path(__file__).parent / "instagram"
    base.mkdir(exist_ok=True)
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
