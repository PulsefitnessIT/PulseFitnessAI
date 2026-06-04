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
import { X, Save, Loader2, FileSpreadsheet, Archive, RotateCcw } from 'lucide-react';

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

          {/* Provenance */}
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
