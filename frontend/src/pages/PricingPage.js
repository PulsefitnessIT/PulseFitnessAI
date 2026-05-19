/**
 * GymAxis AI — Pricing.
 *
 * Dark Swiss high-contrast aesthetic matching the homepage.
 * Three-tier plan grid, one-off Audit tile, comparison strip.
 * Every plan CTA opens the landing trial modal (no separate signup route).
 */
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { motion } from 'framer-motion';
import { useInlineBanner } from '@/components/notifications';
import {
 ArrowLeft, ArrowRight, Check, X as XIcon, Star, Phone, Loader2,
 Zap, ShieldCheck, Sparkles, CheckCircle2,
} from 'lucide-react';
import { useAuth } from '@/App';
import Footer from '../components/shared/Footer';
import Turnstile from '../components/shared/Turnstile';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FADE_UP = {
 hidden: { opacity: 0, y: 24 },
 show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger = { show: { transition: { staggerChildren: 0.08 } } };

const PLANS = [
 {
 id: 'starter',
 name: 'Starter',
 price: 29,
 desc: 'Single-site operators getting their first audit trail online.',
 cta: 'Start 3-day trial',
 features: [
 'AI fault chatbot',
 'Fault logging + triage',
 'Up to 50 pieces of equipment',
 'Daily check-sheets',
 'QR scanning',
 'Warranty display',
 'Basic reports',
 'Email support',
 '2 team members',
 ],
 popular: false,
 },
 {
 id: 'pro',
 name: 'Pro',
 price: 79,
 desc: 'Growing estates with multiple supplier relationships and rising SLAs.',
 cta: 'Start 3-day trial',
 features: [
 'Everything in Starter',
 'Unlimited AI triage',
 'Unlimited AI audits',
 'Risk-assessment photos',
 'PO dispatch via email',
 'Warranty expiry alerts',
 'Supplier management',
 'Custom check-sheets',
 'Operational reports + weekly digest',
 'Unlimited equipment',
 '10 team members',
 'Priority support',
 ],
 popular: false,
 },
 {
 id: 'bundle',
 name: 'GymAxis Bundle',
 price: 199,
 priceHint: 'Save 20% vs buying each',
 desc: 'All three products — Pulse, Memberships & MOD — bundled with cross-module access.',
 cta: 'Start 3-day trial',
 features: [
 'Everything in Pro',
 'GymAxis Memberships Studio (unlimited members)',
 'Member class booking + QR check-ins',
 'Instructor portal + commission reporting',
 'White-label member app at /m/your-slug',
 'MOD Oversight (cross-site monitoring)',
 'Single operator sign-on across modules',
 'Consolidated dashboards & KPIs',
 'Priority engineer escalation',
 'Dedicated onboarding',
 ],
 popular: true,
 badge: 'Best value',
 },
 {
 id: 'enterprise',
 name: 'Enterprise',
 price: 249,
 desc: 'Multi-site groups, tender-heavy commercial teams, ERP & finance integrations.',
 cta: 'Talk to sales',
 features: [
 'Everything in Pro',
 'Multi-site consolidated reporting',
 'Unlimited team members',
 'Supplier API access',
 'Priority engineer escalation',
 'Advanced PO workflow',
 'CSV import + bulk tools',
 'White-label portals',
 'Multi-site discount',
 'Contractual SLA',
 'Dedicated onboarding',
 ],
 popular: false,
 },
];

// Feature comparison matrix — key capabilities side-by-side.
const COMPARE = [
 { label: 'Equipment records', starter: 'Up to 50', pro: 'Unlimited', enterprise: 'Unlimited' },
 { label: 'Team seats', starter: '2', pro: '10', enterprise: 'Unlimited' },
 { label: 'AI fault triage', starter: true, pro: true, enterprise: true },
 { label: 'AI audits (risk-assessment)', starter: false, pro: true, enterprise: true },
 { label: 'Supplier collaboration portal', starter: false, pro: true, enterprise: true },
 { label: 'PPM engine + compliance %', starter: false, pro: true, enterprise: true },
 { label: 'KPI Engine + CSV export', starter: false, pro: true, enterprise: true },
 { label: 'Multi-site consolidated reporting', starter: false, pro: false, enterprise: true },
 { label: 'ERP & finance integration (REST + webhooks)', starter: false, pro: false, enterprise: true },
 { label: 'White-label portals', starter: false, pro: false, enterprise: true },
 { label: 'Contractual SLA', starter: false, pro: false, enterprise: true },
];


// ─── Trial modal (shared with HomePage) ────────────────────────
function PricingTrialModal({ open, onClose, seedPlan }) {
 const [form, setForm] = useState({ full_name: '', email: '', company_name: '', phone: '', password: '' });
 const [showPass, setShowPass] = useState(false);
 const [loading, setLoading] = useState(false);
 const [done, setDone] = useState(false);
 const [captchaToken, setCaptchaToken] = useState('');
 const { banner, show, clear } = useInlineBanner();
 const navigate = useNavigate();
 const { login } = useAuth();

 useEffect(() => {
 if (!open) return undefined;
 const onKey = (e) => e.key === 'Escape' && onClose();
 window.addEventListener('keydown', onKey);
 return () => window.removeEventListener('keydown', onKey);
 }, [open, onClose]);

 useEffect(() => {
 if (!open) return undefined;
 const prev = document.body.style.overflow;
 document.body.style.overflow = 'hidden';
 return () => { document.body.style.overflow = prev; };
 }, [open]);

 useEffect(() => {
 if (!open) {
 setForm({ full_name: '', email: '', company_name: '', phone: '', password: '' });
 setDone(false);
 setCaptchaToken('');
 }
 }, [open]);

 const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

 const submit = async (e) => {
 e.preventDefault();
 clear();
 if (form.password.length < 8) {
 show({ tone: 'error', title: 'Password too short', detail: 'Choose a password of at least 8 characters.' });
 return;
 }
 if (!captchaToken) {
 show({ tone: 'error', title: 'Anti-bot check required', detail: 'Please complete the verification below before continuing.' });
 return;
 }
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
 cf_turnstile_response: captchaToken,
 });
 if (!data?.token) throw new Error('Signup failed');
 login(data.token, data.user);
 setDone(true);
 setTimeout(() => { onClose(); navigate('/dashboard', { replace: true }); }, 1600);
 } catch (err) {
 show({ tone: 'error', title: 'Could not start trial', detail: err.response?.data?.detail || 'Please check your details and try again.' });
 }
 setLoading(false);
 };

 if (!open) return null;

 return (
 <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md" onClick={onClose} data-testid="pricing-trial-overlay">
 <div onClick={(e) => e.stopPropagation()} className="relative w-full max-w-md bg-gradient-to-br from-[var(--color-ink-coal)] to-[var(--color-surface-darker)] border border-white/10 rounded-2xl shadow-[0_40px_120px_rgba(0,0,0,0.6),0_0_60px_rgba(25,205,255,0.15)] overflow-hidden" data-testid="pricing-trial-modal">
 <div className="pointer-events-none absolute -top-24 -right-24 w-64 h-64 bg-[rgb(var(--rgb-brand-cyan)/0.15)] blur-[100px] rounded-full" />
 <div className="relative">
 <div className="flex items-start justify-between p-6 pb-2">
 <div>
 <div className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] mb-2">
 <Zap size={11} /> 3-day free trial {seedPlan ? `· ${seedPlan} preview` : ''}
 </div>
 <h2 className="text-white text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em' }}>Start your trial</h2>
 <p className="text-white/60 text-sm mt-1">Full Pro access. No card required.</p>
 </div>
 <button onClick={onClose} type="button" className="p-1 rounded-md text-white/50 hover:text-white hover:bg-white/5 transition" data-testid="pricing-trial-close">
 <XIcon size={18} />
 </button>
 </div>
 {done ? (
 <div className="p-6 pt-2 text-center" data-testid="pricing-trial-success">
 <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/15 border border-emerald-500/40 flex items-center justify-center mb-4">
 <CheckCircle2 size={28} className="text-emerald-400" />
 </div>
 <h3 className="text-white font-bold text-lg">You're in — welcome aboard.</h3>
 <p className="text-white/60 text-sm mt-1">Taking you to the dashboard…</p>
 </div>
 ) : (
 <form onSubmit={submit} className="p-6 pt-2 space-y-3" data-testid="pricing-trial-form">
 {banner && <div>{banner}</div>}
 {[
 { k: 'full_name', label: 'Full name', type: 'text', placeholder: 'Jane Smith', required: true },
 { k: 'email', label: 'Work email', type: 'email', placeholder: 'jane@yourgym.com', required: true },
 { k: 'company_name', label: 'Gym / Company name', type: 'text', placeholder: 'Acme Fitness', required: true },
 { k: 'phone', label: 'Phone (optional)', type: 'tel', placeholder: '+44 7700 900123', required: false },
 ].map((f) => (
 <div key={f.k}>
 <label className="text-[11px] font-semibold text-white/60 uppercase tracking-wide mb-1.5 block">{f.label}</label>
 <input
 type={f.type} required={f.required} value={form[f.k]} onChange={update(f.k)}
 className="w-full h-11 px-3 rounded-md bg-[var(--color-ink-alt)] border border-white/10 text-white placeholder:text-white/30 focus:outline-none focus:border-[var(--color-brand-cyan)] transition"
 placeholder={f.placeholder}
 data-testid={`pricing-trial-${f.k}`}
 />
 </div>
 ))}
 <div>
 <label className="text-[11px] font-semibold text-white/60 uppercase tracking-wide mb-1.5 block">Password</label>
 <div className="relative">
 <input
 type={showPass ? 'text' : 'password'} required minLength={8}
 value={form.password} onChange={update('password')}
 className="w-full h-11 px-3 pr-14 rounded-md bg-[var(--color-ink-alt)] border border-white/10 text-white placeholder:text-white/30 focus:outline-none focus:border-[var(--color-brand-cyan)] transition"
 placeholder="At least 8 characters"
 data-testid="pricing-trial-password"
 />
 <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-[11px] text-white/50 hover:text-white" tabIndex={-1}>
 {showPass ? 'Hide' : 'Show'}
 </button>
 </div>
 </div>
 <div className="pt-1">
 <Turnstile
 onToken={setCaptchaToken}
 theme="dark"
 testId="pricing-turnstile"
 action="trial_signup"
 />
 </div>
 <button
 type="submit" disabled={loading}
 className="w-full h-12 rounded-md font-bold text-sm transition flex items-center justify-center gap-2 disabled:opacity-60 mt-2"
 style={{ background: 'linear-gradient(135deg, var(--color-brand-cyan) 0%, var(--color-brand-cyan-deep) 100%)', color: 'var(--color-surface-darker)', letterSpacing: '0.05em', boxShadow: '0 0 40px rgba(25,205,255,0.35)' }}
 data-testid="pricing-trial-submit"
 >
 {loading ? <><Loader2 size={14} className="animate-spin" /> Creating your account…</> : <><span className="uppercase">Start 3-day Trial</span> <ArrowRight size={14} /></>}
 </button>
 <p className="text-[10px] text-white/40 text-center">
 By starting a trial you agree to our <Link to="/terms" className="underline hover:text-white/70">Terms</Link> and <Link to="/privacy" className="underline hover:text-white/70">Privacy Policy</Link>.
 </p>
 </form>
 )}
 </div>
 </div>
 </div>
 );
}


