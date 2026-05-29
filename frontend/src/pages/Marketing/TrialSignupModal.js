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
import ProfileCompletionFields, {
  emptyProfileForm, findMissingRequired,
} from '../../components/shared/ProfileCompletionFields';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
  const [step, setStep] = useState(1); // 1 = credentials, 2 = profile, 3 = success
  const [form, setForm] = useState({ full_name: '', email: '', company_name: '', phone: '', password: '' });
  const [profile, setProfile] = useState(emptyProfileForm());
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
      setProfile(emptyProfileForm());
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
  const close = () => setOpen(false);

  // ── Step 1 submit: create the account + sign in. ──────────────────
  const submitStep1 = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.phone.trim())       { setError('Please enter your contact phone number.'); return; }
    if (form.password.length < 8) { setError('Choose a password of at least 8 characters.'); return; }
    if (!captchaToken)            { setError('Please complete the verification check before continuing.'); return; }

    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/auth/register`, {
        email: form.email.trim().toLowerCase(),
        password: form.password,
        full_name: form.full_name.trim(),
        company_name: form.company_name.trim(),
        phone: form.phone.trim(),
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
      // Pre-fill the step-2 form with what we already know so the
      // operator doesn't retype their own contact details.
      setProfile((p) => ({
        ...p,
        primary_contact_name: form.full_name.trim(),
        primary_contact_phone: form.phone.trim(),
        primary_contact_email: form.email.trim().toLowerCase(),
      }));
      setStep(2);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not start trial. Please check your details and try again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2 submit: persist org enrichment + go to module home. ──
  // Iter 216h249 — route the new operator to their declared module
  // (Memberships / CRM / Marketing) instead of dumping every trial
  // user onto the Operations dashboard. Memberships users now land on
  // their own Start tab (add logo, add members) and never see the
  // Equipment wizard meant for gym operators.
  const moduleHome = () => {
    switch (primaryModule) {
      case 'memberships': return '/memberships';
      case 'crm':         return '/crm';
      case 'marketing':   return '/marketing';
      default:            return '/dashboard';
    }
  };
  const submitStep2 = async (e) => {
    e?.preventDefault();
    setError('');
    const missing = findMissingRequired(profile);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ').replace(/_/g, ' ')}`);
      return;
    }
    setLoading(true);
    try {
      // Strip the UI-only checkbox; clear company_phone when the
      // toggle is off so a stale value doesn't slip through.
      const {
        has_different_company_phone,
        company_search_query,
        ...payload
      } = profile;
      if (!has_different_company_phone) payload.company_phone = '';
      await axios.post(`${API}/account/complete-profile`, payload, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      setStep(3);
      setTimeout(() => { close(); navigate(moduleHome(), { replace: true }); }, 1200);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not save profile. Please try again.');
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
        className={`relative w-full ${step === 2 ? 'max-w-2xl' : 'max-w-md'} rounded-[28px] bg-white shadow-2xl border border-white/40 overflow-hidden dark:bg-zinc-900`}
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
                {step === 2 && 'A few details to finish setting up your account — required before we unlock the dashboard.'}
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
              <Field label="Phone *" type="tel" value={form.phone} onChange={update('phone')} placeholder="+44 7700 900123" testid="trial-phone" />
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

          {/* ── Step 2 — mandatory profile completion ────────────── */}
          {step === 2 && (
            <form onSubmit={submitStep2} className="px-6 pb-6 pt-2 max-h-[70vh] overflow-y-auto space-y-3" data-testid="trial-modal-step2-form">
              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" data-testid="trial-modal-step2-error">{error}</div>
              )}

              <ProfileCompletionFields form={profile} setForm={setProfile} />

              <button
                type="submit"
                disabled={loading}
                className="gx-cta w-full inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-60 mt-2"
                data-testid="trial-step2-submit"
              >
                {loading ? <><Loader2 size={14} className="animate-spin" /> Saving…</> : <>Save and unlock dashboard <ArrowRight size={14} /></>}
              </button>

              <p className="text-center text-[11px] text-slate-400 pt-1">
                Required before your trial dashboard opens. You can edit any of these later in Account Settings.
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
