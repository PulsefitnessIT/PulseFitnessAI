/**
 * GymAxis Memberships — Operator console.
 *
 * Tabbed SPA page: Dashboard · Members · Timetable · Plans. Reuses the
 * operator JWT already in localStorage (set by the standard Pulse/Gym
 * login). Dark GymAxis aesthetic — cyan accent, slate surfaces.
 *
 * Phase 1a scope: list + create + key actions. Deeper flows (sell plan,
 * refund, comms) land in Phase 1b.
 */
import React, { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard, Users, Users as UsersIcon, Calendar, PackageOpen, Plus, X, ChevronLeft,
  ChevronRight, Pause, XOctagon, Activity, Sparkles, CheckCircle2, Edit3, Trash2, Dumbbell, Link as LinkIcon, Copy, Megaphone, BarChart3, Printer, Settings, Tag, Brain, ClipboardCheck, Workflow, Smartphone, ReceiptPoundSterling as Receipt, Wand2, HeartHandshake, ShieldCheck, Theater, Loader2, Wallet,
} from 'lucide-react';
import { useAuth } from '@/App';
import EmptyState from '@/components/shared/EmptyState';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';
import ListPanel from '@/components/shared/ListPanel';
import InvitePortalButton from '@/components/memberships/InvitePortalButton';
import ExportCsvButton from '@/components/shared/ExportCsvButton';
import {
  Header, Kpi, StatusPill, CapacityBar, Loading, Empty, Input, Select, ModalShell, ModalActions,
} from '@/pages/Memberships/_shared';
import AddMemberModal from '@/pages/Memberships/modals/AddMemberModal';
import PlanEditorModal from '@/pages/Memberships/modals/PlanEditorModal';
import ClassEditorModal from '@/pages/Memberships/modals/ClassEditorModal';
import SavedViewsDropdown from '@/components/memberships/SavedViewsDropdown';
import MembersBulkBar from '@/components/memberships/MembersBulkBar';
import PullToRefresh from '@/components/shared/PullToRefresh';
import Navbar from '@/components/shared/Navbar';
import MobileBottomNav from '@/components/shared/MobileBottomNav';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import CrossModuleTipsBanner from '@/components/shared/CrossModuleTipsBanner';
import ModuleAccessGate from '@/components/shared/ModuleAccessGate';
import HelpHint from '@/components/HelpHint';
import TourConversionTile from '@/pages/Memberships/TourConversionTile';
import ProductTour from '@/components/shared/ProductTour';

// Iter 216h173 — Heavy operator tabs are lazy-loaded. Only one tab is
// mounted at a time and the dashboard/start surface is the default, so
// none of these need to be parsed on initial page load.
const AnalyticsTab = lazy(() => import('@/pages/Memberships/AnalyticsTab'));
const BookingRulesTab = lazy(() => import('@/pages/Memberships/BookingRulesTab'));
const PromotionsTab = lazy(() => import('@/pages/Memberships/PromotionsTab'));
const InstructorsTab = lazy(() => import('@/pages/Memberships/InstructorsTab'));
const AIInsightsTab = lazy(() => import('@/pages/Memberships/AIInsightsTab'));
const CheckinTab = lazy(() => import('@/pages/Memberships/CheckinTab'));
const CRMLoopTab = lazy(() => import('@/pages/Memberships/CRMLoopTab'));
const MembershipsStartTab = lazy(() => import('@/pages/Memberships/MembershipsStartTab'));
const MobileAppBuilderTab = lazy(() => import('@/pages/Memberships/MobileAppBuilderTab'));
const InvoicingTab = lazy(() => import('@/pages/Memberships/InvoicingTab'));
const DeskSalesReportTab = lazy(() => import('@/pages/Memberships/DeskSalesReportTab'));
const CoursesView = lazy(() => import('@/pages/Memberships/CoursesView'));
const ClassActionDrawer = lazy(() => import('@/pages/Memberships/ClassActionDrawer'));
const MemberEditDrawer = lazy(() => import('@/pages/Memberships/MemberEditDrawer'));
const SellPackAtDeskModal = lazy(() => import('@/pages/Memberships/modals/SellPackAtDeskModal'));
const StudioBuilderTab = lazy(() => import('@/pages/Memberships/StudioBuilderTab'));
const FamilyBillingTab = lazy(() => import('@/pages/Memberships/FamilyBillingTab'));
const ParentPortalTab = lazy(() => import('@/pages/Memberships/ParentPortalTab'));
const EventsTab = lazy(() => import('@/pages/Memberships/EventsTab'));
const StudioBrainTab = lazy(() => import('@/pages/Memberships/StudioBrainTab'));

const TabFallback = () => (
  <div className="flex items-center justify-center py-16 text-zinc-400" data-testid="memberships-tab-loading">
    <Loader2 size={18} className="animate-spin" />
  </div>
);

import PillTabBar from '@/components/shared/PillTabBar';
import { useUserPref } from '@/utils/userPrefs';
import useStudioMode from '@/pages/Memberships/useStudioMode';
import StudioModeToggle from '@/pages/Memberships/StudioModeToggle';
import StudioQuickstart from '@/pages/Memberships/StudioQuickstart';

export default function MembershipsConsole() {
  return (
    <ModuleAccessGate module="memberships">
      <MembershipsConsoleInner />
    </ModuleAccessGate>
  );
}

