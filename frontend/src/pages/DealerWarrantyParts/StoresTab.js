import { useEffect, useState, useCallback } from 'react';
import { Plus, Warehouse, ArrowLeft } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, money, StatusBadge } from './shared';

function StoreStock({ storeId, onBack }) {
  const [data, setData] = useState(null);
  useEffect(() => { dpApi.storeStock(storeId).then(setData); }, [storeId]);
  if (!data) return <Spinner />;
  return (
    <div className="space-y-4" data-testid="dp-store-stock">
      <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-800 inline-flex items-center gap-1"><ArrowLeft size={14} /> Back to stores</button>
      <div>
        <h2 className="text-lg font-bold text-slate-900">{data.store.name}</h2>
        <p className="text-sm text-slate-400">{data.store.dealer_name} · {[data.store.country, data.store.region].filter(Boolean).join(', ')}</p>
      </div>
      {data.stock.length === 0 ? <p className="text-sm text-slate-400">No stock in this store yet.</p> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Part</th><th>Status</th><th>On hand</th><th>In transit</th><th className="text-right">Value</th>
            </tr></thead>
            <tbody>
              {data.stock.map((s) => (
                <tr key={s.id} className="border-b border-slate-50">
                  <td className="py-2.5 px-4"><span className="font-mono text-xs text-slate-500">{s.part_sku}</span> {s.part_name}</td>
                  <td><StatusBadge status={s.stock_status} /></td>
                  <td className="tabular-nums">{s.qty_on_hand}</td>
                  <td className="tabular-nums text-slate-400">{s.qty_in_transit || 0}</td>
                  <td className="text-right tabular-nums">{money((s.qty_on_hand || 0) * (s.unit_value || 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function StoresTab() {
  const [stores, setStores] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ dealer_id: '', name: '', store_type: 'main', country: '', region: '' });

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dpApi.listStores(), dpApi.listDealers()]).then(([s, d]) => {
      setStores(s.stores || []); setDealers(d.dealers || []);
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.dealer_id || !form.name.trim()) { notify.error('Dealer and store name required'); return; }
    try { await dpApi.createStore(form); notify.success('Store created'); setModal(false); setForm({ dealer_id: '', name: '', store_type: 'main', country: '', region: '' }); load(); }
    catch { notify.error('Failed to create store'); }
  };

  if (selected) return <StoreStock storeId={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="space-y-4" data-testid="dp-stores-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500">Global dealer remote stores</h3>
        <button data-testid="dp-add-store-btn" onClick={() => setModal(true)} disabled={dealers.length === 0}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <Plus size={15} /> Add store
        </button>
      </div>
      {loading ? <Spinner /> : stores.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No remote stores yet. Dispatching an allocation auto-creates a Main Dealer Store.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {stores.map((s) => (
            <button key={s.id} data-testid={`dp-store-card-${s.id}`} onClick={() => setSelected(s.id)} className="text-left rounded-xl border border-slate-200 bg-white p-4 hover:shadow-md hover:border-[var(--gx-brand-from)]/40 transition-all">
              <div className="flex items-center gap-2 mb-1"><Warehouse size={16} className="text-[var(--gx-brand-from)]" /><span className="font-semibold text-slate-900 truncate">{s.name}</span></div>
              <div className="text-xs text-slate-400">{s.dealer_name}</div>
              <div className="text-xs text-slate-500 mt-2 capitalize">{s.store_type} · {[s.country, s.region].filter(Boolean).join(', ') || 'No location'}</div>
            </button>
          ))}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Add remote store" testid="dp-store-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-store-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Save store</button>
        </>}>
        <Field label="Dealer *">
          <select data-testid="dp-store-dealer" className={input} value={form.dealer_id} onChange={(e) => setForm({ ...form, dealer_id: e.target.value })}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <Field label="Store name *"><input data-testid="dp-store-name" className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Main Dealer Store" /></Field>
        <Field label="Store type">
          <select className={input} value={form.store_type} onChange={(e) => setForm({ ...form, store_type: e.target.value })}>
            {['main', 'van', 'country_warehouse', 'regional', 'customer_site', 'warranty'].map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Country"><input className={input} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></Field>
          <Field label="Region"><input className={input} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
