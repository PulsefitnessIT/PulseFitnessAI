"""Generate the MODService Open Graph share image (1200x630).

IP-safe: text-only MOD branding (no Crown crest / no commercial pulsefitness.ai
wording). Matches the MOD Service Portal login aesthetic.
Run: python3 scripts/gen_mod_og.py
"""
import cairosvg
from PIL import Image
import io
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "brand", "og-cover-mod.jpg")

SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0A0C10"/>
      <stop offset="55%" stop-color="#0d1424"/>
      <stop offset="100%" stop-color="#0f1c3a"/>
    </linearGradient>
    <radialGradient id="glow" cx="18%" cy="20%" r="60%">
      <stop offset="0%" stop-color="#19CDFF" stop-opacity="0.16"/>
      <stop offset="100%" stop-color="#19CDFF" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#glow)"/>
  <rect x="0" y="0" width="1200" height="8" fill="#19CDFF"/>

  <!-- top label -->
  <text x="80" y="108" fill="#93a4c4" font-family="Arial, Helvetica, sans-serif"
        font-size="26" font-weight="700" letter-spacing="7">MINISTRY OF DEFENCE</text>

  <!-- title -->
  <text x="78" y="238" fill="#ffffff" font-family="Arial, Helvetica, sans-serif"
        font-size="98" font-weight="800" letter-spacing="-1">MOD Service Portal</text>

  <!-- accent underline -->
  <rect x="82" y="266" width="150" height="7" rx="3.5" fill="#19CDFF"/>

  <!-- subtitle -->
  <text x="80" y="342" fill="#cdd7ea" font-family="Arial, Helvetica, sans-serif"
        font-size="36" font-weight="500">Secure fault reporting &amp; equipment registers</text>
  <text x="80" y="392" fill="#cdd7ea" font-family="Arial, Helvetica, sans-serif"
        font-size="36" font-weight="500">for every MOD gym site.</text>

  <!-- services row -->
  <text x="80" y="470" fill="#8ea2c4" font-family="Arial, Helvetica, sans-serif"
        font-size="28" font-weight="600" letter-spacing="1">British Army   ·   Royal Navy   ·   Royal Air Force</text>

  <!-- divider -->
  <rect x="80" y="512" width="1040" height="1.5" fill="#26324c"/>

  <!-- footer -->
  <text x="80" y="566" fill="#93a4c4" font-family="Arial, Helvetica, sans-serif"
        font-size="26" font-weight="600" letter-spacing="1">SERVICE PERSONNEL ONLY</text>
  <text x="1120" y="566" text-anchor="end" fill="#19CDFF" font-family="Arial, Helvetica, sans-serif"
        font-size="30" font-weight="700">modservice.pulsefitness.com</text>
</svg>"""

png_bytes = cairosvg.svg2png(bytestring=SVG.encode("utf-8"), output_width=1200, output_height=630)
img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
img.save(OUT, "JPEG", quality=88, optimize=True)
print("wrote", os.path.abspath(OUT), img.size)
