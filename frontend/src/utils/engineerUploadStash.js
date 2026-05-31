/**
 * Iter 220ea·4 — Engineer App paused-upload stash.
 *
 * Persists in-flight chunked-upload sessions to IndexedDB so a
 * field engineer whose phone dies / loses signal / Safari kills
 * the tab can come back and resume from the chunk they were on,
 * without having to re-select the source file.
 *
 * What gets persisted per session:
 *   {
 *     upload_id   : string  (the server-side session id)
 *     case_id     : string  (engineer service-case the photo/video belongs to)
 *     filename    : string
 *     size        : number
 *     content_type: string
 *     blob        : Blob    (the actual file bytes)
 *     caption     : string
 *     stage       : 'before' | 'after' | ''
 *     kind        : 'photo' | 'video'
 *     saved_at    : number  (ms epoch)
 *   }
 *
 * Sessions are tied to the current engineer (token substring)
 * so two engineers sharing a tablet don't see each other's
 * paused uploads.
 *
 * Why Blob storage?
 *   The browser CANNOT re-read a File handle after the tab is
 *   closed (security). Without persisting the bytes, resume
 *   would require the engineer to re-select the file — usable,
 *   but loses the original timestamp and is friction-ier than
 *   it needs to be. Modern browsers can store ~quotaInBytes/3 of
 *   IndexedDB Blob data — comfortably enough for 5-10 paused
 *   evidence uploads.
 *
 * Why not encrypt?
 *   The blobs already live on the same device behind the user's
 *   OS lock. Adding application-layer encryption would just
 *   shuffle the key into the same localStorage the token is in,
 *   without raising the bar for a determined attacker.
 */

const DB_NAME = 'gymaxis_engineer_upload_stash';
const DB_VER  = 1;
const STORE   = 'paused_uploads';

let dbPromise = null;
const listeners = new Set();

function openDb() {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('idb-unavailable'));
  }
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'upload_id' });
        store.createIndex('owner', 'owner', { unique: false });
        store.createIndex('saved_at', 'saved_at', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror  = () => reject(req.error);
  });
  return dbPromise;
}

function currentOwner() {
  const token = (typeof localStorage !== 'undefined' && localStorage.getItem('token')) || '';
  // Per-engineer namespace; first 12 chars are plenty to dedupe a
  // shared tablet without bleeding token material into IndexedDB
  // keys.
  return token ? token.slice(0, 12) : 'anon';
}

function notify() {
  for (const fn of [...listeners]) {
    try { fn(); } catch { /* listener errors must not crash the stash */ }
  }
}

export function subscribePausedUploads(fn) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export async function stashPausedUpload(session) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put({
        owner: currentOwner(),
        saved_at: Date.now(),
        ...session,
      });
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    notify();
  } catch { /* stash failures must never block the upload itself */ }
}

export async function dropPausedUpload(uploadId) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(uploadId);
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    notify();
  } catch { /* swallow */ }
}

export async function listPausedUploads() {
  try {
    const db = await openDb();
    const rows = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror   = () => reject(req.error);
    });
    const owner = currentOwner();
    return rows
      .filter(r => r.owner === owner)
      .sort((a, b) => (b.saved_at || 0) - (a.saved_at || 0));
  } catch {
    return [];
  }
}

export async function getPausedUpload(uploadId) {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get(uploadId);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror   = () => reject(req.error);
    });
  } catch {
    return null;
  }
}

// Lightweight summary the pill can render without spinning up the
// full sheet — just the count.
export async function countPausedUploads() {
  const rows = await listPausedUploads();
  return rows.length;
}
