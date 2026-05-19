/**
 * Service Desk → Supplier Health (Iter 216h52)
 *
 * GymAxis-facing roll-up: every supplier across every customer org,
 * ranked by performance signals (open issues, SLA breaches, response
 * time). The pitch is: GymAxis can chase under-performing suppliers
 * on behalf of customers, and use the aggregated data as leverage
 * during renewal negotiations.
 *
 * Suppliers are grouped by normalised name (case-insensitive +
 * suffix-stripped) so the same vendor entered slightly differently
 * across customer accounts collapses into one row.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Search, Wrench, Building2, AlertTriangle, Mail, Phone, ChevronDown, ChevronRight, ListChecks,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

const SORTS = [
  { id: 'open_issues',  label: 'Open issues' },
  { id: 'sla_breaches', label: 'SLA breaches' },
  { id: 'equipment',    label: 'Kit serviced' },
  { id: 'name',         label: 'A → Z' },
];

const WINDOW_OPTIONS = [
  { id: 7,   label: '7d' },
  { id: 30,  label: '30d' },
  { id: 90,  label: '90d' },
  { id: 365, label: '1y' },
];

const StatPill = ({ label, value, tone = 'slate' }) => {
  const toneMap = {
    slate:  'bg-slate-50 text-slate-700 border-slate-200',
    red:    'bg-red-50 text-red-700 border-red-200',
    amber:  'bg-amber-50 text-amber-700 border-amber-200',
    emerald:'bg-emerald-50 text-emerald-700 border-emerald-200',
  };
  return (
    <div className={`rounded-lg border px-3 py-2 ${toneMap[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider font-medium opacity-70">{label}</div>
      <div className="text-lg font-semibold mt-0.5 tabular-nums">{value}</div>
    </div>
  );
};

const DeskSuppliers = ({ API }) => {
  const [suppliers, setSuppliers] = useState([]);
  const [totals, setTotals] = useState({ supplier_count: 0, equipment_total: 0, open_issues_total: 0, sla_breaches_total: 0, window_days: 30 });
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('open_issues');
  const [windowDays, setWindowDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/service-desk/suppliers/health`, {
        params: { days: windowDays, sort },
        headers: { Authorization: `Bearer ${token}` },
      });
      setSuppliers(res.data?.suppliers || []);
      setTotals(res.data?.totals || {});
    } catch {
      setSuppliers([]);
    } finally {
      setLoading(false);
    }
  }, [API, sort, windowDays]);

  useEffect(() => { load(); }, [load]);

  const ql = q.trim().toLowerCase();
  const filtered = !ql ? suppliers : suppliers.filter((s) => (
    (s.name || '').toLowerCase().includes(ql)
    || (s.aliases || []).some((a) => a.toLowerCase().includes(ql))
    || (s.orgs || []).some((o) => (o.name || '').toLowerCase().includes(ql))
  ));

  return (
    <div className="space-y-6" data-testid="desk-suppliers">
      <header>
        <h2 className="text-2xl font-bold text-slate-900">Supplier health</h2>
        <p className="text-sm text-slate-500 mt-1">
          Cross-customer rollup. Suppliers grouped by normalised name — same vendor
          across multiple customers shows up once with totals you can drill into.
        </p>
      </header>

      {/* Top-level rollup */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatPill label="Suppliers tracked" value={totals.supplier_count} />
        <StatPill label="Kit serviced" value={totals.equipment_total} />
        <StatPill label="Open issues" value={totals.open_issues_total} tone={totals.open_issues_total > 0 ? 'amber' : 'emerald'} />
        <StatPill label={`SLA breaches · ${totals.window_days}d`} value={totals.sla_breaches_total} tone={totals.sla_breaches_total > 0 ? 'red' : 'emerald'} />
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search suppliers or customer orgs…"
            className="pl-10 h-10 bg-white"
            data-testid="desk-suppliers-search"
          />
        </div>
        <div className="flex items-center gap-1 bg-slate-50 rounded-lg p-1 border border-slate-200">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 px-2">Window</span>
          {WINDOW_OPTIONS.map((w) => (
            <button
              key={w.id}
              onClick={() => setWindowDays(w.id)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md ${windowDays === w.id ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
              data-testid={`desk-suppliers-window-${w.id}`}
            >
              {w.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 bg-slate-50 rounded-lg p-1 border border-slate-200">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 px-2">Sort</span>
          {SORTS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSort(s.id)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md ${sort === s.id ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
              data-testid={`desk-suppliers-sort-${s.id}`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <p className="text-sm text-slate-500" data-testid="desk-suppliers-loading">Loading…</p>
      )}

      {!loading && filtered.length === 0 && (
        <Card className="p-12 text-center bg-white border-slate-200" data-testid="desk-suppliers-empty">
          <Wrench size={36} className="mx-auto mb-3 text-slate-300" />
          <p className="text-sm font-medium text-slate-600">
            {q ? 'No matching suppliers' : 'No suppliers tracked yet'}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {q ? 'Try a different name or org.' : 'Suppliers will appear here once customers add kit linked to them.'}
          </p>
        </Card>
      )}

      <div className="space-y-2">
        {filtered.map((s) => {
          const isOpen = !!expanded[s.normalised_name];
          const isHot = s.sla_breaches_window > 0 || s.open_issues_count >= 5;
          return (
            <Card
              key={s.normalised_name}
              className="bg-white border-slate-200 overflow-hidden"
              data-testid={`desk-supplier-row-${s.normalised_name}`}
            >
              <button
                onClick={() => setExpanded((e) => ({ ...e, [s.normalised_name]: !isOpen }))}
                className="w-full text-left p-4 flex items-start gap-4 hover:bg-slate-50 transition-colors"
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${isHot ? 'bg-red-50 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
                  {isHot ? <AlertTriangle size={18} /> : <Wrench size={18} />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-900 truncate">{s.name}</p>
                    {s.aliases && s.aliases.length > 0 && (
                      <span className="text-[10px] text-slate-400" title={s.aliases.join(', ')}>+{s.aliases.length} alias{s.aliases.length === 1 ? '' : 'es'}</span>
                    )}
                    {(s.supplier_types || []).slice(0, 3).map((t) => (
                      <Badge key={t} variant="outline" className="text-[9px] border-slate-200 text-slate-500 uppercase tracking-wider">{t}</Badge>
                    ))}
                  </div>
                  <div className="flex items-center gap-4 flex-wrap mt-1 text-xs text-slate-500">
                    <span className="flex items-center gap-1"><Building2 size={11} className="text-slate-400" />{s.customer_org_count} customer{s.customer_org_count === 1 ? '' : 's'}</span>
                    <span className="flex items-center gap-1"><ListChecks size={11} className="text-slate-400" />{s.equipment_count} kit</span>
                    {s.email && (
                      <span className="flex items-center gap-1 truncate"><Mail size={11} className="text-slate-400" />{s.email}</span>
                    )}
                    {s.phone && (
                      <span className="flex items-center gap-1"><Phone size={11} className="text-slate-400" />{s.phone}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0 text-right">
                  <div className="text-xs">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Open</p>
                    <p className={`text-base font-semibold tabular-nums ${s.open_issues_count >= 5 ? 'text-red-600' : s.open_issues_count > 0 ? 'text-amber-600' : 'text-slate-700'}`}>{s.open_issues_count}</p>
                  </div>
                  <div className="text-xs">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">SLA breach</p>
                    <p className={`text-base font-semibold tabular-nums ${s.sla_breaches_window > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{s.sla_breaches_window}</p>
                  </div>
                  <div className="text-xs">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Avg resp</p>
                    <p className="text-base font-semibold tabular-nums text-slate-700">{s.avg_response_hours != null ? `${s.avg_response_hours}h` : '—'}</p>
                  </div>
                  {isOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                </div>
              </button>

              {isOpen && (
                <div className="border-t border-slate-100 bg-slate-50/40 p-4 space-y-3" data-testid={`desk-supplier-detail-${s.normalised_name}`}>
                  {/* Drill-down: per-customer breakdown */}
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 font-medium mb-2">Per customer</p>
                    <div className="space-y-1">
                      {(s.orgs || []).map((o) => (
                        <div
                          key={o.id}
                          className="flex items-center justify-between px-3 py-2 bg-white rounded-md border border-slate-100 text-sm"
                          data-testid={`desk-supplier-org-${s.normalised_name}-${o.id}`}
                        >
                          <span className="text-slate-700 truncate flex items-center gap-2">
                            <Building2 size={12} className="text-slate-400" />
                            {o.name}
                          </span>
                          <span className="flex items-center gap-3 text-xs">
                            <span className="text-slate-500">{o.equipment_count} kit</span>
                            <span className={`tabular-nums font-medium ${o.open_issues_count > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                              {o.open_issues_count} open
                            </span>
                          </span>
                        </div>
                      ))}
                      {(s.orgs || []).length === 0 && (
                        <p className="text-xs text-slate-400 italic">No customer linkage data.</p>
                      )}
                    </div>
                  </div>

                  {/* Window metrics */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
                    <div className="text-xs">
                      <span className="text-slate-400 uppercase tracking-wider text-[10px]">Resolved · {totals.window_days}d</span>
                      <p className="tabular-nums font-semibold text-slate-700">{s.resolved_issues_window}</p>
                    </div>
                    <div className="text-xs">
                      <span className="text-slate-400 uppercase tracking-wider text-[10px]">Avg resolution</span>
                      <p className="tabular-nums font-semibold text-slate-700">{s.avg_resolution_hours != null ? `${s.avg_resolution_hours}h` : '—'}</p>
                    </div>
                    <div className="text-xs">
                      <span className="text-slate-400 uppercase tracking-wider text-[10px]">Avg first response</span>
                      <p className="tabular-nums font-semibold text-slate-700">{s.avg_response_hours != null ? `${s.avg_response_hours}h` : '—'}</p>
                    </div>
                    <div className="text-xs">
                      <span className="text-slate-400 uppercase tracking-wider text-[10px]">Breach rate</span>
                      <p className={`tabular-nums font-semibold ${s.resolved_issues_window > 0 && (s.sla_breaches_window / s.resolved_issues_window) > 0.25 ? 'text-red-600' : 'text-slate-700'}`}>
                        {s.resolved_issues_window > 0 ? `${Math.round(100 * s.sla_breaches_window / s.resolved_issues_window)}%` : '—'}
                      </p>
                    </div>
                  </div>

                  {s.aliases && s.aliases.length > 0 && (
                    <p className="text-[10px] text-slate-400 pt-1">
                      Also entered as: {s.aliases.join(' · ')}
                    </p>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export default DeskSuppliers;
