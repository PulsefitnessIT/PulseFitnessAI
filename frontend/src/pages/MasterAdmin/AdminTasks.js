/**
 * AdminTasks — tabbed surface for setup checklists.
 *
 * Tab 1 — Setup Tasks: integration / import / compliance checklist that
 *   auto-ticks itself based on backend state.
 * Tab 2 — CRM / Marketing Tasks: vendor-neutral feature checklist for
 *   the CRM and Marketing modules (replaces the previous "HubSpot Parity"
 *   panel — no third-party brand names anywhere on the platform).
 */
import React, { useState } from 'react';
import SetupTasksPanel from './SetupTasksPanel';
import CrmMarketingTasksPanel from './CrmMarketingTasksPanel';
import { SubTabBar } from './SidebarConfig';

const TABS = [
  { id: 'setup',          label: 'Setup Tasks' },
  { id: 'crm-marketing',  label: 'CRM / Marketing' },
];

const AdminTasks = ({ API, setSection }) => {
  const [tab, setTab] = useState('setup');
  return (
    <div className="space-y-6" data-testid="admin-tasks-page">
      <SubTabBar tabs={TABS} active={tab} onChange={setTab} />
      {tab === 'setup' && <SetupTasksPanel API={API} onJumpToSection={setSection} />}
      {tab === 'crm-marketing' && <CrmMarketingTasksPanel />}
    </div>
  );
};

export default AdminTasks;
