import json
BASE = "https://pulse-mod-portal--8r99ahlc.preview.emergentagent.com"
audit = open('/app/tests/colour_audit.js').read()

def short(r, n=18):
    print(f"== {r['url']} low={r['lowCount']} off={r['offCount']}")
    for x in r['low'][:n]: print("  LOW", json.dumps(x))
    for x in r['off'][:n]: print("  OFF", json.dumps(x))

async def login(page, email, pw):
    await page.goto(BASE + "/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="gx-login-email"]', timeout=15000)
    try:
        await page.get_by_role("button", name="Decline").click(timeout=2000)
    except Exception:
        pass
    await page.fill('[data-testid="gx-login-email"]', email)
    await page.fill('[data-testid="gx-login-password"]', pw)
    await page.click('[data-testid="gx-login-submit"]')
    await page.wait_for_timeout(5000)
    print("after login url:", page.url)
