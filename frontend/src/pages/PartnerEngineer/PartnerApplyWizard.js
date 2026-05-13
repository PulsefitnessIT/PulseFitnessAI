/**
 * Partner Engineer — Apply Wizard (iter 216h75, Phase 1).
 *
 * Mobile-friendly multi-step onboarding for the Partner Engineer
 * Network. Calls POST /api/partners/apply (idempotent) at the end.
 * After approval by Master Admin, the engineer can sign into the
 * Engineer App at /svc/engineer with their referral link active.
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, ArrowLeft, CheckCircle2, Loader2, Wrench, MapPin,
  ShieldCheck, FileText, Sparkles,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const STEPS = [
  { id: 'intro',    label: 'Welcome' },
  { id: 'profile',  label: 'About you' },
  { id: 'area',     label: 'Service area' },
  { id: 'skills',   label: 'Skills & brands' },
  { id: 'terms',    label: 'Terms & submit' },
];

const API = process.env.REACT_APP_BACKEND_URL;

export default function PartnerApplyWizard() {
  const navigate = useNavigate();
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState({
    full_name: '',
    company_name: '',
    phone: '',
    service_postcode: '',
    travel_radius_km: 25,
    brands_supported: '',
    skills: '',
    qualifications: '',
    terms_accepted: false,
  });
  const [existing, setExisting] = useState(null);

  useEffect(() => {
    if (!token) { navigate('/login?next=/partner-engineer/apply'); return; }
    axios.get(`${API}/api/partners/me`, { headers })
      .then((r) => {
        const p = r.data?.partner;
        if (p) {
          setExisting(p);
          setProfile((cur) => ({
            ...cur,
            full_name: p.full_name || cur.full_name,
            company_name: p.company_name || cur.company_name,
            phone: p.phone || cur.phone,
            service_postcode: p.service_postcode || cur.service_postcode,
            travel_radius_km: p.travel_radius_km || 25,
            brands_supported: (p.brands_supported || []).join(', '),
            skills: (p.skills || []).join(', '),
            qualifications: (p.qualifications || []).join(', '),
          }));
        }
      })
      .catch(() => {});
  }, [headers, navigate, token]);

  const step = STEPS[stepIdx];
  const canBack = stepIdx > 0;
  const canNext = stepIdx < STEPS.length - 1;

  const submit = async () => {
    if (!profile.terms_accepted) {
      notify.error('You must accept the Partner Engineer terms.');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...profile,
        brands_supported: profile.brands_supported.split(',').map((s) => s.trim()).filter(Boolean),
        skills: profile.skills.split(',').map((s) => s.trim()).filter(Boolean),
        qualifications: profile.qualifications.split(',').map((s) => s.trim()).filter(Boolean),
      };
      await axios.post(`${API}/api/partners/apply`, payload, { headers });
      notify.success('Application submitted — we\'ll review and email you within 2 working days.');
      navigate('/partner-engineer');
    } catch (e) {
      notifyApiError(notify, e, 'Could not submit application');
    } finally {
      setBusy(false);
    }
  };

  if (existing?.status === 'approved') {
    // Already approved — bounce straight to dashboard.
    navigate('/partner-engineer');
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-50 via-white to-purple-50 dark:from-zinc-950 dark:via-zinc-900 dark:to-purple-950/40 py-10 px-4">
      <div className="max-w-2xl mx-auto" data-testid="partner-apply-wizard">
        {/* Stepper */}
        <div className="flex items-center justify-between mb-6 overflow-x-auto pb-2">
          {STEPS.map((s, i) => (
            <div key={s.id} className="flex items-center gap-2 min-w-0 flex-1" data-testid={`partner-step-${s.id}`}>
              <div className={
                'w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ' +
                (i <= stepIdx ? 'bg-purple-600 text-white' : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-500')}>
                {i < stepIdx ? <CheckCircle2 size={13} /> : i + 1}
              </div>
              <div className={'text-[11px] font-bold uppercase tracking-wider truncate ' +
                (i <= stepIdx ? 'text-purple-700 dark:text-purple-200' : 'text-zinc-400')}>
                {s.label}
              </div>
              {i < STEPS.length - 1 && (
                <div className={'h-0.5 flex-1 ' + (i < stepIdx ? 'bg-purple-500' : 'bg-zinc-200 dark:bg-zinc-800')} />
              )}
            </div>
          ))}
        </div>

        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
          {step.id === 'intro' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-purple-500">
                <Sparkles size={12} /> Partner Engineer Network
              </div>
              <h1 className="text-2xl font-black text-zinc-900 dark:text-zinc-100">Earn while you fix</h1>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Take jobs from your customers and from GymAxis-referred customers through the Engineer App, and earn ongoing commission on every gym you bring onto the platform.
              </p>
              <ul className="text-sm text-zinc-700 dark:text-zinc-300 space-y-2 mt-3">
                <li className="flex gap-2"><CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" /> 50% one-off reward on your referred customer's first Operations payment.</li>
                <li className="flex gap-2"><CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" /> £3/month recurring per active referred site.</li>
                <li className="flex gap-2"><CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" /> Partner App access: £30/mo → £15/mo at 5 active → free at 10+.</li>
                <li className="flex gap-2"><CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" /> Job-specific access only — no full-platform exposure.</li>
              </ul>
            </div>
          )}

          {step.id === 'profile' && (
            <div className="space-y-3">
              <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><Wrench size={16} /> About you</h2>
              <Field label="Full name" value={profile.full_name}
                onChange={(v) => setProfile((p) => ({ ...p, full_name: v }))} testId="partner-field-full-name" required />
              <Field label="Company name (optional)" value={profile.company_name}
                onChange={(v) => setProfile((p) => ({ ...p, company_name: v }))} testId="partner-field-company" />
              <Field label="Mobile" value={profile.phone}
                onChange={(v) => setProfile((p) => ({ ...p, phone: v }))} testId="partner-field-phone" />
            </div>
          )}

          {step.id === 'area' && (
            <div className="space-y-3">
              <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><MapPin size={16} /> Service area</h2>
              <Field label="Base postcode" placeholder="SW1A 1AA" value={profile.service_postcode}
                onChange={(v) => setProfile((p) => ({ ...p, service_postcode: v.toUpperCase() }))} testId="partner-field-postcode" required />
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Travel radius (km)</span>
                <input type="number" min={1} max={500} value={profile.travel_radius_km}
                  onChange={(e) => setProfile((p) => ({ ...p, travel_radius_km: Number(e.target.value || 25) }))}
                  className="mt-1 w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md bg-transparent text-sm"
                  data-testid="partner-field-radius" />
              </label>
            </div>
          )}

          {step.id === 'skills' && (
            <div className="space-y-3">
              <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><ShieldCheck size={16} /> Skills & brands</h2>
              <Field label="Brands supported (comma-separated)" placeholder="Life Fitness, Technogym, Matrix"
                value={profile.brands_supported}
                onChange={(v) => setProfile((p) => ({ ...p, brands_supported: v }))} testId="partner-field-brands" />
              <Field label="Skills (comma-separated)" placeholder="Cardio, strength, electrical, plumbing"
                value={profile.skills}
                onChange={(v) => setProfile((p) => ({ ...p, skills: v }))} testId="partner-field-skills" />
              <Field label="Qualifications (comma-separated, optional)" placeholder="NVQ Level 3, 17th Edition"
                value={profile.qualifications}
                onChange={(v) => setProfile((p) => ({ ...p, qualifications: v }))} testId="partner-field-quals" />
            </div>
          )}

          {step.id === 'terms' && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold mb-2 flex items-center gap-2"><FileText size={16} /> Partner Engineer terms</h2>
              <div className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-300 rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 max-h-44 overflow-auto bg-zinc-50 dark:bg-zinc-900/40 space-y-2">
                <p><strong>Eligibility</strong>: You must be a qualified fitness equipment engineer carrying suitable public liability insurance. GymAxis may request copies for verification.</p>
                <p><strong>Job access</strong>: You'll be granted job-specific access only — no full-platform visibility, no cross-customer data leakage.</p>
                <p><strong>Commission</strong>: Signup reward (50% of first cleared Operations payment) and recurring £3/month per active referred site. Both subject to Master Admin approval and refundable claw-back if the referred customer churns, is refunded, or was already in our pipeline.</p>
                <p><strong>App fee</strong>: £30/mo with automatic discounts (£15 at 5+ active referrals · free at 10+). Billed monthly via Stripe.</p>
                <p><strong>Termination</strong>: Either side can terminate with 14 days' notice. Master Admin may suspend on safety, fraud, or compliance grounds with immediate effect.</p>
              </div>
              <label className="flex items-start gap-2 text-sm cursor-pointer" data-testid="partner-accept-terms">
                <input type="checkbox" checked={profile.terms_accepted}
                  onChange={(e) => setProfile((p) => ({ ...p, terms_accepted: e.target.checked }))}
                  className="mt-1" />
                <span>I have read and accept the Partner Engineer terms.</span>
              </label>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 mt-6 pt-4 border-t border-zinc-100 dark:border-zinc-800">
            <button onClick={() => setStepIdx((i) => Math.max(0, i - 1))} disabled={!canBack}
              className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-100 disabled:opacity-40 inline-flex items-center gap-1"
              data-testid="partner-back-btn">
              <ArrowLeft size={12} /> Back
            </button>
            {canNext ? (
              <button onClick={() => setStepIdx((i) => Math.min(STEPS.length - 1, i + 1))}
                className="px-4 py-2 text-sm font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white inline-flex items-center gap-1.5"
                data-testid="partner-next-btn">
                Continue <ArrowRight size={13} />
              </button>
            ) : (
              <button onClick={submit} disabled={busy || !profile.terms_accepted}
                className="px-5 py-2 text-sm font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
                data-testid="partner-submit-btn">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                Submit application
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, required, testId }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">
        {label}{required && <span className="text-rose-500 ml-0.5">*</span>}
      </span>
      <input type="text" value={value || ''} placeholder={placeholder || ''}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md bg-transparent text-sm"
        data-testid={testId} />
    </label>
  );
}
