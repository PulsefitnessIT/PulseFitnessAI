/**
 * GymAxis Pricing — Iter 215be (May 1, 2026)
 *
 * New flexible pricing model:
 *   • Bundle: GymAxis Pro £150/mo (all 4 modules + AI + integrations + 1 site)
 *   • Add additional sites at +£50/mo each (live site-slider).
 *   • Or pick individual modules:
 *       - Memberships £29/mo
 *       - CRM £49/mo
 *       - Marketing £49/mo
 *       - Operations £69/mo
 *
 * All plans include a 3-day free trial with every module unlocked. CTA
 * triggers the in-app trial signup modal (per user choice 215be — option
 * "a"). Stripe checkout activates automatically once Price IDs are
 * configured in /app/backend/.env (STRIPE_PRICE_GYMAXIS_PRO,
 * STRIPE_PRICE_SITE_ADDON, plus per-module STRIPE_PRICE_MEMBERSHIPS etc.).
 */
import { useMemo, useState } from 'react';
import { ArrowRight, Check, Sparkles, Users, Megaphone, Wrench, Star, Plus, Minus, PlayCircle } from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { openTrial } from './TrialSignupModal';
import { openPreview } from './ProductPreviewModal';
import ROICalculator from './ROICalculator';
import MigrationGuarantee from './MigrationGuarantee';
import { useSeo } from '@/utils/seo';

const BUNDLE = {
  id: 'gymaxis_pro',
  name: 'GymAxis Pro',
  tagline: 'The full operating system. All modules. All AI. All integrations.',
  base: 150,
  perSite: 50,
  highlight: true,
  perks: [
    'All six modules unlocked — Operations, CRM, Memberships, Marketing, Staffing & Reporting',
    'AI built into every module — fault triage, lead scoring, churn early-warning, campaign autopilot, RA generator',
    'Stripe + Mailchimp + Twilio + Sage 200 / Sicon bridge + open API',
    'Master Admin multi-site console with head-office onboarding wizard',
    'Real-time KPIs and tamper-evident audit log across every site',
    'Family Auto-Bill, Family Wallet, sibling discounts',
    'Six selling models, six payroll exports, six reporting cohorts — one platform',
    'Priority support + white-glove onboarding',
  ],
};

const MODULES = [
  {
    id: 'memberships',
    name: 'Memberships',
    icon: Users,
    monthly: 29,
    tagline: 'For studios that just need members + bookings.',
    accent: 'from-blue-500 to-cyan-400',
    features: [
      'Drop-ins, monthly plans, class packs',
      'Public booking page + embed widget',
      'Branded PWA member portal',
      'Stripe payments + email receipts',
      'Family Auto-Bill (add-on)',
    ],
  },
  {
    id: 'marketing',
    name: 'Marketing + CRM Lite',
    icon: Megaphone,
    monthly: 49,
    tagline: 'Everything you need to capture, segment, and convert leads.',
    accent: 'from-purple-500 to-pink-400',
    badge: 'Includes contact directory',
    features: [
      'Email + SMS campaigns',
      'Audience builder + segments',
      'AI Director (campaign autopilot)',
      'Brand Kit + content templates',
      'Contact directory + lead capture forms',
      'CSV import + custom properties',
    ],
    footnote: 'Need pipelines, deals & shared inbox? Upgrade to full CRM (+£49) any time.',
  },
  {
    id: 'crm',
    name: 'CRM (Full)',
    icon: Star,
    monthly: 49,
    tagline: 'Pipelines, deals, shared inbox — for sales-led studios.',
    accent: 'from-emerald-500 to-teal-400',
    badge: 'Most powerful',
    features: [
      'Pipeline + deals + lead scoring',
      'Shared inbox for the whole team',
      'Email sequences + templates',
      'Calendar + task automation',
      'CPQ + quotes (add-on)',
      'Custom properties + reporting',
    ],
    footnote: 'Already on Marketing? CRM Full adds pipelines + deals + inbox on top of your contact directory.',
  },
  {
    id: 'operations',
    name: 'Operations',
    icon: Wrench,
    monthly: 69,
    tagline: 'Assets, faults, RAs, supplier portal — keep your sites safe.',
    accent: 'from-amber-500 to-orange-400',
    features: [
      'Asset register + barcode/QR scan',
      'Fault triage with AI',
      'Risk Assessments + PPM',
      'Supplier portal + work orders',
      'Audit log + compliance reports',
    ],
  },
];

