import { useEffect, useState, useCallback } from 'react';
import { Radar, TrendingUp, AlertTriangle, PackageX, Layers, Download, FileSpreadsheet } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard, TrendBadge, money } from './shared';

const TONE_ICON = { red: 'text-red-500', amber: 'text-amber-500', slate: 'text-slate-400' };

const INSIGHTS = [
  { key: 'bom_missing_high_usage', label: 'High-usage parts missing from BOM', icon: AlertTriangle, tone: 'red', desc: 'Used heavily but not in any current BOM — review & alias.' },
  { key: 'new_failure_trend', label: 'New failure trends', icon: TrendingUp, tone: 'red', desc: 'Recently-appearing parts failing repeatedly.' },
  { key: 'increasing_usage', label: 'Increasing usage', icon: TrendingUp, tone: 'amber', desc: 'Usage rate rising vs historical average.' },
  { key: 'sent_never_used', label: 'Sent but never used', icon: PackageX, tone: 'amber', desc: 'In dealer stock but never consumed — avoid repeat.' },
  { key: 'bom_never_used', label: 'BOM components never used', icon: Layers, tone: 'slate', desc: 'In BOM but no historical usage — likely not dealer spares.' },
];

const REPORTS = [
  { id: 'most-used-since-2022', label: 'Most Used Parts Since 2022' },
  { id: 'parts-used-vs-bom-match', label: 'Parts Used vs BOM Match' },
  { id: 'unmatched-high-usage', label: 'Unmatched High-Usage Parts' },
  { id: 'bom-no-usage', label: 'BOM Components With No Usage' },
];

export default function DataIntelligenceTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState('bom_missing_high_usage');
  const [machineRef, setMachineRef] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    dpApi.dataMonitoring().then(setData).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const dl = async (report, ref = '') => {
    try { await dpApi.downloadDataReport(report, ref); notify.success('Report downloaded'); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Download failed'); }
  };

  if (loading) return <Spinner />;
  if (!data) return <div className="text-slate-400 text-sm py-10 text-center">No data.</div>;
  const ins = data.insights;
  const active = ins[open];

  return (
    <div className="space-y-5" data-testid="dp-intelligence-tab">
      <div className="flex items-center gap-2">
        <Radar size={18} className="text-[var(--gx-brand-from)]" />
        <h3 className="font-semibold text-slate-900">Parts Intelligence &amp; Monitoring</h3>
        <span className="ml-auto text-xs text-slate-400">{data.totals.matched_bom_components}/{data.totals.bom_components} BOM components matched · {data.totals.analysis_parts} parts analysed</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {INSIGHTS.map((cfg) => {
          const v = ins[cfg.key];
          const Icon = cfg.icon;
          return (
            <button key={cfg.key} data-testid={`dp-insight-${cfg.key}`} onClick={() => setOpen(cfg.key)}
              className={`text-left rounded-xl border p-4 transition-all hover:shadow-md ${open === cfg.key ? 'border-[var(--gx-brand-from)] ring-2 ring-[var(--gx-brand-from)]/20' : 'border-slate-200'} bg-white`}>
              <Icon size={16} className={`${TONE_ICON[cfg.tone] || 'text-slate-400'} mb-2`} />
              <div className="text-2xl font-bold text-slate-900 tabular-nums">{v.count}{cfg.key === 'sent_never_used' && v.value ? <span className="text-sm font-normal text-slate-400"> · {money(v.value)}</span> : ''}</div>
              <div className="text-[11px] font-semibold text-slate-500 mt-0.5 leading-tight">{cfg.label}</div>
            </button>
          );
        })}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
          <div className="font-semibold text-sm text-slate-900">{INSIGHTS.find((c) => c.key === open)?.label}</div>
          <div className="text-xs text-slate-500">{INSIGHTS.find((c) => c.key === open)?.desc}</div>
        </div>
        {(active.top || []).length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">Nothing flagged. 🎉</div>
        ) : open === 'sent_never_used' ? (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100"><th className="py-2 px-4">Part</th><th>Store</th><th className="text-right">On hand</th><th className="text-right">Value</th></tr></thead>
            <tbody>{active.top.map((r, i) => (
              <tr key={i} className="border-b border-slate-50"><td className="py-2 px-4"><span className="font-mono text-xs text-slate-500">{r.part_sku}</span> {r.part_name}</td><td className="text-slate-500 text-xs">{r.store_name}</td><td className="text-right tabular-nums">{r.on_hand}</td><td className="text-right tabular-nums">{money(r.value)}</td></tr>
            ))}</tbody>
          </table>
        ) : open === 'bom_never_used' ? (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100"><th className="py-2 px-4">Component</th><th>Description</th></tr></thead>
            <tbody>{active.top.map((r, i) => (
              <tr key={i} className="border-b border-slate-50"><td className="py-2 px-4 font-mono text-xs text-slate-500">{r.code}</td><td className="text-slate-600">{r.description}</td></tr>
            ))}</tbody>
          </table>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100"><th className="py-2 px-4">Part</th><th className="text-right">Total qty</th><th className="text-right">Recent 12m</th><th>Trend</th></tr></thead>
            <tbody>{active.top.map((r, i) => (
              <tr key={i} className="border-b border-slate-50"><td className="py-2 px-4"><span className="font-mono text-xs text-slate-500">{r.code}</span> <span className="text-slate-600">{r.description}</span></td><td className="text-right tabular-nums font-semibold">{r.total_qty}</td><td className="text-right tabular-nums text-slate-500">{r.recent_12m}</td><td><TrendBadge trend={r.trend} /></td></tr>
            ))}</tbody>
          </table>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center gap-2 mb-3"><FileSpreadsheet size={16} className="text-[var(--gx-brand-from)]" /><span className="font-semibold text-sm text-slate-900">Reports &amp; exports (CSV)</span></div>
        <div className="grid sm:grid-cols-2 gap-2">
          {REPORTS.map((r) => (
            <button key={r.id} data-testid={`dp-report-${r.id}`} onClick={() => dl(r.id)}
              className="flex items-center gap-2 rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm text-slate-700 hover:border-[var(--gx-brand-from)]/40 hover:bg-slate-50 text-left">
              <Download size={14} className="text-slate-400" /> {r.label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <input value={machineRef} onChange={(e) => setMachineRef(e.target.value)} placeholder="Machine ref (e.g. 305H-ZZY)" className="flex-1 max-w-xs rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono" />
          <button data-testid="dp-report-by-machine" onClick={() => machineRef.trim() ? dl('most-used-by-machine', machineRef.trim()) : notify.error('Enter a machine ref')}
            className="inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90"><Download size={14} /> Most Used by Machine</button>
        </div>
      </div>
    </div>
  );
}
