import asyncio, os
from playwright.async_api import async_playwright

TOKEN = open("/tmp/tok.txt").read().strip()
BASE = "https://multi-eng-booking.preview.emergentagent.com"
OUT = "/app/decks/shots/"
os.makedirs(OUT, exist_ok=True)

TABS = [
    ("overview",   "01_overview"),
    ("equipment",  "02_equipment"),
    ("issues",     "03_faults"),
    ("maintenance","04_checksheets"),
    ("documents",  "05_documents"),
    ("reports",    "06_reports"),
]

async def dismiss(page):
    for txt in ["Essential Only", "Accept All", "Later", "Reject", "Got it"]:
        try:
            b = page.get_by_role("button", name=txt)
            if await b.count() > 0:
                await b.first.click(timeout=1200); await page.wait_for_timeout(200)
        except Exception: pass
    try:
        await page.add_style_tag(content="[class*='cookie'],[class*='Cookie'],[class*='install'],[class*='Install'],[data-testid*='pwa']{display:none!important;}")
    except Exception: pass

async def close_welcome(page):
    try:
        btns = page.locator("button:has(svg.lucide-x)")
        if await btns.count() > 0:
            await btns.first.click(timeout=1000)
            await page.wait_for_timeout(300)
    except Exception: pass

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path="/root/bin/chromium",
                                    args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(viewport={"width":1512,"height":950}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=45000)
        await page.evaluate(f"localStorage.setItem('token', '{TOKEN}')")
        print("token set")
        for tab, name in TABS:
            try:
                await page.goto(f"{BASE}/dashboard?tab={tab}", wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(2600)
                await dismiss(page)
                await close_welcome(page)
                await page.wait_for_timeout(1000)
                await page.screenshot(path=f"{OUT}{name}.png", full_page=False)
                print("OK", name, page.url)
            except Exception as e:
                print("FAIL", name, str(e)[:150])
        # CAPEX sub-report
        try:
            await page.goto(f"{BASE}/dashboard?tab=reports", wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(2500); await dismiss(page); await close_welcome(page)
            await page.click('[data-testid="report-sub-capex"]', timeout=6000)
            await page.wait_for_timeout(2600)
            await page.screenshot(path=f"{OUT}07_capex.png", full_page=False)
            print("OK 07_capex")
        except Exception as e:
            print("FAIL capex", str(e)[:150])
        await b.close()

asyncio.run(main())