// Sum of all individual module prices — used to show the "save vs buying
// individually" badge on the bundle card.
const MODULES_TOTAL = MODULES.reduce((s, m) => s + m.monthly, 0); // £186

function SiteSlider({ value, onChange }) {
  const min = 1, max = 10;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 dark:bg-zinc-900 dark:border-zinc-800" data-testid="gx-pricing-site-slider">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">Number of sites</div>
          <div className="text-[13px] text-slate-500 mt-0.5">First site included · +£{BUNDLE.perSite}/mo per extra site</div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onChange(Math.max(min, value - 1))}
            disabled={value <= min}
            className="w-9 h-9 rounded-full border border-slate-200 flex items-center justify-center text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed dark:bg-zinc-900 dark:border-zinc-800"
            aria-label="Remove site"
            data-testid="gx-site-decrement"
          >
            <Minus size={14} />
          </button>
          <div className="w-12 text-center font-bold text-2xl text-slate-900 tabular-nums dark:text-zinc-100" data-testid="gx-site-count">{value}</div>
          <button
            type="button"
            onClick={() => onChange(Math.min(max, value + 1))}
            disabled={value >= max}
            className="w-9 h-9 rounded-full border border-slate-200 flex items-center justify-center text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed dark:bg-zinc-900 dark:border-zinc-800"
            aria-label="Add site"
            data-testid="gx-site-increment"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="gx-pricing-range gx-pricing-range--dark w-full"
        style={{ '--fill-pct': `${((value - min) / (max - min)) * 100}%` }}
        data-testid="gx-site-range"
        aria-label="Number of sites"
      />
      <div className="mt-2 flex justify-between text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
        <span>1</span><span>5</span><span>10+</span>
      </div>
    </div>
  );
}

