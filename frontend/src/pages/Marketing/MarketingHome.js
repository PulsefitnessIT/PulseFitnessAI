/**
 * GymAxis homepage — hero with AXIS orbit, platform overview, module
 * preview grid, social proof, final CTA. Iter 215an.
 *
 * Iter 220bc — 6 modules → 4 (Operations, CRM, Memberships, Marketing).
 * Staffing + Reporting fold into Operations / CRM as sub-features per
 * the user's mind-map sketch. Each module now exposes a `features`
 * array which renders as a constellation on hover (orbit) and as a
 * pill grid (module card).
 */
import { Link } from 'react-router-dom';
import {
  ArrowRight, Wrench, Users, Calendar, Megaphone,
  ClipboardCheck, Sparkles, Zap, CheckCircle2, HardHat, Star,
  Wallet, AlertTriangle, ListChecks, UserCog,
  Building2, GitBranch, LineChart,
  CalendarClock, Receipt, Smartphone, BookOpen,
  Image as ImageIcon, MailPlus, Heart,
  MapPin, Camera, PoundSterling, FileDown,
} from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import AxisOrbit from './AxisOrbit';
import LiveCustomerAppPreview from './LiveCustomerAppPreview';
import { openTrial } from './TrialSignupModal';
import { useSeo } from '@/utils/seo';

// Iter 220bc — Canonical 4-module structure. Each module carries the
// feature constellation surfaced by the hero orbit on hover AND the
// module-grid card body below. Single source of truth so the hover
// hint and the deep-dive card never drift.
export const MODULES = [
  {
    id: 'service',
    icon: Wrench,
    color: '#06B6D4',
    to: '/platform/service',
    name: 'Operations',
    tagline: 'Stop equipment downtime.',
    body: 'Asset register, AI fault triage, supplier auto-routing, capex tracking, and the rota + payroll engine that runs your gym floor.',
    features: [
      { icon: AlertTriangle, label: 'Fault Logging' },
      { icon: ListChecks,    label: 'Check Sheets' },
      { icon: Wallet,        label: 'CAPEX' },
      { icon: UserCog,       label: 'Staffing' },
      { icon: LineChart,     label: 'Reporting' },
    ],
  },
  {
    id: 'crm',
    icon: Users,
    color: '#6366F1',
    to: '/platform/crm',
    name: 'CRM',
    tagline: 'Turn leads into members.',
    body: 'Pipeline view, AI lead scoring + reply assistant, churn early-warning, revenue forecasting and a unified contact timeline.',
    features: [
      { icon: Building2,  label: 'Companies' },
      { icon: GitBranch,  label: 'Pipeline' },
      { icon: LineChart,  label: 'Forecast' },
      { icon: Users,      label: 'Contacts' },
    ],
  },
  {
    id: 'memberships',
    icon: Calendar,
    color: '#8B5CF6',
    to: '/platform/memberships',
    name: 'Memberships',
    tagline: 'Classes, plans, walk-ins.',
    body: 'Six selling models, embeddable booking widgets, branded member app and the timetable + invoicing engine for any studio shape.',
    features: [
      { icon: CalendarClock, label: 'Timetable' },
      { icon: Receipt,       label: 'Invoicing' },
      { icon: Smartphone,    label: 'Custom App' },
      { icon: BookOpen,      label: 'Bookings' },
    ],
  },
  {
    id: 'marketing',
    icon: Megaphone,
    color: '#D946EF',
    to: '/platform/marketing',
    name: 'Marketing',
    tagline: 'Campaigns that convert.',
    body: 'AI-written email + SMS sequences, win-back, referral campaigns, an in-app Poster Maker and a Marketing Director that grades every send.',
    features: [
      { icon: MailPlus,  label: 'Campaigns' },
      { icon: ImageIcon, label: 'Poster Maker' },
      { icon: Heart,     label: 'Member Jam' },
      { icon: Megaphone, label: 'Social' },
    ],
  },
  // Iter 220bd — Engineers as 5th module. Maps to /partners/engineers
  // (the partner-engineer landing page). High-vis amber accent
  // distinguishes "partner network" from the four core SaaS modules.
  {
    id: 'engineers',
    icon: HardHat,
    color: '#F59E0B',
    to: '/partners/engineers',
    name: 'Engineers',
    tagline: 'Your partner network on the ground.',
    body: 'A vetted UK-wide engineer network — Uber-style live tracking, mobile-first job dispatch, AI photo triage, signed service reports and a referral revenue share.',
    features: [
      { icon: MapPin,        label: 'Job Routing' },
      { icon: Smartphone,    label: 'Mobile App' },
      { icon: Camera,        label: 'AI Photo Triage' },
      { icon: PoundSterling, label: 'Earnings' },
    ],
  },
];

