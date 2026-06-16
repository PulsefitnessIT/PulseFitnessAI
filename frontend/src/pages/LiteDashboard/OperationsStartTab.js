/**
 * Operations Start tab — guided entry into the Operations (Pulse) module.
 * Same architecture as Memberships/Marketing/CRM Start tabs: overview,
 * outcomes, quick starts, step-by-step preview, fast-path jumps.
 *
 * Requested by the user (msg 741) to welcome gym staff on first login —
 * every CTA is a pure navigation into an existing tab.
 */
import {
  AlertTriangle, ClipboardCheck, Dumbbell, ArrowRight, Truck,
  LayoutDashboard, BarChart3, EyeOff, ShieldCheck, Zap, Wrench, ClipboardList,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUserPref } from '@/utils/userPrefs';
import ActivationMilestonesCard from '../../components/shared/ActivationMilestonesCard';

// Iter 238 — `k` is both the stable testid slug AND the i18n key suffix
// (ops_start.<k>_title / ops_start.<k>_note); title/note are EN fallbacks.
const OUTCOMES = [
  { k: 'log-faults-in-seconds', icon: AlertTriangle,  title: 'Log faults in seconds',  note: 'Photo + severity + auto-routed to the right supplier' },
  { k: 'stay-on-top-of-checks', icon: ClipboardCheck, title: 'Stay on top of checks',  note: 'Daily / weekly check-sheets with digital sign-off' },
  { k: 'track-every-machine',   icon: Dumbbell,       title: 'Track every machine',    note: 'Coverage, status, faults and CAPEX in one view' },
  { k: 'prove-compliance',      icon: ShieldCheck,    title: 'Prove compliance',       note: 'Audit-ready reports for insurers & franchise HQ' },
];

const STEPS = [
  { n: 1, title: 'Add your equipment',  note: 'CSV import or manual — serials, suppliers, warranty' },
  { n: 2, title: 'Invite your team',    note: 'Owners, Managers, Staff, Gym Floor — each with the right access' },
  { n: 3, title: 'Log your first fault', note: 'Photo + severity + one tap routes to the supplier' },
  { n: 4, title: 'Schedule check-sheets', note: 'Daily opens, weekly deep cleans, monthly safety' },
  { n: 5, title: 'Monitor & decide',    note: 'Reports, CAPEX priority, nudges in the Dashboard' },
];

const OutcomeCard = ({ k, icon: Icon, title, note }) => (
  <div
    className="rounded-2xl p-4 border transition-colors"
    style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
    data-testid={`ops-outcome-${k}`}
  >
    <div className="w-9 h-9 rounded-full flex items-center justify-center mb-3" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>
      <Icon size={16} />
    </div>
    <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{title}</div>
    <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{note}</div>
  </div>
);

