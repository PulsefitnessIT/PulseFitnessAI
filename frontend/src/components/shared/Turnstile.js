/**
 * Turnstile — Cloudflare captcha widget wrapper.
 *
 * Loads the Turnstile script once per page, renders a managed-mode widget
 * and emits token via `onToken`. When the token expires it auto-resets
 * and emits an empty string so the parent form disables its submit button.
 *
 * Configured via REACT_APP_TURNSTILE_SITEKEY. If unset (dev without captcha)
 * the component renders nothing and immediately emits a synthetic token
 * `dev-bypass` so forms don't lock up on localhost — the backend fails open
 * when CAPTCHA_SECRET is absent, so this is safe.
 */
import { useEffect, useRef } from 'react';

const TURNSTILE_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
const SITEKEY = process.env.REACT_APP_TURNSTILE_SITEKEY;

// Global loader — at most one <script> tag per page, shared across modals.
let loaderPromise = null;
function loadTurnstileScript() {
  if (typeof window === 'undefined') return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (loaderPromise) return loaderPromise;

  loaderPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src^="${TURNSTILE_SRC.split('?')[0]}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', reject);
      if (window.turnstile) resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = TURNSTILE_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return loaderPromise;
}


export default function Turnstile({
  onToken,
  theme = 'auto',
  size = 'normal',
  action,
  className = '',
  testId = 'turnstile-widget',
}) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);

  // Dev fallback — no sitekey configured, emit a harmless token once.
  useEffect(() => {
    if (!SITEKEY) {
      onToken?.('dev-bypass');
    }
  }, [onToken]);

  useEffect(() => {
    if (!SITEKEY || !containerRef.current) return undefined;
    let cancelled = false;

    loadTurnstileScript()
      .then(() => {
        if (cancelled || !window.turnstile || !containerRef.current) return;
        const id = window.turnstile.render(containerRef.current, {
          sitekey: SITEKEY,
          theme,
          size,
          action,
          callback: (token) => onToken?.(token),
          'error-callback': () => onToken?.(''),
          'expired-callback': () => onToken?.(''),
          'timeout-callback': () => onToken?.(''),
        });
        widgetIdRef.current = id;
      })
      .catch(() => {
        // Script blocked (ad-blocker etc). Emit empty so the submit stays disabled.
        onToken?.('');
      });

    return () => {
      cancelled = true;
      if (widgetIdRef.current && window.turnstile?.remove) {
        try { window.turnstile.remove(widgetIdRef.current); } catch { /* ignore */ }
        widgetIdRef.current = null;
      }
    };
  // Intentionally only run once — re-rendering is destructive.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!SITEKEY) return null; // dev — nothing to render

  return (
    <div
      ref={containerRef}
      className={`turnstile-widget ${className}`}
      data-testid={testId}
    />
  );
}

export const TURNSTILE_ENABLED = Boolean(SITEKEY);
