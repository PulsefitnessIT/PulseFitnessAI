/**
 * GymAxis Marketing Suite — Phase 1 single-page app.
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
import PillTabBar from '@/components/shared/PillTabBar';
import ProductTour from '@/components/shared/ProductTour';

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

// Guided "Start" tab sits first — it's the entry point for non-technical
// users. Power users can ignore it and jump straight to any downstream tab.
// Iter 238h — Performance is now the marketing dashboard, so it sits
// first. The rest is grouped into a logical workflow:
//   Discover → Performance, Insights
//   Reach    → Campaigns, Journeys
//   Segment  → Audiences, Dynamic Lists
//   Capture  → Forms & Pages
//   Create   → Creative Studio, Brand Kit, Social
const TABS = [
  { id: 'performance',   label: 'Performance',     icon: BarChart3,  feature: null },
  { id: 'start',         label: 'Start',           icon: Sparkles,   feature: null },
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

const MarketingSuite = () => {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  // Tabs and the entitlement call here all build their own `${API}/api/...`
  // URLs, so we pass the bare backend URL (no /api suffix).
  const API = process.env.REACT_APP_BACKEND_URL;
  // Iter 238h — default to Performance (the new marketing dashboard)
  // so operators see live KPIs immediately on entering the suite.
  // Iter 215dl — accept ?tab=contacts (or any valid tab id) so the
  // /crm → /marketing fallback for non-CRM-Pro tenants lands on the
  // right place. ?from=crm shows a small "you're on CRM Lite" toast.
  const initialTabFromQuery = (() => {
    if (typeof window === 'undefined') return 'performance';
    const sp = new URLSearchParams(window.location.search);
    const want = sp.get('tab');
    return want && TABS.some((t) => t.id === want) ? want : 'performance';
  })();
  const [tab, setTab] = useState(initialTabFromQuery);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get('from') === 'crm') {
      // Lazy-import-friendly: notify is already imported elsewhere; use a
      // light DOM-friendly toast via the global notify if available.
      try {
        // eslint-disable-next-line global-require
        const { notify } = require('@/components/notifications');
        notify.info('CRM Lite', 'Manage your contacts and segments here. Upgrade to CRM Pro for pipeline & forecasting.');
      } catch (_) { /* notification system unavailable — silent */ }
    }
  }, []);
  const [hideStart] = useUserPref('hideStartTabs', false);
  const visibleTabs = useMemo(() => hideStart ? TABS.filter((t) => t.id !== 'start') : TABS, [hideStart]);
  useEffect(() => {
    // If the user toggled hide while sitting on the Start tab, pivot to Insights.
    if (hideStart && tab === 'start') setTab('insights');
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
  const isTrial = entitlement?.subscription?.status === 'trial';

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
  // "Pulse Fitness" heading + solid cyan active tabs. GymAxis customers
  // see the new GymAxis brand: gradient wordmark + brand-gradient
  // active tab pills + theme-gymaxis class in light mode.
  const isPulseBrandedMkt = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const brandLabel = isPulseBrandedMkt ? 'Pulse Fitness' : 'GymAxis';

  return (
    <div
      className={`min-h-screen ${!isPulseBrandedMkt && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}
      data-testid="marketing-suite"
    >
      <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in">
        {/* Unified app header — byte-for-byte parity with Operations / Memberships
            so the ModuleSwitcher pill bar sits in the same screen position when
            users toggle modules. */}
        <div className="mb-6" data-testid="marketing-app-header">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>
                {isPulseBrandedMkt
                  ? brandLabel
                  : <span className="gx-grad-text">{brandLabel}</span>
                }{' '}
                {(user?.account_type === 'pulse_pro' || user?.account_type === 'full' || user?.is_master_admin) && (
                  <span style={{ color: isPulseBrandedMkt ? 'var(--color-brand-cyan-hover)' : 'var(--gx-brand-to)' }}>Pro</span>
                )}
                {user?.company_name && (
                  <span className="text-base sm:text-lg font-normal ml-2 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
                    · {user.company_name}
                  </span>
                )}
              </h1>
              <p className="pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>Welcome back, {user?.full_name}</p>
            </div>
            <div className="text-sm pulse-font-body shrink-0 mt-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
              {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </div>
          </div>
          <ModuleSwitcher user={user} current="marketing" />
        </div>

        <CrossModuleTipsBanner mode="marketing" />

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
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF', boxShadow: '0 6px 16px -6px rgba(37,99,235,0.35)' };
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
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF' };
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
            <span className="px-3 py-1.5 rounded-full bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-deep)] text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_4px_12px_-4px_rgba(37,99,235,0.35)]">
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

export default function MarketingSuiteGated() {
  return (
    <ModuleAccessGate module="marketing">
      <MarketingSuite />
    </ModuleAccessGate>
  );
}
