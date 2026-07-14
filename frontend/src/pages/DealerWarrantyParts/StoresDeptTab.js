import { useEffect, useState, useCallback } from 'react';
import { Truck, PackageCheck, AlertTriangle, Wrench, Warehouse } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { StatCard, Spinner, StatusBadge, money } from './shared';

export default function StoresDeptTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.storesDashboard().then(setData).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const dispatch = async (a) => {
    try { await dpApi.dispatchAllocation(a.id, {}); notify.success('Dispatched to dealer store'); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Dispatch failed'); }
  };
  const confirmReceipt = async (a) => {
    try { await dpApi.receiveAllocation(a.id, {}); notify.success('Receipt confirmed'); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Receipt failed'); }
  };

  if (loading) return <Spinner />;
  const c = data?.cards || {};

  return (
    <div className="space-y-6" data-testid="dp-stores-dept-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testid="dp-sd-topick" label="Allocations to pick" value={c.to_pick ?? 0} tone={c.to_pick ? 'brand' : 'slate'} />
        <StatCard testid="dp-sd-receipt" label="Awaiting receipt" value={c.awaiting_receipt ?? 0} tone={c.awaiting_receipt ? 'amber' : 'slate'} />
        <StatCard testid="dp-sd-low" label="Low stock lines" value={c.low_stock ?? 0} tone={c.low_stock ? 'red' : 'slate'} />
        <StatCard testid="dp-sd-rma" label="Open RMAs" value={c.open_rma ?? 0} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-sd-picking">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Truck size={15} /> Picking &amp; dispatch queue</h3>
        {(data?.to_pick || []).length === 0 ? <p className="text-sm text-slate-400">No approved allocations awaiting dispatch.</p> : (
          <div className="space-y-2">
            {data.to_pick.map((a) => (
              <div key={a.id} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-slate-800">{a.dealer_name}</div>
                  <div className="text-xs text-slate-400">{(a.items || []).length} parts · {money(a.approved_value || a.recommended_value)}</div>
                </div>
                <button data-testid={`dp-sd-dispatch-${a.id}`} onClick={() => dispatch(a)} className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-[var(--gx-brand-from)]/30 text-[var(--gx-brand-from)] hover:bg-[var(--gx-brand-from)]/5"><Truck size={14} /> Pick &amp; dispatch</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-sd-awaiting">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><PackageCheck size={15} /> Shipments awaiting receipt</h3>
        {(data?.awaiting_receipt || []).length === 0 ? <p className="text-sm text-slate-400">No shipments in transit.</p> : (
          <div className="space-y-2">
            {data.awaiting_receipt.map((a) => (
              <div key={a.id} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-slate-800 flex items-center gap-2">{a.dealer_name} <StatusBadge status={a.status} /></div>
                  <div className="text-xs text-slate-400">{(a.items || []).length} parts · dispatched</div>
                </div>
                <button data-testid={`dp-sd-receive-${a.id}`} onClick={() => confirmReceipt(a)} className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-emerald-300 text-emerald-700 hover:bg-emerald-50"><PackageCheck size={14} /> Confirm receipt</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-sd-usage">
          <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Wrench size={15} /> Recent parts usage</h3>
          {(data?.recent_usage || []).length === 0 ? <p className="text-sm text-slate-400">No recent usage.</p> : (
            <div className="space-y-2">
              {data.recent_usage.map((u) => (
                <div key={u.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-600 truncate"><span className="font-mono text-xs text-slate-400">{u.part_sku}</span> {u.quantity} used · {u.dealer_name}</span>
                  <span className="text-xs text-slate-400 capitalize">{(u.failure_reason || '').replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-sd-lowstock">
          <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><AlertTriangle size={15} /> Low stock alerts</h3>
          {(data?.low_stock || []).length === 0 ? <p className="text-sm text-slate-400">No low-stock lines.</p> : (
            <div className="space-y-2">
              {data.low_stock.map((s) => (
                <div key={s.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                  <span className="text-slate-600"><span className="font-mono text-xs text-slate-400">{s.part_sku}</span> {s.store_name}</span>
                  <span className="text-xs text-red-600 font-semibold">{s.qty_on_hand} / min {s.min_stock}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
