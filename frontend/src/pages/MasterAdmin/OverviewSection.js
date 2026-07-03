import { Suspense, lazy, useState } from 'react';
import { SubTabBar } from './SidebarConfig';
import { useAuth } from '@/App';
import { Loader2 } from 'lucide-react';

// Iter 216h173 — Sub-panels lazy-loaded so the default Overview surface
// only ships the active inner tab (Service Portal · Overview by default)
// instead of dragging every cross-portal dashboard into the initial bundle.
const AdminOverview = lazy(() => import('./AdminOverview'));
const OperationsOverview = lazy(() => import('./OperationsOverview'));
const AdminPulse = lazy(() => import('./AdminPulse'));
const AdminOrganizations = lazy(() => import('./AdminOrganizations'));
const AdminMODConsole = lazy(() => import('./AdminMODConsole'));
const AdminAiUsage = lazy(() => import('./AdminAiUsage'));
const AdminActivity = lazy(() => import('./AdminActivity'));
const AdminCRMAnalytics = lazy(() => import('./AdminCRMAnalytics'));
const AdminMemberships = lazy(() => import('./AdminMemberships/AdminMemberships'));
const AdminMarketingSuite = lazy(() => import('./AdminMarketingSuite'));

const InnerFallback = () => (
  <div className="flex items-center justify-center py-12 text-zinc-400" data-testid="overview-inner-loading">
    <Loader2 size={18} className="animate-spin" />
  </div>
);

/**
 * Combined "Dashboard Overview" section — top-level toggle between
 * Service Portal / CRM / Memberships / MoD, each with its own inner tab strip.
 *
 * The Setup-Tasks checklist lives under its own sidebar item now (see
 * AdminTasks.js) so this section stays focused on KPIs + organisation
 * management.
 */
