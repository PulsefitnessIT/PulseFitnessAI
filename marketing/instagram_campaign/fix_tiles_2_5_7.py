"""
Fix-up pass:
  - Tile 5: PIL composite the real GA mark PNG onto a 1920x1920 white canvas
    (no AI generation -> guaranteed pixel-perfect logo).
  - Tiles 2 & 7: regenerate using ONLY the logo as reference (no master ref)
    with explicit anti-grid wording so the model cannot reproduce a 9-panel
    layout inside a single tile.
"""
import asyncio
import base64
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageFilter

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent  # noqa: E402

OUT = Path("/app/marketing/instagram_campaign")
TILES_DIR = OUT / "mosaic_tiles_fhd_native"
MARK = OUT / "gymaxis_mark.png"
LOGO = OUT / "gymaxis_logo.png"  # full lockup, used only as colour ref
MODEL = "gemini-3-pro-image-preview"
TILE_PX = 1920


# ---------- Tile 5: PIL composite -----------------------------------------
def build_tile_5() -> None:
    canvas = Image.new("RGB", (TILE_PX, TILE_PX), "white")
    mark = Image.open(MARK).convert("RGB")
    # crop the mark to its actual bounding box (the file has whitespace around it)
    # The provided file is 1536x1024 with the GA mark centred. Crop to a square
    # around the centre that contains the mark plus a small padding ring.
    w, h = mark.size
    side = h  # 1024
    left = (w - side) // 2
    mark_sq = mark.crop((left, 0, left + side, side))
    # find non-white bounding box
    grey = mark_sq.convert("L")
    bbox = grey.point(lambda p: 0 if p > 245 else 255).getbbox()
    if bbox:
        mark_sq = mark_sq.crop(bbox)
    # scale so mark occupies ~60% of tile width, keep aspect ratio
    target_w = int(TILE_PX * 0.6)
    aspect = mark_sq.size[1] / mark_sq.size[0]
    target_h = int(target_w * aspect)
    mark_resized = mark_sq.resize((target_w, target_h), Image.LANCZOS)
    # paste centred
    x = (TILE_PX - target_w) // 2
    y = (TILE_PX - target_h) // 2
    canvas.paste(mark_resized, (x, y))
    out = TILES_DIR / "tile_05.png"
    canvas.save(out, "PNG", optimize=True)
    print(f"[ok] tile_05 composited: {out.name} ({out.stat().st_size // 1024} KB)")


# ---------- Tiles 2 & 7: AI regen with logo-only ref -----------------------
TILE_BRIEFS = {
    2: (
        "STRONGER BUSINESS",
        "top-centre",
        "Bottom edge dotted halftone wave running horizontally across the tile.",
        'Centred top: a clean monoline outline DUMBBELL icon in the brand '
        'gradient (blue #2563EB to indigo #1E3A8A). Beneath the icon, a bold '
        'left-aligned-but-centred-as-a-block headline reads "STRONGER" on '
        'line 1 in solid black uppercase, then "BUSINESS." on line 2 in the '
        'gradient blue uppercase. Beneath that, a short two-line sub-copy '
        'in 60% gray, slightly smaller: "Everything you need to run, grow '
        'and scale."',
    ),
    7: (
        "YOUR AXIS YOUR ADVANTAGE",
        "bottom-left",
        "Bottom edge: a band of dotted halftone in the brand gradient running "
        "horizontally across the bottom.",
        'Headline left-aligned at the upper-left of the tile, two lines: '
        '"YOUR AXIS." in solid black uppercase on line 1, then '
        '"YOUR ADVANTAGE." in the gradient blue uppercase on line 2. '
        'Three short sub-lines beneath in 60% gray: "Powerful tools." then '
        '"Smarter insights." then "Better results." Each on its own line.',
    ),
}

