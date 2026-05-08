/**
 * User-preferences store for "Start" tabs.
 *
 * Kept intentionally simple: a single localStorage key `gymaxis_prefs`
 * holding a JSON object. Modules read/write synchronously so the setting
 * takes effect immediately. No backend roundtrip — the preference is
 * per-device (matches the pattern of `crm_tour_seen`, PWA install prompt,
 * etc. already in use across the app).
 *
 * Current prefs:
 *  • hideStartTabs: boolean — hides the "Start" pill in every module's
 *    tab bar. Useful once operators no longer need the guided overlay,
 *    or when the tab bar becomes too crowded to fit additional modules
 *    (e.g. upcoming Machine Asset Management tab in Operations).
 */
const KEY = 'gymaxis_prefs';

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function writeAll(next) {
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* silent — quota, private mode, etc. */
  }
  // Dispatch a same-tab event so live components re-render without a
  // page reload when the preference is toggled from the Start tab
  // itself. React's storage-event listener ignores same-tab writes, so
  // we fire a custom event that modules subscribe to via `useUserPrefs`.
  try { window.dispatchEvent(new CustomEvent('gymaxis:prefs')); } catch { /* noop */ }
}

export function getPref(name, fallback = null) {
  const all = readAll();
  return name in all ? all[name] : fallback;
}

export function setPref(name, value) {
  const next = { ...readAll(), [name]: value };
  writeAll(next);
}

/**
 * React hook — subscribes to both cross-tab `storage` events and
 * same-tab `gymaxis:prefs` events so UI stays in sync.
 */
import { useEffect, useState } from 'react';

export function useUserPref(name, fallback = null) {
  const [val, setVal] = useState(() => getPref(name, fallback));
  // One-shot URL escape hatch: `?show-start=1` forcibly resets the hide
  // flag so users who want the guided tabs back have a discoverable
  // way to re-enable them without digging through localStorage.
  useEffect(() => {
    if (name !== 'hideStartTabs') return;
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('show-start') === '1') {
        setPref('hideStartTabs', false);
        setVal(false);
      }
    } catch { /* noop */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const onStorage = () => setVal(getPref(name, fallback));
    window.addEventListener('storage', onStorage);
    window.addEventListener('gymaxis:prefs', onStorage);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('gymaxis:prefs', onStorage);
    };
  }, [name, fallback]);
  return [val, (v) => { setPref(name, v); setVal(v); }];
}
