import json
BASE = "https://pulse-mod-portal--8r99ahlc.preview.emergentagent.com"
cb_audit = open('/app/tests/core_blue_audit.js').read()


async def cb_login(page, email, pw):
    await page.goto(BASE + "/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="gx-login-email"]', timeout=15000)
    try:
        await page.get_by_role("button", name="Decline").click(timeout=2000)
    except Exception:
        pass
    await page.fill('[data-testid="gx-login-email"]', email)
    await page.fill('[data-testid="gx-login-password"]', pw)
    await page.click('[data-testid="gx-login-submit"]')
    await page.wait_for_timeout(6000)
    print("after login url:", page.url)


async def cb_visit(page, path, theme="light", shot=None, n=15):
    await page.evaluate(f"localStorage.setItem('theme','{theme}')")
    await page.goto(BASE + path, wait_until="domcontentloaded")
    await page.wait_for_timeout(6000)
    for y in range(0, 6000, 1200):
        await page.evaluate(f"window.scrollTo(0,{y})"); await page.wait_for_timeout(120)
    await page.evaluate("window.scrollTo(0,0)")
    r = await page.evaluate(cb_audit)
    print(json.dumps({"path": path, "final": r['url'], "theme": r['theme'], "ok": r['ok'], "darkOnDark": r['darkCount'], "brightOnLight": r['brightCount']}))
    for x in r['darkBlueOnDark'][:n]: print("  DARKonDARK", json.dumps(x))
    for x in r['brightOnLight'][:n]: print("  BRIGHTonLIGHT", json.dumps(x))
    if shot:
        await page.screenshot(path=shot, quality=40, full_page=False)
    return r
