"""
Per-tile FHD regenerator.

Generates each of the 9 mosaic tiles independently at 1024x1024 native
resolution using gemini-3-pro-image-preview, with the master mosaic and the
GymAxis logo passed as reference images so layout/branding stay consistent.
Each tile is then upscaled from 1024 -> 1920 (1.875x, gentle LANCZOS +
UnsharpMask) so the final per-tile detail is true FHD.
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
TILES_DIR.mkdir(exist_ok=True)
LOGO = OUT / "gymaxis_logo.png"
MASTER_REF = OUT / "mosaic_master_fhd_raw.png"   # the 1024x1024 native master
MODEL = "gemini-3-pro-image-preview"
TILE_PX = 1920

POSITIONS = {
    1: ("top-left", "Bottom edge dotted halftone wave fading toward right edge."),
    2: ("top-centre", "Wave continuing from left edge across to right edge."),
    3: ("top-right", "Right edge: gradient curved-line fan radiating from far right."),
    4: ("middle-left", "Bottom edge: cluster of curved gradient waves entering from below."),
    5: ("centre", "Pure white tile: only the GA gradient mark, large, centred."),
    6: ("middle-right", "Right edge: gradient line-fan continuing the one from tile 3."),
    7: ("bottom-left", "Bottom edge: dotted halftone band running along the bottom."),
    8: ("bottom-centre", "Bottom edge: dotted halftone band continuing from tile 7."),
    9: ("bottom-right", "Top-right corner gradient line-fan + bottom-left dotted band converging behind logo."),
}

TILE_BRIEFS = {
    1: ('SMARTER FITNESS',
        'Headline left-aligned: "SMARTER" in solid black, then "FITNESS." in '
        'gradient blue. Sub-line: "Smarter operations. Stronger business." in '
        '60% gray.'),
    2: ('STRONGER BUSINESS',
        'Centred top: clean monoline dumbbell icon in brand gradient. '
        'Headline beneath: "STRONGER" in black, "BUSINESS." in gradient blue. '
        'Sub-line: "Everything you need to run, grow and scale." in 60% gray.'),
    3: ('MEMBERS / DATA / BUILT',
        'Three icon+label rows stacked vertically on the left side: '
        'people-icon "MEMBERS FIRST", upward-trend-arrow "DATA DRIVEN", '
        'shield-with-plus "BUILT FOR FITNESS". Right side has the gradient '
        'line-fan radiating from the far right edge.'),
    4: ('ONE PLATFORM EVERYTHING CONNECTED',
        'Headline left-aligned, three lines stacked tightly: "ONE PLATFORM." '
        '(black), "EVERYTHING" (black), "CONNECTED." (gradient blue).'),
    5: ('GA HERO',
        'Pure white tile. Centred: the GymAxis "GA" mark from the supplied '
        'logo, rendered LARGE (about 60% of tile width), in its native '
        'blue-to-purple gradient. Absolutely nothing else - no text, no '
        'waves, no icons, no border decoration. Vector-clean rendering.'),
    6: ('FOCUS GROWTH PERFORMANCE',
        'Three icon+label rows stacked vertically on the left side: target/'
        'crosshair "FOCUS", rocket "GROWTH", star "PERFORMANCE". Right side '
        'has the gradient line-fan continuing from tile 3.'),
    7: ('YOUR AXIS YOUR ADVANTAGE',
        'Headline: "YOUR AXIS." (black) on line 1, "YOUR ADVANTAGE." '
        '(gradient blue) on line 2. Three sub-lines below: "Powerful tools." '
        '"Smarter insights." "Better results." in 60% gray.'),
    8: ('SIX SERVICE ICONS',
        'Six monoline outline icons arranged 3x2 with small uppercase '
        'labels: top row WRENCH "SERVICE", PEOPLE "CRM", CALENDAR '
        '"MEMBERSHIPS"; bottom row MEGAPHONE "MARKETING", PEOPLE "STAFFING", '
        'PIE-CHART "REPORTING". All icon strokes in brand gradient, labels '
        'in solid black uppercase.'),
    9: ('GYMAXIS FULL LOCKUP',
        'Centred: the supplied GymAxis FULL logo lockup (GA gradient mark + '
        '"GYMAXIS" wordmark with the barbell-A in solid black). Below: the '
        'tagline "SMARTER FITNESS. STRONGER BUSINESS." in light gray '
        'uppercase, separated by small blue dots.'),
}

PROMPT_TEMPLATE = """
You are producing tile {n} of a 9-tile Instagram mosaic for the SaaS brand
GYMAXIS. The two reference images supplied are: (1) the GymAxis logo (use
verbatim, do not invent an alternate logo); (2) the full mosaic master so
you understand how this tile sits in the overall composition.

