"""Generate Pulse Fitness brand favicon + OG social image (Core Blue / Soft Black)."""
import io
import cairosvg
from PIL import Image, ImageDraw, ImageFont

PUB = "/app/frontend/public"
CORE_BLUE = (25, 205, 255)
SOFT_BLACK = (27, 28, 29)
SILVER = (224, 224, 224)
SLATE = (110, 116, 118)

FAV_SRC = f"{PUB}/brand/favicon-source.svg"


def svg_to_png(svg_path=None, svg_bytes=None, width=None, height=None):
    png = cairosvg.svg2png(url=svg_path, bytestring=svg_bytes,
                           output_width=width, output_height=height)
    return Image.open(io.BytesIO(png)).convert("RGBA")


# ---- Favicons ----
for size in (48, 96, 192, 512):
    img = svg_to_png(svg_path=FAV_SRC, width=size, height=size)
    img.save(f"{PUB}/favicon-{size}.png")

# apple-touch-icon 180
svg_to_png(svg_path=FAV_SRC, width=180, height=180).save(f"{PUB}/apple-touch-icon.png")

# favicon.ico multi-size
ico = svg_to_png(svg_path=FAV_SRC, width=256, height=256)
ico.save(f"{PUB}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

print("Favicons done")

# ---- OG social image (1200x630) ----
W, H = 1200, 630
og = Image.new("RGBA", (W, H), SOFT_BLACK + (255,))
draw = ImageDraw.Draw(og)

# subtle Core Blue glow band top-left
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([-260, -320, 620, 360], fill=CORE_BLUE + (26,))
og = Image.alpha_composite(og, glow)
draw = ImageDraw.Draw(og)

# thin Core Blue rule near bottom
draw.rectangle([80, H - 96, 80 + 120, H - 90], fill=CORE_BLUE + (255,))

# Pulse logo (recolor reverse logo mark -> Core Blue, wordmark white)
with open(f"{PUB}/brand/pulse-logo-reverse.svg", "r") as f:
    logo_svg = f.read()
logo_svg = logo_svg.replace("#5dc5ed", "#19CDFF")
logo = svg_to_png(svg_bytes=logo_svg.encode(), width=520)
# vertically position logo
og.alpha_composite(logo, (80, 150))

# fonts
prox_bold = ImageFont.truetype(f"{PUB}/fonts/ProximaNova-Extrabold.otf", 58)
prox_semi = ImageFont.truetype(f"{PUB}/fonts/ProximaNova-Semibold.otf", 30)
prox_reg = ImageFont.truetype(f"{PUB}/fonts/ProximaNova-Regular.otf", 26)

draw = ImageDraw.Draw(og)
draw.text((80, 300), "Fitness Operations Platform", font=prox_bold, fill=(255, 255, 255))
draw.text((80, 380),
          "CRM · Memberships · Operations · Service Desk · Marketing",
          font=prox_semi, fill=SILVER)
draw.text((80, 428),
          "One connected platform. 3-day free trial, all modules unlocked.",
          font=prox_reg, fill=SLATE)
draw.text((80, H - 84), "pulsefitness.ai", font=prox_semi, fill=CORE_BLUE)

og.convert("RGB").save(f"{PUB}/brand/og-cover.jpg", quality=90)
og.convert("RGB").save(f"{PUB}/og/og-cover.jpg", quality=90)
print("OG image done")
