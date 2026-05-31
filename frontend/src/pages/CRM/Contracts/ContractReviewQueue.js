/**
 * Iter 220e5 — Contract Review Queue (coordinator surface).
 *
 * Lists engineer-submitted contract feedback for the org. Allows
 * coordinators to accept / reject / mark-reviewed and drop an
 * internal note. Accepting a renewal-relevant row also fires a
 * renewal task activity on the contract (backend side).
 */
import { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import {
  AlertTriangle, CheckCircle, X, MessageSquare, Wrench,
  ChevronRight, RefreshCw,
} from 'lucide-react';

const KIND_LABELS = {
  asset_condition:       'Asset condition',
  exclusion_recommended: 'Recommend exclusion',
  upgrade_recommended:   'Recommend upgrade',
  renewal_review:        'Renewal review',
  repeated_fault:        'Repeated fault',
  capex_replacement:     'CAPEX replacement',
  upsell_opportunity:    'Upsell opportunity',
  contract_dispute:      'Contract dispute',
  chargeable_flag:       'Chargeable flag',
  pricing_review:        'Pricing review',
  general_note:          'General note',
};

const SEVERITY_COLOR = {
  low: 'var(--color-info-ios)',
  medium: 'var(--color-accent-amber)',
  high: 'var(--color-danger)',
};

export function ContractReviewQueue({ API, headers, c, isDark, onOpenContract }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('open');
  const [filterKind, setFilterKind] = useState('');

  const reload = useMemo(() => () => {
    setLoading(true);
    return axios.get(`${API}/crm/v2/contracts/feedback-queue?status=${status}`, { headers: headers() })
      .then(r => setRows(r.data.feedback || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [API, headers, status]);

  useEffect(() => { reload(); }, [reload]);

  const act = async (row, action) => {
    let note = '';
    if (action === 'accept' || action === 'reject') {
      note = window.prompt(`Optional internal note for ${action}:`, '') || '';
    }
    try {
      await axios.post(`${API}/crm/v2/contracts/feedback/${row.id}/action`,
        { action, note }, { headers: headers() });
      reload();
    } catch (e) { alert(e?.response?.data?.detail || 'Failed'); }
  };

  const filtered = filterKind ? rows.filter(r => r.kind === filterKind) : rows;
  const kinds = [...new Set(rows.map(r => r.kind))];

  if (loading) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div data-testid="contract-review-queue">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold" style={{ color: c.text }}>Contract Review Queue</p>
          <p className="text-[11px]" style={{ color: c.textDim }}>
            Engineer feedback from the field — accept to drop a renewal task on the contract.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={status} onChange={e => setStatus(e.target.value)} data-testid="review-status-filter"
                  className="px-2 py-1 rounded border text-xs"
                  style={{ borderColor: c.border, background: 'transparent', color: c.text }}>
            <option value="open">Open</option>
            <option value="actioned">Actioned</option>
            <option value="rejected">Rejected</option>
            <option value="reviewed">Reviewed</option>
            <option value="all">All</option>
          </select>
          {kinds.length > 1 && (
            <select value={filterKind} onChange={e => setFilterKind(e.target.value)} data-testid="review-kind-filter"
                    className="px-2 py-1 rounded border text-xs"
                    style={{ borderColor: c.border, background: 'transparent', color: c.text }}>
              <option value="">All kinds</option>
              {kinds.map(k => <option key={k} value={k}>{KIND_LABELS[k] || k}</option>)}
            </select>
          )}
          <button onClick={reload} data-testid="review-refresh-btn"
                  className="p-1.5 rounded hover:opacity-70" style={{ color: c.textDim }}>
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-12 text-xs" style={{ color: c.textDim }} data-testid="review-empty">
          <CheckCircle size={28} className="mx-auto mb-2 text-emerald-500/40" />
          Nothing in the queue. Engineers can submit contract feedback from any job.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(r => (
            <div key={r.id} className="p-3 rounded-xl border" data-testid={`review-row-${r.id}`}
                 style={{ background: isDark ? '#111' : '#fff',
                          borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <div className="flex items-start gap-3">
                <div className="shrink-0 pt-0.5">
                  <AlertTriangle size={14} style={{ color: SEVERITY_COLOR[r.severity] || 'var(--color-info-ios)' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded"
                          style={{ background: `${SEVERITY_COLOR[r.severity] || '#666'}15`,
                                   color: SEVERITY_COLOR[r.severity] || c.textDim }}>
                      {KIND_LABELS[r.kind] || r.kind}
                    </span>
                    {r.company_name && (
                      <span className="text-[11px] font-semibold" style={{ color: c.text }}>
                        {r.company_name}
                      </span>
                    )}
                    {r.site_name && (
                      <span className="text-[10px]" style={{ color: c.textDim }}>· {r.site_name}</span>
                    )}
                    {r.contract_number && (
                      <button onClick={() => onOpenContract?.(r.contract_id)}
                              className="text-[10px] font-semibold flex items-center gap-0.5"
                              style={{ color: 'var(--color-info-ios)' }}
                              data-testid={`review-open-contract-${r.id}`}>
                        {r.contract_number} <ChevronRight size={9} />
                      </button>
                    )}
                  </div>
                  <p className="text-xs mb-1" style={{ color: c.text }}>{r.body}</p>
                  <p className="text-[10px]" style={{ color: c.textDim }}>
                    <Wrench size={9} className="inline" /> {r.engineer_name || 'Engineer'} ·{' '}
                    {r.case_reference || r.case_id} · {new Date(r.created_at).toLocaleDateString('en-GB')}
                  </p>
                  {(r.internal_notes || []).length > 0 && (
                    <details className="mt-1 text-[10px]" style={{ color: c.textDim }}>
                      <summary className="cursor-pointer font-semibold">{r.internal_notes.length} internal note(s)</summary>
                      <div className="mt-1 space-y-1">
                        {r.internal_notes.map((n, i) => (
                          <div key={i} className="pl-2 border-l" style={{ borderColor: c.border }}>
                            <p className="text-[10px]" style={{ color: c.text }}>{n.note}</p>
                            <p className="text-[9px]">{n.by} · {new Date(n.at).toLocaleString('en-GB')} · {n.action}</p>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
                {r.status === 'open' && (
                  <div className="flex flex-col gap-1 shrink-0">
                    <button onClick={() => act(r, 'accept')} data-testid={`review-accept-${r.id}`}
                            className="px-2 py-1 text-[10px] font-semibold rounded bg-emerald-600 text-white">Accept</button>
                    <button onClick={() => act(r, 'reject')} data-testid={`review-reject-${r.id}`}
                            className="px-2 py-1 text-[10px] font-semibold rounded bg-rose-500/15 text-rose-700">Reject</button>
                    <button onClick={() => act(r, 'note')} data-testid={`review-note-${r.id}`}
                            className="px-2 py-1 text-[10px] font-semibold rounded"
                            style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }}>
                      <MessageSquare size={9} className="inline mr-0.5" />Note
                    </button>
                  </div>
                )}
                {r.status !== 'open' && (
                  <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded shrink-0"
                        style={{ background: r.status === 'actioned' ? 'var(--color-success-alt)15' : '#94a3b815',
                                 color: r.status === 'actioned' ? 'var(--color-success-alt)' : c.textDim }}>
                    {r.status}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

ContractReviewQueue.displayName = 'ContractReviewQueue';

// Workspace mode hook — single source of truth for "is this org solo
// or enterprise". The Contracts page + the wizard read this to hide
// approval UI / region filters / margin review for solo accounts.
export function useWorkspaceMode(API, headers) {
  const [mode, setMode] = useState({ mode: 'enterprise', capabilities: {} });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/crm/v2/contracts/workspace`, { headers: headers() })
      .then(r => { if (alive && r.data) setMode(r.data); })
      .catch(() => { /* stay on the safe default */ })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [API, headers]);
  return { ...mode, loading };
}