OUTPUT: a SINGLE 1:1 SQUARE TILE at the highest fidelity the model supports.
This tile occupies the {position} position of the 3x3 grid.

MUST-HAVE VISUAL DNA (consistent with the master):
- Background: pure white #FFFFFF.
- Brand colours: vibrant blue #2563EB transitioning to deep indigo #1E3A8A
  with a hint of royal purple #6F42C1 (matches the supplied logo gradient).
- Decorative motif on the relevant tile edges so it visually connects to
  neighbouring tiles: {edge_motif}
- Typography: bold geometric sans-serif (Proxima Nova / Maax Rounded feel),
  uppercase, tight tracking. Sub-copy lighter weight, small. CRISP, sharp,
  fully anti-aliased glyphs - no soft or blurry text.
- Iconography: clean monoline outline icons in brand gradient, ~3px stroke
  weight. No filled shapes.
- No photographs, no 3D renders, no emoji, no clip-art.
- Generous whitespace, editorial composition.

THIS TILE'S CONTENT BRIEF: {brief}

Do NOT include any black gridlines or borders within the tile - the tile is
its own square. Do NOT include the GymAxis wordmark or tagline anywhere
unless this tile is explicitly tile 9 (the full lockup tile).
""".strip()


async def generate_tile(n: int, refs: list[str]) -> tuple[int, bool, str]:
    out_path = TILES_DIR / f"tile_{n:02d}.png"
    position, edge_motif = POSITIONS[n]
    title, brief = TILE_BRIEFS[n]
    prompt = PROMPT_TEMPLATE.format(
        n=n, position=position, edge_motif=edge_motif, brief=brief
    )
    try:
        chat = LlmChat(
            api_key=os.getenv("EMERGENT_LLM_KEY"),
            session_id=f"gymaxis-tile-{n}-{int(time.time())}",
            system_message="You are a senior brand designer rendering a print-quality square tile for a 9-tile Instagram mosaic for GymAxis.",
        )
        chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
        msg = UserMessage(
            text=prompt,
            file_contents=[ImageContent(b) for b in refs],
        )
        text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            return n, False, f"no images. text={text[:160]}"
        raw = base64.b64decode(images[0]["data"])
        tmp_path = TILES_DIR / f"tile_{n:02d}_raw.png"
        tmp_path.write_bytes(raw)
        img = Image.open(tmp_path).convert("RGB")
        # square crop if model returned non-square
        if img.size[0] != img.size[1]:
            side = min(img.size)
            left = (img.size[0] - side) // 2
            top = (img.size[1] - side) // 2
            img = img.crop((left, top, left + side, top + side))
        if img.size[0] != TILE_PX:
            img = img.resize((TILE_PX, TILE_PX), Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=2))
        img.save(out_path, "PNG", optimize=True)
        tmp_path.unlink(missing_ok=True)
        return n, True, f"{out_path.name} ({out_path.stat().st_size // 1024} KB) - {title}"
    except Exception as exc:  # noqa: BLE001
        return n, False, f"{title}: {exc}"


async def main() -> None:
    if not LOGO.exists() or not MASTER_REF.exists():
        raise SystemExit("missing logo or master reference")
    logo_b64 = base64.b64encode(LOGO.read_bytes()).decode("utf-8")
    master_b64 = base64.b64encode(MASTER_REF.read_bytes()).decode("utf-8")
    refs = [logo_b64, master_b64]

    print(f"[start] generating {len(TILE_BRIEFS)} tiles in parallel via {MODEL}...", flush=True)
    results = await asyncio.gather(*[generate_tile(n, refs) for n in TILE_BRIEFS])
    print("\n[results]")
    ok = 0
    for n, success, msg in sorted(results):
        flag = "OK " if success else "FAIL"
        print(f"  {flag} tile_{n:02d}: {msg}")
        if success:
            ok += 1
    print(f"\n[done] {ok}/{len(TILE_BRIEFS)} succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
