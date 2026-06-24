/**
 * Master Admin — Onboarding Hub
 *
 * Single source of truth for ALL onboarding — customers and team.
 * Customers: Onboard Site, Head Office (multi-site), Packets, Bulk Imports,
 * MOD Sites. Team: Onboard Staff (invite + role assignment).
 */
import { useState } from 'react';
import { Building2, Building, Clipboard, FileSpreadsheet, ShieldCheck, UserPlus } from 'lucide-react';

import PulseOnboardingWizard from '../PulseOnboardingWizard';
import HeadOfficeOnboardingWizard from './HeadOfficeOnboardingWizard';
import AdminOnboardingPackets from './AdminOnboardingPackets';
import AdminBulkImports from './AdminBulkImports';
import MODBulkImport from './MODBulkImport';
import StaffOnboardingWizard from './StaffOnboardingWizard';

const TABS = [
  { id: 'site',         group: 'Customers', label: 'Onboard Site',        icon: Building2,       description: 'Step-through wizard for a single brand-new customer site.' },
  { id: 'head-office',  group: 'Customers', label: 'Head Office (multi-site)', icon: Building,   description: 'Create a corporate Head Office and N sites under it in one pass — for chains and multi-location operators.' },
  { id: 'packets',      group: 'Customers', label: 'Onboarding Packets',  icon: Clipboard,       description: 'Shareable self-service forms for customers to complete themselves.' },
  { id: 'imports',      group: 'Customers', label: 'Bulk Imports',        icon: FileSpreadsheet, description: 'Upload CSV rosters of equipment and customers.' },
  { id: 'mod-imports',  group: 'Customers', label: 'MOD Sites (bulk)',    icon: ShieldCheck,     description: 'Provision dozens or thousands of MOD child sites under a HQ / branch with auto-generated kiosk logins.' },
  { id: 'staff',        group: 'Team',      label: 'Onboard Staff',       icon: UserPlus,        description: 'Invite a new team member — admin, owner, manager or staff. Five quick steps; they set their own password from a 72 h invite link.' },
];

const GROUPS = ['Customers', 'Team'];

const AdminOnboardingHub = ({ API, onComplete, isPulseAdmin = false, initialTab = 'site' }) => {
  const [tab, setTab] = useState(TABS.some((t) => t.id === initialTab) ? initialTab : 'site');
  const active = TABS.find((t) => t.id === tab) || TABS[0];

  return (
    <div className="space-y-5" data-testid="admin-onboarding-hub">
      {/* Grouped sub-tab pill bar — Customers vs Team */}
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2 border-b border-zinc-200 -mt-2">
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
                    className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                      isActive
                        ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]'
                        : 'border-transparent text-zinc-500 hover:text-zinc-800 hover:border-zinc-300'
                    }`}
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
      {tab === 'site'        && <PulseOnboardingWizard onComplete={onComplete} />}
      {tab === 'head-office' && <HeadOfficeOnboardingWizard onComplete={onComplete} />}
      {tab === 'packets'     && <AdminOnboardingPackets />}
      {tab === 'imports'     && <AdminBulkImports API={API} />}
      {tab === 'mod-imports' && <MODBulkImport API={API} />}
      {tab === 'staff'       && <StaffOnboardingWizard isPulseAdmin={isPulseAdmin} />}
    </div>
  );
};

export default AdminOnboardingHub;
