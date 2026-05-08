/**
 * Master Admin — Unified Audit Log viewer (iter 215ah).
 *
 * A single timeline of every security-relevant platform event (logins,
 * MFA, password resets, wallet topups/debits, invoice paid, Auto-Bill
 * charges + retries + exhaustion, nightly Auto-Bill sweeps). Filterable
 * by kind / org / actor / time-window, with a one-click CSV export for
 * SOC 2 / pentest evidence packets.
 *
 * Backend:
 *   GET /api/master-admin/audit-log[?since_days=&kinds=&organization_id=&actor_email=&limit=]
 *   GET /api/master-admin/audit-log/summary[?since_days=]
 *   GET /api/master-admin/audit-log/export.csv[?...]
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import {
  Loader2, Shield, ShieldAlert, AlertOctagon, Download, RefreshCw,
  LogIn, CreditCard, Wallet, Receipt, Zap, Info,
} from 'lucide-react';

// Order matters — sets the default order in the filter chips bar.
const KIND_META = {
  login:             { label: 'Login',               icon: LogIn },
  login_failed:      { label: 'Login failed',        icon: ShieldAlert },
  mfa_verify:        { label: 'MFA verified',        icon: Shield },
  mfa_failed:        { label: 'MFA failed',          icon: ShieldAlert },
  password_reset:    { label: 'Password reset',      icon: Shield },
  wallet_topup:      { label: 'Wallet topup',        icon: Wallet },
  wallet_debit:      { label: 'Wallet debit',        icon: Wallet },
  wallet_refund:     { label: 'Wallet refund',       icon: Wallet },
  invoice_generated: { label: 'Invoice generated',   icon: Receipt },
  invoice_paid:      { label: 'Invoice paid',        icon: Receipt },
  autopay_charge:    { label: 'Auto-Bill charged',   icon: Zap },
  autopay_retry:     { label: 'Auto-Bill retry',     icon: Zap },
  autopay_exhausted: { label: 'Auto-Bill exhausted', icon: AlertOctagon },
  autopay_sweep:     { label: 'Auto-Bill sweep',     icon: CreditCard },
};

const SEVERITY_CLASS = {
  info:     'text-zinc-600 bg-zinc-100 border-zinc-200',
  warning:  'text-amber-700 bg-amber-50 border-amber-200',
  critical: 'text-rose-700 bg-rose-50 border-rose-200',
};

const SINCE_OPTIONS = [
  { v: 1,  l: '24 h' },
  { v: 7,  l: '7 d'  },
  { v: 30, l: '30 d' },
  { v: 90, l: '90 d' },
];

export default function AuditLogPanel() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [sinceDays, setSinceDays] = useState(7);
  const [kinds, setKinds] = useState(new Set());  // empty = all
  const [actorEmail, setActorEmail] = useState('');
  const [orgFilter, setOrgFilter] = useState('');

  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const toggleKind = (k) => {
    const next = new Set(kinds);
    if (next.has(k)) next.delete(k); else next.add(k);
    setKinds(next);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ since_days: String(sinceDays), limit: '500' });
      if (kinds.size) params.set('kinds', Array.from(kinds).join(','));
      if (actorEmail.trim()) params.set('actor_email', actorEmail.trim().toLowerCase());
      if (orgFilter.trim()) params.set('organization_id', orgFilter.trim());
      const [list, summ] = await Promise.all([
        axios.get(`${API}/master-admin/audit-log?${params}`, { headers }),
        axios.get(`${API}/master-admin/audit-log/summary?since_days=${sinceDays}`, { headers }),
      ]);
      setData(list.data);
      setSummary(summ.data);
    } catch (e) {
      notify.error('Failed to load audit log');
    } finally {
      setLoading(false);
    }
  }, [API, headers, sinceDays, kinds, actorEmail, orgFilter]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = async () => {
    try {
      const params = new URLSearchParams({ since_days: String(sinceDays), limit: '10000' });
      if (kinds.size) params.set('kinds', Array.from(kinds).join(','));
      if (actorEmail.trim()) params.set('actor_email', actorEmail.trim().toLowerCase());
      if (orgFilter.trim()) params.set('organization_id', orgFilter.trim());
      const res = await fetch(`${API}/master-admin/audit-log/export.csv?${params}`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gymaxis-audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notify.success('CSV exported');
    } catch {
      notify.error('Could not export CSV');
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="audit-log-loading">
        <Loader2 className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }

  const events = data?.events || [];

  return (
    <div data-testid="audit-log-panel" className="space-y-5">
      {/* Summary tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="audit-log-summary">
        <SummaryTile label="Events" value={summary?.total ?? 0} icon={<Info size={16} />} tone="info" testid="aud-tile-total" />
        <SummaryTile label="Warnings" value={summary?.by_severity?.warning ?? 0} icon={<ShieldAlert size={16} />} tone="warning" testid="aud-tile-warn" />
        <SummaryTile label="Critical" value={summary?.by_severity?.critical ?? 0} icon={<AlertOctagon size={16} />} tone="critical" testid="aud-tile-critical" />
        <SummaryTile label="Range" value={SINCE_OPTIONS.find(o => o.v === sinceDays)?.l || ''} icon={<RefreshCw size={16} />} tone="info" testid="aud-tile-range" />
      </div>

      {/* Filters bar */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4 space-y-3" data-testid="audit-log-filters">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Since</span>
          {SINCE_OPTIONS.map((o) => (
            <button key={o.v}
              onClick={() => setSinceDays(o.v)}
              className={`rounded-full px-3 py-1 text-xs font-semibold border ${sinceDays === o.v ? 'bg-zinc-900 text-white border-zinc-900' : 'bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50'}`}
              data-testid={`aud-since-${o.v}`}>
              {o.l}
            </button>
          ))}
          <div className="w-full sm:w-auto sm:ml-auto flex flex-wrap items-center gap-2">
            <input type="text" value={actorEmail} onChange={(e) => setActorEmail(e.target.value)}
              placeholder="filter by email…"
              className="flex-1 sm:flex-none min-w-[140px] sm:w-48 rounded-lg border border-zinc-200 px-3 py-1 text-xs"
              data-testid="aud-filter-email" />
            <input type="text" value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)}
              placeholder="org id…"
              className="flex-1 sm:flex-none min-w-[100px] sm:w-36 rounded-lg border border-zinc-200 px-3 py-1 text-xs"
              data-testid="aud-filter-org" />
            <button onClick={load}
              className="rounded-lg px-3 py-1 text-xs font-semibold border border-zinc-200 hover:bg-zinc-50"
              data-testid="aud-refresh">
              <RefreshCw size={12} className="inline mr-1" />Refresh
            </button>
            <button onClick={exportCsv}
              className="rounded-lg px-3 py-1 text-xs font-bold bg-zinc-900 text-white hover:bg-zinc-700"
              data-testid="aud-export-csv">
              <Download size={12} className="inline mr-1" />CSV
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 pt-2 border-t border-zinc-100">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 self-center mr-1">Kinds</span>
          {Object.entries(KIND_META).map(([k, meta]) => {
            const active = kinds.has(k);
            const Icon = meta.icon;
            return (
              <button key={k}
                onClick={() => toggleKind(k)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold border inline-flex items-center gap-1 ${active ? 'bg-[var(--color-brand-blue)] text-white border-[var(--color-brand-blue)]' : 'bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50'}`}
                data-testid={`aud-kind-${k}`}>
                <Icon size={10} />{meta.label}
                {summary?.by_kind?.[k] ? <span className={`ml-1 ${active ? 'text-white/80' : 'text-zinc-400'}`}>· {summary.by_kind[k]}</span> : null}
              </button>
            );
          })}
          {kinds.size > 0 && (
            <button onClick={() => setKinds(new Set())}
              className="rounded-full px-2.5 py-1 text-[11px] font-semibold text-zinc-500 hover:text-zinc-900 underline"
              data-testid="aud-kind-clear">
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Event table — desktop */}
      <div className="hidden md:block bg-white border border-zinc-200 rounded-lg overflow-hidden" data-testid="audit-log-table">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 border-b border-zinc-200">
            <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-2.5">When</th>
              <th className="px-4 py-2.5">Kind</th>
              <th className="px-4 py-2.5">Org</th>
              <th className="px-4 py-2.5">Actor</th>
              <th className="px-4 py-2.5">Summary</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-zinc-400 text-sm" data-testid="aud-empty">
                No events in this window.
              </td></tr>
            )}
            {events.map((e, i) => {
              const meta = KIND_META[e.kind] || { label: e.kind, icon: Info };
              const Icon = meta.icon;
              return (
                <tr key={`${e.timestamp}-${i}`} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`aud-row-${i}`}>
                  <td className="px-4 py-2.5 text-xs text-zinc-500 whitespace-nowrap tabular-nums">
                    {new Date(e.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold border ${SEVERITY_CLASS[e.severity] || SEVERITY_CLASS.info}`}>
                      <Icon size={10} />{meta.label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-zinc-600 max-w-[220px] truncate">
                    {e.organization_name || <span className="text-zinc-300">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-zinc-600">
                    {e.actor_email || <span className="text-zinc-400">system</span>}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-zinc-700">{e.summary}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Event card list — mobile (iter 215al) */}
      <div className="md:hidden bg-white border border-zinc-200 rounded-lg overflow-hidden divide-y divide-zinc-100"
        data-testid="audit-log-cards">
        {events.length === 0 && (
          <div className="px-4 py-10 text-center text-zinc-400 text-sm" data-testid="aud-empty-mobile">
            No events in this window.
          </div>
        )}
        {events.map((e, i) => {
          const meta = KIND_META[e.kind] || { label: e.kind, icon: Info };
          const Icon = meta.icon;
          return (
            <div key={`${e.timestamp}-${i}`} className="p-3" data-testid={`aud-card-${i}`}>
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold border ${SEVERITY_CLASS[e.severity] || SEVERITY_CLASS.info}`}>
                  <Icon size={10} />{meta.label}
                </span>
                <span className="text-[10px] text-zinc-400 tabular-nums whitespace-nowrap">
                  {new Date(e.timestamp).toLocaleString()}
                </span>
              </div>
              <p className="text-xs text-zinc-700 leading-snug">{e.summary}</p>
              {(e.organization_name || e.actor_email) && (
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-zinc-500">
                  {e.organization_name && (
                    <span><span className="text-zinc-400">org:</span> {e.organization_name}</span>
                  )}
                  {e.actor_email
                    ? <span><span className="text-zinc-400">actor:</span> {e.actor_email}</span>
                    : <span className="text-zinc-400">actor: system</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SummaryTile({ label, value, icon, tone, testid }) {
  const cls = {
    info: 'bg-zinc-50 text-zinc-900 border-zinc-200',
    warning: 'bg-amber-50 text-amber-900 border-amber-200',
    critical: 'bg-rose-50 text-rose-900 border-rose-200',
  }[tone] || 'bg-zinc-50 text-zinc-900 border-zinc-200';
  return (
    <div className={`rounded-lg border p-3 ${cls}`} data-testid={testid}>
      <div className="flex items-center gap-2 opacity-70 text-[10px] font-bold uppercase tracking-wider">{icon}{label}</div>
      <div className="text-2xl font-black tabular-nums mt-1">{value}</div>
    </div>
  );
}
