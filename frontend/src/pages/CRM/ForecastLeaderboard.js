/**
 * ForecastLeaderboard — iter 215di.
 *
 * "Top callers" widget. Ranks reps by average forecast accuracy across the
 * last N snapshotted periods. Highlights:
 *   - Gold/Silver/Bronze podium icons for the top 3.
 *   - Discreet bottom-quartile flag on the lowest 25% of reps.
 *   - Org-wide footer hint "X reps below 70% — might be worth a 1:1".
 *
 * Backend: GET /api/crm/forecast/leaderboard?periods=4
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Trophy, Medal, Award, ChevronDown, ChevronRight } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const PODIUM_ICONS = {
  gold: { Icon: Trophy, colour: '#d4af37' },
  silver: { Icon: Medal, colour: '#9ca3af' },
  bronze: { Icon: Award, colour: '#a16207' },
};

function pctColour(pct) {
  if (pct >= 90) return 'var(--color-success-green, #10b981)';
  if (pct >= 70) return 'var(--color-brand-blue, #1d4ed8)';
  if (pct >= 50) return 'var(--color-warning, #f59e0b)';
  return 'var(--color-danger-red, #ef4444)';
}

export default function ForecastLeaderboard({ periods = 4, limit = 10 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/forecast/leaderboard?periods=${periods}`, auth());
      setData(r.data);
    } catch (e) {
      if (e?.response?.status !== 403) {
        toast.error(e?.response?.data?.detail || 'Failed to load leaderboard');
      }
      setData({ rows: [], summary: {} });
    } finally { setLoading(false); }
  }, [periods]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p className="text-sm opacity-60" data-testid="leaderboard-loading">Loading leaderboard…</p>;
  const rows = (data?.rows || []).slice(0, limit);
  const summary = data?.summary || {};
  if (!rows.length) {
    return (
      <div className="rounded-xl border p-5 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="leaderboard-empty">
        <Trophy size={20} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm opacity-70">No leaderboard yet — take a snapshot to start scoring forecast accuracy.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="forecast-leaderboard">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
        data-testid="leaderboard-toggle"
      >
        <div className="flex items-center gap-2 min-w-0">
          <Trophy size={16} style={{ color: '#d4af37' }} />
          <p className="text-sm font-bold tracking-tight" style={{ color: 'var(--theme-text)' }}>Top callers</p>
          <span className="text-[11px] opacity-60">· last {summary.periods || periods} {summary.period_type || 'quarter'}{(summary.periods || periods) !== 1 ? 's' : ''}</span>
        </div>
        {collapsed ? <ChevronRight size={14} className="opacity-50" /> : <ChevronDown size={14} className="opacity-50" />}
      </button>

      {!collapsed ? (
        <>
          <div className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {rows.map((r) => {
              const podium = PODIUM_ICONS[r.podium];
              const PIcon = podium?.Icon;
              return (
                <div key={r.user_id} className="px-4 py-2.5 flex items-center gap-3" data-testid={`leaderboard-row-${r.user_id}`}>
                  <div className="w-7 text-center text-xs font-extrabold tabular-nums" style={{ color: 'var(--theme-text-muted)' }}>
                    {podium ? <PIcon size={16} style={{ color: podium.colour }} /> : `#${r.rank}`}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: 'var(--theme-text)' }}>{r.owner_name}</p>
                    <p className="text-[11px] opacity-60">
                      {r.periods_scored} period{r.periods_scored !== 1 ? 's' : ''} scored · best {r.best_pct}% · worst {r.worst_pct}%
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-base font-extrabold tabular-nums" style={{ color: pctColour(r.average_accuracy_pct) }}>
                      {r.average_accuracy_pct}%
                    </p>
                    {r.bottom_quartile && r.average_accuracy_pct < 70 ? (
                      <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-danger-red, #ef4444)' }} data-testid={`leaderboard-bottom-${r.user_id}`}>
                        Coach
                      </p>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {summary.below_70_count > 0 ? (
            <div className="px-4 py-2.5 text-[11px] border-t" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="leaderboard-coach-hint">
              <span className="opacity-80">
                <strong style={{ color: 'var(--color-danger-red, #ef4444)' }}>{summary.below_70_count}</strong> rep{summary.below_70_count !== 1 ? 's' : ''} below {summary.below_70_threshold}% accuracy — might be worth a 1:1.
              </span>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
