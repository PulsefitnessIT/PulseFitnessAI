/**
 * Service Desk — UNIFIED (Iter 216h53)
 *
 * Single home for everything service-related. Merges what used to be
 * "Service Desk" (GymAxis internal: customers, equipment, supplier health)
 * with "Service Ops" (case board, scheduler, parts, billing, engineers).
 *
 * Lee's 8-tab spec:
 *   Dashboard | Cases | Scheduler | Customers | Equipment | Parts | Billing | Engineers
 *
 * Auth: master_admin or is_service_desk for now. Tenant owners get
 * access in a later iteration when this becomes Pulse-facing.
 *
 * Embedded ServiceOps pages: each ServiceOps page renders inside
 * <ServiceOpsShell>. We wrap them with <ServiceOpsEmbeddedContext.Provider>
 * so the shell collapses its hero+nav (the new sidebar owns that now).
 */
import { useState, useEffect, lazy, Suspense } from 'react';
import { useAuth } from '@/App';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Users, ClipboardList, Calendar, Package, FileText,
  HardHat, LogOut, ArrowLeft, Wrench, TrendingDown, ScrollText, Loader2,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

import DeskSummary from './ServiceDesk/DeskSummary';
import DeskCustomers from './ServiceDesk/DeskCustomers';
import DeskCustomerDetail from './ServiceDesk/DeskCustomerDetail';
import DeskAuditLog from './ServiceDesk/DeskAuditLog';
import DeskEquipment from './ServiceDesk/DeskEquipment';
import DeskSuppliers from './ServiceDesk/DeskSuppliers';
import { ServiceOpsEmbeddedContext } from './ServiceOps/ServiceOpsShell';

// Lazy-load the heavier Service Ops pages — keeps the initial shell light.
const OpsCases     = lazy(() => import('./ServiceOps/ServiceDeskPage'));
const OpsScheduler = lazy(() => import('./ServiceOps/ServiceScheduler'));
const OpsParts     = lazy(() => import('./ServiceOps/PartsInventoryPage'));
const OpsBilling   = lazy(() => import('./ServiceOps/BillingPage'));
const OpsEngineers = lazy(() => import('./ServiceOps/EngineersAdminPage'));
const OpsReports   = lazy(() => import('./ServiceOps/ServiceOpsReportsPage'));
const OpsSafety    = lazy(() => import('./ServiceOps/SafetyTemplateAdmin'));

// Sidebar order — matches Lee's spec verbatim.
const TABS = [
  { id: 'dashboard',  label: 'Dashboard',  icon: LayoutDashboard },
  { id: 'cases',      label: 'Cases',      icon: ClipboardList },
  { id: 'scheduler',  label: 'Scheduler',  icon: Calendar },
  { id: 'customers',  label: 'Customers',  icon: Users },
  { id: 'equipment',  label: 'Equipment',  icon: Wrench },
  { id: 'parts',      label: 'Parts',      icon: Package },
  { id: 'billing',    label: 'Billing',    icon: FileText },
  { id: 'engineers',  label: 'Engineers',  icon: HardHat },
];

// Insights nav lives under the user/menu footer — keeps the main tab
// row clean and matches Lee's 8-tab spec exactly.
const INSIGHTS_TABS = [
  { id: 'suppliers',  label: 'Supplier health', icon: TrendingDown },
  { id: 'reports',    label: 'Reports',         icon: ScrollText },
  { id: 'safety',     label: 'H&S checklist',   icon: ShieldCheck },
  { id: 'audit',      label: 'Audit log',       icon: ScrollText },
];

const EmbedFallback = () => (
  <div className="flex items-center justify-center py-20 text-slate-500 text-sm" data-testid="service-desk-tab-loading">
    <Loader2 size={16} className="mr-2 animate-spin" /> Loading…
  </div>
);

