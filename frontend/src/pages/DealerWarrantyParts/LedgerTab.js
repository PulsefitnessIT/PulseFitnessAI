import { useEffect, useState } from 'react';
import { ArrowRightLeft } from 'lucide-react';
import { dpApi } from './api';
import { Spinner } from './shared';

const TONE = {
  dispatched_to_dealer: 'text-indigo-600 bg-indigo-50',
  received_by_dealer: 'text-emerald-600 bg-emerald-50',
  part_used: 'text-amber-600 bg-amber-50',
  returned_to_pulse: 'text-slate-600 bg-slate-100',
};

export default function LedgerTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { dpApi.listMovements().then((d) => setRows(d.movements || [])).finally(() => setLoading(false)); }, []);

  if (loading) return <Spinner />;
  return (
    <div className="space-y-4" data-testid="dp-ledger-tab">
      <h3 className="text-sm font-semibold text-slate-500 flex items-center gap-2"><ArrowRightLeft size={15} /> Stock movement ledger</h3>
      {rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No stock movements yet. Every dispatch, receipt and usage is recorded here.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">When</th><th>Type</th><th>Part</th><th>Qty</th><th>Store</th><th>By</th>
            </tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} data-testid={`dp-movement-${m.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 text-slate-400 text-xs whitespace-nowrap">{new Date(m.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                  <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full capitalize ${TONE[m.movement_type] || 'text-slate-600 bg-slate-100'}`}>{m.movement_type.replace(/_/g, ' ')}</span></td>
                  <td><span className="font-mono text-xs text-slate-500">{m.part_sku}</span> {m.part_name}</td>
                  <td className="tabular-nums font-medium">{m.quantity}</td>
                  <td className="text-slate-500 text-xs">{m.store_name}</td>
                  <td className="text-slate-400 text-xs">{m.user_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