function PricingNav() {
 return (
 <nav className="sticky top-0 z-40 bg-[var(--color-surface-darker)]/80 backdrop-blur-lg border-b border-white/10">
 <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
 <Link to="/" className="text-white font-extrabold text-lg tracking-tight" data-testid="pricing-logo-home">
 GymAxis<span className="text-[var(--color-brand-cyan)]">.AI</span>
 </Link>
 <div className="flex items-center gap-3">
 <Link to="/" className="text-white/70 hover:text-white text-sm font-semibold hidden sm:inline-flex items-center gap-1.5">
 <ArrowLeft size={14} /> Home
 </Link>
 <Link to="/contact" className="text-white/70 hover:text-white text-sm font-semibold hidden sm:inline" data-testid="pricing-contact">
 Contact
 </Link>
 <Link to="/login" className="bg-white text-[var(--color-surface-darker)] font-bold text-sm px-4 py-2 rounded-full hover:bg-[var(--color-brand-cyan)] transition-colors" data-testid="pricing-nav-signin">
 Sign In
 </Link>
 </div>
 </div>
 </nav>
 );
}


/* ─────────────────── Dynamic modules section ─────────────────── */
/**
 * Module-level pricing fetched live from /api/pricing/public — driven by
 * the Master Admin → Pricing tab. Operator can flip currency + adjust
 * site-count to see live prices including volume discounts.
 */
