import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

// ─── Sentry error tracking ──────────────────────────────────────────
// Optional: only boots when REACT_APP_SENTRY_DSN is set at build time.
// Zero runtime cost when unset — ship the wiring now so flipping Sentry
// on later is a one-line env change, no code deploy required.
const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN;
if (SENTRY_DSN) {
  // Use a synchronous import via webpack's dynamic require so the bundle
  // includes Sentry only when DSN is set. ESLint's no-undef warning
  // about `require` is a false positive in CRA — webpack provides it.
  // eslint-disable-next-line no-undef
  const Sentry = require("@sentry/react");
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.REACT_APP_SENTRY_ENV || "production",
    release: process.env.REACT_APP_SENTRY_RELEASE || undefined,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: Number(process.env.REACT_APP_SENTRY_TRACES_RATE || 0.05),
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  });
}

const BootSpinner = () => (
  <div data-testid="app-boot-spinner" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
    <div style={{ width: 32, height: 32, border: '3px solid rgba(255,255,255,0.15)', borderTopColor: '#fff', borderRadius: '50%', animation: 'boot-spin 0.8s linear infinite' }} />
    <style>{'@keyframes boot-spin{to{transform:rotate(360deg)}}'}</style>
  </div>
);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <React.Suspense fallback={<BootSpinner />}>
      <App />
    </React.Suspense>
  </React.StrictMode>,
);

// Service worker: register on the field/desk app surfaces so the
// Service Desk + Engineer App are installable (Android Chrome needs an
// active SW with a fetch handler to fire the install prompt) and work
// offline on flaky gym Wi-Fi. The SW itself is network-first for the app
// shell + JS/CSS, so updates always land on the next reload. On every
// other route we proactively unregister to keep marketing/SEO pages free
// of any caching layer.
if ('serviceWorker' in navigator) {
  const _path = window.location.pathname.toLowerCase();
  const _pwaScopes = ['/service-desk', '/svc/engineer', '/partner-engineer', '/bfpo', '/modservice'];
  const _enablePwa = _pwaScopes.some((p) => _path.startsWith(p));
  window.addEventListener('load', () => {
    if (_enablePwa) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    } else {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        registrations.forEach((reg) => reg.unregister());
      });
    }
  });
}
