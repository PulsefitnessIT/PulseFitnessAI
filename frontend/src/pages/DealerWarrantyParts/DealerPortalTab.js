import { useEffect, useState, useCallback } from 'react';
import { Store, PackagePlus, Truck, Wrench } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { StatCard, Spinner, Modal, Field, input, money, StatusBadge } from './shared';

export default function DealerPortalTab() {
  const [dealers, setDealers] = useState([]);
  const [dealerId, setDealerId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ part_sku: '', part_name: '', quantity: 1, note: '' });

  useEffect(() => { dpApi.listDealers().then((d) => { setDealers(d.dealers || []); if (d.dealers?.[0]) setDealerId(d.dealers[0].id); }); }, []);
  const load = useCallback(() => {
    if (!dealerId) return;
    setLoading(true);
    dpApi.portalOverview(dealerId).then(setData).finally(() => setLoading(false));
  }, [dealerId]);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!form.part_sku.trim()) { notify.error('Part SKU required'); return; }
    try {
      await dpApi.requestReplenishment(dealerId, { ...form, quantity: Number(form.quantity) });
      notify.success('Replenishment requested');
      setModal(false); setForm({ part_sku: '', part_name: '', quantity: 1, note: '' }); load();
    } catch { notify.error('Failed to request'); }
  };

  return (
    <div className="space-y-5" data-testid="dp-portal-tab">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-slate-500"><Store size={15} /> Viewing portal as dealer:</div>
        <select data-testid="dp-portal-dealer" className={`${input} max-w-xs`} value={dealerId} onChange={(e) => setDealerId(e.target.value)}>
          {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button data-testid="dp-portal-request-btn" onClick={() => setModal(true)} disabled={!dealerId}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <PackagePlus size={15} /> Request replenishment
        </button>
      </div>
      <p className="text-xs text-slate-400 -mt-2">Dealers only ever see their own store, stock, usage and shipments — never another dealer's data.</p>

      {loading || !data ? <Spinner /> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Stock lines" value={data.stock.length} tone="brand" />
            <StatCard label="Stock value" value={money(data.stock_value)} tone="emerald" />
            <StatCard label="Incoming shipments" value={data.incoming.length} tone={data.incoming.length ? 'amber' : 'slate'} />
            <StatCard label="Open requests" value={(data.requests || []).filter((r) => r.status !== 'fulfilled' && r.status !== 'rejected').length} />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-portal-stock">
            <h3 className="text-sm font-bold text-slate-900 mb-3">My parts store</h3>
            {data.stock.length === 0 ? <p className="text-sm text-slate-400">No stock held.</p> : (
              <div className="overflow-x-auto"><table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100"><th className="py-2">Part</th><th>Status</th><th>On hand</th><th>In transit</th><th className="text-right">Value</th></tr></thead>
                <tbody>{data.stock.map((s) => (
                  <tr key={s.id} className="border-b border-slate-50">
                    <td className="py-2"><span className="font-mono text-xs text-slate-500">{s.part_sku}</span> {s.part_name}</td>
                    <td><StatusBadge status={s.stock_status} /></td>
                    <td className="tabular-nums">{s.qty_on_hand}</td>
                    <td className="tabular-nums text-slate-400">{s.qty_in_transit || 0}</td>
                    <td className="text-right tabular-nums">{money((s.qty_on_hand || 0) * (s.unit_value || 0))}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Truck size={15} /> Incoming shipments</h3>
              {data.incoming.length === 0 ? <p className="text-sm text-slate-400">Nothing in transit.</p> : data.incoming.map((a) => (
                <div key={a.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-600">{(a.items || []).length} parts</span><StatusBadge status={a.status} />
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Wrench size={15} /> Recent usage</h3>
              {data.recent_usage.length === 0 ? <p className="text-sm text-slate-400">No usage logged.</p> : data.recent_usage.map((u) => (
                <div key={u.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-600"><span className="font-mono text-xs text-slate-400">{u.part_sku}</span> {u.quantity} used</span>
                  <span className="text-xs text-slate-400">{(u.at || '').slice(0, 10)}</span>
                </div>
              ))}
            </div>
          </div>

          {(data.requests || []).length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h3 className="text-sm font-bold text-slate-900 mb-3">Replenishment requests</h3>
              {data.requests.map((r) => (
                <div key={r.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-600"><span className="font-mono text-xs text-slate-400">{r.part_sku}</span> × {r.quantity}{r.note ? ` — ${r.note}` : ''}</span>
                  <span className="text-xs font-semibold text-slate-500 capitalize">{r.status.replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Request replenishment" testid="dp-portal-request-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-portal-request-save" onClick={submit} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Send request</button>
        </>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Part SKU *"><input data-testid="dp-portal-req-sku" className={`${input} font-mono`} value={form.part_sku} onChange={(e) => setForm({ ...form, part_sku: e.target.value.toUpperCase() })} /></Field>
          <Field label="Quantity"><input type="number" className={input} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>
        </div>
        <Field label="Part name"><input className={input} value={form.part_name} onChange={(e) => setForm({ ...form, part_name: e.target.value })} /></Field>
        <Field label="Note"><input className={input} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
