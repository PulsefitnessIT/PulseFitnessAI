/**
 * PartsCatalogue — Iter 220ea·20 · Phase 5b.
 *
 * Server-side paginated catalogue browser over /api/svc/parts/catalogue.
 * Search, facet filters (category / manufacturer / status), pagination,
 * inline edit drawer and the bulk Import wizard. Desktop-friendly but
 * usable on mobile. Cost price only shows for owner/admin (show_cost).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Search, Loader2, ChevronLeft, ChevronRight,
  Package, PoundSterling, Pencil, X, Boxes,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import PartsImportWizard from './PartsImportWizard';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STATUS = [
  { k: 'active', label: 'Active' },
  { k: 'inactive', label: 'Inactive' },
  { k: 'obsolete', label: 'Obsolete' },
  { k: 'all', label: 'All' },
];

export default function PartsCatalogue() {
  const navigate = useNavigate();
  const loc = useLocalization();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState({ items: [], total: 0, pages: 1, show_cost: false, can_manage: false });
  const [facets, setFacets] = useState({ categories: [], manufacturers: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('active');
  const [page, setPage] = useState(1);
  const [importing, setImporting] = useState(false);
  const [edit, setEdit] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/parts/catalogue`, {
        ...auth(), params: { search, category, status, page, page_size: 25 },
      });
      setData(r.data);
    } catch {
      notify.error('Could not load catalogue');
    } finally { setLoading(false); }
  }, [search, category, status, page]);

  const loadFacets = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/parts/catalogue/facets`, auth());
      setFacets(r.data);
    } catch { /* non-fatal */ }
  }, []);

  useEffect(() => { loadFacets(); }, [loadFacets]);
  useEffect(() => {
    const t = setTimeout(() => { load(); }, 250);
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => { setPage(1); }, [search, category, status]);

  // Iter 220ea·21 — Import is launched from Account Settings → Stock
  // (?import=1), not from a button on this screen. Open the wizard once
  // the catalogue confirms the user can manage parts.
  useEffect(() => {
    if (searchParams.get('import') === '1' && data.can_manage) {
      setImporting(true);
    }
  }, [searchParams, data.can_manage]);

  const closeImport = () => {
    setImporting(false);
    if (searchParams.get('import')) {
      searchParams.delete('import');
      setSearchParams(searchParams, { replace: true });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="parts-catalogue-page">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/svc/engineer/stock')} className="p-2 -ml-2 text-slate-500" data-testid="catalogue-back" aria-label="Back">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-extrabold text-slate-900 leading-none">Parts Catalogue</h1>
            <p className="text-xs text-slate-500 mt-0.5">{facets.total} parts</p>
          </div>
        </div>
        <div className="max-w-5xl mx-auto px-4 pb-3 space-y-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)}
                   placeholder="Search part, SKU, manufacturer"
                   className="w-full h-11 pl-10 pr-3 rounded-xl border border-slate-200 text-sm bg-white"
                   data-testid="catalogue-search" />
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <select value={category} onChange={(e) => setCategory(e.target.value)}
                    data-testid="catalogue-category"
                    className="shrink-0 h-8 rounded-full border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-600">
              <option value="">All categories</option>
              {facets.categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            {STATUS.map((s) => (
              <button key={s.k} onClick={() => setStatus(s.k)}
                      data-testid={`catalogue-status-${s.k}`}
                      className={`shrink-0 px-3 h-8 rounded-full text-xs font-semibold border ${
                        status === s.k ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200'}`}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 pt-4 pb-28">
        {loading ? (
          <div className="py-20 flex justify-center text-slate-400"><Loader2 className="w-7 h-7 animate-spin" /></div>
        ) : data.items.length === 0 ? (
          <div className="py-16 text-center" data-testid="catalogue-empty">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400"><Boxes className="w-7 h-7" /></div>
            <p className="mt-3 font-bold text-slate-700">No parts found</p>
            <p className="text-sm text-slate-400 mt-1">{data.can_manage ? 'Import parts from Account settings → Stock → Import parts.' : 'Try a different search.'}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.items.map((p) => (
              <div key={p.id} className="bg-white rounded-xl border border-slate-200 p-3.5 flex items-center gap-3"
                   data-testid={`catalogue-item-${p.sku}`}>
                <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 shrink-0"><Package className="w-5 h-5" /></div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-slate-900 text-sm truncate">{p.name}
                    {p.active === false && <span className="ml-2 text-[10px] font-bold text-slate-400 uppercase">{p.status || 'inactive'}</span>}
                  </p>
                  <p className="text-xs text-slate-500 truncate">
                    <span className="font-mono">{p.sku}</span>
                    {p.manufacturer ? ` · ${p.manufacturer}` : ''}{p.category ? ` · ${p.category}` : ''}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm font-bold text-slate-800 inline-flex items-center"><PoundSterling className="w-3 h-3" />{(p.list_price || 0).toFixed(2)}</p>
                  {data.show_cost && <p className="text-[11px] text-slate-400">cost {formatMoney(p.cost || 0, loc)}</p>}
                </div>
                {data.can_manage && (
                  <button onClick={() => setEdit(p)} className="p-2 text-slate-400 hover:text-cyan-600" data-testid={`catalogue-edit-${p.sku}`} aria-label="Edit">
                    <Pencil className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="flex items-center justify-center gap-3 mt-5" data-testid="catalogue-pagination">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
                    className="px-3 h-9 rounded-lg border border-slate-200 text-sm font-semibold disabled:opacity-40 flex items-center gap-1" data-testid="catalogue-prev">
              <ChevronLeft className="w-4 h-4" /> Prev
            </button>
            <span className="text-sm text-slate-500">Page {page} of {data.pages}</span>
            <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}
                    className="px-3 h-9 rounded-lg border border-slate-200 text-sm font-semibold disabled:opacity-40 flex items-center gap-1" data-testid="catalogue-next">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {importing && (
        <PartsImportWizard onClose={closeImport}
                           onComplete={() => { load(); loadFacets(); }} />
      )}
      {edit && (
        <EditDrawer part={edit} showCost={data.show_cost}
                    onClose={() => setEdit(null)}
                    onSaved={() => { setEdit(null); load(); }} />
      )}
    </div>
  );
}

// ── Edit drawer ───────────────────────────────────────────────────
const EditDrawer = ({ part, showCost, onClose, onSaved }) => {
  const [form, setForm] = useState({
    name: part.name || '', category: part.category || '', manufacturer: part.manufacturer || '',
    supplier: part.supplier || '', list_price: part.list_price ?? 0, cost: part.cost ?? 0,
    reorder_threshold: part.reorder_threshold ?? 0, reorder_qty: part.reorder_qty ?? 0,
    reorder_max: part.reorder_max ?? 0,
    bin_location: part.bin_location || '', cover_category: part.cover_category || '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...form };
      if (!showCost) delete payload.cost;
      await axios.patch(`${API}/svc/parts/catalogue/${part.id}`, payload, auth());
      notify.success('Part updated');
      onSaved();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not save');
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[120] bg-slate-900/50 flex items-end sm:items-center justify-center sm:p-4" onClick={onClose} data-testid="catalogue-edit-drawer">
      <div className="w-full sm:max-w-md bg-white rounded-t-2xl sm:rounded-2xl p-5 pb-28 sm:pb-5 space-y-3 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-900">Edit part</h3>
          <button onClick={onClose} className="p-1 text-slate-400"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-xs font-mono text-slate-400">{part.sku}</p>
        <Field label="Name" value={form.name} onChange={(v) => set('name', v)} tid="edit-name" />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category" value={form.category} onChange={(v) => set('category', v)} tid="edit-category" />
          <Field label="Manufacturer" value={form.manufacturer} onChange={(v) => set('manufacturer', v)} tid="edit-manufacturer" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Sell price" type="number" value={form.list_price} onChange={(v) => set('list_price', v)} tid="edit-price" />
          {showCost && <Field label="Cost price" type="number" value={form.cost} onChange={(v) => set('cost', v)} tid="edit-cost" />}
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Min stock" type="number" value={form.reorder_threshold} onChange={(v) => set('reorder_threshold', v)} tid="edit-min" />
          <Field label="Max stock" type="number" value={form.reorder_max} onChange={(v) => set('reorder_max', v)} tid="edit-max" />
          <Field label="Reorder qty" type="number" value={form.reorder_qty} onChange={(v) => set('reorder_qty', v)} tid="edit-reorder" />
        </div>
        <Field label="Van location" value={form.bin_location} onChange={(v) => set('bin_location', v)} tid="edit-bin" />
        <div>
          <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Contract cover category</label>
          <select value={form.cover_category} onChange={(e) => set('cover_category', e.target.value)}
                  data-testid="edit-cover-category"
                  className="w-full mt-1 h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
            <option value="">Auto-detect from name</option>
            <option value="major">Major part</option>
            <option value="wear_tear">Wear &amp; tear part</option>
            <option value="consumable">Consumable</option>
            <option value="treadmill_belts">Treadmill belt</option>
            <option value="treadmill_beds">Treadmill bed/deck</option>
            <option value="upholstery">Upholstery</option>
          </select>
          <p className="text-[10px] text-slate-400 mt-1">Decides whether this part is covered by a contract or chargeable when used on a job.</p>
        </div>
        <button onClick={save} disabled={busy} data-testid="edit-save"
                className="w-full h-12 rounded-xl bg-cyan-600 text-white font-bold flex items-center justify-center gap-2 disabled:opacity-60">
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : null} Save changes
        </button>
      </div>
    </div>
  );
};

const Field = ({ label, value, onChange, type = 'text', tid }) => (
  <div>
    <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</label>
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
           className="w-full mt-1 h-10 px-3 rounded-xl border border-slate-200 text-sm" data-testid={tid} />
  </div>
);

export { PartsCatalogue };
