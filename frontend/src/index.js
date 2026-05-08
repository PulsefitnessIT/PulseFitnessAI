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
  // eslint-disable-next-line no-undef, global-require
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

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Unregister any stale service workers and register fresh
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.getRegistrations().then(registrations => {
      registrations.forEach(reg => reg.unregister());
    });
  });
}
