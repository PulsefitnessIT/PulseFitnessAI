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
  const [siteCount, setSiteCount] = useState(1);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing`)
      .then((r) => { if (!cancelled) setPricing(r.data); })
      .catch(() => { if (!cancelled) setPricing(null); });
    return () => { cancelled = true; };
  }, [API]);

  const startCheckout = async (plan, opts = {}) => {
    setBusy(opts.module_id || plan);
    try {
      const { data } = await axios.post(
        `${API}/payments/checkout/flex`,
        { plan, origin_url: window.location.origin, ...opts },
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
            Pulse Fitness<span className="text-blue-600">.AI</span>
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
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-blue-600 font-semibold mb-4">
            <Sparkles size={13} /> Keep your account active
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-zinc-900 leading-[1.08]">
            {user?.full_name ? `Welcome back, ${user.full_name.split(' ')[0]}.` : 'Choose your plan.'}
          </h1>
          <p className="mt-4 text-base text-zinc-500 leading-relaxed">
            Your trial has ended. Pick the plan that fits and keep everything you&apos;ve already set up —
            no re-import, instant access. Pick the full bundle or just the modules you actually use.
          </p>
          <div className="mt-5 inline-flex items-center gap-2 text-xs text-zinc-500">
            <ShieldCheck size={14} className="text-emerald-500" />
            Secure checkout via Stripe · cancel anytime
          </div>
        </motion.div>

        {!pricing && (
          <div className="mt-12 flex items-center gap-2 text-sm text-zinc-400" data-testid="choose-plan-loading">
            <Loader2 size={16} className="animate-spin" /> Loading plans…
          </div>
        )}

        {pricing && (
          <>
            {/* Recommended bundle */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
              className="mt-10 rounded-2xl border-2 border-blue-600 bg-white shadow-lg overflow-hidden"
              data-testid="choose-plan-bundle"
            >
              <div className="bg-blue-600 px-6 py-2 text-center">
                <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-white">
                  Recommended · everything included
                </span>
              </div>
              <div className="p-6 sm:p-8 grid gap-8 md:grid-cols-2 items-center">
                <div>
                  <h2 className="text-2xl font-extrabold text-zinc-900">{bundle.name}</h2>
                  <p className="mt-2 text-sm text-zinc-500">
                    Every module — Operations, CRM, Marketing &amp; Memberships — in one subscription.
                  </p>
                  <ul className="mt-4 space-y-2">
                    {['All four modules unlocked', 'AI features included', 'Priority support', 'Add sites anytime'].map((f) => (
                      <li key={f} className="flex items-center gap-2 text-sm text-zinc-700">
                        <Check size={15} className="text-emerald-500 flex-shrink-0" /> {f}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl bg-zinc-50 border border-zinc-200 p-6">
                  <div className="flex items-end gap-1">
                    <span className="text-4xl font-extrabold text-zinc-900">£{bundleTotal.toFixed(0)}</span>
                    <span className="text-sm text-zinc-500 mb-1">/month</span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1">
                    £{bundle.monthly.toFixed(0)} base + £{bundle.per_site.toFixed(0)}/mo per extra site
                  </p>

                  {/* Site count selector */}
                  <div className="mt-4 flex items-center justify-between">
                    <span className="text-sm font-medium text-zinc-700">Number of sites</span>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setSiteCount((n) => Math.max(1, n - 1))}
                        className="w-8 h-8 rounded-lg border border-zinc-300 flex items-center justify-center text-zinc-600 hover:bg-white disabled:opacity-40"
                        disabled={siteCount <= 1}
                        data-testid="choose-plan-site-minus"
                      >
                        <Minus size={14} />
                      </button>
                      <span className="w-6 text-center font-semibold text-zinc-900" data-testid="choose-plan-site-count">{siteCount}</span>
                      <button
                        type="button"
                        onClick={() => setSiteCount((n) => Math.min(50, n + 1))}
                        className="w-8 h-8 rounded-lg border border-zinc-300 flex items-center justify-center text-zinc-600 hover:bg-white disabled:opacity-40"
                        disabled={siteCount >= 50}
                        data-testid="choose-plan-site-plus"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Order summary — removes surprise at the Stripe screen */}
                  <div
                    className="mt-4 pt-4 border-t border-zinc-200 flex items-baseline justify-between"
                    data-testid="choose-plan-bundle-summary"
                  >
                    <span className="text-sm text-zinc-600">
                      {bundle.name} · {siteCount} site{siteCount !== 1 ? 's' : ''}
                    </span>
                    <span className="text-sm text-zinc-900">
                      <strong className="text-base">£{bundleTotal.toFixed(0)}</strong>/mo, billed monthly
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => startCheckout('bundle', { site_count: siteCount })}
                    disabled={busy === 'bundle'}
                    className="mt-4 w-full h-12 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-60"
                    data-testid="choose-plan-bundle-checkout"
                  >
                    {busy === 'bundle' ? <Loader2 size={16} className="animate-spin" /> : null}
                    Continue to secure payment <ArrowRight size={16} />
                  </button>
                </div>
              </div>
            </motion.div>

            {/* Individual modules */}
            <div className="mt-12">
              <h3 className="text-sm font-semibold text-zinc-900">Or pick just the modules you need</h3>
              <p className="text-sm text-zinc-500 mt-1">Each module is a standalone monthly subscription.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {modules.map((m) => (
                  <div
                    key={m.id}
                    className="rounded-xl border border-zinc-200 bg-white p-5 flex flex-col justify-between gap-4 hover:border-blue-300 transition-colors"
                    data-testid={`choose-plan-module-${m.id}`}
                  >
                    <div>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-semibold text-zinc-900 capitalize">{m.name}</span>
                        <span className="text-sm text-zinc-500"><strong className="text-zinc-900">£{m.monthly.toFixed(0)}</strong>/mo</span>
                      </div>
                      <p className="text-xs text-zinc-500 mt-1 leading-relaxed">{MODULE_BLURB[m.id] || ''}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => startCheckout('module', { module_id: m.id })}
                      disabled={busy === m.id}
                      className="w-full h-10 rounded-lg border border-zinc-300 text-zinc-800 font-medium text-sm flex items-center justify-center gap-2 hover:bg-zinc-50 transition-colors disabled:opacity-60"
                      data-testid={`choose-plan-module-checkout-${m.id}`}
                    >
                      {busy === m.id ? <Loader2 size={14} className="animate-spin" /> : null}
                      Choose {m.name} <ArrowRight size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Talk to us */}
            <div className="mt-12 rounded-xl border border-zinc-200 bg-white p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                  <MessageCircle size={18} className="text-blue-600" />
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
