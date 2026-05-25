/**
 * PartnerEngineerActivate — Iter 219f.
 *
 * Public landing page for the single-use activation link sent in the
 * "You're approved" welcome email. Engineers arrive here from their
 * inbox with a `?token=…` query string. We:
 *
 *   1. Resolve the token against /api/partners/activation/info to
 *      pre-fill the form with the applicant's name + email (or to
 *      show a clean "this link is expired" fallback).
 *   2. Take a password, POST /api/partners/activation/complete which
 *      creates the user account, links the partner row, and returns a
 *      JWT + `next_url` (the Stripe Checkout deep-link).
 *   3. Store the token, then `window.location` to the Stripe URL so
 *      the engineer lands on Stripe Checkout for the £30/mo plan with
 *      zero further clicks.
 *
 * If the email already belongs to an existing GymAxis account, the
 * info endpoint flags `has_existing_account=true` and we show a
 * "Sign in to claim" prompt instead of a password form — the
 * auto-claim hook in /auth/login will link the partner row on
 * successful login.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  Loader2, CheckCircle2, AlertTriangle, ShieldCheck, ArrowRight,
  Mail, Eye, EyeOff, KeyRound,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PartnerEngineerActivate() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [info, setInfo] = useState(null); // {email, full_name, has_existing_account}
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const loadInfo = useCallback(async () => {
    if (!token) {
      setError('Missing activation token. Please use the link from your approval email.');
      setLoading(false);
      return;
    }
    try {
      const r = await axios.post(`${API}/api/partners/activation/info`, { token });
      setInfo(r.data);
    } catch (e) {
      setError(
        e?.response?.data?.detail ||
        'This activation link is invalid or has expired. Please ask the GymAxis team for a fresh one.'
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadInfo(); }, [loadInfo]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!password || password.length < 8) {
      setError('Choose a password of at least 8 characters.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const r = await axios.post(`${API}/api/partners/activation/complete`, {
        token,
        password,
      });
      const data = r.data || {};
      if (data.token) {
        localStorage.setItem('token', data.token);
      }
      // Hard-redirect to Stripe (or the dashboard auto-fire URL) so
      // the engineer lands on Checkout with the new auth in place.
      if (data.next_url) {
        window.location.href = data.next_url;
      } else {
        navigate('/partner-engineer?action=subscribe', { replace: true });
      }
    } catch (e2) {
      const detail = e2?.response?.data?.detail || 'Could not complete activation. Please try again.';
      setError(detail);
      setSubmitting(false);
    }
  };

  // ─── Frame ────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <header className="border-b border-zinc-800/80 px-6 py-4 flex items-center justify-between">
        <Link to="/" className="text-sm font-extrabold tracking-tight">
          GymAxis · <span className="text-purple-400">Engineer Partners</span>
        </Link>
        <Link to="/login" className="text-xs text-zinc-400 hover:text-white" data-testid="activate-sign-in-link">
          Already have an account? Sign in
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {loading ? (
            <div className="flex flex-col items-center gap-3 py-12" data-testid="activate-loading">
              <Loader2 size={22} className="animate-spin text-purple-400" />
              <p className="text-sm text-zinc-400">Checking your activation link…</p>
            </div>
          ) : error && !info ? (
            <div className="rounded-2xl border border-rose-700/40 bg-rose-900/20 p-6 text-center" data-testid="activate-error-state">
              <AlertTriangle size={28} className="text-rose-300 mx-auto" />
              <h1 className="text-lg font-extrabold mt-3">Link unavailable</h1>
              <p className="text-sm text-rose-100/80 mt-2">{error}</p>
              <a
                href="mailto:support@gymaxisai.com?subject=Partner%20Engineer%20activation%20link"
                className="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-full bg-white text-zinc-900 text-sm font-bold"
              >
                <Mail size={14} /> Email support for a new link
              </a>
            </div>
          ) : info?.has_existing_account ? (
            <div className="rounded-2xl border border-zinc-700/60 bg-zinc-900/70 p-6" data-testid="activate-existing-account">
              <ShieldCheck size={24} className="text-emerald-300" />
              <h1 className="text-xl font-extrabold mt-3">Sign in to claim your approval</h1>
              <p className="text-sm text-zinc-400 mt-2">
                We already have a GymAxis account for <b className="text-white">{info.email}</b>.
                Sign in there — we'll link your Partner Engineer record automatically and then
                take you straight to Stripe to start your £30/mo plan.
              </p>
              <button
                type="button"
                onClick={() => navigate(`/login?email=${encodeURIComponent(info.email)}&next=/partner-engineer?action=subscribe`)}
                className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-purple-500 hover:bg-purple-600 text-white text-sm font-bold"
                data-testid="activate-go-to-login"
              >
                Sign in <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <form
              onSubmit={submit}
              className="rounded-2xl border border-zinc-700/60 bg-zinc-900/70 p-6 space-y-4"
              data-testid="activate-form"
            >
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-purple-400">
                  Engineer Partner · Welcome
                </p>
                <h1 className="text-2xl font-extrabold mt-1" data-testid="activate-headline">
                  Set up your sign-in, {((info?.full_name || '').split(' ')[0]) || 'there'}.
                </h1>
                <p className="text-sm text-zinc-400 mt-2">
                  Choose a password — we'll create your GymAxis account and take you straight to
                  Stripe to start your <b className="text-white">£30/mo Partner Plan</b>.
                </p>
              </div>

              {/* Email — pre-filled, read-only — applicants should not be able to
                  switch it without going via support. */}
              <label className="block">
                <span className="text-[11px] uppercase font-bold tracking-wider text-zinc-400">Email</span>
                <div className="mt-1 relative">
                  <input
                    type="email"
                    value={info?.email || ''}
                    readOnly
                    className="w-full px-3 py-2.5 rounded-lg border border-zinc-700 bg-zinc-800/60 text-zinc-300 text-sm font-mono"
                    data-testid="activate-email"
                  />
                  <Mail size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                </div>
                <p className="text-[11px] text-zinc-500 mt-1">
                  This is the email you applied with. Need to change it?
                  {' '}
                  <a href="mailto:support@gymaxisai.com" className="underline">contact support</a>.
                </p>
              </label>

              <label className="block">
                <span className="text-[11px] uppercase font-bold tracking-wider text-zinc-400">
                  Choose a password
                </span>
                <div className="mt-1 relative">
                  <input
                    type={showPwd ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={8}
                    required
                    autoFocus
                    autoComplete="new-password"
                    placeholder="At least 8 characters"
                    className="w-full pl-9 pr-10 py-2.5 rounded-lg border border-zinc-700 bg-zinc-800 text-white text-sm focus:outline-none focus:border-purple-400"
                    data-testid="activate-password"
                  />
                  <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                  <button
                    type="button"
                    onClick={() => setShowPwd((s) => !s)}
                    aria-label={showPwd ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white"
                  >
                    {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 mt-1">
                  Aim for at least 12 characters with a mix of letters, numbers, and symbols.
                </p>
              </label>

              {error ? (
                <p className="text-xs text-rose-300 bg-rose-900/30 border border-rose-800/50 rounded-md px-3 py-2" data-testid="activate-error">
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={submitting}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-purple-500 hover:bg-purple-600 disabled:opacity-50 text-white text-sm font-bold transition-colors"
                data-testid="activate-submit"
              >
                {submitting ? (
                  <><Loader2 size={14} className="animate-spin" /> Setting up your account…</>
                ) : (
                  <>Continue to Stripe (£30/mo) <ArrowRight size={14} /></>
                )}
              </button>

              <div className="pt-2 border-t border-zinc-800/80 mt-2 text-[11px] text-zinc-500 space-y-1">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-400" />
                  Your application is already approved — this just creates your sign-in.
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-400" />
                  Stripe handles all payment details — we never see your card.
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-400" />
                  The £30/mo fee drops as you refer gyms — free at 10 active sites.
                </div>
              </div>
            </form>
          )}
        </div>
      </main>

      <footer className="text-center text-[11px] text-zinc-600 py-6">
        GymAxis · You can email <a href="mailto:support@gymaxisai.com" className="underline">support@gymaxisai.com</a> any time.
      </footer>
    </div>
  );
}
