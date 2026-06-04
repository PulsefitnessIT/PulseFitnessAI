/**
 * CRM · Master Price List — price changes, approvals & settings (Iter 220 P1).
 * Owners/admins toggle the approval gate, and approve/reject pending changes.
 * Requesters can cancel their pending/scheduled changes.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Check, Ban, Clock, ShieldCheck } from 'lucide-react';

const STATUS = {
  applied: 'var(--color-success-alt)', pending: 'var(--color-accent-amber)',
  scheduled: 'var(--color-info-ios)', rejected: 'var(--color-danger-alt)', cancelled: 'var(--color-text-dim)',
};

export default function CRMPriceChangesModal({ API, headers, c, isDark, onClose, onChanged }) {
  const [changes, setChanges] = useState([]);
  const [isApprover, setIsApprover] = useState(false);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const surface = isDark ? 'var(--color-surface-dark-1)' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ch, st] = await Promise.all([
        axios.get(`${API}/crm/price-list/price-changes`, { headers: headers() }),
        axios.get(`${API}/crm/price-list/settings`, { headers: headers() }),
      ]);
      setChanges(ch.data.changes || []);
      setIsApprover(ch.data.is_approver);
      setSettings(st.data);
    } catch (e) { /* silent */ }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const toggleApproval = async () => {
    setBusy('settings'); setError('');
    try {
      const r = await axios.put(`${API}/crm/price-list/settings`, { require_approval: !settings.require_approval }, { headers: headers() });
      setSettings(r.data);
    } catch (e) { setError(e?.response?.data?.detail || 'Failed'); }
    setBusy('');
  };

  const act = async (id, action, comment = '') => {
    setBusy(`${action}-${id}`); setError('');
    try {
      await axios.post(`${API}/crm/price-list/price-changes/${id}/${action}`, comment ? { comment } : {}, { headers: headers() });
      await load(); onChanged?.();
    } catch (e) { setError(e?.response?.data?.detail || 'Failed'); }
    setBusy('');
  };

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="price-changes-modal">
      <div className="w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: surface, borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><Clock size={15} /> Price changes & approvals</h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="changes-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }}>{error}</div>}

          {/* Approval toggle */}
          {settings && (
            <div className="flex items-center justify-between rounded-lg border px-3 py-2.5" style={{ borderColor: border }} data-testid="changes-settings">
              <div className="flex items-center gap-2 text-xs" style={{ color: c.text }}>
                <ShieldCheck size={14} style={{ color: settings.require_approval ? 'var(--color-success-alt)' : c.textDim }} />
                <div>
                  <div className="font-semibold">Require approval for price changes</div>
                  <div style={{ color: c.textDim }}>When on, managers' changes wait for an owner/admin to approve.</div>
                </div>
              </div>
              <button type="button" disabled={!isApprover || busy === 'settings'} onClick={toggleApproval} className="relative w-11 h-6 rounded-full transition-colors disabled:opacity-40" style={{ background: settings.require_approval ? 'var(--color-success-alt)' : c.textDim }} data-testid="changes-approval-toggle">
                <span className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all" style={{ left: settings.require_approval ? '22px' : '2px' }} />
              </button>
            </div>
          )}

          {loading ? <div className="py-6 text-center"><Loader2 size={18} className="animate-spin mx-auto" /></div> : (
            <table className="w-full text-xs" data-testid="changes-table">
              <thead style={{ color: c.textDim }}><tr><th className="text-left px-2 py-1">Change</th><th className="text-left px-2 py-1">Status</th><th className="text-right px-2 py-1">Affected</th><th className="text-left px-2 py-1">By</th><th className="px-2 py-1"></th></tr></thead>
              <tbody>
                {changes.map(ch => (
                  <tr key={ch.id} className="border-t align-top" style={{ borderColor: border }}>
                    <td className="px-2 py-1.5" style={{ color: c.text }}>
                      {ch.field?.replace('_', ' ')} · {ch.mode} {ch.amount}{(ch.mode === 'pct' || ch.mode === 'margin') ? '%' : ''}
                      {ch.reason && <div style={{ color: c.textDim }}>{ch.reason}</div>}
                      {ch.effective_date && <div style={{ color: 'var(--color-info-ios)' }}>eff {new Date(ch.effective_date).toLocaleString()}</div>}
                    </td>
                    <td className="px-2 py-1.5"><span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase" style={{ background: `${STATUS[ch.status] || c.textDim}22`, color: STATUS[ch.status] || c.textDim }}>{ch.status}</span></td>
                    <td className="px-2 py-1.5 text-right" style={{ color: c.textMuted }}>{ch.affected_count}</td>
                    <td className="px-2 py-1.5" style={{ color: c.textDim }}>{ch.requested_by_name}{ch.approved_by_name && ch.approved_by_name !== ch.requested_by_name ? ` → ${ch.approved_by_name}` : ''}</td>
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      {ch.status === 'pending' && isApprover && (
                        <>
                          <button type="button" onClick={() => act(ch.id, 'approve')} disabled={!!busy} className="text-[11px] mr-2 inline-flex items-center gap-0.5" style={{ color: 'var(--color-success-alt)' }} data-testid={`change-approve-${ch.id}`}>{busy === `approve-${ch.id}` ? <Loader2 size={10} className="animate-spin" /> : <Check size={11} />}Approve</button>
                          <button type="button" onClick={() => act(ch.id, 'reject', window.prompt('Reason for rejection?') || '')} disabled={!!busy} className="text-[11px] inline-flex items-center gap-0.5" style={{ color: 'var(--color-danger-alt)' }} data-testid={`change-reject-${ch.id}`}><Ban size={11} />Reject</button>
                        </>
                      )}
                      {(ch.status === 'pending' || ch.status === 'scheduled') && (
                        <button type="button" onClick={() => act(ch.id, 'cancel')} disabled={!!busy} className="text-[11px] ml-2 underline" style={{ color: c.textDim }} data-testid={`change-cancel-${ch.id}`}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
                {changes.length === 0 && <tr><td colSpan={5} className="px-2 py-4 text-center" style={{ color: c.textDim }}>No price changes yet.</td></tr>}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
