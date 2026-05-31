/**
 * Iter 220e7 — Engineer notification settings panel.
 *
 * Drawer launched from Engineer Account Settings. Lets the engineer:
 *   • Enable / disable Web Push (one-tap).
 *   • Send a self-test push to prove wiring end-to-end.
 *   • Toggle per-kind preferences (new_job / job_update / etc.).
 *   • Snooze all notifications for 30 / 60 / 120 minutes (one-tap).
 *
 * All four flows hit endpoints that already exist on
 * `routes/svc/notifications.py`. No backend changes needed.
 */
import { useEffect, useState } from 'react';
import {
  Bell, BellOff, CheckCircle2, RefreshCw, AlertTriangle, Send, Clock,
} from 'lucide-react';
import {
  isPushSupported, getPushStatus, enablePush, disablePush, sendPushTest,
  getNotificationPrefs, saveNotificationPrefs, snoozeNotifications, clearSnooze,
} from '@/utils/engineerPush';

const SUPPORTED_BROWSER_HELP_LINKS = {
  ios: 'iOS 16.4+ — Add this PWA to Home Screen and open from there.',
  desktop: 'Desktop browsers — Allow notifications in the address-bar permission prompt.',
  android: 'Android — Tap the bell icon and allow notifications.',
};

export default function NotificationSettings({ onClose }) {
  const [status, setStatus] = useState({ supported: true, permission: 'default', subscribed: false });
  const [prefs, setPrefs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [testing, setTesting] = useState(false);

  const reload = async () => {
    setErr(null);
    try {
      const [s, p] = await Promise.all([getPushStatus(), getNotificationPrefs()]);
      setStatus(s);
      setPrefs(p);
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load');
    }
  };

  useEffect(() => { reload();   }, []);

  const toggleSubscribe = async () => {
    setBusy(true); setErr(null);
    try {
      if (status.subscribed) {
        await disablePush();
      } else {
        await enablePush();
      }
      await reload();
    } catch (e) {
      setErr(e?.message || 'Failed to update subscription');
    }
    setBusy(false);
  };

  const sendTest = async () => {
    setTesting(true); setErr(null);
    try { await sendPushTest(); } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || 'Test failed');
    }
    setTesting(false);
  };

  const toggleKind = async (kind, on) => {
    const next = { ...(prefs?.prefs?.kind_prefs || {}), [kind]: on };
    setBusy(true);
    try {
      const saved = await saveNotificationPrefs({ kind_prefs: next });
      setPrefs({ ...prefs, prefs: saved.prefs, kinds: prefs.kinds });
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed to save preference');
    }
    setBusy(false);
  };

  const snooze = async (minutes) => {
    setBusy(true); setErr(null);
    try { await snoozeNotifications(minutes); await reload(); } catch (e) {
      setErr(e?.response?.data?.detail || 'Snooze failed');
    }
    setBusy(false);
  };

  const wake = async () => {
    setBusy(true); setErr(null);
    try { await clearSnooze(); await reload(); } catch (e) {
      setErr(e?.response?.data?.detail || 'Failed');
    }
    setBusy(false);
  };

  // ── Rendering helpers ──
  const supported = isPushSupported();
  const denied = status.permission === 'denied';

  return (
    <div className="fixed inset-0 z-[80] bg-black/40 backdrop-blur-sm flex justify-end"
         data-testid="notification-settings-drawer" onClick={onClose}>
      <div className="w-full max-w-md h-full bg-white overflow-y-auto shadow-xl"
           onClick={e => e.stopPropagation()}>
        <header className="sticky top-0 bg-white border-b px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-widest font-bold text-slate-400">Notifications</p>
            <h2 className="text-base font-extrabold text-slate-900">Push & alerts</h2>
          </div>
          <button onClick={onClose} aria-label="Close" data-testid="notif-close-btn"
                  className="p-1.5 text-slate-500 hover:text-slate-900">✕</button>
        </header>

        <div className="p-4 space-y-4">
          {err && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800"
                 data-testid="notif-error">
              <AlertTriangle size={12} className="inline mr-1" /> {err}
            </div>
          )}

          {/* Master subscribe card */}
          <div className="rounded-xl border p-4"
               style={{ borderColor: status.subscribed ? '#86efac' : '#e2e8f0',
                        background: status.subscribed ? '#f0fdf4' : '#f8fafc' }}>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                   style={{ background: status.subscribed ? '#dcfce7' : '#e2e8f0' }}>
                {status.subscribed
                  ? <Bell size={18} className="text-emerald-700" />
                  : <BellOff size={18} className="text-slate-500" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-slate-900"
                   data-testid="notif-status-label">
                  {!supported
                    ? 'Push not supported on this browser'
                    : denied
                      ? 'Notifications blocked in browser'
                      : status.subscribed
                        ? 'Push notifications are on'
                        : 'Push notifications are off'}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {!supported
                    ? 'Open this PWA on Android / Desktop / iOS 16.4+ from home-screen install.'
                    : denied
                      ? 'Enable notifications in your browser site settings, then come back.'
                      : status.subscribed
                        ? 'You\'ll get a push when a new job is assigned or a customer responds.'
                        : 'Tap below to turn on alerts for new jobs & customer updates.'}
                </p>
                {supported && !denied && (
                  <button onClick={toggleSubscribe} disabled={busy}
                          data-testid="notif-subscribe-toggle"
                          className={`mt-3 w-full py-2 rounded-md text-sm font-semibold text-white ${
                            status.subscribed ? 'bg-slate-700' : 'bg-emerald-600'
                          } disabled:opacity-50`}>
                    {busy
                      ? <RefreshCw size={12} className="inline animate-spin mr-1" />
                      : status.subscribed
                        ? <BellOff size={12} className="inline mr-1" />
                        : <Bell size={12} className="inline mr-1" />}
                    {status.subscribed ? 'Turn off notifications' : 'Enable notifications'}
                  </button>
                )}
                {supported && status.subscribed && (
                  <button onClick={sendTest} disabled={testing}
                          data-testid="notif-send-test-btn"
                          className="mt-2 w-full py-2 rounded-md text-xs font-semibold border border-emerald-300 text-emerald-700">
                    {testing
                      ? <RefreshCw size={11} className="inline animate-spin mr-1" />
                      : <Send size={11} className="inline mr-1" />}
                    Send self-test push
                  </button>
                )}
                {!supported && (
                  <ul className="mt-3 space-y-1 text-[10px] text-slate-500">
                    {Object.values(SUPPORTED_BROWSER_HELP_LINKS).map((line, i) => (
                      <li key={i} className="flex gap-1.5">
                        <CheckCircle2 size={9} className="text-slate-400 mt-0.5 shrink-0" />
                        {line}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>

          {/* Snooze */}
          {status.subscribed && (
            <div className="rounded-xl border border-slate-200 p-4" data-testid="notif-snooze-card">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                <Clock size={11} className="inline mr-1" /> Snooze all
              </p>
              {prefs?.prefs?.dnd_until ? (
                <div className="text-xs text-slate-700 mb-2" data-testid="notif-snooze-active">
                  Snoozed until {new Date(prefs.prefs.dnd_until).toLocaleTimeString('en-GB')}.
                  <button onClick={wake} disabled={busy} data-testid="notif-snooze-wake-btn"
                          className="ml-2 text-[11px] font-semibold text-blue-600">Wake</button>
                </div>
              ) : (
                <div className="flex gap-1.5">
                  {[30, 60, 120].map(m => (
                    <button key={m} onClick={() => snooze(m)} disabled={busy}
                            data-testid={`notif-snooze-${m}-btn`}
                            className="flex-1 py-1.5 rounded text-xs font-semibold border border-slate-200 text-slate-700">
                      {m < 60 ? `${m} min` : `${m / 60} hr`}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Per-kind toggles */}
          {prefs?.kinds?.length > 0 && status.subscribed && (
            <div className="rounded-xl border border-slate-200 p-4" data-testid="notif-kinds-card">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                Notification types
              </p>
              <div className="space-y-1.5">
                {prefs.kinds.map(kind => {
                  const on = prefs.prefs?.kind_prefs?.[kind] !== false;
                  return (
                    <label key={kind} className="flex items-center justify-between cursor-pointer py-1.5"
                           data-testid={`notif-kind-${kind}`}>
                      <span className="text-sm text-slate-700 capitalize">{kind.replace(/_/g, ' ')}</span>
                      <input type="checkbox" checked={on} onChange={e => toggleKind(kind, e.target.checked)}
                             className="w-10 h-5 appearance-none rounded-full bg-slate-200 checked:bg-emerald-500 transition-colors relative cursor-pointer
                                        before:content-[''] before:w-4 before:h-4 before:rounded-full before:bg-white before:absolute before:top-0.5 before:left-0.5
                                        checked:before:left-[22px] before:transition-all" />
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

NotificationSettings.displayName = 'NotificationSettings';
