/**
 * CRM / Marketing — Tasks to Complete
 *
 * Replaces the previous brand-coupled "HubSpot Parity" panel with a
 * vendor-neutral checklist of capabilities the CRM and Marketing modules
 * should ship. Items are hand-curated and grouped so the platform team can
 * see at a glance what's live, what's partially shipped, and what's still
 * on the roadmap.
 *
 * Status values: shipped · partial · planned
 */
import React, { useMemo, useState } from 'react';
import {
  ListChecks, Search, Filter, ChevronRight,
  CheckCircle2, Clock4, CircleDashed, Sparkles,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

const STATUS = {
  shipped: { label: 'Shipped',  tone: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  partial: { label: 'Partial',  tone: 'bg-amber-50 text-amber-700 border-amber-200',       icon: Clock4 },
  planned: { label: 'Planned',  tone: 'bg-zinc-50 text-zinc-600 border-zinc-200',          icon: CircleDashed },
};

const TASKS = [
  // ── CRM ────────────────────────────────────────────────────
  { module: 'CRM', area: 'Pipeline',     title: 'Customisable pipeline stages',       status: 'shipped', priority: 'P0', notes: 'Drag-and-drop + per-org stage colours.' },
  { module: 'CRM', area: 'Pipeline',     title: 'Stage probability & AI win-rate',     status: 'partial', priority: 'P1', notes: 'Probability stored; AI-assisted forecasting still mocked.' },
  { module: 'CRM', area: 'Deals',        title: 'Deal kanban + list view toggle',     status: 'shipped', priority: 'P0' },
  { module: 'CRM', area: 'Deals',        title: 'Recurring revenue / MRR tagging',    status: 'planned', priority: 'P1', notes: 'Schema present, UI not yet shipped.' },
  { module: 'CRM', area: 'Contacts',     title: 'Contact + Company unified record',   status: 'shipped', priority: 'P0' },
  { module: 'CRM', area: 'Contacts',     title: 'Custom properties (per-org)',         status: 'shipped', priority: 'P0' },
  { module: 'CRM', area: 'Inbox',        title: 'Shared team inbox (email + SMS)',     status: 'partial', priority: 'P1', notes: 'Email pipeline live · SMS still mocked (Twilio).' },
  { module: 'CRM', area: 'Activities',   title: 'Calls, meetings & tasks timeline',   status: 'shipped', priority: 'P0' },
  { module: 'CRM', area: 'Quoting',      title: 'Quote builder + e-sign',              status: 'shipped', priority: 'P0' },
  { module: 'CRM', area: 'Reporting',    title: 'Pipeline velocity & loss reasons',    status: 'partial', priority: 'P1' },
  { module: 'CRM', area: 'AI',           title: 'AI deal-coach next-best-action',      status: 'planned', priority: 'P2' },
  { module: 'CRM', area: 'Imports',      title: 'CSV import with column mapping',      status: 'shipped', priority: 'P0' },

  // ── Marketing ───────────────────────────────────────────────
  { module: 'Marketing', area: 'Audiences',  title: 'Dynamic segments + saved lists',  status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Email',      title: 'Drag-and-drop email composer',    status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Email',      title: 'A/B subject-line testing',        status: 'planned', priority: 'P2' },
  { module: 'Marketing', area: 'SMS',        title: 'SMS broadcast + opt-in flow',     status: 'partial', priority: 'P1', notes: 'UI live · sending currently MOCKED, awaiting Twilio.' },
  { module: 'Marketing', area: 'Journeys',   title: 'Multi-step automation canvas',    status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Journeys',   title: 'Send-time optimisation',          status: 'planned', priority: 'P2' },
  { module: 'Marketing', area: 'Forms',      title: 'Embeddable lead-capture forms',   status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Pages',      title: 'Hosted landing pages',            status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Brand kit',  title: 'Per-org brand kit + AI assets',   status: 'shipped', priority: 'P0' },
  { module: 'Marketing', area: 'Performance',title: 'Per-campaign ROI + UTM tracking', status: 'partial', priority: 'P1' },
  { module: 'Marketing', area: 'AI',         title: 'AI Director (campaign autopilot)',status: 'partial', priority: 'P1', notes: 'Drafts live · auto-launch behind feature flag.' },
  { module: 'Marketing', area: 'Win-back',   title: 'Lapsed-member win-back campaigns',status: 'shipped', priority: 'P0' },
];

const TABS = ['All', 'CRM', 'Marketing'];

export default function CrmMarketingTasksPanel() {
  const [tab, setTab] = useState('All');
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return TASKS.filter((t) => {
      if (tab !== 'All' && t.module !== tab) return false;
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (q && !`${t.title} ${t.area} ${t.notes || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [tab, statusFilter, search]);

  const summary = useMemo(() => {
    const base = { shipped: 0, partial: 0, planned: 0, total: 0 };
    TASKS.forEach((t) => {
      if (tab !== 'All' && t.module !== tab) return;
      base[t.status] += 1;
      base.total += 1;
    });
    return base;
  }, [tab]);

  const pct = summary.total ? Math.round((summary.shipped / summary.total) * 100) : 0;

  return (
    <Card className="p-5 rounded-xl border-zinc-200 bg-white" data-testid="crm-marketing-tasks-panel">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)] grid place-items-center">
            <Sparkles size={18} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-zinc-900">CRM / Marketing — tasks to complete</h2>
            <p className="text-xs text-zinc-500">
              {summary.shipped} shipped · {summary.partial} partial · {summary.planned} planned · {pct}% feature-complete
            </p>
          </div>
        </div>
        <div className="hidden sm:block w-40 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Tabs (module) */}
      <div className="subtab-bar mb-4 flex-wrap" data-testid="crm-marketing-module-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`subtab-pill ${tab === t ? 'is-active' : ''}`}
            data-testid={`crm-marketing-tab-${t.toLowerCase()}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks…"
            className="pl-8 h-9 text-sm"
            data-testid="crm-marketing-tasks-search"
          />
        </div>
        <div className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 bg-zinc-50 p-1">
          {[
            { id: 'all',     label: 'All' },
            { id: 'shipped', label: 'Shipped' },
            { id: 'partial', label: 'Partial' },
            { id: 'planned', label: 'Planned' },
          ].map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setStatusFilter(s.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider transition-colors ${
                statusFilter === s.id
                  ? 'bg-white text-zinc-900 shadow-sm border border-zinc-200'
                  : 'text-zinc-500 hover:text-zinc-700'
              }`}
              data-testid={`crm-marketing-status-${s.id}`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="inline-flex items-center gap-1 text-[11px] text-zinc-400">
          <Filter size={11} /> {filtered.length} of {TASKS.length}
        </div>
      </div>

      {/* List */}
      <ul className="space-y-2">
        {filtered.length === 0 && (
          <li className="rounded-lg border border-dashed border-zinc-200 bg-zinc-50/40 p-8 text-center text-sm text-zinc-500" data-testid="crm-marketing-tasks-empty">
            No tasks match the current filters.
          </li>
        )}
        {filtered.map((t, i) => {
          const cfg = STATUS[t.status];
          const Icon = cfg.icon;
          return (
            <li
              key={`${t.module}-${t.title}`}
              className="rounded-lg border border-zinc-200 hover:border-[rgb(var(--rgb-brand-blue)/0.4)] hover:bg-zinc-50/60 transition-colors p-3 flex items-start gap-3"
              data-testid={`crm-marketing-task-${i}`}
            >
              <div className={`shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-md border text-[10px] font-bold uppercase tracking-wider ${cfg.tone}`}>
                <Icon size={11} /> {cfg.label}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">{t.module}</span>
                  <ChevronRight size={11} className="text-zinc-300" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">{t.area}</span>
                  {t.priority && (
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 ml-auto">{t.priority}</span>
                  )}
                </div>
                <p className="text-sm font-medium text-zinc-900 mt-0.5">{t.title}</p>
                {t.notes && <p className="text-[12px] text-zinc-500 mt-0.5 leading-relaxed">{t.notes}</p>}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