function DynamicModulesSection({ onStartTrial, brandHint = 'gymaxis' }) {
  const [currency, setCurrency] = useState('GBP');
  const [sites, setSites] = useState(1);
  const [cycle, setCycle] = useState('monthly');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    axios.get(`${API}/pricing/public?brand=${brandHint}&currency=${currency}&sites=${sites}`)
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [currency, sites, brandHint]);

  if (loading) {
    return (
      <section className="py-12 border-b border-white/10 text-center text-white/40 text-sm" data-testid="dynamic-pricing-loading">
        Loading live module pricing…
      </section>
    );
  }
  if (!data || !(data.plans || []).length) return null;

  const plans = data.plans || [];
  const sym = currency === 'GBP' ? '£' : currency === 'EUR' ? '€' : '$';

  return (
    <section className="relative py-20 border-b border-white/10" data-testid="dynamic-pricing-section">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 mb-3">
            <span className="h-px w-6 bg-white/30" />
            Build your stack
            <span className="h-px w-6 bg-white/30" />
          </div>
          <h2 className="text-white font-extrabold text-3xl sm:text-5xl tracking-tight" style={{ letterSpacing: '-0.02em' }}>
            Pick the modules you need.
          </h2>
          <p className="mt-3 text-white/60 text-base">Volume discount applies the moment you add more sites.</p>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          <div className="inline-flex items-center bg-white/[0.04] border border-white/10 rounded-full p-1" data-testid="pricing-cycle-toggle">
            {['monthly', 'annual'].map((c) => (
              <button
                key={c}
                onClick={() => setCycle(c)}
                className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-full transition ${
                  cycle === c ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)]' : 'text-white/60 hover:text-white'
                }`}
                data-testid={`pricing-cycle-${c}`}
              >
                {c}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center bg-white/[0.04] border border-white/10 rounded-full p-1" data-testid="pricing-currency-toggle">
            {(data.supported_currencies || ['GBP', 'EUR', 'USD']).map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                className={`px-3 py-1.5 text-xs font-bold rounded-full transition ${
                  currency === c ? 'bg-white text-[var(--color-surface-darker)]' : 'text-white/60 hover:text-white'
                }`}
                data-testid={`pricing-ccy-${c}`}
              >
                {c}
              </button>
            ))}
          </div>
          <label className="inline-flex items-center gap-2 bg-white/[0.04] border border-white/10 rounded-full px-4 py-1.5 text-xs text-white/70">
            Sites
            <input
              type="number"
              min={1}
              value={sites}
              onChange={(e) => setSites(Math.max(1, Number(e.target.value) || 1))}
              className="w-14 bg-transparent text-white font-bold text-center outline-none"
              data-testid="pricing-sites-input"
            />
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {plans.map((p) => {
            const q = cycle === 'annual' ? p.quote_annual : p.quote_monthly;
            const total = (q?.total_amount || 0) / 100;
            const per = cycle === 'annual' ? '/year' : '/month';
            const isBundle = p.is_bundle;
            return (
              <div
                key={p.id}
                className={`rounded-2xl p-6 ${
                  isBundle
                    ? 'bg-gradient-to-b from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent border border-[rgb(var(--rgb-brand-cyan)/0.4)] shadow-[0_0_60px_rgba(25,205,255,0.15)] lg:col-span-3'
                    : 'bg-white/[0.03] border border-white/10'
                }`}
                data-testid={`module-card-${p.module_id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[var(--color-brand-cyan)] mb-1.5">
                      {isBundle ? 'Bundle · save more' : p.module_id}
                    </div>
                    <h3 className="text-white text-2xl font-extrabold tracking-tight">{p.name}</h3>
                    <p className="text-white/60 text-sm mt-1.5 leading-relaxed">{p.description}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-white text-3xl font-extrabold leading-none" style={{ letterSpacing: '-0.02em' }}>
                      {sym}{total.toFixed(2)}
                    </div>
                    <div className="text-[11px] text-white/55 mt-1">{per}</div>
                    {q?.discount_pct > 0 && (
                      <div className="text-[10px] uppercase font-bold text-emerald-400 mt-1">
                        {q.discount_pct}% volume off
                      </div>
                    )}
                  </div>
                </div>
                {(p.features || []).length > 0 && (
                  <ul className="mt-5 space-y-2">
                    {p.features.slice(0, 5).map((f) => (
                      <li key={f} className="flex items-start gap-2 text-sm text-white/80">
                        <Check size={14} className="text-[var(--color-brand-cyan)] mt-0.5 shrink-0" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  onClick={() => onStartTrial(p.name)}
                  className={`mt-5 w-full h-11 rounded-md font-bold text-sm uppercase tracking-wider ${
                    isBundle
                      ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] hover:bg-[var(--color-brand-cyan-deep)]'
                      : 'border border-white/20 text-white hover:bg-white/5 hover:border-white/40'
                  }`}
                  data-testid={`module-cta-${p.module_id}`}
                >
                  Start 3-day trial
                </button>
              </div>
            );
          })}
        </div>
        <p className="mt-6 text-center text-xs text-white/40">
          Prices include {((plans[0]?.vat_rate || 0.20) * 100).toFixed(0)}% VAT · Multi-site discount applies automatically.
        </p>
        <p className="mt-2 text-center text-[11px] text-white/40">
          Marketing module includes 5,000 emails/month. Need more? Email Boost packs from <span className="text-white/60 font-semibold">+£19/mo</span> (+25,000) to <span className="text-white/60 font-semibold">+£199/mo</span> (+500,000).
        </p>
      </div>
    </section>
  );
}


function PricingHero() {
 return (
 <section className="relative overflow-hidden border-b border-white/10">
 <div className="pointer-events-none absolute inset-0">
 <div className="absolute -top-40 -left-40 w-[44rem] h-[44rem] rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.1)] blur-[140px]" />
 <div className="absolute -bottom-40 right-0 w-[32rem] h-[32rem] rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.05)] blur-[120px]" />
 <div
 className="absolute inset-0 opacity-[0.035]"
 style={{
 backgroundImage: 'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
 backgroundSize: '80px 80px',
 }}
 />
 </div>
 <div className="relative max-w-5xl mx-auto px-6 pt-20 sm:pt-28 pb-16 text-center">
 <motion.div initial="hidden" animate="show" variants={stagger}>
 <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/60 mb-5">
 <span className="h-px w-6 bg-white/30" />
 Pricing
 <span className="h-px w-6 bg-white/30" />
 </motion.div>
 <motion.h1
 variants={FADE_UP}
 className="text-white font-extrabold leading-[1.04]"
 style={{ fontSize: 'clamp(2.25rem, 6vw, 4.5rem)', letterSpacing: '-0.025em', fontFamily: "'Proxima Nova', sans-serif" }}
 >
 Simple, transparent pricing.<br />
 <span className="italic text-[var(--color-brand-cyan)]" style={{ fontFamily: "'Maax Rounded', 'Proxima Nova', sans-serif" }}>No per-seat surprises.</span>
 </motion.h1>
 <motion.p variants={FADE_UP} className="mt-6 text-lg text-white/80 max-w-2xl mx-auto">
 One platform, three tiers. Start with a 3-day free trial — full Pro access, no card required.
 </motion.p>
 <motion.div variants={FADE_UP} className="mt-5 flex items-center justify-center gap-2 text-xs text-white/50">
 <CheckCircle2 size={12} className="text-emerald-400" />
 3-day trial · Full Pro access · No card required
 </motion.div>
 </motion.div>
 </div>
 </section>
 );
}


function PlanCard({ plan, onStartTrial, onEnterprise }) {
 const popular = plan.popular;
 return (
 <motion.div
 variants={FADE_UP}
 whileHover={{ y: -4 }}
 className={`relative rounded-2xl p-8 transition-all duration-300 overflow-hidden ${
 popular
 ? 'bg-gradient-to-b from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent border border-[rgb(var(--rgb-brand-cyan)/0.4)] shadow-[0_0_60px_rgba(25,205,255,0.18)]'
 : 'bg-gradient-to-br from-white/[0.04] to-transparent border border-white/10 hover:border-white/20'
 }`}
 data-testid={`plan-card-${plan.id}`}
 >
 {popular && (
 <div className="pointer-events-none absolute top-0 right-0 w-32 h-32 bg-[rgb(var(--rgb-brand-cyan)/0.1)] blur-3xl rounded-full" />
 )}
 {popular && (
 <div className="absolute -top-3 left-1/2 -translate-x-1/2">
 <span className="bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] text-[10px] font-extrabold px-3 py-1 rounded-full flex items-center gap-1 uppercase tracking-wider shadow-[0_0_20px_rgba(25,205,255,0.5)]">
 <Star size={10} /> {plan.badge || 'Most Popular'}
 </span>
 </div>
 )}
 <div className="relative">
 <h3 className="text-white text-2xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em' }}>
 {plan.name}
 </h3>
 <p className="text-white/65 text-sm mt-2 leading-relaxed min-h-[3rem]">{plan.desc}</p>

 <div className="mt-6 flex items-baseline gap-1.5">
 <span className="text-white font-extrabold tracking-tight" style={{ fontSize: '3rem', letterSpacing: '-0.03em', lineHeight: 1 }}>
 £{plan.price}
 </span>
 <span className="text-sm text-white/55">/month</span>
 </div>
 {plan.priceHint && (
 <div className="text-[10px] mt-1 uppercase tracking-[0.2em] font-extrabold text-[var(--color-brand-cyan)]">{plan.priceHint}</div>
 )}

 <button
 type="button"
 onClick={plan.id === 'enterprise' ? onEnterprise : () => onStartTrial(plan.name)}
 className={`w-full h-12 rounded-md font-bold text-sm transition flex items-center justify-center gap-2 mt-6 uppercase tracking-wider ${
 popular ? '' : 'border border-white/20 text-white hover:bg-white/5 hover:border-white/40'
 }`}
 style={popular ? {
 background: 'linear-gradient(135deg, var(--color-brand-cyan) 0%, var(--color-brand-cyan-deep) 100%)',
 color: 'var(--color-surface-darker)',
 letterSpacing: '0.05em',
 boxShadow: '0 0 30px rgba(25,205,255,0.3)',
 } : { letterSpacing: '0.05em' }}
 data-testid={`plan-cta-${plan.id}`}
 >
 {plan.cta === 'Talk to sales' ? <Phone size={13} /> : <Zap size={13} />}
 {plan.cta}
 </button>

 <div className="mt-8 pt-6 border-t border-white/10">
 <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/40 mb-4">Included</div>
 <ul className="space-y-2.5">
 {plan.features.map((f) => (
 <li key={f} className="flex items-start gap-2.5 text-sm text-white/80 leading-relaxed">
 <Check size={15} className="text-[var(--color-brand-cyan)] mt-0.5 shrink-0" />
 <span>{f}</span>
 </li>
 ))}
 </ul>
 </div>
 </div>
 </motion.div>
 );
}


function CompareStrip() {
 const Cell = ({ val }) => {
 if (val === true) return <Check size={16} className="text-[var(--color-brand-cyan)] mx-auto" />;
 if (val === false) return <XIcon size={14} className="text-white/25 mx-auto" />;
 return <span className="text-white/80 text-sm">{val}</span>;
 };
 return (
 <section className="relative border-b border-white/10 py-24" data-testid="pricing-compare">
 <div className="max-w-6xl mx-auto px-6">
 <div className="text-center mb-10">
 <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 mb-4">
 <span className="h-px w-6 bg-white/30" />
 Side by side
 <span className="h-px w-6 bg-white/30" />
 </div>
 <h2 className="text-white font-extrabold text-3xl sm:text-5xl tracking-tight" style={{ letterSpacing: '-0.02em' }}>
 Compare every feature.
 </h2>
 </div>

 <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.03] to-transparent overflow-hidden">
 {/* Header */}
 <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] items-center px-5 sm:px-8 py-4 bg-white/[0.03] border-b border-white/10 text-[11px] font-bold uppercase tracking-[0.15em] text-white/60">
 <div>Feature</div>
 <div className="text-center">Starter</div>
 <div className="text-center text-[var(--color-brand-cyan)]">Pro</div>
 <div className="text-center">Enterprise</div>
 </div>
 {/* Rows */}
 {COMPARE.map((row, i) => (
 <div
 key={row.label}
 className={`grid grid-cols-[1.4fr_1fr_1fr_1fr] items-center px-5 sm:px-8 py-3.5 text-sm ${
 i % 2 === 0 ? 'bg-white/[0.015]' : ''
 } ${i !== COMPARE.length - 1 ? 'border-b border-white/5' : ''}`}
 >
 <div className="text-white/85 font-medium">{row.label}</div>
 <div className="text-center"><Cell val={row.starter} /></div>
 <div className="text-center"><Cell val={row.pro} /></div>
 <div className="text-center"><Cell val={row.enterprise} /></div>
 </div>
 ))}
 </div>
 </div>
 </section>
 );
}


