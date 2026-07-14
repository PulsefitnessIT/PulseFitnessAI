import { useEffect, useState } from 'react';
import { PackagePlus } from 'lucide-react';
import { dpApi } from './api';
import { Spinner, money } from './shared';

const LABEL_TONE = {
  'Critical Replenishment': 'bg-red-50 text-red-700 border-red-200',
  'Replenishment Recommended': 'bg-amber-50 text-amber-700 border-amber-200',
  'Low Stock': 'bg-amber-50 text-amber-700 border-amber-200',
  Monitor: 'bg-blue-50 text-blue-700 border-blue-200',
  Overstocked: 'bg-violet-50 text-violet-700 border-violet-200',
  'No Action Needed': 'bg-slate-100 text-slate-500 border-slate-200',
};

export default function ReplenishmentTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [onlyAction, setOnlyAction] = useState(true);

  useEffect(() => { dpApi.replenishment({ days: 90 }).then((d) => setRows(d.rows || [])).finally(() => setLoading(false)); }, []);

  if (loading) return <Spinner />;
  const shown = onlyAction ? rows.filter((r) => r.recommended_qty > 0 || r.urgency === 'critical') : rows;

  return (
    <div className="space-y-4" data-testid="dp-replenishment-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500 flex items-center gap-2"><PackagePlus size={15} /> Replenishment recommendations</h3>
        <label className="ml-auto text-xs text-slate-500 flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={onlyAction} onChange={(e) => setOnlyAction(e.target.checked)} /> Only items needing action
        </label>
      </div>
      {shown.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No replenishment needed right now.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Part</th><th>Store</th><th>On hand</th><th>Used (90d)</th><th>Status</th><th>Recommend</th><th className="text-right">Value</th>
            </tr></thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={`${r.part_sku}-${i}`} data-testid={`dp-replen-row-${i}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4"><span className="font-mono text-xs text-slate-500">{r.part_sku}</span> {r.part_name}</td>
                  <td className="text-slate-500 text-xs">{r.store_name}</td>
                  <td className="tabular-nums">{r.on_hand}</td>
                  <td className="tabular-nums text-slate-500">{r.used_period}</td>
                  <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${LABEL_TONE[r.label] || LABEL_TONE['No Action Needed']}`}>{r.label}</span></td>
                  <td className="tabular-nums font-semibold text-[var(--gx-brand-from)]">{r.recommended_qty > 0 ? `+${r.recommended_qty}` : '—'}</td>
                  <td className="text-right tabular-nums">{r.estimated_value ? money(r.estimated_value) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
