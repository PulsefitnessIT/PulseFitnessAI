import { useEffect, useState, useCallback } from 'react';
import { AlertTriangle, LogIn } from 'lucide-react';

/**
 * Iter 216h68 — Session-resumed banner.
 *
 * Listens for the global `gymaxis:session-expired` event (fired by the
 * axios 401 interceptor in App.js when a silent refresh attempt fails).
 * Renders a sticky bottom-centre card that lets the operator re-auth
 * without losing their current page context — clicking "Sign in again"
 * routes to `/login?next=<current_path>` so they land back exactly
 * where they were.
 *
 * Designed for the long-running tablet / kiosk use case: a manager
 * leaves their browser open overnight, the JWT expires (>24 h), and
 * the next save attempt would normally hard-eject them to /login —
 * losing whatever they had unsaved. Now they see a friendly banner,
 * sign in, and continue.
 *
 * The banner suppresses itself on the /login route so it doesn't
 * stack on top of the login form.
 */
export default function SessionResumedBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onExpired = () => {
      // Don't fire on the login page (avoids double-display when the
      // user is already mid-relogin).
      const path = typeof window !== 'undefined' ? window.location.pathname : '/';
      if (path === '/login' || path === '/' || path.startsWith('/login/')) return;
      // The New Starter / Staff Portal (token-based auth) must not show the
      // main-app session-expired banner.
      if (path.startsWith('/new-starter/') || path.startsWith('/staff-portal')
          || path.startsWith('/staff-login') || path.startsWith('/staff-reset/')) return;
      setShow(true);
    };
    const onResumed = () => setShow(false);
    window.addEventListener('gymaxis:session-expired', onExpired);
    // The axios interceptor dispatches this when a silent refresh
    // succeeds DURING an active "expired" banner (e.g. another tab
    // re-authed and broadcast a token).
    window.addEventListener('gymaxis:token-refreshed', onResumed);
    return () => {
      window.removeEventListener('gymaxis:session-expired', onExpired);
      window.removeEventListener('gymaxis:token-refreshed', onResumed);
    };
  }, []);

  const handleSignIn = useCallback(() => {
    const here = typeof window !== 'undefined'
      ? window.location.pathname + window.location.search
      : '/dashboard';
    const next = encodeURIComponent(here);
    window.location.href = `/login?next=${next}`;
  }, []);

  if (!show) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[9999] max-w-md w-[calc(100%-2rem)] rounded-xl shadow-2xl border bg-white animate-in slide-in-from-bottom-3 fade-in-50 dark:bg-zinc-900"
      style={{
        borderColor: 'var(--color-warning)',
        boxShadow: '0 12px 32px rgba(0,0,0,0.18)',
      }}
      role="alertdialog"
      aria-live="assertive"
      data-testid="session-expired-banner"
    >
      <div className="flex items-start gap-3 p-4">
        <div
          className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center"
          style={{ background: 'var(--color-warning)15', color: 'var(--color-warning)' }}
        >
          <AlertTriangle size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-bold text-slate-900 dark:text-zinc-100">Your session has expired</h4>
          <p className="text-xs text-slate-600 mt-0.5">
            Sign in again to keep working. We'll bring you straight back to this page.
          </p>
        </div>
      </div>
      <div className="flex gap-2 px-4 pb-4">
        <button
          type="button"
          onClick={() => setShow(false)}
          className="px-3 py-1.5 text-xs font-medium rounded-md text-slate-600 hover:bg-slate-50 dark:bg-zinc-900"
          data-testid="session-banner-dismiss"
        >
          Dismiss
        </button>
        <button
          type="button"
          onClick={handleSignIn}
          className="flex-1 px-3 py-1.5 text-xs font-bold rounded-md flex items-center justify-center gap-1.5 hover:opacity-90 transition-opacity"
          style={{ background: 'var(--color-info-ios)', color: '#fff' }}
          data-testid="session-banner-signin"
        >
          <LogIn size={12} /> Sign in again
        </button>
      </div>
    </div>
  );
}
