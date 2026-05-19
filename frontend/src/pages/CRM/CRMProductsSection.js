/**
 * CRM Master Price List admin panel — Iter 216h224.
 *
 * Settings → Products tab. Lets CRM admins manage the product
 * catalogue that backs the quote builder. Shows name / SKU /
 * category / cost / sell / markup % + soft-delete.
 *
 * Bulk import via CSV (multipart upload to /api/crm/products/bulk-import).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Package, Plus, Loader2, Search, Trash2, Upload, X, Save } from 'lucide-react';

const DEFAULT_CATEGORIES = [
  'Equipment', 'Service', 'Labour', 'Callout',
  'Maintenance Plan', 'Membership', 'Parts', 'Discount', 'Other',
];

export default function CRMProductsSection({ API, headers, c, isDark }) {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', sku: '', category: 'Equipment', cost_price: '', sell_price: '', tax_rate: '20', unit: 'each', supplier_name: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/products`, { headers: headers(), params: { search, category: filterCat, active: true } });
      setProducts(r.data.products || []);
      setTotal(r.data.total || 0);
    } catch (e) { /* silent */ }
    setLoading(false);
  }, [API, headers, search, filterCat]);

  const loadCategories = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/products/categories`, { headers: headers() });
      setCategories(r.data.categories || DEFAULT_CATEGORIES);
    } catch (e) { /* silent */ }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadCategories(); }, [loadCategories]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = { ...form, cost_price: Number(form.cost_price || 0), sell_price: Number(form.sell_price || 0), tax_rate: Number(form.tax_rate || 0) };
      if (editingId) {
        await axios.patch(`${API}/crm/products/${editingId}`, payload, { headers: headers() });
      } else {
        await axios.post(`${API}/crm/products`, payload, { headers: headers() });
      }
      setShowCreate(false);
      setEditingId(null);
      setForm({ name: '', sku: '', category: 'Equipment', cost_price: '', sell_price: '', tax_rate: '20', unit: 'each', supplier_name: '', description: '' });
      load();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save product');
    }
    setSaving(false);
  };

  const onDeactivate = async (p) => {
    if (!window.confirm(`Deactivate "${p.name}"? Existing quotes that reference it stay intact.`)) return;
    try {
      await axios.delete(`${API}/crm/products/${p.id}`, { headers: headers() });
      load();
    } catch (err) { setError(err?.response?.data?.detail || 'Delete failed'); }
  };

  const onEdit = (p) => {
    setEditingId(p.id);
    setForm({
      name: p.name || '',
      sku: p.sku || '',
      category: p.category || 'Equipment',
      cost_price: String(p.cost_price ?? ''),
      sell_price: String(p.sell_price ?? ''),
      tax_rate: String(p.tax_rate ?? '20'),
      unit: p.unit || 'each',
      supplier_name: p.supplier_name || '',
      description: p.description || '',
    });
    setShowCreate(true);
  };

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/crm/products/bulk-import`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      setImportResult(r.data);
      load();
    } catch (err) {
      setImportResult({ error: err?.response?.data?.detail || 'Import failed' });
    }
    setImporting(false);
    e.target.value = '';
  };

  const markup = (p) => p.cost_price > 0 ? (((p.sell_price - p.cost_price) / p.cost_price) * 100).toFixed(1) : '—';

  return (
    <div
      className="rounded-lg border p-5"
      style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
      data-testid="settings-products"
    >
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}>
            <Package size={14} /> Master Price List
          </h3>
          <p className="text-xs mt-0.5" style={{ color: c.textDim }}>Products + services with cost & sell prices. Powers margin calculations on quotes.</p>
        </div>
        <div className="flex items-center gap-2">
          <input type="file" accept=".csv" onChange={onImport} className="hidden" id="products-csv-upload" data-testid="products-csv-input" />
          <label htmlFor="products-csv-upload" className="cursor-pointer inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textMuted }}>
            {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} Import CSV
          </label>
          <button
            type="button"
            onClick={() => { setShowCreate(true); setEditingId(null); setForm({ name: '', sku: '', category: 'Equipment', cost_price: '', sell_price: '', tax_rate: '20', unit: 'each', supplier_name: '', description: '' }); }}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white"
            style={{ background: 'var(--color-info-ios)' }}
            data-testid="products-add-btn"
          >
            <Plus size={12} /> Add product
          </button>
        </div>
      </div>

      {importResult && (
        <div className="mb-3 px-3 py-2 rounded-md text-xs" style={{
          background: importResult.error ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)',
          color: importResult.error ? 'var(--color-danger-alt)' : 'var(--color-success-alt)',
          borderLeft: `3px solid ${importResult.error ? 'var(--color-danger-alt)' : 'var(--color-success-alt)'}`,
        }} data-testid="products-import-result">
          {importResult.error ? importResult.error : (
            <>Imported: <strong>{importResult.created}</strong> new · <strong>{importResult.updated}</strong> updated · {importResult.skipped} skipped</>
          )}
        </div>
      )}

      {/* Search + filter bar */}
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 opacity-50" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search name, SKU, description…"
            className="w-full h-9 pl-9 pr-3 text-xs rounded-md border"
            style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }}
            data-testid="products-search"
          />
        </div>
        <select
          value={filterCat}
          onChange={e => setFilterCat(e.target.value)}
          className="h-9 px-2 text-xs rounded-md border"
          style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }}
          data-testid="products-filter-category"
        >
          <option value="">All categories</option>
          {categories.map(c2 => <option key={c2} value={c2}>{c2}</option>)}
        </select>
      </div>

      {error && <div className="mb-2 text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.06)', color: 'var(--color-danger-alt)' }} data-testid="products-error">{error}</div>}

      {loading ? (
        <div className="text-xs py-6 flex items-center gap-2" style={{ color: c.textMuted }}><Loader2 size={12} className="animate-spin" /> Loading…</div>
      ) : (
        <div className="rounded-md border overflow-hidden" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <table className="w-full text-xs">
            <thead style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'rgba(241,245,249,0.5)' }}>
              <tr style={{ color: c.textDim }}>
                <th className="text-left px-3 py-2 font-semibold">Name</th>
                <th className="text-left px-3 py-2 font-semibold">SKU</th>
                <th className="text-left px-3 py-2 font-semibold">Category</th>
                <th className="text-right px-3 py-2 font-semibold">Cost</th>
                <th className="text-right px-3 py-2 font-semibold">Sell</th>
                <th className="text-right px-3 py-2 font-semibold">Markup</th>
                <th className="text-right px-3 py-2 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="products-table">
              {products.map(p => (
                <tr key={p.id} className="border-t" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`products-row-${p.id}`}>
                  <td className="px-3 py-2" style={{ color: c.text }}>{p.name}</td>
                  <td className="px-3 py-2" style={{ color: c.textMuted }}>{p.sku || '—'}</td>
                  <td className="px-3 py-2" style={{ color: c.textMuted }}>{p.category}</td>
                  <td className="text-right px-3 py-2 font-mono" style={{ color: c.textMuted }}>£{Number(p.cost_price).toFixed(2)}</td>
                  <td className="text-right px-3 py-2 font-mono" style={{ color: c.text }}>£{Number(p.sell_price).toFixed(2)}</td>
                  <td className="text-right px-3 py-2 font-mono font-semibold" style={{ color: p.markup_percent >= 30 ? 'var(--color-success-alt)' : p.markup_percent >= 15 ? 'var(--color-accent-amber)' : 'var(--color-danger-alt)' }}>{markup(p)}{p.cost_price > 0 ? '%' : ''}</td>
                  <td className="text-right px-3 py-2">
                    <button type="button" onClick={() => onEdit(p)} className="text-[11px] underline opacity-70 hover:opacity-100 mr-3" data-testid={`products-edit-${p.id}`}>Edit</button>
                    <button type="button" onClick={() => onDeactivate(p)} className="text-[11px] opacity-70 hover:opacity-100" style={{ color: 'var(--color-danger-alt)' }} data-testid={`products-deactivate-${p.id}`}>
                      <Trash2 size={11} />
                    </button>
                  </td>
                </tr>
              ))}
              {products.length === 0 && !loading && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-xs" style={{ color: c.textDim }}>No products yet — add one or import a CSV.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-2 text-[10px] opacity-60" style={{ color: c.textDim }}>{total} total · CSV columns: name, sku, category, unit, cost_price, sell_price, tax_rate, supplier_name, description</div>

      {/* Create / edit modal */}
      {showCreate && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" data-testid="products-modal">
          <form onSubmit={onSubmit} className="w-full max-w-lg rounded-2xl shadow-2xl border p-5 space-y-3" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>{editingId ? 'Edit product' : 'Add product'}</h3>
              <button type="button" onClick={() => { setShowCreate(false); setEditingId(null); }} className="opacity-60 hover:opacity-100"><X size={14} /></button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Name *</label>
                <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-name" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>SKU</label>
                <input value={form.sku} onChange={e => setForm({...form, sku: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-sku" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Category</label>
                <select value={form.category} onChange={e => setForm({...form, category: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-category">
                  {categories.map(cx => <option key={cx} value={cx}>{cx}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Cost £</label>
                <input type="number" step="0.01" min="0" value={form.cost_price} onChange={e => setForm({...form, cost_price: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border font-mono" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-cost" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Sell £</label>
                <input type="number" step="0.01" min="0" value={form.sell_price} onChange={e => setForm({...form, sell_price: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border font-mono" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-sell" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Tax %</label>
                <input type="number" step="0.1" min="0" max="100" value={form.tax_rate} onChange={e => setForm({...form, tax_rate: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border font-mono" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} data-testid="products-tax" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Unit</label>
                <input value={form.unit} onChange={e => setForm({...form, unit: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} placeholder="each / hour / day" />
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Supplier</label>
                <input value={form.supplier_name} onChange={e => setForm({...form, supplier_name: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} />
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Description</label>
                <textarea rows={2} value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.text }} />
              </div>
            </div>
            {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.06)', color: 'var(--color-danger-alt)' }}>{error}</div>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowCreate(false); setEditingId(null); }} className="text-xs font-semibold px-3 py-1.5 rounded-md" style={{ color: c.textMuted }}>Cancel</button>
              <button type="submit" disabled={saving || !form.name.trim()} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="products-submit">
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
