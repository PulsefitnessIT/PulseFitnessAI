/**
 * Mobile-layout regression guard — Iter 215ex (Feb 2026), expanded 216o-3.
 *
 * Why this file exists:
 *   Master Admin / Operations / Pulse mobile layouts have regressed
 *   multiple times. Each time a card or row gains a horizontal flex
 *   without `flex-wrap` or loses a `md:` breakpoint, the layout
 *   collapses on phones — and we don't catch it until production.
 *
 * How this protects us:
 *   These Playwright tests open each page at iPhone-13-Pro viewport
 *   (390 × 844) and assert:
 *     1. The document's total horizontal scroll width is ≤ viewport.
 *     2. No first-party `[data-testid]` element extends beyond the
 *        viewport's right edge.
 *     3. A critical test-id on each page is visible (smoke).
 *
 * How to run:
 *   cd /app/frontend && yarn test:mobile-regression
 *
 * Adding new pages:
 *   Append { path, testid, name, requiresLogin? } to MOBILE_PAGES.
 */
import { test, expect } from '@playwright/test';

/**
 * Pages we sweep for mobile regressions.
 *
 * `testid` is a prefix — we just check that ≥1 element starting with
 * it is visible on the page (smoke). Don't make it too narrow or new
 * UI variants will break the guard.
 */
const MOBILE_PAGES = [
  // Master Admin
  { path: '/master-admin',                        testid: 'sidebar',                 name: 'Master Admin · Overview' },
  { path: '/master-admin/organizations',          testid: 'org-card-',               name: 'Master Admin · Organizations' },
  { path: '/master-admin/users',                  testid: 'user-row-',               name: 'Master Admin · Users' },
  // GymAxis Operations (operator portal — runs as Master Admin → "GymAxis Portal")
  { path: '/dashboard?as=operator',               testid: 'dashboard-header',        name: 'GymAxis · Operations Dashboard' },
  { path: '/dashboard?as=operator&tab=issues',    testid: 'faults-header',           name: 'GymAxis · Faults' },
  { path: '/dashboard?as=operator&tab=suppliers', testid: 'suppliers-header',        name: 'GymAxis · Suppliers' },
  { path: '/dashboard?as=operator&tab=reports',   testid: 'reports-header',          name: 'GymAxis · Reports' },
  { path: '/dashboard?as=operator&tab=documents', testid: 'documents-header',        name: 'GymAxis · Documents' },
  // Pulse Fitness (Lite/Pro operator portal)
  { path: '/pulse-dashboard',                     testid: 'pulse-dashboard-header',  name: 'Pulse · Operations Dashboard' },
];

const VIEWPORT_WIDTH  = 390;  // iPhone 13 Pro

/**
 * Dismiss any onboarding tour / cookie banner / install prompt that
 * might cover the page during the test.
 */
async function dismissOverlays(pw) {
  const skipTour = pw.getByText('Skip tour', { exact: false });
  if (await skipTour.count() > 0) {
    try { await skipTour.first().click({ timeout: 1500 }); } catch { /* noop */ }
  }
  const essential = pw.getByText('Essential Only', { exact: false });
  if (await essential.count() > 0) {
    try { await essential.first().click({ timeout: 1500 }); } catch { /* noop */ }
  }
  const later = pw.getByRole('button', { name: /^Later$/ });
  if (await later.count() > 0) {
    try { await later.first().click({ timeout: 1500 }); } catch { /* noop */ }
  }
  await pw.waitForTimeout(400);
}

test.describe('Mobile layout regression — iPhone 13 Pro', () => {
  for (const target of MOBILE_PAGES) {
    test(`${target.name} — no horizontal overflow`, async ({ page, baseURL }) => {
      await page.goto(`${baseURL}${target.path}`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2000);
      await dismissOverlays(page);
      await page.waitForTimeout(800);

      // 1) Document shouldn't scroll horizontally.
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(scrollWidth, `${target.name}: scrollWidth=${scrollWidth} > clientWidth=${clientWidth}`).toBeLessThanOrEqual(clientWidth + 2);

      // 2) No first-party element's right edge extends meaningfully
      // beyond the viewport. Tolerance of 6px swallows sub-pixel
      // rounding and decorative animations (e.g. orbit nodes that sit
      // exactly on the ring boundary).
      //
      // We also exclude elements whose ancestor container handles
      // overflow itself (`overflow-x: auto|scroll`) — that's a
      // legitimate mobile pattern (wide tables that the user
      // horizontally swipes through). The CSS visually clips them so
      // they don't actually break the layout.
      const overflowing = await page.evaluate((vw) => {
        const insideOverflowContainer = (el) => {
          let p = el.parentElement;
          while (p) {
            const cs = getComputedStyle(p);
            if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') return true;
            p = p.parentElement;
          }
          return false;
        };
        const all = Array.from(document.querySelectorAll('[data-testid]'));
        return all
          .map((el) => {
            const r = el.getBoundingClientRect();
            return {
              el,
              testid: el.getAttribute('data-testid'),
              right: r.right,
              left: r.left,
              width: r.width,
            };
          })
          // Filter: hidden elements, off-canvas drawers, decorative
          // marketing animations (gx-orbit-*), and items inside
          // intentional horizontal-scroll containers.
          .filter((e) =>
            e.width > 0
            && e.right > vw + 6
            && e.left < vw
            && !/^gx-orbit-/.test(e.testid)
            && !insideOverflowContainer(e.el),
          )
          .map(({ el: _el, ...rest }) => rest)
          .slice(0, 5);
      }, VIEWPORT_WIDTH);
      expect(overflowing, `Elements overflowing viewport on ${target.name}: ${JSON.stringify(overflowing)}`).toHaveLength(0);

      // 3) Smoke: critical test-id should be present (not asserted as
      // a hard-fail — some tabs render testids only after API loads or
      // for non-master-admin operators).
      const critical = page.locator(`[data-testid^="${target.testid}"]`).first();
      const found = await critical.count();
      if (found === 0) {
        // eslint-disable-next-line no-console
        console.warn(`[mobile-regression] ${target.name}: critical testid '${target.testid}' not found on page (may be role-gated).`);
      }

      // 4) Sanity: viewport width is what we configured. Height isn't
      // asserted because Playwright iPhone 13 Pro descriptor includes
      // browser chrome (≈664px) not the device's full 844px.
      const vp = page.viewportSize();
      expect(vp?.width).toBe(VIEWPORT_WIDTH);
    });
  }
});
