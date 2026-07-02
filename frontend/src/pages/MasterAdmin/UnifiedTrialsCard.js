/**
 * UnifiedTrialsCard — Master Admin Overview (Iter 220ea·45).
 *
 * Single source of truth for trials. Replaces the old TrialFunnelStrip
 * + FreshTrialsTile, which surfaced overlapping trial data side-by-side
 * and made the overview feel like a wall of duplicate widgets.
 *
 * One card now answers: how's the pipeline (active / expiring / converted
 * / rate), which modules are being trialled (Operations / Memberships /
 * CRM / Marketing — trials are cross-platform, not an "Operations" thing),
 * and who just signed up (freshest 24h prospects). A single "Manage all
 * trials" CTA drills into the full Trials section for everything else.
 *
 * Visual system matches the rest of Master Admin: white Panel card, slate
 * palette, brand-blue/violet accents. Fully responsive — the two-column
 * body stacks on mobile.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import {
  Timer, AlertTriangle, CheckCircle2, Target, ArrowRight, RefreshCw,
  Sparkles, ChevronRight, ExternalLink, Wrench, Users, Building2, Megaphone,
} from 'lucide-react';

const MODULE_META = {
  operations:  { label: 'Operations',  icon: Wrench,    color: '#2563EB', bg: 'rgba(25, 205, 255,0.10)' },
  memberships: { label: 'Memberships', icon: Users,     color: '#059669', bg: 'rgba(5,150,105,0.10)' },
  crm:         { label: 'CRM',         icon: Building2,  color: '#9D4CDD', bg: 'rgba(25, 205, 255,0.10)' },
  marketing:   { label: 'Marketing',   icon: Megaphone,  color: '#D97706', bg: 'rgba(217,119,6,0.10)' },
};
const MODULE_ORDER = ['operations', 'memberships', 'crm', 'marketing'];

function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const mins = Math.floor(Math.max(0, Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const Panel = ({ children, className = '', ...rest }) => (
  <div
    className={`bg-white border border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`}
    {...rest}
  >
    {children}
  </div>
);

function StatTile({ icon: Icon, label, value, tone = 'slate', testid }) {
  const tones = {
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    slate: 'bg-slate-50 border-slate-200 text-slate-700',
  };
  return (
    <div className={`border rounded-xl p-3 ${tones[tone]}`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.12em] font-bold opacity-80">{label}</span>
        <Icon size={13} className="opacity-60" />
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

export default function UnifiedTrialsCard({ onGoTrials }) {
  const { API } = useAuth();
  const [summary, setSummary] = useState(null);
  const [recent, setRecent] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const token = localStorage.getItem('token');
    const headers = { Authorization: `Bearer ${token}` };
    try {
      const [s, r] = await Promise.all([
        axios.get(`${API}/master-admin/trials/summary`, { headers }),
        axios.get(`${API}/master-admin/trials/recent?hours=24&limit=5`, { headers }),
      ]);
      setSummary(s.data);
      setRecent(r.data);
    } catch {
      setSummary(null);
      setRecent(null);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => {
    load();
    const id = setInterval(load, 120_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !summary) {
    return (
      <Panel className="p-6 flex items-center justify-center h-48" data-testid="unified-trials-card">
        <RefreshCw className="animate-spin text-slate-300" size={20} />
      </Panel>
    );
  }

  const byStatus = summary?.by_status || {};
  const byModule = summary?.by_module || {};
  const active = byStatus.active || 0;
  const expiringWeek = summary?.expiring_this_week || 0;
  const converted = byStatus.converted || 0;
  const rate = summary?.conversion_rate_30d || 0;
  const ended30d = summary?.ended_30d || 0;
  const avgDays = summary?.avg_days_to_convert || 0;
  const items = recent?.items || [];

  const rateColor = rate >= 60 ? 'text-emerald-600' : rate >= 30 ? 'text-amber-600' : 'text-rose-600';
  const rateBar = rate >= 60 ? 'bg-emerald-500' : rate >= 30 ? 'bg-amber-500' : 'bg-rose-500';
  const moduleMax = Math.max(1, ...MODULE_ORDER.map((k) => byModule[k] || 0));

  return (
    <Panel className="p-5 lg:p-6" data-testid="unified-trials-card">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
            <Timer size={18} className="text-blue-600" />
          </div>
          <div className="min-w-0">
            <h3 className="text-base lg:text-lg font-bold text-slate-900 tracking-tight">Trial Pipeline</h3>
            <p className="text-xs text-slate-500">
              Platform-wide · across all modules · {ended30d} ended in 30d · avg {avgDays > 0 ? `${avgDays}d` : '—'} to convert
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button" onClick={load} disabled={loading}
            className="text-slate-400 hover:text-slate-700 transition p-2"
            aria-label="Refresh trials" data-testid="unified-trials-refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <Button size="sm" variant="outline" onClick={onGoTrials} data-testid="btn-manage-all-trials" className="rounded-full">
            Manage all trials <ArrowRight size={12} className="ml-1" />
          </Button>
        </div>
      </div>

      {/* Headline KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 lg:gap-3">
        <StatTile icon={CheckCircle2} label="Active" value={active} tone="emerald" testid="trials-kpi-active" />
        <StatTile icon={AlertTriangle} label="Expiring ≤7d" value={expiringWeek} tone={expiringWeek > 0 ? 'amber' : 'slate'} testid="trials-kpi-expiring" />
        <StatTile icon={Sparkles} label="Converted 30d" value={converted} tone="blue" testid="trials-kpi-converted" />
        <StatTile icon={Target} label="Conversion" value={`${rate}%`} tone="slate" testid="trials-kpi-rate" />
      </div>

      {/* Conversion progress bar */}
      <div className="mt-3 flex items-center gap-3">
        <span className="text-[11px] text-slate-500 font-medium whitespace-nowrap">30-day conversion</span>
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div className={`h-full ${rateBar} transition-all`} style={{ width: `${Math.min(100, rate)}%` }} />
        </div>
        <span className={`text-xs font-bold tabular-nums ${rateColor}`}>{converted} / {ended30d}</span>
      </div>

      {/* Expiring-this-week warning */}
      {expiringWeek > 0 && (
        <div className="mt-3 bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-2" data-testid="trials-expiring-alert">
          <AlertTriangle size={14} className="text-amber-600 shrink-0" />
          <div className="flex-1 text-sm text-amber-800">
            <strong>{expiringWeek}</strong> trial{expiringWeek === 1 ? '' : 's'} expiring in the next 7 days.
          </div>
          <Button size="sm" variant="outline" onClick={onGoTrials} className="border-amber-300 text-amber-700 hover:bg-amber-100" data-testid="trials-review-expiring">
            Review
          </Button>
        </div>
      )}

      {/* Two-column body: module breakdown + fresh signups */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-5 lg:gap-6">
        {/* Module breakdown */}
        <div data-testid="trials-module-breakdown">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 mb-3">Active trials by module</p>
          <div className="space-y-2.5">
            {MODULE_ORDER.map((key) => {
              const meta = MODULE_META[key];
              const Icon = meta.icon;
              const val = byModule[key] || 0;
              return (
                <div key={key} className="flex items-center gap-3" data-testid={`trials-module-${key}`}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0" style={{ background: meta.bg }}>
                    <Icon size={14} style={{ color: meta.color }} />
                  </div>
                  <span className="text-sm text-slate-700 font-medium w-24 shrink-0">{meta.label}</span>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{ width: `${(val / moduleMax) * 100}%`, background: meta.color }} />
                  </div>
                  <span className="text-sm font-bold tabular-nums text-slate-900 w-6 text-right">{val}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Fresh signups */}
        <div className="lg:border-l lg:border-slate-100 lg:pl-6" data-testid="trials-recent-list">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">Freshest signups · 24h</p>
            <span className="text-xs font-bold text-slate-900 tabular-nums" data-testid="trials-recent-count">{items.length}</span>
          </div>
          {items.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center" data-testid="trials-recent-empty">
              No new trial signups in the last 24 hours.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 -mx-2">
              {items.map((row) => {
                const mods = (row.modules || []).slice(0, 3);
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      onClick={() => onGoTrials?.()}
                      className="w-full text-left px-2 py-2.5 hover:bg-slate-50 transition rounded-lg group"
                      data-testid={`trials-recent-row-${row.id}`}
                      title={`Open in Trials${row.owner_email ? ` — ${row.owner_email}` : ''}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm font-semibold text-slate-900 truncate">{row.name || 'Untitled gym'}</span>
                          <span className="block text-[11px] text-slate-500 truncate">
                            {row.owner_email || 'No owner contact'}{row.employee_count ? ` · ${row.employee_count}` : ''}
                          </span>
                        </span>
                        <span className="text-[10px] text-slate-400 whitespace-nowrap">{timeAgo(row.trial_started_at)}</span>
                        <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-500 transition" />
                      </div>
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        {mods.map((m) => {
                          const meta = MODULE_META[m];
                          if (!meta) return null;
                          return (
                            <span
                              key={m}
                              className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                              style={{ background: meta.bg, color: meta.color }}
                              data-testid={`trials-recent-row-${row.id}-mod-${m}`}
                            >
                              {meta.label}
                            </span>
                          );
                        })}
                        {row.utm_source && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-bold uppercase tracking-wider">
                            {row.utm_source}
                          </span>
                        )}
                        {row.website && (
                          <a
                            href={row.website.startsWith('http') ? row.website : `https://${row.website}`}
                            target="_blank" rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-slate-50 text-slate-600 hover:text-slate-900 text-[10px] font-semibold border border-slate-200"
                          >
                            <ExternalLink size={9} /> Site
                          </a>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Panel>
  );
}
