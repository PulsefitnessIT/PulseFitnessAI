/**
 * Pulse data explorer (Iter 226).
 *
 * A curated, read-only, Pulse-scoped data browser for Pulse Master Admins.
 * Lists a whitelist of business collections (each hard-filtered to Pulse
 * Fitness organisations on the backend) and lets the admin search +
 * paginate their own records. No GymAxis / other-tenant data is ever
 * returned — scoping is enforced server-side in
 * routes/master_admin_pulse_explorer.py.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Database, Search, ChevronLeft, ChevronRight, Loader2, Table2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` });

const fmtValue = (v) => {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return String(v);
};

const PulseDbExplorerPanel = () => {
  const [collections, setCollections] = useState([]);
  const [orgCount, setOrgCount] = useState(null);
  const [active, setActive] = useState(null);
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1, label: '' });
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDocs, setLoadingDocs] = useState(false);

  useEffect(() => {
    (async () => {
      setLoadingList(true);
      try {
        const r = await axios.get(`${API}/master-admin/pulse-explorer/collections`, { headers: authHeaders() });
        setCollections(r.data?.collections || []);
        setOrgCount(r.data?.pulse_org_count ?? null);
        const first = (r.data?.collections || []).find((c) => c.count > 0) || (r.data?.collections || [])[0];
        if (first) setActive(first.name);
      } catch {
        setCollections([]);
      } finally {
        setLoadingList(false);
      }
    })();
  }, []);

  const loadDocs = useCallback(async (name, pageNum, query) => {
    if (!name) return;
    setLoadingDocs(true);
    try {
      const r = await axios.get(`${API}/master-admin/pulse-explorer/collections/${name}`, {
        params: { page: pageNum, page_size: 25, q: query || undefined },
        headers: authHeaders(),
      });
      setRows(r.data?.docs || []);
      setMeta({ total: r.data?.total || 0, page: r.data?.page || 1, pages: r.data?.pages || 1, label: r.data?.label || name });
    } catch {
      setRows([]);
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  useEffect(() => { if (active) { setPage(1); loadDocs(active, 1, q); } }, [active, loadDocs]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSearch = (e) => { e.preventDefault(); setPage(1); loadDocs(active, 1, q); };
  const goPage = (p) => { setPage(p); loadDocs(active, p, q); };

  // Build column set from the first few rows (union of keys, _id first).
  const columns = (() => {
    const seen = [];
    rows.slice(0, 10).forEach((r) => Object.keys(r).forEach((k) => { if (!seen.includes(k)) seen.push(k); }));
    return seen.slice(0, 8); // keep the table readable
  })();

  return (
    <div className="space-y-5" data-testid="pulse-db-explorer">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[rgb(var(--rgb-brand-cyan)/0.12)] flex items-center justify-center text-[var(--color-brand-cyan)]">
            <Database size={18} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Pulse data explorer</h2>
            <p className="text-sm text-slate-500">
              Read-only view of your Pulse Fitness data{orgCount !== null ? ` · ${orgCount} organisation${orgCount === 1 ? '' : 's'} in scope` : ''}. GymAxis and other tenants are never shown.
            </p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-5">
        {/* Collection list */}
        <div className="lg:col-span-1 rounded-2xl border border-slate-200 bg-white overflow-hidden" data-testid="pulse-db-collections">
          <div className="px-4 py-3 border-b border-slate-200 text-xs font-bold uppercase tracking-wider text-slate-500">Collections</div>
          {loadingList ? (
            <div className="px-4 py-8 text-center text-sm text-slate-400"><Loader2 className="inline animate-spin" size={16} /></div>
          ) : (
            <div className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto">
              {collections.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  onClick={() => setActive(c.name)}
                  className={`w-full text-left px-4 py-2.5 flex items-center justify-between gap-2 transition-colors ${active === c.name ? 'bg-[rgb(var(--rgb-brand-cyan)/0.08)]' : 'hover:bg-slate-50'}`}
                  data-testid={`pulse-db-coll-${c.name}`}
                >
                  <span className={`text-sm ${active === c.name ? 'font-bold text-slate-900' : 'text-slate-600'}`}>{c.label}</span>
                  <span className="text-[11px] font-semibold text-slate-400 tabular-nums">{c.count >= 0 ? c.count : '—'}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Docs table */}
        <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
              <Table2 size={15} className="text-slate-400" />
              {meta.label || 'Select a collection'}
              <span className="text-[11px] font-semibold text-slate-400">{meta.total} record{meta.total === 1 ? '' : 's'}</span>
            </div>
            <form onSubmit={onSearch} className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search id, name, email, slug…"
                className="pl-7 pr-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs w-64 focus:outline-none focus:border-cyan-500"
                data-testid="pulse-db-search"
              />
            </form>
          </div>

          <div className="overflow-x-auto flex-1 min-h-[300px]">
            {loadingDocs ? (
              <div className="px-4 py-16 text-center text-sm text-slate-400"><Loader2 className="inline animate-spin mr-2" size={16} /> Loading…</div>
            ) : rows.length === 0 ? (
              <div className="px-4 py-16 text-center text-sm text-slate-400" data-testid="pulse-db-empty">No records in scope for this collection.</div>
            ) : (
              <table className="w-full text-xs" data-testid="pulse-db-table">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    {columns.map((c) => (
                      <th key={c} className="text-left font-bold uppercase tracking-wider text-slate-500 px-3 py-2 whitespace-nowrap">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={row._id || row.id || i} className="border-b border-slate-100 hover:bg-slate-50/60" data-testid="pulse-db-row">
                      {columns.map((c) => (
                        <td key={c} className="px-3 py-2 text-slate-700 max-w-[260px] truncate" title={fmtValue(row[c])}>{fmtValue(row[c])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {meta.pages > 1 && (
            <div className="px-4 py-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
              <span>Page {meta.page} of {meta.pages}</span>
              <div className="flex items-center gap-1">
                <button type="button" disabled={page <= 1} onClick={() => goPage(page - 1)} className="p-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50" data-testid="pulse-db-prev"><ChevronLeft size={14} /></button>
                <button type="button" disabled={page >= meta.pages} onClick={() => goPage(page + 1)} className="p-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50" data-testid="pulse-db-next"><ChevronRight size={14} /></button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PulseDbExplorerPanel;
