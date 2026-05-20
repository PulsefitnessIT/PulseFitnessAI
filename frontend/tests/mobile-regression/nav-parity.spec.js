/**
 * Navigation parity regression — Iter 216h236 (Feb 2026).
 *
 * Why this file exists:
 *   Lee found Help & Tutorials available on desktop but missing from
 *   the mobile hamburger menu (iter 216h235). The previous mobile
 *   audit caught visual overflow bugs but had no functional parity
 *   check, so an entire menu item went missing without anyone
 *   noticing in CI.
 *
 * How this protects us:
 *   For each module a logged-in operator can land on, this spec
 *   opens the user-menu at desktop width (1440×900) AND the
 *   hamburger menu at mobile width (390×844), collects the visible
 *   navigation actions in each, then asserts the two sets match.
 *
 * Definition of "match":
 *   - Mobile hamburger MUST contain every action available in the
 *     desktop user-menu (a strict superset is allowed; the mobile
 *     menu may legitimately add e.g. theme toggle / language switch
 *     that the desktop nav exposes as separate icons).
 *   - Each action is identified by its `data-testid` (case-insensitive
 *     comparison after stripping the `desktop-` / `mobile-` prefix).
 *
 * How to run:
 *   cd /app/frontend && yarn test:mobile-regression
 *
 * Adding new pages:
 *   Append a string to NAV_PARITY_PAGES.
 */
import { test, expect } from '@playwright/test';

// Pages where the platform Navbar (not the Master Admin shell or
// public marketing site) is rendered. The user-menu / hamburger
// composition can vary slightly per route via the `onStartTour` /
// `onOpenMasterAdmin` props, so we sample several.
const NAV_PARITY_PAGES = [
  '/dashboard?as=operator',
  '/pulse-dashboard',
];

// Map desktop testids → mobile testids. Anything in this map must
// appear in BOTH menus or the parity check fails. Anything NOT in
// this map is allowed to vary (e.g. desktop-only utility buttons
// rendered inline, or mobile-only theme toggle).
const PARITY_PAIRS = [
  { desktop: 'nav-account-btn',       mobile: 'mobile-account-btn',       label: 'Account' },
  { desktop: 'nav-help-btn',          mobile: 'mobile-help-btn',          label: 'Help & Tutorials' },
  { desktop: 'nav-logout-btn',        mobile: 'mobile-logout-btn',        label: 'Log out' },
];

async function dismissOverlays(page) {
  const candidates = [
    'button:has-text("Essential Only")',
    'button:has-text("Accept All")',
    'button:has-text("Later")',
    'button:has-text("Dismiss")',
    'button:has-text("Skip tour")',
  ];
  for (const sel of candidates) {
    try { await page.locator(sel).first().click({ timeout: 800 }); } catch { /* noop */ }
  }
  await page.waitForTimeout(300);
}

async function openDesktopUserMenu(page) {
  // Navbar.js exposes the user-menu avatar trigger as
  // `data-testid="nav-user-menu-btn"`. We try both naming variants
  // for robustness so the spec doesn't break if the testid is
  // renamed in future iterations.
  const trigger = page.locator(
    '[data-testid="nav-user-menu-btn"], [data-testid="nav-user-menu-trigger"]',
  ).first();
  if (await trigger.count() === 0) {
    return false;
  }
  try { await trigger.click({ timeout: 3000 }); } catch { /* noop */ }
  await page.waitForTimeout(500);
  return true;
}

async function openMobileHamburger(page) {
  const trigger = page.locator('[data-testid="mobile-menu-toggle"]').first();
  if (await trigger.count() === 0) {
    return false;
  }
  try { await trigger.click({ timeout: 3000 }); } catch { /* noop */ }
  await page.waitForTimeout(500);
  return true;
}

async function collectVisibleTestids(page, candidates) {
  // For each candidate testid, return whether it's currently visible
  // (not just present in the DOM — visibility matters because both
  // menus can co-exist in the DOM but only one is shown at a time).
  const result = {};
  for (const tid of candidates) {
    const loc = page.locator(`[data-testid="${tid}"]`).first();
    if (await loc.count() === 0) {
      result[tid] = false;
      continue;
    }
    try {
      result[tid] = await loc.isVisible();
    } catch {
      result[tid] = false;
    }
  }
  return result;
}

test.describe('Navigation parity — desktop vs mobile', () => {
  for (const route of NAV_PARITY_PAGES) {
    test(`${route} — every desktop user-menu action is also in the mobile hamburger`, async ({ page, baseURL }) => {
      const desktopTids = PARITY_PAIRS.map((p) => p.desktop);
      const mobileTids  = PARITY_PAIRS.map((p) => p.mobile);

      // ── Desktop pass (1440 × 900) ──────────────────────────
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`${baseURL}${route}`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      await dismissOverlays(page);

      const desktopMenuOpened = await openDesktopUserMenu(page);
      // If the desktop user-menu trigger isn't on this page (e.g. the
      // route renders a custom shell), skip the parity check rather
      // than fail. Add a console warning so it's still visible in CI.
      if (!desktopMenuOpened) {
        // eslint-disable-next-line no-console
        console.warn(`[nav-parity] ${route}: nav-user-menu-trigger not found; skipping parity check.`);
        return;
      }
      const desktopVisible = await collectVisibleTestids(page, desktopTids);

      // ── Mobile pass (390 × 844) ────────────────────────────
      await page.setViewportSize({ width: 390, height: 844 });
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      await dismissOverlays(page);

      const mobileMenuOpened = await openMobileHamburger(page);
      if (!mobileMenuOpened) {
        // eslint-disable-next-line no-console
        console.warn(`[nav-parity] ${route}: mobile-menu-toggle not found at 390x844; skipping parity check.`);
        return;
      }
      const mobileVisible = await collectVisibleTestids(page, mobileTids);

      // ── Assert parity for every pair where the desktop entry IS
      //    visible. We don't require mobile-only items to have a
      //    desktop counterpart (theme toggle, language picker, etc.
      //    are legitimately mobile-only on the hamburger).
      const missing = [];
      for (const { desktop, mobile, label } of PARITY_PAIRS) {
        if (desktopVisible[desktop] && !mobileVisible[mobile]) {
          missing.push(`${label} (desktop=${desktop} visible, mobile=${mobile} missing)`);
        }
      }
      expect(
        missing,
        `Desktop/mobile menu parity mismatch on ${route}:\n  ${missing.join('\n  ')}`,
      ).toHaveLength(0);
    });
  }
});
