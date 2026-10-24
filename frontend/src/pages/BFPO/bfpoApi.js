import axios from 'axios';
import { compressImage } from '../../utils/compressImage';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// The BFPO portal shares the platform's session. Auth travels on the HttpOnly
// `ga_session` cookie (withCredentials) with an `Authorization: Bearer cookie`
// marker — mirroring the global axios auth interceptor in App.js. An explicit
// localStorage token (impersonation / legacy) still wins when present.
function authHeader() {
  let t = null;
  try { t = localStorage.getItem('token'); } catch { /* ignore */ }
  return t && t !== 'cookie' ? `Bearer ${t}` : 'Bearer cookie';
}

const client = axios.create({ baseURL: `${API}/bfpo`, withCredentials: true });
client.interceptors.request.use((cfg) => { cfg.headers.Authorization = authHeader(); return cfg; });

// ── Offline outbox ──────────────────────────────────────────────
// Engineer job updates made with no signal are kept on the phone and
// replayed in order when the connection returns.
const OUTBOX_KEY = 'bfpo_outbox_v1';
const BLOB_PREFIX = 'bfpo_blob_';
const QUEUEABLE = /^\/jobs\/[^/]+\/(accept|arrive|diagnosis|parts|outcome|complete|signature|report-fault)$/;
const listeners = new Set();

const readOutbox = () => { try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]'); } catch { return []; } };
const writeOutbox = (items) => {
  try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(items)); } catch { /* storage full */ }
  listeners.forEach((fn) => fn(items.length));
};
export const outboxCount = () => readOutbox().length;
export const onOutboxChange = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

const isNetworkError = (err) => !err?.response && (err?.code === 'ERR_NETWORK' || err?.message === 'Network Error' || !navigator.onLine);

client.interceptors.response.use((r) => r, (err) => {
  const cfg = err?.config || {};
  const url = (cfg.url || '').split('?')[0];
  if ((cfg.method || '').toLowerCase() === 'post' && QUEUEABLE.test(url) && isNetworkError(err) && !cfg._fromOutbox) {
    let data = cfg.data;
    try { data = typeof data === 'string' ? JSON.parse(data) : data; } catch { /* keep raw */ }
    writeOutbox([...readOutbox(), { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, url, data, at: new Date().toISOString() }]);
    return Promise.resolve({ status: 202, data: { queued: true, offline: true } });
  }
  return Promise.reject(err);
});

let flushing = false;
export async function flushOutbox() {
  if (flushing || !navigator.onLine) return;
  flushing = true;
  try {
    let items = readOutbox();
    while (items.length) {
      const it = items[0];
      let data = it.data;
      try {
        if (data && typeof data.photo_url === 'string' && data.photo_url.startsWith('offline:')) {
          const key = BLOB_PREFIX + data.photo_url.slice(8);
          const dataUrl = localStorage.getItem(key);
          if (dataUrl) {
            const blob = await (await fetch(dataUrl)).blob();
            const up = await uploadFile(new File([blob], 'photo.jpg', { type: blob.type || 'image/jpeg' }));
            data = { ...data, photo_url: up.download_url };
            localStorage.removeItem(key);
          } else {
            data = { ...data, photo_url: '' };
          }
        }
        await client.post(it.url, data, { _fromOutbox: true });
      } catch (e) {
        if (isNetworkError(e)) break; // still offline — try again later
        // Server rejected it (e.g. job already moved on) — drop it so the queue can't jam.
      }
      items = readOutbox().filter((x) => x.id !== it.id);
      writeOutbox(items);
    }
  } finally { flushing = false; }
}
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { flushOutbox(); });
  setInterval(() => { if (readOutbox().length) flushOutbox(); }, 30000);
}

export const bfpo = client;

const fileToDataUrl = (file) => new Promise((res, rej) => {
  const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(file);
});

export async function uploadFile(rawFile) {
  const file = await compressImage(rawFile);
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await axios.post(`${API}/files/upload?category=service`, fd, {
      headers: { Authorization: authHeader(), 'Content-Type': 'multipart/form-data' },
      withCredentials: true,
    });
    return r.data;
  } catch (err) {
    if (!isNetworkError(err)) throw err;
    // No signal — keep the photo on the phone; it uploads with the queued update.
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    localStorage.setItem(BLOB_PREFIX + id, await fileToDataUrl(file));
    return { download_url: `offline:${id}`, offline: true };
  }
}

// Authenticated image fetch → object URL (img tags can't send our auth header).
export async function fetchBlobUrl(path) {
  const r = await client.get(path, { responseType: 'blob' });
  return URL.createObjectURL(r.data);
}

// Public invite flow (no session) — used by the set-password page.
export async function inviteStatus(token) {
  const r = await axios.get(`${API}/bfpo/invite/${token}`);
  return r.data;
}

export async function acceptInvite(token, password) {
  const r = await axios.post(`${API}/bfpo/invite/${token}/accept`, { password });
  return r.data;
}

export async function changePassword(current_password, new_password) {
  const r = await axios.post(`${API}/account/change-password`,
    { current_password, new_password },
    { headers: { Authorization: authHeader() }, withCredentials: true });
  return r.data;
}
