import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Plus, X, Trash2, ReceiptText, Wallet, RotateCcw, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { useAuth } from '@/App';

/* Staged invoicing panel for a CPQ v2 quote — deposit / interim / final,
   running balance and credit notes. Renders inside QuoteDetail. */
export const QuoteInvoicingPanel = ({ quoteId, API, headers, fmt, c, isDark }) => {
  const { user } = useAuth();
  const canManage = !!(user && (user.is_master_admin || user.is_pulse_admin
    || ['owner', 'admin', 'manager'].includes((user.role || '').toLowerCase())));
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState(false);
  const [draftStages, setDraftStages] = useState([]);
  const [payFor, setPayFor] = useState(null);   // stage
  const [payAmt, setPayAmt] = useState('');
  const [cnFor, setCnFor] = useState(null);      // stage
  const [cnAmt, setCnAmt] = useState('');
  const [cnReason, setCnReason] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/v2/quotes/${quoteId}/invoicing`, { headers: headers() });
      setData(r.data);
    } catch (e) { console.error(e); }
  }, [API, headers, quoteId]);

  useEffect(() => { load(); }, [load]);

  const post = async (url, body, key) => {
    setBusy(key);
    try {
      const r = await axios.post(`${API}${url}`, body || {}, { headers: headers() });
      setData(r.data);
      return r.data;
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Action failed');
      throw e;
    } finally { setBusy(''); }
  };

  const applyAuto = (deposit, interim, final) => post(
    `/crm/v2/quotes/${quoteId}/schedule/auto`,
    { deposit_percent: deposit, interim_percent: interim, final_percent: final },
    `auto-${deposit}-${final}`,
  ).then(() => notify.success('Schedule created')).catch(() => {});

  const beginEdit = () => {
    setDraftStages((data?.stages || []).map(s => ({
      id: s.id, kind: s.kind, basis: s.basis || 'percent',
      percent: s.percent || 0, amount: s.amount || 0, due_date: s.due_date || '',
      locked: ['invoiced', 'part_paid', 'paid', 'credited'].includes(s.status),
    })));
    setEditing(true);
  };
  const addDraft = () => setDraftStages(d => [...d, { kind: 'interim', basis: 'percent', percent: 0, amount: 0, due_date: '' }]);
  const updDraft = (i, f, v) => setDraftStages(d => d.map((s, idx) => idx === i ? { ...s, [f]: (f === 'kind' || f === 'basis' || f === 'due_date') ? v : (parseFloat(v) || 0) } : s));
  const rmDraft = (i) => setDraftStages(d => d.filter((_, idx) => idx !== i));
  const saveSchedule = async () => {
    setBusy('save');
    try {
      const r = await axios.put(`${API}/crm/v2/quotes/${quoteId}/schedule`, { stages: draftStages }, { headers: headers() });
      setData(r.data); setEditing(false); notify.success('Schedule saved');
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not save schedule'); }
    setBusy('');
  };

  const doInvoice = (s) => post(`/crm/v2/quotes/${quoteId}/stages/${s.id}/invoice`, { due_date: s.due_date || undefined }, `inv-${s.id}`).then(() => notify.success('Invoice raised')).catch(() => {});
  const submitPay = async () => {
    await post(`/crm/v2/quotes/${quoteId}/stages/${payFor.id}/pay`, payAmt ? { amount: parseFloat(payAmt) } : {}, `pay-${payFor.id}`).then(() => notify.success('Payment recorded')).catch(() => {});
    setPayFor(null); setPayAmt('');
  };
  const submitCn = async () => {
    await post(`/crm/v2/quotes/${quoteId}/stages/${cnFor.id}/credit-note`, { amount: cnAmt ? parseFloat(cnAmt) : undefined, reason: cnReason }, `cn-${cnFor.id}`).then(() => notify.success('Credit note raised')).catch(() => {});
    setCnFor(null); setCnAmt(''); setCnReason('');
  };

  if (!data) return null;
  const s = data.summary;
  const panel = isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)';
  const bd = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const STATUS = {
    pending: { t: 'Not invoiced', col: c.textMuted },
    invoiced: { t: 'Invoiced', col: 'var(--color-info-ios)' },
    part_paid: { t: 'Part paid', col: 'var(--color-accent-amber)' },
    paid: { t: 'Paid', col: 'var(--color-success-alt)' },
    credited: { t: 'Credited', col: 'var(--color-danger-alt)' },
  };
  const KIND = { deposit: 'Deposit', interim: 'Interim payment', final: 'Final balance' };

  return (
    <div className="mt-6" data-testid="quote-invoicing-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: c.text }}>
          <ReceiptText size={15} /> Payment schedule &amp; invoicing
        </h3>
        {canManage && !editing && (
          <button onClick={beginEdit} className="text-xs px-2 py-1 rounded border" style={{ borderColor: bd, color: 'var(--color-info-ios)' }} data-testid="invoicing-schedule-edit">
            {data.stages.length ? 'Edit schedule' : 'Set up schedule'}
          </button>
        )}
      </div>

      {/* Running balance */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { l: 'Deal total', v: fmt(s.total), testid: 'invoicing-summary-total' },
          { l: 'Invoiced', v: fmt(s.invoiced), testid: 'invoicing-summary-invoiced' },
          { l: 'Paid', v: fmt(s.paid), col: 'var(--color-success-alt)', testid: 'invoicing-summary-paid' },
          { l: 'Balance due', v: fmt(s.balance), col: s.balance > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)', bold: true, testid: 'invoicing-summary-balance' },
        ].map(k => (
          <div key={k.l} className="p-3 rounded-lg border" style={{ background: panel, borderColor: bd }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{k.l}</p>
            <p className={`text-base ${k.bold ? 'font-bold' : 'font-medium'}`} style={{ color: k.col || c.text }} data-testid={k.testid}>{k.v}</p>
          </div>
        ))}
      </div>
      {s.credited > 0 && (
        <p className="text-xs mb-3" style={{ color: 'var(--color-danger-alt)' }} data-testid="invoicing-summary-credited">Credit notes issued: {fmt(s.credited)}</p>
      )}

      {/* Empty state — quick presets */}
      {!editing && data.stages.length === 0 && (
        <div className="p-4 rounded-lg border text-center" style={{ background: panel, borderColor: bd }} data-testid="invoicing-empty">
          <p className="text-sm mb-3" style={{ color: c.textMuted }}>No payment schedule yet. Split this deal into staged payments:</p>
          {canManage && (
            <div className="flex flex-wrap gap-2 justify-center">
              <button onClick={() => applyAuto(25, 0, 75)} disabled={!!busy} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: bd, color: c.text }} data-testid="invoicing-auto-25-75">25% deposit / 75% balance</button>
              <button onClick={() => applyAuto(50, 0, 50)} disabled={!!busy} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: bd, color: c.text }} data-testid="invoicing-auto-50-50">50% / 50%</button>
              <button onClick={() => applyAuto(33.34, 33.33, 33.33)} disabled={!!busy} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: bd, color: c.text }} data-testid="invoicing-auto-thirds">Thirds (deposit / interim / final)</button>
              <button onClick={beginEdit} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: bd, color: 'var(--color-info-ios)' }} data-testid="invoicing-custom">Custom…</button>
            </div>
          )}
        </div>
      )}

      {/* Schedule editor */}
      {editing && (() => {
        const dealTotal = data.summary.total;
        const draftTotal = draftStages.reduce((sum, st) => sum + (st.basis === 'percent' ? dealTotal * (Number(st.percent) || 0) / 100 : (Number(st.amount) || 0)), 0);
        const over = draftTotal > dealTotal + 0.01;
        return (
        <div className="p-3 rounded-lg border mb-3" style={{ background: panel, borderColor: bd }} data-testid="invoicing-schedule-editor">
          {draftStages.map((st, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center mb-2" data-testid={`invoicing-draft-${i}`}>
              <select value={st.kind} onChange={e => updDraft(i, 'kind', e.target.value)} disabled={st.locked} className="col-span-3 px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }}>
                <option value="deposit">Deposit</option>
                <option value="interim">Interim</option>
                <option value="final">Final balance</option>
              </select>
              <select value={st.basis} onChange={e => updDraft(i, 'basis', e.target.value)} disabled={st.locked} className="col-span-2 px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }}>
                <option value="percent">%</option>
                <option value="amount">£</option>
              </select>
              <input type="number" min="0" step="0.01" value={st.basis === 'percent' ? st.percent : st.amount} onChange={e => updDraft(i, st.basis === 'percent' ? 'percent' : 'amount', e.target.value)} disabled={st.locked} className="col-span-3 px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid={`invoicing-draft-value-${i}`} />
              <input type="date" value={st.due_date} onChange={e => updDraft(i, 'due_date', e.target.value)} className="col-span-3 px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} />
              <div className="col-span-1 flex justify-center">
                {!st.locked && <button onClick={() => rmDraft(i)} style={{ color: 'var(--color-danger-alt)' }}><Trash2 size={14} /></button>}
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between mt-2">
            <button onClick={addDraft} className="text-xs" style={{ color: 'var(--color-info-ios)' }} data-testid="invoicing-add-stage"><Plus size={12} className="inline" /> Add stage</button>
            <div className="flex items-center gap-3">
              <span className="text-[11px]" style={{ color: over ? 'var(--color-danger-alt)' : c.textDim }} data-testid="invoicing-draft-total">
                Scheduled {fmt(draftTotal)} / {fmt(dealTotal)}{over ? ' — exceeds deal total' : ''}
              </span>
              <button onClick={() => setEditing(false)} className="text-xs px-3 py-1.5" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={saveSchedule} disabled={busy === 'save' || over} className="text-xs px-3 py-1.5 rounded-md bg-[var(--color-info-ios)] text-white disabled:opacity-50" data-testid="invoicing-schedule-save">{busy === 'save' ? 'Saving…' : 'Save schedule'}</button>
            </div>
          </div>
        </div>
        );
      })()}

      {/* Stage rows */}
      {!editing && data.stages.length > 0 && (
        <div className="space-y-2">
          {data.stages.map(st => {
            const stat = STATUS[st.status] || STATUS.pending;
            return (
              <div key={st.id} className="flex items-center gap-3 p-3 rounded-lg border flex-wrap" style={{ background: panel, borderColor: bd }} data-testid={`invoicing-stage-${st.id}`}>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{st.label || KIND[st.kind]} {st.invoice_number && <span className="text-[11px] font-normal" style={{ color: c.textDim }}>· {st.invoice_number}</span>}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>
                    {fmt(st.amount)}{st.due_date ? ` · due ${st.due_date}` : ''}
                    {st.paid_amount > 0 && ` · paid ${fmt(st.paid_amount)}`}
                    {st.credited_amount > 0 && ` · credited ${fmt(st.credited_amount)}`}
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background: `${stat.col}22`, color: stat.col }} data-testid={`invoicing-stage-status-${st.id}`}>{stat.t}</span>
                {canManage && (
                  <div className="flex items-center gap-1.5">
                    {st.status === 'pending' && (
                      <button onClick={() => doInvoice(st)} disabled={busy === `inv-${st.id}`} className="text-xs px-2.5 py-1 rounded-md border" style={{ borderColor: bd, color: 'var(--color-info-ios)' }} data-testid={`invoicing-stage-invoice-${st.id}`}>
                        {busy === `inv-${st.id}` ? <Loader2 size={12} className="animate-spin" /> : 'Raise invoice'}
                      </button>
                    )}
                    {['invoiced', 'part_paid'].includes(st.status) && st.outstanding > 0 && (
                      <button onClick={() => { setPayFor(st); setPayAmt(String(st.outstanding)); }} className="text-xs px-2.5 py-1 rounded-md border inline-flex items-center gap-1" style={{ borderColor: bd, color: 'var(--color-success-alt)' }} data-testid={`invoicing-stage-pay-${st.id}`}><Wallet size={12} /> Record payment</button>
                    )}
                    {['invoiced', 'part_paid', 'paid'].includes(st.status) && st.outstanding + st.paid_amount > 0 && (
                      <button onClick={() => { setCnFor(st); setCnAmt(String(st.outstanding > 0 ? st.outstanding : st.amount)); }} className="text-xs px-2.5 py-1 rounded-md border inline-flex items-center gap-1" style={{ borderColor: bd, color: 'var(--color-danger-alt)' }} data-testid={`invoicing-stage-credit-${st.id}`}><RotateCcw size={12} /> Credit note</button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Pay dialog */}
      {payFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setPayFor(null)}>
          <div className="w-full max-w-sm rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="invoicing-pay-dialog">
            <div className="flex items-center justify-between mb-3"><h4 className="font-semibold" style={{ color: c.text }}>Record payment</h4><button onClick={() => setPayFor(null)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <label className="text-xs" style={{ color: c.textDim }}>Amount ({data.currency})</label>
            <input type="number" min="0" step="0.01" value={payAmt} onChange={e => setPayAmt(e.target.value)} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="invoicing-pay-amount" />
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setPayFor(null)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitPay} disabled={!!busy} className="px-3 py-2 text-sm rounded-md bg-[var(--color-success-alt)] text-white" data-testid="invoicing-pay-submit">Record</button>
            </div>
          </div>
        </div>
      )}

      {/* Credit note dialog */}
      {cnFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setCnFor(null)}>
          <div className="w-full max-w-sm rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="invoicing-credit-dialog">
            <div className="flex items-center justify-between mb-3"><h4 className="font-semibold" style={{ color: c.text }}>Raise credit note</h4><button onClick={() => setCnFor(null)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <label className="text-xs" style={{ color: c.textDim }}>Amount ({data.currency})</label>
            <input type="number" min="0" step="0.01" value={cnAmt} onChange={e => setCnAmt(e.target.value)} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="invoicing-credit-amount" />
            <label className="text-xs mt-3 block" style={{ color: c.textDim }}>Reason</label>
            <input value={cnReason} onChange={e => setCnReason(e.target.value)} placeholder="e.g. goodwill / returned item" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="invoicing-credit-reason" />
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setCnFor(null)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitCn} disabled={!!busy} className="px-3 py-2 text-sm rounded-md bg-[var(--color-danger-alt)] text-white" data-testid="invoicing-credit-submit">Issue credit note</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuoteInvoicingPanel;
