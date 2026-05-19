/**
 * Recent Errors panel — Master Admin Tools (Iter 234).
 *
 * Plugs into the existing `/api/ui-errors/summary` + `/recent` endpoints
 * (telemetry from `notify.error(...)` calls) so master admins can see
 * the last 7 days of failures across both consoles without needing
 * users to send screenshots.
 *
 * Two views:
 *   • Summary — top 50 fingerprints (groups same error across users)
 *   • Recent — chronological list of the last 50 individual events
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  AlertOctagon, RefreshCw, Loader2, Clock, Users, Route as RouteIcon, AlertCircle,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const VIEWS = [
  { id: 'summary', label: 'Top errors (grouped)' },
  { id: 'recent', label: 'Recent events' },
];
const WINDOWS = [
  { value: 1, label: 'Last 24h' },
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
];

const formatRelative = (iso) => {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return 'just now';
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

export default function RecentErrorsPanel() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = React.useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [view, setView] = useState('summary');
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      if (view === 'summary') {
        const r = await axios.get(`${API}/api/ui-errors/summary?days=${days}`, { headers });
        setSummary(r.data);
      } else {
        const r = await axios.get(`${API}/api/ui-errors/recent?limit=80`, { headers });
        setRecent(r.data.items || []);
      }
    } catch (e) {
      setErr(e.response?.data?.detail || 'Failed to load error events');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- deferred: keep current behaviour; revisit if unspecified ever captures state that needs to re-trigger the hook. Pre-existing since iter 216h226-polish-5.
  }, [API, headers, view, days]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="recent-errors-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold tracking-tight inline-flex items-center gap-2 text-zinc-900">
            <AlertOctagon size={20} className="text-rose-500" /> Recent Errors
          </h2>
          <p className="text-xs mt-1 text-zinc-500">
            Captures every error toast users hit, with full server detail. Use this to triage failures without asking for screenshots.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-2 rounded-md border border-zinc-200 hover:bg-zinc-50 text-sm font-semibold inline-flex items-center gap-1.5 text-zinc-700 disabled:opacity-50"
          data-testid="recent-errors-refresh"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Refresh
        </button>
      </div>

      {/* Pill bar */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 rounded-full p-1 bg-zinc-100 border border-zinc-200">
          {VIEWS.map((v) => {
            const on = view === v.id;
            return (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold ${
                  on ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500 hover:text-zinc-800'
                }`}
                data-testid={`recent-errors-view-${v.id}`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
        {view === 'summary' && (
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value, 10))}
            className="px-2 py-1.5 text-xs border border-zinc-200 rounded-md bg-white text-zinc-900"
            data-testid="recent-errors-window"
          >
            {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        )}
      </div>

      {err && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 inline-flex items-center gap-2" data-testid="recent-errors-load-error">
          <AlertCircle size={14} /> {err}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12">
          <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)] mx-auto" />
        </div>
      ) : view === 'summary' ? (
        <SummaryView summary={summary} />
      ) : (
        <RecentView recent={recent} />
      )}
    </div>
  );
}


function SummaryView({ summary }) {
  if (!summary) return null;
  if (!summary.top || summary.top.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-10 text-center" data-testid="recent-errors-empty">
        <AlertOctagon size={36} className="mx-auto text-emerald-300 mb-3" />
        <p className="text-sm font-medium text-zinc-700">No errors in this window</p>
        <p className="text-xs text-zinc-500 mt-1">Nice — your users are having a smooth time.</p>
      </div>
    );
  }
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <SummaryStat label="Total events" value={summary.total_events} />
        <SummaryStat label="Unique users hit" value={summary.unique_users_affected} />
        <SummaryStat label="Distinct errors" value={summary.top.length} />
      </div>
      <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto" data-testid="recent-errors-summary-list">
        <table className="w-full text-sm min-w-[700px]">
          <thead className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200">
            <tr>
              <th className="text-left py-2.5 px-4 font-semibold">Error</th>
              <th className="text-right font-semibold">Count</th>
              <th className="text-right font-semibold">Users</th>
              <th className="text-left font-semibold pl-4">Last seen</th>
              <th className="text-left font-semibold">First seen</th>
              <th className="text-right pr-4 font-semibold">&nbsp;</th>
            </tr>
          </thead>
          <tbody>
            {summary.top.map((row) => (
              <tr key={row.fingerprint} className="border-b border-zinc-50 last:border-b-0 align-top" data-testid={`recent-errors-row-${row.fingerprint}`}>
                <td className="py-2.5 px-4">
                  <p className="font-medium text-zinc-900 text-sm">{row.title}</p>
                  {row.detail && <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{row.detail}</p>}
                  {row.paths && row.paths.length > 0 && (
                    <p className="text-[10px] text-zinc-400 mt-1 inline-flex items-center gap-1">
                      <RouteIcon size={9} />
                      {row.paths.slice(0, 2).join(' · ')}{row.paths.length > 2 ? ` (+${row.paths.length - 2})` : ''}
                    </p>
                  )}
                </td>
                <td className="text-right text-sm font-bold tabular-nums text-rose-600">{row.count}</td>
                <td className="text-right text-sm tabular-nums text-zinc-600 inline-flex items-center justify-end gap-1 pt-2.5"><Users size={11} className="opacity-60" />{row.affected_users}</td>
                <td className="pl-4 text-xs text-zinc-500">{formatRelative(row.last_seen)}</td>
                <td className="text-xs text-zinc-500">{formatRelative(row.first_seen)}</td>
                <td className="text-right pr-4 text-[10px] font-mono text-zinc-400">{row.fingerprint.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}


function SummaryStat({ label, value }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</p>
      <p className="text-2xl font-bold tabular-nums text-zinc-900 mt-0.5">{value ?? 0}</p>
    </div>
  );
}


function RecentView({ recent }) {
  if (recent.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-10 text-center" data-testid="recent-errors-empty-recent">
        <AlertOctagon size={36} className="mx-auto text-emerald-300 mb-3" />
        <p className="text-sm font-medium text-zinc-700">No recent events</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-zinc-200 bg-white divide-y divide-zinc-50" data-testid="recent-errors-recent-list">
      {recent.map((row) => (
        <div key={row.id} className="p-3 flex items-start gap-3" data-testid={`recent-errors-event-${row.id}`}>
          <AlertCircle size={14} className="text-rose-500 shrink-0 mt-1" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-zinc-900">{row.title}</p>
            {row.detail && <p className="text-[11px] text-zinc-500 mt-0.5">{row.detail}</p>}
            <p className="text-[10px] text-zinc-400 mt-1 inline-flex items-center gap-2 flex-wrap">
              <Clock size={9} /> {formatRelative(row.created_at)}
              {row.path && <><span>·</span> <RouteIcon size={9} /> {row.path}</>}
              {row.user_email && <><span>·</span> {row.user_email}</>}
              {row.account_type && <><span>·</span> <span className="font-mono">{row.account_type}</span></>}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
