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

async def click_text(page, txt):
    try:
        await page.get_by_text(txt, exact=True).first.click(timeout=5000)
        await page.wait_for_timeout(3000)
        return True
    except Exception as e:
        print("  clickfail", txt, str(e)[:60]); return False

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":1500,"height":950}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BACKEND+"/", wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)", ["token", APEX])
        await page.goto(BACKEND+"/dashboard", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3500)
        # main operations dashboard (health/overview)
        await click_text(page, "Dashboard")
        await page.screenshot(path="/app/sales/shots/raw/apex_ops_dash.png"); print("OK apex_ops_dash")
        # equipment
        await click_text(page, "Equipment")
        await page.screenshot(path="/app/sales/shots/raw/apex_equipment.png"); print("OK apex_equipment")
        # faults
        await click_text(page, "Faults")
        await page.screenshot(path="/app/sales/shots/raw/apex_faults.png"); print("OK apex_faults")
        # reports
        await click_text(page, "Reports")
        await page.screenshot(path="/app/sales/shots/raw/apex_reports.png"); print("OK apex_reports")
        # memberships
        await page.goto(BACKEND+"/memberships", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3500)
        await click_text(page, "Dashboard")
        await page.screenshot(path="/app/sales/shots/raw/apex_mbr_dash.png"); print("OK apex_mbr_dash")
        await click_text(page, "Members")
        await page.screenshot(path="/app/sales/shots/raw/apex_mbr_members.png"); print("OK apex_mbr_members")
        await b.close()

asyncio.run(main())
