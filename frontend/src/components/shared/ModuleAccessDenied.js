import { useState, useEffect } from 'react';
import { ShieldAlert, ArrowLeft } from 'lucide-react';

/**
 * Global friendly "module access needed" overlay.
 *
 * The axios response interceptor in App.js dispatches
 * `pulse:module-access-denied` whenever a backend module guard
 * (require_module / require_module_or_roles) returns a 403 tagged with the
 * `X-Module-Access-Denied` header. This is the safety net for the rare edge
 * case where a blocked API call slips past the UI route guards — instead of a
 * raw error/toast the user sees a clear "ask your administrator" screen with a
 * way back to an area they can use.
 */
export default function ModuleAccessDenied() {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    const onDenied = (e) => {
      setInfo({
        modules: e?.detail?.modules || '',
        message: e?.detail?.message || '',
      });
    };
    window.addEventListener('pulse:module-access-denied', onDenied);
    return () => window.removeEventListener('pulse:module-access-denied', onDenied);
  }, []);

  if (!info) return null;

  const primary = (info.modules || '').split(',')[0] || '';
  const label = primary ? primary.charAt(0).toUpperCase() + primary.slice(1) : 'this';
  const message = info.message
    || `You don't have access to the ${label} module. Ask your administrator to grant you access.`;

  const goBack = () => { setInfo(null); window.location.assign('/launch'); };

  return (
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center p-4"
      style={{ background: 'rgba(3, 7, 18, 0.72)', backdropFilter: 'blur(6px)' }}
      data-testid="module-access-denied"
      role="alertdialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md rounded-2xl p-8 text-center"
        style={{
          background: 'var(--theme-surface, #fff)',
          border: '1px solid var(--theme-border, #e5e7eb)',
          boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
        }}
      >
        <div
          className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center"
          style={{ background: '#f59e0b1f', color: '#d97706' }}
        >
          <ShieldAlert size={28} />
        </div>
        <h1
          className="mt-5 text-xl font-bold pulse-font-heading"
          style={{ color: 'var(--theme-text, #0f172a)' }}
          data-testid="module-access-denied-title"
        >
          Access needed
        </h1>
        <p
          className="mt-2 text-sm pulse-font-body"
          style={{ color: 'var(--theme-text-muted, #64748b)' }}
          data-testid="module-access-denied-message"
        >
          {message}
        </p>
        <div className="mt-7 flex flex-col gap-2">
          <button
            onClick={goBack}
            data-testid="module-access-denied-back-btn"
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition-colors"
            style={{ background: 'var(--pulse-primary, #0f172a)' }}
          >
            <ArrowLeft size={16} /> Back to my area
          </button>
        </div>
      </div>
    </div>
  );
}
