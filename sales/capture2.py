import asyncio, json, os, urllib.request
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read()
BACKEND = [l.split("=",1)[1].strip() for l in BASE.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0]
BENV = open("/app/backend/.env").read()
BYPASS = [l.split("=",1)[1].strip() for l in BENV.splitlines() if l.startswith("RATE_LIMIT_BYPASS_SECRET")][0]
OUT = "/app/sales/shots/raw"
os.makedirs(OUT, exist_ok=True)

def login(email, pw, crm=False):
    path = "/api/crm/auth/login" if crm else "/api/auth/login"
    data = json.dumps({"email": email, "password": pw}).encode()
    req = urllib.request.Request(BACKEND + path, data=data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "X-RateLimit-Bypass": BYPASS})
    return json.load(urllib.request.urlopen(req))["token"]

ADMIN = login("admin@gymaxisai.com", "MasterAdmin123!")
ADMIN_CRM = login("admin@gymaxisai.com", "MasterAdmin123!", crm=True)
JACK = login("jack.ottey@thirdspace.london", "Test123!")
ENG = login("engineer.smoke@gymaxisai.com", "EngTest123!")

# (label, route, store, click_text)
TASKS = [
    ("ops_equipment", "/dashboard", {"token": JACK}, "Equipment"),
    ("ops_faults", "/dashboard", {"token": JACK}, "Faults"),
    ("ops_reports", "/dashboard", {"token": JACK}, "Reports"),
    ("crm_leads", "/crm", {"token": ADMIN, "crm_token": ADMIN_CRM}, "Leads"),
    ("crm_companies", "/crm", {"token": ADMIN, "crm_token": ADMIN_CRM}, "Companies"),
    ("eng_jobs2", "/svc/engineer/jobs", {"token": ENG}, None),
    ("eng_diary", "/svc/engineer/diary", {"token": ENG}, None),
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(BACKEND + "/", wait_until="domcontentloaded")
        for label, route, store, click in TASKS:
            try:
                await page.evaluate("localStorage.clear()")
                for k, v in store.items():
                    await page.evaluate("([k,v])=>localStorage.setItem(k,v)", [k, v])
                await page.goto(BACKEND + route, wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(2500)
                if click:
                    try:
                        await page.get_by_text(click, exact=True).first.click(timeout=6000)
                        await page.wait_for_timeout(3000)
                    except Exception as ce:
                        print("  clickfail", label, str(ce)[:80])
                await page.screenshot(path=f"{OUT}/{label}.png", full_page=False)
                print("OK", label)
            except Exception as e:
                print("ERR", label, str(e)[:140])
        await browser.close()

asyncio.run(main())
