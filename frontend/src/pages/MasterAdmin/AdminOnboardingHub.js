/**
 * Master Admin — Onboarding Hub
 *
 * Single source of truth for ALL onboarding — customers and team.
 * Manage: project Dashboard (tracks every onboarding, checklist, go-live).
 * Customers: Onboard Site, Head Office (multi-site), Packets, Bulk Imports,
 * MOD Sites. Team: Onboard Staff (invite + role assignment).
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { Building2, Building, Clipboard, FileSpreadsheet, ShieldCheck, UserPlus, LayoutDashboard, BarChart3, Wrench, Dumbbell, Truck } from 'lucide-react';

import PulseOnboardingWizard from '../PulseOnboardingWizard';
import HeadOfficeOnboardingWizard from './HeadOfficeOnboardingWizard';
import AdminOnboardingPackets from './AdminOnboardingPackets';
import AdminBulkImports from './AdminBulkImports';
import MODBulkImport from './MODBulkImport';
import MODEstateWizard from './MODEstateWizard';
import MODSiteOnboarding from './MODSiteOnboarding';
import MODProviderDirectory from './MODProviderDirectory';
import StaffOnboardingWizard from './StaffOnboardingWizard';
import DealerOnboardingWizard from './DealerOnboardingWizard';
import StaffEngineers from '../BFPO/staff/StaffEngineers';
import OnboardingProjects from './OnboardingProjects';
import OnboardingReports from './OnboardingReports';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const TABS = [
  { id: 'dashboard',    group: 'Manage',    label: 'Dashboard',           icon: LayoutDashboard, description: 'Track every customer onboarding — progress, checklist, missing data and go-live readiness in one place.' },
  { id: 'reports',      group: 'Manage',    label: 'Reports',             icon: BarChart3,       description: 'Onboarding analytics, go-live success rate, exports (CSV/Excel/PDF) and the customer-portal toggle.' },
  { id: 'site',         group: 'Customers', label: 'Onboard Site',        icon: Building2,       description: 'Step-through wizard for a single brand-new customer site.' },
  { id: 'head-office',  group: 'Customers', label: 'Head Office (multi-site)', icon: Building,   description: 'Create a corporate Head Office and N sites under it in one pass — for chains and multi-location operators.' },
  { id: 'packets',      group: 'Customers', label: 'Onboarding Packets',  icon: Clipboard,       description: 'Shareable self-service forms for customers to complete themselves.' },
  { id: 'imports',      group: 'Customers', label: 'Bulk Imports',        icon: FileSpreadsheet, description: 'Upload CSV rosters of sites, equipment and customers.' },
  { id: 'mod-estate',   group: 'Customers', label: 'MOD Estate Setup',    icon: ShieldCheck,     description: 'Guided MOD setup — three independent service Head Offices (Army / RAF / Navy), global sites per service, external suppliers for overseas bases, and a whole-of-MOD reporting view.' },
  { id: 'mod-imports',  group: 'Customers', label: 'MOD Sites (CSV bulk)', icon: FileSpreadsheet, description: 'Provision dozens or thousands of MOD child sites under a HQ / branch with auto-generated kiosk logins.' },
  { id: 'mod-equipment', group: 'Customers', label: 'MOD Equipment & Readiness', icon: Dumbbell, description: 'Onboard each MOD site\'s equipment on their behalf (bulk CSV/Excel, like commercial) and track a per-site go-live checklist — Equipment, Staff, Suppliers, Documents, Check Sheets.' },
  { id: 'mod-providers', group: 'Customers', label: 'Service Providers', icon: Truck, description: 'Overseas service-provider directory — contact details and the MOD sites each provider covers. Assign providers to sites from MOD Equipment & Readiness.' },
  { id: 'dealer',       group: 'Partners',  label: 'Dealer / Engineer',   icon: Wrench,          description: 'Onboard a Pulse Fitness distribution dealer or field engineer — gets Service Desk + Inventory & Distribution. Captures full company detail; owner & engineers set up via invite link or temporary password.' },
  { id: 'staff',        group: 'Team',      label: 'Onboard Staff',       icon: UserPlus,        description: 'Invite a new team member — admin, owner, manager or staff. Five quick steps; they set their own password from a 72 h invite link.' },
  { id: 'bfpo-engineers', group: 'Team',    label: 'BFPO / MOD Engineers', icon: ShieldCheck,    description: 'Set up MOD/BFPO field engineers and leads — allocate their territories and sites, then send a set-password invite link or issue a temporary password.' },
];

const GROUPS = ['Manage', 'Customers', 'Partners', 'Team'];

// Map a checklist step launched from a project to the relevant wizard tab.
const STEP_TO_TAB = {
  primary_site: 'site', sites: 'imports', site_hierarchy: 'head-office',
  assets: 'imports', contacts: 'imports', members: 'imports', primary_users: 'site',
};

const AdminOnboardingHub = ({ API: _api, onComplete, isPulseAdmin = false, initialTab = 'dashboard' }) => {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'dashboard');
  const [types, setTypes] = useState([]);
  const active = TABS.find((t) => t.id === tab) || TABS[0];

  useEffect(() => {
    axios.get(`${API}/onboarding/customer-types`).then((r) => setTypes(r.data.types || [])).catch(() => {});
  }, []);

  return (
    <div className="space-y-5" data-testid="admin-onboarding-hub">
      {/* Grouped sub-tab pill bar — Manage / Customers / Team */}
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2 -mt-2">
        {GROUPS.map((grp) => (
          <div key={grp} className="flex flex-col">
            <span className="px-1 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{grp}</span>
            <div className="flex flex-wrap gap-1" role="tablist" aria-label={grp}>
              {TABS.filter((t) => t.group === grp).map((t) => {
                const Icon = t.icon;
                const isActive = tab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setTab(t.id)}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold whitespace-nowrap transition-all"
                    style={isActive
                      ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', boxShadow: '0 6px 16px -6px rgba(25, 205, 255, 0.35)' }
                      : { color: 'var(--theme-text-muted)', background: 'transparent' }}
                    role="tab"
                    aria-selected={isActive}
                    data-testid={`onboarding-subtab-${t.id}`}
                  >
                    <Icon size={14} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Sub-tab caption */}
      <p className="text-xs text-zinc-500" data-testid="onboarding-subtab-caption">{active.description}</p>

      {/* Active panel */}
      {tab === 'dashboard'   && <OnboardingProjects types={types} onLaunchWizard={(stepKey) => setTab(STEP_TO_TAB[stepKey] || 'imports')} />}
      {tab === 'reports'     && <OnboardingReports types={types} />}
      {tab === 'site'        && <PulseOnboardingWizard onComplete={onComplete} />}
      {tab === 'head-office' && <HeadOfficeOnboardingWizard onComplete={onComplete} />}
      {tab === 'packets'     && <AdminOnboardingPackets />}
      {tab === 'imports'     && <AdminBulkImports API={_api} />}
      {tab === 'mod-estate'  && <MODEstateWizard />}
      {tab === 'mod-imports' && <MODBulkImport API={_api} />}
      {tab === 'mod-equipment' && <MODSiteOnboarding />}
      {tab === 'mod-providers' && <MODProviderDirectory />}
      {tab === 'dealer'      && <DealerOnboardingWizard />}
      {tab === 'staff'       && <StaffOnboardingWizard isPulseAdmin={isPulseAdmin} />}
      {tab === 'bfpo-engineers' && <StaffEngineers />}
    </div>
  );
};

export default AdminOnboardingHub;
