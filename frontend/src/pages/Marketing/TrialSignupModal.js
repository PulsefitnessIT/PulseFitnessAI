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
 *
 * Iter 216h219 — Two-step flow to capture richer org intel without
 * tanking conversion:
 *   Step 1 (5 fields, unchanged): name, email, company, phone, password.
 *   Step 2 (NEW, all optional, skippable): website, industry, team
 *           size, "how did you hear about us?". Submitted via PATCH
 *           /api/account/organisation once the user is signed in.
 * Also silently captures UTM tags from the landing URL so the Master
 * Admin → Organisations panel shows the exact campaign that drove
 * the signup.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, X, CheckCircle2, Loader2, Zap } from 'lucide-react';

import { useAuth } from '../../App';
import Turnstile from '../../components/shared/Turnstile';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Mirrors AdminOrganizations.js so Master Admin sees a clean dropdown
// instead of free-text fragments. Keep these two lists in sync.
const INDUSTRY_OPTIONS = [
  'Fitness & Leisure', 'Healthcare', 'Manufacturing', 'Technology', 'Retail',
  'Construction', 'Education', 'Finance', 'Hospitality', 'Property', 'Other',
];
const EMPLOYEE_RANGES = ['1-10', '11-50', '51-200', '201-500', '501-1000', '1000+'];
const REFERRAL_SOURCES = [
  'Google search', 'LinkedIn', 'Facebook / Instagram', 'X (Twitter)',
  'Industry event', 'Referred by a friend', 'Press / article', 'Other',
];

/** Pluck utm_* tags from the current URL once on mount. */
function readUtmTags() {
  if (typeof window === 'undefined') return {};
  try {
    const p = new URLSearchParams(window.location.search);
    const out = {};
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'].forEach((k) => {
      const v = p.get(k);
      if (v) out[k] = v.slice(0, 200);
    });
    return out;
  } catch (_) {
    return {};
  }
}

