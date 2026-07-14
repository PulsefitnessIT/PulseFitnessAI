import { useEffect, useState, useCallback } from 'react';
import { Warehouse, PackageSearch, Truck, Building2, ClipboardList } from 'lucide-react';
import { dpApi } from './DealerWarrantyParts/api';
import { StatCard, Spinner, StatusBadge } from './DealerWarrantyParts/shared';
import StoresDeptTab from './DealerWarrantyParts/StoresDeptTab';

const OPEN_STATUSES = ['draft', 'submitted', 'acknowledged', 'quoted', 'invoiced', 'allocated'];

function fmtDate(v) {
  if (!v) return '';
  try { return new Date(v).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); } catch { return ''; }
}

function WarehouseSection() {
  const [reqs, setReqs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listPartsRequests().then((d) => setReqs(d.requests || [])).catch(() => setReqs([])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner />;

  const total = reqs.length;
  const open = reqs.filter((r) => OPEN_STATUSES.includes(r.status)).length;
  const despatched = reqs.filter((r) => r.status === 'despatched').length;
  const completed = reqs.filter((r) => r.status === 'completed').length;

  return (
    <div className="space-y-4" data-testid="stores-dept-warehouse">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testid="sd-wh-total" label="Warehouse parts requests" value={total} tone="brand" />
        <StatCard testid="sd-wh-open" label="Awaiting despatch" value={open} tone={open ? 'amber' : 'slate'} />
        <StatCard testid="sd-wh-despatched" label="Despatched" value={despatched} tone="slate" />
        <StatCard testid="sd-wh-completed" label="Completed" value={completed} tone="emerald" />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="sd-wh-list">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><PackageSearch size={15} /> Recent parts requests</h3>
        {reqs.length === 0 ? (
          <p className="text-sm text-slate-400">No warehouse parts requests yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="py-2">Reference</th><th>Supplier</th><th className="text-right">Machines</th><th className="text-right">Parts</th><th>Status</th><th className="text-right">Raised</th>
              </tr></thead>
              <tbody>
                {reqs.slice(0, 12).map((r) => (
                  <tr key={r.id} data-testid={`sd-wh-row-${r.id}`} className="border-b border-slate-50 last:border-0">
                    <td className="py-2 font-mono text-xs text-slate-600">{r.reference}</td>
                    <td className="text-slate-600 truncate max-w-[180px]">{r.supplier_name || '—'}</td>
                    <td className="text-right tabular-nums text-slate-500">{r.machine_count ?? 0}</td>
                    <td className="text-right tabular-nums text-slate-500">{r.part_count ?? 0}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="text-right text-xs text-slate-400">{fmtDate(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function StoresDepartment() {
  const [view, setView] = useState('warehouse');
  const views = [
    { id: 'warehouse', label: 'Pulse Warehouse parts', icon: Warehouse },
    { id: 'dealer', label: 'Dealer warranty fulfilment', icon: Building2 },
  ];

  return (
    <div className="space-y-5" data-testid="stores-department">
      <div>
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2"><ClipboardList size={18} className="text-[var(--gx-brand-from)]" /> Stores Department</h2>
        <p className="text-sm text-slate-500">Fulfilment across all parts leaving Pulse Fitness — warehouse supplier requests and dealer warranty allocations.</p>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-slate-200 pb-3">
        {views.map((v) => {
          const Icon = v.icon;
          return (
            <button key={v.id} data-testid={`stores-dept-view-${v.id}`} onClick={() => setView(v.id)}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${view === v.id ? 'bg-[var(--gx-brand-from)] text-white' : 'text-slate-500 hover:bg-slate-100'}`}>
              <Icon size={14} /> {v.label}
            </button>
          );
        })}
      </div>

      {view === 'warehouse' ? <WarehouseSection /> : <StoresDeptTab />}
    </div>
  );
}
