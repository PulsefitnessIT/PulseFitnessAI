/**
 * AdminRoles — combines two GymAxis-master-only role-management surfaces under
 * a single "Roles" sidebar entry:
 *
 *   1. Service Desk Members  (Pulse Fitness internal ops staff with /service-desk access)
 *   2. Pulse Master Admins   (delegated platform admins, see scoped /master-admin)
 *
 * Each lives behind its own sub-tab pill. Replaces the two separate sidebar
 * items that used to clutter the Tools group.
 */
import React, { useState } from 'react';
import { UserCog, KeyRound } from 'lucide-react';
import AdminServiceDesk from './AdminServiceDesk';
import AdminPulseAdmins from './AdminPulseAdmins';

const AdminRoles = ({ API }) => {
  const [tab, setTab] = useState('service-desk');

  return (
    <div className="space-y-6" data-testid="admin-roles-page">
      <div className="flex gap-1 border-b border-zinc-200" data-testid="roles-sub-tabs">
        <button
          onClick={() => setTab('service-desk')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === 'service-desk'
              ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]'
              : 'border-transparent text-zinc-500 hover:text-zinc-700'
          }`}
          data-testid="roles-tab-service-desk"
        >
          <UserCog size={14} className="inline mr-1.5 -mt-0.5" /> Service Desk Members
        </button>
        <button
          onClick={() => setTab('pulse-admins')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === 'pulse-admins'
              ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]'
              : 'border-transparent text-zinc-500 hover:text-zinc-700'
          }`}
          data-testid="roles-tab-pulse-admins"
        >
          <KeyRound size={14} className="inline mr-1.5 -mt-0.5" /> Pulse Master Admins
        </button>
      </div>

      {tab === 'service-desk' && <AdminServiceDesk API={API} />}
      {tab === 'pulse-admins' && <AdminPulseAdmins API={API} />}
    </div>
  );
};

export default AdminRoles;
