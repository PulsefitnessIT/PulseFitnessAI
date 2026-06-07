import asyncio
from playwright.async_api import async_playwright

DECKS = [
    ("file:///app/sales/gymaxisai_operators.html",
     "/app/frontend/public/downloads/GymAxisAI-Operators-Presentation.pdf"),
    ("file:///app/sales/gymaxisai_engineers.html",
     "/app/frontend/public/downloads/GymAxisAI-Suppliers-Presentation.pdf"),
]

async def render(page, html, out):
    await page.goto(html, wait_until="networkidle")
    # ensure all custom fonts are loaded before printing
    await page.evaluate("document.fonts.ready")
    await page.wait_for_timeout(1200)
    await page.pdf(
        path=out,
        width="1280px",
        height="720px",
        print_background=True,
        prefer_css_page_size=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )
    print("PDF written:", out)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        for html, out in DECKS:
            await render(page, html, out)
        await browser.close()

asyncio.run(main())
