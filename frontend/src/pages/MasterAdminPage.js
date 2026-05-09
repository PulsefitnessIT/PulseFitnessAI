import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { RefreshCw, Menu, ArrowLeftRight, Shield } from 'lucide-react';

import IntegrationAdminPanel from './IntegrationAdminPanel';
import SiconIntegrationPage from './MasterAdmin/SiconIntegrationPage';
import FinancialOpsPanel from './FinancialOpsPanel';
import AdminOnboardingHub from './MasterAdmin/AdminOnboardingHub';
import AdminTrials from './MasterAdmin/AdminTrials';
import AdminMarketingSuite from './MasterAdmin/AdminMarketingSuite';
import AdminArchive from './MasterAdmin/AdminArchive';
import AdminTasks from './MasterAdmin/AdminTasks';
import AdminRoles from './MasterAdmin/AdminRoles';
import AdminPayments from './MasterAdmin/AdminPayments';
import AdminSupport from './MasterAdmin/AdminSupport';
import AdminEmails from './MasterAdmin/AdminEmails';
import AdminCapex from './MasterAdmin/AdminCapex';
import AdminDialogs from './MasterAdmin/AdminDialogs';
import TrustDashboard from './MasterAdmin/TrustDashboard';
import AskSupportDesk from './MasterAdmin/AskSupportDesk';
import AdminStripeConnect from './MasterAdmin/AdminStripeConnect';
import DesignSystemPage from './MasterAdmin/DesignSystemPage';
import PricingPanel from './MasterAdmin/PricingPanel';
import OrgBillingPanel from './MasterAdmin/OrgBillingPanel';
import EstateRollupPanel from './MasterAdmin/EstateRollupPanel';
import SalesInsightsPanel from './MasterAdmin/SalesInsightsPanel';
import LoginEventsPanel from './MasterAdmin/LoginEventsPanel';
import AuditLogPanel from './MasterAdmin/AuditLogPanel';
import LockedStaffPanel from './MasterAdmin/LockedStaffPanel';
import BackfillsPanel from './MasterAdmin/BackfillsPanel';
import ActivationFunnelPanel from './MasterAdmin/ActivationFunnelPanel';
import DocumentsPanel from './MasterAdmin/DocumentsPanel';
import CollectionsDashboard from './MasterAdmin/CollectionsDashboard';
import DbViewerPanel from './MasterAdmin/DbViewerPanel';
import CataloguePanel from './MasterAdmin/CataloguePanel';
import CustomPropertiesPanel from './MasterAdmin/CustomPropertiesPanel';
import RecentErrorsPanel from './MasterAdmin/RecentErrorsPanel';
import IntegrationHealthPanel from './MasterAdmin/IntegrationHealthPanel';
import EmailHealthPill from './MasterAdmin/EmailHealthPill';
import CommandPalette from './MasterAdmin/CommandPalette';

import AdminSidebar from './MasterAdmin/AdminSidebar';
import OverviewSection from './MasterAdmin/OverviewSection';
import AnalyticsSection from './MasterAdmin/AnalyticsSection';
import { sectionTitles, sectionDescriptions, GROUP_SUBTABS, SECTION_TO_GROUP } from './MasterAdmin/SidebarConfig';
import ConsolidatedTabsBar from './MasterAdmin/ConsolidatedTabsBar';
import useMasterAdminActions from './MasterAdmin/hooks/useMasterAdminActions';

