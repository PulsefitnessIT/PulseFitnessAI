import { useRef, useEffect, useState } from 'react';
import {
  Sparkles, LayoutDashboard, Dumbbell, AlertTriangle, ClipboardCheck,
  Users, BarChart3, Truck, LayoutGrid, FileText,
} from 'lucide-react';
import { TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUserPref } from '@/utils/userPrefs';

/**
 * Pulse Fitness Dashboard tab bar — aligned with Pulse Fitness Pro (iter 215d2).
 *
 * The tab ids keep the legacy Pulse Fitness values (`overview`, `issues`,
 * `maintenance`, `gym-design`) so existing <TabsContent> routing in
 * DashboardPage.js still matches. The labels, order, and icons are
 * identical to the Pulse Pro owner/manager bar in LiteDashboardPage.js
 * so operators see the same surface regardless of which brand they are
 * logged into.
 *
 *   Pulse Pro (owner/manager):
 *     Start · Dashboard · Equipment · Faults · Check Sheets · Staffing ·
 *     Reports · Suppliers · Gym Layout
 *
 *   Pulse Fitness /dashboard (this component) — identical order + labels.
 */
const DashboardTabs = ({ activeTab, setActiveTab, showSuppliers, hasDeliveries, t, _userRole }) => {
  const pillBarRef = useRef(null);
  const [scrollable, setScrollable] = useState(false);
  const [hideStart] = useUserPref('hideStartTabs', false);

  useEffect(() => {
    if (!pillBarRef.current) return;
    const active = pillBarRef.current.querySelector(`[data-testid="mobile-pill-${activeTab}"]`);
    if (active) active.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [activeTab]);

  useEffect(() => {
    const el = pillBarRef.current;
    if (!el) return;
    const check = () => setScrollable(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Mirror Pulse Pro owner/manager ordering exactly.
  const tabs = [];
  if (!hideStart) tabs.push({ id: 'start', label: t('dashboard.start'), icon: Sparkles });
  tabs.push(
    { id: 'overview',    label: t('dashboard.overview'),     icon: LayoutDashboard },
    { id: 'equipment',   label: t('dashboard.equipment'),    icon: Dumbbell },
    { id: 'issues',      label: t('dashboard.faults'),       icon: AlertTriangle },
    { id: 'maintenance', label: t('check_sheets.title'),     icon: ClipboardCheck },
    { id: 'documents',   label: t('dashboard.documents') || 'Documents', icon: FileText },
    { id: 'staffing',    label: t('dashboard.staffing'),     icon: Users },
    { id: 'reports',     label: t('dashboard.reports'),      icon: BarChart3 },
  );
  // Suppliers is owner/manager only — mirrors Pulse staff-tier behaviour.
  if (showSuppliers) tabs.push({ id: 'suppliers', label: t('dashboard.suppliers_tab'), icon: Truck });
  tabs.push({ id: 'gym-design', label: t('dashboard.gym_layout'), icon: LayoutGrid });
  if (hasDeliveries) tabs.push({ id: 'deliveries', label: t('dashboard.deliveries', 'Deliveries'), icon: Truck });

  const triggerClass = 'flex-shrink-0 inline-flex items-center gap-2 px-4 text-xs sm:text-sm py-2.5 rounded-full font-semibold data-[state=active]:bg-[var(--color-brand-blue)] data-[state=active]:text-white data-[state=active]:shadow-lg';

  return (
    <>
      {/* Desktop tab bar */}
      <TabsList
        className="mb-6 w-full hidden md:flex justify-start overflow-x-auto scrollbar-hide rounded-full h-auto p-1.5 gap-1"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', WebkitOverflowScrolling: 'touch' }}
        data-testid="dashboard-tabs"
      >
        {tabs.map(tab => {
          const Icon = tab.icon;
          return (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className={triggerClass}
              data-testid={`tab-${tab.id}`}
            >
              {Icon && <Icon size={14} />} {tab.label}
            </TabsTrigger>
          );
        })}
      </TabsList>

      {/* Mobile pill bar */}
      <div
        ref={pillBarRef}
        className="md:hidden mb-5 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1 scroll-smooth"
        style={{
          WebkitOverflowScrolling: 'touch',
          maskImage: scrollable
            ? 'linear-gradient(to right, transparent 0, black 18px, black calc(100% - 18px), transparent 100%)'
            : undefined,
          WebkitMaskImage: scrollable
            ? 'linear-gradient(to right, transparent 0, black 18px, black calc(100% - 18px), transparent 100%)'
            : undefined,
        }}
        data-testid="mobile-gymaxis-tab-pills"
        data-scrollable={scrollable ? 'true' : 'false'}
      >
        {tabs.map(tab => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                active ? 'text-white' : 'text-[var(--color-text-muted)] hover:text-white'
              }`}
              style={active ? { background: 'var(--color-brand-blue)' } : { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
              data-testid={`mobile-pill-${tab.id}`}
            >
              {Icon && <Icon size={12} />} {tab.label}
            </button>
          );
        })}
      </div>
    </>
  );
};

export default DashboardTabs;
