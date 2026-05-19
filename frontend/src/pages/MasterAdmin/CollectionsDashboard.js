/**
 * Master Admin → Finance → Collections.
 *
 * CFO-shaped overview of money sitting in the platform's AR pile:
 *   • Aging buckets (current / 1-30 / 31-60 / 61+)
 *   • Top 10 overdue accounts by balance
 *   • MTD dunning reminders fired (with stage breakdown)
 *   • One-click "Run dunning sweep" + jump-to-org links
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  Loader2, AlarmClock, RefreshCw, Wallet, Bell, ArrowRight, AlertCircle,
} from 'lucide-react';

const CCY_SYM = { GBP: '£', EUR: '€', USD: '$' };

const BUCKET_TONE = {
  current: { bg: 'bg-zinc-50',    border: 'border-zinc-200',    text: 'text-zinc-900',    accent: 'text-zinc-500' },
  '1_30':  { bg: 'bg-amber-50',   border: 'border-amber-200',   text: 'text-amber-900',   accent: 'text-amber-700' },
  '31_60': { bg: 'bg-orange-50',  border: 'border-orange-200',  text: 'text-orange-900',  accent: 'text-orange-700' },
  '61_plus': { bg: 'bg-rose-50',  border: 'border-rose-200',    text: 'text-rose-900',    accent: 'text-rose-700' },
};

export default function CollectionsDashboard({ onPickOrg }) {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [currency, setCurrency] = useState('GBP');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/collections/dashboard?currency=${currency}`, { headers });
      setData(r.data);
    } catch (e) {
      notify.error('Failed to load collections dashboard');
    } finally {
      setLoading(false);
    }
  }, [API, headers, currency]);

  useEffect(() => { load(); }, [load]);

  const runDunning = async () => {
    setRunning(true);
    try {
      const r = await axios.post(`${API}/master-admin/billing/dunning/run`, {}, { headers });
      const sent = r.data?.summary?.sent || 0;
      const skipped = r.data?.summary?.skipped || 0;
      if (sent === 0 && skipped === 0) {
        notify.info('Nothing to chase right now — no invoices are past due.');
      } else {
        notify.success(`Dunning sweep complete · ${sent} sent · ${skipped} skipped`);
      }
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Dunning sweep failed');
    } finally {
      setRunning(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }
  if (!data) return null;

  const sym = CCY_SYM[data.currency] || '';
  const fmt = (minor) => `${sym}${(Math.abs(minor || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const totalReminders = data.reminders_mtd?.total || 0;
  const overdueTotal = (data.buckets || []).filter((b) => b.key !== 'current').reduce((s, b) => s + (b.amount || 0), 0);
  const overdueCount = (data.buckets || []).filter((b) => b.key !== 'current').reduce((s, b) => s + (b.count || 0), 0);

  return (
    <div data-testid="collections-dashboard" className="space-y-6">
      {/* ── Toolbar ── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-400">Finance</div>
          <h2 className="text-2xl font-extrabold text-zinc-900 leading-tight">Collections</h2>
          <p className="text-sm text-zinc-500 mt-1">
            Where the money sits, who's slow, and what's been chased this month.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="px-3 py-2 text-sm rounded border border-zinc-200 bg-white"
            data-testid="collections-currency"
          >
            {['GBP', 'EUR', 'USD'].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-zinc-200 bg-white"
            data-testid="collections-refresh"
          >
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            onClick={runDunning}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50"
            data-testid="collections-run-dunning"
          >
            <AlarmClock size={13} /> {running ? 'Running…' : 'Run dunning sweep'}
          </button>
        </div>
      </div>

      {/* ── Headline stats ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard
          icon={Wallet}
          label="Total outstanding"
          value={fmt(data.total_outstanding)}
          accent="text-zinc-900"
          testid="collections-stat-outstanding"
        />
        <StatCard
          icon={AlertCircle}
          label="Overdue"
          value={fmt(overdueTotal)}
          subtext={`${overdueCount} invoice${overdueCount === 1 ? '' : 's'}`}
          accent="text-rose-600"
          testid="collections-stat-overdue"
        />
        <StatCard
          icon={Bell}
          label="Reminders MTD"
          value={String(totalReminders)}
          subtext={
            `Stage 7: ${data.reminders_mtd?.by_stage?.['7'] || 0} · ` +
            `Stage 14: ${data.reminders_mtd?.by_stage?.['14'] || 0} · ` +
            `Stage 28: ${data.reminders_mtd?.by_stage?.['28'] || 0}`
          }
          accent="text-amber-600"
          testid="collections-stat-reminders"
        />
      </div>

      {/* ── Aging buckets ── */}
      <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-100 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
          Aging buckets
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 divide-x divide-zinc-100">
          {(data.buckets || []).map((b) => {
            const tone = BUCKET_TONE[b.key] || BUCKET_TONE.current;
            const pct = data.total_outstanding > 0 ? Math.round((b.amount / data.total_outstanding) * 100) : 0;
            return (
              <div key={b.key} className={`p-4 ${tone.bg}`} data-testid={`collections-bucket-${b.key}`}>
                <div className={`text-[10px] uppercase tracking-wider font-bold ${tone.accent}`}>{b.label}</div>
                <div className={`text-2xl font-extrabold mt-1 ${tone.text}`}>{fmt(b.amount)}</div>
                <div className="text-xs text-zinc-500 mt-1">
                  {b.count} invoice{b.count === 1 ? '' : 's'} · {pct}% of pile
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-zinc-200/60 overflow-hidden">
                  <div className={`h-full ${b.key === 'current' ? 'bg-zinc-400' : b.key === '1_30' ? 'bg-amber-400' : b.key === '31_60' ? 'bg-orange-500' : 'bg-rose-500'}`}
                       style={{ width: `${Math.min(pct, 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Top overdue accounts ── */}
      <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-100 flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">Top overdue accounts</span>
          <span className="text-[11px] text-zinc-400">{(data.top_overdue || []).length} of 10</span>
        </div>
        {(data.top_overdue || []).length === 0 ? (
          <div className="p-10 text-center text-sm text-zinc-400" data-testid="collections-top-empty">
            🎉 No overdue accounts. Everyone's paid.
          </div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead className="bg-zinc-50 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-4 py-2 text-left">Org</th>
                <th className="px-4 py-2 text-right">Outstanding</th>
                <th className="px-4 py-2 text-right">Days late</th>
                <th className="px-4 py-2 text-right">Invoices</th>
                <th className="px-4 py-2 text-right">Reminders</th>
                <th className="px-4 py-2 text-right">Last chase</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {(data.top_overdue || []).map((row, idx) => (
                <tr key={row.organization_id || idx} className={idx > 0 ? 'border-t border-zinc-100' : ''}
                    data-testid={`collections-top-row-${row.organization_id}`}>
                  <td className="px-4 py-3 font-semibold text-zinc-900">
                    {row.organization_name || '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-bold text-zinc-900">{fmt(row.balance)}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      row.max_days_overdue > 60 ? 'bg-rose-100 text-rose-700' :
                      row.max_days_overdue > 30 ? 'bg-orange-100 text-orange-700' :
                      row.max_days_overdue > 0  ? 'bg-amber-100 text-amber-700' :
                      'bg-zinc-100 text-zinc-500'
                    }`}>
                      {row.max_days_overdue}d
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-zinc-500">{row.invoice_count}</td>
                  <td className="px-4 py-3 text-right text-zinc-500">{row.reminder_count}</td>
                  <td className="px-4 py-3 text-right text-zinc-500 text-xs">
                    {row.last_reminded_at ? row.last_reminded_at.slice(0, 10) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {onPickOrg && row.organization_id && (
                      <button
                        onClick={() => onPickOrg(row.organization_id)}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded bg-zinc-900 text-white hover:bg-zinc-800"
                        data-testid={`collections-open-org-${row.organization_id}`}
                      >
                        Open <ArrowRight size={11} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      <div className="text-[11px] text-zinc-400 text-right">
        As of {(data.as_of || '').slice(0, 19).replace('T', ' ')} UTC
      </div>
    </div>
  );
}


function StatCard({ icon: Icon, label, value, subtext, accent, testid }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5" data-testid={testid}>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider font-bold text-zinc-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-3xl font-extrabold mt-2 ${accent || 'text-zinc-900'}`}>{value}</div>
      {subtext && <div className="text-xs text-zinc-500 mt-1">{subtext}</div>}
    </div>
  );
}
