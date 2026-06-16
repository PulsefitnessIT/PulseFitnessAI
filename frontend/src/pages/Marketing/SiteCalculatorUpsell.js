/**
 * Site-Calculator Upsell Widget
 *
 * Drops onto any module deep-dive page (`/platform/*`) to surface live
 * pricing for the Pulse Fitness Pro bundle as the visitor adjusts their site
 * count. Mirrors the math used on /pricing so quotes stay consistent.
 *
 * Bundle: £150/mo (1 site included) + £50/mo per additional site.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Sparkles, Plus, Minus, Building2 } from 'lucide-react';

import { openTrial } from './TrialSignupModal';

const BUNDLE_BASE = 150;
const PER_SITE = 50;
const MAX_SITES = 25;
const INCLUDED_PERKS = [
  'All four modules — Memberships, CRM, Marketing, Operations',
  'AI Triage, AI Director, RA generator',
  'Stripe + Mailchimp + open API integrations',
  '3-day free trial with every module unlocked',
];

export default function SiteCalculatorUpsell({ accent = 'var(--gx-brand-from)' }) {
  const [sites, setSites] = useState(1);

  const { total, extras } = useMemo(() => {
    const extra = Math.max(0, sites - 1);
    return { total: BUNDLE_BASE + extra * PER_SITE, extras: extra };
  }, [sites]);

  const dec = () => setSites((s) => Math.max(1, s - 1));
  const inc = () => setSites((s) => Math.min(MAX_SITES, s + 1));

  return (
    <section
      className="py-20 md:py-24 bg-white dark:bg-zinc-900"
      data-testid="module-site-calculator-upsell"
    >
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] border border-slate-200 bg-gradient-to-br from-white to-slate-50/60 dark:from-zinc-900 dark:to-zinc-950 p-8 md:p-12 shadow-[0_30px_80px_-40px_rgba(15,23,42,0.25)] dark:border-zinc-800"
          style={{ borderTopColor: accent, borderTopWidth: 4 }}
        >
          <div
            className="pointer-events-none absolute -top-24 -right-24 w-72 h-72 rounded-full opacity-20 blur-3xl"
            style={{ background: accent }}
          />

          <div className="relative grid lg:grid-cols-2 gap-10 items-center">
            {/* Left — value pitch */}
            <div>
              <span
                className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] dark:bg-zinc-900 dark:border-zinc-800"
                style={{ color: accent }}
              >
                <Sparkles size={12} /> One bundle · every module
              </span>
              <h2 className="mt-5 text-3xl md:text-4xl font-black tracking-tight leading-[1.1]">
                Price it for your estate <br className="hidden md:inline" />
                in real time.
              </h2>
              <p className="mt-4 text-slate-600 text-base md:text-lg leading-relaxed">
                Drag the slider to see what Pulse Fitness Pro costs across all your sites — every module
                included, no upgrade ladder. First site is on us; each extra site is just £{PER_SITE}/mo.
              </p>

              <ul className="mt-6 space-y-2">
                {INCLUDED_PERKS.map((perk) => (
                  <li key={perk} className="flex items-start gap-2 text-sm text-slate-700">
                    <Check size={15} className="mt-0.5 shrink-0" style={{ color: accent }} />
                    <span>{perk}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Right — interactive calculator */}
            <div className="rounded-3xl bg-slate-900 text-white p-6 md:p-8 shadow-2xl">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] font-bold text-white/50">
                    Live estimate
                  </p>
                  <p className="mt-1 text-sm text-white/80 inline-flex items-center gap-1.5">
                    <Building2 size={13} /> {sites} site{sites === 1 ? '' : 's'}
                  </p>
                </div>
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-white/10 border border-white/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                  data-testid="upsell-extra-sites"
                >
                  +{extras} extra
                </span>
              </div>

              <div className="mt-5 flex items-baseline gap-2">
                <span
                  className="text-5xl md:text-6xl font-black tracking-tighter tabular-nums"
                  data-testid="upsell-total-monthly"
                >
                  £{total}
                </span>
                <span className="text-sm text-white/60 font-semibold">/ month</span>
              </div>
              <p className="mt-1 text-xs text-white/50">
                £{BUNDLE_BASE} base + £{PER_SITE} × {extras} extra site{extras === 1 ? '' : 's'} · billed monthly
              </p>

              {/* Slider + +/- */}
              <div className="mt-6 space-y-3">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={dec}
                    disabled={sites <= 1}
                    className="w-10 h-10 rounded-full border border-white/15 bg-white/5 hover:bg-white/10 transition-colors flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
                    data-testid="upsell-site-decrement"
                    aria-label="Decrease site count"
                  >
                    <Minus size={14} />
                  </button>
                  <input
                    type="range"
                    min={1}
                    max={MAX_SITES}
                    step={1}
                    value={sites}
                    onChange={(e) => setSites(Number(e.target.value))}
                    className="gx-pricing-range gx-pricing-range--dark flex-1"
                    aria-label="Number of sites"
                    data-testid="upsell-site-range"
                    style={{
                      accentColor: accent,
                      '--fill-pct': `${((sites - 1) / (MAX_SITES - 1)) * 100}%`,
                    }}
                  />
                  <button
                    type="button"
                    onClick={inc}
                    disabled={sites >= MAX_SITES}
                    className="w-10 h-10 rounded-full border border-white/15 bg-white/5 hover:bg-white/10 transition-colors flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
                    data-testid="upsell-site-increment"
                    aria-label="Increase site count"
                  >
                    <Plus size={14} />
                  </button>
                </div>
                <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.16em] font-bold text-white/40">
                  <span>1 site</span>
                  <span>{MAX_SITES}+ sites</span>
                </div>
              </div>

              <button
                type="button"
                onClick={openTrial}
                className="mt-6 w-full rounded-full bg-white text-slate-900 font-bold text-sm px-5 py-3.5 inline-flex items-center justify-center gap-1.5 hover:bg-slate-100 shadow-[0_6px_18px_-6px_rgba(0,0,0,0.4)] transition-all dark:bg-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                data-testid="upsell-start-trial-cta"
              >
                Start 3-day Free Trial <ArrowRight size={15} />
              </button>
              <Link
                to="/pricing"
                className="mt-3 block text-center text-xs text-white/60 hover:text-white transition-colors"
                data-testid="upsell-see-full-pricing"
              >
                See full pricing & per-module options →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
