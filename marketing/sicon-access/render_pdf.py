"""Render the Sicon WebAPI access request to a 2-page A4 portrait PDF.

Usage:
    python3 /app/marketing/sicon-access/render_pdf.py

Output:
    /app/marketing/sicon-access/GymAxis_Sicon_Access_Request.pdf
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "index.html"
OUT = ROOT / "GymAxis_Sicon_Access_Request.pdf"


async def render() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(HTML.as_uri(), wait_until="networkidle")
        await page.wait_for_timeout(1200)
        await page.pdf(
            path=str(OUT),
            format="A4",
            landscape=False,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        await browser.close()
    size_kb = OUT.stat().st_size / 1024
    print(f"OK  · {OUT}  ({size_kb:,.0f} KB)")


if __name__ == "__main__":
    asyncio.run(render())
