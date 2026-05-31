/**
 * Playwright global setup — Iter 220ea rewrite (Feb 2026).
 *
 * Logs in via the backend API (more reliable than UI-driven login on
 * the preview environment, where the cookie banner / lazy login
 * bundle hydration occasionally beat the submit click) and seeds the
 * resulting JWT into localStorage so every spec starts authenticated.
 *
 * The captured storage state is written to `.playwright/state.json`
 * and re-used by each test via the `storageState` config option, so
 * we don't hammer the login endpoint (which is rate-limited).
 *
 * Why API-driven and not UI-driven?
 *   The previous UI flow opened /login, filled inputs, clicked
 *   submit, and waited for the URL to flip to /master-admin. On the
 *   preview environment this race-conditions:
 *     - Cookie banner mounts AFTER the inputs hydrate, intercepting
 *       the submit click.
 *     - Lazy chunks for /master-admin can take > 25s to download on
 *       a cold preview, blowing past waitForURL.
 *   The API path is one HTTP round-trip; we just inject the token
 *   the React app reads from localStorage and walk in already
 *   authenticated.
 */
import { chromium, request as pwRequest } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const ADMIN_EMAIL    = process.env.E2E_ADMIN_EMAIL    || 'admin@gymaxisai.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'MasterAdmin123!';

// Iter 220ea — resolve REACT_APP_BACKEND_URL from /app/frontend/.env
// when it isn't set in the shell. Playwright's runner doesn't pick
// up CRA's webpack-injected env, so without this fallback BASE_URL
// silently defaulted to localhost:3000 and every /api call 404'd.
function resolveBaseURL() {
  if (process.env.E2E_BASE_URL)            return process.env.E2E_BASE_URL;
  if (process.env.REACT_APP_BACKEND_URL)   return process.env.REACT_APP_BACKEND_URL;
  try {
    const envPath = path.resolve('./.env');
    if (fs.existsSync(envPath)) {
      const m = fs.readFileSync(envPath, 'utf8').match(/^REACT_APP_BACKEND_URL=(.+)$/m);
      if (m?.[1]) return m[1].trim();
    }
  } catch { /* ignore */ }
  return 'http://localhost:3000';
}
const BASE_URL = resolveBaseURL();

const STATE_DIR  = path.resolve('./.playwright');
const STATE_PATH = path.join(STATE_DIR, 'state.json');

async function fetchAdminToken() {
  const api = await pwRequest.newContext({
    baseURL: BASE_URL, ignoreHTTPSErrors: true,
  });
  const res = await api.post('/api/auth/login', {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    timeout: 30_000,
  });
  if (!res.ok()) {
    throw new Error(
      `globalSetup: admin login failed (${res.status()}): ${await res.text()}`,
    );
  }
  const body = await res.json();
  if (!body?.token) throw new Error('globalSetup: login response missing token');
  await api.dispose();
  return body.token;
}

export default async function globalSetup() {
  fs.mkdirSync(STATE_DIR, { recursive: true });

  const token = await fetchAdminToken();

  // Persist the auth state into a Playwright storage-state file.
  // We need a real browser context to issue `localStorage.setItem`
  // and then dump the state — addInitScript guarantees the script
  // runs before any page bundle loads.
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  await ctx.addInitScript(([tok]) => {
    try {
      window.localStorage.setItem('token', tok);
      // Pop the cookie-consent acknowledgement so the banner
      // doesn't intercept clicks on subsequent specs.
      window.localStorage.setItem('cookie_consent_v1', 'essential');
    } catch { /* quota / SecurityError */ }
  }, [token]);
  const page = await ctx.newPage();
  // Touch the origin so the localStorage seed is committed under
  // the correct hostname; the page itself doesn't need to render.
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' }).catch(() => { /* offline-safe */ });
  await page.waitForTimeout(500);

  await ctx.storageState({ path: STATE_PATH });
  await browser.close();
}

export { STATE_PATH };