function MembershipsConsoleInner() {
  const { user, logout, API, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [tab, setTab] = useState('start');
  // Iter 215d8 — bumped by PullToRefresh to force child tabs to remount/refetch.
  const [reloadKey, setReloadKey] = useState(0);
  const [hideStart] = useUserPref('hideStartTabs', false);
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  // Iter 216ah G1 — auto-hide Start once the operator has ticked every step
  // (or explicitly dismissed the checklist). Single source of truth lives
  // in /api/memberships/studio/onboarding so this stays in sync across
  // tabs/sessions. Re-fetched on mount + whenever the user dismisses.
  const [onboardingHidden, setOnboardingHidden] = useState(false);
  useEffect(() => {
    let live = true;
    const fetchIt = () => {
      axios.get(`${API}/memberships/studio/onboarding`, { headers })
        .then((r) => { if (live) setOnboardingHidden(!!(r.data?.all_complete || r.data?.dismissed)); })
        .catch(() => {});
    };
    fetchIt();
    const onDismiss = () => fetchIt();
    window.addEventListener('memberships-start-dismissed', onDismiss);
    return () => { live = false; window.removeEventListener('memberships-start-dismissed', onDismiss); };
  }, [API, headers]);
  const hideStartFinal = hideStart || onboardingHidden;
  useEffect(() => { if (hideStartFinal && tab === 'start') setTab('dashboard'); }, [hideStartFinal, tab]);
  const pillBarRef = React.useRef(null);
  const studio = useStudioMode();
  // Studio Mode: 5-tab simplified layout for small teams.
  const STUDIO_TAB_IDS = useMemo(() => new Set(['start', 'dashboard', 'schedule', 'studio-builder', 'studio-brain', 'timetable', 'classes', 'members', 'plans', 'family-billing', 'parent-portal', 'events', 'checkin', 'invoicing']), []);

  const TABS = useMemo(() => [
    { id: 'start',     label: 'Start', icon: Sparkles },
    { id: 'dashboard', label: t('memberships_console.tab_dashboard'), icon: LayoutDashboard },
    // Iter 216ai — Sprint A item 6: merged Studio Builder + Timetable +
    // Classes list into one "Classes & Timetable" tab with internal sub-pills.
    // Old tab IDs (studio-builder, timetable, classes) still route here for
    // deep-links / Start checklist CTAs — SchedulingHubTab picks the right
    // sub-view based on the incoming tab value.
    { id: 'schedule', label: 'Classes & Timetable', icon: Calendar },
    { id: 'studio-brain', label: 'Studio brain', icon: Brain },
    { id: 'members',   label: t('memberships_console.tab_members'),   icon: Users },
    { id: 'plans',     label: t('memberships_console.tab_plans'),     icon: PackageOpen },
    { id: 'family-billing', label: 'Family billing', icon: HeartHandshake },
    { id: 'parent-portal', label: 'Parent portal', icon: ShieldCheck },
    { id: 'events', label: 'Events', icon: Theater },
    { id: 'instructors', label: 'Instructors', icon: Activity },
    { id: 'promotions', label: 'Promotions', icon: Tag },
    { id: 'checkin', label: 'Check-in', icon: ClipboardCheck },
    { id: 'invoicing', label: 'Invoicing', icon: Receipt },
    { id: 'desk-sales', label: 'Desk sales', icon: Wallet },
    { id: 'ads',       label: t('memberships_console.tab_ads'),       icon: Megaphone },
    { id: 'analytics', label: t('memberships_console.tab_analytics'), icon: BarChart3 },
    { id: 'ai-insights', label: 'AI Insights', icon: Brain },
    { id: 'crm-loop', label: 'CRM Loop', icon: Workflow },
    { id: 'booking-rules', label: 'Booking rules', icon: Settings },
    { id: 'mobile-app', label: 'Mobile app', icon: Smartphone },
  ], [t]);

  // Filter the tab list when Studio Mode is on — keeps UI focused on
  // the essentials for 1-3 person teams.
  const visibleTabs = useMemo(
    () => (studio.studioMode ? TABS.filter((x) => STUDIO_TAB_IDS.has(x.id)) : TABS),
    [studio.studioMode, TABS, STUDIO_TAB_IDS],
  );

  // If the user flips Studio Mode while on a now-hidden tab, bounce them
  // home to 'start' so they don't end up looking at a blank screen.
  useEffect(() => {
    if (studio.studioMode && !STUDIO_TAB_IDS.has(tab)) setTab('start');
  }, [studio.studioMode, tab, STUDIO_TAB_IDS]);

  // Keep the active pill scrolled into view on mobile when the tab changes.
  React.useEffect(() => {
    if (!pillBarRef.current) return;
    const active = pillBarRef.current.querySelector(`[data-testid="mbr-pill-${tab}"]`);
    active?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [tab]);

  /**
   * Listen for `gymaxis-jump` from the Unified AI Assistant. Honour:
   *   - target='members|plans|classes|...' → switch tab
   *   - deep_link.kind='member' → switch to Members + open detail drawer
   *   - deep_link.kind='plan'   → switch to Plans (drawer support TBD per PlansTab)
   */
  React.useEffect(() => {
    const handler = (e) => {
      const detail = e.detail || {};
      if (detail.mode && detail.mode !== 'memberships') return;
      if (typeof detail.target === 'string' && detail.target) {
        setTab(detail.target);
      }
      const dl = detail.deep_link;
      if (dl?.kind === 'member' && dl.id) {
        setTab('members');
        // MembersTab listens for `mbr-open-member` and opens the drawer.
        setTimeout(() => window.dispatchEvent(new CustomEvent('mbr-open-member', { detail: dl.id })), 200);
      } else if (dl?.kind === 'plan' && dl.id) {
        setTab('plans');
      }
    };
    window.addEventListener('gymaxis-jump', handler);
    return () => window.removeEventListener('gymaxis-jump', handler);
  }, []);

  if (!user) { navigate('/'); return null; }

  // Iter 215ba — brand-aware Memberships console. Pulse-account customers
  // (account_type pulse_pro / lite) keep the legacy "Pulse Fitness" heading +
  // solid cyan active tab. GymAxis customers + master admins see the new
  // GymAxis brand: gradient wordmark heading + brand-gradient active tab.
  const isPulseBrandedMbr = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const brandLabel = isPulseBrandedMbr ? 'Pulse Fitness' : 'GymAxis';

  return (
    <div
      className={`min-h-screen ${!isPulseBrandedMbr && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}
      data-testid="memberships-console"
    >
      <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />
      <ProductTour variant="memberships" />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in">
        {/* Unified app header — matches Pulse / Operations header so the module
            switcher position stays stable across routes. */}
        <div className="mb-6" data-testid="memberships-app-header">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>
                {isPulseBrandedMbr
                  ? brandLabel
                  : <span className="gx-grad-text">{brandLabel}</span>
                }{' '}
                {(user?.account_type === 'pulse_pro' || user?.account_type === 'full' || user?.is_master_admin) && (
                  <span style={{ color: isPulseBrandedMbr ? 'var(--color-brand-cyan-hover)' : 'var(--gx-brand-to)' }}>Pro</span>
                )}
                {user?.company_name && (
                  <span className="text-base sm:text-lg font-normal ml-2 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
                    · {user.company_name}
                  </span>
                )}
              </h1>
              <p className="pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>Welcome back, {user?.full_name}</p>
            </div>
            <div className="text-sm pulse-font-body shrink-0 mt-1.5 flex items-center gap-3" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
              <StudioModeToggle studioMode={studio.studioMode} toggle={studio.toggle} saving={studio.saving} loading={studio.loading} />
              {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </div>
          </div>
          <ModuleSwitcher user={user} current="memberships" />
        </div>

        <CrossModuleTipsBanner mode="memberships" />

        {/* Desktop pill tab bar — canonical PillTabBar so overflow
            auto-scrolls the active tab into view, fades edges, and
            shows chevron affordances when the row is scrollable. */}
        <PillTabBar
          className="hidden md:block mb-6"
          activeId={tab}
          testId="mbr-tabs-desktop"
          ariaLabel="Memberships sections"
        >
          {TABS.filter((x) => !(hideStartFinal && x.id === 'start')).filter((x) => visibleTabs.some((v) => v.id === x.id)).map(({ id, label, icon: Icon }) => {
            const isActive = tab === id;
            const activeStyle = isPulseBrandedMbr
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF', boxShadow: '0 6px 16px -6px rgba(37,99,235,0.35)' };
            return (
              <button
                key={id}
                data-pill-id={id}
                onClick={() => setTab(id)}
                className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
                style={isActive
                  ? activeStyle
                  : { color: 'var(--theme-text-muted)', background: 'transparent' }}
                data-testid={`mbr-tab-${id}`}
              >
                <Icon size={14} /> {label}
              </button>
            );
          })}
        </PillTabBar>

        {/* Mobile scrollable pill tabs */}
        <div ref={pillBarRef} className="md:hidden mb-5 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
          {TABS.filter((x) => !(hideStartFinal && x.id === 'start')).filter((x) => visibleTabs.some((v) => v.id === x.id)).map(({ id, label }) => {
            const isActive = tab === id;
            const activeStyle = isPulseBrandedMbr
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF' };
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap transition-colors"
                style={isActive
                  ? activeStyle
                  : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
                data-testid={`mbr-pill-${id}`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Iter 215d8 — Pull-to-refresh. Bumps `reloadKey` to force the
            currently-active tab to re-fetch. Resolves after a short delay
            so the spinner remains visible for the typical request round-trip. */}
        <PullToRefresh
          onRefresh={async () => {
            setReloadKey((k) => k + 1);
            await new Promise((r) => setTimeout(r, 650));
          }}
        >

        <Suspense fallback={<TabFallback />}>
        {tab === 'start' && studio.studioMode && !studio.quickstartCompleted && (
          <StudioQuickstart onComplete={() => setTab('dashboard')} />
        )}
        {tab === 'start' && !(studio.studioMode && !studio.quickstartCompleted) && <MembershipsStartTab setTab={setTab} />}
        {tab === 'dashboard' && <DashboardTab key={`dash-${reloadKey}`} API={API} headers={headers} />}
        {['schedule', 'studio-builder', 'timetable', 'classes'].includes(tab) && (
          <SchedulingHubTab key={`sch-${reloadKey}`} API={API} headers={headers} activeTabHint={tab} onSetTab={setTab} />
        )}
        {tab === 'studio-brain' && <StudioBrainTab key={`br-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'members'   && <MembersTab   key={`mbr-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'plans'     && <PlansTab     key={`pln-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'family-billing' && <FamilyBillingTab key={`fb-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'parent-portal' && <ParentPortalTab key={`pp-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'events' && <EventsTab key={`ev-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'instructors' && <InstructorsTab key={`ins-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'promotions' && <PromotionsTab key={`pro-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'checkin'    && <CheckinTab    key={`chk-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'invoicing'  && <InvoicingTab  key={`inv-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'desk-sales' && <DeskSalesReportTab key={`ds-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'ads'       && <AdsTab       API={API} headers={headers} />}
        {tab === 'analytics' && <AnalyticsTab key={`ana-${reloadKey}`} API={API} headers={headers} />}
        {tab === 'ai-insights' && <AIInsightsTab API={API} headers={headers} />}
        {tab === 'crm-loop'  && <CRMLoopTab    API={API} headers={headers} />}
        {tab === 'booking-rules' && <BookingRulesTab API={API} headers={headers} />}
        {tab === 'mobile-app' && <MobileAppBuilderTab API={API} headers={headers} />}
        </Suspense>
        </PullToRefresh>
      </main>

      <MobileBottomNav variant="memberships" activeTab={tab} setActiveTab={setTab} />
    </div>
  );
}


/* ─────────────────── Dashboard ─────────────────── */

function DashboardTab({ API, headers }) {
  const [data, setData] = useState(null);
  const [setupStatus, setSetupStatus] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const [dash, setup] = await Promise.all([
          axios.get(`${API}/memberships/dashboard`, { headers }),
          axios.get(`${API}/memberships/setup/status`, { headers }).catch(() => null),
        ]);
        setData(dash.data);
        if (setup) setSetupStatus(setup.data);
      } catch { notify.error('Failed to load dashboard'); }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);
  if (!data) return <Loading />;
  return (
    <div data-testid="mbr-dashboard">
      <Header eyebrow="Overview" title="Studio dashboard" subtitle="Live pulse on members, classes, and revenue." />
      {setupStatus && !setupStatus.organization.setup_completed && <SetupNudge />}
      {/* Iter 215bi — removed duplicate AppUrlCard (with live phone preview)
          from the dashboard. Lives under the Mobile App tab now. */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3 mt-6">
        <Kpi label="Active members"     value={data.active_members} color="cyan" />
        <Kpi label="New this month"     value={data.new_signups_month} color="emerald" />
        <Kpi label="Cancellations"      value={data.cancellations_month} color={data.cancellations_month > 0 ? 'amber' : 'neutral'} />
        <Kpi label="Frozen"             value={data.frozen_memberships} color={data.frozen_memberships > 0 ? 'amber' : 'neutral'} />
        <Kpi label="Expiring < 7d"      value={data.expiring_7d} color={data.expiring_7d > 0 ? 'amber' : 'neutral'} />
        <Kpi label="Today's classes"    value={data.today_classes} color="cyan" />
        <Kpi label="Today's occupancy"  value={`${data.occupancy_pct}%`} color={data.occupancy_pct >= 70 ? 'emerald' : 'neutral'} />
        <Kpi label="Today's bookings"   value={data.today_bookings} color="neutral" />
        <Kpi label="No-shows (MTD)"     value={data.no_shows_month} color={data.no_shows_month > 0 ? 'amber' : 'emerald'} />
        <Kpi label="Waitlisted now"     value={data.waitlisted} color={data.waitlisted > 0 ? 'violet' : 'neutral'} />
      </div>
      <section className="mt-8">
        <h2 className="text-[color:var(--theme-text-muted)] font-bold text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5">
          Today at a glance
          <HelpHint guideId="mbr-first-class" testId="help-hint-today-classes" />
        </h2>
        {(data.today_occurrences || []).length === 0 ? (
          <Empty text="No classes scheduled for today." />
        ) : (
          <div className="space-y-2">
            {data.today_occurrences.map((o) => (
              <div key={o.id} className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-3.5 flex items-center gap-3">
                <div className="w-1 h-10 rounded" style={{ background: o.colour || 'var(--color-brand-cyan)' }} />
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-white text-sm truncate">{o.name}</div>
                  <div className="text-xs text-[color:var(--theme-text-muted)]">{new Date(o.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {o.instructor_name || '—'} · {o.room_name || '—'}</div>
                </div>
                <CapacityBar bookings={o.bookings_count || 0} capacity={o.capacity} />
              </div>
            ))}
          </div>
        )}
      </section>
      <CommissionSection API={API} headers={headers} />
      <section className="mt-8">
        <TourConversionTile />
      </section>
    </div>
  );
}

function CommissionSection({ API, headers }) {
  const [month] = useState(() => new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  useEffect(() => {
    (async () => {
      try { const { data } = await axios.get(`${API}/memberships/commission`, { headers, params: { month } }); setData(data); }
      catch { /* silent if no instructors yet */ }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [month]);

  const downloadCsv = async () => {
    try {
      const res = await axios.get(`${API}/memberships/commission.csv`, {
        headers, params: { month }, responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = `commission-${month}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { notify.error('CSV download failed'); }
  };

  if (!data || (data.rows || []).length === 0) return null;
  return (
    <section className="mt-8" data-testid="mbr-commission">
      <div className="flex items-end justify-between mb-3">
        <h2 className="text-[color:var(--theme-text-muted)] font-bold text-xs uppercase tracking-wider">Instructor commission · {month}</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[color:var(--theme-text-muted)]">Total <strong className="text-white">£{(data.grand_total_pence / 100).toFixed(2)}</strong></span>
          <Button variant="secondary" size="sm" onClick={downloadCsv} data-testid="mbr-commission-csv" className="uppercase tracking-wider">
            CSV
          </Button>
        </div>
      </div>
      <div className="rounded-xl border border-[color:var(--theme-border)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[480px]">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-[color:var(--theme-text-muted)]">
              <tr>
                <th className="px-4 py-3 text-left font-bold">Instructor</th>
                <th className="px-4 py-3 text-right font-bold">Rate</th>
                <th className="px-4 py-3 text-right font-bold">Completed</th>
                <th className="px-4 py-3 text-right font-bold">Attended</th>
                <th className="px-4 py-3 text-right font-bold">Payout</th>
              </tr>
            </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.instructor.id} className="border-t border-[color:var(--theme-border)]" data-testid={`mbr-commission-${r.instructor.id}`}>
                <td className="px-4 py-3 font-bold text-white">{r.instructor.name}</td>
                <td className="px-4 py-3 text-right text-[color:var(--theme-text-muted)]">£{(r.rate_pence / 100).toFixed(2)}</td>
                <td className="px-4 py-3 text-right text-[color:var(--theme-text-muted)]">{r.class_count}</td>
                <td className="px-4 py-3 text-right text-[color:var(--theme-text-muted)]">{r.total_attended}</td>
                <td className="px-4 py-3 text-right font-extrabold text-[var(--color-brand-cyan)]">£{(r.pay_pence / 100).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </section>
  );
}


/* ─────────────────── Members ─────────────────── */

function MembersTab({ API, headers }) {
  const [members, setMembers] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [detail, setDetail] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  // Sprint C — saved views + multi-select.
  const [savedView, setSavedView] = useState(null); // {id, name, filter} or null
  const [selectedIds, setSelectedIds] = useState([]);
  const importFileRef = React.useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Sprint C — if a saved view (preset or custom) is active, route
      // through the dedicated endpoint so the server applies the preset
      // logic. Otherwise use the simpler list endpoint (no regression).
      if (savedView && savedView.filter && Object.keys(savedView.filter).length > 0) {
        const params = { ...savedView.filter };
        if (q) params.q = q;
        const res = await axios.get(`${API}/memberships/members-filtered`, { headers, params });
        setMembers(res.data.members || []);
      } else {
        const res = await axios.get(`${API}/memberships/members`, { headers, params: q ? { q } : {} });
        setMembers(res.data.members || []);
      }
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [q, savedView?.id]);
  useEffect(() => { load(); }, [load]);

  // Clear selection whenever the member list changes identity (filter/view).
  useEffect(() => { setSelectedIds([]); }, [savedView?.id, q]);

  const toggleOne = (id, checked) => {
    setSelectedIds((prev) => (checked ? [...new Set([...prev, id])] : prev.filter((x) => x !== id)));
  };
  const toggleAll = (checked) => {
    setSelectedIds(checked ? members.map((m) => m.id) : []);
  };
  const allSelected = members.length > 0 && selectedIds.length === members.length;
  const someSelected = selectedIds.length > 0 && !allSelected;

  // Listen for "open this member" requests from the Unified AI Assistant.
  useEffect(() => {
    const handler = (e) => {
      if (typeof e.detail === 'string' && e.detail) setDetail(e.detail);
    };
    window.addEventListener('mbr-open-member', handler);
    return () => window.removeEventListener('mbr-open-member', handler);
  }, []);

  // Iter 215bl — deep-link the member edit drawer via URL hash.
  // Any link (e.g. CRM contact card, class roster, invoice) can navigate
  // to #member/<id> and the drawer opens. Closing the drawer cleans up
  // the hash so a refresh doesn't re-open it.
  useEffect(() => {
    const open = () => {
      const m = (window.location.hash || '').match(/^#member\/([\w-]+)/);
      if (m) setDetail(m[1]);
    };
    open();
    window.addEventListener('hashchange', open);
    return () => window.removeEventListener('hashchange', open);
  }, []);

  const downloadTemplate = async () => {
    try {
      const res = await axios.get(`${API}/memberships/members/csv-template`, { headers, responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = 'members-import-template.csv';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      notify.error('Failed to download template', e.response?.data?.detail || 'Try again.');
    }
  };

  const handleImport = async (file) => {
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const { data } = await axios.post(`${API}/memberships/members/bulk-import`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      setImportResult(data);
      notify.success(`Bulk import complete`, `${data.created} added · ${data.skipped} skipped.`);
      load();
    } catch (e) {
      notify.error('Import failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setImporting(false);
      if (importFileRef.current) importFileRef.current.value = '';
    }
  };

  return (
    <div data-testid="mbr-members">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <Header eyebrow="Directory" title="Members" subtitle="Every person who walks through the door." />
        <div className="flex gap-2 items-center flex-wrap">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name / email / phone"
            className="h-9 rounded-full bg-transparent border border-[color:var(--theme-border)] px-3 text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] w-64 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
            data-testid="mbr-search" />
          <SavedViewsDropdown
            API={API}
            headers={headers}
            value={savedView?.id || null}
            onChange={setSavedView}
            currentFilter={{ ...(savedView?.filter || {}), ...(q ? { q } : {}) }}
          />
          <Button variant="secondary" size="sm" onClick={downloadTemplate} data-testid="mbr-csv-template">
            CSV template
          </Button>
          <ExportCsvButton module="members" label="Export CSV" testId="mbr-export-csv" />
          <Button variant="secondary" size="sm" onClick={() => importFileRef.current?.click()}
            disabled={importing}
            loading={importing}
            data-testid="mbr-bulk-import">
            {importing ? 'Importing' : 'Bulk import'}
          </Button>
          <input ref={importFileRef} type="file" accept=".csv,text/csv"
            onChange={(e) => handleImport(e.target.files?.[0])} className="hidden"
            data-testid="mbr-import-input" />
          <Button variant="primary" size="sm" onClick={() => setAdding(true)} icon={Plus} data-testid="mbr-add-member">
            Add member
          </Button>
          <HelpHint guideId="mbr-onboard-first" testId="help-hint-members" />
        </div>
      </div>

      {importResult && (
        <div className="mt-4 rounded-lg border border-[color:var(--theme-border)] p-3 text-sm" data-testid="mbr-import-result">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-white">
              Bulk import: {importResult.created} created · {importResult.skipped} skipped
            </p>
          <Button variant="ghost" size="iconSm" onClick={() => setImportResult(null)} icon={X} title="Dismiss" data-testid="mbr-import-result-dismiss" />
          </div>
          {importResult.skipped > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-[color:var(--theme-text-muted)] max-h-40 overflow-y-auto">
              {importResult.rows.filter(r => !r.ok).slice(0, 25).map((r) => (
                <li key={r.row}>Row {r.row}: <span className="text-amber-300">{r.reason}</span></li>
              ))}
            </ul>
          )}
        </div>
      )}
      {/* Iter 215bt — friendly empty state for fresh tenants. */}
      {!loading && members.length === 0 && !importResult && (
        <div className="mt-6">
          <EmptyState
            icon={UsersIcon}
            title="No members yet"
            hint="Add your first member or bulk-import from CSV. Members can also self-register through your branded app URL."
            primaryAction={{ label: 'Add member', onClick: () => setAdding(true), testId: 'mbr-empty-add' }}
            secondaryAction={{ label: 'Bulk import CSV', onClick: () => importFileRef.current?.click(), testId: 'mbr-empty-import' }}
            testId="mbr-empty-state"
          />
        </div>
      )}

      {!(!loading && members.length === 0 && !importResult) && (
      <>
      <MembersBulkBar
        API={API}
        headers={headers}
        selectedIds={selectedIds}
        onClearSelection={() => setSelectedIds([])}
        onRefresh={load}
      />
      <div className="mt-6 rounded-xl border border-[color:var(--theme-border)] overflow-hidden">
        {/* Desktop table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full text-sm min-w-[560px]">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-[color:var(--theme-text-muted)]">
              <tr>
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => { if (el) el.indeterminate = someSelected; }}
                    onChange={(e) => toggleAll(e.target.checked)}
                    className="h-4 w-4 accent-[color:var(--color-brand-cyan)] cursor-pointer"
                    aria-label="Select all"
                    data-testid="mbr-select-all"
                  />
                </th>
                <th className="px-4 py-3 text-left font-bold">Member</th>
                <th className="px-4 py-3 text-left font-bold">Plan</th>
                <th className="px-4 py-3 text-left font-bold">Status</th>
                <th className="px-4 py-3 text-left font-bold">Credits</th>
                <th className="px-4 py-3 text-right font-bold">No-shows</th>
                <th className="px-2 py-3 text-right font-bold">Portal</th>
              </tr>
            </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="text-center text-[color:var(--theme-text-muted)] py-6">Loading…</td></tr>}
            {members.map((m) => {
              const checked = selectedIds.includes(m.id);
              return (
              <tr key={m.id} onClick={() => setDetail(m.id)} className={`border-t border-[color:var(--theme-border)] hover:bg-white/[0.03] cursor-pointer ${checked ? 'bg-[color:var(--color-brand-cyan)]/5' : ''}`} data-testid={`mbr-row-${m.id}`}>
                <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => toggleOne(m.id, e.target.checked)}
                    className="h-4 w-4 accent-[color:var(--color-brand-cyan)] cursor-pointer"
                    aria-label={`Select ${m.first_name} ${m.last_name}`}
                    data-testid={`mbr-select-${m.id}`}
                  />
                </td>
                <td className="px-4 py-3">
                  <div className="font-bold text-white">{m.first_name} {m.last_name}</div>
                  <div className="text-xs text-[color:var(--theme-text-muted)]">{m.email}</div>
                </td>
                <td className="px-4 py-3">
                  {m.active_membership ? (
                    <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ background: (m.active_membership.plan?.colour || 'var(--color-brand-cyan)') + '22', color: m.active_membership.plan?.colour || 'var(--color-brand-cyan)' }}>
                      {m.active_membership.plan?.name || '—'}
                    </span>
                  ) : <span className="text-xs text-[color:var(--theme-text-muted)]">No plan</span>}
                </td>
                <td className="px-4 py-3"><StatusPill status={m.active_membership?.status || m.status} /></td>
                <td className="px-4 py-3 text-xs text-[color:var(--theme-text-muted)]">{m.active_membership ? `${m.active_membership.credits_remaining ?? '∞'}` : '—'}</td>
                <td className={`px-4 py-3 text-right text-xs font-bold ${(m.no_show_count || 0) > 2 ? 'text-red-300' : 'text-[color:var(--theme-text-muted)]'}`}>{m.no_show_count || 0}</td>
                <td className="px-2 py-3 text-right"><InvitePortalButton API={API} headers={headers} member={m} onDone={load} /></td>
              </tr>
            ); })}
          </tbody>
        </table>
        </div>
        {/* Mobile card list (iter 215ak) */}
        <div className="md:hidden divide-y divide-[color:var(--theme-border)]" data-testid="mbr-members-mobile-list">
          {loading && <div className="p-6 text-center text-[color:var(--theme-text-muted)] text-sm">Loading…</div>}
          {members.map((m) => {
            const checked = selectedIds.includes(m.id);
            return (
            <div key={m.id} className={`flex items-start px-4 py-3 gap-3 ${checked ? 'bg-[color:var(--color-brand-cyan)]/5' : ''}`} data-testid={`mbr-row-mobile-${m.id}`}>
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => toggleOne(m.id, e.target.checked)}
                className="h-4 w-4 accent-[color:var(--color-brand-cyan)] mt-1 shrink-0"
                aria-label={`Select ${m.first_name} ${m.last_name}`}
                data-testid={`mbr-select-mobile-${m.id}`}
              />
              <button onClick={() => setDetail(m.id)}
                className="flex-1 text-left active:bg-white/5 hover:bg-white/5 transition-colors min-w-0">
                <div className="min-w-0">
                  <div className="font-bold text-white truncate">{m.first_name} {m.last_name}</div>
                  <div className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{m.email}</div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {m.active_membership ? (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ background: (m.active_membership.plan?.colour || 'var(--color-brand-cyan)') + '22', color: m.active_membership.plan?.colour || 'var(--color-brand-cyan)' }}>
                        {m.active_membership.plan?.name || '—'}
                      </span>
                    ) : <span className="text-[10px] text-[color:var(--theme-text-muted)]">No plan</span>}
                    <StatusPill status={m.active_membership?.status || m.status} />
                    {m.active_membership && (
                      <span className="text-[10px] text-[color:var(--theme-text-muted)]">{m.active_membership.credits_remaining ?? '∞'} credits</span>
                    )}
                  </div>
                </div>
              </button>
              {(m.no_show_count || 0) > 0 && (
                <span className={`shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded ${(m.no_show_count || 0) > 2 ? 'bg-red-500/15 text-red-300' : 'bg-white/5 text-[color:var(--theme-text-muted)]'}`}>
                  {m.no_show_count} no-show{m.no_show_count === 1 ? '' : 's'}
                </span>
              )}
              <div className="shrink-0">
                <InvitePortalButton API={API} headers={headers} member={m} onDone={load} />
              </div>
            </div>
          ); })}
        </div>
      </div>
      </>
      )}
      {adding && <AddMemberModal API={API} headers={headers} onClose={(refresh) => { setAdding(false); if (refresh) load(); }} />}
      {detail && <MemberDetailDrawer API={API} headers={headers} memberId={detail} onClose={(refresh) => {
        setDetail(null);
        if (window.location.hash.startsWith('#member/')) {
          // Iter 215bl — strip the deep-link hash on close so a refresh
          // doesn't re-open the drawer for a member that's since been edited.
          window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
        if (refresh) load();
      }} />}
    </div>
  );
}


/**
 * Iter 215bk — drawer is now a richer tabbed editor (Profile · Classes ·
 * Payments · Family). The old in-file implementation is preserved below as
 * `LegacyMemberDetailDrawer` for reference but is no longer rendered.
 * `MemberDetailDrawer` is a thin wrapper that delegates to the new component
 * and supplies the plan-action callbacks the legacy drawer hosted inline.
 */
function MemberDetailDrawer({ API, headers, memberId, onClose }) {
  const confirm = useConfirm();
  const [recordingPlan, setRecordingPlan] = useState(null);
  const [sellPackOpen, setSellPackOpen] = useState(false);
  const [plans, setPlans] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  // Load plans once so the Sell-at-desk modal can filter by kind=class_pack.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/memberships/plans`, { headers });
        if (!cancelled) setPlans(r.data?.plans || []);
      } catch { /* surfaced in the modal as "no packs" */ }
    })();
    return () => { cancelled = true; };
  }, [API, headers]);

  const assign = async (plan_id) => {
    try {
      await axios.post(`${API}/memberships/members/${memberId}/assign-plan`, { plan_id }, { headers });
      notify.success('Plan assigned');
      setReloadKey((k) => k + 1);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  const freeze = async () => {
    const days = Number(window.prompt('Freeze for how many days?', '30'));
    if (!days) return;
    try {
      await axios.post(`${API}/memberships/members/${memberId}/freeze`, { days }, { headers });
      notify.success(`Frozen for ${days} days`);
      setReloadKey((k) => k + 1);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  const cancel = async () => {
    const ok = await confirm({
      title: "Cancel this member's plan?",
      detail: 'Their notice period will be respected. The member can re-join later.',
      tone: 'danger',
      confirmLabel: 'Cancel plan',
    });
    if (!ok) return;
    try {
      await axios.post(`${API}/memberships/members/${memberId}/cancel`, { reason: 'operator_cancel' }, { headers });
      notify.success('Cancellation scheduled');
      setReloadKey((k) => k + 1);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  return (
    <>
      <MemberEditDrawer
        // re-mount on reloadKey so plan changes refresh inside the drawer
        key={reloadKey}
        API={API}
        headers={headers}
        memberId={memberId}
        onClose={onClose}
        onAssignPlan={assign}
        onFreeze={freeze}
        onCancel={cancel}
        onRecord={(plan) => setRecordingPlan(plan)}
        onSellPackAtDesk={() => setSellPackOpen(true)}
      />
      {recordingPlan && (
        <RecordPaymentModal
          API={API}
          headers={headers}
          memberId={memberId}
          plan={recordingPlan}
          onClose={(refresh) => { setRecordingPlan(null); if (refresh) setReloadKey((k) => k + 1); }}
        />
      )}
      {sellPackOpen && (
        <Suspense fallback={null}>
          <SellPackAtDeskModal
            API={API}
            headers={headers}
            memberId={memberId}
            plans={plans}
            onClose={(refresh) => { setSellPackOpen(false); if (refresh) setReloadKey((k) => k + 1); }}
          />
        </Suspense>
      )}
    </>
  );
}


// ── Legacy (pre-iter-215bk) drawer kept for reference ──────────
// Not exported, not rendered. Safe to delete once the new drawer
// has been live for a release.
// eslint-disable-next-line unused-imports/no-unused-vars
function LegacyMemberDetailDrawer({ API, headers, memberId, onClose }) {
  const confirm = useConfirm();
  const [data, setData] = useState(null);
  const [plans, setPlans] = useState([]);
  const reload = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([
        axios.get(`${API}/memberships/members/${memberId}`, { headers }),
        axios.get(`${API}/memberships/plans`, { headers }),
      ]);
      setData(a.data); setPlans(b.data.plans || []);
    } catch { notify.error('Failed'); onClose(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [memberId]);
  useEffect(() => { reload(); }, [reload]);

  const [recordingPlan, setRecordingPlan] = useState(null);  // opens RecordPaymentModal
  const assign = async (plan_id) => {
    try { await axios.post(`${API}/memberships/members/${memberId}/assign-plan`, { plan_id }, { headers });
      notify.success('Plan assigned'); reload(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };
  const recordPayment = (plan) => setRecordingPlan(plan);
  const freeze = async () => {
    const days = Number(window.prompt('Freeze for how many days?', '30'));
    if (!days) return;
    try { await axios.post(`${API}/memberships/members/${memberId}/freeze`, { days }, { headers });
      notify.success(`Frozen for ${days} days`); reload(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };
  const cancel = async () => {
    const ok = await confirm({
      title: 'Cancel this member\'s plan?',
      detail: 'Their notice period will be respected. The member can re-join later.',
      tone: 'danger',
      confirmLabel: 'Cancel plan',
    });
    if (!ok) return;
    try { await axios.post(`${API}/memberships/members/${memberId}/cancel`, { reason: 'operator_cancel' }, { headers });
      notify.success('Cancellation scheduled'); reload(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  if (!data) return null;
  const m = data.member;
  const active = data.memberships.find((x) => ['active', 'frozen'].includes(x.status));
  return (
    <div className="fixed inset-0 z-[60] bg-black/40 dark:bg-black/60 flex justify-end" onClick={() => onClose(false)}>
      <div className="w-full max-w-xl h-full bg-[color:var(--theme-surface)] border-l border-[color:var(--theme-border)] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="mbr-detail-drawer">
        <header className="sticky top-0 z-10 bg-[color:var(--theme-bg)] border-b border-[color:var(--theme-border)] px-5 py-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Member profile</div>
            <h3 className="text-xl font-extrabold tracking-tight">{m.first_name} {m.last_name}</h3>
            <div className="text-xs text-[color:var(--theme-text-muted)] mt-1">{m.email} · {m.phone || '—'}</div>
          </div>
          <Button variant="ghost" size="icon" onClick={() => onClose(false)} icon={X} title="Close" data-testid="mbr-drawer-close" />
        </header>
        <div className="p-5 space-y-5">
          <section>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-2">Current plan</div>
            {active ? (
              <div className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <div className="font-bold text-white text-sm">{active.plan?.name}</div>
                    <div className="text-xs text-[color:var(--theme-text-muted)] mt-0.5">Since {new Date(active.start_date).toLocaleDateString()} · <StatusPill status={active.status} /></div>
                  </div>
                  <div className="text-xs text-[color:var(--theme-text-muted)]">Credits <span className="font-bold text-white">{active.credits_remaining ?? '∞'}</span></div>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button variant="secondary" size="sm" onClick={freeze} icon={Pause} data-testid="mbr-freeze">Freeze</Button>
                  <Button variant="destructive" size="sm" onClick={cancel} icon={XOctagon} data-testid="mbr-cancel">Cancel</Button>
                </div>
              </div>
            ) : <Empty text="No active plan." />}
          </section>
          <section>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-2">{active ? 'Top-up or change plan' : 'Assign / sell a plan'}</div>
            <div className="space-y-2">
              {plans.map((p) => (
                <div key={p.id} className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-3" data-testid={`mbr-plan-option-${p.id}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-1 h-7 rounded" style={{ background: p.colour }} />
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-white text-sm truncate">{p.name}</div>
                      <div className="text-xs text-[color:var(--theme-text-muted)]">£{(p.price_pence / 100).toFixed(2)} · {p.billing_cycle}</div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="primary" size="sm" onClick={() => recordPayment(p)} className="flex-1 uppercase tracking-wider" data-testid={`mbr-record-${p.id}`}>
                      Record payment
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => assign(p.id)} className="flex-1 uppercase tracking-wider" data-testid={`mbr-assign-${p.id}`}>
                      Comp / assign
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-2">Recent bookings</div>
            {(data.recent_bookings || []).length === 0 ? <Empty text="No bookings yet." /> : (
              <div className="space-y-1.5">
                {data.recent_bookings.map((b) => (
                  <div key={b.id} className="rounded-lg border border-[color:var(--theme-border)] bg-white/[0.03] p-2.5 text-xs flex items-center justify-between">
                    <div>
                      <div className="font-bold text-white">{b.occurrence?.name || '—'}</div>
                      <div className="text-[color:var(--theme-text-muted)]">{b.occurrence?.starts_at && new Date(b.occurrence.starts_at).toLocaleString()}</div>
                    </div>
                    <StatusPill status={b.status} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
      {recordingPlan && <RecordPaymentModal API={API} headers={headers} memberId={memberId} plan={recordingPlan}
        onClose={(refresh) => { setRecordingPlan(null); if (refresh) reload(); }} />}
    </div>
  );
}


/* ─────────────────── Record Payment modal ─────────────────── */

const PAY_METHODS = [
  { value: 'cash',          label: 'Cash' },
  { value: 'card_terminal', label: 'Card terminal' },
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'direct_debit',  label: 'Direct debit mandate' },
  { value: 'invoice',       label: 'Invoice / pay later' },
  { value: 'comp',          label: 'Complimentary / comp' },
];

function RecordPaymentModal({ API, headers, memberId, plan, onClose }) {
  const [method, setMethod] = useState('cash');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/members/${memberId}/record-payment`,
        { plan_id: plan.id, method, reference: reference || null, note: note || null }, { headers });
      notify.success(`Plan activated · £${(plan.price_pence / 100).toFixed(2)} recorded`);
      onClose(true);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <ModalShell title="Record payment" eyebrow={`£${(plan.price_pence / 100).toFixed(2)} · ${plan.name}`} testId="mbr-record-modal" onClose={() => onClose(false)} wide>
      <Select label="Payment method" value={method} onChange={setMethod} options={PAY_METHODS} testid="mbr-record-method" />
      <Input label="Reference (optional)" value={reference} onChange={setReference} testid="mbr-record-reference" />
      <Input label="Note (optional)" value={note} onChange={setNote} testid="mbr-record-note" />
      <p className="text-[10px] text-[color:var(--theme-text-muted)] leading-relaxed">The member's plan activates immediately. For class packs, credits are added on the spot.</p>
      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-record-save" />
    </ModalShell>
  );
}


/* ─────────── Merged Classes & Timetable hub (Iter 216ai · Sprint A #6) ─────────── */

/**
 * Single tab that unifies the three scheduling surfaces that used to be
 * separate tabs in the top bar. Three sub-pills:
 *
 *   • Timetable — materialised occurrences for the selected week.
 *   • Weekly builder — drag-drop template grid + identity + terms.
 *   • All classes — list of class templates with per-row edit/archive.
 *
 * `activeTabHint` lets deep links (Start checklist CTAs, old URLs, etc.)
 * still land on the sub-view they expected:
 *   'timetable'        → timetable sub-pill
 *   'studio-builder'   → builder sub-pill
 *   'classes'          → classes sub-pill
 *   'schedule' | other → timetable (default, most-useful surface)
 *
 * Having `onSetTab` as a prop is useful for cross-links — e.g. the
 * "Rebuild term" action in the builder can kick back to the timetable.
 */
function SchedulingHubTab({ API, headers, activeTabHint, _onSetTab }) {
  const initialView =
    activeTabHint === 'studio-builder' ? 'builder' :
    activeTabHint === 'classes' ? 'classes' :
    'timetable';
  const [view, setView] = useState(initialView);
  // Keep the sub-pill in sync when the parent routes a deep-link change
  // while the hub is already mounted (e.g. clicking "Studio Builder" CTA
  // from the onboarding checklist while the user is already on 'schedule').
  useEffect(() => { setView(initialView); }, [initialView]);

  const pills = [
    { id: 'timetable', label: 'Timetable',       icon: Calendar,    hint: 'This week' },
    { id: 'builder',   label: 'Weekly builder',  icon: Wand2,       hint: 'Drag classes onto the grid' },
    { id: 'classes',   label: 'All classes',     icon: Dumbbell,    hint: 'List + bulk edit' },
  ];

  return (
    <div data-testid="mbr-schedule-hub">
      <div className="flex items-center gap-2 flex-wrap mb-4" role="tablist" data-testid="mbr-schedule-subtabs">
        {pills.map((p) => {
          const Icon = p.icon;
          const isActive = view === p.id;
          return (
            <button key={p.id} type="button"
              onClick={() => setView(p.id)}
              role="tab" aria-selected={isActive}
              data-testid={`mbr-schedule-sub-${p.id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-extrabold border transition-colors"
              style={{
                background: isActive ? 'var(--color-brand-cyan)' : 'transparent',
                color: isActive ? 'var(--color-surface-darker)' : 'var(--theme-text)',
                borderColor: isActive ? 'transparent' : 'var(--theme-border)',
              }}>
              <Icon size={11} /> {p.label}
            </button>
          );
        })}
        <p className="text-[10px] uppercase tracking-wider text-[color:var(--theme-text-muted)] ml-2 hidden sm:block">
          {pills.find((p) => p.id === view)?.hint}
        </p>
      </div>
      {view === 'timetable' && <TimetableTab API={API} headers={headers} />}
      {view === 'builder'   && <StudioBuilderTab API={API} headers={headers} />}
      {view === 'classes'   && <ClassesTab API={API} headers={headers} />}
    </div>
  );
}


/* ─────────────────── Timetable ─────────────────── */

function TimetableTab({ API, headers }) {
  const [occs, setOccs] = useState([]);
  const [weekStart, setWeekStart] = useState(() => {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - d.getDay());  // start of week (Sunday)
    return d;
  });
  const [activeOcc, setActiveOcc] = useState(null);
  const reload = async () => {
    const from = weekStart.toISOString();
    const to = new Date(weekStart.getTime() + 7 * 86400000).toISOString();
    const res = await axios.get(`${API}/memberships/timetable`, { headers, params: { from, to } });
    setOccs(res.data.occurrences || []);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { reload();   }, [weekStart]);

  const days = [...Array(7)].map((_, i) => new Date(weekStart.getTime() + i * 86400000));
  const byDay = days.map((d) => occs.filter((o) => new Date(o.starts_at).toDateString() === d.toDateString()));

  return (
    <div data-testid="mbr-timetable">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <Header eyebrow="This week" title="Timetable" subtitle="Every class across the studio. Tap a class to announce or mark attendance." />
        <div className="flex gap-2 items-center">
          <Button variant="secondary" size="icon" onClick={() => setWeekStart(new Date(weekStart.getTime() - 7 * 86400000))} icon={ChevronLeft} title="Previous week" data-testid="mbr-week-prev" />
          <div className="text-sm font-bold px-3">{days[0].toLocaleDateString()} – {days[6].toLocaleDateString()}</div>
          <Button variant="secondary" size="icon" onClick={() => setWeekStart(new Date(weekStart.getTime() + 7 * 86400000))} icon={ChevronRight} title="Next week" data-testid="mbr-week-next" />
          <HelpHint guideId="mbr-first-class" testId="help-hint-timetable" />
        </div>
      </div>
      {/* Mobile: stacked day list. Desktop: 7-col grid. */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-7 gap-2">
        {days.map((d, i) => (
          <div key={i} className="bg-white/[0.02] rounded-xl border border-[color:var(--theme-border)] p-2 min-h-[120px] sm:min-h-[300px]" data-testid={`mbr-tt-day-${i}`}>
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-2">{d.toLocaleDateString([], { weekday: 'short', day: 'numeric' })}</div>
            <div className="space-y-1.5">
              {byDay[i].length === 0 && <div className="text-xs text-zinc-500/40 italic">—</div>}
              {byDay[i].map((o) => (
                <button key={o.id}
                  onClick={() => setActiveOcc(o)}
                  className="block w-full text-left rounded-lg p-2 text-xs cursor-pointer hover:scale-[1.01] active:scale-[0.99] transition"
                  style={{ background: (o.colour || 'var(--color-brand-cyan)') + '22', borderLeft: `3px solid ${o.colour || 'var(--color-brand-cyan)'}` }}
                  data-testid={`mbr-tt-occ-${o.id}`}
                  title={`${o.bookings_count || 0}/${o.capacity} booked · tap for actions`}>
                  <div className="font-extrabold truncate">{o.name}</div>
                  <div className="text-[color:var(--theme-text-muted)]">{new Date(o.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                  <div className="text-[10px] text-[color:var(--theme-text-muted)]">{o.bookings_count || 0}/{o.capacity}{(o.waitlist_count || 0) > 0 && ` · +${o.waitlist_count} wait`}</div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {/* Iter 216bd — friendly empty state when the whole week has zero classes. */}
      {occs.length === 0 && (
        <div className="mt-6">
          <EmptyState
            icon={Calendar}
            title="No classes scheduled this week"
            hint="Drag classes onto the weekly grid in Studio Builder, or use the Classes list to create your first class. Member bookings will surface here once your timetable is live."
            testId="mbr-timetable-empty"
          />
        </div>
      )}
      {activeOcc && (
        <ClassActionDrawer
          API={API} headers={headers}
          occurrence={activeOcc}
          onClose={() => setActiveOcc(null)}
          onChange={reload}
        />
      )}
    </div>
  );
}


/* ─────────────────── Plans ─────────────────── */

function PlansTab({ API, headers }) {
  // Iter 216h209 — Craig's feedback ("no credits package in memberships"):
  // class_pack plans were a hidden `kind` toggle inside "+ New plan".
  // Now they get a dedicated "Credit Packs" subtab — discoverable,
  // labelled, and pre-selects kind=class_pack on create.
  const [view, setView] = useState('plans');
  return (
    <div>
      <div className="flex items-end justify-end gap-4 mb-4 flex-wrap">
        <div className="subtab-bar" role="tablist">
          <button type="button" onClick={() => setView('plans')}
            className={`subtab-pill ${view === 'plans' ? 'is-active' : ''}`}
            data-testid="mbr-plans-tab-plans">
            <PackageOpen size={12} /> Plans
          </button>
          <button type="button" onClick={() => setView('credit_packs')}
            className={`subtab-pill ${view === 'credit_packs' ? 'is-active' : ''}`}
            data-testid="mbr-plans-tab-credit-packs">
            <Wallet size={12} /> Credit Packs
          </button>
          <button type="button" onClick={() => setView('courses')}
            className={`subtab-pill ${view === 'courses' ? 'is-active' : ''}`}
            data-testid="mbr-plans-tab-courses">
            <Calendar size={12} /> Courses
          </button>
        </div>
      </div>
      {view === 'plans'         && <PlansInnerView API={API} headers={headers} variant="subscription" />}
      {view === 'credit_packs'  && <PlansInnerView API={API} headers={headers} variant="credit_pack" />}
      {view === 'courses'       && <CoursesView    API={API} headers={headers} />}
    </div>
  );
}

function PlansInnerView({ API, headers, variant = 'subscription' }) {
  const confirm = useConfirm();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);  // null | 'new' | <plan object>

  // Iter 216h209 — Subscription view excludes class_pack (& vice-versa)
  // so each subtab tells a clean story instead of mixing concepts.
  const isCreditPack = variant === 'credit_pack';
  const visiblePlans = isCreditPack
    ? plans.filter((p) => (p.kind || '') === 'class_pack')
    : plans.filter((p) => (p.kind || '') !== 'class_pack');

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/memberships/plans`, { headers }); setPlans(data.plans || []); }
    catch { notify.error('Failed to load plans'); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);
  useEffect(() => { load(); }, [load]);

  const archive = async (p) => {
    if (!(await confirm({ title: `Archive "${p.name}"?`, detail: 'Existing members keep their plan — only new sign-ups are blocked.', tone: 'warning', confirmLabel: 'Archive' }))) return;
    try { await axios.delete(`${API}/memberships/plans/${p.id}`, { headers });
      notify.success('Plan archived'); load(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  const title = isCreditPack ? 'Credit Packs' : 'Membership plans';
  const subtitle = isCreditPack
    ? 'Sell a bundle of class credits up-front. Members redeem them per booking.'
    : 'The shelves you sell from.';
  const ctaLabel = isCreditPack ? 'New credit pack' : 'New plan';
  const ctaTestId = isCreditPack ? 'mbr-credit-pack-add' : 'mbr-plan-add';
  const emptyHint = isCreditPack
    ? 'No credit packs yet. Build a 5-class, 10-class or corporate pack — members can buy it from their portal or you can sell at the desk for cash.'
    : 'Create your first product — a monthly unlimited, a class pack, or a fixed-term course. Plans appear in member sign-up the moment you publish.';

  return (
    <div data-testid={isCreditPack ? 'mbr-credit-packs' : 'mbr-plans'}>
      <ListPanel
        data-testid={isCreditPack ? 'mbr-credit-packs-list' : 'mbr-plans-list'}
        title={title}
        subtitle={subtitle}
        count={{ value: visiblePlans.length, label: isCreditPack ? 'pack' : 'plan' }}
        secondaryActions={[
          <HelpHint key="help" guideId="mbr-first-plan" testId="help-hint-plans" />,
        ]}
        primaryAction={{ label: ctaLabel, icon: Plus, onClick: () => setEditing('new'), testId: ctaTestId }}
        loading={loading}
        empty={{
          when: visiblePlans.length === 0,
          icon: isCreditPack ? Wallet : PackageOpen,
          title: isCreditPack ? 'No credit packs yet' : 'No plans yet',
          hint: emptyHint,
          primaryAction: { label: isCreditPack ? 'Create your first credit pack' : 'Create your first plan', onClick: () => setEditing('new'), testId: isCreditPack ? 'mbr-credit-pack-empty-create' : 'mbr-plan-empty-create' },
          testId: isCreditPack ? 'mbr-credit-packs-empty' : 'mbr-plans-empty',
        }}
        bodyClassName="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        {visiblePlans.map((p) => (
          <div key={p.id} className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-4 group" data-testid={`mbr-plan-${p.id}`}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-1.5 h-8 rounded shrink-0" style={{ background: p.colour }} />
                <div className="min-w-0">
                  <div className="font-bold text-white text-sm truncate">{p.name}</div>
                  <div className="text-xs text-[color:var(--theme-text-muted)] capitalize">{(p.kind || '').replace('_', ' ')} · {p.billing_cycle}</div>
                </div>
              </div>
              <RowActions data-testid={`mbr-plan-actions-${p.id}`}>
                <Button variant="ghost" size="iconSm" onClick={() => setEditing(p)} icon={Edit3} title="Edit" data-testid={`mbr-plan-edit-${p.id}`} />
                <Button variant="ghostDestructive" size="iconSm" onClick={() => archive(p)} icon={Trash2} title="Archive" data-testid={`mbr-plan-archive-${p.id}`} />
              </RowActions>
            </div>
            <div className="text-2xl font-extrabold tracking-tight mt-2">£{(p.price_pence / 100).toFixed(2)}</div>
            <div className="text-xs text-[color:var(--theme-text-muted)] mt-1">
              {p.included_classes === 'unlimited' ? 'Unlimited classes' :
               p.credits_count ? `${p.credits_count} credits` : 'Credits only'}
            </div>
            <div className="flex gap-1.5 mt-3 flex-wrap">
              {p.freeze_allowed && <span className="text-[10px] font-bold text-[color:var(--theme-text-muted)] bg-white/5 rounded px-1.5 py-0.5">Freezable</span>}
              {p.cancel_notice_days > 0 && <span className="text-[10px] font-bold text-[color:var(--theme-text-muted)] bg-white/5 rounded px-1.5 py-0.5">{p.cancel_notice_days}d notice</span>}
              {p.upfront_fee_pence > 0 && <span className="text-[10px] font-bold text-amber-200 bg-amber-500/10 rounded px-1.5 py-0.5">£{(p.upfront_fee_pence/100).toFixed(0)} joining</span>}
            </div>
          </div>
        ))}
      </ListPanel>
      {editing && <PlanEditorModal API={API} headers={headers} plan={editing === 'new' ? null : editing}
        defaultKind={isCreditPack ? 'class_pack' : undefined}
        onClose={(refresh) => { setEditing(null); if (refresh) load(); }} />}
    </div>
  );
}


/* ─────────────────── Classes (templates) ─────────────────── */

const DAYS_OF_WEEK = [
  { value: 0, label: 'Mon' }, { value: 1, label: 'Tue' }, { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' }, { value: 4, label: 'Fri' }, { value: 5, label: 'Sat' }, { value: 6, label: 'Sun' },
];

function ClassesTab({ API, headers }) {
  const confirm = useConfirm();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);  // null | 'new' | <template>

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/memberships/classes/templates`, { headers });
      setTemplates(data.templates || []); }
    catch { notify.error('Failed to load classes'); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);
  useEffect(() => { load(); }, [load]);

  const archive = async (t) => {
    if (!(await confirm({ title: `Archive "${t.name}"?`, detail: 'All future occurrences will be cancelled. Existing bookings stay valid.', tone: 'warning', confirmLabel: 'Archive' }))) return;
    try { await axios.delete(`${API}/memberships/classes/templates/${t.id}`, { headers });
      notify.success('Class archived'); load(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  return (
    <div data-testid="mbr-classes">
      <ListPanel
        data-testid="mbr-classes-list"
        title="Classes"
        subtitle="Recurring class templates — changes generate new occurrences for the next 8 weeks."
        count={{ value: templates.length, label: 'class', plural: 'classes' }}
        primaryAction={{ label: 'New class', icon: Plus, onClick: () => setEditing('new'), testId: 'mbr-class-add' }}
        loading={loading}
        empty={{
          when: templates.length === 0,
          icon: Calendar,
          title: 'No classes yet',
          hint: 'Create your first recurring template — pick days, instructor, and capacity. We auto-generate occurrences 8 weeks out.',
          primaryAction: { label: 'Create your first class', onClick: () => setEditing('new'), testId: 'mbr-class-empty-create' },
          testId: 'mbr-classes-empty',
        }}
      >
        {templates.map((t) => (
          <div key={t.id} onClick={() => setEditing(t)} className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-3.5 flex items-center gap-3 cursor-pointer hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] transition group" data-testid={`mbr-class-${t.id}`}>
            <div className="w-1 h-12 rounded shrink-0" style={{ background: t.colour || 'var(--color-brand-cyan)' }} />
            <div className="flex-1 min-w-0">
              <div className="font-bold text-white text-sm truncate">{t.name} <span className="text-[10px] font-bold text-[color:var(--theme-text-muted)] uppercase ml-1">· {t.category}</span></div>
              <div className="text-xs text-[color:var(--theme-text-muted)] mt-0.5">
                {(t.recurs_days || []).map((d) => DAYS_OF_WEEK[d]?.label).join(', ') || 'No recurrence'} · {t.start_time} · {t.duration_min}min · cap {t.capacity}
              </div>
              <div className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
                {t.instructor_name || 'No instructor'} · {t.room_name || 'No room'} · {t.credits_to_book ?? 1} credit{t.credits_to_book === 1 ? '' : 's'}
              </div>
            </div>
            <RowActions data-testid={`mbr-class-actions-${t.id}`}>
              <Button variant="ghostDestructive" size="icon" onClick={(e) => { e.stopPropagation(); archive(t); }} icon={Trash2} title="Archive" data-testid={`mbr-class-archive-${t.id}`} />
            </RowActions>
          </div>
        ))}
      </ListPanel>
      {editing && <ClassEditorModal API={API} headers={headers} template={editing === 'new' ? null : editing}
        onClose={(refresh) => { setEditing(null); if (refresh) load(); }} />}
    </div>
  );
}



/* ─────────────────── Shared primitives ─────────────────── */

// The page-level Header (eyebrow / title / subtitle) used to render
// directly under the tab bar. It duplicated whatever tab pill was
// active, so we now render nothing — the active tab pill IS the page
// header. Call sites are kept intact for backwards-compat.
function SetupNudge() {
  return (
    <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-500/5 p-4 flex items-center justify-between gap-4" data-testid="mbr-setup-nudge">
      <div>
        <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-amber-200">Finish setup</div>
        <div className="text-sm font-bold text-white mt-0.5">Configure your studio basics, plans and app URL.</div>
      </div>
      {/* Iter 216h201 — Lee reported "Open Wizard" logged him out then
         back in. Root cause: a plain `<a href>` triggers a full page
         reload which the SPA auth bootstrap interprets as a fresh
         session. <Link> performs SPA navigation, preserving the
         in-memory auth state and dropping the user straight on the
         wizard. */}
      <Link to="/memberships/setup" className="rounded-lg px-3 py-2 text-xs font-extrabold uppercase tracking-wider bg-amber-400 text-black hover:brightness-110" data-testid="mbr-setup-nudge-cta">
        Open wizard
      </Link>
    </div>
  );
}

// Iter 215bi — duplicate of the live AppUrlCard in `AppUrlSection.js`.
// Kept for reference; safe to delete once the new section ships.
// eslint-disable-next-line unused-imports/no-unused-vars
function AppUrlCard({ org }) {
  const appUrl = `${window.location.origin}/m/${org.slug}`;
  const API = process.env.REACT_APP_BACKEND_URL;
  const posterUrl = `${API}/api/m/${org.slug}/poster.png`;
  const bragUrl = `${window.location.origin}/m/${org.slug}/brag`;
  const [sendingKit, setSendingKit] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(appUrl); notify.success('App URL copied'); }
    catch { window.prompt('Your app URL:', appUrl); }
  };
  const sendKit = async () => {
    if (sendingKit) return;
    setSendingKit(true);
    try {
      const res = await axios.post(`${API}/api/memberships/setup/resend-launch-kit`, {}, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      if (res.data.sent?.length) notify.success(`Launch kit emailed to ${res.data.sent.length} recipient${res.data.sent.length > 1 ? 's' : ''}`);
      else notify.info('Launch kit built · no operator recipients configured to receive yet.');
    } catch (e) { notifyApiError(notify, e, 'Launch kit send failed'); }
    finally { setSendingKit(false); }
  };
  return (
    <div className="mt-5 rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent overflow-hidden" data-testid="mbr-app-url-card">
      <div className="p-4 flex flex-wrap items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.2)] grid place-items-center shrink-0">
          <LinkIcon className="text-[var(--color-brand-cyan)]" size={18} />
        </div>
        <div className="flex-1 min-w-0 sm:min-w-[240px]">
          <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)]">Your member app</div>
          <div className="text-sm font-mono text-[color:var(--theme-text)] truncate mt-0.5" data-testid="mbr-app-url">{appUrl}</div>
        </div>
        <Button variant="primary" size="sm" onClick={sendKit} disabled={sendingKit} loading={sendingKit} icon={Sparkles} className="uppercase tracking-wider"
          data-testid="mbr-launch-kit-send" title="Email the launch kit (poster + socials + templates)">
          {sendingKit ? 'Sending' : 'Launch kit'}
        </Button>
        <a href={bragUrl} target="_blank" rel="noreferrer" className="text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:bg-black/[0.04] dark:hover:bg-white/5" data-testid="mbr-app-brag-open" title="Shareable live-stats card">Brag</a>
        <a href={posterUrl} target="_blank" rel="noreferrer" download={`${org.slug}-reception-poster.png`} className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border border-[rgb(var(--rgb-brand-cyan)/0.4)] text-[var(--color-brand-cyan)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.1)]" data-testid="mbr-app-poster-download" title="Download A4 reception poster">
          <Printer size={11} /> Poster
        </a>
        <a href={appUrl} target="_blank" rel="noreferrer" className="text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:bg-black/[0.04] dark:hover:bg-white/5" data-testid="mbr-app-url-open">Open</a>
        <Button variant="ghost" size="icon" onClick={copy} icon={Copy} title="Copy URL" data-testid="mbr-app-url-copy" />
      </div>
      <BrandPreview org={org} appUrl={appUrl} />
    </div>
  );
}

function BrandPreview({ org, appUrl }) {
  const accent = org.primary_brand_colour || 'var(--color-brand-cyan)';
  const [expanded, setExpanded] = useState(true);
  const [liveMode, setLiveMode] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);

  const shareText = `Our new member app is live! Book classes, show your check-in QR pass, manage your plan — all from your phone. Get started at ${appUrl}`;
  const smsUrl = `sms:?&body=${encodeURIComponent(shareText)}`;
  const emailUrl = `mailto:?subject=${encodeURIComponent(`Your new ${org.name} app`)}&body=${encodeURIComponent(shareText)}`;

  if (!expanded) {
    return (
      <div className="border-t border-[color:var(--theme-border)] px-4 py-2 flex items-center justify-between">
        <button onClick={() => setExpanded(true)} className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)] hover:underline" data-testid="mbr-brand-preview-show">
          Show brand preview →
        </button>
      </div>
    );
  }

  return (
    <div className="border-t border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)] p-5">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[color:var(--theme-text-muted)]">Brand preview</div>
          <div className="text-xs text-[color:var(--theme-text-muted)] mt-0.5">
            {liveMode ? 'Live preview — tap and navigate just like your members.' : 'Exactly what your members will see.'}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Static / Live toggle */}
          <div className="inline-flex p-0.5 rounded-md border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)]" data-testid="mbr-brand-preview-mode">
            <button
              onClick={() => setLiveMode(false)}
              className={`px-2.5 py-1 rounded text-[10px] font-extrabold uppercase tracking-wider transition ${!liveMode ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)]' : 'text-[color:var(--theme-text-muted)] hover:text-white'}`}
              data-testid="mbr-brand-preview-mode-static"
            >Static</button>
            <button
              onClick={() => setLiveMode(true)}
              className={`px-2.5 py-1 rounded text-[10px] font-extrabold uppercase tracking-wider transition ${liveMode ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)]' : 'text-[color:var(--theme-text-muted)] hover:text-white'}`}
              data-testid="mbr-brand-preview-mode-live"
            >Live</button>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setSendOpen(true)} className="uppercase tracking-wider" data-testid="mbr-brand-send-to-members">
            Send to members
          </Button>
          <Button variant="tertiary" size="sm" onClick={() => setExpanded(false)} data-testid="mbr-brand-preview-hide">Hide</Button>
        </div>
      </div>
      <div className="flex justify-center">
        {/* iPhone-style frame */}
        <div className="w-[280px] rounded-[32px] p-2 bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] shadow-[0_20px_60px_rgba(0,0,0,0.6)]" data-testid="mbr-brand-preview">
          <div className="relative rounded-[24px] overflow-hidden bg-[color:var(--theme-bg)]" style={{ aspectRatio: '9 / 16' }}>
            {/* Notch */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-16 h-4 bg-black rounded-b-xl z-10" />
            {liveMode ? (
              /* Live: real member app inside an iframe — fully interactive */
              <iframe
                key={appUrl}
                src={appUrl}
                title="Live member app preview"
                className="absolute inset-0 w-full h-full bg-white dark:bg-zinc-900"
                style={{ border: 0 }}
                sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
                data-testid="mbr-brand-preview-iframe"
              />
            ) : (
              <>
                {/* App chrome */}
                <div className="px-4 pt-6 pb-3 border-b border-[color:var(--theme-border)]">
                  <div className="flex items-center gap-2">
                    {org.logo_url && <img src={org.logo_url} alt="" className="h-6 w-6 rounded" />}
                    <div>
                      <div className="text-[8px] font-bold uppercase tracking-[0.25em] truncate" style={{ color: accent }}>{org.name || 'Your Studio'}</div>
                      <div className="text-[11px] font-extrabold text-white truncate">Hello, Jane</div>
                    </div>
                  </div>
                </div>
                {/* Body — faux timetable */}
                <div className="px-3 py-3 space-y-2">
                  {['HIIT Blast · 06:30', 'Rhythm Ride · 09:00', 'Strength · 18:00'].map((t, i) => (
                    <div key={i} className="rounded-lg border border-[color:var(--theme-border)] bg-white/[0.03] p-2 flex items-center justify-between" style={{ borderLeft: `3px solid ${accent}` }}>
                      <div>
                        <div className="text-[10px] font-bold text-white truncate">{t.split(' · ')[0]}</div>
                        <div className="text-[8px] text-[color:var(--theme-text-muted)]">{t.split(' · ')[1]}</div>
                      </div>
                      <span className="text-[8px] font-extrabold uppercase px-2 py-1 rounded" style={{ background: accent, color: 'var(--color-surface-darker)' }}>Book</span>
                    </div>
                  ))}
                </div>
                {/* Bottom nav */}
                <div className="absolute bottom-0 inset-x-0 grid grid-cols-5 border-t border-[color:var(--theme-border)] bg-[color:var(--theme-surface)]">
                  {['Book', 'Bookings', 'Plan', 'Pass', 'Profile'].map((l, i) => (
                    <div key={i} className={`py-2 text-center text-[7px] font-bold uppercase tracking-wider ${i === 0 ? '' : 'text-[color:var(--theme-text-muted)]'}`} style={i === 0 ? { color: accent } : {}}>
                      {l}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
      {liveMode && (
        <div className="mt-2 text-center text-[10px] text-[color:var(--theme-text-muted)]">
          Tap inside the phone — clicks, scrolling, and navigation all work.
          <a href={appUrl} target="_blank" rel="noreferrer" className="ml-1 underline hover:text-white">Open full screen ↗</a>
        </div>
      )}
      {sendOpen && (
        <div className="mt-4 rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)] p-4" data-testid="mbr-brand-send-panel">
          <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)] mb-2">Share your app</div>
          <div className="flex flex-wrap gap-2">
            <Button as="a" variant="secondary" size="sm" href={smsUrl} className="uppercase tracking-wider" data-testid="mbr-brand-send-sms">SMS template</Button>
            <Button as="a" variant="secondary" size="sm" href={emailUrl} className="uppercase tracking-wider" data-testid="mbr-brand-send-email">Email template</Button>
            <Button variant="secondary" size="sm" onClick={() => { navigator.clipboard.writeText(shareText); notify.success('Message copied'); }} className="uppercase tracking-wider" data-testid="mbr-brand-send-copy">Copy message</Button>
          </div>
          <div className="text-[10px] text-[color:var(--theme-text-muted)] mt-3 italic">"{shareText}"</div>
        </div>
      )}
    </div>
  );
}


/* ─────────────────── Ads tab ─────────────────── */

const PLACEMENTS = [
  { value: 'book_top',        label: 'Book tab — top' },
  { value: 'bookings_top',    label: 'Bookings tab — top' },
  { value: 'profile_bottom',  label: 'Profile — footer' },
];

function AdsTab({ API, headers }) {
  const confirm = useConfirm();
  const [ads, setAds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/memberships/ads`, { headers }); setAds(data.ads || []); }
    catch { notify.error('Failed to load ads'); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);
  useEffect(() => { load(); }, [load]);

  const del = async (ad) => {
    if (!(await confirm({ title: `Delete "${ad.headline}"?`, detail: 'The ad will be permanently removed.', tone: 'danger', confirmLabel: 'Delete' }))) return;
    try { await axios.delete(`${API}/memberships/ads/${ad.id}`, { headers });
      notify.success('Ad deleted'); load(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };
  const toggle = async (ad) => {
    try { await axios.patch(`${API}/memberships/ads/${ad.id}`, { active: !ad.active }, { headers });
      load(); }
    catch (e) { notifyApiError(notify, e, 'Failed'); }
  };

  return (
    <div data-testid="mbr-ads">
      <ListPanel
        data-testid="mbr-ads-list"
        title="Ads & announcements"
        subtitle="Surface banners in the member app — promos, events, challenges."
        count={{ value: ads.length, label: 'ad' }}
        primaryAction={{ label: 'New ad', icon: Plus, onClick: () => setEditing('new'), testId: 'mbr-ads-add' }}
        loading={loading}
        empty={{
          when: ads.length === 0,
          icon: Megaphone,
          title: 'No ads yet',
          hint: 'Create one to nudge members from the book tab — limited-time promo, upcoming event, or a new challenge.',
          primaryAction: { label: 'Create your first ad', onClick: () => setEditing('new'), testId: 'mbr-ads-empty-create' },
          testId: 'mbr-ads-empty',
        }}
      >
        {ads.map((a) => (
          <div key={a.id} className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-4 group" data-testid={`mbr-ad-${a.id}`}
               style={{ borderLeft: `3px solid ${a.background_colour || 'var(--color-brand-cyan)'}` }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm truncate">{a.headline}</span>
                  {!a.active && <span className="text-[9px] font-extrabold uppercase text-[color:var(--theme-text-muted)] bg-white/10 px-1.5 py-0.5 rounded">Paused</span>}
                </div>
                {a.body && <div className="text-xs text-[color:var(--theme-text-muted)] mt-0.5 truncate">{a.body}</div>}
                <div className="text-[10px] text-[color:var(--theme-text-muted)] mt-1 uppercase tracking-wider">
                  {PLACEMENTS.find((p) => p.value === a.placement)?.label || a.placement} · {a.impressions || 0} views · {a.clicks || 0} clicks
                </div>
              </div>
              <RowActions data-testid={`mbr-ad-actions-${a.id}`}>
                <Button variant="ghost" size="icon" onClick={() => toggle(a)} icon={a.active ? Pause : CheckCircle2} title={a.active ? 'Pause' : 'Resume'} data-testid={`mbr-ad-toggle-${a.id}`} />
                <Button variant="ghost" size="icon" onClick={() => setEditing(a)} icon={Edit3} title="Edit" data-testid={`mbr-ad-edit-${a.id}`} />
                <Button variant="ghostDestructive" size="icon" onClick={() => del(a)} icon={Trash2} title="Delete" data-testid={`mbr-ad-delete-${a.id}`} />
              </RowActions>
            </div>
          </div>
        ))}
      </ListPanel>
      {editing && <AdEditor API={API} headers={headers} ad={editing === 'new' ? null : editing} onClose={(reload) => { setEditing(null); if (reload) load(); }} />}
    </div>
  );
}

function AdEditor({ API, headers, ad, onClose }) {
  const isNew = !ad;
  const [f, setF] = useState(() => ({
    headline: ad?.headline || '',
    body: ad?.body || '',
    cta_label: ad?.cta_label || '',
    cta_url: ad?.cta_url || '',
    image_url: ad?.image_url || '',
    placement: ad?.placement || 'book_top',
    active: ad?.active ?? true,
    background_colour: ad?.background_colour || 'var(--color-brand-cyan)',
    starts_at: ad?.starts_at || '',
    ends_at: ad?.ends_at || '',
  }));
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!f.headline.trim()) { notify.error('Headline required'); return; }
    setSaving(true);
    try {
      const body = { ...f, starts_at: f.starts_at || null, ends_at: f.ends_at || null };
      if (isNew) await axios.post(`${API}/memberships/ads`, body, { headers });
      else await axios.patch(`${API}/memberships/ads/${ad.id}`, body, { headers });
      notify.success(isNew ? 'Ad created' : 'Ad updated');
      onClose(true);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <ModalShell title={isNew ? 'New ad' : 'Edit ad'} eyebrow="Promotion" testId="mbr-ad-editor" onClose={() => onClose(false)} wide>
      <Input label="Headline" value={f.headline} onChange={up('headline')} required testid="mbr-ad-headline" />
      <Input label="Body" value={f.body} onChange={up('body')} testid="mbr-ad-body" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="CTA label" value={f.cta_label} onChange={up('cta_label')} testid="mbr-ad-cta" />
        <Input label="CTA URL" value={f.cta_url} onChange={up('cta_url')} testid="mbr-ad-cta-url" />
      </div>
      <Input label="Image URL (optional)" value={f.image_url} onChange={up('image_url')} testid="mbr-ad-image" />
      <Select label="Placement" value={f.placement} onChange={up('placement')} options={PLACEMENTS} testid="mbr-ad-placement" />
      <div className="grid grid-cols-[1fr_auto] gap-3 items-end">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Starts at (ISO)" value={f.starts_at} onChange={up('starts_at')} testid="mbr-ad-starts" />
          <Input label="Ends at (ISO)"   value={f.ends_at}   onChange={up('ends_at')}   testid="mbr-ad-ends" />
        </div>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Colour</span>
          <input type="color" value={f.background_colour} onChange={(e) => up('background_colour')(e.target.value)} className="mt-1 h-10 w-16 rounded cursor-pointer bg-transparent" data-testid="mbr-ad-colour" />
        </label>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={f.active} onChange={(e) => up('active')(e.target.checked)} data-testid="mbr-ad-active" />
        <span className="text-[color:var(--theme-text-muted)]">Active</span>
      </label>
      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-ad-save" />
    </ModalShell>
  );
}


/**
 * Iter 215bp — canonical ModalShell (final).
 *
 * Pattern fixes both the original "internal slider" bug AND the
 * 215bo regression where tall modals got clipped at the top because
 * the inner card was `max-h-[90vh] overflow-hidden` while centered
 * with `flex items-center` + outer `overflow-y-auto`.
 *
 * Final layout:
 *   • Outer fixed cover with vertical scroll on the document itself.
 *   • Sub-wrapper `min-h-full flex items-center` so SHORT modals stay
 *     vertically centered, but LONG modals (taller than viewport) flow
 *     from the top and scroll naturally — no clipping.
 *   • Inner card has no max-height, no inner scroller. Page scroll only.
 *   • X close in top-right of the (non-sticky, but visible because the
 *     page scrolls from the top) header.
 *   • ESC + backdrop click both close.
 *   • ARIA roles in place.
 */
