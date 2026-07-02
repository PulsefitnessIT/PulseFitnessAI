/**
 * CRM Reports suite — Iter 216h226 (extended in h226-polish).
 *
 * Renders the 7 aggregated reports exposed by /api/crm/reports/*.
 * Each report has a compact card view (table + summary tiles), a
 * "Download CSV" button, and (for reports that accept it) a
 * per-report date-range filter that becomes ?from_iso=…&to_iso=…
 * on the API call.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  BarChart3, PieChart, TrendingUp, AlertTriangle, Users, ShieldCheck, Layers,
  Download, RefreshCw, Calendar, ClipboardList, ShieldAlert,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

// `dateable: true` → the backend honours from_iso / to_iso on this report.
const REPORTS = [
  { id: 'pipeline-by-stage',     label: 'Pipeline by Stage',       category: 'Pipeline',   icon: BarChart3,    dateable: true },
  { id: 'pipeline-by-territory', label: 'Pipeline by Territory',   category: 'Pipeline',   icon: Layers,       dateable: true },
  { id: 'quote-conversion',      label: 'Quote Conversion',        category: 'Sales',      icon: TrendingUp,   dateable: true },
  { id: 'margin',                label: 'Margin Analysis',         category: 'Sales',      icon: PieChart,     dateable: true },
  { id: 'lost-reasons',          label: 'Lost Reasons',            category: 'Sales',      icon: AlertTriangle, dateable: true },
  { id: 'salesperson',           label: 'Salesperson Performance', category: 'Team',       icon: Users,        dateable: true },
  { id: 'consent-overview',      label: 'GDPR Consent',            category: 'Compliance', icon: ShieldCheck,  dateable: false },
  { id: 'site-surveys-status',     label: 'Surveys by Status',        category: 'Site Surveys', icon: ClipboardList, dateable: true, exportable: true },
  { id: 'site-surveys-manager',    label: 'Surveys by Manager',       category: 'Site Surveys', icon: Users,         dateable: true, exportable: true },
  { id: 'site-surveys-high-risk',  label: 'High-Risk Installations',  category: 'Site Surveys', icon: ShieldAlert,   dateable: true, exportable: true },
  { id: 'site-surveys-conversion', label: 'Survey → Install Conversion', category: 'Site Surveys', icon: TrendingUp, dateable: true, exportable: true },
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

async function downloadExport(reportId, fmt, range) {
  try {
    const params = new URLSearchParams({ fmt });
    if (range?.from) params.set('from_iso', range.from);
    if (range?.to) params.set('to_iso', range.to);
    const res = await axios.get(`${API}/crm/reports/${reportId}/export?${params.toString()}`, { ...auth(), responseType: 'blob' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(res.data);
    a.download = `${reportId}.${fmt}`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    toast.error('Export failed');
  }
}


// Today / 7d / 30d / 90d / 365d / All quick-pick presets.
const PRESETS = [
  { id: '7d',   label: '7 days',  days: 7 },
  { id: '30d',  label: '30 days', days: 30 },
  { id: '90d',  label: '90 days', days: 90 },
  { id: 'ytd',  label: 'YTD',     days: 0,   ytd: true },
  { id: '365d', label: '12 mo',   days: 365 },
  { id: 'all',  label: 'All time', days: null },
];

function presetToRange(preset) {
  if (preset.id === 'all') return { from: '', to: '' };
  const to = new Date();
  const from = new Date();
  if (preset.ytd) {
    from.setMonth(0); from.setDate(1); from.setHours(0, 0, 0, 0);
  } else {
    from.setDate(from.getDate() - preset.days);
  }
  return { from: from.toISOString(), to: to.toISOString() };
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

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return iso; }
};

function DateRangePicker({ from, to, onChange, presetId, onPreset, testid }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-3" data-testid={testid}>
      {PRESETS.map(p => (
        <button
          key={p.id}
          type="button"
          onClick={() => onPreset(p)}
          className={`px-2 py-1 rounded-full text-[11px] font-bold border ${presetId === p.id ? 'text-white' : ''}`}
          style={presetId === p.id
            ? { background: 'var(--color-brand-blue)', borderColor: 'var(--color-brand-blue)' }
            : { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }
          }
          data-testid={`${testid}-preset-${p.id}`}
        >
          {p.label}
        </button>
      ))}
      <div className="ml-1 inline-flex items-center gap-1 px-2 py-1 rounded-md border" style={{ borderColor: 'var(--theme-border)' }}>
        <Calendar size={11} className="text-[color:var(--theme-text-muted)]" />
        <input
          type="date"
          value={from ? from.slice(0, 10) : ''}
          onChange={(e) => onChange({ from: e.target.value ? new Date(e.target.value).toISOString() : '', to })}
          className="bg-transparent text-xs outline-none w-[120px]"
          style={{ color: 'var(--theme-text)' }}
          data-testid={`${testid}-from`}
        />
        <span className="text-[10px] text-[color:var(--theme-text-muted)]">→</span>
        <input
          type="date"
          value={to ? to.slice(0, 10) : ''}
          onChange={(e) => onChange({ from, to: e.target.value ? new Date(e.target.value + 'T23:59:59Z').toISOString() : '' })}
          className="bg-transparent text-xs outline-none w-[120px]"
          style={{ color: 'var(--theme-text)' }}
          data-testid={`${testid}-to`}
        />
      </div>
    </div>
  );
}

function ReportPanel({ report }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [presetId, setPresetId] = useState('90d');
  const [range, setRange] = useState(() => presetToRange(PRESETS.find(p => p.id === '90d')));
  const Icon = report.icon || BarChart3;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (report.dateable && range.from) params.set('from_iso', range.from);
      if (report.dateable && range.to) params.set('to_iso', range.to);
      const qs = params.toString();
      const r = await axios.get(`${API}/crm/reports/${report.id}${qs ? `?${qs}` : ''}`, auth());
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load report');
    } finally { setLoading(false); }
  }, [report.id, report.dateable, range.from, range.to]);

  useEffect(() => { load(); }, [load]);

  const handlePreset = (p) => {
    setPresetId(p.id);
    setRange(presetToRange(p));
  };
  const handleManualRange = (r) => {
    setPresetId('custom');
    setRange(r);
  };

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
          {report.exportable && (
            <>
              <button
                onClick={() => downloadExport(report.id, 'xlsx', range)}
                disabled={!data?.rows?.length}
                className="h-8 px-2 rounded-full border border-[color:var(--theme-border)] inline-flex items-center gap-1 text-xs font-bold disabled:opacity-40"
                data-testid={`report-xlsx-${report.id}`}
                type="button"
              >
                <Download size={13} /> Excel
              </button>
              <button
                onClick={() => downloadExport(report.id, 'pdf', range)}
                disabled={!data?.rows?.length}
                className="h-8 px-2 rounded-full border border-[color:var(--theme-border)] inline-flex items-center gap-1 text-xs font-bold disabled:opacity-40"
                data-testid={`report-pdf-${report.id}`}
                type="button"
              >
                <Download size={13} /> PDF
              </button>
            </>
          )}
        </div>
      </header>

      {report.dateable && (
        <DateRangePicker
          testid={`report-range-${report.id}`}
          from={range.from}
          to={range.to}
          onChange={handleManualRange}
          presetId={presetId}
          onPreset={handlePreset}
        />
      )}

      {data?.totals?.from && data?.totals?.to && (
        <p className="text-[10px] text-[color:var(--theme-text-muted)] mb-2">
          Range: <strong>{fmtDate(data.totals.from)}</strong> → <strong>{fmtDate(data.totals.to)}</strong>
        </p>
      )}

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
    <div className="max-w-6xl mx-auto px-4 py-3 space-y-3" data-testid="crm-reports-page">
      {/* Iter 216h243 — H1 + description removed (platform-wide
          sub-header sweep). */}
      <header className="flex flex-wrap items-center justify-end gap-2">
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
