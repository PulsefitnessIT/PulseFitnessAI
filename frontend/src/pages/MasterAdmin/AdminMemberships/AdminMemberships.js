import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import useMembershipsAdmin from './useMembershipsAdmin';
import OverviewTab from './OverviewTab';
import OrganisationsTab from './OrganisationsTab';
import TemplatesTab from './TemplatesTab';
import BookingRulesTab from './BookingRulesTab';
import RevenueTab from './RevenueTab';
import EngagementTab from './EngagementTab';
import InstructorsTab from './InstructorsTab';
import AiAndFlagsTab from './AiAndFlagsTab';
import SignupsFunnelTab from './SignupsFunnelTab';
import OrgDrawer from './OrgDrawer';

const TABS = [
 { id: 'overview', label: 'Overview' },
 { id: 'revenue', label: 'Revenue' },
 { id: 'organisations', label: 'Organisations' },
 { id: 'signups', label: 'Online Sign-ups' },
 { id: 'engagement', label: 'Engagement & Retention' },
 { id: 'instructors', label: 'Instructors' },
 { id: 'templates', label: 'Plan Templates' },
 { id: 'rules', label: 'Booking Rules' },
 { id: 'ai', label: 'AI Insights & Flags' },
];

const AdminMemberships = () => {
 const state = useMembershipsAdmin();
 const [tab, setTab] = useState('overview');
 const [orgId, setOrgId] = useState(null);

 if (state.loading && !state.overview) {
 return (
 <div className="flex items-center justify-center h-64" data-testid="memberships-admin-loading">
 <RefreshCw className="animate-spin text-zinc-400" size={24} />
 </div>
 );
 }

 return (
 <div className="space-y-5" data-testid="admin-memberships">
 <div className="flex gap-1 mb-2 flex-wrap" data-testid="memberships-admin-tabs">
 {TABS.map((t) => (
 <button
 key={t.id}
 onClick={() => setTab(t.id)}
 className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
 tab === t.id ? 'bg-[var(--color-brand-blue)] text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
 }`}
 data-testid={`memberships-tab-${t.id}`}
 >
 {t.label}
 </button>
 ))}
 </div>

 {tab === 'overview' && <OverviewTab overview={state.overview} onDrillOrg={setOrgId} onNavTab={setTab} />}
 {tab === 'organisations' && (
 <OrganisationsTab
 organizations={state.organizations}
 onSetOverrides={state.setOrgOverrides}
 onOpenOrg={setOrgId}
 />
 )}
 {tab === 'templates' && (
 <TemplatesTab
 templates={state.templates}
 organizations={state.organizations}
 onCreate={state.createTemplate}
 onUpdate={state.updateTemplate}
 onDelete={state.deleteTemplate}
 onApply={state.applyTemplate}
 />
 )}
 {tab === 'rules' && <BookingRulesTab rules={state.bookingRules} onSave={state.saveBookingRules} />}
 {tab === 'signups' && <SignupsFunnelTab />}
 {tab === 'revenue' && <RevenueTab revenue={state.revenue} />}
 {tab === 'engagement' && <EngagementTab engagement={state.engagement} />}
 {tab === 'instructors' && <InstructorsTab instructors={state.instructors} />}
 {tab === 'ai' && (
 <AiAndFlagsTab
 aiInsights={state.aiInsights}
 onLoadAiInsights={state.loadAiInsights}
 featureFlags={state.featureFlags}
 onSaveFlags={state.saveFeatureFlags}
 onDrillOrg={setOrgId}
 />
 )}

 <OrgDrawer orgId={orgId} onClose={() => setOrgId(null)} />
 </div>
 );
};

export default AdminMemberships;
