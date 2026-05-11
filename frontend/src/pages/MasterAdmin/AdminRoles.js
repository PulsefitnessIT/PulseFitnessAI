/**
 * AdminRoles — combines GymAxis-master-only role-management surfaces under
 * a single "Roles" sidebar entry:
 *
 *   1. Service Desk Members  (Pulse Fitness internal ops staff with /service-desk access)
 *   2. Pulse Master Admins   (delegated platform admins, see scoped /master-admin)
 *   3. Permissions matrix    (SOC 2 view of who's attached where)
 *   4. Users                 (Iter 216h9 — cross-org user directory with archive + delete + leaver flow)
 *
 * Each lives behind its own sub-tab pill.
 */
import React, { useState } from 'react';
import { UserCog, KeyRound, Grid3x3, Users } from 'lucide-react';
import AdminServiceDesk from './AdminServiceDesk';
import AdminPulseAdmins from './AdminPulseAdmins';
import PermissionsMatrix from './PermissionsMatrix';
import GlobalUsersPanel from './GlobalUsersPanel';

const TABS = [
  { id: 'service-desk', label: 'Service Desk Members', icon: UserCog },
  { id: 'pulse-admins', label: 'Pulse Master Admins', icon: KeyRound },
  { id: 'matrix', label: 'Permissions matrix', icon: Grid3x3 },
  { id: 'users', label: 'Users', icon: Users },
];

const AdminRoles = ({ API, globalUsersProps }) => {
  const [tab, setTab] = useState('service-desk');

  return (
    <div className="space-y-6" data-testid="admin-roles-page">
      <div className="flex gap-1 border-b border-zinc-200 overflow-x-auto" data-testid="roles-sub-tabs">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              tab === id
                ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]'
                : 'border-transparent text-zinc-500 hover:text-zinc-700'
            }`}
            data-testid={`roles-tab-${id}`}
          >
            <Icon size={14} className="inline mr-1.5 -mt-0.5" /> {label}
          </button>
        ))}
      </div>

      {tab === 'service-desk' && <AdminServiceDesk API={API} />}
      {tab === 'pulse-admins' && <AdminPulseAdmins API={API} />}
      {tab === 'matrix' && <PermissionsMatrix API={API} />}
      {tab === 'users' && <GlobalUsersPanel {...(globalUsersProps || {})} />}
    </div>
  );
};

export default AdminRoles;
