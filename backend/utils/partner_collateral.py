"""Iter 216h285 — Partner Engineer referral collateral kit.

Closes Gap 6 from the BA audit: engineers had a raw referral URL and
no professional way to share it. This module generates three
collateral assets per partner on demand:

* **QR poster** — A4 PNG with a large QR code + the engineer's name +
  the friendly URL. Designed for the van, the workshop, or to print
  and stick on a gym wall after a service visit.
* **Social card** — 1200×630 PNG sized for Instagram, LinkedIn, X,
  WhatsApp link-preview. Hero text + colour-block Pulse Fitness branding.
* **PDF pitch deck** — single-page A4 PDF the engineer can email to a
  gym owner. Includes the proposition, the engineer's name, their
  referral code, and a footer QR.

Everything is generated in-memory and streamed back via FastAPI. No
files persisted on disk; cache headers tell the browser to keep each
asset for an hour (long enough to share, short enough that a code
rotation reflects within the same session).
"""
from __future__ import annotations

import io
import logging
import os
from typing import Tuple

import qrcode
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Brand colours (kept in one place — match the marketing landing page).
COLOR_BRAND_BLUE = (0, 85, 255)
COLOR_INK_900    = (15, 23, 42)
COLOR_INK_700    = (51, 65, 85)
COLOR_INK_500    = (100, 116, 139)
COLOR_BG_LIGHT   = (248, 250, 252)
COLOR_ACCENT     = (16, 185, 129)  # emerald-500 — used on the pitch CTA


# ── Font helpers ────────────────────────────────────────────────────


def _font_path(weight: str = "regular") -> str | None:
    """Try a couple of well-known font paths so collateral never falls
    back to the unreadable Pillow default bitmap font. We bundle no
    fonts ourselves — we just probe a few common system paths."""
    candidates_by_weight = {
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ],
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ],
    }
    for p in candidates_by_weight.get(weight, []):
        if os.path.exists(p):
            return p
    return None


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    path = _font_path(weight)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


# ── Shared QR builder ──────────────────────────────────────────────


