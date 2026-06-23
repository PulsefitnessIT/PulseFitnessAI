/**
 * Pulse Fitness AI — Comms Centre.
 *
 * The central, merged campaign module. Layout mirrors the other modules
 * (Operations / Memberships / CRM / Marketing) byte-for-byte — unified
 * header + ModuleSwitcher + canonical PillTabBar — so switching modules
 * feels seamless. The pill tabs are CONTEXT VIEWS (All / Marketing /
 * Member emails / CRM & B2B) that filter the SAME shared campaign
 * records (no duplication).
 */
import React, { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Megaphone, Mail, Users, Briefcase } from 'lucide-react';

import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import PillTabBar from '@/components/shared/PillTabBar';
import CrossModuleTipsBanner from '@/components/shared/CrossModuleTipsBanner';
import CampaignsPanel from './CampaignsPanel';

const VIEWS = [
  { id: 'all', label: 'All campaigns', icon: Megaphone, module: 'all' },
  { id: 'marketing', label: 'Marketing', icon: Mail, module: 'marketing' },
  { id: 'memberships', label: 'Member emails', icon: Users, module: 'memberships' },
  { id: 'crm', label: 'CRM & B2B', icon: Briefcase, module: 'crm' },
];

export default function CommsCentre() {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const API = process.env.REACT_APP_BACKEND_URL;
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const initialView = (() => {
    const sp = new URLSearchParams(location.search);
    const v = sp.get('view');
    return VIEWS.some((x) => x.id === v) ? v : 'all';
  })();
  const [view, setView] = useState(initialView);
  const moduleParam = VIEWS.find((v) => v.id === view)?.module || 'all';

  // Brand parity with MarketingSuite: Pulse-account customers keep solid
  // cyan active pills; everyone else gets the brand gradient pill + the
  // theme-gymaxis token set in light mode.
  const isPulseBranded = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';

  if (!user) { navigate('/'); return null; }

  return (
    <div
      className={`min-h-screen ${!isPulseBranded && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}
      data-testid="comms-centre"
    >
      <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in">
        {/* Unified header — parity with Operations / Memberships / CRM / Marketing. */}
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
                One connected campaign system across Marketing, Memberships and CRM.
              </p>
            </div>
            <div className="text-sm pulse-font-body shrink-0 mt-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
              {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </div>
          </div>
          <ModuleSwitcher user={user} current="comms" />
        </div>

        <CrossModuleTipsBanner mode="marketing" />

        {/* Context views — canonical PillTabBar, branded pills (matches modules). */}
        <PillTabBar className="hidden md:block mb-6" activeId={view} testId="comms-tabs-desktop" ariaLabel="Comms views">
          {VIEWS.map(({ id, label, icon: Icon }) => {
            const isActive = view === id;
            const activeStyle = isPulseBranded
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF', boxShadow: '0 6px 16px -6px rgba(37,99,235,0.35)' };
            return (
              <button
                key={id}
                data-pill-id={id}
                onClick={() => { setView(id); navigate(`/comms?view=${id}`, { replace: true }); }}
                className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
                style={isActive ? activeStyle : { color: 'var(--theme-text-muted)', background: 'transparent' }}
                data-testid={`comms-view-${id}`}
              >
                <Icon size={14} /> {label}
              </button>
            );
          })}
        </PillTabBar>

        {/* Mobile scrollable pills */}
        <div className="md:hidden mb-5 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
          {VIEWS.map(({ id, label }) => {
            const isActive = view === id;
            const activeStyleMobile = isPulseBranded
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF' };
            return (
              <button
                key={id}
                onClick={() => { setView(id); navigate(`/comms?view=${id}`, { replace: true }); }}
                className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap transition-colors"
                style={isActive ? activeStyleMobile : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
                data-testid={`comms-pill-${id}`}
              >
                {label}
              </button>
            );
          })}
        </div>

        <CampaignsPanel key={moduleParam} API={API} headers={headers} module={moduleParam} testIdPrefix="comms" />
      </main>
    </div>
  );
}
