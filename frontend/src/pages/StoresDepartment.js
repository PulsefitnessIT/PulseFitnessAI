import { useEffect, useState, useCallback } from 'react';
import { Warehouse, PackageSearch, Truck, Building2, ClipboardList, ListChecks, ArrowRight, Clock } from 'lucide-react';
import { dpApi } from './DealerWarrantyParts/api';
import { StatCard, Spinner, StatusBadge, money } from './DealerWarrantyParts/shared';
import StoresDeptTab from './DealerWarrantyParts/StoresDeptTab';

const OPEN_STATUSES = ['draft', 'submitted', 'acknowledged', 'quoted', 'invoiced', 'allocated'];
const DESPATCH_READY = ['allocated', 'invoiced', 'quoted', 'acknowledged'];

function fmtDate(v) {
  if (!v) return '';
  try { return new Date(v).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); } catch { return ''; }
}

// Iter 283 — ageing / SLA highlight for the Stores fulfilment queue.
// amber when waiting more than 2 days, red when 5+ days.
function ageDays(v) {
  if (!v) return 0;
  const t = new Date(v).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.floor((Date.now() - t) / 86400000);
}
function slaTone(days) {
  if (days >= 5) return 'red';
  if (days > 2) return 'amber';
  return null;
}

function ActionQueue({ onGoWarehouse, onGoDealer }) {
  const [items, setItems] = useState(null);

  const load = useCallback(() => {
    Promise.all([
      dpApi.listPartsRequests().catch(() => ({ requests: [] })),
      dpApi.storesDashboard().catch(() => ({ to_pick: [] })),
    ]).then(([wh, dealer]) => {
      const rows = [];
      (wh.requests || []).filter((r) => DESPATCH_READY.includes(r.status)).forEach((r) => rows.push({
        key: `wh-${r.id}`, source: 'warehouse', title: r.supplier_name || r.reference,
        sub: `${r.reference} · ${r.part_count ?? 0} parts`, status: r.status,
        action: 'Despatch', date: r.created_at,
      }));
      (dealer.to_pick || []).forEach((a) => rows.push({
        key: `dl-${a.id}`, source: 'dealer', title: a.dealer_name,
        sub: `${(a.items || []).length} parts · ${money(a.approved_value || a.recommended_value)}`, status: 'approved',
        action: 'Pick & dispatch', date: a.approved_at,
      }));
      rows.sort((x, y) => new Date(x.date || 0) - new Date(y.date || 0));
      setItems(rows);
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  if (items === null) return <Spinner />;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="stores-dept-action-queue">
      <div className="flex items-center gap-2 mb-3">
        <ListChecks size={16} className="text-[var(--gx-brand-from)]" />
        <h3 className="text-sm font-bold text-slate-900">To action today</h3>
        <span className="ml-2 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[var(--gx-brand-from)]/10 text-[var(--gx-brand-from)]">{items.length}</span>
        <span className="ml-auto text-xs text-slate-400">Oldest first · <span className="text-amber-600 font-semibold">amber &gt;2 days</span> · <span className="text-red-600 font-semibold">red 5+ days</span></span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing awaiting picking or despatch right now. 🎉</p>
      ) : (
        <div className="divide-y divide-slate-50">
          {items.slice(0, 15).map((it) => {
            const days = ageDays(it.date);
            const tone = slaTone(days);
            const rowAccent = tone === 'red' ? 'border-l-4 border-red-400 bg-red-50/40 pl-2 -ml-2 rounded-r'
              : tone === 'amber' ? 'border-l-4 border-amber-400 bg-amber-50/40 pl-2 -ml-2 rounded-r' : '';
            return (
            <div key={it.key} data-testid={`sd-queue-${it.key}`} className={`flex items-center gap-3 py-2.5 ${rowAccent}`}>
              <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${it.source === 'warehouse' ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-teal-50 text-teal-700 border-teal-200'}`}>
                {it.source === 'warehouse' ? <Warehouse size={11} /> : <Building2 size={11} />}
                {it.source === 'warehouse' ? 'Warehouse' : 'Dealer'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-slate-800 truncate">{it.title}</div>
                <div className="text-xs text-slate-400 truncate">{it.sub}</div>
              </div>
              {tone && (
                <span data-testid={`sd-queue-sla-${it.key}`}
                  className={`inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full ${tone === 'red' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}
                  title={`Waiting ${days} days — ${tone === 'red' ? 'breached SLA (5+ days)' : 'ageing (over 2 days)'}`}>
                  <Clock size={11} /> {days}d
                </span>
              )}
              <StatusBadge status={it.status} />
              <span className="text-xs text-slate-400 w-14 text-right">{fmtDate(it.date)}</span>
              <button data-testid={`sd-queue-go-${it.key}`}
                onClick={() => (it.source === 'warehouse' ? onGoWarehouse() : onGoDealer())}
                className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--gx-brand-from)] hover:underline">
                {it.action} <ArrowRight size={13} />
              </button>
            </div>
          );})}
        </div>
      )}
    </div>
  );
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

      <ActionQueue onGoWarehouse={() => setView('warehouse')} onGoDealer={() => setView('dealer')} />

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