function AuditTile() {
 return (
 <section className="relative border-b border-white/10 py-20">
 <div className="max-w-5xl mx-auto px-6">
 <motion.div
 initial={{ opacity: 0, y: 20 }}
 whileInView={{ opacity: 1, y: 0 }}
 viewport={{ once: true, amount: 0.2 }}
 className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.04] to-transparent p-8 sm:p-10 text-center"
 data-testid="pricing-audit-tile"
 >
 <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 mb-3">
 <Sparkles size={12} className="text-[var(--color-brand-cyan)]" />
 One-off · no subscription
 </div>
 <h3 className="text-white font-extrabold text-2xl sm:text-3xl tracking-tight" style={{ letterSpacing: '-0.01em' }}>
 AI Risk-Assessment Report
 </h3>
 <p className="text-white/70 text-sm sm:text-base max-w-xl mx-auto mt-3 leading-relaxed">
 A single audit report — useful for tender responses, insurance, or a quick estate-wide health check. No commitment beyond the report itself.
 </p>
 <div className="mt-6 flex items-baseline justify-center gap-1.5">
 <span className="text-white font-extrabold" style={{ fontSize: '2.5rem', letterSpacing: '-0.02em' }}>£4.99</span>
 <span className="text-white/55 text-sm">per report</span>
 </div>
 <Link
 to="/contact"
 className="inline-flex items-center gap-2 mt-6 px-6 py-2.5 rounded-full bg-white/5 text-white border border-white/20 text-sm font-bold hover:bg-white/10 transition-colors"
 data-testid="pricing-audit-cta"
 >
 Request a report <ArrowRight size={14} />
 </Link>
 </motion.div>
 </div>
 </section>
 );
}


