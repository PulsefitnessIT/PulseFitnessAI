/**
 * Pulse Fitness homepage — hero with AXIS orbit, platform overview, module
 * preview grid, social proof, final CTA. Iter 215an.
 *
 * Iter 220bc — 6 modules → 4 (Operations, CRM, Memberships, Marketing).
 * Staffing + Reporting fold into Operations / CRM as sub-features per
 * the user's mind-map sketch. Each module now exposes a `features`
 * array which renders as a constellation on hover (orbit) and as a
 * pill grid (module card).
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight, Wrench, Users, Calendar, Megaphone,
  ClipboardCheck, Sparkles, Zap, CheckCircle2, HardHat, Star,
  Wallet, AlertTriangle, ListChecks, UserCog,
  Building2, GitBranch, LineChart,
  CalendarClock, Receipt, Smartphone, BookOpen,
  Image as ImageIcon, MailPlus, Heart,
  MapPin, PoundSterling, Headset,
} from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import AxisOrbit from './AxisOrbit';
import LiveCustomerAppPreview from './LiveCustomerAppPreview';
import ServiceDeskPromo from './ServiceDeskPromo';
import { openTrial } from './TrialSignupModal';
import { useSeo } from '@/utils/seo';

// Iter 220bc — Canonical 4-module structure. Each module carries the
// feature constellation surfaced by the hero orbit on hover AND the
// module-grid card body below. Single source of truth so the hover
// hint and the deep-dive card never drift.
export const MODULES = (t) => [
  {
    id: 'service',
    icon: Wrench,
    color: '#06B6D4',
    to: '/platform/service',
    name: t('mkt.mod_service', 'Operations'),
    tagline: t('mkt.m_service_tag', 'Stop equipment downtime.'),
    body: t('mkt.m_service_body', 'Asset register, AI fault triage, supplier auto-routing, capex tracking, and the rota + payroll engine that runs your gym floor.'),
    features: [
      { icon: AlertTriangle, label: t('mkt.f_fault', 'Fault Logging') },
      { icon: ListChecks,    label: t('mkt.f_checks', 'Check Sheets') },
      { icon: Wallet,        label: t('mkt.f_capex', 'CAPEX') },
      { icon: UserCog,       label: t('mkt.f_staffing', 'Staffing') },
      { icon: LineChart,     label: t('mkt.f_reporting', 'Reporting') },
    ],
  },
  {
    id: 'crm',
    icon: Users,
    color: '#6366F1',
    to: '/platform/crm',
    name: t('mkt.mod_crm', 'CRM'),
    tagline: t('mkt.m_crm_tag', 'Turn leads into members.'),
    body: t('mkt.m_crm_body', 'Pipeline view, AI lead scoring + reply assistant, churn early-warning, revenue forecasting and a unified contact timeline.'),
    features: [
      { icon: Building2,  label: t('mkt.f_companies', 'Companies') },
      { icon: GitBranch,  label: t('mkt.f_pipeline', 'Pipeline') },
      { icon: LineChart,  label: t('mkt.f_forecast', 'Forecast') },
      { icon: Users,      label: t('mkt.f_contacts', 'Contacts') },
    ],
  },
  {
    id: 'memberships',
    icon: Calendar,
    color: '#8B5CF6',
    to: '/platform/memberships',
    name: t('mkt.mod_memberships', 'Memberships'),
    tagline: t('mkt.m_mem_tag', 'Classes, plans, walk-ins.'),
    body: t('mkt.m_mem_body', 'Six selling models, embeddable booking widgets, branded member app and the timetable + invoicing engine for any studio shape.'),
    features: [
      { icon: CalendarClock, label: t('mkt.f_timetable', 'Timetable') },
      { icon: Receipt,       label: t('mkt.f_invoicing', 'Invoicing') },
      { icon: Smartphone,    label: t('mkt.f_customapp', 'Custom App') },
      { icon: BookOpen,      label: t('mkt.f_bookings', 'Bookings') },
    ],
  },
  {
    id: 'marketing',
    icon: Megaphone,
    color: '#D946EF',
    to: '/platform/marketing',
    name: t('mkt.mod_marketing', 'Marketing'),
    tagline: t('mkt.m_mkt_tag', 'Campaigns that convert.'),
    body: t('mkt.m_mkt_body', 'AI-written email + SMS sequences, win-back, referral campaigns, an in-app Poster Maker and a Marketing Director that grades every send.'),
    features: [
      { icon: MailPlus,  label: t('mkt.f_campaigns', 'Campaigns') },
      { icon: ImageIcon, label: t('mkt.f_poster', 'Poster Maker') },
      { icon: Heart,     label: t('mkt.f_jam', 'Member Jam') },
      { icon: Megaphone, label: t('mkt.f_social', 'Social') },
    ],
  },
  // Iter 220bd — Engineers as 5th module. Maps to /partners/engineers
  // (the partner-engineer landing page). High-vis amber accent
  // distinguishes "partner network" from the four core SaaS modules.
  // Iter 257 — renamed to "Partners": now covers BOTH individual partner
  // engineers and service companies running their own Service Desk.
  {
    id: 'engineers',
    icon: HardHat,
    color: '#F59E0B',
    to: '/partners/engineers',
    name: t('mkt.mod_partners', 'Partners'),
    tagline: t('mkt.m_eng_tag', 'Engineers & service suppliers.'),
    body: t('mkt.m_eng_body', 'A vetted UK-wide engineer network with Uber-style tracking and mobile dispatch — plus a full self-serve Service Desk for service companies: SLA boards, scheduling, invoicing and owner analytics.'),
    features: [
      { icon: MapPin,        label: t('mkt.f_routing', 'Job Routing') },
      { icon: Smartphone,    label: t('mkt.f_mobile', 'Mobile App') },
      { icon: Headset,       label: t('mkt.f_servicedesk', 'Service Desk') },
      { icon: PoundSterling, label: t('mkt.f_earnings', 'Earnings') },
    ],
  },
];

export default function MarketingHome() {
  useSeo({
    title: 'Pulse Fitness AI | Gym Management Software for Gyms, Studios & Engineers',
    description: 'Connected gym management software for gyms, studios, fitness operators and equipment engineers — CRM, memberships, operations, asset management, service desk, staffing, marketing and reporting in one platform. 3-day free trial, all modules unlocked.',
    canonical: 'https://www.pulsefitness.ai/',
  });
  return (
    <MarketingShell>
      <Hero />
      <PlatformOverview />
      <ModuleGrid />
      <CustomerExperience />
      <SocialProof />
      {/* Iter 257 — dark-breakout band for the B2B Service Desk package
          (service companies), placed above the individual-engineer banner
          so the two partner audiences read in sequence without mixing. */}
      <ServiceDeskPromo />
      <EngineerBanner />
      <FinalCta />
    </MarketingShell>
  );
}

