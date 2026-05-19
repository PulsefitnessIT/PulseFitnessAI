/**
 * CRM Reports suite — Iter 216h226.
 *
 * Renders the 7 aggregated reports exposed by /api/crm/reports/*.
 * Each report has a compact card view (table + summary tiles) and a
 * "Download CSV" button that exports the current view client-side.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  BarChart3, PieChart, TrendingUp, AlertTriangle, Users, ShieldCheck, Layers,
  Download, RefreshCw,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const REPORTS = [
  { id: 'pipeline-by-stage',     label: 'Pipeline by Stage',     category: 'Pipeline',   icon: BarChart3 },
  { id: 'pipeline-by-territory', label: 'Pipeline by Territory', category: 'Pipeline',   icon: Layers },
  { id: 'quote-conversion',      label: 'Quote Conversion',      category: 'Sales',      icon: TrendingUp },
  { id: 'margin',                label: 'Margin Analysis',       category: 'Sales',      icon: PieChart },
  { id: 'lost-reasons',          label: 'Lost Reasons',          category: 'Sales',      icon: AlertTriangle },
  { id: 'salesperson',           label: 'Salesperson Performance', category: 'Team',     icon: Users },
  { id: 'consent-overview',      label: 'GDPR Consent',          category: 'Compliance', icon: ShieldCheck },
];

function downloadCSV(filename, rows) {
  if (!rows || rows.length === 0) return;
  const headers = Object.keys(rows[0]);
  const esc = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
  const csv = [headers.join(',')].concat(rows.map(r => headers.map(h => esc(r[h])).join(','))).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

const TotalsStrip = ({ totals }) => {
  if (!totals) return null;
  const entries = Object.entries(totals).filter(([k]) => !['from', 'to', 'top', 'bottom', 'leaking'].includes(k));
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-lg border border-[color:var(--theme-border)] p-2.5">
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)]">
            {k.replace(/_/g, ' ')}
          </p>
          <p className="text-base font-extrabold mt-0.5" style={{ color: 'var(--theme-text)' }}>
            {typeof v === 'number' ? (k.includes('value') || k.includes('won') ? `£${v.toLocaleString()}` : v.toLocaleString()) : String(v).slice(0, 20)}
          </p>
        </div>
      ))}
    </div>
  );
};

const DataTable = ({ rows }) => {
  if (!rows || rows.length === 0) {
    return <p className="text-sm text-[color:var(--theme-text-muted)] py-8 text-center">No data in this report yet.</p>;
  }
  const headers = Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto rounded-lg border border-[color:var(--theme-border)]">
      <table className="min-w-full text-sm">
        <thead className="bg-[color:var(--theme-surface-hover)]">
          <tr>
            {headers.map(h => (
              <th key={h} className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">
                {h.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-[color:var(--theme-border)]">
              {headers.map(h => (
                <td key={h} className="px-3 py-2" style={{ color: 'var(--theme-text)' }}>
                  {typeof r[h] === 'number' && (h.includes('value') || h.includes('won')) ? `£${r[h].toLocaleString()}` : String(r[h] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

function ReportPanel({ report }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const Icon = report.icon || BarChart3;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/reports/${report.id}`, auth());
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load report');
    } finally { setLoading(false); }
  }, [report.id]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] p-5 bg-[color:var(--theme-surface)]" data-testid={`report-panel-${report.id}`}>
      <header className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Icon size={18} style={{ color: 'var(--color-brand-blue)' }} />
          <div>
            <h3 className="text-base font-extrabold" style={{ color: 'var(--theme-text)' }}>{report.label}</h3>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)]">{report.category}</p>
          </div>
        </div>
        <div className="flex gap-1.5">
          <button onClick={load} disabled={loading} className="h-8 w-8 rounded-full border border-[color:var(--theme-border)] flex items-center justify-center" aria-label="Refresh" data-testid={`report-refresh-${report.id}`} type="button">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => downloadCSV(`${report.id}.csv`, data?.rows || [])}
            disabled={!data?.rows?.length}
            className="h-8 px-2 rounded-full border border-[color:var(--theme-border)] inline-flex items-center gap-1 text-xs font-bold disabled:opacity-40"
            data-testid={`report-csv-${report.id}`}
            type="button"
          >
            <Download size={13} /> CSV
          </button>
        </div>
      </header>
      {loading && !data ? (
        <p className="text-sm text-[color:var(--theme-text-muted)] py-8 text-center">Loading…</p>
      ) : (
        <>
          <TotalsStrip totals={data?.totals} />
          <DataTable rows={data?.rows || []} />
          {data?.totals?.leaking?.length ? (
            <div className="mt-4">
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[color:var(--color-warning)] mb-2">⚠ Leaking margin — pending approval &gt; 48h</p>
              <DataTable rows={data.totals.leaking} />
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default function CRMReports() {
  const [category, setCategory] = useState('All');
  const categories = useMemo(() => ['All', ...Array.from(new Set(REPORTS.map(r => r.category)))], []);
  const filtered = useMemo(() => REPORTS.filter(r => category === 'All' || r.category === category), [category]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6" data-testid="crm-reports-page">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-brand-blue)' }}>Enterprise CRM</p>
          <h1 className="text-2xl md:text-3xl font-extrabold" style={{ color: 'var(--theme-text)' }}>Reports & analytics</h1>
          <p className="text-sm text-[color:var(--theme-text-muted)] max-w-2xl mt-1">
            Pipeline health, quote conversion, margin distribution, win/loss reasons, salesperson leaderboard, and GDPR consent posture — all aggregated live.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {categories.map(c => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-colors ${category === c ? 'text-white' : ''}`}
              style={category === c
                ? { background: 'var(--color-brand-blue)', borderColor: 'var(--color-brand-blue)' }
                : { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }
              }
              data-testid={`report-category-${c.toLowerCase()}`}
              type="button"
            >
              {c}
            </button>
          ))}
        </div>
      </header>

      <section className="grid lg:grid-cols-2 gap-5">
        {filtered.map(r => <ReportPanel key={r.id} report={r} />)}
      </section>
    </div>
  );
}
