import { Suspense, lazy, useState } from 'react';
import { SubTabBar } from './SidebarConfig';
import { useAuth } from '@/App';
import { Loader2 } from 'lucide-react';

// Iter 216h173 — Sub-panels lazy-loaded so the default Overview surface
// only ships the active inner tab (Service Portal · Overview by default)
// instead of dragging every cross-portal dashboard into the initial bundle.
const AdminOverview = lazy(() => import('./AdminOverview'));
const AdminPulse = lazy(() => import('./AdminPulse'));
const AdminOrganizations = lazy(() => import('./AdminOrganizations'));
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
 stats, pulseData, organizations, users, aiUsage, activityLog,
 orgsProps, mainToken,
 setSection, setSelectedOrg, setOrgFilter,
 loadSectionData, updateAccountType,
 navigate, API,
}) => {
 const { user } = useAuth();
 const isPulseAdmin = !!(user?.is_pulse_admin && !user?.is_master_admin);
 const [overviewActiveTab, setOverviewActiveTab] = useState('service-portal');
 const [spInnerTab, setSpInnerTab] = useState('pulse');
 const [crmInnerTab, setCrmInnerTab] = useState('dashboard');
 const [modInnerTab, setModInnerTab] = useState('organisations');

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

 const renderServicePortal = () => (
   <div>
     {renderTabBar(spTabs, spInnerTab, setSpInnerTab, 'sp')}
 {spInnerTab === 'pulse' && (
 <div className="space-y-6">
 <AdminOverview
 stats={stats}
 onGoPayments={() => setSection('payments')}
 onGoSuspended={() => { setOrgFilter('suspended'); setSpInnerTab('organisations'); }}
 onGoOnboardingPackets={() => setSection('onboarding')}
 onGoTrials={() => setSection('trials')}
 onGoArchive={() => setSection('archive')}
 onGoSection={setSection}
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

 const renderMoD = () => (
   <div>
     {renderTabBar(modTabs, modInnerTab, setModInnerTab, 'mod')}
     {modInnerTab === 'organisations' && (
       <AdminOrganizations
         {...orgsProps}
         accountTypesIn={['mod_site', 'mod_branch', 'mod_org']}
       />
     )}
   </div>
 );

 return (
 <div className="space-y-6">
 <SubTabBar
 tabs={[
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
 {overviewActiveTab === 'service-portal' && renderServicePortal()}
 {overviewActiveTab === 'crm' && renderCRM()}
 {overviewActiveTab === 'memberships' && <AdminMemberships />}
 {overviewActiveTab === 'marketing' && <AdminMarketingSuite API={API} />}
 {overviewActiveTab === 'mod' && renderMoD()}
 </Suspense>
 </div>
 );
};

export default OverviewSection;
