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
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '@/App';

const CCY = { gbp: '£', eur: '€', usd: '$' };

const MODULE_META = {
  operations: { name: 'Operations', tag: 'Pulse Fitness Pro', blurb: 'Equipment, faults, check sheets, AI triage & engineer ops.' },
  crm: { name: 'CRM', blurb: 'Pipeline, quoting, contracts & customer relationships.' },
  marketing: { name: 'Marketing', blurb: 'Campaigns, social autopilot & growth tooling.' },
  memberships: { name: 'Memberships', blurb: 'Members, plans, timetables & the member app.' },
};
const ORDER = ['operations', 'crm', 'marketing', 'memberships'];

export default function PulseModulePricing({ onStart }) {
  const { API, user } = useAuth();
  const navigate = useNavigate();
  const [live, setLive] = useState(null);
  const [currency, setCurrency] = useState('gbp');
  const [cycle, setCycle] = useState('monthly');
  const annual = cycle === 'annual';

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing/live`)
      .then((r) => { if (!cancelled) { setLive(r.data); if (r.data?.detected_currency) setCurrency(r.data.detected_currency); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [API]);

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
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">Modules</div>
          <h2 className="text-2xl sm:text-4xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">
            Build your platform, one module at a time.
          </h2>
          <p className="mt-3 text-sm sm:text-base text-[var(--color-text-slate)]">
            Every module is a standalone subscription — mix and match, cancel anytime. Priced in your currency.
          </p>
        </div>

        {/* Currency + billing controls */}
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3" data-testid="pulse-pricing-controls">
          <div className="inline-flex rounded-full border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-1" data-testid="pulse-currency-toggle">
            {['gbp', 'eur', 'usd'].map((c) => (
              <button key={c} type="button" onClick={() => setCurrency(c)}
                className={`${pillBase} ${currency === c ? activePill : idlePill}`} data-testid={`pulse-currency-${c}`}>
                {CCY[c]} {c.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center rounded-full border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-1" data-testid="pulse-billing-toggle">
            {[['monthly', 'Monthly'], ['annual', 'Annual']].map(([v, label]) => (
              <button key={v} type="button" onClick={() => setCycle(v)}
                className={`${pillBase} ${cycle === v ? activePill : idlePill}`} data-testid={`pulse-billing-${v}`}>
                {label}
              </button>
            ))}
            {live?.annual_discount_pct ? (
              <span className="px-2.5 text-xs font-semibold text-[var(--pulse-primary)]">Save {live.annual_discount_pct}%</span>
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
                    Recommended
                  </span>
                ) : null}
                <div className="font-bold text-lg text-[var(--color-surface-dark-panel-alt)]">{meta.name}</div>
                {featured ? <div className="text-xs font-semibold text-[var(--pulse-primary)] mt-0.5">Pulse Fitness Pro</div> : null}
                <p className="text-xs text-[var(--color-text-slate)] mt-2 leading-relaxed min-h-[48px]">{meta.blurb}</p>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-[var(--color-surface-dark-panel-alt)]" data-testid={`pulse-module-price-${id}`}>{price || '—'}</span>
                  <span className="text-sm text-[var(--color-text-slate)]">{annual ? '/yr' : '/mo'}</span>
                </div>
                <button
                  type="button"
                  onClick={start}
                  className={`mt-5 w-full h-11 rounded-full font-semibold text-sm flex items-center justify-center gap-2 transition-colors ${featured ? 'bg-[var(--pulse-primary)] hover:brightness-95 text-[#0A0C10]' : 'border border-[var(--color-border-subtle,#d4d4d8)] text-[var(--color-surface-dark-panel-alt)] hover:border-[var(--pulse-primary)]'}`}
                  data-testid={`pulse-module-start-${id}`}
                >
                  {user ? 'Choose' : 'Start'} {featured ? 'Pulse Fitness Pro' : meta.name} <ArrowRight size={15} />
                </button>
              </motion.div>
            );
          })}
        </div>
        <p className="mt-5 text-center text-xs text-[var(--color-text-slate)]">
          14-day free trial · no card required to start · cancel anytime
        </p>
      </div>
    </section>
  );
}
