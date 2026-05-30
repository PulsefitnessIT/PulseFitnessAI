/**
 * EngineerAppShellNudge — Iter 220df.
 *
 * Surfaces the two "full app experience" features as a contextual
 * card on the engineer home, since engineers rarely visit the
 * Notifications page (where the subscribe button lives) or wait
 * 30s on the global PWA banner.
 *
 *   • PWA install  — listens to `beforeinstallprompt`; iOS gets a
 *     deep-link to the share-sheet guide.
 *   • Push alerts  — runs the same subscribe flow as
 *     EngineerNotifications.PushSubscribeButton.
 *
 * Quiet states:
 *   • Hidden when already standalone (installed) AND push granted.
 *   • Hidden when user dismissed within the last 14 days.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Bell, Download, X, Smartphone, Loader2, Check } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const DISMISS_KEY = 'engineer_shell_nudge_dismissed_at';
const FOURTEEN_DAYS_MS = 14 * 24 * 60 * 60 * 1000;

const isStandalone = () =>
  typeof window !== 'undefined' && (
    window.matchMedia('(display-mode: standalone)').matches
    || window.navigator.standalone === true
  );

const isIOS = () =>
  typeof navigator !== 'undefined'
  && /iPad|iPhone|iPod/.test(navigator.userAgent)
  && !window.MSStream;

const urlBase64ToUint8Array = (base64String) => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) output[i] = rawData.charCodeAt(i);
  return output;
};

const pushSupported = () =>
  typeof window !== 'undefined'
  && 'serviceWorker' in navigator
  && 'PushManager' in window
  && typeof Notification !== 'undefined';

export default function EngineerAppShellNudge() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [pushPerm, setPushPerm] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'denied',
  );
  const [installed, setInstalled] = useState(isStandalone());
  const [busyPush, setBusyPush] = useState(false);
  const [busyInstall, setBusyInstall] = useState(false);
  const [showIosGuide, setShowIosGuide] = useState(false);
  const [hidden, setHidden] = useState(false);

  // Listen for the install prompt.
  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener('beforeinstallprompt', handler);
    const installedHandler = () => setInstalled(true);
    window.addEventListener('appinstalled', installedHandler);
    return () => {
      window.removeEventListener('beforeinstallprompt', handler);
      window.removeEventListener('appinstalled', installedHandler);
    };
  }, []);

  // Cooldown check.
  useEffect(() => {
    const ts = Number(localStorage.getItem(DISMISS_KEY) || 0);
    if (ts && Date.now() - ts < FOURTEEN_DAYS_MS) setHidden(true);
  }, []);

  if (hidden) return null;

  const pushNeeded = pushSupported() && pushPerm !== 'granted' && pushPerm !== 'denied';
  const installNeeded = !installed && (deferredPrompt || isIOS());
  if (!pushNeeded && !installNeeded) return null;

  const subscribe = async () => {
    if (!pushSupported()) return;
    setBusyPush(true);
    try {
      const perm = await Notification.requestPermission();
      setPushPerm(perm);
      if (perm !== 'granted') {
        notify.error('Notifications blocked', 'Enable them in browser settings.');
        return;
      }
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;
      const keyRes = await axios.get(`${API}/svc/engineer/push/vapid-key`, auth());
      const applicationServerKey = urlBase64ToUint8Array(keyRes.data.public_key);
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
      }
      await axios.post(
        `${API}/svc/engineer/push/subscribe`,
        { subscription: sub.toJSON(), user_agent: navigator.userAgent },
        auth(),
      );
      notify.success('Push alerts on', 'You\'ll be notified of job assignments + reminders.');
    } catch (e) {
      notify.error('Subscribe failed', e?.message || String(e));
    } finally { setBusyPush(false); }
  };

  const install = async () => {
    setBusyInstall(true);
    try {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const result = await deferredPrompt.userChoice;
        if (result.outcome === 'accepted') setInstalled(true);
        setDeferredPrompt(null);
      } else if (isIOS()) {
        setShowIosGuide(true);
      }
    } finally { setBusyInstall(false); }
  };

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setHidden(true);
  };

  return (
    <>
      <div
        className="rounded-2xl bg-gradient-to-br from-indigo-50 via-white to-blue-50 border border-indigo-200 p-3"
        data-testid="engineer-shell-nudge"
      >
        <div className="flex items-start gap-2">
          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center flex-shrink-0">
            <Bell size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-700">
              Get the full experience
            </p>
            <p className="text-xs text-slate-700 leading-snug">
              {pushNeeded && installNeeded
                ? 'Enable alerts so you don\'t miss new jobs, and add the app to your home screen for one-tap access.'
                : pushNeeded
                  ? 'Enable push alerts so dispatch can reach you for new jobs and PPM reminders.'
                  : 'Add the app to your home screen for one-tap, full-screen access.'}
            </p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            className="w-7 h-7 rounded-full hover:bg-white/60 flex items-center justify-center text-slate-500"
            aria-label="Dismiss"
            data-testid="engineer-shell-nudge-dismiss"
          >
            <X size={13} />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {pushNeeded && (
            <button
              type="button"
              onClick={subscribe}
              disabled={busyPush}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold disabled:opacity-50"
              data-testid="engineer-shell-nudge-push"
            >
              {busyPush ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />}
              Enable push alerts
            </button>
          )}
          {installNeeded && (
            <button
              type="button"
              onClick={install}
              disabled={busyInstall}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold disabled:opacity-50"
              data-testid="engineer-shell-nudge-install"
            >
              {busyInstall ? <Loader2 size={12} className="animate-spin" />
                : isIOS() ? <Smartphone size={12} /> : <Download size={12} />}
              {isIOS() ? 'Add to Home Screen' : 'Install app'}
            </button>
          )}
          {pushPerm === 'granted' && installed && (
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold"
              data-testid="engineer-shell-nudge-done"
            >
              <Check size={12} /> All set
            </span>
          )}
        </div>
      </div>
      {showIosGuide && (
        <IosGuide onClose={() => setShowIosGuide(false)} />
      )}
    </>
  );
}

function IosGuide({ onClose }) {
  return (
    <div
      className="fixed inset-0 z-[300] flex items-end sm:items-center justify-center bg-slate-900/70"
      onClick={onClose}
      data-testid="engineer-shell-nudge-ios-guide"
    >
      <div
        className="w-full max-w-sm bg-white rounded-t-3xl sm:rounded-3xl shadow-xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-sm font-bold text-slate-900 mb-2">Add to Home Screen</p>
        <ol className="text-xs text-slate-700 space-y-2 mb-3">
          <li><span className="font-bold">1.</span> Tap the <Smartphone size={11} className="inline -mt-0.5" /> Share button at the bottom of Safari.</li>
          <li><span className="font-bold">2.</span> Tap <span className="font-bold">"Add to Home Screen"</span>.</li>
          <li><span className="font-bold">3.</span> Tap <span className="font-bold">"Add"</span> in the top-right.</li>
        </ol>
        <button
          type="button"
          onClick={onClose}
          className="w-full px-3 py-2 rounded-xl bg-blue-600 text-white text-sm font-bold"
          data-testid="engineer-shell-nudge-ios-close"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
