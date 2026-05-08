/**
 * Playwright global setup — logs in once as Master Admin and saves the
 * resulting storage state to .playwright/state.json. Each test reuses
 * this state via `storageState` so we don't hammer the login endpoint
 * (which is rate-limited).
 */
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const ADMIN_EMAIL    = process.env.E2E_ADMIN_EMAIL    || 'admin@gymaxisai.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'MasterAdmin123!';
const BASE_URL       = process.env.E2E_BASE_URL       || process.env.REACT_APP_BACKEND_URL || 'http://localhost:3000';

const STATE_DIR  = path.resolve('./.playwright');
const STATE_PATH = path.join(STATE_DIR, 'state.json');

export default async function globalSetup() {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();

  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  // Dismiss cookie banner (mobile/desktop both).
  const essential = page.getByRole('button', { name: /Essential Only|Accept All/i }).first();
  if (await essential.count() > 0) {
    try { await essential.click({ timeout: 2000 }); } catch { /* noop */ }
    await page.waitForTimeout(500);
  }

  const inputs = await page.locator('input').all();
  if (inputs.length < 2) {
    throw new Error(`globalSetup: expected ≥2 login inputs, found ${inputs.length}`);
  }
  await inputs[0].fill(ADMIN_EMAIL);
  await inputs[1].fill(ADMIN_PASSWORD);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL(/\/(master-admin|dashboard|pulse-dashboard)/, { timeout: 25000 });
  await page.waitForTimeout(1000);

  await ctx.storageState({ path: STATE_PATH });
  await browser.close();
}

export { STATE_PATH };
