/**
 * ServiceDeskPromo — Iter 257.
 *
 * Homepage dark-breakout band for the B2B Service Desk package (sold to
 * fitness equipment service companies — a different audience to the gym
 * operators the rest of the page speaks to, hence the deliberate
 * high-contrast slate-950 break in the page flow).
 *
 * The "screenshot" is a hand-built JSX/Tailwind product mockup (same
 * approach as LiveCustomerAppPreview) — crisper than a PNG, always
 * theme-consistent, and it never goes stale-blurry on retina screens.
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight, CheckCircle2, LayoutDashboard, ClipboardList, Calendar,
  Users, Receipt, HardHat, BarChart3, UploadCloud, PhoneCall, Headset,
} from 'lucide-react';

/* ── CSS product mockup: the Service Desk case board ───────────── */
function DeskMockup() {
  const { t } = useTranslation();
  const navItems = [
    { icon: LayoutDashboard, label: t('mkt.sd_mock_dashboard', 'Dashboard') },
    { icon: ClipboardList, label: t('mkt.sd_mock_cases', 'Cases'), active: true },
    { icon: Calendar, label: t('mkt.sd_mock_scheduler', 'Scheduler') },
    { icon: Users, label: t('mkt.sd_mock_customers', 'Customers') },
    { icon: Receipt, label: t('mkt.sd_mock_billing', 'Billing') },
    { icon: HardHat, label: t('mkt.sd_mock_engineers', 'Engineers') },
  ];
  const cases = [
    { ref: 'SVC-00412', title: t('mkt.sd_mock_c1', 'Treadmill belt slipping'), who: 'Apex Leisure', sla: t('mkt.sd_mock_sla1', '14m to respond'), slaTone: 'bg-red-50 text-red-600', status: 'new', statusTone: 'bg-sky-50 text-sky-700' },
    { ref: 'SVC-00411', title: t('mkt.sd_mock_c2', 'Cross-trainer console dead'), who: 'Hilltop Gym', sla: t('mkt.sd_mock_sla2', '3h 20m'), slaTone: 'bg-amber-50 text-amber-600', status: 'assigned', statusTone: 'bg-indigo-50 text-indigo-700', eng: 'SK' },
    { ref: 'SVC-00409', title: t('mkt.sd_mock_c3', 'PPM — quarterly service'), who: 'Riverside Fitness', sla: t('mkt.sd_mock_sla3', 'SLA met'), slaTone: 'bg-emerald-50 text-emerald-600', status: 'on site', statusTone: 'bg-emerald-50 text-emerald-700', eng: 'JD' },
  ];
  return (
    <div className="relative" data-testid="gx-sd-mockup">
      <div className="rounded-2xl bg-white shadow-2xl ring-1 ring-white/10 overflow-hidden text-left">
        {/* window chrome */}
        <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-slate-100 bg-slate-50/80">
          <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
          <span className="ml-3 text-[10px] font-semibold text-slate-400 truncate">fitfix.gymaxisai.com/service-desk</span>
        </div>
        <div className="grid grid-cols-[88px_1fr] sm:grid-cols-[120px_1fr]">
          {/* sidebar */}
          <div className="border-r border-slate-100 py-3 px-2 bg-white">
            <div className="flex items-center gap-1.5 px-2 mb-3">
              <span className="w-4 h-4 rounded bg-orange-500" />
              <span className="text-[9px] font-black tracking-tight text-slate-800 hidden sm:block">FITFIX LTD</span>
            </div>
            {navItems.map(({ icon: Icon, label, active }) => (
              <div key={label} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md mb-0.5 ${active ? 'bg-orange-50 text-orange-600' : 'text-slate-400'}`}>
                <Icon size={11} />
                <span className="text-[9px] font-semibold hidden sm:block">{label}</span>
              </div>
            ))}
            <div className="px-2 pt-2 mt-1 border-t border-slate-100">
              <div className="flex items-center gap-1.5 py-1 text-slate-400"><BarChart3 size={11} /><span className="text-[9px] font-semibold hidden sm:block">{t('mkt.sd_mock_analytics', 'Analytics')}</span></div>
              <div className="flex items-center gap-1.5 py-1 text-slate-400"><UploadCloud size={11} /><span className="text-[9px] font-semibold hidden sm:block">{t('mkt.sd_mock_import', 'Import data')}</span></div>
            </div>
          </div>
          {/* case board */}
          <div className="p-3 sm:p-4 bg-slate-50/50">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-bold text-slate-800">{t('mkt.sd_mock_board', 'Live cases')}</span>
              <span className="inline-flex items-center gap-1 rounded-md bg-orange-500 text-white text-[9px] font-bold px-2 py-1"><PhoneCall size={9} /> {t('mkt.sd_mock_new_case', 'New case')}</span>
            </div>
            <div className="space-y-2">
              {cases.map((c) => (
                <div key={c.ref} className="rounded-lg bg-white border border-slate-100 px-2.5 py-2 flex items-center gap-2 shadow-sm">
                  <span className="font-mono text-[8px] text-slate-400 shrink-0">{c.ref}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] font-bold text-slate-800 truncate">{c.title}</p>
                    <p className="text-[8px] text-slate-400 truncate">{c.who}</p>
                  </div>
                  <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap ${c.slaTone}`}>{c.sla}</span>
                  <span className={`hidden sm:inline text-[8px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap ${c.statusTone}`}>{c.status}</span>
                  {c.eng && <span className="w-4.5 h-4.5 w-[18px] h-[18px] rounded-full bg-slate-800 text-white text-[7px] font-bold flex items-center justify-center shrink-0">{c.eng}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* floating dispatch toast */}
      <div className="absolute -bottom-5 -left-3 sm:-left-6 rounded-xl bg-white shadow-xl border border-slate-100 px-3.5 py-2.5 flex items-center gap-2.5" data-testid="gx-sd-mockup-dispatch">
        <span className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center"><HardHat size={13} /></span>
        <div>
          <p className="text-[10px] font-extrabold text-slate-800">{t('mkt.sd_mock_dispatched', 'Engineer dispatched')}</p>
          <p className="text-[9px] text-slate-400">SVC-00412 → Sam K. · ETA 38 min</p>
        </div>
      </div>
      {/* floating SLA chip */}
      <div className="absolute -top-4 -right-2 sm:-right-5 rounded-xl bg-white shadow-xl border border-slate-100 px-3.5 py-2.5" data-testid="gx-sd-mockup-sla">
        <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">{t('mkt.sd_mock_sla_label', 'SLA met · 30 days')}</p>
        <p className="text-lg font-black tracking-tight text-emerald-600 leading-none mt-0.5">94%</p>
      </div>
    </div>
  );
}

export default function ServiceDeskPromo() {
  const { t } = useTranslation();
  return (
    <section className="relative overflow-hidden bg-slate-950 text-white py-24 md:py-32" data-testid="gx-service-desk-promo">
      {/* subtle radial glow — keeps the dark band premium, not flat */}
      <div aria-hidden className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(800px 400px at 80% 10%, rgba(249,115,22,.12), transparent 60%), radial-gradient(600px 400px at 10% 90%, rgba(249,115,22,.06), transparent 60%)' }} />
      <div className="relative max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-orange-400" data-testid="gx-sd-eyebrow">
            <Headset size={12} /> {t('mkt.sd_eyebrow', 'For service companies')}
          </span>
          <h2 className="mt-5 text-4xl sm:text-5xl font-medium tracking-tighter leading-[1.05]">
            <span className="text-slate-200">{t('mkt.sd_title_1', 'Service equipment for a living?')}</span><br />
            <span className="font-black text-orange-500">{t('mkt.sd_title_2', 'Run your whole desk on GymAxis.')}</span>
          </h2>
          <p className="mt-5 text-base sm:text-lg text-slate-300 leading-relaxed max-w-xl">
            {t('mkt.sd_desc', 'The same Service Desk that powers national fitness suppliers — now self-serve. Phone rings, case raised, engineer dispatched in seconds. SLA countdowns, a drag-and-drop scheduler, your engineers on a mobile app, and owner analytics that prove the numbers.')}
          </p>
          <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2.5 text-sm text-slate-200">
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b1', 'Self-serve signup — desk live in minutes')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b2', '4-step setup: branding, SLAs, engineers, data')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b3', 'Migrate your book — CSV/Excel import with AI mapping')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b4', 'SLA compliance, utilisation & revenue-per-job analytics')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b5', 'Engineer mobile app with offline-first job packs')}</span></li>
            <li className="flex items-start gap-2"><CheckCircle2 size={15} className="text-orange-400 mt-0.5 flex-shrink-0" /><span>{t('mkt.sd_b6', 'Quotes, invoicing & customer-facing tracking links')}</span></li>
          </ul>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              to="/service-provider/signup"
              className="inline-flex items-center gap-1.5 rounded-full bg-orange-500 hover:bg-orange-400 transition-colors px-6 py-3 text-sm font-bold text-white whitespace-nowrap"
              data-testid="gx-sd-signup-cta"
            >
              {t('mkt.sd_cta', 'Start your 14-day free trial')} <ArrowRight size={15} />
            </Link>
            <Link
              to="/partners/engineers"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-300 hover:text-white transition-colors whitespace-nowrap"
              data-testid="gx-sd-engineers-link"
            >
              {t('mkt.sd_solo', 'Solo engineer? Join the network instead')} <ArrowRight size={13} />
            </Link>
          </div>
          <p className="mt-5 text-xs font-semibold text-slate-500">
            {t('mkt.sd_footnote', 'No credit card · Bring unlimited engineers · Cancel anytime')}
          </p>
        </div>
        <div className="relative lg:pl-4">
          <DeskMockup />
        </div>
      </div>
    </section>
  );
}
