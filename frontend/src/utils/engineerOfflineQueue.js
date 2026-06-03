/**
 * GymAxis Engineer App — offline writes (iter 216h143 · Phase 4 / Slice 3).
 *
 * Engineer-specific IndexedDB queue for the field-service writes:
 *   time entries, mileage, photos, signatures, parts-used, etc.
 *
 * Keeps a separate object store (`engineer-ops`) from the older
 * platform-wide `mutation-queue` so the two systems don't fight over
 * the same DB schema.
 *
 * Design rules
 *   • JSON-only bodies for the simple writes. Photo uploads keep their
 *     File blob in IndexedDB (works across desktop + mobile browsers)
 *     and rehydrate on replay.
 *   • Every queued op carries an Idempotency-Key reused on every retry.
 *     The engineer mobile API already honours this header for all
 *     write paths (svc_time_entries, svc_engineer_photos, svc_signatures,
 *     mileage, parts_used) so a duplicate replay is a no-op server-side.
 *   • 5xx → keep in queue. 4xx → drop (bad data won't fix itself).
 *     Network error → keep in queue and wait for `online` event.
 */
import { useEffect, useState } from 'react';

const DB_NAME    = 'gymaxis-engineer-offline';
const DB_VERSION = 1;
const STORE      = 'engineer-ops';

let _dbPromise = null;

const _uuid = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);

const _openDB = () => {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' });
        store.createIndex('by_created', 'created_at');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
  return _dbPromise;
};

const _store = async (mode = 'readonly') => {
  const db = await _openDB();
  return db.transaction(STORE, mode).objectStore(STORE);
};

const _listeners = new Set();
const _notify = () => _listeners.forEach((cb) => { try { cb(); } catch { /* ignore */ } });

// ── public CRUD ────────────────────────────────────────────────

export const engineerEnqueue = async (op) => {
  const doc = {
    id:               op.id || _uuid(),
    method:           op.method,
    url:              op.url,
    body:             op.body || null,
    multipart:        !!op.multipart,
    label:            op.label || op.url,
    idempotency_key:  op.idempotency_key || _uuid(),
    created_at:       Date.now(),
    attempts:         0,
    last_error:       null,
  };
  const s = await _store('readwrite');
  s.put(doc);
  _notify();
  return doc;
};

export const engineerListOps = async () => {
  const s = await _store('readonly');
  return new Promise((resolve) => {
    const out = [];
    const req = s.openCursor();
    req.onsuccess = () => {
      const c = req.result;
      if (!c) return resolve(out.sort((a, b) => a.created_at - b.created_at));
      out.push(c.value);
      c.continue();
    };
    req.onerror = () => resolve(out);
  });
};

export const engineerRemoveOp = async (id) => {
  const s = await _store('readwrite');
  s.delete(id);
  _notify();
};

export const engineerClearQueue = async () => {
  const s = await _store('readwrite');
  s.clear();
  _notify();
};

// ── React hook for the offline indicator ───────────────────────

export const useEngineerOfflineQueue = () => {
  const [state, setState] = useState({
    online: typeof navigator !== 'undefined' ? navigator.onLine : true,
    pending: 0,
  });

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const ops = await engineerListOps();
        if (mounted) setState((s) => ({ ...s, pending: ops.length }));
      } catch { /* IDB unavailable */ }
    };
    refresh();
    _listeners.add(refresh);
    const on  = () => setState((s) => ({ ...s, online: true }));
    const off = () => setState((s) => ({ ...s, online: false }));
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      mounted = false;
      _listeners.delete(refresh);
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return state;
};

// ── replay engine ──────────────────────────────────────────────

const _authHeader = () => {
  const t = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
  return t ? { Authorization: `Bearer ${t}` } : {};
};

