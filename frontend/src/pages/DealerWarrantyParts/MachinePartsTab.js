import { useEffect, useState, useCallback } from 'react';
import { Search, Cog, ArrowLeft, TrendingUp } from 'lucide-react';
import { dpApi } from './api';
import { Spinner, StatCard, TrendBadge, money } from './shared';

const PRIORITY_TONE = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  recommended: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  optional: 'bg-blue-50 text-blue-700 border-blue-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
  no_usage: 'bg-slate-50 text-slate-400 border-slate-200',
};

function MachineDetail({ topRef, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [usedOnly, setUsedOnly] = useState(true);

  useEffect(() => {
    setLoading(true);
    dpApi.machineParts(topRef).then(setData).finally(() => setLoading(false));
  }, [topRef]);

  if (loading) return <Spinner />;
  if (!data) return <div className="text-slate-400 text-sm py-10 text-center">Not found.</div>;
  const comps = usedOnly ? data.components.filter((c) => c.used_historically) : data.components;

  return (
    <div className="space-y-4" data-testid="dp-machine-detail">
      <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-800 inline-flex items-center gap-1"><ArrowLeft size={14} /> Back to machines</button>
      <div>
        <h2 className="text-lg font-bold text-slate-900">{data.machine.top_level_ref} <span className="text-sm font-normal text-slate-500">· {data.machine.top_level_stock_code}</span></h2>
        <p className="text-sm text-slate-500">{data.machine.description}</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="BOM components" value={data.component_count} tone="brand" />
        <StatCard label="Used historically" value={data.used_components} tone="emerald" />
        <StatCard label="Never used" value={data.unused_components} tone="slate" />
      </div>
      <label className="text-sm text-slate-600 flex items-center gap-1.5 cursor-pointer">
        <input type="checkbox" checked={usedOnly} onChange={(e) => setUsedOnly(e.target.checked)} /> Show only historically-used components
      </label>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
            <th className="py-2.5 px-4">Component</th><th className="text-right">BOM qty</th><th className="text-right">Used (total)</th><th className="text-right">Recent 12m</th><th>Trend</th><th className="text-right">Cost</th><th>Dealer priority</th>
          </tr></thead>
          <tbody>
            {comps.map((c) => (
              <tr key={c.code_norm} data-testid={`dp-mp-comp-${c.code_norm}`} className="border-b border-slate-50">
                <td className="py-2.5 px-4 max-w-[280px]"><span className="font-mono text-xs text-slate-500">{c.code}</span><div className="text-xs text-slate-500 truncate">{c.description}</div></td>
                <td className="text-right tabular-nums text-slate-500">{c.quantity}</td>
                <td className="text-right tabular-nums font-semibold">{c.used_historically ? <span className="inline-flex items-center gap-1 justify-end">{c.high_usage && <TrendingUp size={11} className="text-emerald-500" />}{c.total_qty_used}</span> : '—'}</td>
                <td className="text-right tabular-nums text-slate-500">{c.recent_12m || '—'}</td>
                <td>{c.trend ? <TrendBadge trend={c.trend} /> : <span className="text-xs text-slate-300">—</span>}</td>
                <td className="text-right tabular-nums text-slate-500">{c.unit_cost ? money(c.unit_cost) : '—'}</td>
                <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${PRIORITY_TONE[c.priority] || PRIORITY_TONE.low}`}>{String(c.priority).replace(/_/g, ' ')}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MachinePartsTab() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listDataMachines({ q, limit: 100 }).then((d) => { setRows(d.machines || []); setTotal(d.total || 0); }).finally(() => setLoading(false));
  }, [q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  if (sel) return <MachineDetail topRef={sel} onBack={() => setSel(null)} />;

  return (
    <div className="space-y-4" data-testid="dp-machine-parts-tab">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="dp-mp-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search machine ref, stock code or name…"
            className="w-full rounded-lg border border-slate-200 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--gx-brand-from)]/30" />
        </div>
        <span className="ml-auto text-xs text-slate-400">{total.toLocaleString()} machines</span>
      </div>
      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No machines. Import the BOM first.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {rows.map((m) => (
            <button key={m.id} data-testid={`dp-mp-machine-${m.id}`} onClick={() => setSel(m.top_level_ref)}
              className="text-left rounded-xl border border-slate-200 bg-white p-4 hover:shadow-md hover:border-[var(--gx-brand-from)]/40 transition-all">
              <div className="flex items-center gap-2">
                <Cog size={15} className="text-[var(--gx-brand-from)]" />
                <span className="font-mono text-sm font-semibold text-slate-900">{m.top_level_ref}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1 line-clamp-2 min-h-[2rem]">{m.description || 'No description'}</div>
              <div className="text-[11px] text-slate-400 mt-2">{m.component_count} components · v{m.version}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
