/**
 * Public Engineer Partner Network landing page — Iter 216h88.
 *
 * Mission: convert independent fitness contractors into Partner Engineers
 * through a clear, trustworthy story:
 *   1. What is the network?
 *   2. Why join? (real jobs, fair pricing, branded customer experience)
 *   3. How it works (apply → verify → £30/mo, drops to free at 10 referrals)
 *   4. Built-in advantages (mobile PWA, AI photo triage, signature capture)
 *   5. Strong CTA → /partner-engineer/apply (login-gated; bounces to signup
 *      if not logged in).
 *
 * Lives at /partners/engineers (indexable, no auth).
 */
import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, HardHat, ShieldCheck, MapPin, Wrench, Smartphone, Camera,
  PoundSterling, Users, BadgeCheck, CheckCircle2, Sparkles, Star, ChevronRight,
  Truck,
} from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { useSeo } from '@/utils/seo';

const TIER_TABLE = [
  { refs: '0',     fee: '£30',  badge: 'Starter',  hint: 'Standard tier — most new partners start here' },
  { refs: '5+',    fee: '£15',  badge: 'Active',   hint: 'Half-price as soon as you bring 5 active gym sites' },
  { refs: '10+',   fee: 'Free', badge: 'Founding', hint: 'Founding Partner — your monthly fee is on us' },
];

const PERKS = [
  { icon: PoundSterling, title: 'Get paid for referrals',
    body: '£100 / £200 / £400 per active gym site you introduce — tiered by their plan. Paid monthly in arrears.' },
  { icon: MapPin, title: 'Jobs routed to you',
    body: 'Customers in your area can request you specifically. We surface skill + postcode matches first.' },
  { icon: BadgeCheck, title: 'Verified profile',
    body: 'Showcase IOSH, PAT, CSCS, 18th Edition. Customers see your name, ★ rating and job count on the live-tracking page.' },
  { icon: Smartphone, title: 'Mobile-first engineer app',
    body: 'Offline-capable PWA — time tracking, photo capture, voice notes, signatures and PDF service reports.' },
  { icon: Camera, title: 'AI photo triage',
    body: 'Claude vision auto-tags severity and fault type as you snap. Save 5–10 minutes of admin per job.' },
  { icon: Star, title: 'Customer rating system',
    body: 'Star ratings appear on your profile and your monthly scorecard. Reach Founding Partner status faster.' },
];

const HOW_IT_WORKS = [
  { n: 1, title: 'Apply',          body: '5-minute application with your trades, certifications and coverage area.' },
  { n: 2, title: 'Get verified',    body: 'Our team reviews your details — usually within 2 working days.' },
  { n: 3, title: 'Subscribe',      body: 'Start the Partner Plan (£30/mo). Auto-discounts to £15 at 5 referrals, free at 10.' },
  { n: 4, title: 'Receive jobs',   body: 'Gyms invite you directly, or you accept open jobs in your postcodes.' },
  { n: 5, title: 'Get paid',       body: 'Monthly CSV payouts cover referral commission. Customer invoices are handled by the gym.' },
];

const APP_BULLETS = [
  'Travel + on-site time tracking',
  'Customer e-signature capture',
  'Voice-dictated wrap-up notes',
  'AI photo classification (Claude vision)',
  'Offline-first with auto-retry queue',
  'Parts allocation & van stock',
  'Branded service report PDF + email to customer',
  'Live "Uber-style" tracking link for customers',
  'Asset history — see prior visits at a glance',
  'In-app directions & customer one-tap dial',
];


export default function PartnerEngineerLanding() {
  useSeo({
    title: 'Engineer Partner Network — GymAxis AI',
    description: 'Join 100+ independent fitness engineers on the GymAxis Partner Network. £30/mo (drops to free at 10 referrals). Apply in 5 minutes.',
    canonical: 'https://www.gymaxisai.com/partners/engineers',
  });
  return (
    <MarketingShell>
      <Hero />
      <Perks />
      <Pricing />
      <HowItWorks />
      <EngineerApp />
      <FAQ />
      <FinalCta />
    </MarketingShell>
  );
}


