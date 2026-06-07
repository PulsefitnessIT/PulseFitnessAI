import asyncio, json, urllib.request
from playwright.async_api import async_playwright
BASE=open("/app/frontend/.env").read()
BACKEND=[l.split("=",1)[1].strip() for l in BASE.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0]
BENV=open("/app/backend/.env").read()
BYPASS=[l.split("=",1)[1].strip() for l in BENV.splitlines() if l.startswith("RATE_LIMIT_BYPASS_SECRET")][0]
def login(e,p):
    d=json.dumps({"email":e,"password":p}).encode()
    r=urllib.request.Request(BACKEND+"/api/auth/login",data=d,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0","X-RateLimit-Bypass":BYPASS})
    return json.load(urllib.request.urlopen(r))["token"]
APEX=login("owner@apexfitness.group","ApexDemo2026!")
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--no-sandbox"]); ctx=await b.new_context(viewport={"width":1500,"height":1000},device_scale_factor=2)
        page=await ctx.new_page(); await page.goto(BACKEND+"/",wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",APEX])
        await page.goto(BACKEND+"/marketing?tab=campaigns",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(4000)
        # dismiss cookie banner if present
        for t in ["Accept all","Accept","Got it"]:
            try:
                await page.get_by_role("button",name=t).first.click(timeout=1500); break
            except Exception: pass
        # scroll to first campaign card
        try:
            await page.get_by_text("Win-back",exact=False).first.scroll_into_view_if_needed(timeout=5000)
            await page.wait_for_timeout(1500)
            await page.evaluate("window.scrollBy(0,-120)")
        except Exception as e:
            print("scroll fail",str(e)[:60]); await page.evaluate("window.scrollBy(0,650)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="/app/sales/shots/raw/apex_marketing.png"); print("OK marketing")
        await b.close()
asyncio.run(main())
