/**
 * Public Engineer Partner Network landing page — Iter 216h88.
 *
 * Mission: convert independent fitness contractors into Partner Engineers
 * through a clear, trustworthy story:
 *   1. What is the network?
 *   2. Why join? (real jobs, fair pricing, branded customer experience)
 *   3. How it works (apply → verify → £30/mo, drops to free at 10 referrals)
 *   4. Built-in advantages (mobile PWA, AI photo triage, signature capture)
 *   5. Strong CTA → /partners/engineers/apply (the canonical single
 *      public application form — no login required).
 *
 * Lives at /partners/engineers (indexable, no auth).
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowRight, HardHat, MapPin, Smartphone, Camera,
  PoundSterling, BadgeCheck, CheckCircle2, Star, ChevronRight,
  Truck, Users, Clock,
} from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import LiveEngineerAppPreview from './LiveEngineerAppPreview';
import { useSeo } from '@/utils/seo';
import { useUtmAttribution } from '@/hooks/useUtmAttribution';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

// Iter 220ea·30 — this landing IS the engineer tester recruitment
// campaign, so every apply CTA carries cohort=tester (counts the
// applicant against the 10 spaces + grants the free trial on approval).
const withCohort = (href) => href + (href.includes('?') ? '&' : '?') + 'cohort=tester';

/* Iter 220ea·30 — live tester-cohort capacity for the "WE NEED YOU!"
   recruitment campaign. Reads the public recruitment-status endpoint
   and shows an urgency counter ("X of 10 tester spaces left"). */
