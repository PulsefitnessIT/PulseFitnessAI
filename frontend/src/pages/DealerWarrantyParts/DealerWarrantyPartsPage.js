/**
 * Dealer Warranty Parts — global dealer spare-parts ecosystem.
 * Lives under Service Desk → Parts. Phase 1: dealers, orders + allowance,
 * allocations workflow, remote stores, stock ledger, dashboard, settings.
 */
import { useState } from 'react';
import { LayoutDashboard, Building2, FileText, Package, Warehouse, ArrowRightLeft, Settings, Globe, Layers, Star } from 'lucide-react';
import DashboardTab from './DashboardTab';
import DealersTab from './DealersTab';
import OrdersTab from './OrdersTab';
import AllocationsTab from './AllocationsTab';
import BomTab from './BomTab';
import MostUsedTab from './MostUsedTab';
import StoresTab from './StoresTab';
import LedgerTab from './LedgerTab';
import SettingsTab from './SettingsTab';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, C: DashboardTab },
  { id: 'dealers', label: 'Dealers', icon: Building2, C: DealersTab },
  { id: 'orders', label: 'Orders & Allowance', icon: FileText, C: OrdersTab },
  { id: 'allocations', label: 'Allocations', icon: Package, C: AllocationsTab },
  { id: 'bom', label: 'BOM Management', icon: Layers, C: BomTab },
  { id: 'most_used', label: 'Most Used Parts', icon: Star, C: MostUsedTab },
  { id: 'stores', label: 'Remote Stores', icon: Warehouse, C: StoresTab },
  { id: 'ledger', label: 'Stock Ledger', icon: ArrowRightLeft, C: LedgerTab },
  { id: 'settings', label: 'Settings', icon: Settings, C: SettingsTab },
];

export default function DealerWarrantyPartsPage() {
  const [tab, setTab] = useState('dashboard');
  const Active = TABS.find((t) => t.id === tab)?.C || DashboardTab;

  return (
    <div className="space-y-6" data-testid="dealer-warranty-parts">
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] flex items-center justify-center shadow-sm">
          <Globe className="text-white" size={22} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Dealer Warranty Parts</h1>
          <p className="text-sm text-slate-500">Manage global dealer warranty parts, remote stock, engineer usage, replenishment and failure intelligence.</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            data-testid={`dp-tab-${id}`}
            onClick={() => setTab(id)}
            className={`px-3.5 py-2.5 text-sm font-semibold -mb-px border-b-2 whitespace-nowrap flex items-center gap-1.5 transition-colors ${
              tab === id
                ? 'border-[var(--gx-brand-from)] text-[var(--gx-brand-from)]'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <Active />
    </div>
  );
}
