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
import { Clipboard, FileSpreadsheet, ShieldCheck, UserPlus, LayoutDashboard, BarChart3, Dumbbell, Truck, ListChecks, KeyRound, History, BookOpen } from 'lucide-react';

import AdminOnboardingPackets from './AdminOnboardingPackets';
import ImportCentre from './CustomerImport/ImportCentre';
import ReviewCentre from './CustomerImport/ReviewCentre';
import ImportHistory from './CustomerImport/ImportHistory';
import { OnboardingDashboard, CustomerActivation, TemplatesGuidance } from './CustomerImport/OnboardingViews';
import MODBulkImport from './MODBulkImport';
import MODEstateWizard from './MODEstateWizard';
import MODSiteOnboarding from './MODSiteOnboarding';
import ExternalServiceProviders from './ExternalServiceProviders';
import StaffOnboardingWizard from './StaffOnboardingWizard';
import OnboardingProjects from './OnboardingProjects';
import OnboardingReports from './OnboardingReports';
import OnboardingDelegates from './CustomerImport/OnboardingDelegates';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const TABS = [
  { id: 'dashboard',     group: 'Onboarding', label: 'Onboarding Dashboard', icon: LayoutDashboard, description: 'Where every Pulse-managed customer is in onboarding: imported, waiting for review, awaiting activation.' },
  { id: 'import-centre', group: 'Onboarding', label: 'Import Centre',        icon: FileSpreadsheet, description: 'The one place to import customer accounts, contacts, sites, equipment and contracts. Every route uses the same customer matching, review and approval.' },
  { id: 'projects',      group: 'Onboarding', label: 'Onboarding Projects',  icon: Clipboard,       description: 'One onboarding project per customer: checklist, missing data and go-live readiness.' },
  { id: 'review',        group: 'Onboarding', label: 'Review Centre',        icon: ListChecks,      description: 'Everything an import could not decide on its own, in one list: possible duplicates, unmatched contacts, proposed sites, Sage holds.' },
  { id: 'activation',    group: 'Onboarding', label: 'Customer Activation',  icon: KeyRound,        description: 'Customers imported but not yet activated. Nobody can sign in until an owner is verified and invited.' },
  { id: 'history',       group: 'Onboarding', label: 'Import History',       icon: History,         description: 'Every import that changed a customer estate, with reports and Undo.' },
  { id: 'guidance',      group: 'Onboarding', label: 'Templates & Guidance', icon: BookOpen,        description: 'Templates for each import type and the onboarding process in plain English.' },
  { id: 'reports',       group: 'Onboarding', label: 'Reports',              icon: BarChart3,       description: 'Onboarding analytics, go-live success rate and exports.' },
  { id: 'packets',       group: 'Specialist', label: 'Customer Questionnaires', icon: Clipboard,    description: 'Self-service onboarding forms customers fill in. Provisioning checks for existing customers first.' },
  { id: 'mod-estate',    group: 'Specialist', label: 'MOD Estate Setup',     icon: ShieldCheck,     description: 'MOD only: Army / RAF / Navy head offices, global sites and overseas suppliers.' },
  { id: 'mod-imports',   group: 'Specialist', label: 'MOD Sites (CSV)',      icon: FileSpreadsheet, description: 'MOD only: bulk MOD child sites with kiosk logins under the MOD access policy.' },
  { id: 'mod-equipment', group: 'Specialist', label: 'MOD Equipment & Readiness', icon: Dumbbell,   description: 'MOD only: per-site equipment and go-live checklist.' },
  { id: 'mod-providers', group: 'Specialist', label: 'External Service Providers', icon: Truck,     description: 'Overseas / external service providers and their field engineers.' },
  { id: 'delegates',     group: 'Pulse staff', label: 'Staff Permissions',   icon: KeyRound,        description: 'Let Service Administration and Aftersales staff prepare, review, approve or undo imports without Master Admin access.' },
  { id: 'staff',         group: 'Pulse staff', label: 'Onboard Pulse Staff', icon: UserPlus,        description: 'Pulse Fitness employees only — not customer logins. They set their own password from a 72 h invite link.' },
];

// Old tab ids and bookmarks → the consolidated screens.
const REDIRECT = { site: 'import-centre', 'head-office': 'import-centre', 'sage-import': 'import-centre', imports: 'import-centre' };

const GROUPS = ['Onboarding', 'Specialist', 'Pulse staff'];

// Map a checklist step launched from a project to the relevant wizard tab.
const STEP_TO_TAB = {
  primary_site: 'import-centre', sites: 'import-centre', site_hierarchy: 'import-centre',
  assets: 'import-centre', contacts: 'import-centre', members: 'import-centre', primary_users: 'activation',
};

const AdminOnboardingHub = ({ API: _api, isPulseAdmin = false, initialTab = 'dashboard' }) => {
  const params = new URLSearchParams(window.location.search);
  const want = REDIRECT[params.get('tab') || initialTab] || params.get('tab') || initialTab;
  const [tab, setTab] = useState(TABS.some((t) => t.id === want) ? want : 'dashboard');
  const [openJob, setOpenJob] = useState(null);
  const openJobIn = (id) => { setOpenJob(id); setTab('import-centre'); };
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
      {tab === 'dashboard'     && <OnboardingDashboard go={setTab} />}
      {tab === 'import-centre' && <ImportCentre key={openJob || 'ic'} initialType={params.get('type') || ''} initialOrg={params.get('org') || ''} openJobId={openJob} />}
      {tab === 'projects'      && <OnboardingProjects types={types} onLaunchWizard={(stepKey) => setTab(STEP_TO_TAB[stepKey] || 'import-centre')} />}
      {tab === 'review'        && <ReviewCentre onOpenJob={openJobIn} />}
      {tab === 'activation'    && <CustomerActivation />}
      {tab === 'history'       && <ImportHistory onOpenJob={openJobIn} />}
      {tab === 'guidance'      && <TemplatesGuidance />}
      {tab === 'reports'       && <OnboardingReports types={types} />}
      {tab === 'packets'       && <AdminOnboardingPackets />}
      {tab === 'mod-estate'    && <MODEstateWizard />}
      {tab === 'mod-imports'   && <MODBulkImport API={_api} />}
      {tab === 'mod-equipment' && <MODSiteOnboarding />}
      {tab === 'mod-providers' && <ExternalServiceProviders />}
      {tab === 'delegates'     && <OnboardingDelegates />}
      {tab === 'staff'         && <StaffOnboardingWizard isPulseAdmin={isPulseAdmin} />}
    </div>
  );
};

export default AdminOnboardingHub;