export default function MarketingHome() {
  useSeo({
    title: 'GymAxis AI — All-in-one platform for fitness operators',
    description: 'CRM, memberships, marketing and gym operations in one place. £150/mo for one site. 3-day free trial, all modules unlocked, no credit card.',
    canonical: 'https://www.gymaxisai.com/',
  });
  return (
    <MarketingShell>
      <Hero />
      <PlatformOverview />
      <ModuleGrid />
      <CustomerExperience />
      <SocialProof />
      <EngineerBanner />
      <FinalCta />
    </MarketingShell>
  );
}

function Hero() {
  return (
    <section className="gx-grid-bg relative overflow-hidden" data-testid="gx-hero">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800" data-testid="gx-hero-eyebrow">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }} />
            One platform · Five modules
          </span>
          <h1 className="mt-5 text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tighter font-black leading-[1.04]" data-testid="gx-hero-headline">
            Smarter Fitness.<br />
            <span className="gx-gradient-text">Stronger Business.</span>
          </h1>
          <p className="mt-5 text-base sm:text-lg md:text-xl text-slate-600 leading-relaxed max-w-xl" data-testid="gx-hero-sub">
            GymAxis is the all-in-one operations platform for gyms, studios, and fitness businesses — built around the modules you actually run on, not the ones you'll never use.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap" data-testid="gx-hero-trial">
              Start Free Trial <ArrowRight size={15} />
            </button>
            {/* Iter 216h256 — "See it in action" removed: the canned preview
                doesn't reflect the live platform and was misleading prospects. */}
          </div>
          <ul className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />3-day free trial</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />All modules unlocked</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />No credit card</li>
          </ul>
        </div>
        <div className="relative">
          <AxisOrbit />
        </div>
      </div>
    </section>
  );
}

function PlatformOverview() {
  return (
    <section className="py-24 md:py-32 bg-white dark:bg-zinc-900" data-testid="gx-platform-overview">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-5">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Why GymAxis</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">One platform.<br /><span className="gx-gradient-text">Everything connected.</span></h2>
          <p className="mt-5 text-lg text-slate-600 leading-relaxed">Stop stitching together a CRM, a booking app, an asset tracker, an email tool and a rota spreadsheet. GymAxis is one system, five modules, zero handoff bugs.</p>
        </div>
        <div className="lg:col-span-7 grid sm:grid-cols-2 gap-4">
          <OverviewCard icon={<Sparkles size={18} />} title="AI built in everywhere" body="Lead scoring in CRM, churn prediction in Memberships, copywriter in Marketing, fault triage in Operations." />
          <OverviewCard icon={<Zap size={18} />} title="Flows across modules" body="A no-show in Memberships triggers a CRM win-back. A late invoice triggers an Operations freeze. It just works." />
          <OverviewCard icon={<ClipboardCheck size={18} />} title="Risk-aware operations" body="Risk Assessment templates, equipment safety reports, and fault audit trails — built into Operations from day one." />
          <OverviewCard icon={<CheckCircle2 size={18} />} title="Mobile-first" body="PWA-installable member portal, tablet-friendly check-in, drawer-based admin on phones." />
        </div>
      </div>
    </section>
  );
}

function OverviewCard({ icon, title, body }) {
  return (
    <div className="gx-card rounded-3xl border border-slate-100 bg-slate-50/40 p-6 dark:border-zinc-800">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
        {icon}
      </div>
      <h3 className="mt-4 text-lg font-bold tracking-tight">{title}</h3>
      <p className="mt-1 text-sm text-slate-600 leading-relaxed">{body}</p>
    </div>
  );
}

