/**
 * Playwright config — Mobile UI regression suite (Iter 216o-3, Feb 2026)
 *
 * Targets the running Frontend (REACT_APP_BACKEND_URL or localhost:3000)
 * at iPhone-13-Pro viewport (390 × 844) and asserts no horizontal
 * overflow on the pages listed in tests/mobile-regression/*.spec.js.
 *
 * Output:
 *   - Pretty list reporter to stdout
 *   - JSON report to /app/test_reports/mobile-regression-latest.json
 *     (parity with /app/test_reports/iteration_*.json convention)
 *
 * How to run:
 *   cd /app/frontend && yarn test:mobile-regression
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/mobile-regression',
  testMatch: /.*\.spec\.(js|ts)/,
  globalSetup: './tests/mobile-regression/global-setup.js',
  timeout: 45 * 1000,
  expect: { timeout: 8 * 1000 },
  fullyParallel: false,
  retries: 1,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: '/app/test_reports/mobile-regression-latest.json' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || process.env.REACT_APP_BACKEND_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10 * 1000,
    navigationTimeout: 25 * 1000,
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'iPhone 13 Pro',
      use: {
        ...devices['iPhone 13 Pro'],
        // iPhone-13-Pro device descriptor defaults to WebKit; override
        // to Chromium so we don't need to install WebKit binaries (the
        // viewport / userAgent / touch settings still apply).
        browserName: 'chromium',
        defaultBrowserType: 'chromium',
        // Reuse the auth state captured by global-setup so we don't
        // hammer the login endpoint on every test.
        storageState: '.playwright/state.json',
      },
    },
  ],
});
