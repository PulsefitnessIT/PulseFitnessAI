import asyncio
from playwright.async_api import async_playwright

HTML = "file:///app/sales/gymaxis_presentation.html"
OUT = "/app/frontend/public/downloads/GymAxis-AI-Presentation.pdf"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(HTML, wait_until="networkidle")
        # ensure all custom fonts are loaded before printing
        await page.evaluate("document.fonts.ready")
        await page.wait_for_timeout(1200)
        await page.pdf(
            path=OUT,
            width="1280px",
            height="720px",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        await browser.close()
        print("PDF written:", OUT)

asyncio.run(main())
