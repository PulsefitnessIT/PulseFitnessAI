/**
 * GymAxis service worker — iter 215d9.
 *
 * Adds selective network-first-with-cache-fallback strategy for a
 * whitelist of read-only GET endpoints. When the device is offline
 * (or the request times out > 4s) we serve the last known good
 * response so operators can keep checking members, classes, equipment
 * and faults on patchy gym Wi-Fi instead of staring at a spinner.
 *
 * Mutating requests (POST/PUT/PATCH/DELETE) are never served from
 * cache. They simply fail with the browser's default offline error,
 * and the app layer is expected to surface a toast.
 */
const CACHE_NAME = 'gymaxis-v14';
const API_CACHE  = 'gymaxis-api-v14';
const STATIC_ASSETS = [
  '/',
  '/crm',
  '/service-desk',
  '/manifest.json',
  '/manifest-servicedesk.json',
  '/pulse-photos/carshalton-igym.webp',
  '/pulse-photos/strength-accessories.webp',
  '/brand/gymaxis-mark-tight.webp',
];

// Paths that must NEVER be served from cache — public token-based URLs
// that suppliers open from email links. Any stale cached fallback would
// break these (e.g. redirect to /login or serve the landing page).
const PUBLIC_TOKEN_PATHS = [
  '/supplier/case/',
  '/onboarding/',
  '/scan/',
  '/reset-password',
];

// API endpoints that benefit from offline fallback. Match as
// "path contains substring" — keeps the list readable and avoids
// over-aggressive caching of one-off admin endpoints.
const OFFLINE_API_PATTERNS = [
  '/api/equipment',
  '/api/issues',
  '/api/memberships/members',
  '/api/memberships/plans',
  '/api/memberships/classes',
  '/api/memberships/dashboard',
  '/api/memberships/timetable',
  '/api/memberships/instructors',
  '/api/me',
  '/api/auth/me',
  '/api/activation/me',
  '/api/organizations/current',
  // Iter 216h176 — Engineer mobile app offline whitelist. These keep
  // a field engineer productive on flaky 4G in basement gyms: the
  // active week of jobs, diary, dispatcher diary, notifications and
  // job detail all survive going offline.
  '/api/svc/engineer/queue',
  '/api/svc/engineer/diary',
  '/api/svc/engineer/notifications',
  '/api/svc/engineer/inbox',
  '/api/svc/cases',  // covers both list and /cases/{id}
  '/api/svc/dispatcher/diary',
  // Iter 275 — Service Desk PWA: keep the provider desk usable offline.
  '/api/service-desk',  // summary, provider-customers, audit (org-scoped)
  '/api/svc/scheduler',
  '/api/svc/engineers',
];

// How long a cached API response stays considered "fresh". After this
// we still serve it offline, but the UI may flag it as stale via the
// `x-gymaxis-cache` response header.
const API_MAX_AGE_MS = 1000 * 60 * 60 * 6; // 6 hours

// Hard cap so the cache never balloons — oldest entries are evicted.
// Iter 216h176 — Bumped from 60 → 200 to fit the engineer's full
// week of cases + diary + notifications. Each cached blob is small
// (≤30 KB) so 200 entries ≈ 6 MB on disk — well below quota.
const API_MAX_ENTRIES = 200;

function isPublicTokenUrl(url) {
  return PUBLIC_TOKEN_PATHS.some((p) => url.pathname.startsWith(p));
}

function isOfflineCacheableApi(url) {
  return OFFLINE_API_PATTERNS.some((p) => url.pathname.includes(p));
}

async function trimCache(cacheName, maxEntries) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length <= maxEntries) return;
    const overflow = keys.length - maxEntries;
    for (let i = 0; i < overflow; i += 1) {
      await cache.delete(keys[i]);
    }
  } catch (_e) {
    /* ignore — cache trimming is best-effort */
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only GET is cacheable.
  if (request.method !== 'GET') return;

  // Offline-cache API whitelist.
  if (request.url.includes('/api/')) {
    if (!isOfflineCacheableApi(url)) return; // skip other APIs entirely
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  // Always go straight to network for public token URLs.
  if (isPublicTokenUrl(url)) {
    event.respondWith(fetch(request));
    return;
  }

  // Navigations — network-first with static shell fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(async () => {
        // Prefer the matching app shell when offline (Service Desk first
        // for /service-desk routes), else the root SPA shell.
        if (url.pathname.startsWith('/service-desk')) {
          const desk = await caches.match('/service-desk');
          if (desk) return desk;
        }
        return (await caches.match('/')) || caches.match('/crm');
      })
    );
    return;
  }

  // JS/CSS — network-first so app updates land on the next reload.
  if (request.url.includes('.js') || request.url.includes('.css')) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => caches.match(request))
    );
    return;
  }

  // Everything else — cache-first (fonts, images).
  event.respondWith(
    caches.match(request).then((cached) => {
      return cached || fetch(request).then((response) => {
        if (response.ok && (request.url.includes('.woff') || request.url.includes('.webp') || request.url.includes('.otf'))) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});

/**
 * Network-first, cache-fallback handler for whitelisted GET API
 * requests. Streams the live response when online, tucks a copy in
 * the API cache (with a timestamp header), and serves from cache
 * transparently when offline. Adds `x-gymaxis-cache: hit` on cached
 * responses so the UI can render a stale-data banner if needed.
 */
async function networkFirstWithCache(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      // Clone, inject timestamp meta, store.
      const cloned = fresh.clone();
      const headers = new Headers(cloned.headers);
      headers.set('x-gymaxis-cache-stored-at', String(Date.now()));
      const body = await cloned.blob();
      cache.put(request, new Response(body, { status: cloned.status, statusText: cloned.statusText, headers }));
      trimCache(API_CACHE, API_MAX_ENTRIES);
    }
    return fresh;
  } catch (_networkErr) {
    const cached = await cache.match(request);
    if (cached) {
      // Stamp the response so the client can show "showing cached data".
      const headers = new Headers(cached.headers);
      const storedAt = Number(headers.get('x-gymaxis-cache-stored-at') || 0);
      const ageMs = storedAt ? Date.now() - storedAt : 0;
      headers.set('x-gymaxis-cache', 'hit');
      headers.set('x-gymaxis-cache-age-ms', String(ageMs));
      headers.set('x-gymaxis-cache-stale', ageMs > API_MAX_AGE_MS ? 'true' : 'false');
      const body = await cached.blob();
      return new Response(body, { status: cached.status, statusText: cached.statusText, headers });
    }
    // No cache available — propagate the network failure so the
    // client's existing error handling kicks in.
    throw _networkErr;
  }
}

// Iter 216h142 — Web Push handlers for the Engineer Notifications slice.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_e) {
    try { data = { title: 'GymAxis', body: event.data ? event.data.text() : '' }; }
    catch (_e2) { data = { title: 'GymAxis', body: '' }; }
  }
  const title = data.title || 'GymAxis';
  const body  = data.body  || '';
  const options = {
    body,
    icon: data.icon || '/manifest-icons/icon-192.png',
    badge: data.badge || '/manifest-icons/icon-72.png',
    tag: data.tag || 'gymaxis',
    data: data.data || {},
    requireInteraction: false,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/svc/engineer/notifications';
  event.waitUntil((async () => {
    const clientList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clientList) {
      if (client.url.endsWith(url) && 'focus' in client) return client.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
});