def _qr_image(url: str, size_px: int) -> Image.Image:
    """Crisp PNG QR with the brand-blue foreground on transparent
    background. We use ``box_size=10`` then resize down so the QR
    pixels stay sharp at any target size."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=COLOR_BRAND_BLUE, back_color="white").convert("RGB")
    return img.resize((size_px, size_px), Image.LANCZOS)


def _wrap(text: str, max_chars: int) -> list[str]:
    """Tiny wrapper for headline blocks. Splits on whitespace."""
    words = (text or "").split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


# ── 1. QR poster (A4 PNG, portrait) ─────────────────────────────────


def generate_qr_poster(full_name: str, referral_code: str, referral_url: str) -> bytes:
    """Return PNG bytes for an A4 portrait poster at 150 DPI.

    Layout (centre-aligned):
      1. "Refer a gym to Pulse Fitness" headline
      2. QR code (centre, ~50 % page width)
      3. "{full_name}" attribution + code
      4. URL printed under the QR for non-camera users
      5. Footer pitch line + small disclaimer
    """
    W, H = 1240, 1754  # A4 portrait @ 150 DPI
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # Top brand bar
    d.rectangle([0, 0, W, 32], fill=COLOR_BRAND_BLUE)

    # Headline
    headline_font = _font(72, "bold")
    title = "Refer a gym to Pulse Fitness"
    bbox = d.textbbox((0, 0), title, font=headline_font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, 130), title, fill=COLOR_INK_900, font=headline_font)

    sub_font = _font(36, "regular")
    sub = "Scan the code or visit the link below"
    bbox = d.textbbox((0, 0), sub, font=sub_font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, 240), sub, fill=COLOR_INK_500, font=sub_font)

    # QR — 60 % of width, centred
    qr_size = int(W * 0.55)
    qr = _qr_image(referral_url, qr_size)
    qr_x = (W - qr_size) // 2
    qr_y = 360
    img.paste(qr, (qr_x, qr_y))

    # Attribution
    attrib_font = _font(40, "bold")
    attrib = f"Referred by {full_name or 'a Pulse Fitness partner engineer'}"
    bbox = d.textbbox((0, 0), attrib, font=attrib_font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, qr_y + qr_size + 60), attrib, fill=COLOR_INK_900, font=attrib_font)

    # Code block
    code_font = _font(36, "regular")
    code_line = f"Code: {referral_code}"
    bbox = d.textbbox((0, 0), code_line, font=code_font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, qr_y + qr_size + 120), code_line, fill=COLOR_INK_700, font=code_font)

    # URL
    url_font = _font(28, "regular")
    bbox = d.textbbox((0, 0), referral_url, font=url_font)
    d.text(((W - (bbox[2] - bbox[0])) / 2, qr_y + qr_size + 180), referral_url, fill=COLOR_BRAND_BLUE, font=url_font)

    # Footer pitch
    pitch_font = _font(28, "regular")
    pitch_lines = [
        "Pulse Fitness is the all-in-one fitness operations platform — maintenance,",
        "memberships, marketing and CRM under one roof. Use a partner code and",
        "you get one month free.",
    ]
    fy = H - 230
    for line in pitch_lines:
        bbox = d.textbbox((0, 0), line, font=pitch_font)
        d.text(((W - (bbox[2] - bbox[0])) / 2, fy), line, fill=COLOR_INK_500, font=pitch_font)
        fy += 38

    # Bottom brand bar
    d.rectangle([0, H - 32, W, H], fill=COLOR_BRAND_BLUE)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── 2. Social card (1200×630 PNG, landscape) ────────────────────────


def generate_social_card(full_name: str, referral_code: str, referral_url: str) -> bytes:
    """Return PNG bytes sized for OpenGraph / LinkedIn / Instagram link
    previews. Asymmetric layout: blue brand block on the right with the
    QR + code; left side for the engineer headline."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # Right brand block (40 % width)
    block_x = int(W * 0.6)
    d.rectangle([block_x, 0, W, H], fill=COLOR_BRAND_BLUE)

    # Left side — headline + engineer attribution
    headline_font = _font(56, "bold")
    sub_font = _font(28, "regular")
    name_font = _font(36, "bold")
    code_font = _font(24, "regular")

    headline_lines = _wrap("Refer your gyms to Pulse Fitness", 22)
    y = 90
    for line in headline_lines:
        d.text((70, y), line, fill=COLOR_INK_900, font=headline_font)
        y += 64

    sub_lines = _wrap(
        "Maintenance, memberships, marketing and CRM — one platform. Use a "
        "partner code and your first month is free.", 56,
    )
    y += 24
    for line in sub_lines:
        d.text((70, y), line, fill=COLOR_INK_500, font=sub_font)
        y += 34

    # Attribution block
    y = H - 170
    d.text((70, y), f"Referred by {full_name or 'a Pulse Fitness partner engineer'}",
           fill=COLOR_INK_900, font=name_font)
    d.text((70, y + 46), f"Code: {referral_code}", fill=COLOR_INK_700, font=code_font)
    d.text((70, y + 78), referral_url, fill=COLOR_BRAND_BLUE, font=code_font)

    # Right block — QR + brand text
    qr_size = 280
    qr = _qr_image(referral_url, qr_size)
    qr_x = block_x + ((W - block_x) - qr_size) // 2
    qr_y = (H - qr_size) // 2 - 30
    # Paste with a soft white card behind so the QR scans cleanly.
    card = Image.new("RGB", (qr_size + 32, qr_size + 32), "white")
    img.paste(card, (qr_x - 16, qr_y - 16))
    img.paste(qr, (qr_x, qr_y))

    brand_font = _font(28, "bold")
    brand_text = "Pulse Fitness · Partner"
    bbox = d.textbbox((0, 0), brand_text, font=brand_font)
    text_x = block_x + ((W - block_x) - (bbox[2] - bbox[0])) // 2
    d.text((text_x, qr_y + qr_size + 36), brand_text, fill="white", font=brand_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── 3. PDF pitch (single-page A4 portrait) ──────────────────────────


def generate_pdf_pitch(full_name: str, referral_code: str, referral_url: str) -> bytes:
    """One-page A4 PDF the engineer can email to a gym owner. Built
    with reportlab — fonts are stock Helvetica so no font-file
    dependency. Includes a small footer QR."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    page_w, page_h = A4  # (595.28, 841.89) points

    c = canvas.Canvas(buf, pagesize=A4)
    # Top brand bar
    c.setFillColorRGB(*[v / 255 for v in COLOR_BRAND_BLUE])
    c.rect(0, page_h - 10 * mm, page_w, 10 * mm, fill=1, stroke=0)

    # Logo wordmark + tagline
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_900])
    c.setFont("Helvetica-Bold", 28)
    c.drawString(20 * mm, page_h - 30 * mm, "Pulse Fitness")
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_500])
    c.drawString(20 * mm, page_h - 36 * mm, "Operations platform for fitness")

    # Hero
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_900])
    c.setFont("Helvetica-Bold", 26)
    c.drawString(20 * mm, page_h - 60 * mm, "Run your gym, not your admin.")
    c.setFont("Helvetica", 13)
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_700])
    body_lines = [
        "Maintenance · Memberships · Marketing · CRM — one platform. Built for",
        "single-site studios and multi-site operators alike.",
        "",
        "Why operators switch:",
        "   •  Automated equipment maintenance with engineer-routed jobs",
        "   •  Member lifecycle automations (joins → renewals → win-back)",
        "   •  Multi-channel marketing with attribution to revenue",
        "   •  CRM with quote-to-invoice for B2B sales (corporates, schools, NHS)",
    ]
    text_y = page_h - 75 * mm
    for line in body_lines:
        c.drawString(20 * mm, text_y, line)
        text_y -= 6 * mm

    # Offer call-out
    c.setFillColorRGB(*[v / 255 for v in COLOR_ACCENT])
    c.rect(20 * mm, text_y - 18 * mm, page_w - 40 * mm, 14 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(26 * mm, text_y - 11 * mm,
                 f"One month free when you sign up with code {referral_code}")

    # Attribution + QR
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_900])
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, 60 * mm, f"Referred by {full_name or 'a Pulse Fitness partner engineer'}")
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_700])
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, 54 * mm, f"Sign up: {referral_url}")

    # Footer QR (45×45 mm — large enough to scan from a printed sheet)
    qr_size_px = 300
    qr = _qr_image(referral_url, qr_size_px)
    qr_io = io.BytesIO()
    qr.save(qr_io, format="PNG")
    qr_io.seek(0)
    qr_reader = ImageReader(qr_io)
    qr_mm = 45 * mm
    c.drawImage(qr_reader, page_w - qr_mm - 20 * mm, 20 * mm, width=qr_mm, height=qr_mm)

    # Bottom brand bar + tiny print
    c.setFillColorRGB(*[v / 255 for v in COLOR_INK_500])
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 14 * mm, "Pulse Fitness · pulsefitness.ai · Partner engineer referral")
    c.setFillColorRGB(*[v / 255 for v in COLOR_BRAND_BLUE])
    c.rect(0, 0, page_w, 6 * mm, fill=1, stroke=0)
    c.showPage()
    c.save()
    return buf.getvalue()


# ── Selector ────────────────────────────────────────────────────────


COLLATERAL_KINDS = ("qr-poster", "social-card", "pdf-pitch")


def generate(kind: str, full_name: str, referral_code: str, referral_url: str) -> Tuple[bytes, str, str]:
    """Return ``(bytes, mime, filename)`` for a single asset."""
    safe_code = (referral_code or "code").replace("/", "_")
    if kind == "qr-poster":
        return generate_qr_poster(full_name, referral_code, referral_url), "image/png", f"gymaxis-qr-poster-{safe_code}.png"
    if kind == "social-card":
        return generate_social_card(full_name, referral_code, referral_url), "image/png", f"gymaxis-social-card-{safe_code}.png"
    if kind == "pdf-pitch":
        return generate_pdf_pitch(full_name, referral_code, referral_url), "application/pdf", f"gymaxis-pitch-{safe_code}.pdf"
    raise ValueError(f"Unknown collateral kind: {kind}")
