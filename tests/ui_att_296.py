import json
async def login(page):
    await page.goto(page.url.split('/MODService')[0] + '/MODService')
    await page.wait_for_selector('[data-testid="mod-login-email"]', timeout=15000)
    await page.click('[data-testid="mod-login-email"]')
    await page.keyboard.type("test_295_siteuser@example.test")
    await page.locator('[data-testid="mod-login-form"] input[type="password"]').click()
    await page.keyboard.type("TestPhoto295#2026")
    await page.keyboard.press("Enter")
    await page.wait_for_url("**/pulse**", timeout=20000)
    await page.wait_for_timeout(2500)
    try:
        await page.get_by_text("Decline", exact=True).click(timeout=2000)
    except Exception:
        pass

async def open_fault(page, mobile):
    tab = '[data-testid="mobile-nav-faults"]' if mobile else '[data-testid="lite-tab-faults"]'
    await page.click(tab, force=True)
    await page.wait_for_selector('[data-testid="issue-card-TEST_295_i_photos"]', timeout=15000)
    await page.click('[data-testid="issue-title-TEST_295_i_photos"]', force=True)
    await page.wait_for_timeout(1500)
    if await page.locator('[data-testid^="issue-attachment-name-"]').count() == 0:
        await page.click('[data-testid="issue-card-TEST_295_i_photos"]', force=True)
        await page.wait_for_timeout(1500)
    await page.wait_for_selector('[data-testid^="issue-attachment-name-"]', timeout=15000)
    await page.wait_for_timeout(2500)

JS = """() => {
 const rows = Array.from(document.querySelectorAll('[data-testid^="issue-attachment-"]')).filter(e => /^issue-attachment-[^-]/.test(e.dataset.testid) && !/^issue-attachment-(thumb|name|open)-/.test(e.dataset.testid));
 const out = rows.map(r => {
   const id = r.dataset.testid.replace('issue-attachment-','');
   const q = s => r.querySelector(`[data-testid="issue-attachment-${s}-${id}"]`);
   const n = q('name'), t = q('thumb'), o = q('open');
   const meta = n ? n.nextElementSibling : null;
   const nr = n && n.getBoundingClientRect(), mr = meta && meta.getBoundingClientRect(), orr = o && o.getBoundingClientRect();
   return {id, text: n && n.textContent, nameW: nr && Math.round(nr.width), nameScrollW: n && n.scrollWidth, truncated: n && n.scrollWidth > n.clientWidth,
     metaText: meta && meta.textContent, metaBelow: !!(nr && mr && mr.top >= nr.bottom - 1), metaTrunc: meta && meta.scrollWidth > meta.clientWidth,
     thumbNW: t ? t.naturalWidth : null, thumbComplete: t ? t.complete : null,
     openGap: (orr && nr) ? Math.round(orr.left - Math.max(nr.right, mr ? mr.right : 0)) : null, openHref: o && o.href.slice(0,120)};
 });
 const h = Array.from(document.querySelectorAll('h3,h4,div,span,p')).map(e=>e.textContent).find(t=>/^\\s*Attachments\\s*\\(\\d+\\)/.test(t||''));
 return {rows: out, sw: document.documentElement.scrollWidth, iw: window.innerWidth, attHeader: h && h.trim().slice(0,30),
   notified: !!document.querySelector('[data-testid*="notified"]'), notifiedIds: Array.from(document.querySelectorAll('[data-testid*="notified"]')).map(e=>e.dataset.testid).slice(0,8),
   comments: Array.from(document.querySelectorAll('*')).filter(e=>e.children.length==0 && /TEST_ msg (edit|del)/.test(e.textContent)).length};
}"""

async def run(page, w, h, mobile):
    await page.set_viewport_size({"width": w, "height": h})
    await login(page)
    await open_fault(page, mobile)
    res = await page.evaluate(JS)
    print(f"=== {w}x{h} ===")
    print(json.dumps(res, indent=1))
    first = page.locator('[data-testid^="issue-attachment-name-"]').first
    await first.scroll_into_view_if_needed()
    await page.wait_for_timeout(500)
    await page.screenshot(path=f".screenshots/att_{w}.jpg", quality=40, full_page=False)
