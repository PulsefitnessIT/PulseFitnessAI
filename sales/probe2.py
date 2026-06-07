import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read()
BACKEND = [l.split("=",1)[1].strip() for l in BASE.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0]
BENV = open("/app/backend/.env").read()
BYPASS = [l.split("=",1)[1].strip() for l in BENV.splitlines() if l.startswith("RATE_LIMIT_BYPASS_SECRET")][0]

def login(email, pw):
    data = json.dumps({"email": email, "password": pw}).encode()
    req = urllib.request.Request(BACKEND + "/api/auth/login", data=data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "X-RateLimit-Bypass": BYPASS})
    return json.load(urllib.request.urlopen(req))["token"]

ADMIN = login("admin@gymaxisai.com", "MasterAdmin123!")

async def shot(page, tabtid, label):
    try:
        await page.locator(f'[data-testid="{tabtid}"]').first.click(timeout=6000)
        await page.wait_for_timeout(3500)
    except Exception as e:
        print("clickfail", label, str(e)[:80])
    await page.screenshot(path=f"/app/sales/shots/raw/full_{label}.png", full_page=False)
    print("OK", label)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":1500,"height":950})
        page = await ctx.new_page()
        await page.goto(BACKEND+"/", wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)", ["token", ADMIN])
        await page.goto(BACKEND+"/dashboard", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/app/sales/shots/raw/full_dashboard.png")
        await shot(page, "module-switcher-operations", "operations")
        # try clicking an equipment tab if present
        for tid in ["lite-tab-equipment","mobile-pill-equipment"]:
            try:
                await page.locator(f'[data-testid="{tid}"]').first.click(timeout=3000)
                await page.wait_for_timeout(2500); break
            except Exception: pass
        await page.screenshot(path="/app/sales/shots/raw/full_operations_equipment.png")
        print("OK operations_equipment")
        await b.close()

asyncio.run(main())