function FAQ() {
 const items = [
 { q: 'What does "full Pro access" mean during the trial?',
 a: 'Every Pro feature — unlimited AI triage, unlimited audits, supplier portal, PPM, KPI engine, weekly digest — is unlocked for 3 days. Nothing is gated, nothing is sample data.' },
 { q: 'Do I need to enter a credit card to start?',
 a: 'No. The trial is completely card-free. If you decide to continue after 3 days, you\'ll upgrade through Stripe Checkout from inside the app.' },
 { q: 'What happens when the trial ends?',
 a: 'Your data stays. The app shows a friendly upgrade prompt, and you can continue in read-only mode or upgrade to the plan that matches your usage.' },
 { q: 'Can I switch plans later?',
 a: 'Yes — upgrades and downgrades are instant and prorated. Master Admin exposes one-click tier changes with audit logging.' },
 { q: 'Do you charge per user?',
 a: 'Pro includes 10 seats, Enterprise is unlimited. No per-user surprises, no "call us for pricing".' },
 ];
 return (
 <section className="relative border-b border-white/10 py-24" data-testid="pricing-faq">
 <div className="max-w-3xl mx-auto px-6">
 <div className="text-center mb-10">
 <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/60 mb-4">
 <span className="h-px w-6 bg-white/30" />
 Questions
 <span className="h-px w-6 bg-white/30" />
 </div>
 <h2 className="text-white font-extrabold text-3xl sm:text-5xl tracking-tight" style={{ letterSpacing: '-0.02em' }}>
 Good questions, plain answers.
 </h2>
 </div>
 <div className="space-y-3">
 {items.map((it) => (
 <details
 key={it.q}
 className="group rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.03] to-transparent p-5 open:border-[rgb(var(--rgb-brand-cyan)/0.3)] transition-all"
 >
 <summary className="text-white font-bold text-base cursor-pointer list-none flex items-center justify-between gap-4">
 <span>{it.q}</span>
 <ArrowRight size={14} className="text-white/50 shrink-0 group-open:rotate-90 transition-transform" />
 </summary>
 <p className="mt-3 text-white/75 text-sm leading-relaxed">{it.a}</p>
 </details>
 ))}
 </div>
 </div>
 </section>
 );
}


