import { useEffect, useState, useCallback } from 'react';
import { Plus, Trash2, CheckCircle2, Send, Truck, PackageCheck, Sparkles, AlertTriangle } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, inputTight, money, StatusBadge } from './shared';

const ACTIONS = {
  draft: { label: 'Submit', icon: Send, fn: 'submitAllocation', next: 'submitted for approval' },
  awaiting_approval: { label: 'Approve', icon: CheckCircle2, fn: 'approveAllocation', next: 'approved' },
  approved: { label: 'Dispatch', icon: Truck, fn: 'dispatchAllocation', next: 'dispatched to dealer store' },
  dispatched: { label: 'Confirm receipt', icon: PackageCheck, fn: 'receiveAllocation', next: 'received' },
  partially_received: { label: 'Confirm receipt', icon: PackageCheck, fn: 'receiveAllocation', next: 'received' },
};

export default function AllocationsTab() {
  const [allocs, setAllocs] = useState([]);
  const [orders, setOrders] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [dealerId, setDealerId] = useState('');
  const [orderId, setOrderId] = useState('');
  const [items, setItems] = useState([{ part_sku: '', part_name: '', machine_model: '', quantity: 1, unit_value: '', reason: '' }]);
  const [recMeta, setRecMeta] = useState(null);
  const [recLoading, setRecLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dpApi.listAllocations(), dpApi.listOrders(), dpApi.listDealers()]).then(([a, o, d]) => {
      setAllocs(a.allocations || []); setOrders(o.orders || []); setDealers(d.dealers || []);
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const dealerOrders = orders.filter((o) => o.dealer_id === dealerId);
  const order = orders.find((o) => o.id === orderId);
  const itemsValue = items.reduce((s, i) => s + (Number(i.quantity) || 0) * (Number(i.unit_value) || 0), 0);
  const allowance = order?.allowance || 0;
  const overAllowance = allowance > 0 && itemsValue > allowance;

  const create = async () => {
    if (!dealerId) { notify.error('Select a dealer'); return; }
    const clean = items.filter((i) => i.part_sku).map((i) => ({ ...i, quantity: Number(i.quantity), unit_value: Number(i.unit_value) }));
    if (clean.length === 0) { notify.error('Add at least one part'); return; }
    try {
      await dpApi.createAllocation({ dealer_id: dealerId, order_id: orderId || null, items: clean });
      notify.success('Allocation created');
      setModal(false); setDealerId(''); setOrderId(''); setRecMeta(null);
      setItems([{ part_sku: '', part_name: '', machine_model: '', quantity: 1, unit_value: '', reason: '' }]);
      load();
    } catch { notify.error('Failed to create allocation'); }
  };

  const generateRecommendation = async () => {
    if (!orderId) { notify.error('Select an order first'); return; }
    setRecLoading(true);
    try {
      const rec = await dpApi.recommend({ order_id: orderId });
      const recItems = (rec.recommended_items || []).map((i) => ({
        part_sku: i.part_sku, part_name: i.part_name, machine_model: i.machine_model,
        quantity: i.recommended_qty, unit_value: i.unit_value, reason: i.reason,
      }));
      if (recItems.length === 0) {
        notify.info('No new parts recommended — dealer already holds the required stock.');
        setItems([{ part_sku: '', part_name: '', machine_model: '', quantity: 1, unit_value: '', reason: '' }]);
      } else {
        setItems(recItems);
      }
      setRecMeta(rec);
      notify.success(`AI recommendation ready — ${recItems.length} parts, ${rec.duplicates_avoided} duplicate(s) avoided`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not generate recommendation');
    } finally { setRecLoading(false); }
  };

  const runAction = async (a) => {
    const act = ACTIONS[a.status];
    if (!act) return;
    try {
      await dpApi[act.fn](a.id, {});
      notify.success(`Allocation ${act.next}`);
      load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Action failed');
    }
  };

  return (
    <div className="space-y-4" data-testid="dp-allocations-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500">Dealer warranty parts allocations</h3>
        <button data-testid="dp-add-alloc-btn" onClick={() => { setModal(true); setRecMeta(null); }} disabled={dealers.length === 0}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <Plus size={15} /> New allocation
        </button>
      </div>

      {loading ? <Spinner /> : allocs.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No allocations yet.</div>
      ) : (
        <div className="space-y-2">
          {allocs.map((a) => {
            const act = ACTIONS[a.status];
            const Icon = act?.icon;
            return (
              <div key={a.id} data-testid={`dp-alloc-row-${a.id}`} className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900">{a.dealer_name}</span>
                    <StatusBadge status={a.status} />
                    {a.over_allowance && <span className="text-[11px] font-semibold text-red-600 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">Over allowance</span>}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {(a.items || []).length} parts · {money(a.recommended_value)}
                    {a.allowance ? ` · allowance ${money(a.allowance)} (${money(a.allowance_remaining)} left)` : ''}
                  </div>
                </div>
                {act && (
                  <button data-testid={`dp-alloc-action-${a.id}`} onClick={() => runAction(a)}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-[var(--gx-brand-from)]/30 text-[var(--gx-brand-from)] hover:bg-[var(--gx-brand-from)]/5">
                    <Icon size={14} /> {act.label}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="New warranty parts allocation" testid="dp-alloc-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-alloc-save" onClick={create} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Create allocation</button>
        </>}>
        <Field label="Dealer *">
          <select data-testid="dp-alloc-dealer" className={input} value={dealerId} onChange={(e) => { setDealerId(e.target.value); setOrderId(''); }}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        {dealerId && (
          <Field label="Link to order (sets allowance)">
            <select data-testid="dp-alloc-order" className={input} value={orderId} onChange={(e) => { setOrderId(e.target.value); setRecMeta(null); }}>
              <option value="">No order</option>
              {dealerOrders.map((o) => <option key={o.id} value={o.id}>{o.order_reference || o.id.slice(0, 6)} — allowance {money(o.allowance)}</option>)}
            </select>
          </Field>
        )}

        {orderId && (
          <button data-testid="dp-generate-rec-btn" onClick={generateRecommendation} disabled={recLoading}
            className="w-full mb-3 inline-flex items-center justify-center gap-2 text-sm font-semibold px-3 py-2.5 rounded-lg bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white hover:opacity-90 disabled:opacity-50">
            <Sparkles size={15} /> {recLoading ? 'Generating…' : 'Generate recommended parts pack'}
          </button>
        )}

        {recMeta && (
          <div className="mb-3 rounded-lg border border-[var(--gx-brand-from)]/20 bg-[var(--gx-brand-from)]/5 p-3 text-xs space-y-1" data-testid="dp-rec-meta">
            <p className="text-slate-600">AI recommendation — please review before approval. {recMeta.duplicates_avoided} duplicate part(s) avoided using dealer stock &amp; prior allocations.</p>
            {recMeta.missing_bom_models?.length > 0 && (
              <p className="text-amber-700 flex items-center gap-1"><AlertTriangle size={12} /> No BOM found for: {recMeta.missing_bom_models.join(', ')} — add a BOM for fuller coverage.</p>
            )}
          </div>
        )}

        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500">Recommended parts</span>
          <button onClick={() => setItems([...items, { part_sku: '', part_name: '', machine_model: '', quantity: 1, unit_value: '', reason: '' }])} className="text-xs text-[var(--gx-brand-from)] font-semibold">+ Add part</button>
        </div>
        {items.map((it, i) => (
          <div key={i} className="border border-slate-100 rounded-lg p-2.5 mb-2 space-y-2">
            <div className="flex gap-2">
              <input placeholder="Part SKU" className={`${inputTight} w-32 font-mono`} value={it.part_sku} onChange={(e) => { const n = [...items]; n[i].part_sku = e.target.value.toUpperCase(); setItems(n); }} />
              <input placeholder="Part name" className={`${inputTight} flex-1`} value={it.part_name} onChange={(e) => { const n = [...items]; n[i].part_name = e.target.value; setItems(n); }} />
              {items.length > 1 && <button onClick={() => setItems(items.filter((_, x) => x !== i))} className="text-slate-300 hover:text-red-500"><Trash2 size={15} /></button>}
            </div>
            <div className="flex gap-2">
              <input placeholder="Machine model" className={`${inputTight} flex-1`} value={it.machine_model} onChange={(e) => { const n = [...items]; n[i].machine_model = e.target.value; setItems(n); }} />
              <input type="number" placeholder="Qty" className={`${inputTight} w-16`} value={it.quantity} onChange={(e) => { const n = [...items]; n[i].quantity = e.target.value; setItems(n); }} />
              <input type="number" placeholder="Unit £" className={`${inputTight} w-24`} value={it.unit_value} onChange={(e) => { const n = [...items]; n[i].unit_value = e.target.value; setItems(n); }} />
            </div>
            <input placeholder="Reason for recommendation" className={input} value={it.reason} onChange={(e) => { const n = [...items]; n[i].reason = e.target.value; setItems(n); }} />
          </div>
        ))}

        <div className={`rounded-lg border p-3 text-sm ${overAllowance ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-200'}`} data-testid="dp-alloc-value">
          <div className="flex justify-between"><span className="text-slate-500">Recommended value</span><span className="font-bold tabular-nums">{money(itemsValue)}</span></div>
          {allowance > 0 && <div className="flex justify-between mt-1"><span className="text-slate-500">Allowance remaining</span><span className={`font-semibold tabular-nums ${overAllowance ? 'text-red-600' : 'text-emerald-600'}`}>{money(allowance - itemsValue)}</span></div>}
          {overAllowance && <p className="text-xs text-red-600 mt-1.5">Exceeds allowance — manager approval will be required.</p>}
        </div>
      </Modal>
    </div>
  );
}
