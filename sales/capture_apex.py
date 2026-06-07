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

APEX = login("owner@apexfitness.group", "ApexDemo2026!")
print("token ok")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":1500,"height":950}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BACKEND+"/", wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)", ["token", APEX])
        # dashboard (operations)
        await page.goto(BACKEND+"/dashboard", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path="/app/sales/shots/raw/apex_dashboard.png")
        print("OK apex_dashboard, url=", page.url)
        # try equipment tab
        for tid in ["lite-tab-equipment","mobile-pill-equipment"]:
            try:
                await page.locator(f'[data-testid="{tid}"]').first.click(timeout=4000)
                await page.wait_for_timeout(3000); print("clicked", tid); break
            except Exception: pass
        await page.screenshot(path="/app/sales/shots/raw/apex_equipment.png")
        # faults
        for tid in ["lite-tab-faults","mobile-pill-faults"]:
            try:
                await page.locator(f'[data-testid="{tid}"]').first.click(timeout=4000)
                await page.wait_for_timeout(3000); print("clicked", tid); break
            except Exception: pass
        await page.screenshot(path="/app/sales/shots/raw/apex_faults.png")
        # memberships
        await page.goto(BACKEND+"/memberships", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path="/app/sales/shots/raw/apex_memberships.png")
        print("OK apex_memberships, url=", page.url)
        await b.close()

asyncio.run(main())
