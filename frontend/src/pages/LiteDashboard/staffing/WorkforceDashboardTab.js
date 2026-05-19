/**
 * Phase S1 — Workforce Dashboard tab.
 *
 * Pre-aggregated control centre for the Staffing console. Hits ONE
 * endpoint (`GET /api/staffing/workforce-dashboard`) and renders:
 *
 *   • 6 headline KPIs (active staff, on-now, late, absent, open today, coverage%)
 *   • Week totals — hours, labour cost, overtime, avg £/hour
 *   • 7×24 coverage heatmap (Mon→Sun × hour-of-day)
 *   • Live on-shift roster + upcoming today
 *   • Open shifts backlog (next 14 days)
 *   • Compliance hot-spots (top 10 conflicts for this week)
 *
 * Mobile-friendly: KPI grid collapses to 3 cols, heatmap scrolls
 * horizontally, on-now roster stacks. Auto-refreshes every 60s to
 * keep the live counters honest without hammering the backend.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Users, Loader2, Circle, Clock, AlertTriangle, PoundSterling,
  TrendingUp, RefreshCw, ShieldCheck, Zap,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => i);

function Kpi({ icon: Icon, label, value, accent, hint, testId }) {
  return (
    <div
      className="rounded-xl border p-4 flex items-start gap-3"
      style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
      data-testid={testId}
    >
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
        style={{ background: accent + '22', color: accent }}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--theme-text-muted)' }}>{label}</p>
        <p className="text-2xl font-bold tabular-nums pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{value}</p>
        {hint && <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{hint}</p>}
      </div>
    </div>
  );
}

function HeatmapCell({ value, peak }) {
  // 0.0 → 1.0 intensity based on peak. Uses brand cyan tint.
  const intensity = peak > 0 ? Math.min(1, value / peak) : 0;
  if (value === 0) {
    return <div className="w-6 h-6 rounded-sm" style={{ background: 'var(--theme-border)', opacity: 0.3 }} />;
  }
  return (
    <div
      className="w-6 h-6 rounded-sm text-[9px] font-bold flex items-center justify-center tabular-nums"
      title={`${value.toFixed(1)} staff-hours`}
      style={{
        background: `rgba(25, 205, 255, ${0.15 + intensity * 0.7})`,
        color: intensity > 0.6 ? '#001219' : 'var(--theme-text)',
      }}
    >
      {value >= 1 ? Math.round(value) : ''}
    </div>
  );
}

function formatGBP(n) { return `£${(Number(n) || 0).toFixed(2)}`; }

export default function WorkforceDashboardTab({ headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    else setRefreshing(true);
    try {
      const { data: d } = await axios.get(`${API}/staffing/workforce-dashboard`, { headers });
      setData(d);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load dashboard');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [headers]);

  useEffect(() => {
    load();
    // Auto-refresh every 60s while tab is visible.
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') load(true);
    }, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const peak = data?.heatmap?.peak || 0;

  if (loading && !data) {
    return (
      <div className="py-12 flex items-center justify-center gap-2 text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="workforce-dashboard-loading">
        <Loader2 size={14} className="animate-spin" /> Loading workforce dashboard…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-sm inline-flex items-center gap-2 text-rose-500" data-testid="workforce-dashboard-error">
        <AlertTriangle size={14} /> {error}
      </div>
    );
  }

  const k = data.kpis || {};
  const w = data.week || {};

  return (
    <div className="space-y-6" data-testid="workforce-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Workforce Control Centre</p>
          <h3 className="text-lg font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
            Week of {data.week_start}
          </h3>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            Last refresh {new Date(data.as_of).toLocaleTimeString()}
          </p>
        </div>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-full border px-3 h-8 text-xs font-bold disabled:opacity-60"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
          data-testid="workforce-dashboard-refresh"
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Kpi icon={Users}        label="Active staff"  value={k.active_staff ?? 0}   accent="#19CDFF"  testId="kpi-active-staff" />
        <Kpi icon={Circle}       label="On shift now"  value={k.on_now ?? 0}         accent="#10B981"  testId="kpi-on-now" hint="Scheduled, live" />
        <Kpi icon={Clock}        label="Running late"  value={k.late ?? 0}           accent="#F59E0B"  testId="kpi-late" />
        <Kpi icon={AlertTriangle} label="Absent"       value={k.absent ?? 0}         accent="#EF4444"  testId="kpi-absent" />
        <Kpi icon={Zap}          label="Open today"    value={k.open_today ?? 0}     accent="#8B5CF6"  testId="kpi-open-today" hint="Need fill" />
        <Kpi icon={ShieldCheck}  label="Coverage"      value={`${k.coverage_pct ?? 0}%`} accent="#0EA5E9" testId="kpi-coverage" />
      </div>

      {/* Week money row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi icon={Clock}         label="Scheduled hours"   value={`${w.hours ?? 0}h`}              accent="#19CDFF" testId="week-hours" />
        <Kpi icon={PoundSterling} label="Labour cost"       value={formatGBP(w.labour_cost)}        accent="#10B981" testId="week-cost" />
        <Kpi icon={TrendingUp}    label="Overtime"          value={`${w.overtime_hours ?? 0}h`}     accent="#F59E0B" testId="week-overtime" />
        <Kpi icon={PoundSterling} label="Avg / hour"        value={formatGBP(w.avg_hourly)}         accent="#0EA5E9" testId="week-avg" />
      </div>

      {/* Heatmap */}
      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Coverage heatmap</p>
            <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>7-day × hour-of-day</p>
          </div>
          <div className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
            <span>low</span>
            <div className="flex gap-0.5">
              {[0.15, 0.3, 0.45, 0.6, 0.85].map((op) => (
                <div key={op} className="w-4 h-2 rounded-sm" style={{ background: `rgba(25,205,255,${op})` }} />
              ))}
            </div>
            <span>peak {peak.toFixed(1)}h</span>
          </div>
        </div>
        <div className="overflow-x-auto" data-testid="workforce-heatmap">
          <table className="text-[10px]">
            <thead>
              <tr>
                <th className="w-12"></th>
                {HOUR_LABELS.map((h) => (
                  <th key={h} className="w-6 font-bold text-center" style={{ color: 'var(--theme-text-muted)' }}>
                    {h % 3 === 0 ? h : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAY_LABELS.map((label, row) => (
                <tr key={label}>
                  <td className="pr-2 py-0.5 font-bold text-right" style={{ color: 'var(--theme-text-muted)' }}>{label}</td>
                  {HOUR_LABELS.map((h) => (
                    <td key={h} className="px-0.5 py-0.5">
                      <HeatmapCell value={data.heatmap?.grid?.[row]?.[h] || 0} peak={peak} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Two-column live panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* On now / upcoming */}
        <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Live roster</p>
          {(data.on_now || []).length === 0 && (data.upcoming || []).length === 0 && (
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Nothing scheduled right now.</p>
          )}
          {(data.on_now || []).length > 0 && (
            <>
              <p className="text-[11px] font-bold mt-2 mb-1" style={{ color: 'var(--theme-text)' }}>On shift now ({data.on_now.length})</p>
              <ul className="space-y-1">
                {data.on_now.map((sh) => (
                  <li key={sh.id} className="flex items-center justify-between text-xs gap-2" data-testid={`on-now-${sh.id}`}>
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                      <span className="font-bold truncate" style={{ color: 'var(--theme-text)' }}>{sh.staff_name}</span>
                      <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{sh.primary_role}</span>
                    </span>
                    <span className="tabular-nums text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{sh.start_time}–{sh.end_time}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {(data.upcoming || []).length > 0 && (
            <>
              <p className="text-[11px] font-bold mt-3 mb-1" style={{ color: 'var(--theme-text)' }}>Starting today ({data.upcoming.length})</p>
              <ul className="space-y-1">
                {data.upcoming.map((sh) => (
                  <li key={sh.id} className="flex items-center justify-between text-xs gap-2">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-sky-500 shrink-0" />
                      <span className="truncate" style={{ color: 'var(--theme-text)' }}>{sh.staff_name}</span>
                    </span>
                    <span className="tabular-nums text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{sh.start_time}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {/* Open shifts + compliance */}
        <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Attention</p>
          {(data.open_shifts || []).length === 0 && (data.compliance?.top || []).length === 0 && (
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No open shifts or compliance warnings.</p>
          )}
          {(data.open_shifts || []).length > 0 && (
            <>
              <p className="text-[11px] font-bold mt-2 mb-1 inline-flex items-center gap-1" style={{ color: 'var(--theme-text)' }}>
                <Zap size={11} className="text-violet-500" /> Open shifts (next 14 days · {data.open_shifts.length})
              </p>
              <ul className="space-y-1" data-testid="open-shifts-list">
                {data.open_shifts.slice(0, 6).map((sh) => (
                  <li key={sh.id} className="flex items-center justify-between text-xs gap-2">
                    <span className="truncate" style={{ color: 'var(--theme-text)' }}>
                      {sh.date} · {sh.role}
                    </span>
                    <span className="tabular-nums text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{sh.start_time}–{sh.end_time}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {(data.compliance?.top || []).length > 0 && (
            <>
              <p className="text-[11px] font-bold mt-3 mb-1 inline-flex items-center gap-1" style={{ color: 'var(--theme-text)' }}>
                <AlertTriangle size={11} className="text-amber-500" /> Compliance ({data.compliance.count})
              </p>
              <ul className="space-y-1" data-testid="compliance-list">
                {data.compliance.top.slice(0, 5).map((c, i) => (
                  <li key={`${c.shift_id}-${i}`} className="text-xs flex items-start gap-2">
                    <span
                      className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${c.severity === 'error' ? 'bg-rose-500' : 'bg-amber-500'}`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="font-bold" style={{ color: 'var(--theme-text)' }}>{c.staff_name || '—'}</span>
                      {c.date && <span className="ml-1 text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>· {c.date}</span>}
                      <span className="block text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{c.reason}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
