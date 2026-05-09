"""
GymAxis 9-tile Instagram MOSAIC — FHD edition.

Differences vs generate_mosaic.py:
- Uses `gemini-3-pro-image-preview` (Pro model, higher native fidelity).
- Upscales the master to a 5760x5760 working canvas with LANCZOS + a sharpening
  pass before slicing, so each 1/3 tile crops out at true >=1920x1920 (FHD+).
- Each tile is saved at 1920x1920 PNG (Instagram-FHD square).
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
TILES_DIR = OUT / "mosaic_tiles_fhd"
TILES_DIR.mkdir(exist_ok=True)
LOGO = OUT / "gymaxis_logo.png"
MASTER = OUT / "mosaic_master_fhd.png"
MODEL = "gemini-3-pro-image-preview"  # Pro = sharper output

PROMPT = """
Design a single SQUARE 3x3 INSTAGRAM GRID mosaic, 1:1 aspect, intended to be
viewed at very high resolution (Full-HD per tile). The final image is one
large canvas divided by THIN HAIRLINE BLACK GRIDLINES into nine equal
square tiles. The mosaic is for the SaaS brand GYMAXIS. Use the supplied
reference logo verbatim - do NOT invent an alternate logo.

GLOBAL VISUAL DNA (must be consistent across every tile):
- Background: pure white (#FFFFFF) on every tile.
- Brand colour family: vibrant blue #2563EB transitioning to deep indigo
  #1E3A8A and a hint of royal purple #6F42C1 - exactly matching the supplied
  logo's gradient.
- Decorative motif: flowing thin curved line patterns and dotted halftone
  wave patterns in the brand gradient. These waves and dots MUST flow
  CONTINUOUSLY across tile boundaries so the 3x3 reads as one unified piece
  when viewed as a profile grid. A wave that exits the right edge of tile 1
  must enter the left edge of tile 2 at the same vertical position.
- Typography: bold geometric sans-serif (Proxima Nova / Maax Rounded feel),
  uppercase, tight tracking. Sub-copy in lighter weight, small. Render text
  CRISP and sharp, full-resolution kerning.
- Iconography: clean monoline outline icons in the brand gradient, ~3px
  stroke weight relative to a 1024px-wide tile. No filled shapes.
- No photographs, no 3D renders, no emoji, no clip-art.

EXACT TILE LAYOUT (numbered top-left to bottom-right, row-major):

TILE 1 (top-left):
  Headline left-aligned: "SMARTER" in solid black, then "FITNESS." in gradient blue.
  Sub-line: "Smarter operations. Stronger business." in 60% gray.
  Bottom-half: a sweep of dotted halftone waves arcing from lower-left toward
  the right edge, exiting cleanly so they continue into tile 2.

TILE 2 (top-center):
  Centered top: a clean monoline dumbbell icon in the brand gradient.
  Headline beneath: "STRONGER" in black, "BUSINESS." in gradient blue.
  Sub-line: "Everything you need to run, grow and scale." in 60% gray.
  Mid-tile: dotted halftone waves continuing in from tile 1 and exiting
  into tile 3.

TILE 3 (top-right):
  Right side dominated by a fan of thin gradient curved lines radiating from
  the right edge - they MUST visually continue downward into tile 6.
  Left side: three short icon+label rows stacked vertically:
    - people-icon  "MEMBERS FIRST"
    - upward-trend-arrow icon  "DATA DRIVEN"
    - shield-with-plus icon  "BUILT FOR FITNESS"
  All icon strokes in brand gradient, labels in solid black uppercase.

TILE 4 (middle-left):
  Headline left-aligned, three lines stacked tightly:
    "ONE PLATFORM." (black)
    "EVERYTHING" (black)
    "CONNECTED." (gradient blue)
  Lower portion: a soft cluster of thin curved gradient waves entering from
  the bottom edge (continuing into tile 7).

TILE 5 (CENTER - the hero tile):
  PURE WHITE TILE. Centered: the GymAxis "GA" mark from the supplied logo,
  rendered LARGE (about 60% of tile width), in its native blue-to-purple
  gradient. Nothing else on this tile - no text, no waves, no icons. This is
  the visual anchor of the whole mosaic.

TILE 6 (middle-right):
  Right side: continuation of the gradient line-fan from tile 3, sweeping
  downward and exiting into tile 9.
  Left side: three short icon+label rows stacked vertically:
    - target / crosshair icon  "FOCUS"
    - rocket icon  "GROWTH"
    - star icon  "PERFORMANCE"

TILE 7 (bottom-left):
  Headline: "YOUR AXIS." (black) on line 1, "YOUR ADVANTAGE." (gradient
  blue) on line 2.
  Sub-line three rows: "Powerful tools. / Smarter insights. / Better
  results." in 60% gray.
  Bottom edge: a band of dotted halftone waves continuing into tile 8.

TILE 8 (bottom-center):
  Six monoline outline icons arranged 3x2, with small uppercase labels under
  each (in this exact order top-row then bottom-row):
    Top: WRENCH "SERVICE", PEOPLE "CRM", CALENDAR "MEMBERSHIPS"
    Bot: MEGAPHONE "MARKETING", PEOPLE "STAFFING", PIE-CHART "REPORTING"
  Bottom edge: dotted halftone band continuing in from tile 7 and out to
  tile 9.

TILE 9 (bottom-right):
  Centered: the supplied GymAxis FULL logo lockup = the GA gradient mark on
  the left, the wordmark "GYMAXIS" with the barbell-A in solid black on the
  right.
  Below the lockup: the tagline "SMARTER FITNESS. STRONGER BUSINESS." in
  light gray uppercase, separated by small blue dots.
  Background: thin gradient curved lines flowing in from the top-right corner
  (continuing the fan from tile 6) and the bottom-left corner (continuing
  the dotted band from tile 8) - the two motifs converge gracefully behind
  the logo lockup.

CRITICAL CONSISTENCY & QUALITY RULES:
- Output the largest possible square canvas the model supports. High DPI,
  print-ready quality. Anti-aliased curves, crisp edges on every typeface
  glyph, vector-clean icon strokes.
- Every wave/line/dot pattern that exits one tile edge MUST continue at the
  same position and angle into the adjacent tile.
- Gridlines between tiles are HAIRLINE thin (1-2 px), pure black, perfectly
  straight, dividing the canvas into exact thirds horizontally and vertically.
- Generous editorial whitespace - no clutter.
- The supplied logo is the source of truth for the GA mark and the full
  GYMAXIS lockup. Do not stylise, recolour, or simplify it.
""".strip()

TILE_PX = 1920          # FHD per tile
MASTER_TARGET_PX = TILE_PX * 3  # 5760


def upscale_with_sharpen(img: Image.Image, target_px: int) -> Image.Image:
    """LANCZOS upscale + mild unsharp mask so resized type stays crisp."""
    if img.size[0] != img.size[1]:
        # centre-crop to square
        side = min(img.size)
        left = (img.size[0] - side) // 2
        top = (img.size[1] - side) // 2
        img = img.crop((left, top, left + side, top + side))
    if img.size[0] < target_px:
        img = img.resize((target_px, target_px), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=2))
    elif img.size[0] > target_px:
        img = img.resize((target_px, target_px), Image.LANCZOS)
    return img


async def main() -> None:
    if not LOGO.exists():
        raise SystemExit(f"missing logo at {LOGO}")
    logo_b64 = base64.b64encode(LOGO.read_bytes()).decode("utf-8")

    print(f"[start] generating master mosaic with {MODEL}...", flush=True)
    chat = LlmChat(
        api_key=os.getenv("EMERGENT_LLM_KEY"),
        session_id=f"gymaxis-mosaic-fhd-{int(time.time())}",
        system_message="You are a senior brand designer producing a print-quality cohesive 9-tile Instagram grid mosaic for GymAxis.",
    )
    chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
    msg = UserMessage(text=PROMPT, file_contents=[ImageContent(logo_b64)])
    text, images = await chat.send_message_multimodal_response(msg)

    if not images:
        print(f"[fail] no images returned. text={text[:300]}")
        return

    raw_bytes = base64.b64decode(images[0]["data"])
    raw_path = OUT / "mosaic_master_fhd_raw.png"
    raw_path.write_bytes(raw_bytes)
    raw_img = Image.open(raw_path).convert("RGB")
    print(f"[ok] raw master from model: {raw_img.size} ({raw_path.stat().st_size // 1024} KB)")

    # upscale to 5760x5760 if smaller
    master_img = upscale_with_sharpen(raw_img, MASTER_TARGET_PX)
    master_img.save(MASTER, "PNG", optimize=True)
    print(f"[ok] FHD master saved: {MASTER.name} {master_img.size} ({MASTER.stat().st_size // 1024} KB)")

    # slice into 1920x1920 tiles
    w, h = master_img.size
    tile_w = w // 3
    tile_h = h // 3
    saved = []
    for row in range(3):
        for col in range(3):
            idx = row * 3 + col + 1
            box = (col * tile_w, row * tile_h, (col + 1) * tile_w, (row + 1) * tile_h)
            tile = master_img.crop(box)
            if tile.size != (TILE_PX, TILE_PX):
                tile = tile.resize((TILE_PX, TILE_PX), Image.LANCZOS)
            out = TILES_DIR / f"tile_{idx:02d}.png"
            tile.save(out, "PNG", optimize=True)
            saved.append((out.name, out.stat().st_size // 1024))
    print(f"[ok] sliced into {len(saved)} FHD tiles -> {TILES_DIR}")
    for name, kb in saved:
        print(f"     {name} ({kb} KB)")


if __name__ == "__main__":
    asyncio.run(main())
