import { useState } from 'react';
import { ArrowRightLeft, PackagePlus, RotateCcw } from 'lucide-react';
import LedgerTab from './LedgerTab';
import ReplenishmentTab from './ReplenishmentTab';
import RmaTab from './RmaTab';

// Iter 282 — consolidates Stock Ledger, Replenishment and Returns/RMA into a
// single "Stock Movement" area with sub-tabs. No functionality is removed —
// each sub-tab renders the original component verbatim.
const SUB_TABS = [
  { id: 'ledger', label: 'Stock Ledger', icon: ArrowRightLeft, C: LedgerTab },
  { id: 'replenishment', label: 'Replenishment', icon: PackagePlus, C: ReplenishmentTab },
  { id: 'rma', label: 'Returns / RMA', icon: RotateCcw, C: RmaTab },
];

export default function StockMovementTab() {
  const [sub, setSub] = useState('ledger');
  const Active = SUB_TABS.find((t) => t.id === sub)?.C || LedgerTab;

  return (
    <div className="space-y-4" data-testid="dp-stock-movement">
      <div className="inline-flex gap-1 rounded-lg bg-slate-100 p-1">
        {SUB_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            data-testid={`dp-stock-sub-${id}`}
            onClick={() => setSub(id)}
            className={`px-3.5 py-1.5 text-sm font-semibold rounded-md flex items-center gap-1.5 transition-colors ${
              sub === id ? 'bg-white text-[var(--gx-brand-from)] shadow-sm' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>
      <Active />
    </div>
  );
}
