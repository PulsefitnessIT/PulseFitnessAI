/**
 * DeskSalesReportTab — Memberships console (iter 216h204).
 *
 * Daily reconciliation for cash-style desk sales (iter 216h203). Lee
 * uses this to:
 *   • Tick the cash drawer against the system at end-of-day.
 *   • Spot anomalies (e.g. all sales by one operator with no card
 *     terminal entries).
 *   • Hand a CSV to the bookkeeper / Sage import.
 *
 * Defaults to TODAY (operator local) but supports any date range.
 *
 * Wire: GET /api/memberships/reports/desk-sales
 *       GET /api/memberships/reports/desk-sales/export.csv (download)
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Download, Calendar, Wallet, Users, RefreshCcw, FileText,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import EmptyState from '@/components/shared/EmptyState';
import DatePicker from '@/components/shared/DatePicker';

const METHOD_LABEL = {
  cash: 'Cash',
  card_terminal: 'Card terminal',
  bank_transfer: 'Bank transfer',
  comp: 'Comp',
  other: 'Other',
};

const METHOD_STYLE = {
  cash:          'bg-emerald-500/15 text-emerald-300',
  card_terminal: 'bg-sky-500/15 text-sky-300',
  bank_transfer: 'bg-violet-500/15 text-violet-300',
  comp:          'bg-zinc-500/15 text-zinc-300',
  other:         'bg-amber-500/15 text-amber-300',
};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function MethodPill({ method }) {
  const klass = METHOD_STYLE[method] || METHOD_STYLE.other;
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 text-[10px] font-bold rounded ${klass}`}
      data-testid={`desk-method-pill-${method}`}
    >
      {METHOD_LABEL[method] || method}
    </span>
  );
}

function Money({ pence }) {
  const v = typeof pence === 'number' ? pence : 0;
  return <span className="tabular-nums">£{(v / 100).toFixed(2)}</span>;
}

export default function DeskSalesReportTab({ API, headers }) {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [method, setMethod] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [data, setData] = useState({ rows: [], summary: null });
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { from, to };
      if (method) params.method = method;
      if (operatorId) params.operator_id = operatorId;
      const r = await axios.get(`${API}/memberships/reports/desk-sales`, { headers, params });
      setData(r.data || { rows: [], summary: null });
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load desk sales');
      setData({ rows: [], summary: null });
    } finally {
      setLoading(false);
    }
  }, [API, headers, from, to, method, operatorId]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams({ from, to });
      if (method) params.set('method', method);
      if (operatorId) params.set('operator_id', operatorId);
      const r = await axios.get(
        `${API}/memberships/reports/desk-sales/export.csv?${params}`,
        { headers, responseType: 'blob' },
      );
      // Trigger browser download.
      const url = window.URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `desk-sales-${from}-${to}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      notify.success('CSV downloaded');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to export');
    } finally {
      setExporting(false);
    }
  };

  const presetToday = () => { setFrom(todayISO()); setTo(todayISO()); };
  const presetWeek = () => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    setFrom(d.toISOString().slice(0, 10));
    setTo(todayISO());
  };
  const presetMonth = () => {
    const d = new Date();
    d.setDate(1);
    setFrom(d.toISOString().slice(0, 10));
    setTo(todayISO());
  };

  const summary = data.summary || { count: 0, total_pence: 0, by_method: {}, top_operators: [] };
  const methodRows = useMemo(
    () => Object.entries(summary.by_method || {}).sort(
      (a, b) => (b[1]?.total_pence || 0) - (a[1]?.total_pence || 0),
    ),
    [summary.by_method],
  );

  return (
    <div className="space-y-5" data-testid="desk-sales-report-tab">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>
            Desk sales reconciliation
          </h2>
          <p className="text-[12px] text-[color:var(--theme-text-muted)] mt-0.5">
            Every pack sold at the front desk (cash, card, comp). Filter, total and export for the bookkeeper.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[color:var(--theme-border)] text-[11px] font-bold hover:bg-white/5"
            data-testid="desk-sales-refresh"
          >
            <RefreshCcw size={12} /> Refresh
          </button>
          <button
            onClick={exportCsv}
            disabled={exporting || data.rows.length === 0}
            className="gx-btn-primary inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-extrabold uppercase tracking-wider disabled:opacity-40"
            data-testid="desk-sales-export-csv"
          >
            <Download size={12} /> {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <section className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">From</p>
            <DatePicker value={from} onChange={setFrom} testid="desk-sales-from" />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">To</p>
            <DatePicker value={to} onChange={setTo} testid="desk-sales-to" />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">Method</p>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="w-full h-10 px-2 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm"
              data-testid="desk-sales-method-filter"
            >
              <option value="">All methods</option>
              <option value="cash">Cash</option>
              <option value="card_terminal">Card terminal</option>
              <option value="bank_transfer">Bank transfer</option>
              <option value="comp">Comp</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">Operator</p>
            <input
              type="text"
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              placeholder="Operator user id (blank = all)"
              className="w-full h-10 px-2 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm"
              data-testid="desk-sales-operator-filter"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          <button onClick={presetToday} className="px-2.5 py-1 rounded-md border border-[color:var(--theme-border)] text-[11px] font-bold hover:bg-white/5" data-testid="desk-sales-preset-today">Today</button>
          <button onClick={presetWeek}  className="px-2.5 py-1 rounded-md border border-[color:var(--theme-border)] text-[11px] font-bold hover:bg-white/5" data-testid="desk-sales-preset-week">Last 7 days</button>
          <button onClick={presetMonth} className="px-2.5 py-1 rounded-md border border-[color:var(--theme-border)] text-[11px] font-bold hover:bg-white/5" data-testid="desk-sales-preset-month">This month</button>
        </div>
      </section>

      {/* Summary cards */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="desk-sales-summary">
        <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]"><Wallet size={12} /> Total taken</div>
          <p className="text-2xl font-extrabold mt-2 text-emerald-400" data-testid="desk-sales-total">
            <Money pence={summary.total_pence} />
          </p>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-1">{summary.count} sale{summary.count === 1 ? '' : 's'}</p>
        </div>

        <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]"><FileText size={12} /> By method</div>
          {methodRows.length === 0 && <p className="text-sm text-[color:var(--theme-text-muted)] mt-2">No sales in range.</p>}
          {methodRows.length > 0 && (
            <ul className="mt-2 space-y-1.5 text-[12px]">
              {methodRows.map(([m, v]) => (
                <li key={m} className="flex items-center justify-between gap-3" data-testid={`desk-sales-bymethod-${m}`}>
                  <span className="flex items-center gap-2"><MethodPill method={m} /> <span className="text-[color:var(--theme-text-muted)]">{v.count}×</span></span>
                  <span className="font-bold"><Money pence={v.total_pence} /></span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]"><Users size={12} /> Top operators</div>
          {(summary.top_operators || []).length === 0 && <p className="text-sm text-[color:var(--theme-text-muted)] mt-2">—</p>}
          {(summary.top_operators || []).length > 0 && (
            <ul className="mt-2 space-y-1.5 text-[12px]">
              {summary.top_operators.map((op) => (
                <li key={op.operator_id} className="flex items-center justify-between gap-3" data-testid={`desk-sales-operator-${op.operator_id}`}>
                  <span className="truncate">{op.operator_name || op.operator_id}</span>
                  <span className="font-bold"><Money pence={op.total_pence} /></span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Transactions table */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Transactions</p>
        {loading ? (
          <div className="text-[12px] text-[color:var(--theme-text-muted)] py-8 text-center" data-testid="desk-sales-loading">Loading…</div>
        ) : data.rows.length === 0 ? (
          <EmptyState
            icon={Calendar}
            title="No desk sales in this range"
            subtitle="Try widening the date range, or check the staff sold any packs today."
            testId="desk-sales-empty"
          />
        ) : (
          <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] overflow-hidden">
            <table className="w-full text-[12px]" data-testid="desk-sales-table">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] border-b border-[color:var(--theme-border)]">
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Member</th>
                  <th className="px-3 py-2">Pack</th>
                  <th className="px-3 py-2">Method</th>
                  <th className="px-3 py-2">Operator</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.id} className="border-b border-[color:var(--theme-border)] last:border-b-0 hover:bg-white/5" data-testid={`desk-sales-row-${r.id}`}>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.created_at ? new Date(r.created_at).toLocaleString('en-GB', {
                        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
                      }) : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-semibold">{r.member_name || '—'}</div>
                      {r.member_email && <div className="text-[10px] text-[color:var(--theme-text-muted)]">{r.member_email}</div>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-semibold">{r.plan_name || '—'}</div>
                      {r.credits_added > 0 && <div className="text-[10px] text-[color:var(--theme-text-muted)]">+{r.credits_added} credits</div>}
                    </td>
                    <td className="px-3 py-2"><MethodPill method={r.method} /></td>
                    <td className="px-3 py-2">{r.operator_name || '—'}</td>
                    <td className="px-3 py-2 text-right font-bold"><Money pence={r.amount_pence} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
