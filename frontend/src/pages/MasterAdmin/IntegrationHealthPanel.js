/**
 * Master Admin → Security → Integration Health
 *
 * Iter 215l. Live diagnostic dashboard for third-party integrations
 * (DB / Stripe / Resend / Storage / Emergent LLM). Designed so the
 * GymAxis HQ team can answer "is X up?" in under 5 seconds without
 * SSHing into the backend pod.
 *
 * Endpoints used:
 *   GET /api/master-admin/integration-health         — run all
 *   GET /api/master-admin/integration-health/{key}   — re-run one
 *
 * Security: backend route enforces `is_master_admin`. We never render
 * raw API keys — only safe metadata (account ids, latency, domain
 * counts, etc.).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Activity, RefreshCw, CheckCircle2, AlertTriangle,
  XCircle, MinusCircle, ChevronDown, ChevronUp,
} from 'lucide-react';
import { useAuth } from '@/App';
import { Skeleton } from '@/components/ui/skeleton';
import HelpHint from '@/components/HelpHint';

const STATUS_TONE = {
  healthy: {
    Icon: CheckCircle2,
    dot: 'bg-emerald-500',
    text: 'text-emerald-700',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    label: 'Healthy',
  },
  degraded: {
    Icon: AlertTriangle,
    dot: 'bg-amber-500',
    text: 'text-amber-700',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    label: 'Degraded',
  },
  down: {
    Icon: XCircle,
    dot: 'bg-rose-500',
    text: 'text-rose-700',
    bg: 'bg-rose-50',
    border: 'border-rose-200',
    label: 'Down',
  },
  not_configured: {
    Icon: MinusCircle,
    dot: 'bg-zinc-400',
    text: 'text-zinc-600',
    bg: 'bg-zinc-50',
    border: 'border-zinc-200',
    label: 'Not configured',
  },
};

export default function IntegrationHealthPanel() {
  const { API } = useAuth();
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }),
    [],
  );

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState({}); // {key: bool} per-row spinner
  const [openRows, setOpenRows] = useState({}); // {key: bool} expand details
  const [lastRun, setLastRun] = useState(null);

  const runAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API}/master-admin/integration-health`, { headers });
      setData(r.data);
      setLastRun(new Date());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed to run checks');
    } finally {
      setLoading(false);
    }
  }, [API, headers]);

  const runOne = useCallback(async (key) => {
    setBusy((b) => ({ ...b, [key]: true }));
    try {
      const r = await axios.get(
        `${API}/master-admin/integration-health/${key}`,
        { headers },
      );
      setData((prev) => {
        if (!prev) return prev;
        const checks = prev.checks.map((c) => (c.key === key ? { ...c, ...r.data } : c));
        const summary = recomputeSummary(checks);
        return { checks, summary };
      });
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed');
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  }, [API, headers]);

  useEffect(() => { runAll(); }, [runAll]);

  return (
    <div className="space-y-5" data-testid="integration-health-panel">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 flex items-center gap-2">
            <Activity size={20} className="text-zinc-500" />
            Integration Health
            <HelpHint guideId="admin-integration-health" testId="help-hint-integration-health" />
          </h2>
          <p className="text-sm text-zinc-500 mt-1 max-w-xl">
            Live status of every third-party service the platform depends on.
            Master Admin only — failures here are dev/HQ concerns, not
            customer-facing.
          </p>
        </div>
        <button
          type="button"
          onClick={runAll}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-900 text-white text-sm font-semibold hover:bg-zinc-800 disabled:opacity-50"
          data-testid="integration-health-refresh-all"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Run all checks
        </button>
      </div>

      {error && (
        <div
          className="rounded-lg border border-rose-200 bg-rose-50 text-rose-700 px-3 py-2 text-sm"
          data-testid="integration-health-error"
        >
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : data ? (
        <>
          <SummaryStrip summary={data.summary} lastRun={lastRun} />
          <ul className="space-y-2" data-testid="integration-health-list">
            {data.checks.map((c) => (
              <CheckRow
                key={c.key}
                check={c}
                busy={!!busy[c.key]}
                expanded={!!openRows[c.key]}
                onToggle={() => setOpenRows((r) => ({ ...r, [c.key]: !r[c.key] }))}
                onRefresh={() => runOne(c.key)}
              />
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function recomputeSummary(checks) {
  const init = { healthy: 0, degraded: 0, down: 0, not_configured: 0, total: checks.length };
  return checks.reduce((acc, c) => {
    const k = c.status in acc ? c.status : 'down';
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, init);
}

function SummaryStrip({ summary, lastRun }) {
  const cells = [
    { key: 'healthy', label: 'Healthy', tone: STATUS_TONE.healthy },
    { key: 'degraded', label: 'Degraded', tone: STATUS_TONE.degraded },
    { key: 'down', label: 'Down', tone: STATUS_TONE.down },
    { key: 'not_configured', label: 'Not configured', tone: STATUS_TONE.not_configured },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="integration-health-summary">
      {cells.map((c) => (
        <div
          key={c.key}
          className={`rounded-lg border ${c.tone.border} ${c.tone.bg} p-3`}
          data-testid={`summary-${c.key}`}
        >
          <div className={`text-[10px] uppercase tracking-wider font-bold ${c.tone.text}`}>
            <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${c.tone.dot}`} />
            {c.label}
          </div>
          <div className="text-2xl font-bold text-zinc-900 mt-1">{summary[c.key] ?? 0}</div>
        </div>
      ))}
      {lastRun && (
        <div className="col-span-2 sm:col-span-4 text-[11px] text-zinc-400" data-testid="integration-health-last-run">
          Last run: {lastRun.toLocaleTimeString()} · {summary.total} checks
        </div>
      )}
    </div>
  );
}

function CheckRow({ check, busy, expanded, onToggle, onRefresh }) {
  const tone = STATUS_TONE[check.status] || STATUS_TONE.down;
  const detailEntries = Object.entries(check.details || {}).filter(([, v]) => v !== null && v !== undefined);
  const hasDetails = detailEntries.length > 0;

  return (
    <li
      className={`rounded-lg border ${tone.border} bg-white`}
      data-testid={`integration-row-${check.key}`}
    >
      <div className="flex items-center gap-3 p-3">
        <tone.Icon size={20} className={tone.text} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-semibold text-zinc-900">{check.label}</span>
            <span className={`text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded ${tone.bg} ${tone.text}`}>
              {tone.label}
            </span>
            {typeof check.latency_ms === 'number' && check.latency_ms > 0 && (
              <span className="text-[11px] text-zinc-400">{check.latency_ms} ms</span>
            )}
          </div>
          <div className="text-sm text-zinc-600 mt-0.5 break-words">{check.message}</div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {hasDetails && (
            <button
              type="button"
              onClick={onToggle}
              className="p-1.5 rounded hover:bg-zinc-100 text-zinc-500"
              title={expanded ? 'Hide details' : 'Show details'}
              data-testid={`integration-toggle-${check.key}`}
            >
              {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          )}
          <button
            type="button"
            onClick={onRefresh}
            disabled={busy}
            className="p-1.5 rounded hover:bg-zinc-100 text-zinc-500 disabled:opacity-50"
            title="Re-run this check"
            data-testid={`integration-rerun-${check.key}`}
          >
            <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
      {expanded && hasDetails && (
        <div className="border-t border-zinc-100 px-3 py-2 bg-zinc-50/60 text-xs">
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
            {detailEntries.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2 break-all">
                <dt className="text-zinc-500 font-medium">{k}</dt>
                <dd className="text-zinc-800 font-mono text-right">{String(v)}</dd>
              </div>
            ))}
          </dl>
          <div className="text-[10px] text-zinc-400 mt-2">
            Checked {check.checked_at ? new Date(check.checked_at).toLocaleString() : '—'}
          </div>
        </div>
      )}
    </li>
  );
}
