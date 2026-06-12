/**
 * Master Admin — Access Matrix (Iter 246).
 *
 * Live role × capability grid. Two row groups:
 *   1. Backend gates — evaluated server-side by running the REAL guard
 *      functions against synthetic persona users (never drifts).
 *   2. UI capabilities — evaluated in-browser against the same personas
 *      using `can()` from utils/capabilities.js.
 *
 * Personas (and their live headcounts) come from the backend so both
 * halves of the grid share one definition.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Check, Minus, Filter, Loader2, ShieldCheck, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { can, listCapabilities, CAPABILITY_LABELS } from '@/utils/capabilities';

const Cell = ({ value, informational }) => (
  <td className="px-2 py-2 text-center">
    {value ? (
      informational ? (
        <Filter size={14} className="inline text-blue-500" aria-label="Scoped" />
      ) : (
        <Check size={15} className="inline text-emerald-500" aria-label="Allowed" />
      )
    ) : (
      <Minus size={14} className="inline text-slate-300 dark:text-slate-600" aria-label="No access" />
    )}
  </td>
);

const SectionRow = ({ label, span }) => (
  <tr className="bg-slate-50 dark:bg-zinc-800/60">
    <td colSpan={span} className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
      {label}
    </td>
  </tr>
);

export default function AccessMatrixPanel() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await axios.get(`${API}/master-admin/access-matrix`, { headers });
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to load access matrix');
    } finally {
      setLoading(false);
    }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const personas = data?.personas || [];
  const uiCaps = listCapabilities();

  return (
    <div className="space-y-4" data-testid="access-matrix-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-zinc-100 flex items-center gap-2">
            <ShieldCheck size={22} className="text-emerald-500" /> Access matrix
          </h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Who can see and do what — evaluated <strong>live from the permission code</strong> (backend
            guards + <code className="text-xs">capabilities.js</code>), so this grid can never drift from reality.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="access-matrix-refresh">
          <RefreshCw size={14} className="mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1"><Check size={13} className="text-emerald-500" /> Allowed</span>
        <span className="flex items-center gap-1"><Minus size={13} className="text-slate-300" /> No access</span>
        <span className="flex items-center gap-1"><Filter size={13} className="text-blue-500" /> Data scoped (filter, not a privilege)</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-500 text-sm" data-testid="access-matrix-loading">
          <Loader2 size={16} className="mr-2 animate-spin" /> Evaluating permissions…
        </div>
      ) : error ? (
        <div className="text-sm text-rose-600 py-8" data-testid="access-matrix-error">{error}</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <table className="w-full text-sm" data-testid="access-matrix-table">
            <thead>
              <tr className="border-b border-slate-200 dark:border-zinc-800">
                <th className="text-left px-3 py-2.5 font-semibold text-slate-700 dark:text-zinc-200 min-w-[230px]">
                  Capability
                </th>
                {personas.map((p) => (
                  <th key={p.key} className="px-2 py-2.5 text-center font-medium text-slate-600 dark:text-zinc-300 min-w-[88px]" data-testid={`access-matrix-persona-${p.key}`}>
                    <div className="text-xs leading-tight">{p.label}</div>
                    <div className="text-[10px] text-slate-400 font-normal mt-0.5">{p.count} user{p.count === 1 ? '' : 's'}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <SectionRow label="Backend gates · evaluated server-side" span={personas.length + 1} />
              {(data?.gates || []).map((g) => (
                <tr key={g.key} className="border-t border-slate-100 dark:border-zinc-800/60" data-testid={`access-matrix-gate-${g.key}`}>
                  <td className="px-3 py-2">
                    <div className="text-slate-800 dark:text-zinc-200">{g.label}</div>
                    <div className="text-[10px] text-slate-400 font-mono">{g.source}</div>
                  </td>
                  {personas.map((p) => (
                    <Cell key={p.key} value={!!g.access?.[p.key]} informational={g.informational} />
                  ))}
                </tr>
              ))}

              <SectionRow label="UI capabilities · evaluated from capabilities.js" span={personas.length + 1} />
              {uiCaps.map((cap) => (
                <tr key={cap} className="border-t border-slate-100 dark:border-zinc-800/60" data-testid={`access-matrix-cap-${cap}`}>
                  <td className="px-3 py-2">
                    <div className="text-slate-800 dark:text-zinc-200">{CAPABILITY_LABELS[cap] || cap}</div>
                    <div className="text-[10px] text-slate-400 font-mono">can(user, '{cap}')</div>
                  </td>
                  {personas.map((p) => (
                    <Cell key={p.key} value={can(p.user, cap)} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-slate-400">
        Engineer App access is subscription / grant based (Partner Engineer Plan, customer grants,
        or master &amp; pulse admin QA access) and is therefore not a static role gate — see Partners → Engineer access.
      </p>
    </div>
  );
}
