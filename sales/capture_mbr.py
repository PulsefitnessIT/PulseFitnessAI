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
async def tap(page,tid):
    try:
        await page.locator(f'[data-testid="{tid}"]').first.click(timeout=5000); await page.wait_for_timeout(3000); return True
    except Exception as e: print("fail",tid,str(e)[:50]); return False
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--no-sandbox"]); ctx=await b.new_context(viewport={"width":1500,"height":950},device_scale_factor=2)
        page=await ctx.new_page(); await page.goto(BACKEND+"/",wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",APEX])
        await page.goto(BACKEND+"/memberships",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(3500)
        for tid,name in [("mbr-tab-members","apex_members"),("mbr-tab-plans","apex_plans"),("mbr-tab-schedule","apex_schedule"),("mbr-tab-analytics","apex_mbr_analytics")]:
            await tap(page,tid)
            await page.screenshot(path=f"/app/sales/shots/raw/{name}.png"); print("OK",name)
        await b.close()
asyncio.run(main())
