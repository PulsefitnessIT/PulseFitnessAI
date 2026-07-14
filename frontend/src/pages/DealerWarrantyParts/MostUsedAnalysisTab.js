import { useEffect, useState, useCallback } from 'react';
import { Search, TrendingUp, Link2, HelpCircle } from 'lucide-react';
import { dpApi } from './api';
import { Spinner, StatCard, TrendBadge, money } from './shared';

const TRENDS = ['', 'increasing', 'new_failure_trend', 'stable', 'decreasing', 'dormant', 'one_off'];

export default function MostUsedAnalysisTab() {
  const [data, setData] = useState({ parts: [], total: 0, matched: 0, unmatched: 0 });
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [trend, setTrend] = useState('');
  const [matched, setMatched] = useState('');
  const [highOnly, setHighOnly] = useState(false);
  const [sort, setSort] = useState('rank');

  const load = useCallback(() => {
    setLoading(true);
    dpApi.mostUsedAnalysis({
      q, trend, sort, limit: 300,
      ...(matched ? { matched } : {}),
      ...(highOnly ? { high_usage: 'true' } : {}),
    }).then(setData).finally(() => setLoading(false));
  }, [q, trend, matched, highOnly, sort]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <div className="space-y-4" data-testid="dp-most-used-analysis-tab">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Unique parts" value={data.total?.toLocaleString() || 0} tone="brand" testid="dp-mua-total" />
        <StatCard label="Matched to BOM" value={data.matched?.toLocaleString() || 0} tone="emerald" />
        <StatCard label="Unmatched" value={data.unmatched?.toLocaleString() || 0} tone="amber" />
        <StatCard label="Showing" value={data.parts?.length || 0} tone="slate" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="dp-mua-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search code or description…"
            className="w-full rounded-lg border border-slate-200 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--gx-brand-from)]/30" />
        </div>
        <select data-testid="dp-mua-trend" value={trend} onChange={(e) => setTrend(e.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
          {TRENDS.map((t) => <option key={t} value={t}>{t ? t.replace(/_/g, ' ') : 'All trends'}</option>)}
        </select>
        <select data-testid="dp-mua-matched" value={matched} onChange={(e) => setMatched(e.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
          <option value="">All</option><option value="true">Matched</option><option value="false">Unmatched</option>
        </select>
        <label className="text-sm text-slate-600 flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={highOnly} onChange={(e) => setHighOnly(e.target.checked)} /> High usage
        </label>
        <select data-testid="dp-mua-sort" value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm ml-auto">
          <option value="rank">Rank</option><option value="qty">Total qty</option><option value="cost">Total cost</option><option value="recent">Recent 12m</option>
        </select>
      </div>

      {loading ? <Spinner /> : data.parts.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No parts. Import Parts Used first.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">#</th><th>Part</th><th className="text-right">Total qty</th><th className="text-right">Events</th>
              <th className="text-right">Recent 12m</th><th className="text-right">Avg/mo</th><th>Trend</th><th className="text-right">Cost</th><th>BOM</th>
            </tr></thead>
            <tbody>
              {data.parts.map((p) => (
                <tr key={p.id} data-testid={`dp-mua-row-${p.code_norm}`} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="py-2.5 px-4 text-slate-400 tabular-nums">{p.rank}</td>
                  <td className="max-w-[280px]">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs text-slate-500">{p.code}</span>
                      {p.high_usage && <TrendingUp size={12} className="text-emerald-500" title="High usage" />}
                    </div>
                    <div className="text-xs text-slate-500 truncate">{p.description}</div>
                  </td>
                  <td className="text-right tabular-nums font-semibold">{p.total_qty?.toLocaleString()}</td>
                  <td className="text-right tabular-nums text-slate-500">{p.usage_count}</td>
                  <td className="text-right tabular-nums text-slate-500">{p.recent_12m}</td>
                  <td className="text-right tabular-nums text-slate-500">{p.avg_monthly}</td>
                  <td><TrendBadge trend={p.trend} /></td>
                  <td className="text-right tabular-nums text-slate-500">{p.total_cost ? money(p.total_cost) : '—'}</td>
                  <td>
                    {p.matched
                      ? <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600" title={p.matched_bom_code}><Link2 size={12} /> {p.matched_bom_code}</span>
                      : <span className="inline-flex items-center gap-1 text-[11px] text-amber-600"><HelpCircle size={12} /> Unmatched</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
