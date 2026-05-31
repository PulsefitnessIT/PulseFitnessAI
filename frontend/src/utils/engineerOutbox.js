/**
 * Iter 220e6 — Engineer App offline write outbox (IndexedDB-backed).
 *
 * Wraps mutating engineer-app API calls so they survive a flaky
 * connection (basement gym, poor 4G, train tunnel). Behaviour:
 *
 *   1. `outboxPost(url, body, opts)` and `outboxPut(url, body, opts)`
 *      attempt the request immediately. On success they return the
 *      response as normal.
 *   2. On a network error (no response received) or 502/503/504/0
 *      response the payload is persisted to an IndexedDB queue
 *      keyed by an auto-incrementing id, and the function resolves
 *      with `{ queued: true, queueId }` so the caller can show
 *      "Saved offline — will sync when back online".
 *   3. The queue is drained automatically whenever the browser
 *      regains network (`online` event) and on every successful
 *      request (catching up after a brief blip). A background
 *      `setInterval` retries every 60 s as a belt-and-braces safety
 *      net for service-worker edge cases.
 *
 * Genuine server-side failures (4xx other than 408/429) are NOT
 * queued — they bubble up to the caller because retrying them
 * blindly would just hammer the server.
 *
 * The outbox is namespaced per engineer (`token` substring) so two
 * engineers sharing a tablet don't replay each other's work.
 */
import axios from 'axios';

const DB_NAME  = 'gymaxis_engineer_outbox';
const DB_VER   = 1;
const STORE    = 'outbox';

const RETRYABLE_STATUS = new Set([0, 408, 425, 429, 500, 502, 503, 504]);

let dbPromise = null;
let drainInFlight = false;
const listeners = new Set();

function openDb() {
  if (typeof indexedDB === 'undefined') return Promise.reject(new Error('idb-unavailable'));
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        store.createIndex('owner', 'owner', { unique: false });
        store.createIndex('queued_at', 'queued_at', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function currentOwner() {
  const token = (typeof localStorage !== 'undefined' && localStorage.getItem('token')) || '';
  // Use last 12 chars so we never persist the full bearer token in
  // IndexedDB. Enough to disambiguate two engineers on one device.
  return token ? token.slice(-12) : 'anon';
}

async function persist(entry) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    const req = tx.objectStore(STORE).add(entry);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function listPending() {
  const db = await openDb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).index('owner').getAll(currentOwner());
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => resolve([]);
  });
}

async function removeEntry(id) {
  const db = await openDb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => resolve(false);
  });
}

async function bumpAttempt(id, lastError) {
  const db = await openDb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const row = getReq.result;
      if (!row) return resolve(false);
      row.attempts = (row.attempts || 0) + 1;
      row.last_error = lastError ? String(lastError).slice(0, 280) : '';
      row.last_attempt_at = new Date().toISOString();
      store.put(row);
    };
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => resolve(false);
  });
}

function isNetworkLikeError(err) {
  if (!err) return false;
  if (err.message === 'Network Error') return true;
  if (err.code === 'ECONNABORTED') return true;
  if (!err.response) return true;       // request never reached server
  const s = err.response.status;
  return RETRYABLE_STATUS.has(s || 0);
}

async function attempt(entry) {
  const cfg = {
    method: entry.method,
    url: entry.url,
    data: entry.body,
    headers: entry.headers || {},
    timeout: 15000,
  };
  return axios(cfg);
}

/** Drain all pending entries. Stops on the first network-like
 *  failure (so we don't burn battery while still offline). */
export async function drainOutbox() {
  if (drainInFlight) return { drained: 0, remaining: -1 };
  drainInFlight = true;
  let drained = 0;
  try {
    const pending = await listPending();
    pending.sort((a, b) => a.id - b.id);
    for (const row of pending) {
      try {
        await attempt(row);
        await removeEntry(row.id);
        drained++;
      } catch (err) {
        if (isNetworkLikeError(err)) {
          await bumpAttempt(row.id, err?.message);
          break;     // still offline — stop draining
        }
        // Permanent failure (4xx). Mark with attempts so the UI can
        // expose it, but drop from the queue so it doesn't blockade
        // the rest of the work.
        await bumpAttempt(row.id, `permanent: ${err?.response?.status} ${err?.message}`);
        await removeEntry(row.id);
      }
    }
  } finally {
    drainInFlight = false;
    notifyListeners();
  }
  const remaining = (await listPending()).length;
  return { drained, remaining };
}

function notifyListeners() {
  for (const fn of listeners) { try { fn(); } catch (_) { /* swallow */ } }
}

export function onOutboxChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export async function outboxStatus() {
  const pending = await listPending();
  return { pending: pending.length, online: typeof navigator !== 'undefined' ? navigator.onLine : true };
}

async function performWithOutbox(method, url, body, opts = {}) {
  try {
    const res = await attempt({
      method, url, body, headers: opts.headers || {},
    });
    // On success, opportunistically drain anything that piled up.
    setTimeout(() => { drainOutbox().catch(() => {}); }, 100);
    return res;
  } catch (err) {
    if (!isNetworkLikeError(err)) throw err;
    // Allow caller to opt-out of queueing (e.g. read-after-write).
    if (opts.noQueue) throw err;
    const entry = {
      owner: currentOwner(),
      method, url, body,
      headers: opts.headers || {},
      kind: opts.kind || 'mutation',
      label: opts.label || `${method} ${url}`,
      queued_at: new Date().toISOString(),
      attempts: 0,
    };
    const id = await persist(entry);
    notifyListeners();
    return {
      data: { queued: true, queueId: id, label: entry.label },
      status: 202,
      headers: {},
      queued: true,
      queueId: id,
    };
  }
}

export function outboxPost(url, body, opts) { return performWithOutbox('POST', url, body, opts); }
export function outboxPut(url, body, opts)  { return performWithOutbox('PUT', url, body, opts); }
export function outboxPatch(url, body, opts){ return performWithOutbox('PATCH', url, body, opts); }

// Boot — drain when the tab regains network, and on a slow ticker
// so misfired `online` events don't strand entries.
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { drainOutbox().catch(() => {}); });
  // Initial drain after a moment (gives auth setup time to settle).
  setTimeout(() => { drainOutbox().catch(() => {}); }, 3000);
  setInterval(() => { drainOutbox().catch(() => {}); }, 60000);
}
