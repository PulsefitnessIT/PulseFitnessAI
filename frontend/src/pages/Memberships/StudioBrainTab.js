/**
 * StudioBrainTab — Phase E (Iter 216ad)
 *
 * AI-powered boardroom view:
 *   • Headline card — the one thing the operator should act on
 *   • Growth / revenue / bookings KPIs
 *   • Retention-risk leaderboard (per-student)
 *   • Occupancy heat-map (7 days × 6 time-buckets)
 *   • AI timetable suggestions
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Loader2, Sparkles, TrendingUp, TrendingDown, AlertTriangle,
  Users, CalendarRange, Wand2, RefreshCw, Brain, Zap,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const RISK_TONES = {
  high:   { bg: 'rgba(239,68,68,0.14)',  fg: '#b91c1c', label: 'High' },
  medium: { bg: 'rgba(245,158,11,0.14)', fg: '#b45309', label: 'Medium' },
  low:    { bg: 'rgba(16,185,129,0.14)', fg: '#047857', label: 'Low' },
};
const fmtGBP = (p) => `£${(((p ?? 0) / 100) || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

export default function StudioBrainTab({ API, headers }) {
  const auth = useMemo(() => ({ headers }), [headers]);
  const [data, setData] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [retention, setRetention] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [board, hm, sg, rk] = await Promise.all([
        axios.get(`${API}/memberships/studio/boardroom`, auth),
        axios.get(`${API}/memberships/studio/occupancy-heatmap?weeks=4`, auth),
        axios.get(`${API}/memberships/studio/timetable-suggestions`, auth),
        axios.get(`${API}/memberships/studio/retention-risk?weeks=8&limit=25`, auth),
      ]);
      setData(board.data);
      setHeatmap(hm.data);
      setSuggestions(sg.data);
      setRetention(rk.data);
    } catch (e) {
      notify.error('Failed to load studio brain', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth]);
  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="studio-brain-loading">
        <Loader2 size={14} className="animate-spin" /> Scoring your studio…
      </div>
    );
  }
  if (!data) return null;

  const k = data.kpis || {};
  const risk = retention?.summary || data.retention_summary || {};
  const rows = retention?.rows || [];
  const sugg = suggestions?.suggestions || [];

  return (
    <div className="space-y-5" data-testid="studio-brain-tab">
      {/* Headline */}
      <section
        className="rounded-2xl border p-4 flex items-start gap-3 flex-wrap"
        style={{
          borderColor: 'var(--theme-border, #e2e8f0)',
          background: 'linear-gradient(135deg, rgba(25, 205, 255,0.10), rgba(59,130,246,0.06))',
        }}
        data-testid="studio-brain-headline"
      >
        <div className="rounded-full p-2" style={{ background: 'rgba(25, 205, 255,0.2)' }}>
          <Brain size={18} className="text-violet-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">
            Headline · what to do this week
          </p>
          <h2 className="text-base font-bold leading-snug mt-0.5" data-testid="studio-brain-headline-text">
            {data.headline}
          </h2>
        </div>
        <button type="button" onClick={load} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-brain-refresh">
          <RefreshCw size={11} /> Refresh
        </button>
      </section>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="studio-brain-kpis">
        <Kpi label="Members" value={k.members_total} icon={Users} />
        <Kpi
          label="New (30d)"
          value={k.members_new_30d}
          hint={k.growth_pct !== null && k.growth_pct !== undefined
            ? `${k.growth_pct >= 0 ? '+' : ''}${k.growth_pct}% vs prev 30d`
            : null}
          trend={k.growth_pct}
          icon={TrendingUp}
        />
        <Kpi label="Revenue (30d)" value={fmtGBP(k.revenue_30d_pence)} icon={Sparkles} />
        <Kpi label="Bookings (30d)" value={k.bookings_30d} icon={CalendarRange} />
      </div>

      {/* At-risk + Heatmap — two columns */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <RetentionCard summary={risk} rows={rows} testid="retention" />
        <HeatmapCard heatmap={heatmap} testid="heatmap" />
      </div>

      {/* AI suggestions */}
      <SuggestionsCard suggestions={sugg} model={suggestions?.model} />
    </div>
  );
}

function Kpi({ label, value, hint, icon: Icon, trend }) {
  const trendIcon = trend && trend > 0 ? TrendingUp : (trend !== null && trend !== undefined && trend < 0 ? TrendingDown : null);
  return (
    <div className="rounded-2xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid={`studio-brain-kpi-${label.toLowerCase().replace(/\s+/g, '-').replace(/[()]/g, '')}`}>
      <div className="flex items-center gap-2 opacity-70">
        {Icon ? <Icon size={12} /> : null}
        <span className="text-[10px] uppercase tracking-wider font-bold">{label}</span>
      </div>
      <p className="text-xl font-extrabold tabular-nums mt-1">{value ?? '—'}</p>
      {hint ? (
        <p className="text-[11px] opacity-70 mt-0.5 inline-flex items-center gap-1">
          {trendIcon && React.createElement(trendIcon, { size: 10, style: { color: trend > 0 ? '#10b981' : '#ef4444' } })}
          <span>{hint}</span>
        </p>
      ) : null}
    </div>
  );
}