function TesterSpaces() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/partners/recruitment/status`)
      .then(r => { if (alive) setStatus(r.data); })
      .catch(() => { /* non-blocking — hide the badge on failure */ });
    return () => { alive = false; };
  }, []);
  if (!status) return null;
  const { remaining, total_spaces, trial_days, open } = status;
  return (
    <div
      className="mt-6 inline-flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-2xl border border-[var(--gx-brand-to)]/30 bg-white/80 px-4 py-2.5 shadow-sm backdrop-blur dark:bg-zinc-900/70"
      data-testid="pe-tester-spaces"
    >
      <span className="inline-flex items-center gap-1.5 text-sm font-black tracking-tight" style={{ color: 'var(--gx-brand-from)' }}>
        <Users size={15} />
        {open
          ? <>Only <span data-testid="pe-tester-remaining">{remaining}</span> of {total_spaces} tester spaces left</>
          : <>All {total_spaces} tester spaces filled — join the waitlist</>}
      </span>
      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-600">
        <Clock size={12} /> {trial_days}-day free trial
      </span>
    </div>
  );
}

const TIER_TABLE = [
  { refs: '0',     fee: '£30',  badge: 'Starter',  hint: 'Standard tier — most new partners start here' },
  { refs: '5+',    fee: '£15',  badge: 'Active',   hint: 'Half-price as soon as you bring 5 active gym sites' },
  { refs: '10+',   fee: 'Free', badge: 'Founding', hint: 'Founding Partner — your monthly fee is on us' },
];

/* Iter 216h105 — Commission detail, surfaced front-and-centre on the
   page so engineers see the earnings story before pricing or
   pre-requisites. The first card is a one-off signup reward, the
   second is the per-site monthly recurring split.

   Iter 216h194 — Removed only the £100–£400 premium-plan bonus card.
   Engineers still receive (a) 50% of the gym's first cleared
   Operations payment AND (b) £3/site/mo recurring for as long as the
   gym stays on the platform. Both are released after the referred
   gym has been active on the platform for 3 consecutive months
   (no missed payments, no cancellation). Centralised in a single
   QUALIFYING_PERIOD constant so future edits change one place. */
const QUALIFYING_PERIOD = '3 months';
const COMMISSION_PLANS = [
  {
    kicker: 'SIGNUP REWARD',
    headline: '50%',
    sub: 'of the gym\'s first cleared Operations module payment',
    detail: `Paid as a one-off lump sum once the referred gym has been active on the platform for ${QUALIFYING_PERIOD} (no cancellation, no missed payments). Stacks with the recurring share below.`,
    cta: 'One-off · per gym',
    accent: 'from-violet-500 to-purple-600',
  },
  {
    kicker: 'MONTHLY RECURRING',
    headline: '£3 / site / mo',
    sub: 'for every active gym site you brought on, every month they stay',
    detail: `Starts paying from month 4 once the referred gym has cleared the ${QUALIFYING_PERIOD} qualifying period. Refer 10 active sites → £30/mo · 30 sites → £90/mo · 100 sites → £300/mo. Paid for as long as the gym stays on the platform.`,
    cta: 'Recurring · per gym',
    accent: 'from-blue-500 to-indigo-600',
  },
];

const COMMISSION_STATS = [
  { stat: '50%',        label: `of the first cleared Operations payment per gym (one-off)` },
  { stat: '£3 / mo',    label: 'recurring per active site — from month 4 onward' },
  { stat: 'Monthly',    label: 'payouts · direct to your account' },
  { stat: 'No cap',     label: 'on how many sites you can refer' },
];

const PERKS = [
  { icon: PoundSterling, title: 'Get paid for referrals',
    body: `50% one-off + £3/site/month recurring for every gym you bring on. Released once the referred gym has been on Pulse Fitness for ${QUALIFYING_PERIOD}.` },
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
  { n: 5, title: 'Get paid',       body: `Once each referred gym has been active for ${QUALIFYING_PERIOD}, we release the signup reward (50% of their first cleared Operations payment) and start the £3/site/mo recurring share from month 4 onward. Paid monthly, straight to your account.` },
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
    title: 'Engineer Partner Network — Pulse Fitness AI',
    description: 'Join 100+ independent fitness engineers on the Pulse Fitness Partner Network. £30/mo (drops to free at 10 referrals). Apply in 5 minutes.',
    canonical: 'https://pulsefitness.ai/partners/engineers',
  });
  return (
    <MarketingShell>
      <AudienceSwitch />
      <Hero />
      <Perks />
      <Commission />
      <Pricing />
      <HowItWorks />
      <EngineerApp />
      <FAQ />
      <FinalCta />
    </MarketingShell>
  );
}


/* ── Audience switch (Iter 257b) ─────────────────────────
   The Partners nav tab serves two audiences. This slim strip lets
   service COMPANIES self-select out to the Service Desk funnel before
   they read a page written for individual engineers. */
function AudienceSwitch() {
  return (
    <div className="bg-slate-950 text-white" data-testid="pe-audience-switch">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm">
        <span className="font-semibold text-slate-300">
          <span className="text-emerald-400 font-bold">Independent engineer?</span> You're in the right place — read on.
        </span>
        <Link
          to="/service-provider/signup"
          className="inline-flex items-center gap-1.5 font-bold text-orange-400 hover:text-orange-300 transition-colors"
          data-testid="pe-audience-supplier-link"
        >
          Run a service company? Get your own Service Desk <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}


/* ── Hero ──────────────────────────────────────────────── */
function Hero() {
  // Iter 220o — Instagram-attributed landing. When the visitor arrives
  // via `?utm_source=instagram` (e.g. from one of the launch campaign
  // posts), swap the hero copy so it greets them in context. The
  // attribution itself is captured + persisted by the hook so the
  // apply form receives it regardless of which CTA they tap.
  const { isInstagram, applyHref } = useUtmAttribution();
  const eyebrowText = isInstagram ? 'Saw us on Instagram' : 'Partner Engineer Network';
  const headlineLine1 = isInstagram ? 'You found us.' : 'For independent';
  const headlineLine2 = isInstagram ? 'Now let\'s talk shop.' : 'fitness engineers.';
  const subCopy = isInstagram
    ? <>
        Welcome from Instagram. Everything you saw in the campaign is real —
        £30/mo that drops to <strong className="text-slate-800">free at 10 referrals</strong>,
        50% of each gym's first cleared payment, and £3/site/mo recurring.
        Apply in 5 minutes; we'll come back within 2 working days.
      </>
    : <>
        Run your own business — but plug into the gym-operator network that already trusts Pulse Fitness. Steady jobs, a powerful mobile app, and a fair monthly fee that drops to <strong className="text-slate-800">free</strong> once you refer 10 active gym sites.
      </>;
  return (
    <section className="gx-grid-bg relative overflow-hidden" data-testid="pe-hero" data-attribution-source={isInstagram ? 'instagram' : 'organic'}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800" data-testid="pe-hero-eyebrow">
            <HardHat size={12} /> {eyebrowText}
          </span>
          <h1 className="mt-5 text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tighter font-black leading-[1.04]" data-testid="pe-hero-headline">
            {headlineLine1}<br />
            <span className="gx-gradient-text">{headlineLine2}</span>
          </h1>
          <p className="mt-5 text-base sm:text-lg md:text-xl text-slate-600 leading-relaxed max-w-xl" data-testid="pe-hero-sub">
            {subCopy}
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              to={withCohort(applyHref)}
              className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap"
              data-testid="pe-hero-apply"
            >
              {isInstagram ? 'Claim your Instagram spot' : 'Start application'} <ArrowRight size={15} />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors whitespace-nowrap dark:bg-zinc-900"
              data-testid="pe-hero-howitworks"
            >
              How it works <ChevronRight size={15} />
            </a>
          </div>
          <ul className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
            <li className="inline-flex items-center gap-1.5"><PoundSterling size={13} className="text-emerald-500" />50% of first payment + £3/site/mo recurring (after {QUALIFYING_PERIOD} on platform)</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />£30/mo · drops automatically</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />Cancel anytime</li>
          </ul>
          <TesterSpaces />
        </div>
        {/* Visual: stylised engineer profile card preview */}
        <div className="relative" data-testid="pe-hero-card">
          <div className="rounded-3xl bg-white shadow-xl border border-slate-100 p-6 max-w-sm mx-auto dark:bg-zinc-900 dark:border-zinc-800">
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
            <div className="mt-4 pt-4 border-t border-slate-100 dark:border-zinc-800">
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
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="pe-perks">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-12">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Why partner with Pulse Fitness</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">The independent engineer's unfair advantage.</h2>
          <p className="mt-3 text-base text-slate-600 max-w-2xl mx-auto">
            You stay independent. We bring the gym-operator network, the customer-facing tech and the credit-card-ready customers.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {PERKS.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-3xl border border-slate-100 bg-slate-50/40 p-6 dark:border-zinc-800" data-testid={`pe-perk-${title.toLowerCase().replace(/\W+/g, '-')}`}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                <Icon size={18} className="text-white" />
              </div>
              <h3 className="font-bold tracking-tight text-slate-900 dark:text-zinc-100">{title}</h3>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


/* ── Commission (Iter 216h105) — the headline earning story ──────── */
function Commission() {
  return (
    <section className="relative py-20 md:py-28 overflow-hidden" data-testid="pe-commission">
      <div className="absolute inset-0 -z-10" style={{ background: 'radial-gradient(60% 40% at 20% 0%, rgba(124,58,237,0.08), transparent 60%), radial-gradient(50% 40% at 90% 80%, rgba(16,185,129,0.08), transparent 60%)' }} />
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="grid lg:grid-cols-[1fr_1.6fr] gap-12 items-start">
          {/* Left intro */}
          <div className="lg:sticky lg:top-28">
            <p className="text-xs uppercase tracking-[0.2em] font-bold text-emerald-600">Earnings</p>
            <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">
              Two ways<br /> you get <span className="gx-gradient-text">paid.</span>
            </h2>
            <p className="mt-4 text-base text-slate-600 leading-relaxed">
              Every gym you bring to Pulse Fitness pays you back two ways — a one-off signup reward (50% of their first cleared Operations payment) and a £3/site/mo recurring share that grows as the network grows. Both are released after the referred gym has stayed on the platform for {QUALIFYING_PERIOD} (protects everyone from trial-and-cancel churn). No cap. No exclusivity. No volume targets.
            </p>
            <div className="mt-7 grid grid-cols-2 gap-3" data-testid="pe-commission-stats">
              {COMMISSION_STATS.map((s) => (
                <div key={s.label} className="rounded-2xl border border-slate-100 bg-white p-4 dark:bg-zinc-900 dark:border-zinc-800">
                  <p className="text-2xl font-black tracking-tight text-slate-900 dark:text-zinc-100">{s.stat}</p>
                  <p className="mt-1 text-xs text-slate-500 leading-snug">{s.label}</p>
                </div>
              ))}
            </div>
            <p className="mt-6 text-xs text-slate-500">Paid straight to your bank account. We handle the reconciliation — you just refer.</p>
          </div>

          {/* Right plan cards */}
          <div className="grid gap-4">
            {COMMISSION_PLANS.map((p, i) => (
              <div
                key={p.kicker}
                className="relative rounded-3xl border border-slate-200 bg-white p-6 md:p-7 overflow-hidden hover:border-slate-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800"
                data-testid={`pe-commission-card-${i}`}
              >
                <div className={`absolute -top-12 -right-12 w-48 h-48 rounded-full opacity-25 bg-gradient-to-br ${p.accent}`} />
                <div className="relative">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-400">{p.kicker}</p>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 dark:bg-zinc-800">
                      {p.cta}
                    </span>
                  </div>
                  <p className="mt-4 text-5xl md:text-6xl font-black tracking-tighter text-slate-900 dark:text-zinc-100">{p.headline}</p>
                  <p className="mt-1 text-sm font-semibold text-slate-600">{p.sub}</p>
                  <p className="mt-4 text-sm text-slate-500 leading-relaxed max-w-2xl">{p.detail}</p>
                </div>
              </div>
            ))}

            {/* Worked example */}
            <div className="rounded-3xl bg-slate-900 text-white p-6 md:p-7 mt-2" data-testid="pe-commission-example">
              <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-emerald-300">A worked example · 10 gyms in your area · year-1 earnings</p>
              <div className="mt-4 grid sm:grid-cols-3 gap-4">
                <ExampleStat label={`Signup rewards × 10 (paid after ${QUALIFYING_PERIOD})`} value="~£345" />
                <ExampleStat label="Recurring (10 sites × £3 × 9 mo)" value="£270 / yr-1" />
                <ExampleStat label="Engineer App fee" value="£0 (waived at 10+)" highlight />
              </div>
              <p className="mt-5 text-xs text-slate-300 leading-relaxed">
                Months 1–3 are the qualifying period — commissions accrue but aren\'t released until each gym crosses month 3. Year-2+ recurring runs the full 12 months (£360/yr per 10 sites). Numbers shown ex-VAT — see FAQ for claw-back rules if a gym cancels inside the qualifying window.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ExampleStat({ label, value, highlight }) {
  return (
    <div className={`rounded-2xl border p-4 ${highlight ? 'bg-emerald-500/15 border-emerald-400/30' : 'bg-white/5 border-white/10'}`}>
      <p className={`text-2xl font-black tracking-tight ${highlight ? 'text-emerald-300' : 'text-white'}`}>{value}</p>
      <p className="mt-1 text-[11px] text-slate-300 leading-snug">{label}</p>
    </div>
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
            Bring gyms to Pulse Fitness and we'll discount your monthly engineer fee automatically. No paperwork. Tiers re-evaluate each billing cycle.
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
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" id="how-it-works" data-testid="pe-howitworks">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-12">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">How it works</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Five steps to your first job.</h2>
        </div>
        <ol className="space-y-3">
          {HOW_IT_WORKS.map(({ n, title, body }) => (
            <li key={n} className="flex items-start gap-4 rounded-2xl border border-slate-100 p-5 bg-slate-50/40 dark:border-zinc-800" data-testid={`pe-step-${n}`}>
              <span className="w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center font-black text-lg text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                {n}
              </span>
              <div>
                <h3 className="font-bold text-slate-900 dark:text-zinc-100">{title}</h3>
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
          <LiveEngineerAppPreview />
        </div>
      </div>
    </section>
  );
}


/* ── FAQ ───────────────────────────────────────────────── */
function FAQ() {
  const items = [
    { q: 'How much can I actually earn?',
      a: `Two stacking commissions per gym you bring on: a one-off signup reward (50% of their first cleared Operations payment) and a £3/site/month recurring share for as long as the gym stays active. Both are released after the referred gym has been active on the platform for ${QUALIFYING_PERIOD} — see the next FAQ. There's no cap on the number of gyms you can refer.` },
    { q: `Why the ${QUALIFYING_PERIOD} qualifying period?`,
      a: `It protects everyone — engineers and Pulse Fitness — from trial-and-cancel referrals where a gym signs up, takes a free quarter, and leaves. Commissions accrue from day one but are released once the referred gym has paid for ${QUALIFYING_PERIOD} of active service. If a gym cancels inside the window, no commission is paid (no claw-back from you either). Once they cross month 3, the signup reward releases in the next payout and the £3/site/mo recurring kicks in from month 4.` },
    { q: 'Do I work for Pulse Fitness?',
      a: 'No — you stay completely independent. Gyms invoice their customers directly, and you run your own business. We connect you, equip you with the app, and pay your referral commissions monthly.' },
    { q: 'Who handles invoicing customers?',
      a: 'The gym (our customer) bills the end customer. Your relationship is with the gym — they decide how to pay you per job. We only handle your referral commissions.' },
    { q: 'How and when do commissions get paid?',
      a: `Monthly, straight to your bank account. Once a referred gym crosses the ${QUALIFYING_PERIOD} qualifying period, the signup reward is released in the next payout, and the £3/site/mo recurring share starts from month 4 onward. Recurring shares roll up at the end of each calendar month.` },
    { q: 'What are the £30/mo for?',
      a: 'Access to the Engineer App (mobile PWA), the gym-operator network, customer-facing tracking & service-report tooling, and AI tools like photo triage. The fee drops to £15 once you bring 5 referrals (verified active) and is waived at 10.' },
    { q: 'How fast does the fee tier update?',
      a: `Automatically at each Stripe billing cycle. We re-count your active gym referrals (gyms past the ${QUALIFYING_PERIOD} qualifying mark) at renewal and apply the lower tier.` },
    { q: 'Do I need my own insurance?',
      a: 'Yes — public liability and (where relevant) PAT/electrical insurance are required. We verify cover during the application.' },
    { q: 'Can a gym add me to one specific job without me joining?',
      a: 'Yes. Gyms can issue you a Job Grant that unlocks a single case at a time, free for you. Most engineers convert to a paid Partner Plan once they receive 2–3 grants.' },
    { q: 'What if a referred gym cancels in months 1–3?',
      a: `No commission is paid for that referral — but there's no claw-back from your other earnings, and the gym doesn't count against your fee-tier discount either. The Stripe webhook automatically marks the referral as "lapsed" so you see exactly where it stands in your dashboard.` },
  ];
  return (
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="pe-faq">
      <div className="max-w-4xl mx-auto px-6 lg:px-8">
        <div className="text-center mb-10">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">FAQ</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Common questions.</h2>
        </div>
        <dl className="space-y-3">
          {items.map(({ q, a }, i) => (
            <details key={q} className="group rounded-2xl border border-slate-100 bg-slate-50/40 p-5 dark:border-zinc-800" data-testid={`pe-faq-${i}`}>
              <summary className="font-bold cursor-pointer text-slate-900 list-none flex items-start gap-3 dark:text-zinc-100">
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
  // Iter 220o — carry attribution into the apply form from the bottom
  // CTA too, so attribution doesn't depend on which button the
  // visitor taps.
  const { applyHref, isInstagram } = useUtmAttribution();
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
              5-minute application. Decision within 2 working days. £30/mo · drops automatically as you bring gyms to Pulse Fitness.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <Link
                to={withCohort(applyHref)}
                className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow dark:bg-zinc-900 dark:text-zinc-100"
                data-testid="pe-final-apply"
              >
                {isInstagram ? 'Claim your Instagram spot' : 'Start application'} <ArrowRight size={15} />
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
