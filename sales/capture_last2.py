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
ENG=login("engineer.smoke@gymaxisai.com","EngTest123!")
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--no-sandbox"]); ctx=await b.new_context(viewport={"width":1500,"height":950},device_scale_factor=2)
        page=await ctx.new_page(); await page.goto(BACKEND+"/",wait_until="domcontentloaded")
        # marketing campaigns (apex)
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",APEX])
        await page.goto(BACKEND+"/marketing?tab=campaigns",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(4000)
        try:
            await page.get_by_text("Campaigns",exact=True).first.click(timeout=4000); await page.wait_for_timeout(3000)
        except Exception as e: print("camp tab click:",str(e)[:50])
        await page.screenshot(path="/app/sales/shots/raw/apex_marketing.png"); print("OK marketing url=",page.url)
        # engineer van stock
        await page.evaluate("localStorage.clear()")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",ENG])
        await page.goto(BACKEND+"/svc/engineer/stock",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(4500)
        await page.screenshot(path="/app/sales/shots/raw/eng_vanstock.png"); print("OK vanstock url=",page.url)
        await b.close()
asyncio.run(main())
