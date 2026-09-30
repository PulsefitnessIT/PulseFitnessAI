import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Spinner, Empty, inputCls, Field } from '../ui';
import { FileText, FileSpreadsheet, BarChart3, Filter } from 'lucide-react';

const TYPES = [
  { key: 'jobs', label: 'Jobs & Faults' },
  { key: 'services', label: 'Planned Servicing' },
  { key: 'sla', label: 'SLA' },
];

export default function PPMReports() {
  const [type, setType] = useState('jobs');
  const [filters, setFilters] = useState({ territory: '', site: '', from: '', to: '' });
  const [meta, setMeta] = useState({ sites: [], territories: [] });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    bfpo.get('/sites').then((r) => {
      const sites = r.data.sites;
      const terr = {};
      sites.forEach((s) => { if (s.territory_id) terr[s.territory_id] = s.territory_name; });
      setMeta({ sites, territories: Object.entries(terr).map(([id, name]) => ({ id, name })) });
    });
  }, []);

  const fetchReport = useCallback(() => {
    setLoading(true);
    const qs = new URLSearchParams({ report: type, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) }).toString();
    bfpo.get(`/staff/reports?${qs}`).then((r) => { setData(r.data); setLoading(false); });
  }, [type, filters]);
  useEffect(() => { fetchReport(); }, [fetchReport]);

  const exportUrl = (fmt) => {
    const qs = new URLSearchParams({ report: type, fmt, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) }).toString();
    return `${process.env.REACT_APP_BACKEND_URL}/api/bfpo/staff/reports/export?${qs}`;
  };
  const download = async (fmt) => {
    // Uses the shared cookie session; fall back to an explicit token if present.
    let t = null; try { t = localStorage.getItem('token'); } catch (e) { /* noop */ }
    const auth = t && t !== 'cookie' ? `Bearer ${t}` : 'Bearer cookie';
    const res = await fetch(exportUrl(fmt), { headers: { Authorization: auth }, credentials: 'include' });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${(data?.title || 'report').replace(/ /g, '_')}.${fmt === 'xlsx' ? 'xlsx' : 'pdf'}`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="ppm-reports">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="w-6 h-6 text-cyan-600" />
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
      </div>

      <div className="flex gap-1.5 mb-4 flex-wrap">
        {TYPES.map((t) => (
          <button key={t.key} onClick={() => setType(t.key)} data-testid={`report-type-${t.key}`}
            className={`px-4 py-2 rounded-full text-sm font-semibold transition-colors ${type === t.key ? 'bg-cyan-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <Card className="p-4 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm font-semibold mb-3"><Filter className="w-4 h-4" /> Filters</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
          <Field label="Territory"><select className={inputCls} value={filters.territory} onChange={(e) => set('territory', e.target.value)} data-testid="report-filter-territory"><option value="">All</option>{meta.territories.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
          <Field label="Site"><select className={inputCls} value={filters.site} onChange={(e) => set('site', e.target.value)} data-testid="report-filter-site"><option value="">All</option>{meta.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
          <Field label="From"><input type="date" className={inputCls} value={filters.from} onChange={(e) => set('from', e.target.value)} data-testid="report-filter-from" /></Field>
          <Field label="To"><input type="date" className={inputCls} value={filters.to} onChange={(e) => set('to', e.target.value)} data-testid="report-filter-to" /></Field>
          <div className="flex gap-2">
            <Btn variant="outline" onClick={() => download('pdf')} data-testid="report-export-pdf"><FileText className="w-4 h-4" /> PDF</Btn>
            <Btn variant="outline" onClick={() => download('xlsx')} data-testid="report-export-xlsx"><FileSpreadsheet className="w-4 h-4" /> Excel</Btn>
          </div>
        </div>
      </Card>

      {loading || !data ? <Spinner /> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-4">
            {data.summary.map((s) => (
              <Card key={s.label} className="p-4" data-testid={`report-kpi-${s.label}`}>
                <p className="text-2xl font-bold text-slate-900">{s.value}</p>
                <p className="text-sm text-slate-500">{s.label}</p>
              </Card>
            ))}
          </div>
          {data.rows.length === 0 ? <Empty icon={BarChart3} title="No records match" testid="report-empty" /> : (
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                  <tr>{data.columns.map((c) => <th key={c} className="text-left p-3 whitespace-nowrap">{c}</th>)}</tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100" data-testid={`report-row-${i}`}>
                      {data.columns.map((c) => <td key={c} className="p-3 whitespace-nowrap text-slate-700">{r[c]}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