function Hero() {
  const { t } = useTranslation();
  return (
    <section className="gx-grid-bg relative overflow-hidden" data-testid="gx-hero">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800" data-testid="gx-hero-eyebrow">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }} />
            {t('mkt.hero_eyebrow', 'One platform · Five modules')}
          </span>
          <h1 className="mt-5 text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tighter font-black leading-[1.04]" data-testid="gx-hero-headline">
            {t('mkt.hero_h1_1', 'Smarter Fitness.')}<br />
            <span className="gx-gradient-text">{t('mkt.hero_h1_2', 'Stronger Business.')}</span>
          </h1>
          <p className="mt-5 text-base sm:text-lg md:text-xl text-slate-600 leading-relaxed max-w-xl" data-testid="gx-hero-sub">
            {t('mkt.hero_sub', "Pulse Fitness is the all-in-one operations platform for gyms, studios, and fitness businesses — built around the modules you actually run on, not the ones you'll never use.")}
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap" data-testid="gx-hero-trial">
              {t('mkt.start_trial', 'Start Free Trial')} <ArrowRight size={15} />
            </button>
            {/* Iter 216h256 — "See it in action" removed: the canned preview
                doesn't reflect the live platform and was misleading prospects. */}
          </div>
          <ul className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.hero_check_1', '3-day free trial')}</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.hero_check_2', 'All modules unlocked')}</li>
            <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.hero_check_3', 'No credit card')}</li>
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
  const { t } = useTranslation();
  return (
    <section className="py-24 md:py-32 bg-white dark:bg-zinc-900" data-testid="gx-platform-overview">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-5">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">{t('mkt.ov_eyebrow', 'Why Pulse Fitness')}</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{t('mkt.ov_title_1', 'One platform.')}<br /><span className="gx-gradient-text">{t('mkt.ov_title_2', 'Everything connected.')}</span></h2>
          <p className="mt-5 text-lg text-slate-600 leading-relaxed">{t('mkt.ov_desc', 'Stop stitching together a CRM, a booking app, an asset tracker, an email tool and a rota spreadsheet. Pulse Fitness is one system, five modules, zero handoff bugs.')}</p>
        </div>
        <div className="lg:col-span-7 grid sm:grid-cols-2 gap-4">
          <OverviewCard icon={<Sparkles size={18} />} title={t('mkt.ov1_t', 'AI built in everywhere')} body={t('mkt.ov1_b', 'Lead scoring in CRM, churn prediction in Memberships, copywriter in Marketing, fault triage in Operations.')} />
          <OverviewCard icon={<Zap size={18} />} title={t('mkt.ov2_t', 'Flows across modules')} body={t('mkt.ov2_b', 'A no-show in Memberships triggers a CRM win-back. A late invoice triggers an Operations freeze. It just works.')} />
          <OverviewCard icon={<ClipboardCheck size={18} />} title={t('mkt.ov3_t', 'Risk-aware operations')} body={t('mkt.ov3_b', 'Risk Assessment templates, equipment safety reports, and fault audit trails — built into Operations from day one.')} />
          <OverviewCard icon={<CheckCircle2 size={18} />} title={t('mkt.ov4_t', 'Mobile-first')} body={t('mkt.ov4_b', 'PWA-installable member portal, tablet-friendly check-in, drawer-based admin on phones.')} />
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
  const { t } = useTranslation();
  return (
    <section className="py-24 md:py-32 bg-slate-50/60" data-testid="gx-module-grid">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">{t('mkt.mg_eyebrow', 'The five modules')}</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{t('mkt.mg_title', 'Built for every part of your business')}</h2>
        </div>
        <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="gx-module-grid-list">
          {MODULES(t).map((m) => <ModuleCard key={m.id} m={m} />)}
        </div>
      </div>
    </section>
  );
}

