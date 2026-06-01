"""Generate the on-brand "WE NEED YOU!" engineer recruitment poster set.

Hybrid pipeline (Iter 220ea·30):
  1. Nano Banana (gemini-3.1-flash-image-preview) renders a moody, on-brand
     background photo per post — NO text baked in (image models garble copy).
  2. Pillow composites crisp, guaranteed-legible GymAxis brand text on top:
     real wordmark, white headline, brand blue→purple accent + footer CTA.

Output: /app/frontend/public/marketing/engineer_recruit/post_0N.png (1080x1920,
9:16 — works for Instagram Reels/Stories + TikTok). Procedural navy fallback
if the image API is unavailable so the script always produces a full set.

Run:  cd /app/backend && set -a && . ./.env && set +a && python -m scripts.gen_engineer_recruit_posters
"""
from __future__ import annotations

import asyncio
import base64
import os
from io import BytesIO

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()

W, H = 1080, 1920
OUT_DIR = "/app/frontend/public/marketing/engineer_recruit"
LOGO_PATH = "/app/frontend/public/brand/gymaxis-full-tight.png"
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

BRAND_FROM = (37, 99, 235)    # #2563EB navy-blue
BRAND_TO = (157, 76, 221)     # #9D4CDD purple
NAVY = (8, 11, 28)
WHITE = (255, 255, 255)

# Each post: AI background prompt + composed copy.
POSTS: list[dict] = [
    {
        "file": "post_01.png",
        "bg": "Cinematic wide photo of a confident professional fitness equipment "
              "engineer in a branded work polo and tool belt standing in a dark "
              "modern empty gym at dawn, dramatic deep blue and purple rim lighting, "
              "treadmills and strength machines silhouetted behind, moody atmospheric, "
              "shot on 35mm, shallow depth of field, no text, no words.",
        "kicker": "GYMAXIS ENGINEER NETWORK",
        "headline": "WE NEED\nYOU!",
        "accent": "Fitness equipment engineers",
        "sub": "We're opening 10 tester spaces to put the GymAxis Engineer App "
               "through its paces. Real jobs. A serious mobile toolkit. Your business.",
        "cta": "10 spaces · 10-day free trial",
    },
    {
        "file": "post_02.png",
        "bg": "Close-up cinematic photo of a fitness engineer's hands holding a "
              "smartphone showing a maintenance app, broken gym treadmill in the "
              "background, dark workshop, deep blue and purple lighting, shallow "
              "depth of field, professional, no text, no words.",
        "kicker": "INSIDE THE APP",
        "headline": "ONE JOB.\nEVERY MACHINE.",
        "accent": "Multi-machine fault batching",
        "sub": "Log five faults across three rigs under a single visit — but track "
               "each machine's resolution clock independently. No duplicate visits.",
        "cta": "Apply free — link in bio",
    },
    {
        "file": "post_03.png",
        "bg": "Cinematic photo of a fitness engineer working alone in a gym plant "
              "room / basement with no signal, headtorch glow, servicing equipment, "
              "dark moody blue purple lighting, atmospheric, professional, no text, "
              "no words.",
        "kicker": "INSIDE THE APP",
        "headline": "WORKS\nOFFLINE.",
        "accent": "Complete jobs anywhere",
        "sub": "Plant rooms and basements kill signal. The app captures the whole "
               "visit offline and syncs the second you're back on data.",
        "cta": "Apply free — link in bio",
    },
    {
        "file": "post_04.png",
        "bg": "Cinematic photo of an organised engineer's van interior full of gym "
              "equipment spare parts, belts and tools neatly racked, dark with blue "
              "and purple accent lighting, professional product photography, no text, "
              "no words.",
        "kicker": "INSIDE THE APP",
        "headline": "PARTS &\nVAN STOCK.",
        "accent": "Know what's on the van",
        "sub": "Track van stock, log parts used on each machine, and fire reorder "
               "requests before you run dry. Covered-vs-chargeable handled for you.",
        "cta": "Apply free — link in bio",
    },
    {
        "file": "post_05.png",
        "bg": "Cinematic photo of a tablet on a gym machine showing a maintenance "
              "checklist being ticked, clean modern gym, dark moody blue purple "
              "lighting, shallow depth of field, professional, no text, no words.",
        "kicker": "INSIDE THE APP",
        "headline": "PAPERLESS\nCHECK-SHEETS.",
        "accent": "PPM & H&S, audit-ready",
        "sub": "Daily, weekly, monthly PPM and safety sign-offs captured on the "
               "floor — time-stamped and geo-stamped before you leave the building.",
        "cta": "Apply free — link in bio",
    },
    {
        "file": "post_06.png",
        "bg": "Cinematic photo of an engineer photographing a serviced gym treadmill "
              "with a phone, generating a report, modern gym, dark moody blue purple "
              "lighting, professional, shallow depth of field, no text, no words.",
        "kicker": "INSIDE THE APP",
        "headline": "PHOTOS →\nREPORTS.",
        "accent": "Branded PDFs in seconds",
        "sub": "Snap before/after photos and the app builds a clean, branded service "
               "report with signatures — sent to the customer before you drive off.",
        "cta": "Apply free — link in bio",
    },
    {
        "file": "post_07.png",
        "bg": "Cinematic photo of a happy professional fitness engineer smiling, "
              "leaning on a gym machine with a phone in hand, dark modern gym, warm "
              "but deep blue and purple lighting, aspirational, professional, no "
              "text, no words.",
        "kicker": "RUN YOUR BUSINESS",
        "headline": "GET\nPAID.",
        "accent": "Quotes, invoices & payouts",
        "sub": "Raise quotes on-site, invoice in a tap, and get paid through the "
               "platform. £30/mo that drops to free once you refer 10 sites.",
        "cta": "Join the 10 testers — apply now",
    },
]


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if draw.textlength(trial, font=fnt) <= max_w or not line:
                line = trial
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def grad_image(w: int, h: int, c0, c1, horizontal: bool = True) -> Image.Image:
    base = Image.new("RGB", (w, h), c0)
    top = Image.new("RGB", (w, h), c1)
    mask = Image.new("L", (w, h))
    md = mask.load()
    for i in range(w if horizontal else h):
        v = int(255 * i / max(1, (w if horizontal else h) - 1))
        for j in range(h if horizontal else w):
            if horizontal:
                md[i, j] = v
            else:
                md[j, i] = v
    base.paste(top, (0, 0), mask)
    return base