const MasterAdminPage = ({ onBack }) => {
  const { user, API, logout } = useAuth();
  const isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin);
  const navigate = useNavigate();
  const handleLogout = () => { logout(); navigate('/login', { replace: true }); };

  const [section, setSection] = useState('overview');

  // Iter 215d — Master Admin is a light-mode-only surface. Force the
  // global `data-theme` attribute to "light" while this page is mounted
  // so any dark-mode preference inherited from operator portals does
  // not bleed into HQ tooling. Restored on unmount.
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.getAttribute('data-theme');
    root.setAttribute('data-theme', 'light');
    return () => {
      if (previous) root.setAttribute('data-theme', previous);
      else root.removeAttribute('data-theme');
    };
  }, []);

 // Honour ?section= deep links AND keep the URL in sync as the user
 // navigates. This makes every Master Admin section bookmarkable and
 // makes the browser back/forward buttons work as expected.
 //
 // - On mount: read ?section= from URL and apply it to local state.
 // - On state change: push the new section into the URL via
 //   replaceState (no extra history entries — just keeps the URL fresh).
 // - On popstate (back/forward): re-read the URL into state.
 useEffect(() => {
   const param = new URLSearchParams(window.location.search).get('section');
   if (param && param !== section) setSection(param);

   const onPop = () => {
     const p = new URLSearchParams(window.location.search).get('section') || 'overview';
     setSection(p);
   };
   window.addEventListener('popstate', onPop);
   return () => window.removeEventListener('popstate', onPop);
   // eslint-disable-next-line react-hooks/exhaustive-deps
 }, []);

 // Push state changes back into the URL (without adding a history entry
 // for every internal click — replaceState is intentional).
 useEffect(() => {
   const params = new URLSearchParams(window.location.search);
   const current = params.get('section');
   if (section === 'overview') {
     if (current) {
       params.delete('section');
       const qs = params.toString();
       window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname);
     }
     return;
   }
   if (current === section) return;
   params.set('section', section);
   window.history.replaceState({}, '', `?${params.toString()}`);
 }, [section]);

 // Iter 215ai — Listen for in-app navigation events. The LoginEvents
 // panel fires 'gymaxis:set-section' when the operator clicks
 // "View in full audit log →", and we route without a full reload.
 useEffect(() => {
   const onSet = (e) => {
     const next = typeof e.detail === 'string' ? e.detail : e.detail?.section;
     if (next) setSection(next);
   };
   window.addEventListener('gymaxis:set-section', onSet);
   return () => window.removeEventListener('gymaxis:set-section', onSet);
 }, []);
  const [refreshTick, setRefreshTick] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  const [users, setUsers] = useState([]);
  const [aiUsage, setAiUsage] = useState(null);
  const [activityLog, setActivityLog] = useState([]);
  const [emails, setEmails] = useState([]);
  const [pulseData, setPulseData] = useState(null);
  const [search, setSearch] = useState('');
  const [orgFilter, setOrgFilter] = useState('all');
  const [accountTypeFilter, setAccountTypeFilter] = useState('all');

  // Iter 215as · QW#3 — persist Org list filters in the URL so navigating
  // away and back (or sharing a link with a colleague) preserves the
  // exact view the master admin was looking at. We hydrate from the
  // URL on mount and replaceState on every state change.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const q = p.get('q'); if (q !== null) setSearch(q);
    const s = p.get('status'); if (s) setOrgFilter(s);
    const a = p.get('account'); if (a) setAccountTypeFilter(a);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const writeOrDelete = (k, v, def) => {
      if (!v || v === def) params.delete(k); else params.set(k, v);
    };
    writeOrDelete('q', search, '');
    writeOrDelete('status', orgFilter, 'all');
    writeOrDelete('account', accountTypeFilter, 'all');
    const qs = params.toString();
    window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname);
  }, [search, orgFilter, accountTypeFilter]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [featuresDialog, setFeaturesDialog] = useState(null);
  const [impersonateDialog, setImpersonateDialog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [capexThresholds, setCapexThresholds] = useState(null);
  const [capexOverview, setCapexOverview] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [billingOrgId, setBillingOrgId] = useState(null);

  const mainToken = localStorage.getItem('token');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const handlePulseSwitch = () => { window.location.href = '/pulse'; };
  // Iter 215bs — One-click "as operator" preview into the GymAxis dashboard
  // so master admins can sanity-check the operator UX without seeding a
  // fake user. The `?as=operator` flag bypasses the master-admin redirect
  // gate in App.js for this navigation.
  const handleGymAxisSwitch = () => { window.location.href = '/dashboard?as=operator'; };

  const loadCapexConfig = useCallback(async () => {
    try {
      const [tRes, oRes] = await Promise.all([
        axios.get(`${API}/capex/defaults`, { headers }).catch(() => null),
        axios.get(`${API}/capex/master-admin/overview`, { headers }).catch(() => null),
      ]);
      if (tRes?.data) setCapexThresholds(tRes.data.thresholds);
      if (oRes?.data) setCapexOverview(oRes.data.organizations);
    } catch { /* ignored */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, orgsRes, usersRes] = await Promise.all([
        axios.get(`${API}/master-admin/stats`, { headers }),
        axios.get(`${API}/master-admin/organizations`, { headers }),
        axios.get(`${API}/master-admin/users`, { headers }),
      ]);
      setStats(statsRes.data);
      setOrganizations(orgsRes.data.organizations || []);
      setUsers(usersRes.data.users || []);
    } catch { /* ignored */ }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  const loadSectionData = useCallback(async (sec) => {
    try {
      if (sec === 'overview') {
        const [usage, activity, pulse] = await Promise.all([
          axios.get(`${API}/master-admin/ai-usage`, { headers }),
          axios.get(`${API}/master-admin/activity-log`, { headers }),
          axios.get(`${API}/master-admin/pulse-stats`, { headers }),
        ]);
        setAiUsage(usage.data);
        setActivityLog(activity.data.logs || []);
        setPulseData(pulse.data);
      }
      if (sec === 'emails') {
        const res = await axios.get(`${API}/master-admin/emails`, { headers });
        setEmails(res.data.emails || []);
      }
      if (sec === 'capex-config') loadCapexConfig();
    } catch { /* ignored */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API, loadCapexConfig]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { loadSectionData(section); }, [section, loadSectionData]);

  const actions = useMasterAdminActions({ API, headers, loadData, loadSectionData });

  const saveCapexThresholds = async () => {
    try {
      await axios.put(`${API}/capex/thresholds`, capexThresholds, { headers });
      notify.success('CAPEX thresholds updated');
    } catch { notify.error('Failed to save thresholds'); }
  };

  const filteredOrgs = organizations.filter(o => {
    if (orgFilter !== 'all' && o.status !== orgFilter) return false;
    if (search && !o.name?.toLowerCase().includes(search.toLowerCase()) && !o.owner_email?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  // Shared props bundle for the AdminOrganizations component (used in both SP & CRM sub-tabs)
  const orgsProps = {
    filteredOrgs, search, onSearchChange: setSearch,
    orgFilter, onOrgFilterChange: setOrgFilter,
    accountTypeFilter, onAccountTypeFilterChange: setAccountTypeFilter,
    onUpdateTier: actions.updateOrgTier,
    onUpdateStatus: actions.updateOrgStatus,
    onUpdateAccountType: actions.updateAccountType,
    onToggleTest: actions.toggleTestFlag,
    onSetFeatures: setFeaturesDialog,
    onSelectOrg: setSelectedOrg,
    selectedOrg,
    users,
    onImpersonate: (userId) => actions.impersonateUser(userId, setImpersonateDialog),
    onResetPassword: actions.resetPassword,
    onDisableUser: actions.disableUser,
    onUpdateFeatures: actions.updateOrgFeatures,
    onCreateOrg: actions.createOrganization,
    onAddUserToOrg: actions.addUserToOrganization,
    onArchiveUser: actions.archiveUser,
    onHardDeleteUser: actions.hardDeleteUser,
    onEditUser: actions.editUser,
    onSendEmailPreview: actions.sendEmailPreview,
    // QW#4 — let the org panel refresh data without a full page reload.
    onReloadOrgs: loadData,
  };

  const renderSection = () => {
    switch (section) {
      case 'overview':
        return (
          <OverviewSection
            stats={stats}
            pulseData={pulseData}
            organizations={organizations}
            users={users}
            aiUsage={aiUsage}
            activityLog={activityLog}
            orgsProps={orgsProps}
            mainToken={mainToken}
            setSection={setSection}
            setSelectedOrg={setSelectedOrg}
            setOrgFilter={setOrgFilter}
            loadSectionData={loadSectionData}
            updateAccountType={actions.updateAccountType}
            navigate={navigate}
            API={API}
          />
        );
      case 'payments':
        return <AdminPayments stats={stats} organizations={organizations} />;
      case 'trust':
        return <TrustDashboard refreshTick={refreshTick} />;
      case 'ask-support':
        return <AskSupportDesk />;
      case 'analytics':
        return <AnalyticsSection />;
      case 'orbit4':
        return <IntegrationAdminPanel integrationId="orbit4" title="Orbit 4" icon={ArrowLeftRight} color="bg-blue-600" />;
      case 'sicon-integration':
        return <SiconIntegrationPage />;
      case 'support':
        return <AdminSupport stats={stats} onGoUsers={() => setSection('organizations')} />;
      case 'emails':
        return <AdminEmails emails={emails} />;
      case 'capex-config':
        return (
          <AdminCapex
            capexThresholds={capexThresholds}
            setCapexThresholds={setCapexThresholds}
            capexOverview={capexOverview}
            onSave={saveCapexThresholds}
            onRefresh={loadCapexConfig}
          />
        );
      case 'financial-ops':
        return <FinancialOpsPanel />;
      case 'refunds':
        return <AdminRefundsPanel />;
      case 'design-system':
        return <DesignSystemPage />;
      case 'onboarding':
        return <AdminOnboardingHub API={API} onComplete={(orgId) => {
          // Iter 216f — drop directly into the org edit drawer for the
          // freshly-created org so the operator can immediately add
          // per-site users without hunting through the org list.
          setSection('organizations');
          if (orgId) {
            // The list page reads `?expand=<id>` from the URL on mount.
            try { window.history.replaceState({}, '', `/master-admin/organizations?expand=${orgId}&view=users`); } catch { /* noop */ }
          }
        }} />;
      case 'trials':
        return <AdminTrials />;
      case 'tasks':
        return <AdminTasks API={API} setSection={setSection} />;
      case 'marketing-suite':
        return <AdminMarketingSuite API={API} />;
      case 'roles':
        return <AdminRoles API={API} />;
      case 'stripe-connect':
        return <AdminStripeConnect API={API} isMasterAdmin={!isPulseAdmin} />;
      case 'pricing':
        return <PricingPanel />;
      case 'estate-rollup':
        return <EstateRollupPanel />;
      case 'sales-insights':
        return <SalesInsightsPanel />;
      case 'org-billing': {
        const selected = billingOrgId ? organizations.find((o) => o.id === billingOrgId) : null;
        if (selected) {
          return <OrgBillingPanel org={selected} onBack={() => setBillingOrgId(null)} />;
        }
        return <OrgBillingPicker organizations={filteredOrgs} search={search} setSearch={setSearch} onPick={setBillingOrgId} />;
      }
      case 'login-events':
        return <LoginEventsPanel />;
      case 'audit-log':
        return <AuditLogPanel />;
      case 'locked-staff':
        return <LockedStaffPanel />;
      case 'backfills':
        return <BackfillsPanel />;
      case 'activation-funnel':
        return <ActivationFunnelPanel />;
      case 'documents':
        return <DocumentsPanel />;
      case 'collections':
        return <CollectionsDashboard onPickOrg={(orgId) => { setSection('org-billing'); setBillingOrgId(orgId); }} />;
      case 'db-viewer':
        return <DbViewerPanel />;
      case 'catalogue':
        return <CataloguePanel />;
      case 'custom-properties':
        return <CustomPropertiesPanel />;
      case 'recent-errors':
        return <RecentErrorsPanel />;
      case 'integration-health':
        return <IntegrationHealthPanel />;
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen bg-[var(--gx-bg)] theme-gymaxis" data-testid="master-admin-page" data-theme="light">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          data-testid="sidebar-backdrop"
        />
      )}

      <AdminSidebar
        section={section}
        setSection={setSection}
        setSearch={setSearch}
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        onLogout={handleLogout}
        onPulseSwitch={handlePulseSwitch}
        onGymAxisSwitch={handleGymAxisSwitch}
        isPulseAdmin={isPulseAdmin}
      />

      <main className="flex-1 overflow-y-auto min-w-0">
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1440px]">
          <div className="flex items-center gap-3 mb-4 lg:mb-6">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 -ml-2 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg"
              data-testid="sidebar-toggle-btn"
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900 truncate">
                {sectionTitles[section]}
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5 truncate">
                {sectionDescriptions[section] || ''}
              </p>
            </div>
            {isPulseAdmin && (
              <span
                className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-amber-700"
                title="Pulse Master Admin scope — only Pulse-visible accounts are shown"
                data-testid="pulse-admin-scope-pill"
              >
                <Shield size={11} />Pulse Admin
              </span>
            )}
            <CommandPalette
              orgs={organizations}
              isPulseAdmin={isPulseAdmin}
              onJumpSection={(id) => setSection(id)}
              onOpenOrg={(o) => {
                // Jump to overview, then surface the org by setting the
                // shared selectedOrg state — AdminOrganizations consumes
                // it via the orgsProps bundle.
                setSection('overview');
                setSelectedOrg(o);
              }}
            />
            <EmailHealthPill />
            <Button
              size="sm"
              variant="outline"
              disabled={refreshing}
              className="border-zinc-200 text-zinc-600 hover:bg-zinc-100 flex-shrink-0"
              onClick={async () => {
                setRefreshing(true);
                try {
                  await Promise.all([loadData(), loadSectionData(section)]);
                  setRefreshTick(t => t + 1);  // signals child sections to re-fetch
                  notify.success('Refreshed');
                } catch (e) {
                  notify.error('Refresh failed');
                } finally {
                  setRefreshing(false);
                }
              }}
              data-testid="refresh-data-btn"
            >
              <RefreshCw size={14} className={`mr-1 hidden sm:inline ${refreshing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{refreshing ? 'Refreshing…' : 'Refresh'}</span>
              <RefreshCw size={14} className={`sm:hidden ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>

          {loading && !stats ? (
            <div className="flex items-center justify-center h-64">
              <RefreshCw className="animate-spin text-zinc-400" size={24} />
            </div>
          ) : (
            <>
              {(() => {
                // Render the in-page sub-tab bar when the active section
                // belongs to a consolidated group (Finance / Security /
                // Growth / Support).
                const groupId = SECTION_TO_GROUP[section];
                const subTabs = groupId ? GROUP_SUBTABS[groupId] : null;
                if (!subTabs) return null;
                const visible = subTabs.filter((t) => !t.gymaxisOnly || !isPulseAdmin);
                return (
                  <ConsolidatedTabsBar
                    tabs={visible}
                    active={section}
                    onChange={setSection}
                    testid={`group-tabs-${groupId}`}
                  />
                );
              })()}
              {renderSection()}
            </>
          )}
        </div>
      </main>

      <AdminDialogs
        featuresDialog={featuresDialog}
        setFeaturesDialog={setFeaturesDialog}
        onUpdateFeatures={actions.updateOrgFeatures}
        impersonateDialog={impersonateDialog}
        setImpersonateDialog={setImpersonateDialog}
        selectedOrg={selectedOrg}
        setSelectedOrg={setSelectedOrg}
      />
    </div>
  );
};

export default MasterAdminPage;


/* ─────────────────── Org Billing — simple picker ─────────────────── */
/**
 * Lightweight org chooser shown when the master admin opens the
 * "Org Billing" section before drilling into a specific organisation.
 */
function OrgBillingPicker({ organizations, search, setSearch, onPick }) {
  const [running, setRunning] = useState(false);

  const runRenewals = async () => {
    setRunning(true);
    try {
      const token = localStorage.getItem('token');
      const r = await axios.post(
        `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/billing/run-renewals`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const d = r.data;
      const msg = `${d.invoices_created} invoice(s) generated, ${d.skipped} skipped${d.errors?.length ? `, ${d.errors.length} errors` : ''}`;
      window.alert(`Renewals complete — ${msg}`);
    } catch (e) {
      window.alert('Renewals failed: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div data-testid="org-billing-picker" className="space-y-4">
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <input
            type="search"
            value={search || ''}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search organisations…"
            className="flex-1 min-w-[200px] px-3 py-2 text-sm rounded border border-zinc-200 bg-zinc-50 text-zinc-900"
            data-testid="org-billing-search"
          />
          <button
            onClick={runRenewals}
            disabled={running}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50 whitespace-nowrap"
            data-testid="org-billing-run-renewals-btn"
            title="Auto-generate invoices for orgs whose next_renewal_at has passed"
          >
            {running ? '⟳ Running…' : '⟳ Run renewals now'}
          </button>
        </div>
        <div className="text-xs text-zinc-500 mb-3">
          Pick an organisation to view their bill-to-date, generate invoices, or record manual payments.
        </div>
        <div className="space-y-1 max-h-[60vh] overflow-y-auto">
          {organizations.map((o) => (
            <button
              key={o.id}
              onClick={() => onPick(o.id)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-zinc-100 text-left"
              data-testid={`org-billing-pick-${o.id}`}
            >
              <div className="w-2 h-8 rounded bg-[var(--color-brand-cyan)]" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-zinc-900 truncate">
                  {o.name || o.company_name}
                </div>
                <div className="text-xs text-zinc-500 truncate">
                  {o.account_type || 'gymaxis'} · {o.owner_email || '—'}
                </div>
              </div>
              <span className="text-xs text-zinc-400 hidden sm:inline">Open →</span>
            </button>
          ))}
          {organizations.length === 0 && (
            <div className="text-sm text-zinc-400 italic text-center py-8">No organisations match.</div>
          )}
        </div>
      </div>
    </div>
  );
}