function ModuleCard({ m }) {
  const { t } = useTranslation();
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
        {t('mkt.mg_learn_more', 'Learn more')} <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function CustomerExperience() {
  const { t } = useTranslation();
  return (
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="gx-customer-xp">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">{t('mkt.cx_eyebrow', 'What your customer sees')}</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">
            {t('mkt.cx_title_1', 'Uber-clear service.')}<br />
            <span className="gx-gradient-text">{t('mkt.cx_title_2', 'Branded as yours.')}</span>
          </h2>
          <p className="mt-5 text-base text-slate-600 leading-relaxed max-w-xl">
            {t('mkt.cx_desc', 'When a fault is logged in your gym, the manager sees a live tracker — engineer photo, rating, ETA, on-site progress, then a branded PDF receipt and a star rating they can leave for the engineer. Same craft Uber and Deliveroo gave their customers, now wired into your equipment.')}
          </p>
          <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-slate-700">
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_1', 'Live map + ETA countdown')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_2', 'One-tap call & message the engineer')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_3', 'Step-by-step on-site timeline')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_4', 'Branded PDF + audit chain')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_5', '5-star rating feeds engineer score')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-emerald-500 mt-0.5 flex-shrink-0" /><span>{t('mkt.cx_6', 'No app install — opens in any browser')}</span></li>
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
  const { t } = useTranslation();
  return (
    <section className="py-20 md:py-28 bg-white dark:bg-zinc-900" data-testid="gx-social-proof">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="text-center">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">{t('mkt.sp_eyebrow', 'Built for fitness operators')}</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{t('mkt.sp_title', 'What the platform delivers on day one')}</h2>
        </div>
        <div className="mt-12 grid grid-cols-2 lg:grid-cols-4 gap-6">
          <Stat value={t('mkt.sp1_v', '5 modules')} label={t('mkt.sp1_l', 'Operations · CRM · Memberships · Marketing · Partners')} />
          <Stat value={t('mkt.sp2_v', 'AI-first')} label={t('mkt.sp2_l', 'Lead scoring, churn prediction, copywriter, fault triage — all built in')} />
          <Stat value={t('mkt.sp3_v', 'Multi-site')} label={t('mkt.sp3_l', 'Head-office onboarding wizard handles unlimited child sites in one pass')} />
          <Stat value={t('mkt.sp4_v', 'GDPR-ready')} label={t('mkt.sp4_l', 'UK GDPR DPA, UK-only data residency, tamper-evident audit log')} />
        </div>
        <blockquote className="mt-16 max-w-3xl mx-auto text-center">
          <p className="text-2xl md:text-3xl font-bold tracking-tight text-slate-800 leading-snug">
            {t('mkt.sp_quote', '"Built by gym operators, for gym operators. Replace four tools with one that thinks like you do."')}
          </p>
          <footer className="mt-5 text-sm text-slate-500">{t('mkt.sp_quote_by', 'Founding principle · Pulse Fitness AI')}</footer>
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
  const { t } = useTranslation();
  return (
    <section className="py-16 md:py-20 bg-slate-50 dark:bg-zinc-900" data-testid="gx-engineer-banner">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="rounded-[36px] bg-white border border-slate-100 shadow-sm overflow-hidden grid lg:grid-cols-5 dark:bg-zinc-900 dark:border-zinc-800">
          <div className="lg:col-span-3 p-8 md:p-12">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:border-zinc-800">
              <HardHat size={12} /> {t('mkt.eb_badge', 'Independent fitness engineer?')}
            </span>
            <h2 className="mt-4 text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight">
              {t('mkt.eb_title', 'Run your own business — backed by the Pulse Fitness network.')}
            </h2>
            <p className="mt-4 text-base text-slate-600 leading-relaxed max-w-xl">
              {t('mkt.eb_desc', "Join the Partner Engineer Network. Get on every gym's roster, use our offline-first mobile app, and earn a one-off signup reward (50% of the gym's first cleared Operations payment) plus £3/site/mo recurring for as long as the gym stays on the platform. Both released after the gym stays on the platform for 3 months. Monthly fee drops to")} <strong className="text-slate-800">{t('mkt.eb_desc_free', 'free')}</strong> {t('mkt.eb_desc_end', 'at 10 referrals.')}
            </p>
            <ul className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs font-semibold text-slate-500">
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.eb_check_1', '£30 / £15 / free auto-tier')}</li>
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.eb_check_2', 'Cancel anytime')}</li>
              <li className="inline-flex items-center gap-1.5"><CheckCircle2 size={13} className="text-emerald-500" />{t('mkt.eb_check_3', 'Decision in 2 working days')}</li>
            </ul>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/partners/engineers" className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold whitespace-nowrap" data-testid="gx-engineer-banner-cta">
                {t('mkt.eb_learn', 'Learn more')} <ArrowRight size={15} />
              </Link>
              <Link to="/partners/engineers/apply" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors whitespace-nowrap dark:bg-zinc-900" data-testid="gx-engineer-banner-apply">
                {t('mkt.eb_apply', 'Start application')} <ArrowRight size={15} />
              </Link>
            </div>
          </div>
          <div className="lg:col-span-2 p-8 md:p-10 flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #f1f5f9 0%, #e0e7ff 100%)' }}>
            <div className="rounded-2xl bg-white shadow-lg border border-slate-100 p-5 max-w-xs dark:bg-zinc-900 dark:border-zinc-800">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{t('mkt.eb_your_engineer', 'Your engineer')}</p>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-700">{t('mkt.eb_verified', '✓ Verified')}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-extrabold text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>S</div>
                <div>
                  <p className="font-bold text-slate-800">Sarah</p>
                  <div className="flex items-center gap-1 text-xs text-slate-500 mt-0.5">
                    <Star size={11} className="text-amber-400" fill="currentColor" />
                    <span className="font-bold text-slate-700">4.9</span>
                    <span>{t('mkt.eb_jobs', '· 52 jobs in 90d')}</span>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-1 mt-3">
                {['IOSH', 'PAT', 'CSCS'].map((q) => (
                  <span key={q} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-bold border border-emerald-200 bg-emerald-50 text-emerald-700">✓ {q}</span>
                ))}
              </div>
              <p className="mt-3 text-[10px] text-slate-400 leading-relaxed">{t('mkt.eb_profile_note', 'This is the profile customers see when you accept their job.')}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  const { t } = useTranslation();
  return (
    <section className="py-24 md:py-32" data-testid="gx-final-cta">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-16 text-center text-white"
          style={{ background: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)' }}
        >
          <div className="absolute inset-0 opacity-30 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.6), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.4), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-4xl md:text-5xl lg:text-6xl font-black tracking-tighter leading-[1.04]">{t('mkt.fc_title_1', 'Run your entire fitness business')}<br />{t('mkt.fc_title_2', 'from one platform')}</h2>
            <p className="mt-5 text-lg text-white/90 max-w-xl mx-auto">{t('mkt.fc_sub', "3-day free trial — all five modules unlocked. No credit card. We're always reachable, but you don't need to wait for us.")}</p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow dark:bg-zinc-900 dark:text-zinc-100" data-testid="gx-final-trial">
                {t('mkt.start_trial', 'Start Free Trial')} <ArrowRight size={15} />
              </button>
              {/* Iter 216h256 — "See it in action" removed; the canned
                  walkthrough is no longer representative of the live build. */}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