function BundleHero({ siteCount, setSiteCount, billingCycle, setBillingCycle }) {
  const isAnnual = billingCycle === 'annual';
  const baseMonthly = BUNDLE.base + Math.max(0, siteCount - 1) * BUNDLE.perSite;
  const annualPaid = baseMonthly * 10; // 10 months for the price of 12
  const annualEqMonthly = (annualPaid / 12).toFixed(2);
  const total = isAnnual ? annualPaid : baseMonthly;
  const periodLabel = isAnnual ? '/yr' : '/mo';
  const savings = MODULES_TOTAL - BUNDLE.base; // £186 - £150 = £36 savings
  return (
    <div className="relative" data-testid="gx-pricing-bundle">
      {/* Most Popular ribbon */}
      <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white text-[11px] font-bold uppercase tracking-[0.18em] px-3 py-1 shadow-[0_8px_20px_-6px_rgba(37,99,235,0.45)]">
          <Sparkles size={12} /> Most Popular
        </span>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-[0_20px_50px_-20px_rgba(15,23,42,0.18)] dark:bg-zinc-900 dark:border-zinc-800">
        {/* Billing cycle toggle */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1 dark:bg-zinc-900 dark:border-zinc-800" data-testid="gx-billing-toggle">
            <button
              type="button"
              onClick={() => setBillingCycle('monthly')}
              data-testid="gx-billing-monthly"
              className={`px-4 py-1.5 rounded-full text-xs font-semibold transition ${!isAnnual ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`}
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setBillingCycle('annual')}
              data-testid="gx-billing-annual"
              className={`px-4 py-1.5 rounded-full text-xs font-semibold transition flex items-center gap-1.5 ${isAnnual ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`}
            >
              Annual
              <span className="px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px]">Save 17%</span>
            </button>
          </div>
        </div>

        <div className="grid lg:grid-cols-12 gap-6 lg:gap-10 items-start">
          {/* Left: name + perks */}
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
              <Sparkles size={11} className="text-[var(--gx-brand-from)]" /> Recommended
            </div>
            <h2 className="mt-3 text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 dark:text-zinc-100">
              {BUNDLE.name}
            </h2>
            <p className="mt-2 text-base text-slate-600 max-w-md">{BUNDLE.tagline}</p>

            <ul className="mt-5 grid sm:grid-cols-2 gap-x-4 gap-y-2.5">
              {BUNDLE.perks.map((p) => (
                <li key={p} className="flex items-start gap-2 text-sm text-slate-700">
                  <Check size={15} className="text-emerald-500 shrink-0 mt-0.5" />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Right: price card + slider + CTA */}
          <div className="lg:col-span-5">
            <div className="rounded-2xl bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] p-5 sm:p-6 text-white shadow-[0_18px_45px_-18px_rgba(91,91,245,0.55)]">
              <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/80">Your price</div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-5xl font-black tracking-tighter tabular-nums" data-testid="gx-bundle-total">£{total.toLocaleString('en-GB')}</span>
                <span className="text-base font-semibold text-white/80">{periodLabel}</span>
              </div>
              <div className="mt-1 text-[13px] text-white/90 tabular-nums" data-testid="gx-bundle-breakdown">
                {isAnnual
                  ? `≈ £${annualEqMonthly}/mo · 2 months free vs monthly`
                  : `£${BUNDLE.base} base + £${BUNDLE.perSite} × ${Math.max(0, siteCount - 1)} extra site${siteCount === 2 ? '' : 's'}`}
              </div>

              <div className="mt-4">
                <SiteSlider value={siteCount} onChange={setSiteCount} />
              </div>

              <button
                type="button"
                onClick={openTrial}
                className="mt-4 w-full rounded-full bg-white text-slate-900 font-bold text-sm px-5 py-3 inline-flex items-center justify-center gap-1.5 hover:bg-slate-50 shadow-[0_6px_16px_-6px_rgba(0,0,0,0.25)] dark:bg-zinc-900 dark:text-zinc-100"
                data-testid="gx-bundle-cta"
              >
                Start 3-day Free Trial <ArrowRight size={14} />
              </button>
              <p className="mt-2 text-center text-[11px] text-white/85">All modules unlocked · No credit card · Cancel any time</p>

              {/* Savings vs individually badge — only shown at 1 site to keep it accurate */}
              {siteCount === 1 && savings > 0 && (
                <div className="mt-3 rounded-full bg-white/10 border border-white/20 px-3 py-1.5 text-[12px] font-semibold text-white text-center" data-testid="gx-bundle-savings">
                  Save £{savings}/mo vs buying modules separately
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ModuleCard({ mod }) {
  const Icon = mod.icon;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 transition-shadow hover:shadow-[0_18px_45px_-18px_rgba(15,23,42,0.18)] flex flex-col dark:bg-zinc-900 dark:border-zinc-800" data-testid={`gx-module-${mod.id}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${mod.accent} flex items-center justify-center text-white shadow-[0_8px_20px_-8px_rgba(37,99,235,0.35)] shrink-0`}>
          <Icon size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold tracking-tight text-slate-900 leading-tight dark:text-zinc-100">{mod.name}</h3>
          <p className="text-[13px] text-slate-500 mt-0.5">{mod.tagline}</p>
        </div>
      </div>
      {mod.badge && (
        <div className="mt-3 inline-flex w-fit items-center gap-1 rounded-full bg-slate-50 border border-slate-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
          {mod.badge}
        </div>
      )}
      <div className="mt-4 flex items-baseline gap-1">
        <span className="text-3xl font-black tracking-tighter text-slate-900 tabular-nums dark:text-zinc-100">£{mod.monthly}</span>
        <span className="text-sm font-semibold text-slate-500">/mo</span>
      </div>
      <ul className="mt-4 space-y-2 flex-1">
        {mod.features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-[13px] text-slate-700">
            <Check size={14} className="text-emerald-500 shrink-0 mt-0.5" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      {mod.footnote && (
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500 border-t border-slate-100 pt-3 dark:border-zinc-800" data-testid={`gx-module-${mod.id}-footnote`}>
          {mod.footnote}
        </p>
      )}
      <button
        type="button"
        onClick={openTrial}
        className="mt-5 w-full rounded-full border border-slate-200 px-4 py-2.5 text-[13px] font-bold text-slate-800 hover:border-[var(--gx-brand-from)] hover:text-slate-900 hover:bg-slate-50 transition-all dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
        data-testid={`gx-module-${mod.id}-cta`}
      >
        Start with {mod.name}
      </button>
    </div>
  );
}

const FAQ = [
  { q: 'Is there a free trial?', a: 'Yes — every plan includes a 3-day free trial with all modules unlocked. No credit card required. Bring your data, kick the tires, cancel any time.' },
  { q: 'Can I add or remove sites later?', a: 'Yes. Add a site any time and your subscription updates automatically with prorated billing. Remove a site at the end of the billing period — no penalties, no lock-ins.' },
  { q: 'Can I start with just one module and add more?', a: 'Absolutely. Start with the module that solves your biggest pain. When you outgrow it, upgrade to GymAxis Pro and unlock everything else for £150/mo — usually cheaper than two individual modules.' },
  { q: 'How does multi-site billing work?', a: 'GymAxis Pro is £150/mo and includes one site. Every additional site is £50/mo, billed on the same invoice. So 3 sites is £250/mo, 5 sites is £350/mo. Sites can have separate branding, staff, and reports.' },
  { q: 'What happens after my 3-day trial?', a: 'You\'ll be invited to add a card to keep your modules. If you don\'t convert, your account moves to read-only — your data is preserved for 30 days so you never lose it.' },
  { q: 'Do you offer Enterprise pricing?', a: 'Yes. For chains, franchises, or 10+ sites with advanced needs (SSO, dedicated CSM, custom DPA, ERP sync) — talk to our team.' },
];

export default function GymAxisPricingPage() {
  const [siteCount, setSiteCount] = useState(1);
  const [billingCycle, setBillingCycle] = useState('monthly');

  useSeo({
    title: 'Pricing — GymAxis AI · From £29/mo',
    description: 'Pick a single module from £29/mo or unlock everything with GymAxis Pro at £150/mo. 3-day free trial, all modules unlocked, no credit card.',
    canonical: 'https://www.gymaxisai.com/pricing',
    structuredData: {
      '@context': 'https://schema.org',
      '@type': 'Product',
      name: 'GymAxis AI',
      description: 'All-in-one operations platform for fitness operators.',
      brand: { '@type': 'Brand', name: 'GymAxis AI' },
      offers: [
        { '@type': 'Offer', name: 'GymAxis Pro', price: '150.00', priceCurrency: 'GBP', priceSpecification: { '@type': 'UnitPriceSpecification', price: '150.00', priceCurrency: 'GBP', referenceQuantity: { '@type': 'QuantitativeValue', value: 1, unitCode: 'MON' } } },
        { '@type': 'Offer', name: 'Memberships', price: '29.00', priceCurrency: 'GBP' },
        { '@type': 'Offer', name: 'CRM',         price: '49.00', priceCurrency: 'GBP' },
        { '@type': 'Offer', name: 'Marketing',   price: '49.00', priceCurrency: 'GBP' },
        { '@type': 'Offer', name: 'Operations',  price: '69.00', priceCurrency: 'GBP' },
      ],
    },
  });

  const moduleTotal = useMemo(() => MODULES_TOTAL, []);

  return (
    <MarketingShell>
      <main className="gx-marketing min-h-screen pt-20" data-testid="gx-pricing-page">
        <section className="gx-grid-bg pt-12 pb-10 sm:pt-16 sm:pb-14">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-3xl mx-auto">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 backdrop-blur px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800">
                <Sparkles size={11} className="text-[var(--gx-brand-from)]" /> Simple. Transparent. Scalable.
              </span>
              <h1 className="mt-4 text-4xl sm:text-5xl md:text-6xl font-black tracking-tighter leading-[1.04] text-slate-900 dark:text-zinc-100" data-testid="gx-pricing-title">
                Start small.<br />
                <span className="gx-gradient-text">Scale at your pace.</span>
              </h1>
              <p className="mt-5 text-base sm:text-lg text-slate-600 max-w-xl mx-auto">
                Pick a single module, or unlock the full platform with GymAxis Pro. Every plan grows with you — add modules and sites in a click.
              </p>
            </div>

            <div className="mt-10">
              <BundleHero siteCount={siteCount} setSiteCount={setSiteCount} billingCycle={billingCycle} setBillingCycle={setBillingCycle} />
            </div>
          </div>
        </section>

        {/* Individual modules */}
        <section className="py-12 sm:py-16 bg-slate-50/50 border-y border-slate-200/60">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center max-w-2xl mx-auto">
              <h2 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 dark:text-zinc-100">Or just pick what you need</h2>
              <p className="mt-3 text-base text-slate-600">
                Start with the module that solves your biggest pain. Upgrade to GymAxis Pro any time — together they'd be £{moduleTotal}/mo, the bundle is £{BUNDLE.base}.
              </p>
            </div>
            <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5" data-testid="gx-pricing-modules-grid">
              {MODULES.map((m) => <ModuleCard key={m.id} mod={m} />)}
            </div>
          </div>
        </section>

        {/* ROI Calculator */}
        <ROICalculator />

        {/* Migration guarantee */}
        <MigrationGuarantee />

        {/* FAQ */}
        <section className="py-12 sm:py-16 bg-slate-50/40 border-t border-slate-200/60">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 className="text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 text-center dark:text-zinc-100">Frequently asked</h2>
            <div className="mt-8 space-y-3" data-testid="gx-pricing-faq">
              {FAQ.map((f, i) => (
                <details key={i} className="group rounded-2xl border border-slate-200 bg-white p-5 cursor-pointer dark:bg-zinc-900 dark:border-zinc-800">
                  <summary className="flex items-center justify-between font-bold text-slate-900 list-none dark:text-zinc-100">
                    {f.q}
                    <Plus size={16} className="text-slate-400 group-open:rotate-45 transition-transform" />
                  </summary>
                  <p className="mt-3 text-[14px] text-slate-600 leading-relaxed">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="py-16 sm:py-20">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="rounded-3xl bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] p-8 sm:p-12 text-center text-white shadow-[0_24px_60px_-20px_rgba(91,91,245,0.55)]">
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-black tracking-tighter leading-[1.06]">3 days free. All modules unlocked. No credit card.</h2>
              <p className="mt-5 text-base sm:text-lg text-white/90 max-w-xl mx-auto">Get every module + every AI feature for 3 days. Cancel any time. We're real humans on the other end if you need help.</p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                <button type="button" onClick={openTrial} className="rounded-full bg-white text-slate-900 font-bold text-sm px-6 py-3 inline-flex items-center gap-1.5 hover:bg-slate-50 dark:bg-zinc-900 dark:text-zinc-100" data-testid="gx-pricing-final-cta">
                  Start Free Trial <ArrowRight size={14} />
                </button>
                <button type="button" onClick={openPreview} className="rounded-full border border-white/30 px-6 py-3 text-sm font-bold text-white hover:bg-white/10 inline-flex items-center gap-1.5" data-testid="gx-pricing-preview">
                  <PlayCircle size={14} /> See it in action
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
    </MarketingShell>
  );
}