function PricingCTA({ onStartTrial }) {
 return (
 <section className="relative py-24 overflow-hidden">
 <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[var(--color-brand-cyan)]/[0.04] to-transparent pointer-events-none" />
 <div className="relative max-w-5xl mx-auto px-6">
 <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-[var(--color-ink-midnight)] to-[var(--color-surface-darker)] p-10 sm:p-14 text-center">
 <ShieldCheck size={28} className="text-[var(--color-brand-cyan)] mx-auto mb-5" />
 <h2 className="text-white font-extrabold text-3xl sm:text-5xl leading-tight tracking-tight" style={{ letterSpacing: '-0.02em' }}>
 Try it on your data. For free.
 </h2>
 <p className="mt-4 text-white/70 max-w-2xl mx-auto text-base sm:text-lg">
 Spin up a real workspace in under 60 seconds. Every feature unlocked for 3 days. No card, no strings.
 </p>
 <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
 <button
 type="button"
 onClick={() => onStartTrial(null)}
 className="inline-flex items-center justify-center gap-2 font-bold text-sm px-6 py-3 rounded-full uppercase tracking-wider transition-colors"
 style={{ background: 'linear-gradient(135deg, var(--color-brand-cyan) 0%, var(--color-brand-cyan-deep) 100%)', color: 'var(--color-surface-darker)', letterSpacing: '0.05em', boxShadow: '0 0 40px rgba(25,205,255,0.35)' }}
 data-testid="pricing-final-start-trial"
 >
 <Zap size={13} /> Start Free Trial <ArrowRight size={14} />
 </button>
 <Link
 to="/contact"
 className="inline-flex items-center justify-center gap-2 bg-white/5 text-white border border-white/20 font-bold text-sm px-6 py-3 rounded-full hover:bg-white/10 transition-colors"
 data-testid="pricing-final-book-demo"
 >
 Book a demo
 </Link>
 </div>
 </div>
 </div>
 </section>
 );
}