function RetentionCard({ summary, rows, testid }) {
  return (
    <section className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid={`studio-brain-${testid}`}>
      <header className="flex items-start justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <AlertTriangle size={11} /> Retention risk
          </p>
          <h3 className="text-base font-bold">Students trending towards churn</h3>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          <BandPill tone={RISK_TONES.high}   value={summary.high ?? 0}   label="high" />
          <BandPill tone={RISK_TONES.medium} value={summary.medium ?? 0} label="medium" />
          <BandPill tone={RISK_TONES.low}    value={summary.low ?? 0}    label="low" />
        </div>
      </header>
      {rows.length === 0 ? (
        <div className="text-center py-6 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`studio-brain-${testid}-empty`}>
          <Zap size={22} className="mx-auto mb-1 text-emerald-500" />
          <p className="text-sm font-bold">All clear</p>
          <p className="text-xs opacity-70 mt-1">No students show a concerning attendance pattern. We'll surface any drops as they appear.</p>
        </div>
      ) : (
        <ul className="space-y-1.5" data-testid={`studio-brain-${testid}-list`}>
          {rows.map((r, idx) => {
            const tone = RISK_TONES[r.band] || RISK_TONES.low;
            return (
              <li key={`${r.member_id}-${r.sub_profile_id}-${idx}`} className="flex items-start gap-2 p-2 rounded border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`studio-brain-${testid}-row-${idx}`}>
                <span style={{ width: 4, alignSelf: 'stretch', background: tone.fg, borderRadius: 2, flexShrink: 0 }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold truncate">{r.attendee_name}</span>
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold tabular-nums" style={{ background: tone.bg, color: tone.fg }}>
                      {r.score}/100 · {tone.label}
                    </span>
                    {r.days_since_last_attended !== null ? (
                      <span className="text-[10px] opacity-60 ml-auto tabular-nums">{r.days_since_last_attended}d ago</span>
                    ) : null}
                  </div>
                  <ul className="list-disc list-inside space-y-0 text-[11px] opacity-80 mt-0.5">
                    {(r.reasons || []).map((reason, i) => <li key={i}>{reason}</li>)}
                  </ul>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function BandPill({ tone, value, label }) {
  return (
    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold" style={{ background: tone.bg, color: tone.fg }}>
      {value} {label}
    </span>
  );
}

function HeatmapCard({ heatmap, testid }) {
  if (!heatmap) return null;
  const { days = [], buckets = [], cells = [] } = heatmap;
  const byDayBucket = {};
  cells.forEach((c) => { byDayBucket[`${c.day}/${c.bucket}`] = c; });

  // Colour by utilisation %.
  const colourFor = (pct, occurrences) => {
    if (!occurrences) return 'rgba(148,163,184,0.08)';
    if (pct >= 90) return '#dc2626';
    if (pct >= 75) return '#ea580c';
    if (pct >= 50) return '#f59e0b';
    if (pct >= 25) return '#84cc16';
    return '#3b82f6';
  };

  return (
    <section className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid={`studio-brain-${testid}`}>
      <header className="mb-3">
        <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
          <CalendarRange size={11} /> Occupancy heatmap · last 4 weeks
        </p>
        <h3 className="text-base font-bold">Where your studio is full (and empty)</h3>
      </header>
      <div className="overflow-x-auto" data-testid={`studio-brain-${testid}-grid`}>
        <table className="w-full text-[11px]" style={{ tableLayout: 'fixed' }}>
          <thead>
            <tr>
              <th className="text-left p-1"></th>
              {days.map((d) => <th key={d} className="text-center p-1 font-bold opacity-70">{d}</th>)}
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b}>
                <td className="p-1 opacity-70 tabular-nums">{b}</td>
                {days.map((d) => {
                  const c = byDayBucket[`${d}/${b}`] || { utilisation_pct: 0, occurrences: 0, booked: 0, capacity_total: 0 };
                  const bg = colourFor(c.utilisation_pct, c.occurrences);
                  return (
                    <td key={`${d}-${b}`} className="p-0.5">
                      <div
                        className="rounded text-center tabular-nums font-bold"
                        style={{
                          background: bg,
                          color: c.utilisation_pct >= 50 && c.occurrences ? '#fff' : 'inherit',
                          padding: '6px 2px',
                          minHeight: 26,
                          opacity: c.occurrences ? 1 : 0.5,
                        }}
                        title={`${d} ${b} — ${c.booked}/${c.capacity_total} (${c.utilisation_pct}%) across ${c.occurrences} classes`}
                        data-testid={`studio-brain-${testid}-cell-${d}-${b}`}
                      >
                        {c.occurrences ? `${c.utilisation_pct}%` : ''}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-2 mt-3 text-[10px] opacity-70 flex-wrap" data-testid={`studio-brain-${testid}-legend`}>
        <LegendSwatch c="#3b82f6" label="<25%" />
        <LegendSwatch c="#84cc16" label="25–49%" />
        <LegendSwatch c="#f59e0b" label="50–74%" />
        <LegendSwatch c="#ea580c" label="75–89%" />
        <LegendSwatch c="#dc2626" label="≥ 90%" />
      </div>
      {heatmap.hottest && heatmap.coldest ? (
        <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
          <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`studio-brain-${testid}-hottest`}>
            <p className="opacity-60 uppercase tracking-wider text-[10px] font-bold">Hottest slot</p>
            <p className="font-bold">{heatmap.hottest.day} {heatmap.hottest.bucket}</p>
            <p className="opacity-70">{heatmap.hottest.booked}/{heatmap.hottest.capacity_total} · {heatmap.hottest.utilisation_pct}%</p>
          </div>
          <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`studio-brain-${testid}-coldest`}>
            <p className="opacity-60 uppercase tracking-wider text-[10px] font-bold">Coldest slot</p>
            <p className="font-bold">{heatmap.coldest.day} {heatmap.coldest.bucket}</p>
            <p className="opacity-70">{heatmap.coldest.booked}/{heatmap.coldest.capacity_total} · {heatmap.coldest.utilisation_pct}%</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function LegendSwatch({ c, label }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span style={{ width: 10, height: 10, borderRadius: 2, background: c, display: 'inline-block' }} />
      {label}
    </span>
  );
}

function SuggestionsCard({ suggestions, model }) {
  const hot = suggestions.filter((s) => s.kind === 'open_extra_slot');
  const cold = suggestions.filter((s) => s.kind === 'consolidate_or_drop');
  const other = suggestions.filter((s) => !['open_extra_slot', 'consolidate_or_drop'].includes(s.kind));
  return (
    <section className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid="studio-brain-suggestions">
      <header className="flex items-start justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <Wand2 size={11} className="text-violet-500" /> AI timetable optimisation
          </p>
          <h3 className="text-base font-bold">What to change about your schedule</h3>
        </div>
        <span className="text-[10px] opacity-60 px-2 py-0.5 rounded-full border" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-brain-suggestions-model">
          {model || 'heuristic_only'}
        </span>
      </header>
      {suggestions.length === 0 ? (
        <div className="text-center py-6 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="studio-brain-suggestions-empty">
          <Sparkles size={22} className="mx-auto mb-1 text-violet-500" />
          <p className="text-sm font-bold">Not enough signal yet</p>
          <p className="text-xs opacity-70 mt-1">We need at least a few weeks of booking history to suggest meaningful timetable changes.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <SuggestionGroup title="Open another slot" tone="#10b981" items={hot} icon={TrendingUp} testid="hot" />
          <SuggestionGroup title="Consolidate or drop" tone="#f97316" items={cold} icon={TrendingDown} testid="cold" />
          {other.length ? (
            <SuggestionGroup title="Other opportunities" tone="#8b5cf6" items={other} icon={Sparkles} testid="other" />
          ) : null}
        </div>
      )}
    </section>
  );
}

function SuggestionGroup({ title, tone, items, icon: Icon, testid }) {
  if (!items.length) {
    return (
      <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)', opacity: 0.7 }} data-testid={`studio-brain-suggestions-${testid}-empty`}>
        <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
          <Icon size={11} style={{ color: tone }} /> {title}
        </p>
        <p className="text-xs opacity-60 italic mt-1">No candidates in this band.</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`studio-brain-suggestions-${testid}`}>
      <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
        <Icon size={11} style={{ color: tone }} /> {title}
      </p>
      <ul className="space-y-2 mt-2">
        {items.map((s, i) => (
          <li key={i} className="text-xs" data-testid={`studio-brain-suggestions-${testid}-${i}`}>
            <p className="font-bold">
              {s.day} {s.bucket}
              {s.confidence ? <span className="ml-2 text-[10px] font-normal opacity-70">({s.confidence} confidence)</span> : null}
            </p>
            <p className="opacity-80 leading-snug">{s.rationale}</p>
            {s.impact ? <p className="opacity-60 text-[11px] mt-0.5">Impact: {s.impact}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
