/**
 * Public Partner Engineer application form — iter 216h104.
 *
 * Lives at /partners/engineers/apply (no auth required). Submits a
 * multipart application + CV/certification uploads to the public
 * endpoint POST /api/partners/public-apply, which stores into the
 * `partner_applications` collection for Master Admin review.
 *
 * After approval the engineer gets an email magic-link to claim a
 * GymAxis account and finish onboarding via the existing wizard.
 */
import React, { useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import {
  ArrowRight, ArrowLeft, CheckCircle2, Loader2, Wrench, MapPin,
  ShieldCheck, FileText, Sparkles, Upload, Trash2, FileUp, Mail,
  HardHat,
} from 'lucide-react';

import MarketingShell from './MarketingShell';
import { useSeo } from '@/utils/seo';

const API = process.env.REACT_APP_BACKEND_URL;

const STEPS = [
  { id: 'profile',   label: 'About you',         icon: Wrench },
  { id: 'area',      label: 'Service area',      icon: MapPin },
  { id: 'skills',    label: 'Skills & insurance', icon: ShieldCheck },
  { id: 'uploads',   label: 'CV & supporting',   icon: FileUp },
  { id: 'terms',     label: 'Review & submit',   icon: FileText },
];

const MAX_FILE_MB = 10;
const ACCEPTED_EXT = '.pdf,.doc,.docx,.txt,.rtf,.png,.jpg,.jpeg';

function isValidEmail(e) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((e || '').trim());
}

function isValidUkPostcode(p) {
  if (!p) return true; // optional
  return /^[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}$/i.test((p || '').trim());
}

