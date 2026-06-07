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
APEX=login("owner@apexfitness.group","ApexDemo2026!")
try:
    APEX_CRM=login("owner@apexfitness.group","ApexDemo2026!",crm=True); print("crm token ok")
except Exception as e:
    APEX_CRM=None; print("crm login failed:",str(e)[:80])
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--no-sandbox"]); ctx=await b.new_context(viewport={"width":1500,"height":950},device_scale_factor=2)
        page=await ctx.new_page(); await page.goto(BACKEND+"/",wait_until="domcontentloaded")
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["token",APEX])
        if APEX_CRM: await page.evaluate("([k,v])=>localStorage.setItem(k,v)",["crm_token",APEX_CRM])
        await page.goto(BACKEND+"/crm",wait_until="networkidle",timeout=45000); await page.wait_for_timeout(4000)
        await page.screenshot(path="/app/sales/shots/raw/apex_crm_landing.png"); print("OK landing url=",page.url)
        for txt in ["Pipeline","Deals","Leads"]:
            try:
                await page.get_by_text(txt,exact=True).first.click(timeout=4000); await page.wait_for_timeout(3000)
                await page.screenshot(path=f"/app/sales/shots/raw/apex_crm_{txt.lower()}.png"); print("OK",txt)
            except Exception as e: print("fail",txt,str(e)[:50])
        await b.close()
asyncio.run(main())
