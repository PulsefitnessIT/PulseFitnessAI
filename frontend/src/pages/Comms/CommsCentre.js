/**
 * Pulse Fitness AI — Comms Centre.
 *
 * The central, merged campaign + intelligence module. Layout mirrors the
 * other modules (unified header + ModuleSwitcher + canonical PillTabBar).
 * Main tabs: Campaigns / Flows / Segments / Analytics / Inactive.
 * Analytics groups Engagement / Best Send Time / Benchmarks behind a
 * sub-tab row; Deliverability / Import / API & Webhooks live behind a
 * Settings menu. A module-scope control (All / Marketing / Members / CRM)
 * filters the shared records — no duplication.
 */
import React, { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Megaphone, TrendingUp, Clock, Award, ShieldCheck, Users, Filter, Workflow, Upload, Webhook, Settings, ChevronDown, Check } from 'lucide-react';

import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import ModulePageHeader from '@/components/shared/ModulePageHeader';
import PillTabBar from '@/components/shared/PillTabBar';
import CrossModuleTipsBanner from '@/components/shared/CrossModuleTipsBanner';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu';
import CampaignsPanel from './CampaignsPanel';
import { EngagementView, InactiveView, BestTimeView, BenchmarksView, DeliverabilityView } from './Intelligence';
import { SegmentsView } from './Segments';
import { FlowsView } from './Flows';
import { MigrateView } from './Migrate';
import { DeveloperView } from './Developer';

const SECTIONS = [
  { id: 'campaigns', label: 'Campaigns', icon: Megaphone },
  { id: 'flows', label: 'Flows', icon: Workflow },
  { id: 'segments', label: 'Segments', icon: Filter },
  { id: 'analytics', label: 'Analytics', icon: TrendingUp },
  { id: 'inactive', label: 'Inactive', icon: Users },
];

const ANALYTICS_TABS = [
  { id: 'engagement', label: 'Engagement', icon: TrendingUp },
  { id: 'best-time', label: 'Best Send Time', icon: Clock },
  { id: 'benchmarks', label: 'Benchmarks', icon: Award },
];

const SETTINGS_ITEMS = [
  { id: 'deliverability', label: 'Deliverability', icon: ShieldCheck },
  { id: 'migrate', label: 'Import', icon: Upload },
  { id: 'developer', label: 'API & Webhooks', icon: Webhook },
];

const ANALYTICS_IDS = ANALYTICS_TABS.map((t) => t.id);
const SETTINGS_IDS = SETTINGS_ITEMS.map((s) => s.id);
const LEAF_VIEWS = [
  ...SECTIONS.map((s) => s.id).filter((id) => id !== 'analytics'),
  ...ANALYTICS_IDS,
  ...SETTINGS_IDS,
];

const SCOPES = [
  { id: 'all', label: 'All' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'memberships', label: 'Members' },
  { id: 'crm', label: 'CRM & B2B' },
];

