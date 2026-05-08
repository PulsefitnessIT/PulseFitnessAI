/**
 * Memberships Start tab — guided entry into the Memberships module.
 * Same architecture as Marketing/StartTab.js: overview, outcomes, quick
 * starts, step-by-step preview, templates, fast-path jumps. No new
 * backend work — every CTA links to an existing tab / action.
 */
import React from 'react';
import {
  Zap, UserPlus, CalendarPlus, Ticket, ArrowRight, Users2, Clock,
  Sparkles, TrendingUp, Heart, FileSpreadsheet, CheckCircle2, EyeOff,
} from 'lucide-react';
import { useUserPref } from '@/utils/userPrefs';

const OUTCOMES = [
  { icon: UserPlus,    title: 'Onboard new members',        note: 'Bulk import from CSV in under a minute' },
  { icon: CalendarPlus, title: 'Fill your timetable',        note: 'Publish classes members can book themselves' },
  { icon: Ticket,      title: 'Sell plans and passes',      note: 'Stripe-powered recurring + pay-as-you-go' },
  { icon: Heart,       title: 'Retain & engage',            note: 'Automated win-back, birthday and check-in flows' },
];

const STEPS = [
  { n: 1, title: 'Import members',     note: 'CSV template or add one-by-one' },
  { n: 2, title: 'Set up your plans',  note: 'Membership tiers + class packs' },
  { n: 3, title: 'Build the timetable', note: 'Classes, instructors, capacity' },
  { n: 4, title: 'Invite members',     note: 'Email / SMS welcome flow' },
  { n: 5, title: 'Track & iterate',    note: 'Live insights in Analytics' },
];

const OutcomeCard = ({ icon: Icon, title, note }) => (
  <div className="rounded-2xl p-4 border transition-colors" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`mbr-outcome-${title.toLowerCase().replace(/\s+/g, '-')}`}>
    <div className="w-9 h-9 rounded-full flex items-center justify-center mb-3" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}><Icon size={16} /></div>
    <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{title}</div>
    <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{note}</div>
  </div>
);

export default function MembershipsStartTab({ setTab, onBulkImport }) {
  // eslint-disable-next-line no-unused-vars
  const [, setHideStart] = useUserPref('hideStartTabs', false);
  const quickStart = [
    { id: 'qs-import',   title: 'Bulk import members',          desc: 'Drop in a CSV — done in 60s', icon: FileSpreadsheet, cta: () => { setTab('members'); onBulkImport?.(); } },
    { id: 'qs-timetable', title: 'Add your first class',         desc: 'Open the timetable and publish', icon: CalendarPlus,    cta: () => setTab('timetable') },
    { id: 'qs-plan',      title: 'Create a membership plan',     desc: 'Tier + price + Stripe-ready',    icon: Ticket,          cta: () => setTab('plans') },
  ];
  const jumps = [
    { label: 'Members',      tab: 'members',     icon: Users2,       desc: 'Directory + profiles' },
    { label: 'Timetable',    tab: 'timetable',   icon: Clock,        desc: 'Classes and schedules' },
    { label: 'Analytics',    tab: 'analytics',   icon: TrendingUp,   desc: 'Performance intelligence' },
  ];

  return (
    <div className="space-y-8 pulse-font-body" data-testid="mbr-start-tab">
      <div>
        <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>
          Your Memberships Hub
        </h2>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
          Manage members, classes, plans, and the app your members book through — all in one place.
        </p>
        <button
          type="button"
          onClick={() => { setHideStart(true); setTab('dashboard'); }}
          className="mt-2 inline-flex items-center gap-1 text-xs opacity-70 hover:opacity-100"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid="mbr-hide-start-btn"
        >
          <EyeOff size={11} /> Hide this tab
        </button>
      </div>

      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>What you can achieve</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {OUTCOMES.map((o) => <OutcomeCard key={o.title} {...o} />)}
        </div>
      </section>

      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Quick start</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {quickStart.map((q) => {
            const Icon = q.icon;
            return (
              <button key={q.id} type="button" onClick={q.cta}
                className="group rounded-2xl p-5 text-left border transition-all hover:-translate-y-0.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
                data-testid={q.id}>
                <div className="flex items-start justify-between mb-6">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Icon size={18} /></div>
                  <ArrowRight size={16} className="opacity-40 group-hover:opacity-100 group-hover:text-[var(--color-brand-cyan)] transition-all" />
                </div>
                <div className="text-base font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{q.title}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{q.desc}</div>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Launch in 5 steps</div>
        <ol className="grid grid-cols-1 md:grid-cols-5 gap-2 rounded-2xl p-3 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          {STEPS.map((s, i) => (
            <li key={s.n} className="flex items-start gap-3 p-2">
              <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold pulse-font-heading" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}>{s.n}</div>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{s.title}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.note}</div>
              </div>
              {i < STEPS.length - 1 && <div className="hidden md:block flex-1 h-px self-center" style={{ background: 'var(--theme-border)' }} />}
            </li>
          ))}
        </ol>
      </section>

      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Or jump straight in</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {jumps.map((j) => {
            const Icon = j.icon;
            return (
              <button key={j.tab} type="button" onClick={() => setTab(j.tab)}
                className="group rounded-xl p-4 border text-left transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] flex items-center gap-3"
                style={{ background: 'transparent', borderColor: 'var(--theme-border)' }}
                data-testid={`mbr-jump-${j.tab}`}>
                <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--theme-surface)', color: 'var(--color-brand-cyan)' }}><Icon size={14} /></div>
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
    </div>
  );
}
