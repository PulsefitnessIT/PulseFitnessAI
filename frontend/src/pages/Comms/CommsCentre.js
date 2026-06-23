/**
 * Pulse Fitness AI — Comms Centre.
 *
 * The central, merged campaign + intelligence module. Layout mirrors the
 * other modules (unified header + ModuleSwitcher + canonical PillTabBar).
 * Section tabs: Campaigns / Engagement / Inactive / Best Send Time /
 * Benchmarks / Deliverability. A module-scope control (All / Marketing /
 * Members / CRM) filters the shared records — no duplication.
 */
import React, { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Megaphone, TrendingUp, Clock, Award, ShieldCheck, Users } from 'lucide-react';

import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import PillTabBar from '@/components/shared/PillTabBar';
import CrossModuleTipsBanner from '@/components/shared/CrossModuleTipsBanner';
import CampaignsPanel from './CampaignsPanel';
import { EngagementView, InactiveView, BestTimeView, BenchmarksView, DeliverabilityView } from './Intelligence';

const SECTIONS = [
  { id: 'campaigns', label: 'Campaigns', icon: Megaphone },
  { id: 'engagement', label: 'Engagement', icon: TrendingUp },
  { id: 'inactive', label: 'Inactive', icon: Users },
  { id: 'best-time', label: 'Best Send Time', icon: Clock },
  { id: 'benchmarks', label: 'Benchmarks', icon: Award },
  { id: 'deliverability', label: 'Deliverability', icon: ShieldCheck },
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
  const [section, setSection] = useState(SECTIONS.some((s) => s.id === sp.get('view')) ? sp.get('view') : 'campaigns');
  const [scope, setScope] = useState('all');

  const isPulseBranded = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';

  if (!user) { navigate('/'); return null; }

  const renderSection = () => {
    switch (section) {
      case 'engagement': return <EngagementView API={API} headers={headers} module={scope} />;
      case 'inactive': return <InactiveView API={API} headers={headers} module={scope} />;
      case 'best-time': return <BestTimeView API={API} headers={headers} module={scope} />;
      case 'benchmarks': return <BenchmarksView API={API} headers={headers} module={scope} />;
      case 'deliverability': return <DeliverabilityView API={API} headers={headers} />;
      default: return <CampaignsPanel key={scope} API={API} headers={headers} module={scope} testIdPrefix="comms" />;
    }
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
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>
                {isPulseBranded ? 'Comms Centre' : <span className="gx-grad-text">Comms Centre</span>}
                {user?.company_name && (
                  <span className="text-base sm:text-lg font-normal ml-2 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>· {user.company_name}</span>
                )}
              </h1>
              <p className="pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>
                One connected campaign &amp; intelligence system across Marketing, Memberships and CRM.
              </p>
            </div>
            <div className="text-sm pulse-font-body shrink-0 mt-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
              {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </div>
          </div>
          <ModuleSwitcher user={user} current="comms" />
        </div>

        <CrossModuleTipsBanner mode="marketing" />

        {/* Section tabs */}
        <PillTabBar className="hidden md:block mb-4" activeId={section} testId="comms-sections-desktop" ariaLabel="Comms sections">
          {SECTIONS.map(({ id, label, icon: Icon }) => {
            const isActive = section === id;
            const activeStyle = isPulseBranded
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF', boxShadow: '0 6px 16px -6px rgba(37,99,235,0.35)' };
            return (
              <button
                key={id}
                data-pill-id={id}
                onClick={() => { setSection(id); navigate(`/comms?view=${id}`, { replace: true }); }}
                className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
                style={isActive ? activeStyle : { color: 'var(--theme-text-muted)', background: 'transparent' }}
                data-testid={`comms-section-${id}`}
              >
                <Icon size={14} /> {label}
              </button>
            );
          })}
        </PillTabBar>

        {/* Mobile section pills */}
        <div className="md:hidden mb-4 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
          {SECTIONS.map(({ id, label }) => {
            const isActive = section === id;
            return (
              <button key={id} onClick={() => { setSection(id); navigate(`/comms?view=${id}`, { replace: true }); }}
                className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap"
                style={isActive ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
                data-testid={`comms-section-pill-${id}`}>{label}</button>
            );
          })}
        </div>

        {/* Module scope (hidden for deliverability which is org-wide) */}
        {section !== 'deliverability' && (
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
