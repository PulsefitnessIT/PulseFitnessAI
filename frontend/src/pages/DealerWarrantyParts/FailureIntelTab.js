import { useEffect, useState, useCallback } from 'react';
import { Globe, TrendingUp } from 'lucide-react';
import { dpApi } from './api';
import { StatCard, Spinner } from './shared';

const GROUPS = [
  { id: 'part', label: 'By part' },
  { id: 'country', label: 'By country' },
  { id: 'dealer', label: 'By dealer' },
  { id: 'model', label: 'By model' },
  { id: 'serial', label: 'By serial range' },
];

function Bars({ title, data }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-sm font-bold text-slate-900 mb-3">{title}</h3>
      {data.length === 0 ? <p className="text-sm text-slate-400">No data.</p> : (
        <div className="space-y-2.5">
          {data.map((d) => (
            <div key={d.label}>
              <div className="flex justify-between text-xs mb-1"><span className="font-medium text-slate-700">{d.label}</span><span className="tabular-nums text-slate-500">{d.count}</span></div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)]" style={{ width: `${(d.count / max) * 100}%` }} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function FailureIntelTab() {
  const [ov, setOv] = useState(null);
  const [group, setGroup] = useState('part');
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { dpApi.intelOverview({ days: 90 }).then(setOv).finally(() => setLoading(false)); }, []);
  const loadFailures = useCallback(() => { dpApi.intelFailures({ group_by: group, days: 90 }).then((d) => setFailures(d.rows || [])); }, [group]);
  useEffect(() => { loadFailures(); }, [loadFailures]);

  if (loading) return <Spinner />;
  return (
    <div className="space-y-6" data-testid="dp-intel-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testid="dp-intel-events" label="Usage events (90d)" value={ov?.total_usage_events ?? 0} />
        <StatCard testid="dp-intel-failures" label="Failures (90d)" value={ov?.total_failures ?? 0} tone="red" />
        <StatCard label="Top failing part" value={ov?.top_failing_parts?.[0]?.part_sku || '—'} tone="amber" />
        <StatCard label="Worst country" value={ov?.by_country?.[0]?.label || '—'} />
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><TrendingUp size={15} /> Top failing parts</h3>
          {(ov?.top_failing_parts || []).length === 0 ? <p className="text-sm text-slate-400">No failures recorded.</p> : (
            <div className="space-y-2">
              {ov.top_failing_parts.map((p) => (
                <div key={p.part_sku} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-700"><span className="font-mono text-xs text-slate-400">{p.part_sku}</span> {p.part_name}</span>
                  <span className="font-semibold text-red-600 tabular-nums">{p.failures}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <Bars title="Failures by country" data={ov?.by_country || []} />
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <Bars title="Failures by dealer" data={ov?.by_dealer || []} />
        <Bars title="Failures by machine model" data={ov?.by_model || []} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-intel-failures-table">
        <div className="flex items-center gap-1 mb-4 flex-wrap">
          <h3 className="text-sm font-bold text-slate-900 mr-3 flex items-center gap-2"><Globe size={15} /> Global failure intelligence</h3>
          {GROUPS.map((g) => (
            <button key={g.id} data-testid={`dp-intel-group-${g.id}`} onClick={() => setGroup(g.id)}
              className={`px-3 py-1 text-xs font-semibold rounded-full border ${group === g.id ? 'bg-[var(--gx-brand-from)] text-white border-transparent' : 'text-slate-500 border-slate-200 hover:bg-slate-50'}`}>{g.label}</button>
          ))}
        </div>
        {failures.length === 0 ? <p className="text-sm text-slate-400">No failures for this grouping.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100"><th className="py-2">Group</th><th>Failures</th><th>Warranty</th><th>Quality flags</th></tr></thead>
              <tbody>
                {failures.map((r) => (
                  <tr key={r.group} className="border-b border-slate-50">
                    <td className="py-2 text-slate-700">{r.group}</td>
                    <td className="tabular-nums font-semibold">{r.failures}</td>
                    <td className="tabular-nums text-slate-500">{r.warranty}</td>
                    <td className="tabular-nums">{r.quality_flags > 0 ? <span className="text-red-600 font-semibold">{r.quality_flags}</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
