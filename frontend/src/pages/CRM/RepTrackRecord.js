/**
 * RepTrackRecord — iter 215dh.
 *
 * Per-rep "Your forecast track record" widget. Renders the last N
 * snapshotted periods for one rep with:
 *   - sparkline of accuracy %
 *   - row-by-row breakdown (period / call / actual / Δ / verdict)
 *   - summary tiles: average / best / worst / trend
 *
 * Used in two places:
 *   1. Rep self-view on the CRM start dashboard (no userId prop → defaults to me).
 *   2. Drill-down on the Accuracy tab (userId prop set to the row's rep).
 *
 * Backend: GET /api/crm/forecast/track-record?user_id=&periods=
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Award, AlertTriangle, Target, TrendingUp, TrendingDown, Activity } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

function fmtMoney(n) {
  const v = Number(n) || 0;
  return `£${v.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

const VERDICT_META = {
  on_call: { label: 'On call', icon: Target, colour: 'var(--color-success-green, #10b981)' },
  under: { label: 'Missed', icon: AlertTriangle, colour: 'var(--color-danger-red, #ef4444)' },
  over: { label: 'Sandbagger', icon: Award, colour: 'var(--color-warning, #f59e0b)' },
};

function Sparkline({ points, height = 36 }) {
  if (!points.length) return null;
  const w = 200;
  const max = 100; // accuracy is 0-100
  const stepX = w / Math.max(1, points.length - 1);
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * stepX},${height - (p / max) * (height - 4) - 2}`)
    .join(' ');
  return (
    <svg width={w} height={height} className="overflow-visible" data-testid="track-record-sparkline">
      <path d={path} fill="none" stroke="var(--color-brand-blue, #1d4ed8)" strokeWidth="2" />
      {points.map((p, i) => (
        <circle key={i} cx={i * stepX} cy={height - (p / 100) * (height - 4) - 2} r="3" fill="var(--color-brand-blue, #1d4ed8)" />
      ))}
    </svg>
  );
}

export default function RepTrackRecord({ userId = '', periods = 4, compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ periods: String(periods) });
      if (userId) params.set('user_id', userId);
      const r = await axios.get(`${API}/crm/forecast/track-record?${params.toString()}`, auth());
      setData(r.data);
    } catch (e) {
      if (e?.response?.status !== 403) toast.error(e?.response?.data?.detail || 'Failed to load track record');
      setData({ rows: [], summary: {} });
    } finally { setLoading(false); }
  }, [userId, periods]);

  useEffect(() => { load(); }, [load]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) unspecified; pre-existing as of iter 216h226-polish-5.
  const rows = data?.rows || [];
  const summary = data?.summary || {};
  const sparkPoints = useMemo(() => rows.map(r => r.call_accuracy_pct ?? 0), [rows]);

  const trendIcon = summary.trend === 'improving' ? TrendingUp : summary.trend === 'declining' ? TrendingDown : Activity;
  const trendColour = summary.trend === 'improving' ? 'var(--color-success-green, #10b981)' : summary.trend === 'declining' ? 'var(--color-danger-red, #ef4444)' : 'var(--theme-text-muted, #6b7280)';
  const TrendIcon = trendIcon;

  if (loading) return <p className="text-sm opacity-60" data-testid="track-record-loading">Loading track record…</p>;
  if (!rows.length) {
    return (
      <div className="rounded-xl border p-5 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="track-record-empty">
        <Activity size={20} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm opacity-70">No forecast snapshots yet — your manager hasn't frozen any periods.</p>
        <p className="text-xs opacity-50 mt-1">Once a snapshot is taken at period close, your accuracy track record will start filling in here.</p>
      </div>
    );
  }

  return (
    <div className={compact ? 'space-y-3' : 'space-y-4'} data-testid="rep-track-record">
      {!compact ? (
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-brand-blue, #1d4ed8)' }}>Your forecast track record</p>
            <h3 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>
              {data?.owner_name ? `${data.owner_name}'s call accuracy` : 'Call accuracy over time'}
            </h3>
          </div>
          <Sparkline points={sparkPoints} />
        </div>
      ) : (
        <Sparkline points={sparkPoints} />
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="track-record-tiles">
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Average</p>
          <p className="text-lg font-extrabold tabular-nums mt-0.5" style={{ color: 'var(--color-brand-blue, #1d4ed8)' }}>
            {summary.average_accuracy_pct != null ? `${summary.average_accuracy_pct}%` : '—'}
          </p>
        </div>
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Best</p>
          <p className="text-lg font-extrabold tabular-nums mt-0.5" style={{ color: 'var(--color-success-green, #10b981)' }}>
            {summary.best_pct != null ? `${summary.best_pct}%` : '—'}
          </p>
        </div>
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Worst</p>
          <p className="text-lg font-extrabold tabular-nums mt-0.5" style={{ color: 'var(--color-danger-red, #ef4444)' }}>
            {summary.worst_pct != null ? `${summary.worst_pct}%` : '—'}
          </p>
        </div>
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Trend</p>
          <p className="text-base font-extrabold capitalize mt-0.5 inline-flex items-center gap-1" style={{ color: trendColour }}>
            <TrendIcon size={14} /> {summary.trend || 'stable'}
          </p>
        </div>
      </div>

      <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }} data-testid="track-record-table">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead style={{ background: 'var(--theme-surface)' }}>
              <tr className="text-left text-[11px] uppercase tracking-wider opacity-70">
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2 text-right">Call / Commit</th>
                <th className="px-3 py-2 text-right">Actual won</th>
                <th className="px-3 py-2 text-right">Δ</th>
                <th className="px-3 py-2 text-right">Accuracy</th>
                <th className="px-3 py-2">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const v = VERDICT_META[r.verdict] || VERDICT_META.on_call;
                const VIcon = v.icon;
                return (
                  <tr key={r.period_key} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`track-record-row-${r.period_key}`}>
                    <td className="px-3 py-2 font-semibold" style={{ color: 'var(--theme-text)' }}>{r.period_key}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.manager_call > 0 ? fmtMoney(r.manager_call) : fmtMoney(r.commit_at_snapshot)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-success-green, #10b981)', fontWeight: 700 }}>{fmtMoney(r.actual_closed_won)}</td>
                    <td className="px-3 py-2 text-right tabular-nums" style={{ color: r.delta >= 0 ? 'var(--color-success-green, #10b981)' : 'var(--color-danger-red, #ef4444)' }}>
                      {r.delta >= 0 ? '+' : ''}{fmtMoney(r.delta)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold">{r.call_accuracy_pct != null ? `${r.call_accuracy_pct}%` : '—'}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-bold" style={{ background: `${v.colour}22`, color: v.colour }}>
                        <VIcon size={11} /> {v.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
