import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ShieldCheck, X, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Global step-up (fresh re-authentication) dialog.
 *
 * Mounted once at the app root. It registers `window.__pulseStepUp({mfa_enabled,
 * action})` which returns a Promise. The axios response interceptor (App.js)
 * calls it whenever the backend returns `403 {error:"step_up_required"}`,
 * awaits a successful re-auth, then transparently retries the original request.
 *
 * Challenge: an authenticator code when MFA is enrolled, otherwise the account
 * password — matching the backend `verify_step_up_challenge`.
 */
export default function StepUpDialog() {
  const [open, setOpen] = useState(false);
  const [opts, setOpts] = useState({});
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const resolverRef = useRef(null);

  useEffect(() => {
    window.__pulseStepUp = (o = {}) =>
      new Promise((resolve, reject) => {
        resolverRef.current = { resolve, reject };
        setOpts(o || {});
        setCode('');
        setPassword('');
        setErr('');
        setBusy(false);
        setOpen(true);
      });
    return () => {
      try { delete window.__pulseStepUp; } catch { /* noop */ }
    };
  }, []);

  const finish = (ok) => {
    setOpen(false);
    const r = resolverRef.current;
    resolverRef.current = null;
    if (r) {
      if (ok) r.resolve(true);
      else r.reject(new Error('step_up_cancelled'));
    }
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setBusy(true);
    setErr('');
    try {
      const token = localStorage.getItem('token');
      const body = opts.mfa_enabled ? { code: code.trim() } : { password };
      await axios.post(`${API}/auth/step-up`, body, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        withCredentials: true,
      });
      finish(true);
    } catch (e2) {
      const d = e2?.response?.data?.detail;
      setErr(typeof d === 'string' ? d : (d?.message || 'Verification failed. Please try again.'));
      setBusy(false);
    }
  };

  if (!open) return null;

  const label = (opts.action || '').replace(/_/g, ' ');

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      data-testid="step-up-dialog"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) finish(false); }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-2xl border border-white/10 bg-[var(--color-surface,#12151c)] p-6 shadow-2xl"
        style={{ color: 'var(--color-text, #e7ebf3)' }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-brand-blue,#2f6bff)]/15">
              <ShieldCheck className="h-5 w-5" style={{ color: 'var(--color-brand-blue,#2f6bff)' }} />
            </div>
            <div>
              <h2 className="text-base font-semibold leading-tight">Confirm it's you</h2>
              <p className="text-xs opacity-60">Extra check required for this action</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => finish(false)}
            disabled={busy}
            className="rounded-lg p-1 opacity-60 transition-opacity hover:opacity-100 disabled:opacity-30"
            data-testid="step-up-cancel-btn"
            aria-label="Cancel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-4 text-sm opacity-80">
          {label
            ? <>This is a sensitive action (<span className="font-medium">{label}</span>). </>
            : 'This is a sensitive action. '}
          {opts.mfa_enabled
            ? 'Enter your 6-digit authenticator code to continue.'
            : 'Re-enter your account password to continue.'}
        </p>

        <div className="mt-4">
          {opts.mfa_enabled ? (
            <input
              autoFocus
              inputMode="numeric"
              maxLength={8}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="123456"
              className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2.5 text-center text-lg tracking-[0.4em] outline-none focus:border-[var(--color-brand-blue,#2f6bff)]"
              data-testid="step-up-code-input"
            />
          ) : (
            <input
              autoFocus
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
              className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2.5 text-sm outline-none focus:border-[var(--color-brand-blue,#2f6bff)]"
              data-testid="step-up-password-input"
            />
          )}
        </div>

        {err && (
          <div className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400" data-testid="step-up-error">
            {err}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => finish(false)}
            disabled={busy}
            className="rounded-lg px-4 py-2 text-sm opacity-70 transition-opacity hover:opacity-100 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || (opts.mfa_enabled ? code.length < 6 : !password)}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-brand-blue,#2f6bff)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            data-testid="step-up-submit-btn"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy ? 'Verifying…' : 'Confirm'}
          </button>
        </div>
      </form>
    </div>
  );
}
