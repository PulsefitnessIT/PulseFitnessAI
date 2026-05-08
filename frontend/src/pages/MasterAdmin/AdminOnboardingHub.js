/**
 * Master Admin — Onboarding Hub
 *
 * Single landing page for everything customer-onboarding related.
 * Sub-tabs: Onboard Site (interactive wizard), Onboarding Packets
 * (shareable self-service links), Bulk Imports (CSV uploads).
 */
import React, { useState } from 'react';
import { Building2, Building, Clipboard, FileSpreadsheet } from 'lucide-react';

import PulseOnboardingWizard from '../PulseOnboardingWizard';
import HeadOfficeOnboardingWizard from './HeadOfficeOnboardingWizard';
import AdminOnboardingPackets from './AdminOnboardingPackets';
import AdminBulkImports from './AdminBulkImports';

const TABS = [
  { id: 'site',         label: 'Onboard Site',        icon: Building2,       description: 'Step-through wizard for a single brand-new customer site.' },
  { id: 'head-office',  label: 'Head Office (multi-site)', icon: Building,   description: 'Create a corporate Head Office and N sites under it in one pass — for chains and multi-location operators.' },
  { id: 'packets',      label: 'Onboarding Packets',  icon: Clipboard,       description: 'Shareable self-service forms for customers to complete themselves.' },
  { id: 'imports',      label: 'Bulk Imports',        icon: FileSpreadsheet, description: 'Upload CSV rosters of equipment and customers.' },
];

const AdminOnboardingHub = ({ API, onComplete }) => {
  const [tab, setTab] = useState('site');

  const active = TABS.find((t) => t.id === tab) || TABS[0];

  return (
    <div className="space-y-5" data-testid="admin-onboarding-hub">
      {/* Sub-tab pill bar */}
      <div className="flex flex-wrap gap-1 border-b border-zinc-200 -mt-2" role="tablist">
        {TABS.map((t) => {
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

      {/* Sub-tab caption */}
      <p className="text-xs text-zinc-500" data-testid="onboarding-subtab-caption">{active.description}</p>

      {/* Active panel */}
      {tab === 'site'        && <PulseOnboardingWizard onComplete={onComplete} />}
      {tab === 'head-office' && <HeadOfficeOnboardingWizard onComplete={onComplete} />}
      {tab === 'packets'     && <AdminOnboardingPackets />}
      {tab === 'imports'     && <AdminBulkImports API={API} />}
    </div>
  );
};

export default AdminOnboardingHub;
