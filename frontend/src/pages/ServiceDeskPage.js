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
 * Auth: capability `view_service_desk` — master_admin, is_service_desk,
 * or Pulse Master Admin (Pulse Fitness runs the service operation).
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
  ShieldCheck, Menu, X, BarChart3, UploadCloud,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { can, isPulseAdmin } from '@/utils/capabilities';

import DeskSummary from './ServiceDesk/DeskSummary';
import DeskCustomers from './ServiceDesk/DeskCustomers';
import DeskCustomerDetail from './ServiceDesk/DeskCustomerDetail';
import DeskAuditLog from './ServiceDesk/DeskAuditLog';
import DeskEquipment from './ServiceDesk/DeskEquipment';
import DeskSuppliers from './ServiceDesk/DeskSuppliers';
// Iter 254 — Owner Analytics (SLA / utilisation / revenue-per-job)
const DeskAnalytics = lazy(() => import('./ServiceDesk/DeskAnalytics'));
// Iter 255 — Migration import wizard (customers/sites + historical cases)
const DeskImports = lazy(() => import('./ServiceDesk/DeskImports'));
// Iter 256 — Provider-native Customers tab (field-service customer book)
const DeskProviderCustomers = lazy(() => import('./ServiceDesk/DeskProviderCustomers'));
import { ServiceOpsEmbeddedContext } from './ServiceOps/ServiceOpsShell';

// Lazy-load the heavier Service Ops pages — keeps the initial shell light.
const OpsCases     = lazy(() => import('./ServiceOps/ServiceDeskPage'));
const OpsScheduler = lazy(() => import('./ServiceOps/ServiceScheduler'));
const OpsParts     = lazy(() => import('./ServiceOps/PartsInventoryPage'));
const OpsBilling   = lazy(() => import('./ServiceOps/BillingPage'));
const OpsEngineers = lazy(() => import('./ServiceOps/EngineersAdminPage'));
const OpsReports   = lazy(() => import('./ServiceOps/ServiceOpsReportsPage'));
const OpsSafety    = lazy(() => import('./ServiceOps/SafetyTemplateAdmin'));
const OpsCompliance = lazy(() => import('./ServiceOps/ComplianceAdmin'));

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
  { id: 'analytics',  label: 'Analytics',       icon: BarChart3 },
  { id: 'imports',    label: 'Import data',     icon: UploadCloud },
  { id: 'suppliers',  label: 'Supplier health', icon: TrendingDown },
  { id: 'reports',    label: 'Reports',         icon: ScrollText },
  { id: 'safety',     label: 'H&S checklist',   icon: ShieldCheck },
  { id: 'compliance', label: 'Compliance',      icon: ShieldCheck },
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
  // Iter 216h256 — mobile-first: sidebar is an off-canvas drawer below
  // `md`. State drives the hamburger toggle + backdrop.
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!can(user, 'view_service_desk')) {
      navigate('/login', { replace: true });
    }
  }, [user, navigate]);

  const handleSelectCustomer = (id) => {
    setSelectedOrgId(id);
    setTab('customers');
  };

  // Iter 257c — Equipment + Supplier-health are platform concepts (they
  // search the gym-operator estate), so they're empty for self-serve
  // providers. Hide them to keep the trial desk purpose-built.
  const isProvider = user?.account_type === 'service_provider';
  const PROVIDER_HIDDEN = isProvider ? new Set(['equipment', 'suppliers']) : new Set();
  const visibleTabs = TABS.filter((t) => !PROVIDER_HIDDEN.has(t.id));
  const visibleInsights = INSIGHTS_TABS.filter((t) => !PROVIDER_HIDDEN.has(t.id));

  // Render the active tab body. The ServiceOps pages render inside their
  // own <ServiceOpsShell> — we wrap with the embedded-context provider
  // so the shell collapses its duplicate hero + nav.
  const Body = () => {
    switch (tab) {
      case 'dashboard':
        return <DeskSummary API={API} onJumpToCustomers={() => setTab('customers')} />;
      case 'customers':
        // Iter 256 — self-serve providers manage their field-service
        // customer book; the platform/Pulse desk manages customer orgs.
        if (user?.account_type === 'service_provider') {
          return <Suspense fallback={<EmbedFallback />}><DeskProviderCustomers API={API} /></Suspense>;
        }
        return selectedOrgId
          ? <DeskCustomerDetail API={API} orgId={selectedOrgId} onBack={() => setSelectedOrgId(null)} />
          : <DeskCustomers API={API} onSelect={handleSelectCustomer} />;
      case 'equipment':
        return isProvider ? <DeskSummary API={API} onJumpToCustomers={() => setTab('customers')} /> : <DeskEquipment API={API} />;
      case 'suppliers':
        return isProvider ? <DeskSummary API={API} onJumpToCustomers={() => setTab('customers')} /> : <DeskSuppliers API={API} />;
      case 'audit':
        return <DeskAuditLog API={API} />;
      case 'analytics':
        return <Suspense fallback={<EmbedFallback />}><DeskAnalytics API={API} /></Suspense>;
      case 'imports':
        return <Suspense fallback={<EmbedFallback />}><DeskImports API={API} /></Suspense>;
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
      case 'compliance':
        return (
          <ServiceOpsEmbeddedContext.Provider value={true}>
            <Suspense fallback={<EmbedFallback />}><OpsCompliance /></Suspense>
          </ServiceOpsEmbeddedContext.Provider>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-[var(--gx-bg)] flex theme-gymaxis" data-testid="service-desk-page" data-theme="light">
      {/* Iter 216h256 — Mobile backdrop. Tapping the dimmed area closes
          the off-canvas sidebar. Hidden on md+. */}
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          data-testid="desk-sidebar-backdrop"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 md:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        {/* Logo header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm">
              <img src="/brand/gymaxis-mark-tight.webp" alt="GymAxis" className="w-6 h-6 object-contain" draggable={false} loading="eager" decoding="async" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-900 tracking-tight">Service Desk</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold">Field service ops</div>
            </div>
          </div>
          {/* Mobile-only close button inside the drawer. */}
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="md:hidden text-slate-400 hover:text-slate-700"
            aria-label="Close sidebar"
            data-testid="desk-sidebar-close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Primary tabs */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {visibleTabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedOrgId(null); setSidebarOpen(false); }}
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
          {visibleInsights.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedOrgId(null); setSidebarOpen(false); }}
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
            {!user?.is_master_admin && isPulseAdmin(user) && (
              <Badge variant="outline" className="mt-1 text-[9px] border-slate-200" data-testid="desk-pulse-admin-badge">Pulse Master Admin</Badge>
            )}
          </div>
          {(user?.is_master_admin || isPulseAdmin(user)) && (
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

      <main className="flex-1 md:ml-60 p-4 sm:p-6 md:p-8 max-w-[1400px] w-full">
        {/* Iter 216h256 — Mobile-only top bar with hamburger trigger. */}
        <div className="md:hidden flex items-center justify-between mb-4 sticky top-0 z-20 bg-[var(--gx-bg)] py-2">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="inline-flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            aria-label="Open navigation"
            data-testid="desk-sidebar-open"
          >
            <Menu size={18} />
          </button>
          <div className="text-sm font-bold text-slate-900 capitalize truncate">{tab.replace(/_/g, ' ')}</div>
          <div className="w-9" aria-hidden />
        </div>
        <Body />
      </main>
    </div>
  );
}
