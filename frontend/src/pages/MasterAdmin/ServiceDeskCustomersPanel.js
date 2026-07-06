import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import {
  Headphones, Loader2, RefreshCw, UserPlus, Timer, AlertTriangle,
  CheckCircle2, Activity, TrendingUp, Wrench, Search,
} from 'lucide-react';

/**
 * Master Admin → Organisations → Service Desk customers.
 * Founder lens on the Service Desk product's own customers
 * (service_provider orgs): signup → trial → setup → usage → conversion.
 * Data: GET /api/master-admin/service-desk/customers.
 */
const STATUS = {
  converted:     { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  active:        { cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  onboarding:    { cls: 'bg-violet-50 text-violet-700 border-violet-200' },
  at_risk:       { cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  dormant:       { cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  churned_trial: { cls: 'bg-rose-50 text-rose-700 border-rose-200' },
};

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) : '—');
const fmtAgo = (s) => {
  if (!s) return 'never';
  const d = Math.floor((Date.now() - new Date(s).getTime()) / 86400000);
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d}d ago`;
};

function Kpi({ icon: Icon, label, value, sub, tone = 'slate', testId }) {
  const tones = {
    slate: 'text-slate-700', blue: 'text-blue-600', emerald: 'text-emerald-600',
    amber: 'text-amber-600', violet: 'text-violet-600',
  };
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid={testId}>
      <div className="flex items-center gap-2 text-slate-400 mb-1">
        <Icon size={15} /><span className="text-xs font-medium">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${tones[tone]}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function ServiceDeskCustomersPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get('/master-admin/service-desk/customers');
      setData(d);
    } catch (e) { /* surfaced via empty state */ }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  }
  const s = data?.summary || {};
  let rows = data?.customers || [];
  if (filter !== 'all') rows = rows.filter((r) => r.status === filter);
  if (q.trim()) {
    const t = q.toLowerCase();
    rows = rows.filter((r) => `${r.name} ${r.brand}`.toLowerCase().includes(t));
  }

  const filters = [
    { id: 'all', label: 'All' },
    { id: 'active', label: 'Active users' },
    { id: 'onboarding', label: 'Setting up' },
    { id: 'at_risk', label: 'At risk' },
    { id: 'converted', label: 'Paying' },
    { id: 'churned_trial', label: 'Lapsed' },
  ];

  return (
    <div className="space-y-6" data-testid="service-desk-customers-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center">
            <Headphones className="w-5 h-5 text-orange-500" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Service Desk customers</h2>
            <p className="text-sm text-slate-500">Who's signed up to the Service Desk — and how they're using it.</p>
          </div>
        </div>
        <button onClick={load} className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold border border-slate-200 text-slate-700 hover:bg-slate-50" data-testid="sd-customers-refresh">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Kpi icon={Headphones} label="Customers" value={s.total || 0} tone="slate" testId="sd-kpi-total" />
        <Kpi icon={UserPlus} label="New (30d)" value={s.new_30d || 0} tone="blue" sub="recent signups" testId="sd-kpi-new" />
        <Kpi icon={Timer} label="Active trials" value={s.trials_active || 0} tone="violet" sub={`${s.trials_expiring_7d || 0} expiring ≤7d`} testId="sd-kpi-trials" />
        <Kpi icon={Activity} label="Active this week" value={s.active_this_week || 0} tone="emerald" sub="logged cases" testId="sd-kpi-active" />
        <Kpi icon={CheckCircle2} label="Paying" value={s.converted || 0} tone="emerald" sub={`${s.conversion_rate || 0}% conversion`} testId="sd-kpi-converted" />
        <Kpi icon={TrendingUp} label="Total cases" value={s.total_cases || 0} tone="slate" sub="all customers" testId="sd-kpi-cases" />
      </div>

      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-1.5">
          {filters.map((f) => (
            <button key={f.id} onClick={() => setFilter(f.id)} data-testid={`sd-filter-${f.id}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                filter === f.id ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customers…"
            className="pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            data-testid="sd-customers-search" />
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="sd-customers-table">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                <th className="px-4 py-3 font-semibold">Customer</th>
                <th className="px-4 py-3 font-semibold">Signed up</th>
                <th className="px-4 py-3 font-semibold">Trial</th>
                <th className="px-4 py-3 font-semibold">Setup</th>
                <th className="px-4 py-3 font-semibold text-center">Engineers</th>
                <th className="px-4 py-3 font-semibold text-center">Cases</th>
                <th className="px-4 py-3 font-semibold text-center">Last 7d</th>
                <th className="px-4 py-3 font-semibold">Last activity</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-12 text-center text-slate-400" data-testid="sd-customers-empty">No customers match this view.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50/60" data-testid={`sd-customer-row-${r.id}`}>
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-900">{r.name || 'Unnamed'}</div>
                    <div className="text-[11px] text-slate-400">{r.brand || '—'}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(r.created_at)}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {r.subscription_active ? <span className="text-emerald-600 font-medium">Converted</span>
                      : r.days_left != null
                        ? <span className={r.days_left <= 7 && r.days_left >= 0 ? 'text-amber-600 font-medium' : r.days_left < 0 ? 'text-rose-500' : ''}>
                            {r.days_left < 0 ? 'Expired' : `${r.days_left}d left`}
                          </span>
                        : <span className="text-slate-400">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {r.setup_complete
                      ? <CheckCircle2 size={16} className="text-emerald-500" />
                      : <AlertTriangle size={15} className="text-amber-400" />}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-700"><span className="inline-flex items-center gap-1"><Wrench size={12} className="text-slate-400" />{r.engineers}</span></td>
                  <td className="px-4 py-3 text-center font-medium text-slate-700">{r.cases_total}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={r.cases_7d > 0 ? 'font-semibold text-emerald-600' : 'text-slate-300'}>{r.cases_7d}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{fmtAgo(r.last_activity)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold border ${(STATUS[r.status] || STATUS.dormant).cls}`}>
                      {r.status_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