export default function CommsCentre() {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const API = process.env.REACT_APP_BACKEND_URL;
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const sp = new URLSearchParams(location.search);
  const requested = sp.get('view');
  const initialView = requested === 'analytics'
    ? 'engagement'
    : (LEAF_VIEWS.includes(requested) ? requested : 'campaigns');

  const [view, setView] = useState(initialView);
  const [scope, setScope] = useState('all');

  const isPulseBranded = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';

  if (!user) { navigate('/'); return null; }

  const analyticsActive = ANALYTICS_IDS.includes(view);
  const settingsActive = SETTINGS_IDS.includes(view);

  const go = (id) => { setView(id); navigate(`/comms?view=${id}`, { replace: true }); };

  const activeStyle = isPulseBranded
    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
    : { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', boxShadow: '0 6px 16px -6px rgba(25, 205, 255, 0.35)' };

  const renderSection = () => {
    switch (view) {
      case 'flows': return <FlowsView API={API} headers={headers} />;
      case 'migrate': return <MigrateView API={API} headers={headers} />;
      case 'developer': return <DeveloperView API={API} headers={headers} />;
      case 'segments': return <SegmentsView API={API} headers={headers} />;
      case 'engagement': return <EngagementView API={API} headers={headers} module={scope} />;
      case 'inactive': return <InactiveView API={API} headers={headers} module={scope} />;
      case 'best-time': return <BestTimeView API={API} headers={headers} module={scope} />;
      case 'benchmarks': return <BenchmarksView API={API} headers={headers} module={scope} />;
      case 'deliverability': return <DeliverabilityView API={API} headers={headers} />;
      default: return <CampaignsPanel key={scope} API={API} headers={headers} module={scope} testIdPrefix="comms" />;
    }
  };

  const SettingsMenu = ({ testId }) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          data-testid={testId}
          className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
          style={settingsActive ? activeStyle : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
        >
          <Settings size={14} /> Settings <ChevronDown size={14} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52" data-testid="comms-settings-menu">
        {SETTINGS_ITEMS.map(({ id, label, icon: Icon }) => (
          <DropdownMenuItem key={id} onClick={() => go(id)} data-testid={`comms-settings-${id}`} className="gap-2 cursor-pointer">
            <Icon size={15} className="text-slate-500" />
            <span className="flex-1">{label}</span>
            {view === id && <Check size={14} className="text-[#0891b2]" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );

  const mainTab = ({ id, label, icon: Icon }, isMobile) => {
    const isActive = id === 'analytics' ? analyticsActive : view === id;
    const onClick = () => go(id === 'analytics' ? 'engagement' : id);
    if (isMobile) {
      return (
        <button key={id} onClick={onClick}
          className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap"
          style={isActive ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
          data-testid={`comms-section-pill-${id}`}>{label}</button>
      );
    }
    return (
      <button
        key={id}
        data-pill-id={id}
        onClick={onClick}
        className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
        style={isActive ? activeStyle : { color: 'var(--theme-text-muted)', background: 'transparent' }}
        data-testid={`comms-section-${id}`}
      >
        <Icon size={14} /> {label}
      </button>
    );
  };

  return (
    <div
      className={`min-h-screen ${!isPulseBranded && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}
      data-testid="comms-centre"
    >
      <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in">
        <div className="mb-6" data-testid="comms-app-header">
          <ModulePageHeader
            moduleName="Comms Centre"
            tenantName={user?.company_name}
            subtitle="One connected campaign & intelligence system across Marketing, Memberships and CRM."
            isPulseBranded={isPulseBranded}
          />
          <ModuleSwitcher user={user} current="comms" />
        </div>

        <CrossModuleTipsBanner mode="marketing" />

        {/* Section tabs (desktop) — main tabs + Settings menu */}
        <div className="hidden md:flex items-center gap-2 mb-4">
          <PillTabBar className="flex-1 min-w-0" activeId={analyticsActive ? 'analytics' : view} testId="comms-sections-desktop" ariaLabel="Comms sections">
            {SECTIONS.map((s) => mainTab(s, false))}
          </PillTabBar>
          <SettingsMenu testId="comms-settings-btn" />
        </div>

        {/* Mobile section pills */}
        <div className="md:hidden mb-4 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
          {SECTIONS.map((s) => mainTab(s, true))}
          <SettingsMenu testId="comms-settings-btn-mobile" />
        </div>

        {/* Analytics sub-tabs */}
        {analyticsActive && (
          <div className="mb-4 inline-flex items-center gap-1 p-1 rounded-full flex-wrap" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }} data-testid="comms-analytics-tabs">
            {ANALYTICS_TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => go(id)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold transition-all"
                style={view === id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)' }}
                data-testid={`comms-analytics-${id}`}><Icon size={13} />{label}</button>
            ))}
          </div>
        )}

        {/* Module scope (hidden for org-wide / source views) */}
        {!['deliverability', 'segments', 'flows', 'migrate', 'developer'].includes(view) && (
          <div className="mb-5 inline-flex items-center gap-1 p-1 rounded-full" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }} data-testid="comms-scope">
            {SCOPES.map((s) => (
              <button key={s.id} onClick={() => setScope(s.id)}
                className="px-3.5 py-1.5 rounded-full text-xs font-bold transition-all"
                style={scope === s.id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)' }}
                data-testid={`comms-scope-${s.id}`}>{s.label}</button>
            ))}
          </div>
        )}

        {renderSection()}
      </main>
    </div>
  );
}