export default function PricingPage() {
 const navigate = useNavigate();
 const [trialOpen, setTrialOpen] = useState(false);
 const [seed, setSeed] = useState(null);

 // Theme-lock to dark
 useEffect(() => {
 const html = document.documentElement;
 const prev = html.getAttribute('data-theme');
 html.setAttribute('data-theme', 'dark');
 return () => {
 if (prev) html.setAttribute('data-theme', prev);
 };
 }, []);

 const openTrial = (planName) => { setSeed(planName); setTrialOpen(true); };

 return (
 <div className="min-h-screen bg-[var(--color-surface-darker)] text-white" data-testid="pricing-page">
 <PricingNav />
 <PricingTrialModal open={trialOpen} onClose={() => setTrialOpen(false)} seedPlan={seed} />

 <PricingHero />

 <DynamicModulesSection onStartTrial={openTrial} brandHint="gymaxis" />

 {/* Plans */}
 <section className="relative py-20 border-b border-white/10">
 <div className="max-w-6xl mx-auto px-6">
 <motion.div
 initial="hidden"
 whileInView="show"
 viewport={{ once: true, amount: 0.1 }}
 variants={stagger}
 className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5"
 >
 {PLANS.map((plan) => (
 <PlanCard
 key={plan.id}
 plan={plan}
 onStartTrial={openTrial}
 onEnterprise={() => navigate('/contact')}
 />
 ))}
 </motion.div>
 </div>
 </section>

 <CompareStrip />
 <AuditTile />
 <FAQ />
 <PricingCTA onStartTrial={openTrial} />
 <Footer />
 </div>
 );
}
