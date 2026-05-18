/**
 * Master Admin — Client Errors diagnostics.
 *
 * Iter 216h210 — paired with the Login Events timeline so the
 * security/QA team has a single page that answers "why did this
 * stakeholder's session break". Wraps `client_errors` collection
 * which is populated by `<ModalErrorBoundary>` (see
 * `/app/frontend/src/components/shared/ModalErrorBoundary.jsx`).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import {
  Loader2, RefreshCw, AlertOctagon, ChevronDown, ChevronRight, Bug, Search,
} from 'lucide-react';
import EmptyState from '@/components/shared/EmptyState';

export default function ClientErrorsPanel() {
  const { API } = useAuth();
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }),
    [],
  );
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [labelFilter, setLabelFilter] = useState('');
  const [expanded, setExpanded] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (labelFilter.trim()) params.set('label', labelFilter.trim());
      const { data: payload } = await axios.get(
        `${API}/master-admin/client-errors?${params}`, { headers });
      setData(payload);
    } catch (e) {
      notify.error('Failed to load client errors');
    } finally {
      setLoading(false);
    }
  }, [API, headers, labelFilter]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }

  const errors = data?.errors || [];
  const byLabel = data?.by_label || [];

  return (
    <div data-testid="client-errors-panel" className="space-y-5">
      {/* Summary tiles by label */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-zinc-500 mb-3">
          <Bug size={13} /> Errors grouped by dialog · last {errors.length}
        </div>
        {byLabel.length === 0 ? (
          <p className="text-sm text-zinc-500">No errors captured. Healthy.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {byLabel.map(({ label, count }) => (
              <button
                key={label}
                type="button"
                onClick={() => setLabelFilter(label)}
                className="text-left rounded-lg border border-rose-200 bg-rose-50 hover:bg-rose-100 transition p-3"
                data-testid={`client-errors-tile-${label.replace(/\s+/g, '-').toLowerCase()}`}
              >
                <div className="text-[10px] font-bold uppercase tracking-wider text-rose-600 truncate">
                  {label}
                </div>
                <div className="text-2xl font-extrabold text-rose-700 mt-1">{count}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="search"
            value={labelFilter}
            onChange={(e) => setLabelFilter(e.target.value)}
            placeholder="Filter by dialog label (e.g. Class Builder)…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded border border-zinc-200 bg-white"
            data-testid="client-errors-label-filter"
          />
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-zinc-200 bg-white"
          data-testid="client-errors-refresh"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Error timeline */}
      <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-100 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
          Recent crashes · {errors.length}
        </div>
        {errors.length === 0 ? (
          <EmptyState
            icon={AlertOctagon}
            title="No client crashes recorded"
            hint="ModalErrorBoundary captures every React render error in wrapped modals (Class Builder, Plan Editor, Add Member). If a user reports a 'crash', the trace lands here automatically."
            testId="client-errors-empty"
          />
        ) : (
          <ol className="divide-y divide-zinc-100">
            {errors.map((e) => {
              const open = expanded[e.id];
              return (
                <li key={e.id} data-testid={`client-error-row-${e.id}`}>
                  <button
                    type="button"
                    onClick={() => setExpanded((s) => ({ ...s, [e.id]: !s[e.id] }))}
                    className="w-full text-left px-4 py-3 hover:bg-rose-50/50 transition flex items-start gap-3"
                  >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border bg-rose-500/10 text-rose-600 border-rose-500/30">
                      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-zinc-900 flex items-center gap-2 flex-wrap">
                        <span className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border bg-rose-500/10 text-rose-700 border-rose-500/30">
                          {e.label || 'unknown'}
                        </span>
                        <span className="truncate">{e.message || 'no message'}</span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5 font-mono truncate">
                        {(e.server_ts || '').slice(0, 19).replace('T', ' ')}
                        {e.user_id && <span> · user {e.user_id.slice(0, 8)}</span>}
                        {e.organization_id && <span> · org {e.organization_id.slice(0, 8)}</span>}
                        {e.url && <span className="ml-2 truncate">{e.url.slice(0, 80)}</span>}
                      </div>
                    </div>
                  </button>
                  {open && (
                    <div className="px-4 pb-4 pl-15 ml-11 space-y-3 text-xs">
                      {e.user_agent && (
                        <div>
                          <div className="font-semibold text-zinc-700 mb-1">User-Agent</div>
                          <code className="block text-[11px] bg-zinc-100 rounded p-2 break-all">
                            {e.user_agent}
                          </code>
                        </div>
                      )}
                      {e.stack && (
                        <div>
                          <div className="font-semibold text-zinc-700 mb-1">JS Stack</div>
                          <pre className="text-[11px] bg-zinc-100 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">{e.stack}</pre>
                        </div>
                      )}
                      {e.component_stack && (
                        <div>
                          <div className="font-semibold text-zinc-700 mb-1">React Component Stack</div>
                          <pre className="text-[11px] bg-zinc-100 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">{e.component_stack}</pre>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