const _replay = async (op) => {
  const headers = {
    ..._authHeader(),
    'Idempotency-Key': op.idempotency_key,
  };
  if (op.multipart && op.body) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(op.body.fields || {})) {
      fd.append(k, v);
    }
    if (op.body.file_blob) {
      const file = new File(
        [op.body.file_blob],
        op.body.file_name || 'upload.bin',
        { type: op.body.file_type || 'application/octet-stream' },
      );
      fd.append(op.body.file_field || 'file', file);
    }
    return fetch(op.url, { method: op.method, headers, body: fd });
  }
  return fetch(op.url, {
    method: op.method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: op.body ? JSON.stringify(op.body) : undefined,
  });
};

let _running = false;
export const engineerFlushQueue = async () => {
  if (_running) return { flushed: 0, remaining: -1 };
  _running = true;
  let flushed = 0;
  let last_error = null;
  try {
    const ops = await engineerListOps();
    for (const op of ops) {
      try {
        const res = await _replay(op);
        if (res.ok || (res.status >= 400 && res.status < 500)) {
          await engineerRemoveOp(op.id);
          flushed += 1;
        } else {
          // 5xx — keep and stop the run
          const s = await _store('readwrite');
          s.put({ ...op, attempts: (op.attempts || 0) + 1, last_error: `HTTP ${res.status}` });
          _notify();
          break;
        }
      } catch (e) {
        last_error = e?.message || String(e);
        const s = await _store('readwrite');
        s.put({ ...op, attempts: (op.attempts || 0) + 1, last_error });
        _notify();
        break;
      }
    }
  } finally {
    _running = false;
  }
  const remaining = (await engineerListOps()).length;
  return { flushed, remaining, last_error };
};

// Auto-flush hooks
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { engineerFlushQueue().catch(() => {}); });
  // Initial 2s after boot
  setTimeout(() => { engineerFlushQueue().catch(() => {}); }, 2000);
  // Retry every 60s while there's anything queued
  setInterval(() => {
    engineerListOps().then((ops) => {
      if (ops.length) engineerFlushQueue().catch(() => {});
    });
  }, 60000);
}

// ── Convenience helper for engineer write paths ─────────────────
const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

/**
 * Try the write online first; if the network throws OR we're already
 * offline, queue it. Returns `{ ok: true, data }` on success or
 * `{ ok: false, queued: opId }` if we couldn't reach the server.
 */
export const engineerSendOrQueue = async ({ method, path, body, label, multipart }) => {
  const url = `${API}${path}`;
  const op = {
    method,
    url,
    body,
    label,
    multipart: !!multipart,
    idempotency_key: _uuid(),
  };
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    const queued = await engineerEnqueue(op);
    return { ok: false, offline: true, queued: queued.id };
  }
  try {
    const res = await _replay(op);
    if (res.ok) {
      const ct = res.headers.get('content-type') || '';
      const data = ct.includes('application/json') ? await res.json() : await res.text();
      return { ok: true, data };
    }
    if (res.status >= 400 && res.status < 500) {
      // Iter 220eb — a 4xx is a real validation/business error (e.g. the
      // 412 H&S-signoff gate on the on-site timer). It will NEVER succeed
      // on replay, so do NOT queue it — surface it to the caller so the
      // UI can show the real reason instead of a misleading
      // "queued — will sync" toast that strands the timer at 0m.
      let detail = null;
      let raw = '';
      try {
        raw = await res.text();
        const parsed = JSON.parse(raw);
        detail = parsed?.detail ?? parsed;
      } catch { /* non-JSON body */ }
      const err = new Error(`HTTP ${res.status}: ${raw || res.statusText}`);
      err.status = res.status;
      err.detail = detail;
      err.is4xx = true;
      throw err;
    }
    // 5xx — server is up but unhappy; safe to retry later.
    const queued = await engineerEnqueue(op);
    return { ok: false, server_5xx: true, queued: queued.id };
  } catch (e) {
    // Re-throw genuine 4xx errors so callers can handle them.
    if (e && e.is4xx) throw e;
    // Network/transport failure → queue for replay on reconnect.
    const queued = await engineerEnqueue(op);
    return { ok: false, offline: true, queued: queued.id, error: e?.message || String(e) };
  }
};
