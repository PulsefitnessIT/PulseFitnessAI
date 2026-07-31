/**
 * Public, multi-currency module pricing for the /pulse-pricing page.
 * Modules are the product: Operations is the flagship ("Pulse Fitness Pro").
 * Prices come live from Stripe via GET /api/payments/pricing/live (public).
 * CTAs route unauthenticated visitors into sign-in/start; the actual Stripe
 * checkout stays behind auth at /choose-plan.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { ArrowRight, Check, Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/App';

const CCY = { gbp: '£', eur: '€', usd: '$' };

const MODULE_META = {
  operations: { name: 'Operations', tag: 'Pulse Fitness Pro', blurbKey: 'pulse_pricing.blurb_operations' },
  crm: { name: 'CRM', blurbKey: 'pulse_pricing.blurb_crm' },
  marketing: { name: 'Marketing', blurbKey: 'pulse_pricing.blurb_marketing' },
  memberships: { name: 'Memberships', blurbKey: 'pulse_pricing.blurb_memberships' },
};
const ORDER = ['operations', 'crm', 'marketing', 'memberships'];

export default function PulseModulePricing({ onStart }) {
  const { API, user, token } = useAuth();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [live, setLive] = useState(null);
  const [trialBusy, setTrialBusy] = useState(false);
  // Language nudges the currency (FR/DE → €), so the price matches the words a
  // visitor sees. IP-detected currency disambiguates GBP vs USD for English.
  const langCcy = (l, detected) => {
    const base = (l || 'en').slice(0, 2);
    if (base === 'de' || base === 'fr') return 'eur';
    return detected || 'gbp';
  };
  const [currency, setCurrency] = useState(() => langCcy(i18n.language));
  const [ccyPicked, setCcyPicked] = useState(false);
  const [cycle, setCycle] = useState('monthly');
  const annual = cycle === 'annual';

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing/live`)
      .then((r) => { if (!cancelled) { setLive(r.data); if (!ccyPicked) setCurrency(langCcy(i18n.language, r.data?.detected_currency)); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [API]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-nudge currency if the visitor switches language (unless they picked one).
  useEffect(() => {
    if (!ccyPicked) setCurrency(langCcy(i18n.language, live?.detected_currency));
  }, [i18n.language]); // eslint-disable-line react-hooks/exhaustive-deps

  const fmt = (id) => {
    const node = live?.pricing?.[id]?.[currency];
    if (!node) return null;
    const minor = annual ? node.annual : node.monthly;
    return minor == null ? null : `${CCY[currency]}${Math.round(minor / 100)}`;
  };

  const start = (moduleId) => {
    const qs = `?module=${moduleId}&billing=${cycle}&currency=${currency}`;
    const dest = `/choose-plan${qs}`;
    // Everyone is already a Pulse Lite customer, so there is no public sign-up:
    // logged-in users go straight to Stripe checkout for the chosen module;
    // otherwise they sign in first and are then routed to the same checkout.
    if (user) navigate(dest);
    else if (onStart) onStart(dest);
    else navigate(`/login?next=${encodeURIComponent(dest)}`);
  };

  // Lite is included free with a Pulse Fitness equipment agreement — the CTA
  // just takes the customer into their existing portal (or sign-in first).
  const goToPortal = () => {
    if (user) navigate('/dashboard');
    else if (onStart) onStart('/dashboard');
    else navigate('/login?next=/dashboard');
  };

  // Start a free 3-day trial with ALL modules unlocked (owners/managers only).
  const startTrial = async () => {
    if (!user) { if (onStart) onStart('/dashboard'); else navigate('/login?next=/dashboard'); return; }
    setTrialBusy(true);
    try {
      const r = await axios.post(
        `${API}/me/upgrade-to-pro`,
        { start_trials: ['crm', 'marketing', 'memberships'] },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (r.data?.already_pro) toast.info("You're already on Pulse Pro — all modules are available.");
      else toast.success('Your free 3-day trial is live — all modules unlocked.');
      navigate('/dashboard');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not start the trial. Please try again.');
    } finally {
      setTrialBusy(false);
    }
  };

  const pillBase = 'px-3.5 h-8 rounded-full text-sm font-semibold transition-colors';
  const activePill = 'bg-[var(--pulse-primary)] text-[#0A0C10]';
  const idlePill = 'text-[var(--color-text-slate)] hover:text-[var(--color-surface-dark-panel-alt)]';

  return (
    <section className="relative py-6" data-testid="pulse-module-pricing">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center max-w-2xl mx-auto">
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">{t('pulse_pricing.modules_eyebrow', 'Modules')}</div>
          <h2 className="text-2xl sm:text-4xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">
            {t('pulse_pricing.heading', 'Build your platform, one module at a time.')}
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[var(--color-text-slate)]">
            {t('pulse_pricing.subtitle', 'Every module is a standalone subscription — mix and match, cancel anytime. Priced in your currency.')}
          </p>
        </div>

        {/* Currency + billing controls */}
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3" data-testid="pulse-pricing-controls">
          <div className="inline-flex rounded-full border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-1" data-testid="pulse-currency-toggle">
            {['gbp', 'eur', 'usd'].map((c) => (
              <button key={c} type="button" onClick={() => { setCcyPicked(true); setCurrency(c); }}
                className={`${pillBase} ${currency === c ? activePill : idlePill}`} data-testid={`pulse-currency-${c}`}>
                {CCY[c]} {c.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center rounded-full border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-1" data-testid="pulse-billing-toggle">
            {[['monthly', t('pulse_pricing.monthly', 'Monthly')], ['annual', t('pulse_pricing.annual', 'Annual')]].map(([v, label]) => (
              <button key={v} type="button" onClick={() => setCycle(v)}
                className={`${pillBase} ${cycle === v ? activePill : idlePill}`} data-testid={`pulse-billing-${v}`}>
                {label}
              </button>
            ))}
            {live?.annual_discount_pct ? (
              <span className="px-2.5 text-xs font-semibold text-[var(--pulse-primary)]">{t('pulse_pricing.save_pct', 'Save {{pct}}%', { pct: live.annual_discount_pct })}</span>
            ) : null}
          </div>
        </div>

        {/* Module cards */}
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ORDER.map((id, i) => {
            const meta = MODULE_META[id];
            const featured = id === 'operations';
            const price = fmt(id);
            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.05 }}
                className={`relative rounded-2xl bg-white p-6 flex flex-col ${featured ? 'border-2 border-[var(--pulse-primary)] shadow-lg' : 'border border-[var(--color-border-subtle,#e5e7eb)]'}`}
                data-testid={`pulse-module-card-${id}`}
              >
                {featured ? (
                  <span className="absolute -top-2.5 left-6 bg-[var(--pulse-primary)] text-[#0A0C10] text-[10px] font-bold uppercase tracking-[0.14em] px-2.5 py-0.5 rounded-full" data-testid="pulse-flagship-badge">
                    {t('pulse_pricing.recommended', 'Recommended')}
                  </span>
                ) : null}
                <div className="font-bold text-lg text-[var(--color-surface-dark-panel-alt)]">{meta.name}</div>
                {featured ? <div className="text-xs font-semibold text-[var(--pulse-primary)] mt-0.5">Pulse Fitness Pro</div> : null}
                <p className="text-xs text-[var(--color-text-slate)] mt-2 leading-relaxed min-h-[48px]">{t(meta.blurbKey)}</p>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-[var(--color-surface-dark-panel-alt)]" data-testid={`pulse-module-price-${id}`}>{price || '—'}</span>
                  <span className="text-sm text-[var(--color-text-slate)]">{annual ? t('pulse_pricing.per_year', '/yr') : t('pulse_pricing.per_month', '/mo')}</span>
                </div>
                <button
                  type="button"
                  onClick={() => start(id)}
                  className={`mt-5 w-full h-11 rounded-full font-semibold text-sm flex items-center justify-center gap-2 transition-colors ${featured ? 'bg-[var(--pulse-primary)] hover:brightness-95 text-[#0A0C10]' : 'border border-[var(--color-border-subtle,#d4d4d8)] text-[var(--color-surface-dark-panel-alt)] hover:border-[var(--pulse-primary)]'}`}
                  data-testid={`pulse-module-start-${id}`}
                >
                  {user
                    ? <>{t('pulse_pricing.cta_upgrade', 'Upgrade to')} {featured ? 'Pulse Fitness Pro' : meta.name}</>
                    : <>{t('pulse_pricing.cta_signin_upgrade', 'Sign in to upgrade')}</>} <ArrowRight size={15} />
                </button>
              </motion.div>
            );
          })}
        </div>

        {/* Lite — free, included with a Pulse Fitness equipment agreement */}
        <div
          className="mt-6 rounded-2xl border border-[var(--color-border-subtle,#d4d4d8)] bg-[var(--color-surface-dark-panel-alt,#0f172a)] text-white p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
          data-testid="pulse-module-lite-tile"
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex items-center justify-center w-9 h-9 rounded-xl bg-[var(--pulse-primary)]/15 text-[var(--pulse-primary)]">
              <Sparkles size={18} />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold">Lite</h3>
                <span className="text-xs font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-[var(--pulse-primary)] text-[#0A0C10]">Free</span>
              </div>
              <p className="text-sm text-white/70 mt-0.5 max-w-md">
                {t('pulse_pricing.lite_blurb', 'Included free with your Pulse Fitness equipment agreement — asset register, fault logging and your service portal.')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={goToPortal}
            className="shrink-0 h-11 px-5 rounded-full font-semibold text-sm flex items-center justify-center gap-2 border border-white/25 text-white hover:border-[var(--pulse-primary)] hover:text-[var(--pulse-primary)] transition-colors"
            data-testid="pulse-module-lite-cta"
          >
            {user ? t('pulse_pricing.lite_open', 'Open your portal') : t('pulse_pricing.lite_signin', 'Sign in to your portal')} <ArrowRight size={15} />
          </button>
        </div>

        {/* Free 3-day all-module trial (owners / managers) */}
        <div className="mt-5 flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={startTrial}
            disabled={trialBusy}
            className="h-12 px-7 rounded-full font-bold text-sm flex items-center justify-center gap-2 bg-[var(--pulse-primary)] text-[#0A0C10] hover:brightness-95 transition disabled:opacity-60"
            data-testid="pulse-start-trial-btn"
          >
            {trialBusy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {t('pulse_pricing.start_trial', 'Start your free 3-day trial (all modules)')}
          </button>
          <p className="text-center text-xs text-[var(--color-text-slate)]">
            {t('pulse_pricing.trial_footer', '3-day free trial · all modules unlocked for owners & managers · cancel anytime')}
          </p>
        </div>
      </div>
    </section>
  );
}