PROMPT_TEMPLATE = """
You are producing ONE single Instagram tile for the SaaS brand GYMAXIS.
This is tile {n} of a 9-tile mosaic, but the OUTPUT IS ONE TILE ONLY.

ABSOLUTELY CRITICAL OUTPUT RULES (READ CAREFULLY):
- The output must be a SINGLE 1:1 SQUARE TILE. ONE tile. ONE composition.
- DO NOT render a 3x3 grid. DO NOT render multiple panels. DO NOT subdivide
  the canvas with internal black lines. DO NOT show 9 small versions of
  this tile. The canvas is ONE single white square containing ONE single
  composition.
- DO NOT include the GymAxis wordmark, the tagline, or any "GYMAXIS" text
  anywhere. This tile is purely typographic + decorative content as briefed.
- DO NOT include the GA logo mark on this tile. The logo reference is
  supplied only so you match its colour palette (blue #2563EB to indigo
  #1E3A8A to a hint of royal purple #6F42C1).

VISUAL DNA (must match the rest of the GymAxis mosaic series):
- Background: pure white #FFFFFF, generous editorial whitespace.
- Brand gradient: vibrant blue #2563EB to deep indigo #1E3A8A with a hint
  of royal purple #6F42C1.
- Decorative motif on the relevant edge ONLY: {edge_motif}
- Typography: bold geometric sans-serif (Proxima Nova / Maax Rounded feel),
  uppercase, tight tracking. Sub-copy lighter weight, small. CRISP, sharp,
  fully anti-aliased glyphs.
- Iconography (if any): clean monoline outline icons in brand gradient,
  ~3px stroke weight. No filled shapes.
- No photographs, no 3D renders, no emoji, no clip-art.

TILE BRIEF (the entire content of this single tile): {brief}

Output ONE tile only.
""".strip()


async def regen_tile(n: int, logo_b64: str) -> tuple[int, bool, str]:
    title, position, edge_motif, brief = TILE_BRIEFS[n]
    prompt = PROMPT_TEMPLATE.format(n=n, edge_motif=edge_motif, brief=brief)
    out_path = TILES_DIR / f"tile_{n:02d}.png"
    try:
        chat = LlmChat(
            api_key=os.getenv("EMERGENT_LLM_KEY"),
            session_id=f"gymaxis-fix-{n}-{int(time.time())}",
            system_message="You are a senior brand designer. Output exactly ONE square tile, never a multi-panel grid.",
        )
        chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
        msg = UserMessage(text=prompt, file_contents=[ImageContent(logo_b64)])
        text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            return n, False, f"no images. text={text[:160]}"
        raw = base64.b64decode(images[0]["data"])
        tmp = TILES_DIR / f"tile_{n:02d}_raw.png"
        tmp.write_bytes(raw)
        img = Image.open(tmp).convert("RGB")
        if img.size[0] != img.size[1]:
            side = min(img.size)
            left = (img.size[0] - side) // 2
            top = (img.size[1] - side) // 2
            img = img.crop((left, top, left + side, top + side))
        if img.size[0] != TILE_PX:
            img = img.resize((TILE_PX, TILE_PX), Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=2))
        img.save(out_path, "PNG", optimize=True)
        tmp.unlink(missing_ok=True)
        return n, True, f"{out_path.name} ({out_path.stat().st_size // 1024} KB) - {title}"
    except Exception as exc:  # noqa: BLE001
        return n, False, f"{title}: {exc}"


async def main() -> None:
    build_tile_5()  # synchronous PIL composite
    logo_b64 = base64.b64encode(LOGO.read_bytes()).decode("utf-8")
    print("[start] regenerating tiles 2 and 7 with logo-only reference...", flush=True)
    results = await asyncio.gather(*[regen_tile(n, logo_b64) for n in TILE_BRIEFS])
    for n, ok, msg in sorted(results):
        flag = "OK " if ok else "FAIL"
        print(f"  {flag} tile_{n:02d}: {msg}")


if __name__ == "__main__":
    asyncio.run(main())
