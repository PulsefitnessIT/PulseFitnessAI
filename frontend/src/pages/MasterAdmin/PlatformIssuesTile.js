/**
 * PlatformIssuesTile — 24h passive trust signal.
 *
 * Iter 216h215. Pulls `/api/master-admin/platform-issues-24h` and
 * renders a green / amber / red dot + breakdown. Each row is a button
 * that switches the Master Admin section to the relevant detail panel
 * (login-events / client-errors / trust).
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Activity, RefreshCw, ChevronRight } from 'lucide-react';
import { useAuth } from '@/App';

const TONE_CLASSES = {
  green: { dot: 'bg-emerald-500', value: 'text-emerald-700', label: 'All quiet' },
  amber: { dot: 'bg-amber-500',   value: 'text-amber-700',   label: 'Worth a look' },
  red:   { dot: 'bg-rose-500 animate-pulse', value: 'text-rose-700', label: 'Investigate now' },
};

export default function PlatformIssuesTile({ onGoSection }) {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const { data: payload } = await axios.get(
        `${API}/master-admin/platform-issues-24h`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setData(payload);
    } catch (_) {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => {
    load();
    // Refresh every 60 seconds so the tile is live without a page reload.
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const tone = data?.tone || 'green';
  const cls = TONE_CLASSES[tone];

  return (
    <div
      data-testid="platform-issues-tile"
      className="bg-white border border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-5 lg:p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center">
          <Activity size={16} className="text-slate-700" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
            Platform issues · 24h
          </p>
          <p className="text-xs text-slate-400">
            Failed logins + client crashes + high-severity trust events
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="text-slate-400 hover:text-slate-700 transition"
          aria-label="Refresh"
          data-testid="platform-issues-refresh"
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className={`w-3 h-3 rounded-full ${cls.dot}`} />
        <div className="flex items-baseline gap-2">
          <span
            className={`text-4xl font-extrabold tracking-tight ${cls.value}`}
            data-testid="platform-issues-count"
          >
            {data?.total ?? '—'}
          </span>
          <span className="text-xs text-slate-500 font-semibold">
            {cls.label}
          </span>
        </div>
      </div>

      <ul className="divide-y divide-slate-100 -mx-2">
        {(data?.breakdown || []).map((row) => (
          <li key={row.key}>
            <button
              type="button"
              onClick={() => onGoSection?.(row.panel)}
              className="w-full text-left px-2 py-2 hover:bg-slate-50 transition flex items-center gap-3 rounded"
              data-testid={`platform-issues-row-${row.key}`}
              title={row.hint}
            >
              <span className="flex-1 text-sm font-semibold text-slate-700 truncate">
                {row.label}
              </span>
              <span className={`text-sm font-bold tabular-nums ${row.count > 0 ? 'text-slate-900' : 'text-slate-400'}`}>
                {row.count}
              </span>
              <ChevronRight size={14} className="text-slate-300" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