const OverviewSection = ({
 stats, pulseData, organizations, _users, aiUsage, activityLog,
 orgsProps, mainToken,
 setSection, setSelectedOrg, setOrgFilter,
 loadSectionData, updateAccountType,
 _navigate, API,
}) => {
 const { user } = useAuth();
 const isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin);
 const [overviewActiveTab, setOverviewActiveTab] = useState('platform');
 const [spInnerTab, setSpInnerTab] = useState('pulse');
 const [crmInnerTab, setCrmInnerTab] = useState('dashboard');
 const [modInnerTab, setModInnerTab] = useState('organisations');
 // Iter 233b — MoD KPI cards act as account-type filters on the list.
 const [modTypeFilter, setModTypeFilter] = useState(null);

 const spTabs = [
 { id: 'pulse', label: 'Overview' },
 { id: 'organisations', label: 'Organisations' },
 { id: 'ai-usage', label: 'AI Usage' },
 { id: 'activity', label: 'Activity Log' },
 ];

 const crmTabs = [
 { id: 'dashboard', label: 'CRM Dashboard' },
 { id: 'organisations', label: 'Organisations' },
 ];

 const modTabs = [
 { id: 'organisations', label: 'Organisations' },
 { id: 'console', label: 'MOD Console & ASER' },
 ];

 const renderTabBar = (tabs, activeId, setActiveId, testIdPrefix) => (
   <div className="subtab-bar mb-5 flex-wrap" data-testid={`${testIdPrefix}-inner-tabs`}>
     {tabs.map(tab => (
       <button
         key={tab.id}
         type="button"
         onClick={() => setActiveId(tab.id)}
         className={`subtab-pill ${activeId === tab.id ? 'is-active' : ''}`}
         data-testid={`${testIdPrefix}-tab-${tab.id}`}
       >
         {tab.label}
       </button>
     ))}
   </div>
 );

 const renderPlatform = () => (
   <div data-testid="platform-overview">
     <AdminOverview
       stats={stats}
       isPulseAdmin={isPulseAdmin}
       onGoPayments={() => setSection('payments')}
       onGoSuspended={() => { setOrgFilter('suspended'); setOverviewActiveTab('service-portal'); setSpInnerTab('organisations'); }}
       onGoOnboardingPackets={() => setSection('onboarding')}
       onGoTrials={() => setSection('trials')}
       onGoArchive={() => setSection('archive')}
       onGoSection={setSection}
     />
   </div>
 );

 const renderServicePortal = () => (
   <div>
     {renderTabBar(spTabs, spInnerTab, setSpInnerTab, 'sp')}
 {spInnerTab === 'pulse' && (
 <div className="space-y-6">
 <OperationsOverview
 token={mainToken}
 onGoSection={setSection}
 onGoPayments={() => setSection('payments')}
 onGoSuspended={() => { setOrgFilter('suspended'); setSpInnerTab('organisations'); }}
 />
 {pulseData && (
 <AdminPulse
 pulseData={pulseData}
 onRefresh={() => loadSectionData('pulse')}
 organizations={organizations}
 onSelectOrg={setSelectedOrg}
 onUpgrade={updateAccountType}
 headers={{ Authorization: `Bearer ${mainToken}` }}
 API={API}
 />
 )}
 </div>
 )}
 {spInnerTab === 'organisations' && (
 <AdminOrganizations {...orgsProps} portalFilter="service_portal" />
 )}
 {spInnerTab === 'ai-usage' && <AdminAiUsage aiUsage={aiUsage} />}
 {spInnerTab === 'activity' && (
 <AdminActivity activityLog={activityLog} onRefresh={() => loadSectionData('activity')} />
 )}
 </div>
 );

 const renderCRM = () => (
   <div>
     {renderTabBar(crmTabs, crmInnerTab, setCrmInnerTab, 'crm')}
     {crmInnerTab === 'dashboard' && <AdminCRMAnalytics />}
     {crmInnerTab === 'organisations' && (
       <AdminOrganizations {...orgsProps} portalFilter="crm" />
     )}
   </div>
 );

 const MOD_TYPES = [
   { type: 'mod_org', label: 'MoD Organisations', hint: 'Top-level commands' },
   { type: 'mod_branch', label: 'Branches', hint: 'Regional branches' },
   { type: 'mod_site', label: 'Sites', hint: 'Individual sites' },
 ];

 const renderMoD = () => {
   const modCounts = MOD_TYPES.map((t) => ({
     ...t,
     count: (organizations || []).filter((o) => o.account_type === t.type).length,
   }));
   return (
   <div>
     {renderTabBar(modTabs, modInnerTab, setModInnerTab, 'mod')}
     {modInnerTab === 'organisations' && (
       <>
         {/* Iter 233b — KPI cards double as account-type filters: click a
             card to narrow the list to that tier, click again to clear. */}
         <div className="grid grid-cols-3 gap-3 mb-5" data-testid="mod-kpi-row">
           {modCounts.map((c) => {
             const active = modTypeFilter === c.type;
             return (
               <button
                 key={c.type}
                 type="button"
                 onClick={() => setModTypeFilter(active ? null : c.type)}
                 className={`text-left rounded-xl border p-4 transition-all cursor-pointer hover:-translate-y-0.5 hover:shadow-md ${active
                   ? 'border-[var(--color-brand-blue)] bg-blue-50 dark:bg-blue-500/10 ring-1 ring-[var(--color-brand-blue)]'
                   : 'border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-700'}`}
                 data-testid={`mod-kpi-${c.type}`}
                 aria-pressed={active}
               >
                 <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">{c.label}</p>
                 <p className="text-2xl font-bold mt-1 text-zinc-900 dark:text-zinc-100">{c.count}</p>
                 <p className="text-[11px] text-zinc-400 mt-0.5">{active ? 'Filtering — click to clear' : c.hint}</p>
               </button>
             );
           })}
         </div>
         <AdminOrganizations
           {...orgsProps}
           accountTypesIn={modTypeFilter ? [modTypeFilter] : ['mod_site', 'mod_branch', 'mod_org']}
         />
       </>
     )}
     {modInnerTab === 'console' && (
       <Suspense fallback={<div className="py-10 text-center text-sm text-zinc-500">Loading MOD Console…</div>}>
         <AdminMODConsole API={API} />
       </Suspense>
     )}
   </div>
   );
 };

 return (
 <div className="space-y-6">
 <SubTabBar
 tabs={[
 { id: 'platform', label: 'Platform' },
 { id: 'service-portal', label: isPulseAdmin ? 'Operations Portal (Pulse)' : 'Operations Portal' },
 { id: 'crm', label: 'CRM' },
 { id: 'memberships', label: 'Memberships' },
 { id: 'marketing', label: 'Marketing' },
 { id: 'mod', label: 'MoD' },
 ]}
 active={overviewActiveTab}
 onChange={setOverviewActiveTab}
 />
 <Suspense fallback={<InnerFallback />}>
 {overviewActiveTab === 'platform' && renderPlatform()}
 {overviewActiveTab === 'service-portal' && renderServicePortal()}
 {overviewActiveTab === 'crm' && renderCRM()}
 {overviewActiveTab === 'memberships' && <AdminMemberships />}
 {overviewActiveTab === 'marketing' && (
   <AdminMarketingSuite
     API={API}
     onGoSection={setSection}
     onGoAiUsage={() => { setOverviewActiveTab('service-portal'); setSpInnerTab('ai-usage'); }}
   />
 )}
 {overviewActiveTab === 'mod' && renderMoD()}
 </Suspense>
 </div>
 );
};

export default OverviewSection;
