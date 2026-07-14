/**
 * Dealer Warranty Parts — global dealer spare-parts ecosystem.
 * Lives under Service Desk → Parts. Phase 1: dealers, orders + allowance,
 * allocations workflow, remote stores, stock ledger, dashboard, settings.
 */
import { useState } from 'react';
import { LayoutDashboard, Building2, FileText, Package, Warehouse, ArrowRightLeft, Settings, Globe, Wrench, RotateCcw, Truck, PackagePlus, Store, BarChart3, Wand2 } from 'lucide-react';
import DashboardTab from './DashboardTab';
import DealersTab from './DealersTab';
import OrdersTab from './OrdersTab';
import AllocationsTab from './AllocationsTab';
import UsageTab from './UsageTab';
import StoresDeptTab from './StoresDeptTab';
import RmaTab from './RmaTab';
import ReplenishmentTab from './ReplenishmentTab';
import DealerPortalTab from './DealerPortalTab';
import StoresTab from './StoresTab';
import LedgerTab from './LedgerTab';
import AllocationWizardTab from './AllocationWizardTab';
import AnalyticsTab from './AnalyticsTab';
import SettingsHubTab from './SettingsHubTab';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, C: DashboardTab },
  { id: 'wizard', label: 'Allocation Wizard', icon: Wand2, C: AllocationWizardTab },
  { id: 'dealers', label: 'Dealers', icon: Building2, C: DealersTab },
  { id: 'orders', label: 'Orders & Allowance', icon: FileText, C: OrdersTab },
  { id: 'allocations', label: 'Allocations', icon: Package, C: AllocationsTab },
  { id: 'stores_dept', label: 'Stores Dept', icon: Truck, C: StoresDeptTab },
  { id: 'stores', label: 'Remote Stores', icon: Warehouse, C: StoresTab },
  { id: 'usage', label: 'Engineer Usage', icon: Wrench, C: UsageTab },
  { id: 'replenishment', label: 'Replenishment', icon: PackagePlus, C: ReplenishmentTab },
  { id: 'rma', label: 'Returns / RMA', icon: RotateCcw, C: RmaTab },
  { id: 'ledger', label: 'Stock Ledger', icon: ArrowRightLeft, C: LedgerTab },
  { id: 'portal', label: 'Dealer Portal', icon: Store, C: DealerPortalTab },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, C: AnalyticsTab },
  { id: 'settings', label: 'Settings', icon: Settings, C: SettingsHubTab },
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
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Dealer Parts</h1>
          <p className="text-sm text-slate-500">Manage global dealer parts — warranty allocations, remote stock, engineer usage, replenishment and failure intelligence.</p>
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