export default function PartnerApplyPublic() {
  useSeo({
    title: 'Apply — Partner Engineer Network · GymAxis AI',
    description: 'Apply to join the GymAxis Partner Engineer Network. Upload your CV and certifications — most decisions within 2 working days.',
    canonical: 'https://www.gymaxisai.com/partners/engineers/apply',
  });

  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(null); // { application_id, message }
  const [errors, setErrors] = useState({});
  const [profile, setProfile] = useState({
    full_name: '',
    email: '',
    phone: '',
    company_name: '',
    service_postcode: '',
    travel_radius_km: 25,
    brands_supported: '',
    skills: '',
    qualifications: '',
    years_experience: '',
    has_insurance: false,
    insurance_provider: '',
    referral_source: '',
    cover_letter: '',
    terms_accepted: false,
  });
  const [cvFile, setCvFile] = useState(null);
  const [certFile, setCertFile] = useState(null);
  const cvInputRef = useRef(null);
  const certInputRef = useRef(null);

  const step = STEPS[stepIdx];

  const setField = (key) => (e) => {
    const v = e && e.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e;
    setProfile((p) => ({ ...p, [key]: v }));
    if (errors[key]) setErrors((er) => ({ ...er, [key]: null }));
  };

  const handleFile = (kind) => (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > MAX_FILE_MB * 1024 * 1024) {
      setErrors((er) => ({ ...er, [kind]: `File is too large — keep under ${MAX_FILE_MB} MB` }));
      e.target.value = '';
      return;
    }
    setErrors((er) => ({ ...er, [kind]: null }));
    if (kind === 'cv') setCvFile(f);
    else setCertFile(f);
  };

  const validateStep = () => {
    const er = {};
    if (step.id === 'profile') {
      if (!profile.full_name.trim()) er.full_name = 'Required';
      if (!isValidEmail(profile.email)) er.email = 'Enter a valid email so we can contact you';
      // Iter 216h216 — Craig's audit: mobile must be mandatory.
      // Engineers without phones can't be dispatched to urgent jobs.
      const p = (profile.phone || '').trim();
      if (!p) er.phone = 'Required — we need to reach you for urgent jobs';
      else if (p.replace(/\D/g, '').length < 7) er.phone = 'Looks too short — full mobile number please';
    }
    if (step.id === 'area') {
      if (profile.service_postcode && !isValidUkPostcode(profile.service_postcode)) {
        er.service_postcode = 'Looks like an invalid UK postcode';
      }
      // Iter 216h216 — Craig's audit: 2km is unworkable. Set min 5km.
      const r = Number(profile.travel_radius_km || 0);
      if (!r || r < 5) er.travel_radius_km = 'Set a sensible travel radius — minimum 5 km';
      if (r > 500) er.travel_radius_km = 'Cap your radius at 500 km';
    }
    if (step.id === 'terms' && !profile.terms_accepted) {
      er.terms_accepted = 'Please accept the Partner Engineer terms';
    }
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const goNext = () => {
    if (!validateStep()) return;
    setStepIdx((i) => Math.min(STEPS.length - 1, i + 1));
  };
  const goBack = () => setStepIdx((i) => Math.max(0, i - 1));

  const submit = async () => {
    if (!validateStep()) return;
    setBusy(true);
    try {
      const fd = new FormData();
      Object.entries(profile).forEach(([k, v]) => {
        fd.append(k, typeof v === 'boolean' ? String(v) : (v ?? ''));
      });
      if (cvFile) fd.append('cv_file', cvFile);
      if (certFile) fd.append('cert_file', certFile);
      const r = await axios.post(`${API}/api/partners/public-apply`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSubmitted(r.data || { message: 'Application received.' });
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || 'Submission failed';
      setErrors((er) => ({ ...er, _submit: typeof detail === 'string' ? detail : 'Submission failed' }));
    } finally {
      setBusy(false);
    }
  };

  const completedSteps = useMemo(() => stepIdx, [stepIdx]);

  if (submitted) {
    return (
      <MarketingShell>
        <section className="py-20 md:py-28" data-testid="pe-apply-success">
          <div className="max-w-2xl mx-auto px-6 lg:px-8">
            <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-8 md:p-12 text-center">
              <div className="w-16 h-16 mx-auto mb-5 rounded-full bg-emerald-600 text-white flex items-center justify-center">
                <CheckCircle2 size={32} />
              </div>
              <h1 className="text-3xl md:text-4xl font-black tracking-tight text-slate-900">Application received</h1>
              <p className="mt-4 text-base text-slate-700 leading-relaxed">
                {submitted.message || "Thanks — we'll review your application and email you within 2 working days."}
              </p>
              <p className="mt-3 text-xs text-slate-500">Reference: <span className="font-mono">{submitted.application_id}</span></p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                {/* Iter 216h216 — was bg-slate-900 (black-on-black look on
                    iOS Safari where the label rendered against dark area
                    of the gradient bg). Switched to the brand gradient
                    button class with explicit white text. */}
                <Link to="/partners/engineers"
                  className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 text-white px-6 py-3 text-sm font-bold shadow-sm transition"
                  data-testid="pe-apply-back-network">
                  Back to network <ArrowRight size={14} />
                </Link>
                <Link to="/" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-100">
                  Home
                </Link>
              </div>
            </div>
          </div>
        </section>
      </MarketingShell>
    );
  }

  return (
    <MarketingShell>
      <section className="py-12 md:py-16" data-testid="partner-apply-public">
        <div className="max-w-3xl mx-auto px-6 lg:px-8">
          {/* Header */}
          <div className="mb-8">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600">
              <HardHat size={12} /> Partner Engineer · application
            </span>
            <h1 className="mt-4 text-3xl md:text-4xl lg:text-5xl tracking-tight font-black leading-[1.04]">
              Apply to the <span className="gx-gradient-text">Engineer Network.</span>
            </h1>
            <p className="mt-3 text-base text-slate-600 leading-relaxed">
              5-minute form. Upload your CV and any qualifications — we'll review and email you within 2 working days. No GymAxis account needed yet.
            </p>
          </div>

          {/* Stepper — Iter 216h216: Craig's audit flagged steps cut off
              on mobile. Refactored:
                • Mobile: pill row scrolls horizontally with snap, AND a
                  "Step X of N" label appears above so context is never lost.
                • Desktop: full inline stepper with connecting lines as before. */}
          <div className="mb-3 sm:hidden text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500"
               data-testid="partner-apply-stepper-mobile-label">
            Step {stepIdx + 1} of {STEPS.length} · <span className="text-slate-900">{step.label}</span>
          </div>
          <div className="flex items-center mb-6 gap-2 overflow-x-auto pb-2 snap-x snap-mandatory"
               data-testid="partner-apply-stepper">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const reached = i <= completedSteps;
              return (
                <div key={s.id}
                  className="flex items-center gap-2 shrink-0 snap-start sm:min-w-0 sm:flex-1"
                  data-testid={`partner-apply-step-${s.id}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                    reached ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-400'
                  }`}>
                    {i < stepIdx ? <CheckCircle2 size={14} /> : <Icon size={14} />}
                  </div>
                  <div className={`text-[11px] font-bold uppercase tracking-wider whitespace-nowrap ${
                    reached ? 'text-slate-800' : 'text-slate-400'
                  }`}>{s.label}</div>
                  {i < STEPS.length - 1 && (
                    <div className={`hidden sm:block h-0.5 flex-1 ${i < stepIdx ? 'bg-slate-900' : 'bg-slate-200'}`} />
                  )}
                </div>
              );
            })}
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-6 md:p-8 shadow-sm">
            {/* Profile */}
            {step.id === 'profile' && (
              <div className="space-y-4">
                <h2 className="text-lg font-bold flex items-center gap-2"><Wrench size={16} /> About you</h2>
                <Field label="Full name" required error={errors.full_name} testId="pe-apply-name"
                  value={profile.full_name} onChange={setField('full_name')} />
                <Field label="Email" required type="email" error={errors.email} testId="pe-apply-email"
                  placeholder="you@example.com" value={profile.email} onChange={setField('email')} />
                <Field label="Mobile" required type="tel" testId="pe-apply-phone"
                  placeholder="07700 900000"
                  error={errors.phone}
                  value={profile.phone} onChange={setField('phone')} />
                <Field label="Company / trading name (optional)" testId="pe-apply-company"
                  value={profile.company_name} onChange={setField('company_name')} />
              </div>
            )}

            {/* Area */}
            {step.id === 'area' && (
              <div className="space-y-4">
                <h2 className="text-lg font-bold flex items-center gap-2"><MapPin size={16} /> Service area</h2>
                <Field label="Base postcode" placeholder="SW1A 1AA" testId="pe-apply-postcode"
                  error={errors.service_postcode}
                  value={profile.service_postcode}
                  onChange={(e) => setField('service_postcode')({ target: { value: (e?.target?.value || '').toUpperCase() } })} />
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wider font-bold text-slate-500">
                    Travel radius (km) <span className="text-rose-500" aria-hidden>*</span>
                  </span>
                  <input type="number" min={5} max={500} value={profile.travel_radius_km}
                    onChange={(e) => {
                      const n = Number(e.target.value || 25);
                      setProfile((p) => ({ ...p, travel_radius_km: n }));
                      if (errors.travel_radius_km) setErrors((er) => ({ ...er, travel_radius_km: null }));
                    }}
                    className={`mt-1.5 w-full px-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:border-slate-900 ${
                      errors.travel_radius_km ? 'border-rose-400' : 'border-slate-200'
                    }`}
                    data-testid="pe-apply-radius" />
                  <span className="block text-[11px] text-slate-400 mt-1">Minimum 5 km — covers your home patch + a couple of clusters.</span>
                  {errors.travel_radius_km && (
                    <span className="block text-[11px] font-semibold text-rose-500 mt-1" data-testid="pe-apply-radius-error">
                      {errors.travel_radius_km}
                    </span>
                  )}
                </label>
              </div>
            )}

            {/* Skills + insurance */}
            {step.id === 'skills' && (
              <div className="space-y-4">
                <h2 className="text-lg font-bold flex items-center gap-2"><ShieldCheck size={16} /> Skills & insurance</h2>
                <Field label="Brands supported (comma-separated)" placeholder="Life Fitness, Technogym, Matrix, Precor"
                  testId="pe-apply-brands"
                  value={profile.brands_supported} onChange={setField('brands_supported')} />
                <Field label="Skills (comma-separated)" placeholder="Cardio, strength, electrical, plumbing, plate-loaded"
                  testId="pe-apply-skills"
                  value={profile.skills} onChange={setField('skills')} />
                <Field label="Qualifications (comma-separated)" placeholder="IOSH, PAT, CSCS, 18th Edition, NVQ Level 3"
                  testId="pe-apply-quals"
                  value={profile.qualifications} onChange={setField('qualifications')} />
                <Field label="Years of experience" placeholder="e.g. 8" testId="pe-apply-years"
                  value={profile.years_experience} onChange={setField('years_experience')} />
                <label className="flex items-center gap-2 cursor-pointer text-sm" data-testid="pe-apply-insurance-toggle">
                  <input type="checkbox" checked={profile.has_insurance} onChange={setField('has_insurance')} />
                  <span>I currently hold public liability insurance</span>
                </label>
                {profile.has_insurance && (
                  <Field label="Insurance provider (optional)" testId="pe-apply-insurer"
                    value={profile.insurance_provider} onChange={setField('insurance_provider')} />
                )}
                <Field label="How did you hear about us? (optional)" placeholder="Referral, Google, LinkedIn, trade show…"
                  testId="pe-apply-source"
                  value={profile.referral_source} onChange={setField('referral_source')} />
              </div>
            )}

            {/* Uploads */}
            {step.id === 'uploads' && (
              <div className="space-y-4">
                <h2 className="text-lg font-bold flex items-center gap-2"><FileUp size={16} /> CV & supporting documents</h2>
                <p className="text-sm text-slate-600">
                  Upload your CV or a service portfolio. You can also attach scanned certifications (PAT, IOSH, CSCS, 18th Edition) — anything that helps build your profile. Accepted: PDF, DOC/DOCX, TXT, RTF, PNG, JPG · max {MAX_FILE_MB} MB each.
                </p>

                <FileDropTile
                  label="CV / résumé"
                  file={cvFile}
                  onClear={() => setCvFile(null)}
                  onPick={() => cvInputRef.current?.click()}
                  testId="pe-apply-cv-tile"
                />
                <input ref={cvInputRef} type="file" accept={ACCEPTED_EXT} className="hidden"
                  onChange={handleFile('cv')} data-testid="pe-apply-cv-input" />
                {errors.cv && <p className="text-xs text-rose-600">{errors.cv}</p>}

                <FileDropTile
                  label="Certifications / portfolio (optional)"
                  file={certFile}
                  onClear={() => setCertFile(null)}
                  onPick={() => certInputRef.current?.click()}
                  testId="pe-apply-cert-tile"
                />
                <input ref={certInputRef} type="file" accept={ACCEPTED_EXT} className="hidden"
                  onChange={handleFile('cert')} data-testid="pe-apply-cert-input" />
                {errors.cert && <p className="text-xs text-rose-600">{errors.cert}</p>}

                <div>
                  <span className="text-[11px] uppercase tracking-wider font-bold text-slate-500">A few words about yourself (optional)</span>
                  <textarea rows={4} maxLength={4000}
                    value={profile.cover_letter}
                    onChange={setField('cover_letter')}
                    placeholder="Why do you want to join the network? Any particular gym chains you already work with?"
                    className="mt-1.5 w-full px-3 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-900"
                    data-testid="pe-apply-cover-letter" />
                </div>
              </div>
            )}

            {/* Terms */}
            {step.id === 'terms' && (
              <div className="space-y-4">
                <h2 className="text-lg font-bold flex items-center gap-2"><FileText size={16} /> Review & submit</h2>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 space-y-1">
                  <Summary label="Name" value={profile.full_name || '—'} />
                  <Summary label="Email" value={profile.email || '—'} />
                  <Summary label="Phone" value={profile.phone || '—'} />
                  <Summary label="Company" value={profile.company_name || '—'} />
                  <Summary label="Postcode" value={profile.service_postcode || '—'} />
                  <Summary label="Travel radius" value={`${profile.travel_radius_km} km`} />
                  <Summary label="Brands" value={profile.brands_supported || '—'} />
                  <Summary label="Skills" value={profile.skills || '—'} />
                  <Summary label="Qualifications" value={profile.qualifications || '—'} />
                  <Summary label="Experience" value={profile.years_experience ? `${profile.years_experience} years` : '—'} />
                  <Summary label="Insurance" value={profile.has_insurance ? `Yes${profile.insurance_provider ? ` · ${profile.insurance_provider}` : ''}` : 'Not yet — we can help'} />
                  <Summary label="CV attached" value={cvFile ? cvFile.name : 'No file'} />
                  <Summary label="Certifications attached" value={certFile ? certFile.name : 'No file'} />
                </div>

                <div className="rounded-2xl border border-slate-200 p-4 text-xs leading-relaxed text-slate-600 space-y-2 max-h-48 overflow-auto bg-white">
                  <p><strong>Eligibility</strong>: You must be a qualified fitness equipment engineer. Public liability insurance is required before you accept a job (we can help you get covered).</p>
                  <p><strong>Job access</strong>: You'll be granted job-specific access only — no full-platform visibility, no cross-customer data leakage.</p>
                  <p><strong>Commission</strong>: 50% of the referred gym's first cleared Operations payment (one-off) + £3/site per month recurring for as long as the gym stays on the platform. Both released after the referred gym has been active for 3 months. Subject to Master Admin approval and refundable claw-back.</p>
                  <p><strong>App fee</strong>: £30/mo with automatic discounts (£15 at 5+ active referrals · free at 10+). Billed monthly via Stripe.</p>
                  <p><strong>Termination</strong>: Either side can terminate with 14 days' notice. Master Admin may suspend on safety, fraud, or compliance grounds with immediate effect.</p>
                </div>

                <label className="flex items-start gap-2 text-sm cursor-pointer" data-testid="pe-apply-accept-terms">
                  <input type="checkbox" checked={profile.terms_accepted} onChange={setField('terms_accepted')} className="mt-1" />
                  <span>I have read and accept the Partner Engineer terms.</span>
                </label>
                {errors.terms_accepted && <p className="text-xs text-rose-600">{errors.terms_accepted}</p>}
                {errors._submit && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" data-testid="pe-apply-submit-error">{errors._submit}</p>}
              </div>
            )}

            {/* Footer nav */}
            <div className="flex items-center justify-between gap-3 mt-7 pt-5 border-t border-slate-100">
              <button onClick={goBack} disabled={stepIdx === 0}
                className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-slate-900 disabled:opacity-40 inline-flex items-center gap-1"
                data-testid="pe-apply-back-btn">
                <ArrowLeft size={12} /> Back
              </button>
              {stepIdx < STEPS.length - 1 ? (
                <button onClick={goNext}
                  className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-bold"
                  data-testid="pe-apply-next-btn">
                  Continue <ArrowRight size={13} />
                </button>
              ) : (
                <button onClick={submit} disabled={busy || !profile.terms_accepted}
                  className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-2.5 text-sm font-bold disabled:opacity-50"
                  data-testid="pe-apply-submit-btn">
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                  Submit application
                </button>
              )}
            </div>
          </div>

          {/* Trust footer */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
            <span className="inline-flex items-center gap-1.5"><CheckCircle2 size={12} className="text-emerald-500" />Decision in 2 working days</span>
            <span className="inline-flex items-center gap-1.5"><CheckCircle2 size={12} className="text-emerald-500" />£30/mo · free at 10 referrals</span>
            <span className="inline-flex items-center gap-1.5"><Mail size={12} className="text-slate-500" />Need help? <Link to="/contact" className="underline">Contact us</Link></span>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}

/* ── helpers ──────────────────────────────────────────── */
function Field({ label, value, onChange, placeholder, required, error, type = 'text', testId }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider font-bold text-slate-500">
        {label}{required && <span className="text-rose-500 ml-0.5">*</span>}
      </span>
      <input
        type={type}
        value={value || ''}
        placeholder={placeholder || ''}
        onChange={onChange}
        className={`mt-1.5 w-full px-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:border-slate-900 ${
          error ? 'border-rose-300 bg-rose-50/60' : 'border-slate-200'
        }`}
        data-testid={testId}
      />
      {error && <span className="text-[11px] text-rose-600 mt-1 block">{error}</span>}
    </label>
  );
}

