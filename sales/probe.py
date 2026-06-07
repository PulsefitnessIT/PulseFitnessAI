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

JACK = login("jack.ottey@thirdspace.london", "Test123!")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1500, "height": 950})
        page = await ctx.new_page()
        await page.goto(BACKEND + "/", wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)", ["token", JACK])
        await page.goto(BACKEND + "/dashboard", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2500)
        await page.get_by_text("Equipment", exact=True).first.click(timeout=6000)
        await page.wait_for_timeout(3000)
        # find any text node containing 'Pulse'
        pulse = await page.evaluate("""() => {
            const out=[]; const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
            let n; while(n=w.nextNode()){ if(/pulse/i.test(n.nodeValue)){ out.push(n.nodeValue.trim().slice(0,60)); } }
            return out.slice(0,20);
        }""")
        print("PULSE TEXT NODES:", json.dumps(pulse))
        # list data-testids
        tids = await page.evaluate("""() => Array.from(document.querySelectorAll('[data-testid]')).map(e=>e.getAttribute('data-testid')).slice(0,60)""")
        print("TESTIDS:", json.dumps(tids))
        # tables
        ntables = await page.evaluate("() => document.querySelectorAll('table').length")
        print("TABLES:", ntables)
        await browser.close()

asyncio.run(main())
