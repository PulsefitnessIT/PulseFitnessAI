import asyncio, json, urllib.request
from playwright.async_api import async_playwright
BASE=open("/app/frontend/.env").read()
BACKEND=[l.split("=",1)[1].strip() for l in BASE.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0]
BENV=open("/app/backend/.env").read()
BYPASS=[l.split("=",1)[1].strip() for l in BENV.splitlines() if l.startswith("RATE_LIMIT_BYPASS_SECRET")][0]
def login(e,p,crm=False):
    path="/api/crm/auth/login" if crm else "/api/auth/login"
    d=json.dumps({"email":e,"password":p}).encode()
    r=urllib.request.Request(BACKEND+path,data=d,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0","X-RateLimit-Bypass":BYPASS})
    return json.load(urllib.request.urlopen(r))["token"]
APEX=login("owner@apexfitness.group","ApexDemo2026!"); APEX_CRM=login("owner@apexfitness.group","ApexDemo2026!",crm=True)
JACK=login("jack.ottey@thirdspace.london","Test123!")
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--no-sandbox"])
        ctx=await b.new_context(viewport={"width":1400,"height":900},device_scale_factor=2)
        page=await ctx.new_page(); await page.goto(BACKEND+"/",wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",APEX])
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["crm_token",APEX_CRM])
        await page.goto(BACKEND+"/crm",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(3000)
        try: await page.get_by_text("Pipeline",exact=True).first.click(timeout=5000); await page.wait_for_timeout(3500)
        except Exception as e: print("pipeline nav fail",str(e)[:50])
        await page.screenshot(path="/app/sales/shots/raw/p1_pipeline.png"); print("OK pipeline")
        # Jack equipment mobile
        ctx2=await b.new_context(viewport={"width":390,"height":850},device_scale_factor=2)
        page2=await ctx2.new_page(); await page2.goto(BACKEND+"/",wait_until="domcontentloaded")
        await page2.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",JACK])
        await page2.goto(BACKEND+"/pulse",wait_until="networkidle",timeout=45000); await page2.wait_for_timeout(3500)
        clicked=False
        for sel in ['[data-testid="mobile-pill-equipment"]','[data-testid="lite-tab-equipment"]']:
            try:
                await page2.locator(sel).first.click(timeout=4000); await page2.wait_for_timeout(3500); clicked=True; print("clicked",sel); break
            except Exception: pass
        if not clicked:
            try: await page2.get_by_text("Equipment",exact=False).first.click(timeout=4000); await page2.wait_for_timeout(3500); print("clicked text")
            except Exception as e: print("eq fail",str(e)[:50])
        await page2.screenshot(path="/app/sales/shots/raw/p1_equipment_mobile.png"); print("OK equipment mobile")
        await b.close()
asyncio.run(main())
