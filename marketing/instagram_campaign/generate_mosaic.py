"""
GymAxis — 9-tile Instagram MOSAIC generator.

Produces a single 3072x3072 master canvas (3x3 grid) where wave/dot patterns
flow seamlessly across tile borders and the GA mark sits in the center tile.
Then slices it into nine 1024x1024 tiles ready for sequential Instagram
posting (post order: tile9 -> tile1 so the profile grid reads top-left -> bot-right).
"""
import asyncio
import base64
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent  # noqa: E402

OUT = Path("/app/marketing/instagram_campaign")
TILES_DIR = OUT / "mosaic_tiles"
TILES_DIR.mkdir(exist_ok=True)
LOGO = OUT / "gymaxis_logo.png"
MASTER = OUT / "mosaic_master.png"
MODEL = "gemini-3.1-flash-image-preview"

PROMPT = """
Design a single SQUARE 3x3 INSTAGRAM GRID mosaic (3072x3072 effective). The
final image is one big canvas divided by THIN HAIRLINE BLACK GRIDLINES into
nine equal square tiles. The mosaic is for the SaaS brand GYMAXIS. Use the
supplied reference logo verbatim - do NOT invent an alternate logo.

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
  uppercase, tight tracking. Sub-copy in lighter weight, small.
- Iconography: minimal monoline outline icons in the brand gradient, no
  filled shapes, ~64px stroke weight relative to tile size.
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

CRITICAL CONSISTENCY RULES:
- Every wave/line/dot pattern that exits one tile edge MUST continue at the
  same position and angle into the adjacent tile.
- Gridlines between tiles are HAIRLINE thin (1-2 px equivalent), pure black,
  perfectly straight, dividing the canvas into exact thirds horizontally
  AND vertically.
- White space dominates - the design feels editorial and breathable, not
  cluttered.
- The supplied logo is the source of truth for the GA mark and the full
  GYMAXIS lockup. Do not stylise, recolour, or simplify it.
""".strip()


async def main() -> None:
    if not LOGO.exists():
        raise SystemExit(f"missing logo at {LOGO}")
    logo_b64 = base64.b64encode(LOGO.read_bytes()).decode("utf-8")

    print("[start] generating 9-tile master mosaic...", flush=True)
    chat = LlmChat(
        api_key=os.getenv("EMERGENT_LLM_KEY"),
        session_id=f"gymaxis-mosaic-{int(time.time())}",
        system_message="You are a senior brand designer producing a cohesive 9-tile Instagram grid mosaic for GymAxis.",
    )
    chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
    msg = UserMessage(text=PROMPT, file_contents=[ImageContent(logo_b64)])
    text, images = await chat.send_message_multimodal_response(msg)

    if not images:
        print(f"[fail] no images returned. text={text[:300]}")
        return

    MASTER.write_bytes(base64.b64decode(images[0]["data"]))
    print(f"[ok] master saved: {MASTER.name} ({MASTER.stat().st_size // 1024} KB)")

    # --- slice into 3x3 tiles ----------------------------------------------
    img = Image.open(MASTER).convert("RGB")
    w, h = img.size
    side = min(w, h)
    # crop to centered square if model returned non-square
    if w != h:
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        w = h = side

    tile_w = w // 3
    tile_h = h // 3
    saved = []
    for row in range(3):
        for col in range(3):
            idx = row * 3 + col + 1
            box = (col * tile_w, row * tile_h, (col + 1) * tile_w, (row + 1) * tile_h)
            tile = img.crop(box).resize((1080, 1080), Image.LANCZOS)
            out = TILES_DIR / f"tile_{idx:02d}.png"
            tile.save(out, "PNG", optimize=True)
            saved.append(out.name)
    print(f"[ok] sliced into {len(saved)} tiles -> {TILES_DIR}")
    for s in saved:
        print(f"     {s}")


if __name__ == "__main__":
    asyncio.run(main())
