"""Reception poster generator for a gym's white-label member app.

Renders a single PNG (A4 portrait, 300dpi quality) with:
  • Studio name + brand colour band
  • Large QR code pointing to /m/{slug}
  • Short tagline + shareable URL

The poster is public (no auth): operators embed it in print jobs, email
it to members, or tape it to the reception counter.
"""
from __future__ import annotations

import io
import logging
from typing import Literal

import qrcode
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = (hex_str or "#19CDFF").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return 25, 205, 255


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Fall back gracefully across common server font paths."""
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    candidates_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in (candidates_bold if bold else candidates_regular):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, canvas_w: int) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((canvas_w - w) // 2, y), text, font=font, fill=fill)
    return y + h


def render_poster_png(
    *,
    studio_name: str,
    url: str,
    brand_hex: str = "#19CDFF",
    tagline: str = "Book your next class — scan to open the app.",
    variant: Literal["book", "brag"] = "book",
    fmt: Literal["a4", "square", "story"] = "a4",
) -> bytes:
    """Render a QR poster PNG.

    Formats:
      • `a4`     → 1240×1754 (A4 portrait, reception print)
      • `square` → 1080×1080 (Instagram feed post)
      • `story`  → 1080×1920 (Instagram / TikTok story)
    """
    dims = {
        "a4":     (1240, 1754),
        "square": (1080, 1080),
        "story":  (1080, 1920),
    }
    W, H = dims.get(fmt, dims["a4"])
    bg = (5, 7, 10)  # #05070A
    white = (255, 255, 255)
    muted = (180, 190, 200)
    brand = _hex_to_rgb(brand_hex)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # ── Brand band header (scales with canvas height)
    band_h = max(170, min(280, H // 7))
    draw.rectangle((0, 0, W, band_h), fill=brand)
    # Soft vignette under the band
    for i in range(14):
        draw.rectangle((0, band_h + i, W, band_h + i + 1), fill=bg)

    # Wordmark
    eyebrow_size = max(20, W // 45)
    studio_size = max(44, min(88, W // 17))
    f_eyebrow = _load_font(eyebrow_size, bold=True)
    f_studio = _load_font(studio_size, bold=True)
    margin_x = max(60, W // 20)
    draw.text((margin_x, band_h // 4), "GYMAXIS  ·  YOUR STUDIO APP", font=f_eyebrow, fill=(5, 7, 10))
    # Studio name — single line, shrinks to fit
    name_font = f_studio
    display_name = (studio_name or "Your Studio")
    while draw.textbbox((0, 0), display_name, font=name_font)[2] > W - (margin_x * 2) and name_font.size > 30:
        name_font = _load_font(name_font.size - 4, bold=True)
    draw.text((margin_x, band_h // 2 + 10), display_name, font=name_font, fill=(5, 7, 10))

    # ── QR code card (scales to canvas)
    qr_card = min(W - (margin_x * 2), H - band_h - 380, 880)
    qr_inner = qr_card - 120  # padding
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=18,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((qr_inner, qr_inner), Image.NEAREST)

    card_x = (W - qr_card) // 2
    card_y = band_h + max(60, H // 25)
    draw.rounded_rectangle((card_x, card_y, card_x + qr_card, card_y + qr_card), radius=34, fill=white)
    img.paste(qr_img, (card_x + 60, card_y + 60))

    # Brand centre-tag on QR
    tag_d = max(80, qr_card // 8)
    tag_cx = card_x + qr_card // 2
    tag_cy = card_y + qr_card // 2
    draw.ellipse(
        (tag_cx - tag_d // 2, tag_cy - tag_d // 2,
         tag_cx + tag_d // 2, tag_cy + tag_d // 2),
        fill=brand, outline=white, width=8,
    )
    f_tag = _load_font(tag_d // 3, bold=True)
    letter = (studio_name[:1] or "G").upper()
    bb = draw.textbbox((0, 0), letter, font=f_tag)
    draw.text((tag_cx - (bb[2] - bb[0]) // 2, tag_cy - (bb[3] - bb[1]) // 2 - 4), letter, font=f_tag, fill=(5, 7, 10))

    # ── Footer block (scales with canvas width)
    y = card_y + qr_card + max(40, H // 30)
    f_cta = _load_font(max(36, W // 22), bold=True)
    f_tagline = _load_font(max(22, W // 45), bold=False)
    f_url = _load_font(max(20, W // 50), bold=True)
    f_fine = _load_font(max(16, W // 60), bold=False)

    cta = "Scan to see live class times" if variant == "brag" else "Scan to book your next class"
    y = _draw_centered(draw, cta, y, f_cta, white, W)
    y += 14
    y = _draw_centered(draw, tagline, y, f_tagline, muted, W)
    y += 30
    # URL pill
    url_display = url.replace("https://", "").replace("http://", "")
    if len(url_display) > 54:
        url_display = url_display[:54] + "…"
    bb = draw.textbbox((0, 0), url_display, font=f_url)
    pill_w = (bb[2] - bb[0]) + 60
    pill_h = (bb[3] - bb[1]) + 28
    pill_x = (W - pill_w) // 2
    draw.rounded_rectangle(
        (pill_x, y, pill_x + pill_w, y + pill_h),
        radius=pill_h // 2, outline=brand, width=3,
    )
    draw.text((pill_x + 30, y + 12), url_display, font=f_url, fill=brand)
    _draw_centered(draw, "Powered by Pulse Fitness", H - max(40, H // 30), f_fine, (120, 128, 140), W)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_og_png(
    *,
    studio_name: str,
    brand_hex: str = "#19CDFF",
    stats: dict | None = None,
    tagline: str = "Live class times · instant booking · your studio.",
) -> bytes:
    """Render a 1200×630 Open Graph preview image for social-share unfurls.

    Landscape layout: studio wordmark + hero number + tagline on the left,
    three mini stat chips down the right.
    """
    W, H = 1200, 630
    bg = (5, 7, 10)
    white = (255, 255, 255)
    muted = (160, 170, 180)
    brand = _hex_to_rgb(brand_hex)
    stats = stats or {}

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Brand side bar
    draw.rectangle((0, 0, 14, H), fill=brand)

    # Eyebrow + studio name
    f_eyebrow = _load_font(20, bold=True)
    f_studio = _load_font(64, bold=True)
    f_hero_label = _load_font(18, bold=True)
    f_hero_value = _load_font(110, bold=True)
    f_tagline = _load_font(24, bold=False)
    f_chip_label = _load_font(14, bold=True)
    f_chip_value = _load_font(42, bold=True)
    f_foot = _load_font(16, bold=False)

    draw.text((60, 60), "GYMAXIS · STUDIO APP", font=f_eyebrow, fill=brand)
    name_font = f_studio
    display_name = (studio_name or "Your Studio")
    while draw.textbbox((0, 0), display_name, font=name_font)[2] > 640 and name_font.size > 32:
        name_font = _load_font(name_font.size - 4, bold=True)
    draw.text((60, 100), display_name, font=name_font, fill=white)

    # Hero number — active members
    active = str(stats.get("active_members") or "—")
    draw.text((60, 240), "ACTIVE MEMBERS", font=f_hero_label, fill=muted)
    draw.text((58, 270), active, font=f_hero_value, fill=brand)

    # Tagline
    draw.text((60, 420), tagline, font=f_tagline, fill=muted)
    draw.text((60, H - 52), "Powered by Pulse Fitness", font=f_foot, fill=(120, 128, 140))

    # Right-side stat chips
    chip_w, chip_h = 380, 130
    chip_x = W - chip_w - 60
    chips = [
        ("CLASSES THIS MONTH", str(stats.get("classes_this_month") or "—")),
        ("CHECK-INS",          str(stats.get("attendance_this_month") or "—")),
        ("TOP CLASS",          (stats.get("top_class") or {}).get("name") or "—"),
    ]
    chip_y = 70
    for label, value in chips:
        draw.rounded_rectangle(
            (chip_x, chip_y, chip_x + chip_w, chip_y + chip_h),
            radius=20, fill=(14, 18, 24), outline=(255, 255, 255, 20), width=1,
        )
        draw.text((chip_x + 24, chip_y + 22), label, font=f_chip_label, fill=brand)
        # value shrinks if too wide
        value_font = f_chip_value
        while draw.textbbox((0, 0), value, font=value_font)[2] > chip_w - 48 and value_font.size > 18:
            value_font = _load_font(value_font.size - 4, bold=True)
        draw.text((chip_x + 24, chip_y + 52), value, font=value_font, fill=white)
        chip_y += chip_h + 20

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_poster_pdf(**kwargs) -> bytes:
    """A4 poster wrapped in a minimal one-page PDF for print shops."""
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.utils import ImageReader

    png_bytes = render_poster_png(fmt="a4", **kwargs)
    buf = _io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.drawImage(ImageReader(_io.BytesIO(png_bytes)), 0, 0, width=W, height=H, preserveAspectRatio=True, anchor="c")
    c.showPage()
    c.save()
    return buf.getvalue()
