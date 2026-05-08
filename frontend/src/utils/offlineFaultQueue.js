/**
 * MOD offline fault queue — IndexedDB-backed.
 *
 * When the wizard's submit fails due to network (fetch TypeError), we stash
 * the fault payload and raw attachment blobs in IDB and surface a friendly
 * "Saved offline — will sync when back online" confirmation. A best-effort
 * flush runs automatically on every page load and on the browser `online`
 * event.
 *
 * Why raw blobs, not URLs? In offline mode the upload endpoint hasn't been
 * hit yet. We hold the raw files locally and upload them first at flush
 * time, THEN submit the fault with the resulting storage paths.
 *
 * Uses plain DOM IndexedDB — no library — to keep the bundle lean.
 */
const DB_NAME = 'mod-offline';
const DB_VERSION = 1;
const STORE = 'pendingFaults';

function open() {
  return new Promise((resolve, reject) => {
    // window.indexedDB is the browser global — guarding via window.* avoids
    // ESLint's no-undef warning while still failing fast in non-browser envs.
    const idb = typeof window !== 'undefined' ? window.indexedDB : null;
    if (!idb) { reject(new Error('IndexedDB unavailable')); return; }
    const req = idb.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const os = db.createObjectStore(STORE, { keyPath: 'id' });
        os.createIndex('created_at', 'created_at');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode = 'readonly') {
  const db = await open();
  return db.transaction(STORE, mode).objectStore(STORE);
}

function genId() {
  return `offline-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export async function enqueueFault({ form, attachments }) {
  const id = genId();
  const record = {
    id,
    created_at: new Date().toISOString(),
    try_count: 0,
    form,
    attachments: (attachments || []).map((a) => ({
      blob: a.blob,
      content_type: a.content_type,
      kind: a.kind,
      filename: a.filename,
    })),
  };
  const store = await tx('readwrite');
  return new Promise((resolve, reject) => {
    const r = store.add(record);
    r.onsuccess = () => resolve(id);
    r.onerror = () => reject(r.error);
  });
}

export async function listPending() {
  const store = await tx();
  return new Promise((resolve, reject) => {
    const r = store.getAll();
    r.onsuccess = () => resolve(r.result || []);
    r.onerror = () => reject(r.error);
  });
}

export async function countPending() {
  try {
    const items = await listPending();
    return items.length;
  } catch {
    return 0;
  }
}

async function removeOne(id) {
  const store = await tx('readwrite');
  return new Promise((resolve, reject) => {
    const r = store.delete(id);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
  });
}

async function updateOne(record) {
  const store = await tx('readwrite');
  return new Promise((resolve, reject) => {
    const r = store.put(record);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
  });
}


/** Flush everything — returns {synced, failed}. Safe to call repeatedly. */
export async function flushQueue(API) {
  if (!navigator.onLine) return { synced: 0, failed: 0, skipped: 'offline' };
  const token = localStorage.getItem('token');
  if (!token) return { synced: 0, failed: 0, skipped: 'no-token' };
  const pending = await listPending();
  let synced = 0;
  let failed = 0;
  for (const rec of pending) {
    try {
      // 1. Upload any queued attachment blobs → paths
      const paths = [];
      for (const a of rec.attachments || []) {
        const fd = new FormData();
        const file = new File([a.blob], a.filename || `mod-${rec.id}.bin`, { type: a.content_type });
        fd.append('file', file);
        const up = await fetch(`${API}/mod/site/attachments`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });
        if (!up.ok) throw new Error(`attachment upload ${up.status}`);
        const j = await up.json();
        paths.push(j.path);
      }
      // 2. Submit the fault
      const res = await fetch(`${API}/mod/site/faults`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ...rec.form, attachment_urls: paths }),
      });
      if (!res.ok) throw new Error(`fault submit ${res.status}`);
      await removeOne(rec.id);
      synced += 1;
    } catch {
      rec.try_count = (rec.try_count || 0) + 1;
      rec.last_try = new Date().toISOString();
      try { await updateOne(rec); } catch { /* ignore */ }
      failed += 1;
    }
  }
  return { synced, failed };
}


/** Install the online-event auto-flush once per page load. */
export function installAutoFlush(API, onChange) {
  const run = async () => {
    const before = await countPending();
    if (before === 0) return;
    const result = await flushQueue(API);
    if (onChange) onChange({ remaining: await countPending(), ...result });
  };
  window.addEventListener('online', run);
  // Kick one off on install (covers case where user returns while online).
  run();
  return () => window.removeEventListener('online', run);
}


/** Lightweight offline-capable cache for equipment + staff lists. Lets the
 * wizard open even without network, assuming the dashboard was loaded once
 * online earlier. */
const CACHE_KEY_EQUIPMENT = 'mod-cache-equipment';
const CACHE_KEY_STAFF = 'mod-cache-staff';

export function cacheListSnapshot({ equipment, staff }) {
  try {
    if (equipment) localStorage.setItem(CACHE_KEY_EQUIPMENT, JSON.stringify({ at: Date.now(), data: equipment }));
    if (staff) localStorage.setItem(CACHE_KEY_STAFF, JSON.stringify({ at: Date.now(), data: staff }));
  } catch { /* quota etc */ }
}

export function readCachedSnapshot() {
  try {
    const e = JSON.parse(localStorage.getItem(CACHE_KEY_EQUIPMENT) || 'null');
    const s = JSON.parse(localStorage.getItem(CACHE_KEY_STAFF) || 'null');
    return {
      equipment: e?.data || [],
      staff: s?.data || [],
      cachedAt: Math.max(e?.at || 0, s?.at || 0),
    };
  } catch {
    return { equipment: [], staff: [], cachedAt: 0 };
  }
}
