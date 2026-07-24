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
import { ArrowRight } from 'lucide-react';
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
  const { API, user } = useAuth();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [live, setLive] = useState(null);
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

  const start = () => {
    if (user) navigate('/choose-plan');
    else if (onStart) onStart();
    else navigate('/login?next=/choose-plan');
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
                  onClick={start}
                  className={`mt-5 w-full h-11 rounded-full font-semibold text-sm flex items-center justify-center gap-2 transition-colors ${featured ? 'bg-[var(--pulse-primary)] hover:brightness-95 text-[#0A0C10]' : 'border border-[var(--color-border-subtle,#d4d4d8)] text-[var(--color-surface-dark-panel-alt)] hover:border-[var(--pulse-primary)]'}`}
                  data-testid={`pulse-module-start-${id}`}
                >
                  {user ? t('pulse_pricing.cta_choose', 'Choose') : t('pulse_pricing.cta_start', 'Start')} {featured ? 'Pulse Fitness Pro' : meta.name} <ArrowRight size={15} />
                </button>
              </motion.div>
            );
          })}
        </div>
        <p className="mt-5 text-center text-xs text-[var(--color-text-slate)]">
          {t('pulse_pricing.trial_footer', '14-day free trial · no card required to start · cancel anytime')}
        </p>
      </div>
    </section>
  );
}
