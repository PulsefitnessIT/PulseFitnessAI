"""Render the GymAxis MOD presentation HTML to A4-landscape PDF.

Usage:
    python3 /app/marketing/mod-presentation/render_pdf.py

Output:
    /app/marketing/mod-presentation/GymAxis_MOD_Briefing.pdf

Why Playwright (not weasyprint / wkhtmltopdf):
    The deck uses CSS features (background-clip: text, mask-image,
    Google Fonts, modern gradients) that only a modern Chromium-based
    renderer handles cleanly. Playwright is already installed in this
    environment and ships with Chromium.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "index.html"
OUT = ROOT / "GymAxis_MOD_Briefing.pdf"


async def render() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # file:// URL so relative screenshot paths resolve
        await page.goto(HTML.as_uri(), wait_until="networkidle")

        # Give web fonts a beat to settle before snapshot
        await page.wait_for_timeout(1500)

        await page.pdf(
            path=str(OUT),
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        await browser.close()

    size_kb = OUT.stat().st_size / 1024
    print(f"OK  · {OUT}  ({size_kb:,.0f} KB)")


if __name__ == "__main__":
    asyncio.run(render())
