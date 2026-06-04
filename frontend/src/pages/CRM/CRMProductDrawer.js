/**
 * CRM · Master Price List — product detail drawer (Phase 1).
 *
 * Shows the full product record incl. extended catalogue fields, the
 * "Additional Imported Data" (every preserved unmapped cell) and the
 * spreadsheet provenance (source sheet / row / import batch). Editors
 * can edit; everyone else sees a read-only view.
 */
import { useState } from 'react';
import axios from 'axios';
import { X, Save, Loader2, FileSpreadsheet, Archive, RotateCcw, Sparkles, Check } from 'lucide-react';

export default function CRMProductDrawer({ API, headers, c, isDark, product, canEdit, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: product.name || '', sku: product.sku || '', category: product.category || '',
    cost_price: String(product.cost_price ?? ''), sell_price: String(product.sell_price ?? ''),
    tax_rate: String(product.tax_rate ?? '20'), supplier_name: product.supplier_name || '',
    sage_code: product.sage_code || '', manufacturer: product.manufacturer || '',
    model: product.model || '', description: product.description || '',
    internal_notes: product.internal_notes || '', customer_notes: product.customer_notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState(null);
  const [aiError, setAiError] = useState('');

  const surface = isDark ? 'var(--color-surface-dark-1)' : '#fff';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';

  const save = async () => {
    setSaving(true); setError('');
    try {
      await axios.patch(`${API}/crm/products/${product.id}`, {
        ...form, cost_price: Number(form.cost_price || 0), sell_price: Number(form.sell_price || 0), tax_rate: Number(form.tax_rate || 0),
      }, { headers: headers() });
      onSaved?.();
      onClose();
    } catch (err) { setError(err?.response?.data?.detail || 'Save failed'); }
    setSaving(false);
  };

  const toggleArchive = async () => {
    setSaving(true); setError('');
    try {
      if (product.active === false) await axios.post(`${API}/crm/products/${product.id}/restore`, {}, { headers: headers() });
      else await axios.delete(`${API}/crm/products/${product.id}`, { headers: headers() });
      onSaved?.();
      onClose();
    } catch (err) { setError(err?.response?.data?.detail || 'Failed'); }
    setSaving(false);
  };

  const aiClean = async () => {
    setAiBusy(true); setAiError(''); setAiSuggestion(null);
    try {
      const r = await axios.post(`${API}/crm/products/${product.id}/ai-clean-description`,
        { description: form.description }, { headers: headers() });
      setAiSuggestion(r.data.suggestion || '');
    } catch (err) {
      setAiError(err?.response?.data?.detail || 'AI is unavailable — please try again.');
    }
    setAiBusy(false);
  };

  const fld = (key, label, type = 'text') => (
    <div>
      <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{label}</label>
      <input type={type} step={type === 'number' ? '0.01' : undefined} value={form[key]} disabled={!canEdit}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        className="w-full mt-1 px-3 py-1.5 text-sm rounded-md border disabled:opacity-70"
        style={{ background: surface2, borderColor: border, color: c.text }}
        data-testid={`product-drawer-${key}`} />
    </div>
  );

  return (
    <div className="fixed inset-0 z-[260] flex justify-end bg-black/40" onMouseDown={e => e.target === e.currentTarget && onClose()} data-testid="product-drawer">
      <div className="w-full max-w-xl h-full overflow-y-auto shadow-2xl border-l" style={{ background: surface, borderColor: border }}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b" style={{ background: surface, borderColor: border }}>
          <div>
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>{product.name}</h3>
            <p className="text-[11px]" style={{ color: c.textDim }}>{product.sku || 'No code'} · {product.category}{product.active === false ? ' · Archived' : ''}</p>
          </div>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="product-drawer-close"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }}>{error}</div>}

          <div className="grid grid-cols-2 gap-3">
            {fld('name', 'Name')}
            {fld('sku', 'Product code / SKU')}
            {fld('sage_code', 'Sage item code')}
            {fld('category', 'Category')}
            {fld('cost_price', 'Cost £', 'number')}
            {fld('sell_price', 'Sell £', 'number')}
            {fld('tax_rate', 'VAT %', 'number')}
            {fld('supplier_name', 'Supplier')}
            {fld('manufacturer', 'Manufacturer')}
            {fld('model', 'Model')}
          </div>

          {/* Description + AI clean */}
          <div data-testid="product-drawer-description-block">
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Description</label>
              {canEdit && (
                <button type="button" onClick={aiClean} disabled={aiBusy || !form.description.trim()}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border disabled:opacity-50"
                  style={{ borderColor: border, color: 'var(--color-info-ios)' }}
                  data-testid="product-drawer-ai-clean">
                  {aiBusy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} AI improve grammar
                </button>
              )}
            </div>
            <textarea value={form.description} disabled={!canEdit} rows={4}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full px-3 py-1.5 text-sm rounded-md border disabled:opacity-70"
              style={{ background: surface2, borderColor: border, color: c.text }}
              data-testid="product-drawer-description" />
            {aiError && <div className="text-[11px] mt-1" style={{ color: 'var(--color-danger-alt)' }} data-testid="product-drawer-ai-error">{aiError}</div>}
            {aiSuggestion != null && (
              <div className="mt-2 rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--color-info-ios)', background: surface2 }} data-testid="product-drawer-ai-suggestion">
                <div className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--color-info-ios)' }}>Suggested (grammar only — meaning preserved)</div>
                <p className="text-sm whitespace-pre-wrap" style={{ color: c.text }}>{aiSuggestion}</p>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => { setForm(f => ({ ...f, description: aiSuggestion })); setAiSuggestion(null); }}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-md text-white"
                    style={{ background: 'var(--color-success-alt)' }} data-testid="product-drawer-ai-accept">
                    <Check size={11} /> Use this
                  </button>
                  <button type="button" onClick={() => setAiSuggestion(null)}
                    className="text-[11px] font-semibold px-2.5 py-1 rounded-md border" style={{ borderColor: border, color: c.textMuted }}
                    data-testid="product-drawer-ai-reject">Discard</button>
                </div>
              </div>
            )}
          </div>

          {product.source_sheet && (
            <div className="rounded-lg border px-3 py-2 text-xs flex items-center gap-2" style={{ borderColor: border, background: surface2, color: c.textMuted }} data-testid="product-drawer-provenance">
              <FileSpreadsheet size={13} />
              <span>Imported from <strong style={{ color: c.text }}>{product.source_sheet}</strong> · row {product.source_row}{product.section ? ` · ${product.section}` : ''}</span>
            </div>
          )}

          {/* Additional imported data */}
          {Array.isArray(product.unmapped_fields) && product.unmapped_fields.length > 0 && (
            <div className="rounded-lg border" style={{ borderColor: border }} data-testid="product-drawer-unmapped">
              <div className="px-3 py-1.5 text-xs font-semibold border-b" style={{ color: c.text, borderColor: border }}>
                Additional imported data ({product.unmapped_fields.length})
              </div>
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <tbody>
                    {product.unmapped_fields.map((u, i) => (
                      <tr key={i} className="border-t" style={{ borderColor: border }}>
                        <td className="px-3 py-1.5" style={{ color: c.textDim }}>{u.column}</td>
                        <td className="px-3 py-1.5 text-right font-mono" style={{ color: c.text }}>{u.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {/* Price history */}
          {Array.isArray(product.price_history) && product.price_history.length > 0 && (
            <div className="rounded-lg border" style={{ borderColor: border }} data-testid="product-drawer-history">
              <div className="px-3 py-1.5 text-xs font-semibold border-b" style={{ color: c.text, borderColor: border }}>
                Price history ({product.price_history.length})
              </div>
              <div className="max-h-48 overflow-y-auto">
                {[...product.price_history].reverse().map((h, i) => (
                  <div key={i} className="px-3 py-1.5 border-t text-xs flex items-center justify-between gap-2" style={{ borderColor: border }}>
                    <span style={{ color: c.textMuted }}>
                      {(h.field || '').replace('_', ' ')} {h.old != null ? <><s style={{ color: c.textDim }}>£{h.old}</s> → <strong style={{ color: c.text }}>£{h.new}</strong></> : null}
                      {h.reason ? <span style={{ color: c.textDim }}> · {h.reason}</span> : null}
                    </span>
                    <span style={{ color: c.textDim }} className="whitespace-nowrap">{h.by} · {h.at ? new Date(h.at).toLocaleDateString() : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {canEdit && (
          <div className="sticky bottom-0 flex items-center justify-between px-5 py-3 border-t" style={{ background: surface, borderColor: border }}>
            <button type="button" onClick={toggleArchive} disabled={saving} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ borderColor: border, color: product.active === false ? 'var(--color-success-alt)' : 'var(--color-danger-alt)' }} data-testid="product-drawer-archive">
              {product.active === false ? <><RotateCcw size={12} /> Restore</> : <><Archive size={12} /> Archive</>}
            </button>
            <button type="button" onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="product-drawer-save">
              {saving ? <Loader2 size={13} className="animate-spin" /> : <><Save size={13} /> Save</>}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
