/**
 * Dedicated "Choose your plan" checkout page (iter 221).
 *
 * Where trial-ending emails now land. Unlike the public marketing pricing
 * page, this surface is login-gated and shows NO free-trial offer — the
 * visitor already has an account, so we get them straight to picking a
 * paid plan and into Stripe Checkout. On successful payment the backend
 * webhook converts the trial to paid automatically.
 *
 * Reuses the existing self-serve flow:
 *   GET  /api/payments/pricing        → bundle + module catalogue
 *   POST /api/payments/checkout/flex  → Stripe Checkout session
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import {
  Check, ArrowRight, Loader2, Minus, Plus, ShieldCheck, Sparkles, MessageCircle,
} from 'lucide-react';
import { useAuth } from '@/App';

const MODULE_BLURB = {
  operations: 'Equipment, faults, check sheets, AI triage & engineer ops.',
  crm: 'Pipeline, quoting, contracts & customer relationships.',
  marketing: 'Campaigns, social autopilot & growth tooling.',
  memberships: 'Members, plans, timetables & the member app.',
};

export default function ChoosePlanPage() {
  const { API, token, user, logout } = useAuth();
  const [pricing, setPricing] = useState(null);
  const [live, setLive] = useState(null);
  const [currency, setCurrency] = useState('gbp');
  const [cycle, setCycle] = useState('monthly');
  const [siteCount, setSiteCount] = useState(1);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing`)
      .then((r) => { if (!cancelled) setPricing(r.data); })
      .catch(() => { if (!cancelled) setPricing(null); });
    axios.get(`${API}/payments/pricing/live`)
      .then((r) => { if (!cancelled) { setLive(r.data); if (r.data?.detected_currency) setCurrency(r.data.detected_currency); } })
      .catch(() => { if (!cancelled) setLive(null); });
    return () => { cancelled = true; };
  }, [API]);

  const CCY = { gbp: '£', eur: '€', usd: '$' };
  const annual = cycle === 'annual';
  const priceFor = (moduleId) => {
    const node = live?.pricing?.[moduleId]?.[currency];
    if (!node) return null;
    const minor = annual ? node.annual : node.monthly;
    return minor == null ? null : minor / 100;
  };
  const fmtPrice = (moduleId) => {
    const v = priceFor(moduleId);
    if (v == null) return null;
    return `${CCY[currency] || ''}${Math.round(v)}${annual ? '/yr' : '/mo'}`;
  };

  const startCheckout = async (plan, opts = {}) => {
    setBusy(opts.module_id || plan);
    try {
      const { data } = await axios.post(
        `${API}/payments/checkout/flex`,
        { plan, origin_url: window.location.origin, currency, billing_cycle: cycle, ...opts },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (data?.url) {
        window.location.href = data.url;
      } else {
        toast.error('Could not open checkout');
        setBusy(null);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not open checkout');
      setBusy(null);
    }
  };

  const bundle = pricing?.bundle;
  const modules = pricing?.modules || [];
  const bundleTotal = bundle ? bundle.monthly + (siteCount - 1) * bundle.per_site : 0;

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="choose-plan-page">
      {/* Top bar */}
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="font-extrabold tracking-tight text-zinc-900 text-lg">
            Pulse Fitness<span className="text-[#19CDFF]">.AI</span>
          </span>
          <button
            type="button"
            onClick={logout}
            className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors"
            data-testid="choose-plan-signout"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-12 sm:py-16">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="max-w-2xl"
        >
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[#0E7490] font-semibold mb-4">
            <Sparkles size={13} /> Keep your account active
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-zinc-900 leading-[1.08]">
            {user?.full_name ? `Welcome back, ${user.full_name.split(' ')[0]}.` : 'Choose your plan.'}
          </h1>
          <p className="mt-4 text-base text-zinc-500 leading-relaxed">
            Your trial has ended. Pick the plan that fits and keep everything you&apos;ve already set up —
            no re-import, instant access. Choose the modules you need — each one is a standalone subscription.
          </p>
          <div className="mt-5 inline-flex items-center gap-2 text-xs text-zinc-500">
            <ShieldCheck size={14} className="text-emerald-500" />
            Secure checkout via Stripe · cancel anytime
          </div>
        </motion.div>

        {/* Currency + billing controls */}
        <div className="mt-8 flex flex-wrap items-center gap-3" data-testid="choose-plan-controls">
          <div className="inline-flex rounded-full border border-zinc-200 bg-white p-1" data-testid="currency-toggle">
            {['gbp', 'eur', 'usd'].map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCurrency(c)}
                className={`px-3.5 h-8 rounded-full text-sm font-semibold transition-colors ${currency === c ? 'bg-[#19CDFF] text-[#0A0C10]' : 'text-zinc-500 hover:text-zinc-900'}`}
                data-testid={`currency-${c}`}
              >
                {CCY[c]} {c.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center rounded-full border border-zinc-200 bg-white p-1" data-testid="billing-toggle">
            {[['monthly', 'Monthly'], ['annual', 'Annual']].map(([v, label]) => (
              <button
                key={v}
                type="button"
                onClick={() => setCycle(v)}
                className={`px-3.5 h-8 rounded-full text-sm font-semibold transition-colors ${cycle === v ? 'bg-[#19CDFF] text-[#0A0C10]' : 'text-zinc-500 hover:text-zinc-900'}`}
                data-testid={`billing-${v}`}
              >
                {label}
              </button>
            ))}
            {live?.annual_discount_pct ? (
              <span className="px-2.5 text-xs font-semibold text-[#0E7490]">Save {live.annual_discount_pct}%</span>
            ) : null}
          </div>
        </div>


        {!pricing && (
          <div className="mt-12 flex items-center gap-2 text-sm text-zinc-400" data-testid="choose-plan-loading">
            <Loader2 size={16} className="animate-spin" /> Loading plans…
          </div>
        )}

        {pricing && (
          <>
            {/* Individual modules */}
            <div className="mt-12">
              <h3 className="text-lg font-bold text-zinc-900" style={{ fontFamily: 'Nunito, sans-serif' }}>Choose your modules</h3>
              <p className="text-sm text-zinc-500 mt-1">Every module is a standalone subscription — mix and match, cancel anytime.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {[...modules].sort((a, b) => (a.id === 'operations' ? -1 : b.id === 'operations' ? 1 : 0)).map((m) => {
                  const featured = m.id === 'operations';
                  return (
                  <div
                    key={m.id}
                    className={`relative rounded-xl bg-white p-5 flex flex-col justify-between gap-4 transition-colors ${featured ? 'border-2 border-[#19CDFF] shadow-lg' : 'border border-zinc-200 hover:border-[#19CDFF]'}`}
                    data-testid={`choose-plan-module-${m.id}`}
                  >
                    {featured ? (
                      <span className="absolute -top-2.5 left-5 bg-[#19CDFF] text-[#0A0C10] text-[10px] font-bold uppercase tracking-[0.14em] px-2.5 py-0.5 rounded-full" data-testid="choose-plan-flagship-badge">Recommended</span>
                    ) : null}
                    <div>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-semibold text-zinc-900 capitalize">{featured ? 'Operations — Pulse Fitness Pro' : m.name}</span>
                        <span className="text-sm text-zinc-500" data-testid={`choose-plan-module-price-${m.id}`}><strong className="text-zinc-900">{fmtPrice(m.id) || `£${m.monthly.toFixed(0)}/mo`}</strong></span>
                      </div>
                      <p className="text-xs text-zinc-500 mt-1 leading-relaxed">{MODULE_BLURB[m.id] || ''}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => startCheckout('module', { module_id: m.id })}
                      disabled={busy === m.id}
                      className={`w-full h-10 rounded-full font-medium text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-60 ${featured ? 'bg-[#19CDFF] hover:bg-[#4DDBFF] text-[#0A0C10]' : 'border border-zinc-300 text-zinc-800 hover:border-[#19CDFF] hover:bg-[#E6F9FF]'}`}
                      data-testid={`choose-plan-module-checkout-${m.id}`}
                    >
                      {busy === m.id ? <Loader2 size={14} className="animate-spin" /> : null}
                      Choose {featured ? 'Pulse Fitness Pro' : m.name} <ArrowRight size={14} />
                    </button>
                  </div>
                  );
                })}
              </div>
            </div>

            {/* Talk to us */}
            <div className="mt-12 rounded-xl border border-zinc-200 bg-white p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-[#E6F9FF] flex items-center justify-center flex-shrink-0">
                  <MessageCircle size={18} className="text-[#0E7490]" />
                </div>
                <div>
                  <p className="font-semibold text-zinc-900 text-sm">Prefer to talk it through first?</p>
                  <p className="text-sm text-zinc-500">Not sure which plan fits? Our team will help you pick the right setup.</p>
                </div>
              </div>
              <a
                href="mailto:support@pulsefitness.ai?subject=Help%20choosing%20a%20PulseFitness%20plan"
                className="flex-shrink-0 h-10 px-5 rounded-lg border border-zinc-300 text-zinc-800 font-medium text-sm flex items-center justify-center hover:bg-zinc-50 transition-colors"
                data-testid="choose-plan-talk-to-us"
              >
                Talk to us
              </a>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