/* ── Hero ──────────────────────────────────────────────── */
function Hero() {
  return (
    <section className="gx-grid-bg relative overflow-hidden" data-testid="pe-hero">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600" data-testid="pe-hero-eyebrow">
            <HardHat size={12} /> Partner Engineer Network
          </span>
          <h1 className="mt-5 text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tighter font-black leading-[1.04]" data-testid="pe-hero-headline">
            For independent<br />
            <span className="gx-gradient-text">fitness engineers.</span>
          </h1>
          <p className="mt-5 text-base sm:text-lg md:text-xl text-slate-600 leading-relaxed max-w-xl" data-testid="pe-hero-sub">
            Run your own business — but plug into the gym-operator network that already trusts GymAxis. Steady jobs, a powerful mobile app, and a fair monthly fee that drops to <strong className="text-slate-800">free</strong> once you refer 10 active gym sites.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              to="/partners/engineers/apply"
              className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap"
              data-testid="pe-hero-apply"
            >
              Start application <ArrowRight size={15} />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors whitespace-nowrap"
              data-testid="pe-hero-howitworks"
            >
              How it works <ChevronRight size={15} />
            </a>
          </div>
          <ul className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />£30/mo · drops automatically</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />Mobile app · offline-capable</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />Cancel anytime</li>
          </ul>
        </div>
        {/* Visual: stylised engineer profile card preview */}
        <div className="relative" data-testid="pe-hero-card">
          <div className="rounded-3xl bg-white shadow-xl border border-slate-100 p-6 max-w-sm mx-auto">
            <div className="flex items-center justify-between mb-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Your engineer</p>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-700">
                ✓ Verified
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-14 h-14 rounded-full flex items-center justify-center text-xl font-extrabold text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>S</div>
              <div>
                <p className="font-bold text-slate-800 text-base">Sarah</p>
                <div className="flex flex-wrap gap-3 text-xs text-slate-500 mt-0.5">
                  <span className="inline-flex items-center gap-0.5">
                    <Star size={11} className="text-amber-400" fill="currentColor" />
                    <span className="font-bold text-slate-700">4.9</span>
                    <span>· 26 reviews</span>
                  </span>
                  <span>52 jobs in 90 days</span>
                  <span>8+ yrs experience</span>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {['cardio', 'strength', 'electrical', 'plate-loaded'].map((s) => (
                <span key={s} className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-blue-700">{s}</span>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {['IOSH Working Safely', 'PAT Tester', 'CSCS Card'].map((q) => (
                <span key={q} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider border border-emerald-200 bg-emerald-50 text-emerald-700">✓ {q}</span>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <Truck size={14} className="text-blue-600" />
                <span><strong className="text-slate-800">On the way</strong> · ETA 14:23</span>
              </div>
              <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                This is what a gym customer sees when an engineer accepts their job. Your name. Your photo. Your real ratings.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


/* ── Perks ─────────────────────────────────────────────── */
function Perks() {
  return (
    <section className="py-20 md:py-28 bg-white" data-testid="pe-perks">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-12">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Why partner with GymAxis</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">The independent engineer's unfair advantage.</h2>
          <p className="mt-3 text-base text-slate-600 max-w-2xl mx-auto">
            You stay independent. We bring the gym-operator network, the customer-facing tech and the credit-card-ready customers.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {PERKS.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-3xl border border-slate-100 bg-slate-50/40 p-6" data-testid={`pe-perk-${title.toLowerCase().replace(/\W+/g, '-')}`}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                <Icon size={18} className="text-white" />
              </div>
              <h3 className="font-bold tracking-tight text-slate-900">{title}</h3>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


/* ── Pricing tiers ─────────────────────────────────────── */
function Pricing() {
  return (
    <section className="py-20 md:py-28" data-testid="pe-pricing">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-10">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Auto-tiered pricing</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Your fee drops as you grow the network.</h2>
          <p className="mt-3 text-base text-slate-600 max-w-2xl mx-auto">
            Bring gyms to GymAxis and we'll discount your monthly engineer fee automatically. No paperwork. Tiers re-evaluate each billing cycle.
          </p>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {TIER_TABLE.map(({ refs, fee, badge, hint }, i) => (
            <div
              key={badge}
              className={
                'relative rounded-3xl p-6 border ' +
                (i === 2
                  ? 'bg-gradient-to-br from-slate-900 to-slate-800 text-white border-slate-900 shadow-2xl'
                  : 'bg-white border-slate-200')
              }
              data-testid={`pe-pricing-${badge.toLowerCase()}`}
            >
              <p className={'text-[10px] font-bold uppercase tracking-[0.2em] ' + (i === 2 ? 'text-amber-300' : 'text-slate-400')}>
                {badge}
              </p>
              <p className={'mt-3 text-5xl font-black tracking-tighter ' + (i === 2 ? 'text-white' : 'text-slate-900')}>
                {fee}
                {fee !== 'Free' ? (
                  <span className={'text-base font-bold ml-1 ' + (i === 2 ? 'text-slate-300' : 'text-slate-500')}>/mo</span>
                ) : null}
              </p>
              <p className={'mt-1 text-sm ' + (i === 2 ? 'text-slate-300' : 'text-slate-500')}>
                {refs} active gym referral{refs === '0' ? '' : 's'}
              </p>
              <p className={'mt-4 text-sm leading-relaxed ' + (i === 2 ? 'text-slate-200' : 'text-slate-600')}>
                {hint}
              </p>
            </div>
          ))}
        </div>
        <p className="text-center mt-6 text-xs text-slate-500">
          Stripe billing · cancel any time · all prices ex-VAT.
        </p>
      </div>
    </section>
  );
}


/* ── How it works ──────────────────────────────────────── */
function HowItWorks() {
  return (
    <section className="py-20 md:py-28 bg-white" id="how-it-works" data-testid="pe-howitworks">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-12">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">How it works</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Five steps to your first job.</h2>
        </div>
        <ol className="space-y-3">
          {HOW_IT_WORKS.map(({ n, title, body }) => (
            <li key={n} className="flex items-start gap-4 rounded-2xl border border-slate-100 p-5 bg-slate-50/40" data-testid={`pe-step-${n}`}>
              <span className="w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center font-black text-lg text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                {n}
              </span>
              <div>
                <h3 className="font-bold text-slate-900">{title}</h3>
                <p className="text-sm text-slate-600 mt-1 leading-relaxed">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}


/* ── Engineer App showcase ─────────────────────────────── */
function EngineerApp() {
  return (
    <section className="py-20 md:py-28" data-testid="pe-app">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">The Engineer App</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">A pocket-sized service-desk that follows you to every site.</h2>
          <p className="mt-4 text-base text-slate-600 leading-relaxed max-w-xl">
            Built for the way real engineers work. Tap to clock on. Photograph the fault, sign off, hand over a branded PDF — all from your phone, even on a basement Wi-Fi.
          </p>
          <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-slate-700">
            {APP_BULLETS.map((b) => (
              <li key={b} className="flex items-start gap-2">
                <CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative" data-testid="pe-app-visual">
          {/* Stylised "phone" mock */}
          <div className="mx-auto max-w-xs rounded-[40px] border-8 border-slate-900 bg-slate-900 shadow-2xl overflow-hidden">
            <div className="bg-slate-100 px-4 py-3 flex items-center justify-between text-xs">
              <span className="font-bold text-slate-700">9:41</span>
              <span className="font-bold text-slate-700">●●● ●●</span>
            </div>
            <div className="bg-white p-4 space-y-3 text-left text-xs h-[440px] overflow-hidden">
              <div className="flex items-center justify-between">
                <p className="font-extrabold text-slate-900 text-sm">Job · CASE-1287</p>
                <span className="px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase tracking-wider bg-blue-100 text-blue-700">On site</span>
              </div>
              <p className="text-slate-500">PureGym Birmingham · Treadmill #4 · belt slip at 12 km/h</p>
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-amber-900">
                <p className="text-[10px] font-bold uppercase tracking-wider">⚡ Asset history</p>
                <p className="mt-1">3 prior visits in 90 days · last: BELT_SLIP · ★★★★★</p>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-2.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Time on site</p>
                <p className="font-bold text-slate-800 mt-0.5">Travel 25m · On site 42m</p>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-2.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Parts (1)</p>
                <p className="font-semibold text-slate-800 mt-0.5">1 × BELT-001 <span className="opacity-60">· from van</span></p>
              </div>
              <button type="button" className="w-full mt-2 rounded-lg bg-blue-600 text-white font-bold py-2.5 text-sm">
                View report
              </button>
              <button type="button" className="w-full rounded-lg border border-slate-200 text-slate-700 font-bold py-2.5 text-sm">
                Send to customer
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


/* ── FAQ ───────────────────────────────────────────────── */
function FAQ() {
  const items = [
    { q: 'Do I work for GymAxis?',
      a: 'No — you stay completely independent. Gyms invoice their customers directly, and you run your own business. We connect you, equip you with the app, and pay your referral commissions.' },
    { q: 'Who handles invoicing customers?',
      a: 'The gym (our customer) bills the end customer. Your relationship is with the gym — they decide how to pay you per job. You can use Sage 200 integration for time-card reporting.' },
    { q: 'What are the £30/mo for?',
      a: 'Access to the Engineer App (mobile PWA), the gym-operator network, customer-facing tracking & service-report tooling, and AI tools like photo triage. The fee drops to £15 once you bring 5 referrals and is waived at 10.' },
    { q: 'How fast does the fee tier update?',
      a: 'Automatically at each Stripe billing cycle. We re-count your active gym referrals at renewal and apply the lower tier.' },
    { q: 'Do I need my own insurance?',
      a: 'Yes — public liability and (where relevant) PAT/electrical insurance are required. We verify cover during the application.' },
    { q: 'Can a gym add me to one specific job without me joining?',
      a: 'Yes. Gyms can issue you a Job Grant that unlocks a single case at a time, free for you. Most engineers convert to a paid Partner Plan once they receive 2–3 grants.' },
  ];
  return (
    <section className="py-20 md:py-28 bg-white" data-testid="pe-faq">
      <div className="max-w-4xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-10">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">FAQ</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Common questions.</h2>
        </div>
        <dl className="space-y-3">
          {items.map(({ q, a }, i) => (
            <details key={q} className="group rounded-2xl border border-slate-100 bg-slate-50/40 p-5" data-testid={`pe-faq-${i}`}>
              <summary className="font-bold cursor-pointer text-slate-900 list-none flex items-start gap-3">
                <ChevronRight size={18} className="mt-0.5 flex-shrink-0 transition-transform group-open:rotate-90 text-slate-400" />
                <span>{q}</span>
              </summary>
              <dd className="mt-3 ml-7 text-sm text-slate-600 leading-relaxed">{a}</dd>
            </details>
          ))}
        </dl>
      </div>
    </section>
  );
}


/* ── Final CTA ─────────────────────────────────────────── */
function FinalCta() {
  return (
    <section className="py-24 md:py-32" data-testid="pe-final-cta">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-16 text-center text-white"
          style={{ background: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)' }}
        >
          <div className="absolute inset-0 opacity-30 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.6), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.4), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-4xl md:text-5xl lg:text-6xl font-black tracking-tighter leading-[1.04]">Independent engineer?<br />Get on the network.</h2>
            <p className="mt-5 text-lg text-white/90 max-w-xl mx-auto">
              5-minute application. Decision within 2 working days. £30/mo · drops automatically as you bring gyms to GymAxis.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <Link
                to="/partners/engineers/apply"
                className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow"
                data-testid="pe-final-apply"
              >
                Start application <ArrowRight size={15} />
              </Link>
              <Link
                to="/contact"
                className="inline-flex items-center gap-1.5 rounded-full border-2 border-white/40 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors"
                data-testid="pe-final-contact"
              >
                Talk to us first <ArrowRight size={15} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
