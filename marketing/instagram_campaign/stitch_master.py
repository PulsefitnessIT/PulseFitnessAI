"""Stitch the 9 native FHD tiles into a single 5760x5760 preview master."""
from pathlib import Path
from PIL import Image, ImageDraw

TILES_DIR = Path("/app/marketing/instagram_campaign/mosaic_tiles_fhd_native")
OUT = Path("/app/marketing/instagram_campaign/mosaic_master_fhd_native.png")
TILE_PX = 1920

canvas = Image.new("RGB", (TILE_PX * 3, TILE_PX * 3), "white")
for n in range(1, 10):
    row, col = (n - 1) // 3, (n - 1) % 3
    tile = Image.open(TILES_DIR / f"tile_{n:02d}.png").convert("RGB")
    if tile.size != (TILE_PX, TILE_PX):
        tile = tile.resize((TILE_PX, TILE_PX), Image.LANCZOS)
    canvas.paste(tile, (col * TILE_PX, row * TILE_PX))

# hairline gridlines
draw = ImageDraw.Draw(canvas)
for i in (1, 2):
    draw.line([(i * TILE_PX, 0), (i * TILE_PX, TILE_PX * 3)], fill="black", width=2)
    draw.line([(0, i * TILE_PX), (TILE_PX * 3, i * TILE_PX)], fill="black", width=2)

canvas.save(OUT, "PNG", optimize=True)
print(f"saved {OUT.name} {canvas.size} ({OUT.stat().st_size // 1024} KB)")