export default function TrialSignupModal() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(1); // 1 = credentials, 2 = enrichment, 3 = success
  const [form, setForm] = useState({ full_name: '', email: '', company_name: '', phone: '', password: '' });
  const [extras, setExtras] = useState({ website: '', industry: '', employee_count: '', referral_source: '' });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [captchaToken, setCaptchaToken] = useState('');
  // Iter 216h227 — module intent captured from the CTA that opened
  // the modal (e.g. clicking "Start Free Trial" on the Marketing
  // module page sets this to "marketing"). Drives the per-module
  // activation milestones + onboarding checklist post-signup.
  const [primaryModule, setPrimaryModule] = useState('');
  const utmRef = useRef({});
  const navigate = useNavigate();
  const { login } = useAuth();

  // Open / close via window events so any CTA on any page can trigger it.
  useEffect(() => {
    const onOpen = (ev) => {
      utmRef.current = readUtmTags();
      // CTAs may pass { module: 'marketing' | 'crm' | 'operations' | 'memberships' }
      // via the CustomEvent detail. Default to '' so unannotated CTAs
      // keep their existing "show every module's milestones" behaviour.
      const mod = (ev?.detail?.module || '').toString().trim().toLowerCase();
      setPrimaryModule(['operations', 'memberships', 'crm', 'marketing'].includes(mod) ? mod : '');
      setOpen(true);
    };
    const onClose = () => setOpen(false);
    window.addEventListener('gymaxis:open-trial', onOpen);
    window.addEventListener('gymaxis:close-trial', onClose);
    return () => {
      window.removeEventListener('gymaxis:open-trial', onOpen);
      window.removeEventListener('gymaxis:close-trial', onClose);
    };
  }, []);

  // Reset state whenever the modal closes.
  useEffect(() => {
    if (!open) {
      setForm({ full_name: '', email: '', company_name: '', phone: '', password: '' });
      setExtras({ website: '', industry: '', employee_count: '', referral_source: '' });
      setStep(1);
      setShowPass(false);
      setCaptchaToken('');
      setPrimaryModule('');
      setError('');
    }
  }, [open]);

  // Esc-to-close + body-scroll lock.
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
  const updateExtra = (k) => (e) => setExtras((x) => ({ ...x, [k]: e.target.value }));
  const close = () => setOpen(false);

  // ── Step 1 submit: create the account + sign in. ──────────────────
  const submitStep1 = async (e) => {
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
        // Module intent — see useState comment above.
        primary_module: primaryModule || undefined,
        // Silent attribution — forwarded straight from the landing URL.
        ...utmRef.current,
      });
      if (!data?.token) throw new Error('Signup failed');
      login(data.token, data.user);
      setStep(2);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not start trial. Please check your details and try again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2 submit: persist org enrichment + go to dashboard. ──────
  const submitStep2 = async (e) => {
    e?.preventDefault();
    setError('');
    setLoading(true);
    try {
      // Only PATCH the fields the user actually filled in. Trim &
      // skip empties so we don't overwrite the org's other defaults.
      const payload = {};
      Object.entries(extras).forEach(([k, v]) => {
        const trimmed = (v || '').trim();
        if (trimmed) payload[k] = trimmed;
      });
      if (Object.keys(payload).length) {
        await axios.patch(`${API}/account/organisation`, payload, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        });
      }
      setStep(3);
      setTimeout(() => { close(); navigate('/dashboard', { replace: true }); }, 1200);
    } catch (err) {
      // Soft-fail: prospect is already in. Don't block their first
      // dashboard load over an optional profile field.
      setStep(3);
      setTimeout(() => { close(); navigate('/dashboard', { replace: true }); }, 1200);
    } finally {
      setLoading(false);
    }
  };

  const skipStep2 = () => {
    setStep(3);
    setTimeout(() => { close(); navigate('/dashboard', { replace: true }); }, 700);
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
        className="relative w-full max-w-md rounded-[28px] bg-white shadow-2xl border border-white/40 overflow-hidden dark:bg-zinc-900"
        data-testid="trial-modal"
      >
        {/* Brand halo */}
        <div className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 rounded-full opacity-30 blur-3xl"
             style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }} />

        <div className="relative">
          <div className="flex items-start justify-between p-6 pb-2">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-50 border border-slate-200 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
                <Zap size={11} /> 3-day free trial · all modules unlocked
              </span>
              <h2 className="mt-3 text-2xl font-black tracking-tight text-slate-900 dark:text-zinc-100" data-testid="trial-modal-title">
                {step === 1 && 'Start your trial'}
                {step === 2 && 'Tell us about your gym'}
                {step === 3 && "You're in!"}
              </h2>
              <p className="mt-1 text-sm text-slate-500" data-testid="trial-modal-subtitle">
                {step === 1 && 'Every module unlocked for 3 days. No credit card required.'}
                {step === 2 && 'Optional — helps us tailor your dashboard. Skip anytime.'}
                {step === 3 && 'Taking you to your dashboard…'}
              </p>
            </div>
            <button
              onClick={close}
              type="button"
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition dark:bg-zinc-900"
              data-testid="trial-modal-close"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          {/* Step indicator (only visible on step 2 — step 1 is the "real" signup) */}
          {step === 2 && (
            <div className="px-6 -mt-1 mb-1 flex items-center gap-1.5" data-testid="trial-modal-step-indicator">
              <span className="h-1 w-8 rounded-full bg-slate-900" />
              <span className="h-1 w-8 rounded-full bg-slate-900" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 ml-1">Step 2 of 2</span>
            </div>
          )}

          {/* ── Step 1 — credentials ─────────────────────────────── */}
          {step === 1 && (
            <form onSubmit={submitStep1} className="p-6 pt-2 space-y-3" data-testid="trial-modal-form">
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
                    className="w-full h-11 px-3 pr-14 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
                    placeholder="At least 8 characters"
                    data-testid="trial-password"
                  />
                  <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-[11px] font-semibold text-slate-500 hover:text-slate-900 dark:text-zinc-100" tabIndex={-1}>
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

          {/* ── Step 2 — org enrichment (all optional) ───────────── */}
          {step === 2 && (
            <form onSubmit={submitStep2} className="p-6 pt-2 space-y-3" data-testid="trial-modal-step2-form">
              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" data-testid="trial-modal-step2-error">{error}</div>
              )}
              <Field label="Website" value={extras.website} onChange={updateExtra('website')} placeholder="https://acmefitness.com" testid="trial-extra-website" optional />
              <SelectField
                label="Industry"
                value={extras.industry}
                onChange={updateExtra('industry')}
                options={INDUSTRY_OPTIONS}
                placeholder="Select..."
                testid="trial-extra-industry"
              />
              <SelectField
                label="Team size"
                value={extras.employee_count}
                onChange={updateExtra('employee_count')}
                options={EMPLOYEE_RANGES}
                placeholder="Select..."
                testid="trial-extra-employees"
              />
              <SelectField
                label="How did you hear about us?"
                value={extras.referral_source}
                onChange={updateExtra('referral_source')}
                options={REFERRAL_SOURCES}
                placeholder="Select..."
                testid="trial-extra-referral"
              />

              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={skipStep2}
                  className="flex-1 rounded-full px-4 py-3 text-sm font-semibold text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition dark:bg-zinc-900 dark:text-zinc-100"
                  data-testid="trial-step2-skip"
                  disabled={loading}
                >
                  Skip for now
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="gx-cta flex-1 inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-60"
                  data-testid="trial-step2-submit"
                >
                  {loading ? <><Loader2 size={14} className="animate-spin" /> Saving…</> : <>Save &amp; continue <ArrowRight size={14} /></>}
                </button>
              </div>

              <p className="text-center text-[11px] text-slate-400 pt-1">
                You can always update these later in Account Settings.
              </p>
            </form>
          )}

          {/* ── Step 3 — success ─────────────────────────────────── */}
          {step === 3 && (
            <div className="p-6 pt-2 text-center" data-testid="trial-modal-success">
              <div className="w-14 h-14 mx-auto rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mb-4">
                <CheckCircle2 size={28} className="text-emerald-500" />
              </div>
              <h3 className="text-slate-900 font-bold text-lg dark:text-zinc-100">You&apos;re in — welcome aboard.</h3>
              <p className="text-slate-500 text-sm mt-1">Taking you to the dashboard…</p>
            </div>
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
        className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
        data-testid={testid}
      />
    </div>
  );
}

function SelectField({ label, value, onChange, options, placeholder, testid }) {
  return (
    <div>
      <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">{label}</label>
      <select
        value={value}
        onChange={onChange}
        className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-slate-400 transition appearance-none dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
        data-testid={testid}
      >
        <option value="">{placeholder || 'Select...'}</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}

/** Helper any CTA can call. Also exported so JSX can use onClick={openTrial}.
 *
 * Iter 216h227 — pass an optional `module` so the post-signup
 * activation milestones + onboarding checklist tailor themselves to
 * what the prospect actually came in for:
 *
 *     <button onClick={() => openTrial('marketing')}>Start free trial</button>
 *
 * Valid modules: 'operations' | 'memberships' | 'crm' | 'marketing'.
 * Calls without an argument keep the legacy "show every module" behaviour.
 */
export function openTrial(module) {
  const detail = module ? { module } : undefined;
  window.dispatchEvent(new CustomEvent('gymaxis:open-trial', { detail }));
}
