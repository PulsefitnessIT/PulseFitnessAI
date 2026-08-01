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
 * If the email already belongs to an existing Pulse Fitness account, the
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

// Iter 271 — localized Partner Plan pricing, mirroring the apply form
// (PartnerApplyPublic.js). GB unchanged (£30 → £15); USD & EUR are
// 39.99 → 19.99; CAD/AUD mirror the same figures in their local symbol.
const PARTNER_PRICING = {
  GB: { base: '£30', discount: '£15' },
  US: { base: '$39.99', discount: '$19.99' },
  IE: { base: '€39.99', discount: '€19.99' },
  CA: { base: 'C$39.99', discount: 'C$19.99' },
  AU: { base: 'A$39.99', discount: 'A$19.99' },
};
const partnerPricing = (code) => PARTNER_PRICING[(code || '').toUpperCase()] || PARTNER_PRICING.GB;

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
        'This activation link is invalid or has expired. Please ask the Pulse Fitness team for a fresh one.'
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadInfo(); }, [loadInfo]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!password || password.length < 8) {
      setError('Choose a password of at least 12 characters (with an uppercase letter, number and symbol).');
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
        // Iter 227 — sentinel only; real JWT is in the HttpOnly cookie set
        // by /partners/activation/complete.
        localStorage.setItem('token', 'cookie');
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
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-teal-950 to-teal-900 text-slate-900 flex flex-col">
      <header className="border-b border-white/10 bg-white/95 backdrop-blur px-6 py-4 flex items-center justify-between shadow-sm">
        <Link to="/" className="text-sm font-extrabold tracking-tight text-slate-900">
          Pulse Fitness · <span className="text-teal-600">Engineer Partners</span>
        </Link>
        <Link to="/login" className="text-xs text-slate-500 hover:text-teal-600 font-bold" data-testid="activate-sign-in-link">
          Already have an account? Sign in
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {loading ? (
            <div className="flex flex-col items-center gap-3 py-12" data-testid="activate-loading">
              <Loader2 size={22} className="animate-spin text-teal-300" />
              <p className="text-sm text-white/80">Checking your activation link…</p>
            </div>
          ) : error && !info ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center" data-testid="activate-error-state">
              <AlertTriangle size={28} className="text-rose-500 mx-auto" />
              <h1 className="text-lg font-extrabold mt-3 text-slate-900">Link unavailable</h1>
              <p className="text-sm text-rose-700 mt-2">{error}</p>
              <a
                href="mailto:support@pulsefitness.ai?subject=Partner%20Engineer%20activation%20link"
                className="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-bold"
              >
                <Mail size={14} /> Email support for a new link
              </a>
            </div>
          ) : info?.has_existing_account ? (
            <div className="rounded-2xl border border-slate-200 bg-white shadow-xl p-6" data-testid="activate-existing-account">
              <ShieldCheck size={24} className="text-emerald-500" />
              <h1 className="text-xl font-extrabold mt-3 text-slate-900">Sign in to claim your approval</h1>
              <p className="text-sm text-slate-600 mt-2">
                We already have a Pulse Fitness account for <b className="text-slate-900">{info.email}</b>.
                Sign in there — we'll link your Partner Engineer record automatically and then
                take you straight to Stripe to start your {partnerPricing(info.country_code).base}/mo plan.
              </p>
              <button
                type="button"
                onClick={() => navigate(`/login?email=${encodeURIComponent(info.email)}&next=/partner-engineer?action=subscribe`)}
                className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-teal-600 hover:bg-teal-700 text-white text-sm font-bold shadow-lg shadow-teal-600/20"
                data-testid="activate-go-to-login"
              >
                Sign in <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <form
              onSubmit={submit}
              className="rounded-2xl border border-slate-200 bg-white shadow-xl p-6 space-y-4"
              data-testid="activate-form"
            >
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-teal-600">
                  Engineer Partner · Welcome
                </p>
                <h1 className="text-2xl font-extrabold mt-1 text-slate-900" data-testid="activate-headline">
                  Set up your sign-in, {((info?.full_name || '').split(' ')[0]) || 'there'}.
                </h1>
                <p className="text-sm text-slate-600 mt-2">
                  Choose a password — we'll create your Pulse Fitness account and take you straight to
                  Stripe to start your <b className="text-slate-900">{partnerPricing(info?.country_code).base}/mo Partner Plan</b>.
                </p>
              </div>

              {/* Email — pre-filled, read-only — applicants should not be able to
                  switch it without going via support. */}
              <label className="block">
                <span className="text-[11px] uppercase font-bold tracking-wider text-slate-500">Email</span>
                <div className="mt-1 relative">
                  <input
                    type="email"
                    value={info?.email || ''}
                    readOnly
                    className="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-800 text-sm font-mono"
                    data-testid="activate-email"
                  />
                  <Mail size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  This is the email you applied with. Need to change it?
                  {' '}
                  <a href="mailto:support@pulsefitness.ai" className="underline text-teal-600">contact support</a>.
                </p>
              </label>

              <label className="block">
                <span className="text-[11px] uppercase font-bold tracking-wider text-slate-500">
                  Choose a password
                </span>
                <div className="mt-1 relative">
                  <input
                    type={showPwd ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={12}
                    required
                    autoFocus
                    autoComplete="new-password"
                    placeholder="At least 12 characters"
                    className="w-full pl-9 pr-10 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 text-sm focus:outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-200"
                    data-testid="activate-password"
                  />
                  <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <button
                    type="button"
                    onClick={() => setShowPwd((s) => !s)}
                    aria-label={showPwd ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                  >
                    {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Aim for at least 12 characters with a mix of letters, numbers, and symbols.
                </p>
              </label>

              {error ? (
                <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2" data-testid="activate-error">
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={submitting}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white text-sm font-bold transition-colors shadow-lg shadow-teal-600/20"
                data-testid="activate-submit"
              >
                {submitting ? (
                  <><Loader2 size={14} className="animate-spin" /> Setting up your account…</>
                ) : (
                  <>Continue to Stripe ({partnerPricing(info?.country_code).base}/mo) <ArrowRight size={14} /></>
                )}
              </button>

              <div className="pt-2 border-t border-slate-100 mt-2 text-[11px] text-slate-500 space-y-1">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-600" />
                  Your application is already approved — this just creates your sign-in.
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-600" />
                  Stripe handles all payment details — we never see your card.
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-emerald-600" />
                  The {partnerPricing(info?.country_code).base}/mo fee drops as you refer gyms — free at 10 active sites.
                </div>
              </div>
            </form>
          )}
        </div>
      </main>

      <footer className="text-center text-[11px] text-white/70 py-6">
        Pulse Fitness · You can email <a href="mailto:support@pulsefitness.ai" className="underline text-teal-200 hover:text-white">support@pulsefitness.ai</a> any time.
      </footer>
    </div>
  );
}
