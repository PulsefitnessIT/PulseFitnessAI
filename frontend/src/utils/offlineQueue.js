/**
 * Offline mutation queue (iter 215da).
 *
 * Small, dependency-free IndexedDB-backed queue for HTTP mutations the
 * user triggers while offline. Call `enqueueMutation` in place of the
 * network call when `navigator.onLine === false`; on reconnect the
 * `OfflineQueueController` drains the queue in FIFO order.
 *
 * Shape of a queued entry:
 *   {
 *     id:        UUID,
 *     method:    'POST' | 'PUT' | 'PATCH' | 'DELETE',
 *     url:       string,              // full URL
 *     body:      serializable | null, // JSON-encoded at send time
 *     headers:   Record<string,string>,
 *     label:     string,              // user-facing description, e.g. "Log fault: Treadmill #3"
 *     kind:      string,              // 'fault' | 'member' | 'booking' | …
 *     created_at:ISO date,
 *     attempts:  number,
 *   }
 *
 * LocalStorage is used as a last-resort fallback for browsers without
 * IndexedDB (very rare — Android 4.x era).
 */
const DB_NAME = 'gymaxis-offline';
const STORE   = 'mutation-queue';
const LS_KEY  = 'gymaxis:offline_queue_fallback';
const MAX_ATTEMPTS = 5;

function hasIDB() {
  return typeof indexedDB !== 'undefined';
}

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

async function idbTx(mode, run) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const store = tx.objectStore(STORE);
    const result = run(store);
    tx.oncomplete = () => resolve(result);
    tx.onerror    = () => reject(tx.error);
  });
}

function lsRead() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); }
  catch { return []; }
}
function lsWrite(items) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(items)); } catch { /* quota */ }
}

/** Enqueue one mutation. Returns the persisted entry. */
export async function enqueueMutation(entry) {
  const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const record = {
    id,
    method: entry.method || 'POST',
    url: entry.url,
    body: entry.body ?? null,
    headers: entry.headers || {},
    label: entry.label || entry.url,
    kind: entry.kind || 'generic',
    created_at: new Date().toISOString(),
    attempts: 0,
  };
  if (hasIDB()) {
    await idbTx('readwrite', (store) => store.add(record));
  } else {
    const items = lsRead();
    items.push(record);
    lsWrite(items);
  }
  notifyChange();
  return record;
}

/** Read all pending entries in insertion order. */
export async function listPending() {
  if (!hasIDB()) return lsRead();
  return new Promise((resolve) => {
    openDB().then((db) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror   = () => resolve([]);
    }).catch(() => resolve([]));
  });
}

async function removeEntry(id) {
  if (hasIDB()) {
    await idbTx('readwrite', (store) => store.delete(id));
  } else {
    lsWrite(lsRead().filter((e) => e.id !== id));
  }
  notifyChange();
}

async function bumpAttempt(entry) {
  const updated = { ...entry, attempts: entry.attempts + 1 };
  if (hasIDB()) {
    await idbTx('readwrite', (store) => store.put(updated));
  } else {
    const items = lsRead().map((e) => (e.id === entry.id ? updated : e));
    lsWrite(items);
  }
  notifyChange();
  return updated;
}

/**
 * Drain the queue — attempts each entry once, in order. Successful
 * entries are removed. Failed entries stay queued with incremented
 * `attempts`; after MAX_ATTEMPTS they are moved to the "failed"
 * bucket (for now: dropped with a console warn — a future iter could
 * surface them to the user for manual retry).
 */
export async function drainQueue(fetchImpl = fetch) {
  const pending = await listPending();
  let sent = 0, failed = 0;
  for (const entry of pending) {
    try {
      const res = await fetchImpl(entry.url, {
        method: entry.method,
        headers: { 'Content-Type': 'application/json', ...entry.headers },
        body: entry.body !== null ? JSON.stringify(entry.body) : undefined,
      });
      if (res.ok || res.status === 409 /* already-exists idempotency */) {
        await removeEntry(entry.id);
        sent += 1;
      } else if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
        // Client-side error — dropping the entry (server will not accept
        // it on retry). Keep the user informed.
         
        console.warn('[offline-queue] dropping unrecoverable entry', entry.id, res.status);
        await removeEntry(entry.id);
        failed += 1;
      } else {
        await bumpAttempt(entry);
        failed += 1;
      }
    } catch (_e) {
      const updated = await bumpAttempt(entry);
      if (updated.attempts >= MAX_ATTEMPTS) {
        await removeEntry(entry.id);
      }
      failed += 1;
    }
  }
  return { sent, failed };
}

// ── Change notifications — tiny pub/sub so React hooks can re-render ──
const listeners = new Set();
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function notifyChange() {
  for (const fn of listeners) {
    try { fn(); } catch { /* ignore */ }
  }
}
