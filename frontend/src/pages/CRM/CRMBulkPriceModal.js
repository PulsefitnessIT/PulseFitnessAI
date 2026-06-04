/**
 * CRM · Master Price List — bulk / single price change (Iter 220 P1).
 * Preview → submit. Applies immediately, queues for approval, or schedules
 * for a future effective date depending on org settings + the date.
 */
import { useState } from 'react';
import axios from 'axios';
import { X, Loader2, Calculator, AlertTriangle, Check, Percent } from 'lucide-react';

export default function CRMBulkPriceModal({ API, headers, c, isDark, categories = [], suppliers = [], onClose, onDone }) {
  const [field, setField] = useState('sell_price');
  const [mode, setMode] = useState('pct');
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('');
  const [supplier, setSupplier] = useState('');
  const [reason, setReason] = useState('');
  const [effective, setEffective] = useState('');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const surface = isDark ? 'var(--color-surface-dark-1)' : '#fff';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const inp = { background: surface2, borderColor: border, color: c.text };

  const payload = () => ({
    field, mode, amount: Number(amount || 0),
    filter: { ...(category ? { category } : {}), ...(supplier ? { supplier } : {}) },
    reason, effective_date: effective ? new Date(effective).toISOString() : '',
  });

  const runPreview = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const r = await axios.post(`${API}/crm/price-list/price-changes/preview`, payload(), { headers: headers() });
      setPreview(r.data.preview);
    } catch (e) { setError(e?.response?.data?.detail || 'Preview failed'); }
    setBusy(false);
  };

  const submit = async () => {
    setBusy(true); setError('');
    try {
      const r = await axios.post(`${API}/crm/price-list/price-changes`, payload(), { headers: headers() });
      setResult(r.data.change);
      onDone?.();
    } catch (e) { setError(e?.response?.data?.detail || 'Submit failed'); }
    setBusy(false);
  };

  const modeLabel = { pct: '% uplift', fixed: 'Fixed +/-', set: 'Set to', margin: 'Set margin %' };

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="bulk-price-modal">
      <div className="w-full max-w-2xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: surface, borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><Calculator size={15} /> Bulk price change</h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="bulk-price-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {error && <div className="text-xs px-3 py-1.5 rounded-md flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="bulk-price-error"><AlertTriangle size={13} />{error}</div>}

          {!result && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Apply to</label>
                  <select value={field} onChange={e => { setField(e.target.value); setPreview(null); }} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-field">
                    <option value="sell_price">Sell price</option>
                    <option value="cost_price">Cost price</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Method</label>
                  <select value={mode} onChange={e => { setMode(e.target.value); setPreview(null); }} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-mode">
                    {Object.entries(modeLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>{mode === 'pct' || mode === 'margin' ? 'Percent' : 'Amount £'}</label>
                  <input type="number" step="0.01" value={amount} onChange={e => { setAmount(e.target.value); setPreview(null); }} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-amount" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Effective (optional)</label>
                  <input type="datetime-local" value={effective} onChange={e => setEffective(e.target.value)} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-effective" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Category filter</label>
                  <select value={category} onChange={e => { setCategory(e.target.value); setPreview(null); }} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-category">
                    <option value="">All categories</option>
                    {categories.map(x => <option key={x} value={x}>{x}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Supplier filter</label>
                  <select value={supplier} onChange={e => { setSupplier(e.target.value); setPreview(null); }} className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-supplier">
                    <option value="">All suppliers</option>
                    {suppliers.map(x => <option key={x} value={x}>{x}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Reason</label>
                <input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Annual supplier cost rise" className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="bulk-price-reason" />
              </div>

              {preview && (
                <div className="rounded-lg border" style={{ borderColor: border }} data-testid="bulk-price-preview">
                  <div className="flex items-center gap-3 px-3 py-2 border-b text-xs" style={{ borderColor: border, color: c.text }}>
                    <span className="font-semibold" data-testid="bulk-price-affected">{preview.affected_count} products affected</span>
                    {preview.warnings?.below_margin > 0 && <span style={{ color: 'var(--color-accent-amber)' }} className="inline-flex items-center gap-1"><Percent size={11} />{preview.warnings.below_margin} below {preview.warnings.margin_threshold}% margin</span>}
                    {preview.warnings?.cost_gt_sell > 0 && <span style={{ color: 'var(--color-danger-alt)' }}>{preview.warnings.cost_gt_sell} cost &gt; sell</span>}
                    {preview.warnings?.negative > 0 && <span style={{ color: 'var(--color-danger-alt)' }}>{preview.warnings.negative} negative</span>}
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead style={{ background: surface2, color: c.textDim }}><tr><th className="text-left px-3 py-1">SKU</th><th className="text-left px-3 py-1">Name</th><th className="text-right px-3 py-1">Old</th><th className="text-right px-3 py-1">New</th></tr></thead>
                      <tbody>
                        {preview.preview.map((r, i) => (
                          <tr key={i} className="border-t" style={{ borderColor: border }}>
                            <td className="px-3 py-1 font-mono" style={{ color: c.textDim }}>{r.sku}</td>
                            <td className="px-3 py-1 truncate" style={{ color: c.text, maxWidth: 200 }}>{r.name}</td>
                            <td className="px-3 py-1 text-right" style={{ color: c.textMuted }}>£{r.old}</td>
                            <td className="px-3 py-1 text-right font-semibold" style={{ color: 'var(--color-success-alt)' }}>£{r.new}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {result && (
            <div className="text-center py-8" data-testid="bulk-price-result">
              <Check size={36} className="mx-auto mb-2" style={{ color: 'var(--color-success-alt)' }} />
              <div className="text-sm font-semibold" style={{ color: c.text }}>
                {result.status === 'applied' && `Applied to ${result.affected_count} products`}
                {result.status === 'pending' && 'Submitted for approval'}
                {result.status === 'scheduled' && `Scheduled for ${new Date(result.effective_date).toLocaleString()}`}
              </div>
              <div className="text-xs mt-1" style={{ color: c.textDim }}>{result.affected_count} products · {result.field} · {result.mode} {result.amount}</div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t" style={{ borderColor: border }}>
          {!result && <button type="button" onClick={runPreview} disabled={busy || !amount} className="text-xs font-semibold px-4 py-1.5 rounded-md border disabled:opacity-50" style={{ borderColor: border, color: c.text }} data-testid="bulk-price-preview-btn">{busy ? <Loader2 size={13} className="animate-spin" /> : 'Preview'}</button>}
          {!result && <button type="button" onClick={submit} disabled={busy || !preview || preview.affected_count === 0} className="text-xs font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="bulk-price-submit">Apply change</button>}
          {result && <button type="button" onClick={() => { onDone?.(); onClose(); }} className="text-xs font-semibold px-4 py-1.5 rounded-md text-white" style={{ background: 'var(--color-info-ios)' }} data-testid="bulk-price-done">Done</button>}
        </div>
      </div>
    </div>
  );
}
