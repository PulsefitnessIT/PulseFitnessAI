"""Deterministic, brand-accurate social card renderer (Iter 222).

Replaces the unreliable generative-AI image path that hallucinated fake
dashboards, wrong logos and blank gradients. Every card here is rendered
with Pillow from real brand tokens + the real Pulse Fitness logo + (optionally)
a REAL product screenshot — so nothing is ever invented.

Five layouts, all channel-aware (1:1 / 9:16 / 1.91:1):
  * ``hook``        — bold one-line statement on a brand gradient.
  * ``stat``        — big number + label (numbers-led) on a dark canvas.
  * ``feature``     — feature title + up to 3 benefit bullets.
  * ``punchline``   — setup → payoff (tasteful ops humour).
  * ``screenshot``  — a real product screenshot in a browser frame.

This module imports nothing from ``social_autopilot`` (one-way dependency)
to avoid an import cycle. The orchestrator passes brand tokens + the
chosen layout fields in.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Font discovery ────────────────────────────────────────────────────
_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]
_FONT_REG_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


def _font_path(bold: bool) -> Optional[str]:
    cands = _FONT_BOLD_CANDIDATES if bold else _FONT_REG_CANDIDATES
    return next((p for p in cands if os.path.exists(p)), None)


def _font(size: int, bold: bool = True):
    from PIL import ImageFont  # type: ignore
    path = _font_path(bold)
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _hex(h: str) -> tuple[int, int, int]:
    s = h.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _text_w(font, text: str) -> int:
    try:
        return int(font.getlength(text))
    except Exception:
        try:
            b = font.getbbox(text)
            return int(b[2] - b[0])
        except Exception:
            return len(text) * 6


def _wrap(font, text: str, max_w: int) -> list[str]:
    out: list[str] = []
    cur = ""
    for word in (text or "").split():
        cand = (cur + " " + word).strip()
        if _text_w(font, cand) <= max_w:
            cur = cand
        else:
            if cur:
                out.append(cur)
            # hard-truncate a single over-wide word
            while word and _text_w(font, word + "…") > max_w:
                word = word[:-1]
            cur = (word + "…") if word and _text_w(font, word) > max_w else word
    if cur:
        out.append(cur)
    return out


def _fit_font(text: str, max_w: int, start_px: int, *, bold: bool = True,
              min_px: int = 14):
    """Return the largest single-line font ≤ start_px that fits max_w."""
    px = start_px
    while px > min_px:
        f = _font(px, bold)
        if _text_w(f, text) <= max_w:
            return f
        px = int(px * 0.92)
    return _font(min_px, bold)


# ── Backgrounds ───────────────────────────────────────────────────────
def _gradient_bg(w: int, h: int, c1: str, c2: str):
    from PIL import Image, ImageDraw  # type: ignore
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    a, b = _hex(c1), _hex(c2)
    for y in range(h):
        t = y / max(1, h - 1)
        draw.line([(0, y), (w, y)], fill=(
            int(a[0] * (1 - t) + b[0] * t),
            int(a[1] * (1 - t) + b[1] * t),
            int(a[2] * (1 - t) + b[2] * t),
        ))
    # subtle depth circles
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.ellipse([int(w * 0.74), int(h * 0.04), int(w * 1.02), int(h * 0.30)],
               fill=(255, 255, 255, 16))
    od.ellipse([int(w * -0.04), int(h * 0.78), int(w * 0.18), int(h * 0.98)],
               fill=(255, 255, 255, 12))
    return Image.alpha_composite(img.convert("RGBA"), ov)


def _dark_bg(w: int, h: int, c1: str, c2: str):
    """Deep-navy canvas (matches the Pulse Fitness app dark theme) with two
    soft brand-coloured glows. Premium, never a flat block."""
    from PIL import Image, ImageDraw, ImageFilter  # type: ignore
    base = Image.new("RGBA", (w, h), (10, 14, 31, 255))  # #0A0E1F
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    r = int(min(w, h) * 0.55)
    gd.ellipse([int(w * 0.55), int(-h * 0.18), int(w * 0.55) + r * 2, int(-h * 0.18) + r * 2],
               fill=_hex(c1) + (120,))
    gd.ellipse([int(-w * 0.25), int(h * 0.55), int(-w * 0.25) + r * 2, int(h * 0.55) + r * 2],
               fill=_hex(c2) + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.10)))
    return Image.alpha_composite(base, glow)


# ── Logo badge ────────────────────────────────────────────────────────
def _draw_logo_badge(img, x: int, y: int, h: int, brand: dict, logo_path: Optional[str],
                     *, light_bg: bool = False):
    """Paste a rounded white badge with the real logo. The website
    domain is intentionally NOT rendered (Iter 223 — brand wants clean,
    URL-free cards). Mutates and returns ``img`` (RGBA)."""
    from PIL import Image, ImageDraw  # type: ignore
    sub_font = _font(int(h * 0.026), bold=False)
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            target_h = int(h * 0.066)
            scale = target_h / logo.height
            logo = logo.resize((int(logo.width * scale), target_h), Image.LANCZOS)
            pad_x, pad_y = int(target_h * 0.55), int(target_h * 0.28)
            bw, bh = logo.width + pad_x * 2, target_h + pad_y * 2
            badge = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            bd = ImageDraw.Draw(badge)
            bd.rounded_rectangle([0, 0, bw, bh], radius=int(bh * 0.32),
                                 fill=(255, 255, 255, 250))
            badge.paste(logo, (pad_x, pad_y), logo)
            img.paste(badge, (x, y), badge)
            return img
        except Exception as exc:  # pragma: no cover
            logger.info("[social-tpl] logo badge failed: %s", exc)
    # text fallback — brand name only, no URL
    d = ImageDraw.Draw(img)
    d.text((x, y), brand["name"].upper(), fill=(255, 255, 255, 255),
           font=_font(int(h * 0.032)))
    return img


def _draw_kicker(draw, x: int, y: int, h: int, text: str, color):
    f = _font(int(h * 0.026), bold=True)
    # letter-spacing emulation
    cx = x
    for ch in text.upper():
        draw.text((cx, y), ch, fill=color, font=f)
        cx += _text_w(f, ch) + int(h * 0.006)


# ── Layout renderers ──────────────────────────────────────────────────
def _render_hook(w, h, brand, fields, logo_path):
    from PIL import ImageDraw  # type: ignore
    img = _gradient_bg(w, h, brand["color_primary"], brand["color_accent"])
    draw = ImageDraw.Draw(img)
    x = int(w * 0.07)
    safe = w - 2 * x
    headline = (fields.get("headline") or "").strip()
    px = int(h * 0.092)
    font = _font(px)
    lines = _wrap(font, headline, safe)
    while len(lines) > 4 and px > int(h * 0.05):
        px = int(px * 0.9)
        font = _font(px)
        lines = _wrap(font, headline, safe)
    lh = int(px * 1.16)
    y0 = int(h * 0.38) - (len(lines) - 1) * lh // 2
    for i, ln in enumerate(lines):
        draw.text((x, y0 + i * lh), ln, fill=(255, 255, 255), font=font)
    sub = (fields.get("subtitle") or brand.get("tagline") or "").strip()
    if sub:
        sf = _font(int(h * 0.030), bold=False)
        sy = y0 + len(lines) * lh + int(h * 0.025)
        for ln in _wrap(sf, sub, safe)[:2]:
            draw.text((x, sy), ln, fill=(255, 255, 255, 220), font=sf)
            sy += int(h * 0.046)
    _draw_logo_badge(img, x, int(h * 0.84), h, brand, logo_path)
    return img


def _render_stat(w, h, brand, fields, logo_path):
    from PIL import ImageDraw  # type: ignore
    img = _dark_bg(w, h, brand["color_primary"], brand["color_accent"])
    draw = ImageDraw.Draw(img)
    x = int(w * 0.08)
    safe = w - 2 * x
    is_industry = (fields.get("stat_kind") == "industry")
    kicker = "INDUSTRY ESTIMATE" if is_industry else "BY THE NUMBERS"
    _draw_kicker(draw, x, int(h * 0.16), h, kicker,
                 _hex(brand["color_primary"]) + (255,))
    # Big stat value
    value = (fields.get("stat_value") or "").strip()
    vfont = _fit_font(value, safe, int(h * 0.26), bold=True, min_px=int(h * 0.10))
    vy = int(h * 0.22)
    draw.text((x, vy), value, fill=(255, 255, 255), font=vfont)
    try:
        vh = vfont.getbbox(value)[3]
    except Exception:
        vh = int(h * 0.20)
    # Label
    label = (fields.get("stat_label") or "").strip()
    lfont = _font(int(h * 0.046), bold=True)
    ly = vy + vh + int(h * 0.03)
    for ln in _wrap(lfont, label, safe)[:4]:
        draw.text((x, ly), ln, fill=(220, 225, 240), font=lfont)
        ly += int(h * 0.058)
    # thin accent bar
    draw.rectangle([x, int(h * 0.205), x + int(w * 0.16), int(h * 0.205) + max(4, int(h * 0.006))],
                   fill=_hex(brand["color_accent"]))
    _draw_logo_badge(img, x, int(h * 0.84), h, brand, logo_path)
    return img


def _render_feature(w, h, brand, fields, logo_path):
    from PIL import ImageDraw  # type: ignore
    img = _dark_bg(w, h, brand["color_primary"], brand["color_accent"])
    draw = ImageDraw.Draw(img)
    x = int(w * 0.08)
    safe = w - 2 * x
    _draw_kicker(draw, x, int(h * 0.14), h, "GYMAXIS FEATURE",
                 _hex(brand["color_primary"]) + (255,))
    title = (fields.get("headline") or "").strip()
    tfont = _font(int(h * 0.066))
    tlines = _wrap(tfont, title, safe)[:2]
    ty = int(h * 0.21)
    for ln in tlines:
        draw.text((x, ty), ln, fill=(255, 255, 255), font=tfont)
        ty += int(h * 0.078)
    # bullets
    bullets = [b for b in (fields.get("bullets") or []) if isinstance(b, str) and b.strip()][:3]
    bfont = _font(int(h * 0.040), bold=False)
    by = ty + int(h * 0.04)
    dot_r = max(4, int(h * 0.010))
    for b in bullets:
        cy = by + int(h * 0.022)
        draw.ellipse([x, cy, x + dot_r * 2, cy + dot_r * 2],
                     fill=_hex(brand["color_accent"]))
        bx = x + dot_r * 2 + int(w * 0.03)
        blines = _wrap(bfont, b.strip(), safe - (bx - x))[:2]
        for j, ln in enumerate(blines):
            draw.text((bx, by + j * int(h * 0.05)), ln, fill=(225, 230, 245), font=bfont)
        by += int(h * 0.05) * max(1, len(blines)) + int(h * 0.028)
    _draw_logo_badge(img, x, int(h * 0.85), h, brand, logo_path)
    return img


def _render_punchline(w, h, brand, fields, logo_path):
    from PIL import ImageDraw  # type: ignore
    img = _gradient_bg(w, h, brand["color_accent"], brand["color_primary"])
    draw = ImageDraw.Draw(img)
    x = int(w * 0.08)
    safe = w - 2 * x
    setup = (fields.get("setup") or "").strip()
    payoff = (fields.get("payoff") or fields.get("headline") or "").strip()
    sf = _font(int(h * 0.038), bold=False)
    sy = int(h * 0.24)
    for ln in _wrap(sf, setup, safe)[:3]:
        draw.text((x, sy), ln, fill=(255, 255, 255, 225), font=sf)
        sy += int(h * 0.050)
    px = int(h * 0.078)
    pfont = _font(px)
    plines = _wrap(pfont, payoff, safe)
    while len(plines) > 3 and px > int(h * 0.05):
        px = int(px * 0.9)
        pfont = _font(px)
        plines = _wrap(pfont, payoff, safe)
    plines = plines[:3]
    plh = int(px * 1.16)
    py = sy + int(h * 0.045)
    for ln in plines:
        draw.text((x, py), ln, fill=(255, 255, 255), font=pfont)
        py += plh
    _draw_logo_badge(img, x, int(h * 0.85), h, brand, logo_path)
    return img


def _render_screenshot(w, h, brand, fields, logo_path):
    from PIL import Image, ImageDraw, ImageFilter  # type: ignore
    img = _dark_bg(w, h, brand["color_primary"], brand["color_accent"])
    draw = ImageDraw.Draw(img)
    x = int(w * 0.07)
    safe = w - 2 * x
    headline = (fields.get("headline") or "").strip()
    hpx = int(h * 0.050)
    hfont = _font(hpx)
    hlines = _wrap(hfont, headline, safe)
    if len(hlines) > 2:
        hpx = int(h * 0.042)
        hfont = _font(hpx)
        hlines = _wrap(hfont, headline, safe)[:3]
    hlh = int(hpx * 1.22)
    hy = int(h * 0.06)
    for ln in hlines:
        draw.text((x, hy), ln, fill=(255, 255, 255), font=hfont)
        hy += hlh

    shot_path = fields.get("screenshot_path")
    if shot_path and os.path.exists(shot_path):
        try:
            shot = Image.open(shot_path).convert("RGB")
            frame_w = int(w * 0.86)
            bar_h = max(20, int(frame_w * 0.035))
            inner_w = frame_w
            scale = inner_w / shot.width
            inner_h = int(shot.height * scale)
            # cap height so it fits between headline and logo
            avail_h = int(h * 0.83) - (hy + int(h * 0.02))
            max_inner_h = avail_h - bar_h
            if inner_h > max_inner_h and max_inner_h > 0:
                inner_h = max_inner_h
                inner_w = int(shot.width * (inner_h / shot.height))
                frame_w = inner_w
            shot = shot.resize((inner_w, inner_h), Image.LANCZOS)
            total_h = inner_h + bar_h
            frame = Image.new("RGBA", (frame_w, total_h), (255, 255, 255, 255))
            # top browser bar
            fd = ImageDraw.Draw(frame)
            fd.rectangle([0, 0, frame_w, bar_h], fill=(20, 26, 46, 255))
            cdot = bar_h // 2
            for k, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                fd.ellipse([int(bar_h * 0.6) + k * int(bar_h * 0.7), cdot - cdot // 3,
                            int(bar_h * 0.6) + k * int(bar_h * 0.7) + (cdot // 3) * 2,
                            cdot + cdot // 3], fill=col)
            frame.paste(shot, (0, bar_h))
            # rounded corners mask
            mask = Image.new("L", (frame_w, total_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, frame_w, total_h],
                                                   radius=int(bar_h * 0.7), fill=255)
            # drop shadow
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            sx = (w - frame_w) // 2
            sy = hy + int(h * 0.02)
            sh = Image.new("RGBA", (frame_w, total_h), (0, 0, 0, 150))
            shadow.paste(sh, (sx, sy + int(h * 0.012)), mask)
            shadow = shadow.filter(ImageFilter.GaussianBlur(int(h * 0.02)))
            img = Image.alpha_composite(img, shadow)
            img.paste(frame, (sx, sy), mask)
            draw = ImageDraw.Draw(img)
        except Exception as exc:  # pragma: no cover
            logger.info("[social-tpl] screenshot compose failed: %s", exc)
    _draw_logo_badge(img, x, int(h * 0.86), h, brand, logo_path)
    return img


_RENDERERS = {
    "hook": _render_hook,
    "stat": _render_stat,
    "feature": _render_feature,
    "punchline": _render_punchline,
    "screenshot": _render_screenshot,
}

LAYOUTS = tuple(_RENDERERS.keys())


def render_social_card(layout: str, *, w: int, h: int, brand: dict,
                       fields: dict, logo_path: Optional[str]) -> Optional[bytes]:
    """Render a layout to PNG bytes. Falls back to ``hook`` for unknown
    layouts, and returns ``None`` only if Pillow is unavailable."""
    try:
        from PIL import Image  # noqa: F401  type: ignore
    except Exception as exc:  # pragma: no cover
        logger.info("[social-tpl] Pillow unavailable: %s", exc)
        return None
    renderer = _RENDERERS.get(layout, _render_hook)
    try:
        img = renderer(w, h, brand, fields or {}, logo_path)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as exc:  # pragma: no cover
        logger.warning("[social-tpl] render %s failed: %s", layout, exc)
        try:
            img = _render_hook(w, h, brand, fields or {}, logo_path)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception:
            return None
