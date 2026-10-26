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
const QUEUEABLE = /^\/jobs\/[^/]+\/(accept|arrive|diagnosis|parts|outcome|complete|signature|report-fault|equipment\/[^/]+\/details)$/;
const listeners = new Set();

const readOutbox = () => { try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]'); } catch { return []; } };
const writeOutbox = (items) => {
  try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(items)); } catch { /* storage full */ }
  listeners.forEach((fn) => fn(items.length));
};
let outboxOwner = '';
// Saved updates belong to the engineer who made them; never replay them under another login.
export const setOutboxOwner = (key) => { outboxOwner = (key || '').toLowerCase(); };
export const outboxCount = () => readOutbox().length;
let lastFlushError = '';
export const outboxError = () => lastFlushError;

const STEP_STATUS = { accept: 'assigned', parts: 'paused_parts', complete: 'closed' };
// Status a job will have once its queued offline updates are sent (for the UI).
export function pendingStatusFor(jobId, status) {
  let st = status;
  readOutbox().filter((x) => x.url.startsWith(`/jobs/${jobId}/`)).forEach((x) => {
    const step = x.url.split('/').pop();
    if (step === 'arrive') { if (x.data?.safe !== false) st = 'on_site'; } else if (STEP_STATUS[step]) st = STEP_STATUS[step];
  });
  return st;
}

function dataUrlToBlob(dataUrl) {
  const [head, b64] = dataUrl.split(',');
  const mime = (head.match(/data:([^;]+)/) || [])[1] || 'image/jpeg';
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}
export const onOutboxChange = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

const isNetworkError = (err) => !err?.response && (err?.code === 'ERR_NETWORK' || err?.message === 'Network Error' || !navigator.onLine);

client.interceptors.response.use((r) => r, (err) => {
  const cfg = err?.config || {};
  const url = (cfg.url || '').split('?')[0];
  if ((cfg.method || '').toLowerCase() === 'post' && QUEUEABLE.test(url) && isNetworkError(err) && !cfg._fromOutbox) {
    let data = cfg.data;
    try { data = typeof data === 'string' ? JSON.parse(data) : data; } catch { /* keep raw */ }
    writeOutbox([...readOutbox(), { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, owner: outboxOwner, url, data, at: new Date().toISOString() }]);
    return Promise.resolve({ status: 202, data: { queued: true, offline: true } });
  }
  return Promise.reject(err);
});

let flushing = false;
export async function flushOutbox() {
  if (flushing || !navigator.onLine || !outboxOwner) return;
  flushing = true;
  lastFlushError = '';
  try {
    // Items saved before owners were recorded belong to whoever is signed in now
    // (BFPOApp wipes the outbox first if a *different* person signed in).
    const mine = (x) => !x.owner || x.owner === outboxOwner;
    if (readOutbox().some((x) => !mine(x))) writeOutbox(readOutbox().filter(mine));
    let items = readOutbox();
    while (items.length) {
      const it = items[0];
      let data = it.data;
      try {
        if (data && typeof data.photo_url === 'string' && data.photo_url.startsWith('offline:')) {
          const key = BLOB_PREFIX + data.photo_url.slice(8);
          const dataUrl = localStorage.getItem(key);
          if (dataUrl) {
            const blob = dataUrlToBlob(dataUrl);
            const up = await uploadFile(new File([blob], 'photo.jpg', { type: blob.type || 'image/jpeg' }));
            if (up.offline) throw Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });
            data = { ...data, photo_url: up.download_url };
            const q = readOutbox().map((x) => (x.id === it.id ? { ...x, data } : x));
            writeOutbox(q);
            localStorage.removeItem(key);
          } else {
            data = { ...data, photo_url: '' };
          }
        }
        await client.post(it.url, data, { _fromOutbox: true });
      } catch (e) {
        const code = e?.response?.status;
        // Only a definitive rejection (job already moved on, bad data) is dropped;
        // signal loss, server errors and expired sessions keep it for the next try.
        if (![400, 404, 409, 422].includes(code)) {
          lastFlushError = isNetworkError(e) ? '' : (code === 401 ? 'Please sign in again to send your saved updates' : 'Could not send yet — will retry');
          listeners.forEach((fn) => fn(readOutbox().length));
          break;
        }
        // Later steps for the same job depended on this one — drop them too.
        const jobPrefix = it.url.split('/').slice(0, 3).join('/') + '/';
        const later = readOutbox().filter((x) => x.id !== it.id && x.url.startsWith(jobPrefix));
        lastFlushError = `A saved update was refused${later.length ? ` (and ${later.length} follow-on step${later.length === 1 ? '' : 's'} not sent)` : ''}: ${e?.response?.data?.detail || 'the job had already changed'}`;
        writeOutbox(readOutbox().filter((x) => x.id !== it.id && !later.some((l) => l.id === x.id)));
        items = readOutbox();
        continue;
      }
      items = readOutbox().filter((x) => x.id !== it.id);
      writeOutbox(items);
    }
  } finally { flushing = false; listeners.forEach((fn) => fn(readOutbox().length)); }
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
