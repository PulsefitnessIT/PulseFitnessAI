/**
 * Master Admin — Login Event Timeline.
 *
 * Chronological feed of every login / logout / failed attempt / MFA
 * verification / password reset across the platform, joined with
 * brute-force trust events. Built for security-team triage during
 * "is this account compromised?" investigations.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import {
  Loader2, Search, ShieldAlert, ShieldCheck, LogIn, LogOut,
  KeyRound, RefreshCw, AlertTriangle, Clock, ScrollText,
} from 'lucide-react';
import EmptyState from '@/components/shared/EmptyState';

const ACTION_META = {
  login:           { label: 'Login',          icon: LogIn,       tone: 'ok' },
  login_failed:    { label: 'Login failed',   icon: ShieldAlert, tone: 'bad' },
  logout:          { label: 'Logout',         icon: LogOut,      tone: 'neutral' },
  mfa_verify:      { label: 'MFA verified',   icon: ShieldCheck, tone: 'ok' },
  mfa_failed:      { label: 'MFA failed',     icon: ShieldAlert, tone: 'bad' },
  password_reset:  { label: 'Password reset', icon: KeyRound,    tone: 'neutral' },
};

const TONE_CLASSES = {
  ok:      'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  bad:     'bg-rose-500/10 text-rose-600 border-rose-500/30',
  neutral: 'bg-zinc-500/10 text-zinc-600 border-zinc-500/30',
};

export default function LoginEventsPanel() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [emailFilter, setEmailFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (emailFilter.trim()) params.set('email', emailFilter.trim().toLowerCase());
      const [events, summ] = await Promise.all([
        axios.get(`${API}/master-admin/login-events?${params}`, { headers }),
        axios.get(`${API}/master-admin/login-events/summary`, { headers }),
      ]);
      setData(events.data);
      setSummary(summ.data);
    } catch (e) {
      notify.error('Failed to load login events');
    } finally {
      setLoading(false);
    }
  }, [API, headers, emailFilter]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>;
  }

  return (
    <div data-testid="login-events-panel" className="space-y-5">
      {/* ── Summary tiles ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryTile
          label="Successful logins · 24h"
          value={summary?.success ?? 0}
          icon={<LogIn size={16} />}
          tone="ok"
          testid="lev-summary-success"
        />
        <SummaryTile
          label="Failed attempts · 24h"
          value={summary?.failure ?? 0}
          icon={<ShieldAlert size={16} />}
          tone={summary?.failure > 5 ? 'bad' : 'neutral'}
          testid="lev-summary-failure"
        />
        <SummaryTile
          label="Brute-force signals · 24h"
          value={summary?.brute_force_signals ?? 0}
          icon={<AlertTriangle size={16} />}
          tone={summary?.brute_force_signals > 0 ? 'bad' : 'neutral'}
          testid="lev-summary-bf"
        />
        <SummaryTile
          label="Unique users · last 100"
          value={data?.stats?.unique_users ?? 0}
          icon={<Clock size={16} />}
          tone="neutral"
          testid="lev-summary-unique"
        />
      </div>

      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="search"
            value={emailFilter}
            onChange={(e) => setEmailFilter(e.target.value)}
            placeholder="Filter by email…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded border border-zinc-200 bg-white"
            data-testid="lev-email-filter"
          />
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-zinc-200 bg-white"
          data-testid="lev-refresh-btn"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
        <a
          href="?section=audit-log"
          onClick={(e) => {
            // Let the sidebar state router handle it if possible (no full reload);
            // fallback to the native link on direct-bookmark usage.
            try {
              e.preventDefault();
              window.dispatchEvent(new CustomEvent('gymaxis:set-section', { detail: 'audit-log' }));
            } catch { /* fall through to href */ }
          }}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-[var(--color-brand-blue)] text-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue)] hover:text-white transition"
          data-testid="lev-open-audit-log"
          title="Open the unified audit log (supersets this view with wallet, invoice, Auto-Bill events)"
        >
          <ScrollText size={13} /> View in full audit log →
        </a>
      </div>

      {/* ── Trust event banner ── */}
      {(data?.trust_events || []).length > 0 && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-3" data-testid="lev-trust-banner">
          <div className="flex items-center gap-2 text-sm font-bold text-rose-700">
            <AlertTriangle size={14} /> {data.trust_events.length} brute-force signal{data.trust_events.length === 1 ? '' : 's'} in the last 24 h
          </div>
          <ul className="mt-2 space-y-1 text-xs text-rose-700/80">
            {data.trust_events.slice(0, 3).map((t) => (
              <li key={t.id} className="font-mono">
                {(t.created_at || '').slice(0, 19).replace('T', ' ')} · {t.severity?.toUpperCase()} · {t.summary}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Timeline ── */}
      <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-100 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
          Recent activity · last {data?.events?.length || 0}
        </div>
        {(!data?.events || data.events.length === 0) ? (
          <EmptyState
            icon={ScrollText}
            title="No login events match this filter"
            hint="Try widening the time window or clearing the search box. The platform records every login, logout, MFA event and password reset for SOC 2 evidence."
            testId="login-events-empty"
          />
        ) : (
          <ol className="divide-y divide-zinc-100">
            {data.events.map((e, idx) => (
              <EventRow key={`${e.timestamp}-${idx}`} event={e} />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}


/* ─────────────────── Bits ─────────────────── */

function SummaryTile({ label, value, icon, tone, testid }) {
  const cls = TONE_CLASSES[tone] || TONE_CLASSES.neutral;
  return (
    <div className={`rounded-lg border ${cls} p-4 sm:p-5`} data-testid={testid}>
      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider opacity-80">
        {icon} <span className="truncate">{label}</span>
      </div>
      <div className="text-3xl font-extrabold mt-1">{value.toLocaleString()}</div>
    </div>
  );
}

function EventRow({ event }) {
  const meta = ACTION_META[event.action] || { label: event.action, icon: KeyRound, tone: 'neutral' };
  const Icon = meta.icon;
  const tone = TONE_CLASSES[meta.tone] || TONE_CLASSES.neutral;
  return (
    <li className="flex items-center gap-3 px-4 py-3" data-testid={`lev-event-row-${event.action}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${tone}`}>
        <Icon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-zinc-900">
          {meta.label}
          {event.user_email && (
            <span className="ml-2 text-xs font-normal text-zinc-500 truncate">· {event.user_email}</span>
          )}
        </div>
        <div className="text-xs text-zinc-500 mt-0.5 truncate">
          {event.details || ''}
          {event.ip_address && <span className="ml-2 font-mono">{event.ip_address}</span>}
        </div>
      </div>
      <div className="text-xs text-zinc-400 font-mono shrink-0 hidden sm:block">
        {(event.timestamp || '').slice(0, 19).replace('T', ' ')}
      </div>
    </li>
  );
}
