/**
 * Marketing-side "Start Free Trial" modal — opens in-place over any
 * MarketingShell page when the user clicks a Start Free Trial CTA.
 *
 * Design: light/glass theme matching the new GymAxis marketing spec
 * (Stripe / Salesforce premium feel). Posts to /api/auth/register
 * with is_trial=true and signs the user in immediately.
 *
 * Trigger: dispatch a window event from any CTA:
 *   window.dispatchEvent(new CustomEvent('gymaxis:open-trial'));
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, X, CheckCircle2, Loader2, Zap } from 'lucide-react';

import { useAuth } from '../../App';
import Turnstile from '../../components/shared/Turnstile';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TrialSignupModal() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: '', email: '', company_name: '', phone: '', password: '' });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [captchaToken, setCaptchaToken] = useState('');
  const navigate = useNavigate();
  const { login } = useAuth();

  // Open / close via window events so any CTA on any page can trigger it
  // without prop-drilling.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    const onClose = () => setOpen(false);
    window.addEventListener('gymaxis:open-trial', onOpen);
    window.addEventListener('gymaxis:close-trial', onClose);
    return () => {
      window.removeEventListener('gymaxis:open-trial', onOpen);
      window.removeEventListener('gymaxis:close-trial', onClose);
    };
  }, []);

  // Reset form whenever the modal closes.
  useEffect(() => {
    if (!open) {
      setForm({ full_name: '', email: '', company_name: '', phone: '', password: '' });
      setDone(false);
      setShowPass(false);
      setCaptchaToken('');
      setError('');
    }
  }, [open]);

  // Esc-to-close + body-scroll lock while open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const close = () => setOpen(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 8) { setError('Choose a password of at least 8 characters.'); return; }
    if (!captchaToken)            { setError('Please complete the verification check before continuing.'); return; }

    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/auth/register`, {
        email: form.email.trim().toLowerCase(),
        password: form.password,
        full_name: form.full_name.trim(),
        company_name: form.company_name.trim(),
        phone: form.phone.trim() || undefined,
        is_trial: true,
        trial_duration_days: 3,
        trial_unlock_all_modules: true,
        cf_turnstile_response: captchaToken,
      });
      if (!data?.token) throw new Error('Signup failed');
      login(data.token, data.user);
      setDone(true);
      setTimeout(() => { close(); navigate('/dashboard', { replace: true }); }, 1400);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not start trial. Please check your details and try again.');
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm"
      onClick={close}
      data-testid="trial-modal-overlay"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-[28px] bg-white shadow-2xl border border-white/40 overflow-hidden"
        data-testid="trial-modal"
      >
        {/* Brand halo */}
        <div className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 rounded-full opacity-30 blur-3xl"
             style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }} />

        <div className="relative">
          <div className="flex items-start justify-between p-6 pb-2">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-50 border border-slate-200 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600">
                <Zap size={11} /> 3-day free trial · all modules unlocked
              </span>
              <h2 className="mt-3 text-2xl font-black tracking-tight text-slate-900">Start your trial</h2>
              <p className="mt-1 text-sm text-slate-500">Every module unlocked for 3 days. No credit card required.</p>
            </div>
            <button
              onClick={close}
              type="button"
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition"
              data-testid="trial-modal-close"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          {done ? (
            <div className="p-6 pt-2 text-center" data-testid="trial-modal-success">
              <div className="w-14 h-14 mx-auto rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mb-4">
                <CheckCircle2 size={28} className="text-emerald-500" />
              </div>
              <h3 className="text-slate-900 font-bold text-lg">You&apos;re in — welcome aboard.</h3>
              <p className="text-slate-500 text-sm mt-1">Taking you to the dashboard…</p>
            </div>
          ) : (
            <form onSubmit={submit} className="p-6 pt-2 space-y-3" data-testid="trial-modal-form">
              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" data-testid="trial-modal-error">{error}</div>
              )}
              <Field label="Full name *" value={form.full_name} onChange={update('full_name')} placeholder="Jane Smith" testid="trial-name" />
              <Field label="Work email *" type="email" value={form.email} onChange={update('email')} placeholder="jane@yourgym.com" testid="trial-email" />
              <Field label="Gym / Company name *" value={form.company_name} onChange={update('company_name')} placeholder="Acme Fitness" testid="trial-company" />
              <Field label="Phone (optional)" type="tel" value={form.phone} onChange={update('phone')} placeholder="+44 7700 900123" testid="trial-phone" optional />
              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Password *</label>
                <div className="relative">
                  <input
                    type={showPass ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={form.password}
                    onChange={update('password')}
                    className="w-full h-11 px-3 pr-14 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition"
                    placeholder="At least 8 characters"
                    data-testid="trial-password"
                  />
                  <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-[11px] font-semibold text-slate-500 hover:text-slate-900" tabIndex={-1}>
                    {showPass ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>

              <div className="pt-1">
                <Turnstile onToken={setCaptchaToken} theme="light" testId="trial-turnstile" action="trial_signup" />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="gx-cta w-full inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-60 mt-2"
                data-testid="trial-submit"
              >
                {loading ? <><Loader2 size={14} className="animate-spin" /> Creating your account…</> : <>Start 3-day Trial <ArrowRight size={14} /></>}
              </button>

              <div className="flex items-center justify-center gap-4 text-[11px] text-slate-400 pt-1">
                <span className="flex items-center gap-1"><Zap size={10} /> Instant access</span>
                <span>·</span>
                <span>No credit card</span>
                <span>·</span>
                <span>Cancel anytime</span>
              </div>
              <p className="text-center text-[11px] text-slate-400 pt-1" data-testid="trial-modal-refund-note">
                You won&apos;t be charged during the 3-day trial. Read our{' '}
                <a href="/refunds" target="_blank" rel="noreferrer" className="underline hover:text-slate-700" data-testid="trial-modal-refund-link">refund &amp; cancellation policy</a>.
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', placeholder, testid, optional = false }) {
  return (
    <div>
      <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">{label}</label>
      <input
        type={type}
        required={!optional}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition"
        data-testid={testid}
      />
    </div>
  );
}

/** Helper any CTA can call. Also exported so JSX can use onClick={openTrial}. */
export function openTrial() {
  window.dispatchEvent(new CustomEvent('gymaxis:open-trial'));
}