export default function OperationsStartTab({ setTab, onLogFault, onOpenEquipmentImport }) {
   
  const { t } = useTranslation();
  const [, setHideStart] = useUserPref('hideStartTabs', false);

  const quickStart = [
    {
      id: 'ops-qs-fault',
      title: t('ops_start.qs_fault', 'Log a fault'),
      desc: t('ops_start.qs_fault_desc', 'Photo + severity in 10 seconds'),
      icon: AlertTriangle,
      cta: () => { setTab('faults'); onLogFault?.(); },
    },
    {
      id: 'ops-qs-equipment',
      title: t('ops_start.qs_equipment', 'Add your equipment'),
      desc: t('ops_start.qs_equipment_desc', 'Import from CSV or add manually'),
      icon: Dumbbell,
      cta: () => { setTab('equipment'); onOpenEquipmentImport?.(); },
    },
    {
      id: 'ops-qs-checks',
      title: t('ops_start.qs_checks', 'Run a check-sheet'),
      desc: t('ops_start.qs_checks_desc', 'Daily opens / weekly safety'),
      icon: ClipboardCheck,
      cta: () => setTab('check-sheets'),
    },
  ];

  const jumps = [
    { label: t('dashboard.overview', 'Dashboard'),          tab: 'overview',     icon: LayoutDashboard, desc: t('ops_start.j_overview', 'Today at a glance') },
    { label: t('dashboard.equipment', 'Equipment'),         tab: 'equipment',    icon: Dumbbell,        desc: t('ops_start.j_equipment', 'All machines + coverage') },
    { label: t('dashboard.faults', 'Faults'),               tab: 'faults',       icon: AlertTriangle,   desc: t('ops_start.j_faults', 'Open, in-progress, resolved') },
    { label: t('dashboard.check_sheets', 'Check Sheets'),   tab: 'check-sheets', icon: ClipboardList,   desc: t('ops_start.j_checks', 'Recurring safety checks') },
    { label: t('dashboard.suppliers_tab', 'Suppliers'),     tab: 'suppliers',    icon: Truck,           desc: t('ops_start.j_suppliers', 'Contacts + response times') },
    { label: t('dashboard.reports', 'Reports'),             tab: 'reports',      icon: BarChart3,       desc: t('ops_start.j_reports', 'Weekly digest + exports') },
  ];

  return (
    <div className="space-y-8 pulse-font-body" data-testid="ops-start-tab">
      {/* Iter 216c — "Your first wins" moved here from Dashboard so the
          Start tab is the single onboarding surface. The card auto-hides
          the entire Start tab once every milestone fires (handled inside
          ActivationMilestonesCard via the `hideStartTabs` user pref). */}
      <ActivationMilestonesCard />

      {/* Welcome */}
      <div>
        <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>
          {t('ops_start.title', 'Your Operations Hub')}
        </h2>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
          {t('ops_start.subtitle', 'Equipment, faults, check-sheets, and compliance — one place for the whole floor team.')}
        </p>
        <button
          type="button"
          onClick={() => { setHideStart(true); setTab('overview'); }}
          className="mt-2 inline-flex items-center gap-1 text-xs opacity-70 hover:opacity-100"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid="ops-hide-start-btn"
        >
          <EyeOff size={11} /> {t('ops_start.hide_tab', 'Hide this tab')}
        </button>
      </div>

      {/* Outcomes */}
      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('ops_start.sec_outcomes', 'What you can achieve')}</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {OUTCOMES.map((o) => <OutcomeCard key={o.k} {...o} title={t(`ops_start.${o.k}_title`, o.title)} note={t(`ops_start.${o.k}_note`, o.note)} />)}
        </div>
      </section>

      {/* Quick start */}
      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('ops_start.sec_quick', 'Quick start')}</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {quickStart.map((q) => {
            const Icon = q.icon;
            return (
              <button
                key={q.id}
                type="button"
                onClick={q.cta}
                className="group rounded-2xl p-5 text-left border transition-all hover:-translate-y-0.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                data-testid={q.id}
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
                    <Icon size={18} />
                  </div>
                  <ArrowRight size={16} className="opacity-40 group-hover:opacity-100 group-hover:text-[var(--color-brand-cyan)] transition-all" />
                </div>
                <div className="text-base font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{q.title}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{q.desc}</div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 5-step preview */}
      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('ops_start.sec_steps', 'Launch in 5 steps')}</div>
        <ol
          className="grid grid-cols-1 md:grid-cols-5 gap-2 rounded-2xl p-3 border"
          style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
        >
          {STEPS.map((s, i) => (
            <li key={s.n} className="flex items-start gap-3 p-2">
              <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold pulse-font-heading" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>
                {s.n}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t(`ops_start.step${s.n}_title`, s.title)}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t(`ops_start.step${s.n}_note`, s.note)}</div>
              </div>
              {i < STEPS.length - 1 && <div className="hidden md:block flex-1 h-px self-center" style={{ background: 'var(--theme-border)' }} />}
            </li>
          ))}
        </ol>
      </section>

      {/* Fast-path jumps */}
      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('ops_start.sec_jump', 'Or jump straight in')}</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {jumps.map((j) => {
            const Icon = j.icon;
            return (
              <button
                key={j.tab}
                type="button"
                onClick={() => setTab(j.tab)}
                className="group rounded-xl p-4 border text-left transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] flex items-center gap-3"
                style={{ background: 'transparent', borderColor: 'var(--theme-border)' }}
                data-testid={`ops-jump-${j.tab}`}
              >
                <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--theme-surface)', color: 'var(--color-brand-cyan)' }}>
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{j.label}</div>
                  <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{j.desc}</div>
                </div>
                <ArrowRight size={14} className="opacity-40 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--color-brand-cyan)' }} />
              </button>
            );
          })}
        </div>
      </section>

      {/* Reassurance footer */}
      <div
        className="rounded-xl p-4 border flex items-start gap-3"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
        data-testid="ops-reassurance"
      >
        <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>
          <Zap size={15} />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
            {t('ops_start.reassure_title', 'Pulse Fitness does the boring bits')}
          </div>
          <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            {t('ops_start.reassure_note', 'Auto-route faults to suppliers, auto-generate weekly reports, auto-flag at-risk machines — so your team focuses on members, not spreadsheets.')}
          </div>
        </div>
        <Wrench size={14} className="opacity-40" style={{ color: 'var(--theme-text-muted)' }} />
      </div>
    </div>
  );
}
