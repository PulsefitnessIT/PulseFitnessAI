/**
 * Dealer Warranty Parts — global dealer spare-parts ecosystem.
 * Lives under Service Desk → Parts. Phase 1: dealers, orders + allowance,
 * allocations workflow, remote stores, stock ledger, dashboard, settings.
 */
import { useState } from 'react';
import { LayoutDashboard, Building2, FileText, Package, Warehouse, ArrowRightLeft, Settings, Globe, Layers, Star, Wrench, RotateCcw, Truck, Radar, PackagePlus, Store, FileSpreadsheet, UploadCloud, BarChart3, GitCompare, HelpCircle, Cog } from 'lucide-react';
import DashboardTab from './DashboardTab';
import DealersTab from './DealersTab';
import OrdersTab from './OrdersTab';
import AllocationsTab from './AllocationsTab';
import BomTab from './BomTab';
import MostUsedTab from './MostUsedTab';
import UsageTab from './UsageTab';
import StoresDeptTab from './StoresDeptTab';
import RmaTab from './RmaTab';
import FailureIntelTab from './FailureIntelTab';
import AlertsTab from './AlertsTab';
import ReplenishmentTab from './ReplenishmentTab';
import DealerPortalTab from './DealerPortalTab';
import ReportsTab from './ReportsTab';
import StoresTab from './StoresTab';
import LedgerTab from './LedgerTab';
import SettingsTab from './SettingsTab';
import DataImportsTab from './DataImportsTab';
import MostUsedAnalysisTab from './MostUsedAnalysisTab';
import MatchReviewTab from './MatchReviewTab';
import UnmatchedReviewTab from './UnmatchedReviewTab';
import MachinePartsTab from './MachinePartsTab';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, C: DashboardTab },
  { id: 'imports', label: 'Data Imports', icon: UploadCloud, C: DataImportsTab },
  { id: 'analysis', label: 'Most-Used Analysis', icon: BarChart3, C: MostUsedAnalysisTab },
  { id: 'match_review', label: 'Match Review', icon: GitCompare, C: MatchReviewTab },
  { id: 'unmatched', label: 'Unmatched Review', icon: HelpCircle, C: UnmatchedReviewTab },
  { id: 'machine_parts', label: 'Machine Parts', icon: Cog, C: MachinePartsTab },
  { id: 'dealers', label: 'Dealers', icon: Building2, C: DealersTab },
  { id: 'orders', label: 'Orders & Allowance', icon: FileText, C: OrdersTab },
  { id: 'allocations', label: 'Allocations', icon: Package, C: AllocationsTab },
  { id: 'bom', label: 'BOM Management', icon: Layers, C: BomTab },
  { id: 'most_used', label: 'Most Used Parts', icon: Star, C: MostUsedTab },
  { id: 'usage', label: 'Engineer Usage', icon: Wrench, C: UsageTab },
  { id: 'stores_dept', label: 'Stores Dept', icon: Truck, C: StoresDeptTab },
  { id: 'intel', label: 'Failure Intelligence', icon: Globe, C: FailureIntelTab },
  { id: 'alerts', label: 'Monitoring & Alerts', icon: Radar, C: AlertsTab },
  { id: 'replenishment', label: 'Replenishment', icon: PackagePlus, C: ReplenishmentTab },
  { id: 'portal', label: 'Dealer Portal', icon: Store, C: DealerPortalTab },
  { id: 'reports', label: 'Reports', icon: FileSpreadsheet, C: ReportsTab },
  { id: 'rma', label: 'Returns / RMA', icon: RotateCcw, C: RmaTab },
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
