/**
 * AdminRoles — Master Admin "People" hub.
 *
 * Iter 216h19 (P3) — leads with the new unified People Directory
 * (Single source of truth). Legacy detail panels live behind their
 * own sub-tabs for one release as a safety net.
 *
 * Tab order:
 *   1. Directory          — NEW: unified list, role chips, filters, search.
 *   2. Permissions matrix — Cross-org attach view (SOC 2).
 *   3. Service Desk team  — Pulse Fitness internal ops staff.
 *   4. Pulse Master Admins — delegated platform admins.
 *   5. Legacy: Users      — pre-P3 GlobalUsersPanel (kept for archive/purge UI).
 *
 * Once operators are happy with the Directory, the "Legacy" tab is
 * removed in a follow-up iter and GlobalUsersPanel's UX moves into
 * the Directory's drawer.
 */
import React, { useState } from 'react';
import { Users, Grid3x3, UserCog, KeyRound, FolderArchive } from 'lucide-react';
import AdminServiceDesk from './AdminServiceDesk';
import AdminPulseAdmins from './AdminPulseAdmins';
import PermissionsMatrix from './PermissionsMatrix';
import GlobalUsersPanel from './GlobalUsersPanel';
import PeopleDirectory from './PeopleDirectory';

const TABS = [
  { id: 'directory', label: 'Directory', icon: Users },
  { id: 'matrix', label: 'Permissions matrix', icon: Grid3x3 },
  { id: 'service-desk', label: 'Service Desk team', icon: UserCog },
  { id: 'pulse-admins', label: 'Pulse Master Admins', icon: KeyRound },
  { id: 'legacy-users', label: 'Legacy users panel', icon: FolderArchive },
];

const AdminRoles = ({ API, globalUsersProps }) => {
  const [tab, setTab] = useState('directory');

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

      {tab === 'directory' && (
        <PeopleDirectory
          users={globalUsersProps?.users || []}
          onOpenUser={(u) => globalUsersProps?.onOpenUser?.(u) ?? globalUsersProps?.onReload?.()}
        />
      )}
      {tab === 'matrix' && <PermissionsMatrix API={API} />}
      {tab === 'service-desk' && <AdminServiceDesk API={API} />}
      {tab === 'pulse-admins' && <AdminPulseAdmins API={API} />}
      {tab === 'legacy-users' && <GlobalUsersPanel {...(globalUsersProps || {})} />}
    </div>
  );
};

export default AdminRoles;
