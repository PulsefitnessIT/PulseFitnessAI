/* global TextEncoder */
/**
 * Iter 220e7 — Engineer App Web Push helper.
 *
 * Pure browser-side helper around the Push API. The backend already
 * ships VAPID + subscribe/unsubscribe/test endpoints (see
 * `routes/svc/notifications.py`). This file is the single place the
 * UI talks to the Push API + Service Worker, with graceful
 * fallbacks for browsers that don't support web push (Safari pre-16,
 * Brave with notifications disabled, etc.).
 *
 * Usage:
 *   const status = await getPushStatus();
 *   await enablePush();
 *   await disablePush();
 *   await sendPushTest();
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export function isPushSupported() {
  return typeof window !== 'undefined'
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && typeof Notification !== 'undefined';
}

function urlBase64ToUint8Array(b64) {
  const padding = '='.repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function readyRegistration() {
  if (!isPushSupported()) throw new Error('Push not supported on this browser.');
  if (!navigator.serviceWorker.controller) {
    // Try to register the existing /sw.js if the worker isn't active yet.
    try { await navigator.serviceWorker.register('/sw.js'); } catch (_) { /* swallow */ }
  }
  return navigator.serviceWorker.ready;
}

/** Returns { supported, permission, subscribed, endpoint_hash }. */
export async function getPushStatus() {
  if (!isPushSupported()) {
    return { supported: false, permission: 'unsupported', subscribed: false };
  }
  const permission = Notification.permission;
  let subscribed = false;
  let endpointHash = null;
  try {
    const reg = await readyRegistration();
    const sub = await reg.pushManager.getSubscription();
    subscribed = !!sub;
    if (sub) {
      // 12-char SHA-256 of endpoint — matches backend's _endpoint_hash.
      const enc = new TextEncoder().encode(sub.endpoint);
      const digest = await crypto.subtle.digest('SHA-256', enc);
      endpointHash = Array.from(new Uint8Array(digest))
        .map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 24);
    }
  } catch (_) { /* swallow — surface as not-subscribed */ }
  return { supported: true, permission, subscribed, endpoint_hash: endpointHash };
}

export async function enablePush() {
  if (!isPushSupported()) throw new Error('Push not supported on this browser.');
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') {
    throw new Error(perm === 'denied'
      ? 'Notifications are blocked. Enable them in your browser settings to receive job alerts.'
      : 'Notification permission was dismissed.');
  }
  const reg = await readyRegistration();
  const { data } = await axios.get(`${API}/svc/engineer/push/vapid-key`, auth());
  const publicKey = data.public_key;
  if (!publicKey) throw new Error('Server has no VAPID key configured.');
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }
  await axios.post(`${API}/svc/engineer/push/subscribe`, {
    subscription: sub.toJSON(),
    user_agent: (navigator.userAgent || '').slice(0, 300),
  }, auth());
  return getPushStatus();
}

export async function disablePush() {
  if (!isPushSupported()) return { supported: false };
  try {
    const reg = await readyRegistration();
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      // Compute hash before unsubscribing so backend can lookup.
      const enc = new TextEncoder().encode(sub.endpoint);
      const digest = await crypto.subtle.digest('SHA-256', enc);
      const hash = Array.from(new Uint8Array(digest))
        .map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 24);
      try {
        await axios.delete(`${API}/svc/engineer/push/subscriptions/${hash}`, auth());
      } catch (_) { /* server may have already cleaned up */ }
      await sub.unsubscribe();
    }
  } catch (_) { /* swallow */ }
  return getPushStatus();
}

export async function sendPushTest() {
  const res = await axios.post(`${API}/svc/engineer/push/test`, {}, auth());
  return res.data;
}

export async function getNotificationPrefs() {
  const { data } = await axios.get(`${API}/svc/engineer/notification-prefs`, auth());
  return data;
}

export async function saveNotificationPrefs(payload) {
  const { data } = await axios.put(`${API}/svc/engineer/notification-prefs`, payload, auth());
  return data;
}

export async function snoozeNotifications(minutes) {
  const { data } = await axios.post(`${API}/svc/engineer/notification-prefs/snooze`,
                                    { minutes }, auth());
  return data;
}

export async function clearSnooze() {
  const { data } = await axios.delete(`${API}/svc/engineer/notification-prefs/snooze`, auth());
  return data;
}