function FileDropTile({ label, file, onPick, onClear, testId }) {
  return (
    <div
      className="flex items-center gap-3 p-4 rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50/40"
      data-testid={testId}
    >
      <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center shrink-0">
        <Upload size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-slate-800 truncate">{label}</p>
        <p className="text-xs text-slate-500 truncate">
          {file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : 'No file selected'}
        </p>
      </div>
      {file ? (
        <button type="button" onClick={onClear} className="px-2 py-1.5 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-md inline-flex items-center gap-1" data-testid={`${testId}-clear`}>
          <Trash2 size={12} /> Remove
        </button>
      ) : (
        <button type="button" onClick={onPick} className="px-3 py-1.5 text-xs font-bold text-slate-700 border border-slate-300 hover:bg-white rounded-md" data-testid={`${testId}-pick`}>
          Choose file
        </button>
      )}
    </div>
  );
}

function Summary({ label, value }) {
  return (
    <div className="flex items-baseline gap-3 text-sm">
      <span className="w-32 shrink-0 text-[11px] uppercase tracking-wider font-bold text-slate-500">{label}</span>
      <span className="flex-1 text-slate-800 break-words">{value}</span>
    </div>
  );
}

/* Unused — declared so lint stays happy on Sparkles import. */
// eslint-disable-next-line no-unused-vars
const _kept = Sparkles;
