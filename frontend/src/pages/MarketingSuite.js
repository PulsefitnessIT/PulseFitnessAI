/**
 * Pulse Fitness Marketing Suite — Phase 1 single-page app.
 *
 * Layout pattern is intentionally identical to LiteDashboardPage (Operations)
 * and MembershipsConsole (Memberships) so the user experiences a seamless
 * cross-module transition when toggling the ModuleSwitcher pill bar:
 *
 *   1. Top Navbar (logo + theme + lang + user menu)
 *   2. Unified header — "Pulse Fitness Pro · {company}", welcome line, ModuleSwitcher
 *   3. Horizontal pill tab bar (Insights · Audiences · Campaigns · Journeys · Creative · Social · Performance)
 *   4. Tab content
 *
 * Sub-tab components live in `pages/Marketing/` to keep this entry slim.
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Lightbulb, Users, UsersRound, Mail, Workflow, ImagePlus, Share2, BarChart3,
  ShieldCheck, Lock, Palette, Sparkles, FileText, ListChecks,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import ModulePageHeader from '@/components/shared/ModulePageHeader';
import PillTabBar from '@/components/shared/PillTabBar';

import StartTab from './Marketing/StartTab';
import CampaignWizard from './Marketing/CampaignWizard';
import UndoLaunchBanner from './Marketing/UndoLaunchBanner';
import { useUserPref } from '@/utils/userPrefs';
import AudiencesTab from './Marketing/AudiencesTab';
import CampaignsTab from './Marketing/CampaignsTab';
import CreativeStudioTab from './Marketing/CreativeStudioRoot';
import JourneysTab from './Marketing/JourneysTab';
import InsightsTab from './Marketing/InsightsTab';
import PerformanceTab from './Marketing/PerformanceTab';
import SocialTab from './Marketing/SocialTab';
import BrandKitTab from './Marketing/BrandKitTab';
import FormsAndPagesTab from './Marketing/FormsAndPagesTab';
import DynamicListsTab from './Marketing/DynamicListsTab';
import ContactsTab from './Marketing/ContactsTab';
import MarketingTour from './Marketing/MarketingTour';
import CrossModuleTipsBanner from '@/components/shared/CrossModuleTipsBanner';
import ModuleAccessGate from '@/components/shared/ModuleAccessGate';
import EmailVolumePanel from './Marketing/EmailVolumePanel';
import LocaleLanguageNudge from '@/components/shared/LocaleLanguageNudge';

// Guided "Start" tab sits first — it's the entry point for non-technical
// users. Power users can ignore it and jump straight to any downstream tab.
// Iter 216h70 — Lee's Feb 2026 ask: "Move Start to the first option —
// Start should be the same as the other modules, a check sheet of
// tasks that auto-removes once complete. Next option should be
// Dashboard (which takes over from Performance)."
//   1. Start    — guided onboarding checklist (auto-hides via
//                 ActivationMilestonesCard when all milestones land)
//   2. Dashboard — live KPI dashboard (the old Performance tab, renamed)
//   3. Insights, Campaigns, Journeys, … (unchanged order below)
const TABS = [
  { id: 'start',         label: 'Start',           icon: Sparkles,   feature: null },
  { id: 'performance',   label: 'Dashboard',       icon: BarChart3,  feature: null },
  { id: 'insights',      label: 'Insights',        icon: Lightbulb,  feature: null },
  { id: 'campaigns',     label: 'Campaigns',       icon: Mail,       feature: 'campaigns' },
  { id: 'journeys',      label: 'Journeys',        icon: Workflow,   feature: 'journeys' },
  { id: 'contacts',      label: 'Contacts',        icon: UsersRound, feature: null },
  { id: 'audiences',     label: 'Audiences',       icon: Users,      feature: 'audiences' },
  { id: 'dynamic-lists', label: 'Dynamic Lists',   icon: ListChecks, feature: 'audiences' },
  { id: 'forms-pages',   label: 'Forms & Pages',   icon: FileText,   feature: null },
  { id: 'creative',      label: 'Creative Studio', icon: ImagePlus,  feature: 'ai_creative_studio' },
  { id: 'brand-kit',     label: 'Brand Kit',       icon: Palette,    feature: null },
  { id: 'social',        label: 'Social',          icon: Share2,     feature: 'social_scheduling' },
];

const MarketingSuite = ({ embedded = false } = {}) => {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  // Tabs and the entitlement call here all build their own `${API}/api/...`
  // URLs, so we pass the bare backend URL (no /api suffix).
  const API = process.env.REACT_APP_BACKEND_URL;
  // Iter 216h70 — first visit lands on Start (the new first tab); once
  // ActivationMilestonesCard flips `hideStartTabs=true`, the next
  // visit defaults to Dashboard (the renamed Performance) because
  // Start is the first visible tab when present, otherwise Dashboard.
  const initialTabFromQuery = (() => {
    if (typeof window === 'undefined') return 'start';
    const sp = new URLSearchParams(window.location.search);
    const want = sp.get('tab');
    if (want && TABS.some((t) => t.id === want)) return want;
    try {
      const hidden = localStorage.getItem('userPref:hideStartTabs') === 'true';
      return hidden ? 'performance' : 'start';
    } catch {
      return 'start';
    }
  })();
  const [tab, setTab] = useState(initialTabFromQuery);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get('from') === 'crm') {
      // Dynamic import keeps the marketing bundle lean and avoids the
      // eslint `no-undef` for require() in ESM-mode lint.
      import('@/components/notifications').then(({ notify }) => {
        notify.info('CRM Lite', 'Manage your contacts and segments here. Upgrade to CRM Pro for pipeline & forecasting.');
      }).catch(() => { /* notification system unavailable — silent */ });
    }
  }, []);
  const [hideStart] = useUserPref('hideStartTabs', false);
  const visibleTabs = useMemo(() => hideStart ? TABS.filter((t) => t.id !== 'start') : TABS, [hideStart]);
  useEffect(() => {
    // If the user toggled hide while sitting on the Start tab, pivot to
    // Dashboard (the new label for performance).
    if (hideStart && tab === 'start') setTab('performance');
  }, [hideStart, tab]);
  const [wizardState, setWizardState] = useState({ open: false, preset: null, templateId: null });
  const [undoCampaignId, setUndoCampaignId] = useState(null);
  const [emailPanelOpen, setEmailPanelOpen] = useState(false);
  const openWizard = (opts = {}) => setWizardState({ open: true, preset: opts.preset || 'wizard', templateId: opts.templateId || null });
  const closeWizard = (result) => {
    setWizardState({ open: false, preset: null, templateId: null });
    if (result?.launched) {
      if (result.campaignId) setUndoCampaignId(result.campaignId);
      setTab('performance');
    } else if (result?.draft) {
      setTab('campaigns');
    }
  };
  const [entitlement, setEntitlement] = useState(null);
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const pillBarRef = React.useRef(null);

  useEffect(() => {
    if (!token) return;
    axios.get(`${API}/api/marketing/me/entitlement`, { headers })
      .then((r) => setEntitlement(r.data))
      .catch(() => {});
    // eslint-disable-next-line
  }, []);

  // Keep the active pill scrolled into view on mobile when the tab changes —
  // mirrors MembershipsConsole behaviour for layout parity.
  React.useEffect(() => {
    if (!pillBarRef.current) return;
    const active = pillBarRef.current.querySelector(`[data-testid="mkt-pill-${tab}"]`);
    active?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [tab]);

  // Listen for both the legacy `mkt-jump-tab` event AND the new
  // `gymaxis-jump` event from UnifiedAssistant so we keep working
  // regardless of which assistant fires the action.
  React.useEffect(() => {
    const legacy = (e) => {
      const target = e.detail;
      if (typeof target === 'string' && target) setTab(target);
    };
    const unified = (e) => {
      const { mode, target } = e.detail || {};
      if (mode === 'marketing' && typeof target === 'string') setTab(target);
    };
    window.addEventListener('mkt-jump-tab', legacy);
    window.addEventListener('gymaxis-jump', unified);
    return () => {
      window.removeEventListener('mkt-jump-tab', legacy);
      window.removeEventListener('gymaxis-jump', unified);
    };
  }, []);

  if (!user) { navigate('/'); return null; }

  const isLocked = (feature) => feature && entitlement && !entitlement.features?.[feature];
  const planName = entitlement?.plan?.name || 'Loading…';
  // Iter 216h192 — Lee's Feb 2026 fix: a paid platform plan (Pulse Pro,
  // Pulse Fitness Full, Lite) bundles Marketing. Don't tease "Free trial" at
  // those users — it implies billing will start, which is misleading.
  // We still honour the actual marketing-subscription status so true
  // self-service trials keep showing the pill.
  const isOnPaidPlatformPlan = (
    user?.account_type === 'pulse_pro' ||
    user?.account_type === 'full' ||
    user?.account_type === 'lite' ||
    !!user?.is_master_admin
  );
  const isTrial = entitlement?.subscription?.status === 'trial' && !isOnPaidPlatformPlan;

  const ActiveTab = () => {
    switch (tab) {
      case 'start':       return <StartTab openWizard={openWizard} setTab={setTab} />;
      case 'insights':    return <InsightsTab API={API} headers={headers} setTab={setTab} />;
      case 'audiences':   return <AudiencesTab API={API} headers={headers} />;
      case 'dynamic-lists': return <DynamicListsTab API={API} headers={headers} />;
      case 'contacts':    return <ContactsTab />;
      case 'campaigns':   return <CampaignsTab API={API} headers={headers} />;
      case 'journeys':    return <JourneysTab API={API} headers={headers} entitlement={entitlement} />;
      case 'creative':    return <CreativeStudioTab API={API} headers={headers} entitlement={entitlement} />;
      case 'forms-pages': return <FormsAndPagesTab API={API} headers={headers} />;
      case 'brand-kit':   return <BrandKitTab API={API} headers={headers} />;
      case 'social':      return <SocialTab API={API} headers={headers} />;
      case 'performance': return <PerformanceTab API={API} headers={headers} />;
      default: return null;
    }
  };

  // Iter 215bc — Phase 5 brand-aware Marketing Suite. Pulse-account
  // customers (account_type pulse_pro / lite) keep the legacy
  // "Pulse Fitness" heading + solid cyan active tabs. Pulse Fitness customers
  // see the new Pulse Fitness brand: gradient wordmark + brand-gradient
  // active tab pills + theme-gymaxis class in light mode.
  const isPulseBrandedMkt = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const brandLabel = isPulseBrandedMkt ? 'Pulse Fitness' : 'Pulse Fitness';

  return (
    <div
      className={`${embedded ? '' : 'min-h-screen'} ${!isPulseBrandedMkt && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={embedded
        ? { color: 'var(--theme-text)' }
        : { background: 'var(--theme-bg)', color: 'var(--theme-text)' }}
      data-testid="marketing-suite"
    >
      {!embedded && <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />}

      <main className={embedded
        ? 'module-fade-in'
        : 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in'}>
        <LocaleLanguageNudge />
        {/* Unified app header — byte-for-byte parity with Operations / Memberships
            so the ModuleSwitcher pill bar sits in the same screen position when
            users toggle modules. Suppressed in embedded mode (Master Admin →
            Growth → Marketing Studio supplies its own chrome). */}
        {!embedded && (
          <div className="mb-6" data-testid="marketing-app-header">
            <ModulePageHeader
              moduleName="Marketing"
              tenantName={user?.company_name}
              subtitle="Campaigns, journeys, creative & growth insights."
              isPulseBranded={isPulseBrandedMkt}
            />
            <ModuleSwitcher user={user} current="marketing" />
          </div>
        )}

        {!embedded && <CrossModuleTipsBanner mode="marketing" />}

        {/* Desktop pill tab bar — canonical PillTabBar so overflow
            auto-scrolls the active tab into view and fades edges. */}
        <PillTabBar
          className="hidden md:block mb-6"
          activeId={tab}
          testId="mkt-tabs-desktop"
          ariaLabel="Marketing sections"
        >
          {visibleTabs.map(({ id, label, icon: Icon, feature }) => {
            const locked = isLocked(feature);
            const isActive = tab === id;
            const activeStyle = isPulseBrandedMkt
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', boxShadow: '0 6px 16px -6px rgba(25, 205, 255, 0.35)' };
            return (
              <button
                key={id}
                data-pill-id={id}
                onClick={() => !locked && setTab(id)}
                disabled={locked}
                className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap disabled:cursor-not-allowed"
                style={isActive
                  ? activeStyle
                  : { color: locked ? 'var(--theme-text-muted)' : 'var(--theme-text-muted)', background: 'transparent', opacity: locked ? 0.5 : 1 }}
                data-testid={`marketing-tab-${id}`}
              >
                <Icon size={14} /> {label}
                {locked && <Lock size={11} />}
              </button>
            );
          })}
        </PillTabBar>

        {/* Mobile scrollable pill tabs */}
        <div ref={pillBarRef} className="md:hidden mb-5 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
          {visibleTabs.map(({ id, label, feature }) => {
            const locked = isLocked(feature);
            const isActive = tab === id;
            const activeStyleMobile = isPulseBrandedMkt
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' };
            return (
              <button
                key={id}
                onClick={() => !locked && setTab(id)}
                disabled={locked}
                className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed"
                style={isActive
                  ? activeStyleMobile
                  : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', opacity: locked ? 0.5 : 1 }}
                data-testid={`mkt-pill-${id}`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Plan badge strip — sits beneath the tab bar so the unified header
            stays clean. */}
        {entitlement && (
          <div className="flex items-center gap-2 mb-5" data-testid="marketing-plan-badge">
            <span className="px-3 py-1.5 rounded-full bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-deep)] text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_4px_12px_-4px_rgba(25, 205, 255,0.35)]">
              <ShieldCheck size={13} /> {planName}
            </span>
            {isTrial && (
              <span className="px-3 py-1.5 rounded-full bg-amber-100 text-amber-800 text-xs font-semibold">
                Free trial
              </span>
            )}
            <button
              type="button"
              onClick={() => setEmailPanelOpen(true)}
              className="ml-auto text-[11px] hover:underline cursor-pointer transition-colors"
              style={{ color: 'var(--theme-text-muted)' }}
              data-testid="marketing-email-volume-trigger"
              title="View email volume cap and bolt-on packs"
            >
              {entitlement.subscription.usage_this_period.emails_sent ?? 0} / {entitlement.limits.monthly_emails.toLocaleString()} emails ·{' '}
              {entitlement.subscription.usage_this_period.ai_generations ?? 0} / {entitlement.limits.ai_generations.toLocaleString()} AI gens
              <span className="ml-1.5 underline-offset-2 underline">manage packs</span>
            </button>
          </div>
        )}

        <ActiveTab />
      </main>

      <CampaignWizard
        open={wizardState.open}
        preset={wizardState.preset}
        templateId={wizardState.templateId}
        API={API}
        headers={headers}
        toast={({ title, intent }) => intent === 'warn' ? toast.warning(title) : toast.success(title)}
        onClose={closeWizard}
      />

      {undoCampaignId && (
        <UndoLaunchBanner
          campaignId={undoCampaignId}
          API={API}
          headers={headers}
          onUndone={() => { setUndoCampaignId(null); toast.success('Campaign cancelled.'); }}
          onExpire={() => setUndoCampaignId(null)}
        />
      )}

      <MarketingTour
        API={API}
        headers={headers}
        onJumpToTab={setTab}
        onComplete={() => { /* tour state already persisted server-side */ }}
      />

      {emailPanelOpen && (
        <EmailVolumePanel
          API={API}
          headers={headers}
          onClose={() => setEmailPanelOpen(false)}
        />
      )}
    </div>
  );
};

export default function MarketingSuiteGated({ embedded = false } = {}) {
  const { user } = useAuth();
  // Iter 220ac — master admin gets the suite ungated so the Growth →
  // Marketing Studio surface inside Master Admin can promote Pulse Fitness
  // itself without buying a marketing seat.
  if (user?.is_master_admin || embedded) {
    return <MarketingSuite embedded={embedded} />;
  }
  return (
    <ModuleAccessGate module="marketing">
      <MarketingSuite />
    </ModuleAccessGate>
  );
}