function ModuleGrid() {
  return (
    <section className="py-24 md:py-32 bg-slate-50/60" data-testid="gx-module-grid">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">The five modules</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Built for every part of your business</h2>
        </div>
        <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="gx-module-grid-list">
          {MODULES.map((m) => <ModuleCard key={m.id} m={m} />)}
        </div>
      </div>
    </section>
  );
}

function ModuleCard({ m }) {
  const Icon = m.icon;
  return (
    <Link to={m.to} className="gx-card group block rounded-3xl border border-slate-100 bg-white p-6 md:p-7 dark:bg-zinc-900 dark:border-zinc-800" data-testid={`gx-module-${m.id}`}>
      <div className="w-11 h-11 rounded-2xl flex items-center justify-center" style={{ background: `${m.color}14` }}>
        <Icon size={20} style={{ color: m.color }} />
      </div>
      <h3 className="mt-5 text-xl font-bold tracking-tight">{m.name}</h3>
      <p className="mt-1 text-sm font-semibold" style={{ color: m.color }}>{m.tagline}</p>
      <p className="mt-3 text-sm text-slate-600 leading-relaxed">{m.body}</p>
      {/* Iter 220bc — Feature pills mirror the orbit's on-hover constellation
          so the messaging is consistent between the hero and the deep-dive
          card. */}
      <div className="mt-5 flex flex-wrap gap-1.5" data-testid={`gx-module-${m.id}-features`}>
        {m.features.map((f) => {
          const FIcon = f.icon;
          return (
            <span
              key={f.label}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-bold text-slate-700 dark:border-zinc-800 dark:text-zinc-200"
              style={{ background: `${m.color}0d` }}
            >
              <FIcon size={11} style={{ color: m.color }} />
              {f.label}
            </span>
          );
        })}
      </div>
      <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold" style={{ color: m.color }}>
        Learn more <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function CustomerExperience() {
  return (
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="gx-customer-xp">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">What your customer sees</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">
            Uber-clear service.<br />
            <span className="gx-gradient-text">Branded as yours.</span>
          </h2>
          <p className="mt-5 text-base text-slate-600 leading-relaxed max-w-xl">
            When a fault is logged in your gym, the manager sees a live tracker — engineer photo, rating, ETA, on-site progress, then a branded PDF receipt and a star rating they can leave for the engineer. Same craft Uber and Deliveroo gave their customers, now wired into your equipment.
          </p>
          <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-slate-700">
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>Live map + ETA countdown</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>One-tap call &amp; message the engineer</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>Step-by-step on-site timeline</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>Branded PDF + audit chain</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>5-star rating feeds engineer score</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>No app install — opens in any browser</span></li>
          </ul>
        </div>
        <div className="relative" data-testid="gx-customer-xp-visual">
          <LiveCustomerAppPreview />
        </div>
      </div>
    </section>
  );
}

function SocialProof() {
  return (
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="gx-social-proof">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="text-center">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Built for fitness operators</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">What the platform delivers on day one</h2>
        </div>
        <div className="mt-12 grid grid-cols-2 lg:grid-cols-4 gap-6">
          <Stat value="5 modules" label="Operations · CRM · Memberships · Marketing · Engineers" />
          <Stat value="AI-first" label="Lead scoring, churn prediction, copywriter, fault triage — all built in" />
          <Stat value="Multi-site" label="Head-office onboarding wizard handles unlimited child sites in one pass" />
          <Stat value="GDPR-ready" label="UK GDPR DPA, UK-only data residency, tamper-evident audit log" />
        </div>
        <blockquote className="mt-16 max-w-3xl mx-auto text-center">
          <p className="text-2xl md:text-3xl font-bold tracking-tight text-slate-800 leading-snug">
            "Built by gym operators, for gym operators. Replace four tools with one that thinks like you do."
          </p>
          <footer className="mt-5 text-sm text-slate-500">Founding principle · GymAxis AI</footer>
        </blockquote>
      </div>
    </section>
  );
}

function Stat({ value, label }) {
  return (
    <div className="rounded-3xl border border-slate-100 bg-slate-50/40 p-6 text-center dark:border-zinc-800">
      <div className="text-4xl md:text-5xl font-black tracking-tighter gx-gradient-text">{value}</div>
      <p className="mt-2 text-sm text-slate-600 leading-snug">{label}</p>
    </div>
  );
}

/* ── Engineer Partner banner (Iter 216h88) ─────────────── */
function EngineerBanner() {
  return (
    <section className="py-16 md:py-20 bg-slate-50 dark:bg-zinc-900" data-testid="gx-engineer-banner">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="rounded-[36px] bg-white border border-slate-100 shadow-sm overflow-hidden grid lg:grid-cols-5 dark:bg-zinc-900 dark:border-zinc-800">
          <div className="lg:col-span-3 p-8 md:p-12">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800">
              <HardHat size={12} /> Independent fitness engineer?
            </span>
            <h2 className="mt-4 text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight">
              Run your own business — backed by the GymAxis network.
            </h2>
            <p className="mt-4 text-base text-slate-600 leading-relaxed max-w-xl">
              Join the Partner Engineer Network. Get on every gym's roster, use our offline-first mobile app, and earn a one-off signup reward (50% of the gym's first cleared Operations payment) plus £3/site/mo recurring for as long as the gym stays on the platform. Both released after the gym stays on the platform for 3 months. Monthly fee drops to <strong className="text-slate-800">free</strong> at 10 referrals.
            </p>
            <ul className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs font-semibold text-slate-500">
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />£30 / £15 / free auto-tier</li>
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />Cancel anytime</li>
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />Decision in 2 working days</li>
            </ul>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/partners/engineers" className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap" data-testid="gx-engineer-banner-cta">
                Learn more <ArrowRight size={15} />
              </Link>
              <Link to="/partners/engineers/apply" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors whitespace-nowrap dark:bg-zinc-900" data-testid="gx-engineer-banner-apply">
                Start application <ArrowRight size={15} />
              </Link>
            </div>
          </div>
          <div className="lg:col-span-2 p-8 md:p-10 flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #f1f5f9 0%, #e0e7ff 100%)' }}>
            <div className="rounded-2xl bg-white shadow-lg border border-slate-100 p-5 max-w-xs dark:bg-zinc-900 dark:border-zinc-800">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Your engineer</p>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-700">✓ Verified</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-extrabold text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>S</div>
                <div>
                  <p className="font-bold text-slate-800">Sarah</p>
                  <div className="flex items-center gap-1 text-xs text-slate-500 mt-0.5">
                    <Star size={11} className="text-amber-400" fill="currentColor" />
                    <span className="font-bold text-slate-700">4.9</span>
                    <span>· 52 jobs in 90d</span>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-1 mt-3">
                {['IOSH', 'PAT', 'CSCS'].map((q) => (
                  <span key={q} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-bold border border-emerald-200 bg-emerald-50 text-emerald-700">✓ {q}</span>
                ))}
              </div>
              <p className="mt-3 text-[10px] text-slate-400 leading-relaxed">This is the profile customers see when you accept their job.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="py-24 md:py-32" data-testid="gx-final-cta">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-16 text-center text-white"
          style={{ background: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)' }}
        >
          <div className="absolute inset-0 opacity-30 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.6), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.4), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-4xl md:text-5xl lg:text-6xl font-black tracking-tighter leading-[1.04]">Run your entire fitness business<br />from one platform</h2>
            <p className="mt-5 text-lg text-white/90 max-w-xl mx-auto">3-day free trial — all five modules unlocked. No credit card. We're always reachable, but you don't need to wait for us.</p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow dark:bg-zinc-900 dark:text-zinc-100" data-testid="gx-final-trial">
                Start Free Trial <ArrowRight size={15} />
              </button>
              <a
                href="/downloads/GymAxis-AI-Presentation.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full border border-white/60 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors"
                data-testid="gx-final-deck"
              >
                <FileDown size={15} /> Download Sales Deck
              </a>
              {/* Iter 216h256 — "See it in action" removed; the canned
                  walkthrough is no longer representative of the live build. */}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
