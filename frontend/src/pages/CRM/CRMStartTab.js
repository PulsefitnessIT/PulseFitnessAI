/**
 * CRM Start tab — guided entry into the CRM module.
 * Same architecture as Marketing/StartTab.js and Memberships equivalent:
 * overview, outcomes, quick starts, 5-step preview, fast-path jumps.
 */
import React from 'react';
import {
  UserPlus, Building2, TrendingUp, HeartHandshake, FileText, ArrowRight,
  CheckSquare, Activity, Plus, EyeOff,
} from 'lucide-react';
import { useUserPref } from '@/utils/userPrefs';
import RepTrackRecord from './RepTrackRecord';

const OUTCOMES = [
  { icon: UserPlus,       title: 'Track every lead',           note: 'Contacts + inbox of every touchpoint' },
  { icon: Building2,      title: 'Manage accounts',            note: 'Corporate gyms, councils, chains' },
  { icon: TrendingUp,     title: 'Close more deals',           note: 'Pipeline with stages + weighted forecast' },
  { icon: HeartHandshake, title: 'Keep customers happy',       note: 'Tasks, follow-ups, and renewals on autopilot' },
];

const STEPS = [
  { n: 1, title: 'Add your first contact', note: 'Or bulk import from CSV' },
  { n: 2, title: 'Link to a company',      note: 'Accounts with multi-contact view' },
  { n: 3, title: 'Start a deal',           note: 'Move it through stages' },
  { n: 4, title: 'Log the activity',       note: 'Calls, emails, meetings' },
  { n: 5, title: 'Automate follow-up',     note: 'Workflows do the chasing' },
];

const OutcomeCard = ({ icon: Icon, title, note }) => (
  <div className="rounded-2xl p-4 border transition-colors" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`crm-outcome-${title.toLowerCase().replace(/\s+/g, '-')}`}>
    <div className="w-9 h-9 rounded-full flex items-center justify-center mb-3" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}><Icon size={16} /></div>
    <div className="text-sm font-semibold mb-1 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{title}</div>
    <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{note}</div>
  </div>
);

export default function CRMStartTab({ setActiveTab }) {
  // eslint-disable-next-line no-unused-vars
  const [, setHideStart] = useUserPref('hideStartTabs', false);
  const quickStart = [
    { id: 'qs-new-contact',  title: 'Add a new contact',        desc: 'Name, email, and you\'re in',           icon: UserPlus,      cta: () => setActiveTab('contacts') },
    { id: 'qs-new-deal',     title: 'Start your first deal',    desc: 'Drop it on the pipeline board',         icon: TrendingUp,    cta: () => setActiveTab('pipeline') },
    { id: 'qs-new-workflow', title: 'Automate a follow-up',     desc: 'Template-based in 2 minutes',           icon: Activity,      cta: () => setActiveTab('workflows') },
  ];
  const jumps = [
    { label: 'Contacts',    id: 'contacts', icon: UserPlus,    desc: 'People in your world' },
    { label: 'Pipeline',    id: 'pipeline', icon: TrendingUp,  desc: 'Deals moving through stages' },
    { label: 'Activity',    id: 'inbox',    icon: CheckSquare, desc: 'Calls, tasks, notes' },
    { label: 'Documents',   id: 'documents',icon: FileText,    desc: 'Contracts and signed PDFs' },
  ];

  return (
    <div className="space-y-8 pulse-font-body" data-testid="crm-start-tab">
      <div>
        <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>
          Your CRM Command Center
        </h2>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
          Every lead, company, deal and task in one place. Close more, chase less.
        </p>
        <button
          type="button"
          onClick={() => { setHideStart(true); setActiveTab('dashboard'); }}
          className="mt-2 inline-flex items-center gap-1 text-xs opacity-70 hover:opacity-100"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid="crm-hide-start-btn"
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
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>From zero to close in 5 steps</div>
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
        <div className="mt-3">
          <button type="button" onClick={() => setActiveTab('contacts')} className="btn-primary" data-testid="crm-start-add-first-contact">
            <Plus size={14} /> Add my first contact
          </button>
        </div>
      </section>

      <section>
        <div className="text-[11px] font-bold uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Or jump straight in</div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {jumps.map((j) => {
            const Icon = j.icon;
            return (
              <button key={j.id} type="button" onClick={() => setActiveTab(j.id)}
                className="group rounded-xl p-4 border text-left transition-colors hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] flex items-center gap-3"
                style={{ background: 'transparent', borderColor: 'var(--theme-border)' }}
                data-testid={`crm-jump-${j.id}`}>
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

      {/* Iter 215dh — per-rep "Your forecast track record" widget. Renders
          empty-state until a manager freezes a snapshot. */}
      <section data-testid="crm-start-track-record">
        <RepTrackRecord periods={4} />
      </section>
    </div>
  );
}