export default function ServiceDeskPage() {
  const { user, logout, API } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('dashboard');
  const [selectedOrgId, setSelectedOrgId] = useState(null);

  useEffect(() => {
    if (!user?.is_service_desk && !user?.is_master_admin) {
      navigate('/login', { replace: true });
    }
  }, [user, navigate]);

  const handleSelectCustomer = (id) => {
    setSelectedOrgId(id);
    setTab('customers');
  };

  // Render the active tab body. The ServiceOps pages render inside their
  // own <ServiceOpsShell> — we wrap with the embedded-context provider
  // so the shell collapses its duplicate hero + nav.
  const Body = () => {
    switch (tab) {
      case 'dashboard':
        return <DeskSummary API={API} onJumpToCustomers={() => setTab('customers')} />;
      case 'customers':
        return selectedOrgId
          ? <DeskCustomerDetail API={API} orgId={selectedOrgId} onBack={() => setSelectedOrgId(null)} />
          : <DeskCustomers API={API} onSelect={handleSelectCustomer} />;
      case 'equipment':
        return <DeskEquipment API={API} />;
      case 'suppliers':
        return <DeskSuppliers API={API} />;
      case 'audit':
        return <DeskAuditLog API={API} />;
      // Service Ops embedded pages
      case 'cases':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsCases /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'scheduler':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsScheduler /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'parts':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsParts /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'billing':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsBilling /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'engineers':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsEngineers /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'reports':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsReports /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      case 'safety':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsSafety /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-[var(--gx-bg)] flex theme-gymaxis" data-testid="service-desk-page" data-theme="light">
      <aside className="fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-slate-200 flex flex-col">
        {/* Logo header */}
        <div className="p-5 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm">
              <img src="/brand/gymaxis-mark-tight.webp" alt="GymAxis" className="w-6 h-6 object-contain" draggable={false} loading="eager" decoding="async" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-900 tracking-tight">Service Desk</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold">Field service ops</div>
            </div>
          </div>
        </div>

        {/* Primary tabs */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedOrgId(null); }}
              data-testid={`desk-tab-${id}`}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-all ${
                tab === id
                  ? 'bg-gradient-to-r from-[var(--gx-brand-from)]/10 to-[var(--gx-brand-to)]/10 text-[var(--gx-brand-from)] font-semibold ring-1 ring-[var(--gx-brand-from)]/15'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="flex-1">{label}</span>
            </button>
          ))}

          {/* Insights group (separated) */}
          <p className="text-[9px] uppercase tracking-[0.16em] text-slate-400 px-3 pt-4 pb-1 font-semibold">Insights</p>
          {INSIGHTS_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedOrgId(null); }}
              data-testid={`desk-tab-${id}`}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-all ${
                tab === id
                  ? 'bg-gradient-to-r from-[var(--gx-brand-from)]/10 to-[var(--gx-brand-to)]/10 text-[var(--gx-brand-from)] font-semibold ring-1 ring-[var(--gx-brand-from)]/15'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="flex-1">{label}</span>
            </button>
          ))}
        </nav>

        {/* User footer */}
        <div className="border-t border-slate-100 p-3 space-y-2">
          <div className="text-xs text-slate-500 px-1">
            <div className="font-medium text-slate-700 truncate">{user?.full_name || user?.email}</div>
            <div className="truncate">{user?.email}</div>
            {user?.is_master_admin && (
              <Badge variant="outline" className="mt-1 text-[9px] border-slate-200">Master Admin</Badge>
            )}
          </div>
          {user?.is_master_admin && (
            <Button
              variant="ghost" size="sm"
              onClick={() => navigate('/master-admin')}
              className="w-full justify-start text-slate-600 hover:text-slate-900"
              data-testid="desk-back-to-master-admin"
            >
              <ArrowLeft className="w-4 h-4 mr-2" /> Back to Master Admin
            </Button>
          )}
          <Button
            variant="ghost" size="sm"
            onClick={() => { logout(); navigate('/login'); }}
            className="w-full justify-start text-slate-600 hover:text-slate-900"
            data-testid="desk-logout"
          >
            <LogOut className="w-4 h-4 mr-2" /> Log out
          </Button>
        </div>
      </aside>

      <main className="flex-1 ml-60 p-8 max-w-[1400px]">
        <Body />
      </main>
    </div>
  );
}
