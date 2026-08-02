/**
 * languagePref — offline-resilient language preference helper.
 *
 * i18next already caches the active language to localStorage (offline-safe),
 * so the UI stays in the chosen language with no signal. The gap this closes
 * is the *reconnect revert*: when the server-side `user.language` is applied
 * on hydrate (App.js), a language a field engineer picked while OFFLINE — whose
 * profile sync never landed — would get reverted to the stale server value.
 *
 * `setLanguagePreference` switches the UI + persists locally immediately, then
 * best-effort syncs to the account. On failure it queues the choice under
 * `pf_lang_pending`; App.js treats that pending choice as authoritative and
 * `flushPendingLanguageSync` pushes it up the moment connectivity returns.
 */
import i18n from '@/i18n';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
export const LANG_PENDING_KEY = 'pf_lang_pending';

function authHeaders() {
  try {
    const tk = localStorage.getItem('token');
    return tk && tk !== 'cookie' ? { headers: { Authorization: `Bearer ${tk}` } } : {};
  } catch { return {}; }
}

function isSignedIn() {
  try { return !!localStorage.getItem('token'); } catch { return false; }
}

export function hasPendingLanguageSync() {
  try { return !!localStorage.getItem(LANG_PENDING_KEY); } catch { return false; }
}

function syncToServer(lang) {
  return axios.patch(`${API}/account/profile`, { language: lang }, authHeaders());
}

// Change UI language + persist locally (offline-safe) + best-effort server sync.
export async function setLanguagePreference(lang) {
  try { i18n.changeLanguage(lang); } catch { /* ignore */ }
  try { localStorage.setItem('i18nextLng', lang); } catch { /* quota */ }
  if (!isSignedIn()) return;
  try {
    await syncToServer(lang);
    try { localStorage.removeItem(LANG_PENDING_KEY); } catch { /* ignore */ }
  } catch {
    // Offline / transient — remember the choice so a stale server value
    // doesn't revert it on the next hydrate; retried when back online.
    try { localStorage.setItem(LANG_PENDING_KEY, lang); } catch { /* quota */ }
  }
}

// Retry a queued offline language change. Safe to call repeatedly.
export async function flushPendingLanguageSync() {
  let pending;
  try { pending = localStorage.getItem(LANG_PENDING_KEY); } catch { pending = null; }
  if (!pending || !isSignedIn()) return;
  try {
    await syncToServer(pending);
    try { localStorage.removeItem(LANG_PENDING_KEY); } catch { /* ignore */ }
  } catch { /* still offline; keep the marker for the next attempt */ }
}
