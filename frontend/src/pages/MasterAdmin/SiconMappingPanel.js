/**
 * Master Admin → Sicon → Field mapping reference table.
 *
 * Read-only view of every Pulse Fitness ↔ Sicon field pair, grouped by
 * entity (Case / Contract / Engineer / Customer). Used so admins can
 * audit which Pulse Fitness field flows into which Sicon column for every
 * sync without having to dig in the codebase.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Loader2, ArrowRight, ArrowLeft, ArrowLeftRight, Search } from 'lucide-react';

const DIRECTION_ICON = {
  '→': ArrowRight,
  '←': ArrowLeft,
  '↔': ArrowLeftRight,
};
const DIRECTION_TONE = {
  '→': 'text-sky-600',
  '←': 'text-amber-600',
  '↔': 'text-emerald-600',
};

export default function SiconMappingPanel() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [entityFilter, setEntityFilter] = useState('All');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/sicon/field-mapping`, { headers });
        if (alive) setData(r.data);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [API, headers]);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>;
  if (!data) return null;

  const needle = q.trim().toLowerCase();
  const filtered = data.mappings.filter((row) => {
    if (entityFilter !== 'All' && row.entity !== entityFilter) return false;
    if (!needle) return true;
    return [row.gymaxis_field, row.sicon_field, row.notes, row.entity, row.type]
      .some((v) => (v || '').toLowerCase().includes(needle));
  });

  return (
    <div data-testid="sicon-mapping-panel" className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-400">Sicon integration</div>
          <h2 className="text-xl font-bold text-zinc-900">Field mapping</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            All <strong>{data.total}</strong> field pairs flowing between Pulse Fitness and Sicon.
            Direction: <span className="text-sky-600 font-semibold">→</span> push only,
            <span className="text-amber-600 font-semibold mx-1">←</span> pull only,
            <span className="text-emerald-600 font-semibold ml-1">↔</span> two-way.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            className="px-2 py-1.5 text-xs rounded border border-zinc-200 bg-white"
            data-testid="sicon-mapping-entity-filter"
          >
            <option value="All">All entities ({data.mappings.length})</option>
            {data.entities.map((e) => (
              <option key={e} value={e}>{e} ({data.grouped[e].length})</option>
            ))}
          </select>
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search field, type, note…"
              className="pl-7 pr-3 py-1.5 text-xs rounded border border-zinc-200"
              data-testid="sicon-mapping-search"
            />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-zinc-50 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-3 py-2 text-left">Entity</th>
              <th className="px-3 py-2 text-left">Pulse Fitness field</th>
              <th className="px-3 py-2 text-center">Dir</th>
              <th className="px-3 py-2 text-left">Sicon field</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Notes</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-10 text-center text-zinc-400" data-testid="sicon-mapping-empty">
                  No fields match.
                </td>
              </tr>
            ) : filtered.map((row, idx) => {
              const Dir = DIRECTION_ICON[row.direction] || ArrowRight;
              return (
                <tr key={idx} className="border-t border-zinc-100 hover:bg-zinc-50/50" data-testid={`sicon-mapping-row-${idx}`}>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-zinc-100 text-zinc-700">{row.entity}</span>
                  </td>
                  <td className="px-3 py-2 font-mono text-zinc-900">{row.gymaxis_field}</td>
                  <td className={`px-3 py-2 text-center ${DIRECTION_TONE[row.direction] || 'text-zinc-500'}`}>
                    <Dir size={14} className="inline" />
                  </td>
                  <td className="px-3 py-2 font-mono text-zinc-900">{row.sicon_field}</td>
                  <td className="px-3 py-2 text-zinc-500">{row.type}</td>
                  <td className="px-3 py-2 text-zinc-500">{row.notes || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="text-[11px] text-zinc-400 text-right">
        Showing <strong>{filtered.length}</strong> of {data.total} mappings.
      </div>
    </div>
  );
}
