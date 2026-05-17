/**
 * Iter 216h176 — Engineer service-worker warm-up.
 *
 * The service worker already caches a whitelist of read endpoints with
 * a network-first-with-fallback strategy. But until the engineer
 * actually opens each page, that cache is empty — so the first time
 * they lose signal on the road, the diary and job detail are blank.
 *
 * This helper warms up the SW cache with the engineer's "active week"
 * data the moment the queue page loads on Wi-Fi:
 *   1. Queue (already loaded — kept warm via re-fetch on auto-refresh).
 *   2. Diary for the next 7 days (one GET, multi-day range).
 *   3. Notifications inbox.
 *   4. /me + /organizations/current (chrome).
 *
 * On a flaky 4G connection in a basement gym the engineer can now
 * keep opening jobs from cache while the SW retries network in the
 * background.
 *
 * No-op when the service worker isn't installed (e.g. dev iframe,
 * in-app webview, or browsers that don't support it).
 */

const API_BASE = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

function todayIso() { return new Date().toISOString(); }
function inDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString();
}

/**
 * Issue a no-await fetch with credentials — the response itself is
 * discarded; we only care that the SW's `fetch` handler picks it up
 * and tucks the body in `gymaxis-api-v12`.
 */
function silentFetch(url, token) {
  if (!url) return;
  fetch(url, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'same-origin',
    cache: 'no-store',
  }).catch(() => { /* network may be offline — that's the whole point */ });
}

export function warmEngineerCache() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;
  if (!navigator.serviceWorker.controller) return;  // SW not yet active

  const token = (() => {
    try { return localStorage.getItem('token') || ''; } catch { return ''; }
  })();
  if (!token) return;

  // Throttle: warm at most once every 5 minutes. Auto-refresh fires
  // every 30s and we don't want to spam the network on a slow link.
  try {
    const last = Number(sessionStorage.getItem('gymaxis_engineer_warm_at') || 0);
    if (Date.now() - last < 5 * 60 * 1000) return;
    sessionStorage.setItem('gymaxis_engineer_warm_at', String(Date.now()));
  } catch { /* sessionStorage may be unavailable in private mode */ }

  const from = todayIso();
  const to = inDays(7);

  silentFetch(`${API_BASE}/svc/engineer/diary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`, token);
  silentFetch(`${API_BASE}/svc/engineer/notifications`, token);
  silentFetch(`${API_BASE}/auth/me`, token);
  silentFetch(`${API_BASE}/activation/me`, token);
}