def draw_grad_text(img: Image.Image, xy, text: str, fnt, c0, c1) -> None:
    """Draw text filled with a horizontal brand gradient."""
    dummy = ImageDraw.Draw(img)
    tw = int(dummy.textlength(text, font=fnt))
    asc, desc = fnt.getmetrics()
    th = asc + desc
    if tw <= 0:
        return
    txt_mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(txt_mask).text((0, 0), text, font=fnt, fill=255)
    grad = grad_image(tw, th, c0, c1, horizontal=True)
    img.paste(grad, (int(xy[0]), int(xy[1])), txt_mask)


def cover_fit(src: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = src.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    src = src.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return src.crop((left, top, left + w, top + h))


def overlay(bg: Image.Image) -> Image.Image:
    """Darken for legibility: global tint + heavy bottom gradient + brand glow."""
    bg = bg.convert("RGB")
    # Global tint toward navy.
    tint = Image.new("RGB", (W, H), NAVY)
    bg = Image.blend(bg, tint, 0.42)
    # Bottom-up dark gradient (text sits in the lower third).
    grad = Image.new("L", (1, H))
    gp = grad.load()
    for y in range(H):
        t = y / (H - 1)
        gp[0, y] = int(255 * min(1.0, max(0.0, (t - 0.30) / 0.70)) ** 1.3 * 0.96)
    grad = grad.resize((W, H))
    dark = Image.new("RGB", (W, H), (4, 6, 18))
    bg = Image.composite(dark, bg, grad)
    # Subtle brand glow band behind the headline area.
    glow = Image.new("RGB", (W, H), NAVY)
    gd = ImageDraw.Draw(glow, "RGB")
    gd.ellipse([-200, 980, W + 200, 1480], fill=(28, 30, 96))
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    bg = Image.blend(bg, glow, 0.28)
    return bg


async def gen_background(prompt: str) -> Image.Image | None:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.getenv("EMERGENT_LLM_KEY")
        chat = LlmChat(api_key=api_key, session_id=f"recruit-{os.urandom(4).hex()}",
                       system_message="You are a world-class advertising photographer.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(
            modalities=["image", "text"])
        msg = UserMessage(text=(
            f"{prompt} Vertical 9:16 composition, leave the lower third darker and "
            "less busy for text overlay. Photorealistic, premium brand advertising."))
        _text, images = await chat.send_message_multimodal_response(msg)
        if images:
            data = base64.b64decode(images[0]["data"])
            return Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! background gen failed ({exc}); using procedural fallback")
    return None


def procedural_bg() -> Image.Image:
    bg = grad_image(W, H, (10, 14, 40), (26, 14, 54), horizontal=False)
    glow = Image.new("RGB", (W, H), NAVY)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.1, H * 0.05, W * 1.1, H * 0.6], fill=BRAND_FROM)
    gd.ellipse([-W * 0.3, H * 0.4, W * 0.6, H * 0.95], fill=(70, 30, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(240))
    return Image.blend(bg, glow, 0.5)


def compose(post: dict, bg: Image.Image) -> Image.Image:
    img = overlay(cover_fit(bg, W, H))
    draw = ImageDraw.Draw(img)
    margin = 84
    max_w = W - margin * 2

    # Logo (real wordmark) on an intentional white rounded chip, top-left.
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        lw = 300
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        pad = 22
        chip_w, chip_h = lw + pad * 2, logo.height + pad * 2
        chip = Image.new("RGBA", (chip_w, chip_h), (0, 0, 0, 0))
        ImageDraw.Draw(chip).rounded_rectangle(
            [0, 0, chip_w, chip_h], radius=28, fill=(255, 255, 255, 255))
        chip.paste(logo, (pad, pad), logo)
        img.paste(chip, (margin, 92), chip)
    except Exception:
        pass

    # Bottom-anchored text block. Measure from the bottom up.
    f_kick = font(FONT_BOLD, 34)
    # Headline auto-fits: shrink until the widest line fits the column.
    head_lines = post["headline"].split("\n")
    head_size = 150
    while head_size > 88:
        ftest = font(FONT_BOLD, head_size)
        if max(draw.textlength(ln, font=ftest) for ln in head_lines) <= max_w:
            break
        head_size -= 4
    f_head = font(FONT_BOLD, head_size)
    head_lh = int(head_size * 1.0)
    f_acc = font(FONT_BOLD, 52)
    f_sub = font(FONT_REG, 40)
    f_cta = font(FONT_BOLD, 40)

    sub_lines = wrap(draw, post["sub"], f_sub, max_w)

    sub_lh = 54
    cta_h = 112
    block_h = (
        40 + 16                       # kicker
        + len(head_lines) * head_lh + 18
        + 66 + 24                     # accent
        + len(sub_lines) * sub_lh + 40
        + cta_h
    )
    y = H - 120 - block_h

    # Kicker (gradient).
    draw_grad_text(img, (margin, y), post["kicker"], f_kick, BRAND_FROM, BRAND_TO)
    y += 40 + 16

    # Headline (white, tight leading) with soft shadow.
    for ln in head_lines:
        draw.text((margin + 3, y + 3), ln, font=f_head, fill=(0, 0, 0))
        draw.text((margin, y), ln, font=f_head, fill=WHITE)
        y += head_lh
    y += 18

    # Accent line (gradient).
    draw_grad_text(img, (margin, y), post["accent"], f_acc, BRAND_FROM, BRAND_TO)
    y += 66 + 24

    # Sub copy.
    for ln in sub_lines:
        draw.text((margin, y), ln, font=f_sub, fill=(224, 228, 240))
        y += sub_lh
    y += 40

    # Footer CTA pill (brand gradient).
    cta = post["cta"]
    pad_x, pill_h = 44, 84
    tw = int(draw.textlength(cta, font=f_cta))
    pill_w = min(max_w, tw + pad_x * 2)
    pill = grad_image(pill_w, pill_h, BRAND_FROM, BRAND_TO, horizontal=True)
    mask = Image.new("L", (pill_w, pill_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pill_w, pill_h], radius=pill_h // 2, fill=255)
    img.paste(pill, (margin, int(y)), mask)
    tx = margin + (pill_w - tw) // 2
    ImageDraw.Draw(img).text((tx, int(y) + (pill_h - f_cta.getmetrics()[0] - 6) // 2),
                             cta, font=f_cta, fill=WHITE)
    return img


async def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    cache = os.path.join(OUT_DIR, "_bg")
    os.makedirs(cache, exist_ok=True)
    for post in POSTS:
        print(f"• {post['file']} — {post['headline'].replace(chr(10), ' ')}")
        bg_path = os.path.join(cache, post["file"])
        if os.path.exists(bg_path):
            bg = Image.open(bg_path).convert("RGB")
            print("  reusing cached background")
        else:
            bg = await gen_background(post["bg"])
            if bg is not None:
                bg.save(bg_path, "PNG")
            else:
                bg = procedural_bg()
        out = compose(post, bg)
        out.save(os.path.join(OUT_DIR, post["file"]), "PNG")
        print(f"  saved {OUT_DIR}/{post['file']}")
    print("Done — 7 posters generated.")


if __name__ == "__main__":
    asyncio.run(main())
