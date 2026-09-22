/**
 * Dealer Warranty Parts — global dealer spare-parts ecosystem.
 * Lives under Service Desk → Parts. Phase 1: dealers, orders + allowance,
 * allocations workflow, remote stores, stock ledger, dashboard, settings.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { LayoutDashboard, Building2, FileText, Package, Warehouse, ArrowRightLeft, Settings, Globe, Wrench, RotateCcw, Truck, PackagePlus, Store, BarChart3, Wand2 } from 'lucide-react';
import DashboardTab from './DashboardTab';
import DealersTab from './DealersTab';
import OrdersTab from './OrdersTab';
import AllocationsTab from './AllocationsTab';
import UsageTab from './UsageTab';
import DealerPortalTab from './DealerPortalTab';
import StoresTab from './StoresTab';
import StockMovementTab from './StockMovementTab';
import AllocationWizardTab from './AllocationWizardTab';
import AnalyticsTab from './AnalyticsTab';
import SettingsHubTab from './SettingsHubTab';
import SubTabBar from '../../components/shared/SubTabBar';
import { DealerPartsNavContext } from './navGuard';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, C: DashboardTab },
  { id: 'wizard', label: 'Allocation Wizard', icon: Wand2, C: AllocationWizardTab },
  { id: 'dealers', label: 'Dealers', icon: Building2, C: DealersTab },
  { id: 'orders', label: 'Orders & Allowance', icon: FileText, C: OrdersTab },
  { id: 'allocations', label: 'Allocations', icon: Package, C: AllocationsTab },
  { id: 'stores', label: 'Remote Stores', icon: Warehouse, C: StoresTab },
  { id: 'usage', label: 'Engineer Usage', icon: Wrench, C: UsageTab },
  { id: 'stock-movement', label: 'Stock Movement', icon: ArrowRightLeft, C: StockMovementTab },
  { id: 'portal', label: 'Dealer Portal', icon: Store, C: DealerPortalTab },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, C: AnalyticsTab },
  { id: 'settings', label: 'Settings', icon: Settings, C: SettingsHubTab },
];

export default function DealerWarrantyPartsPage() {
  const [tab, setTab] = useState('dashboard');
  const Active = TABS.find((t) => t.id === tab)?.C || DashboardTab;
  // Iter 282 — unsaved-work guard. A child tab (Allocation Wizard) reports
  // in-progress work; we warn before switching tabs and arm a browser
  // beforeunload prompt so work isn't lost by accident.
  const dirtyRef = useRef(false);
  const setDirty = useCallback((v) => { dirtyRef.current = !!v; }, []);

  useEffect(() => {
    const handler = (e) => {
      if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; return ''; }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const guardedSetTab = (id) => {
    if (id === tab) return;
    if (dirtyRef.current && !window.confirm('You have unsaved work in this section. Leave without finishing? Your progress will be lost.')) {
      return;
    }
    dirtyRef.current = false;
    setTab(id);
  };

  return (
    <DealerPartsNavContext.Provider value={{ setDirty }}>
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

      <SubTabBar
        tabs={TABS}
        active={tab}
        onChange={guardedSetTab}
        testId="dp-tab"
      />

      <Active />
    </div>
    </DealerPartsNavContext.Provider>
  );
}
