/**
 * AdminRoles — Master Admin "People" hub.
 *
 * Iter 216h20 (P3-followup) — wired the new People Directory row click
 * into the `UserDetailDrawer` so operators can issue a 72 h reset link
 * and jump into the legacy panel for archive/purge without leaving
 * the page. The legacy GlobalUsersPanel stays one tab away as a
 * safety net.
 *
 * Tab order:
 *   1. Directory          — unified list, row → drawer.
 *   2. Permissions matrix — Cross-org attach view (SOC 2).
 *   3. Service Desk team  — Pulse Fitness internal ops staff.
 *   4. Pulse Master Admins — delegated platform admins.
 *   5. Legacy: Users      — pre-P3 GlobalUsersPanel (kept for archive/purge UI).
 */
import React, { useState } from 'react';
import { Users, Grid3x3, UserCog, KeyRound, FolderArchive } from 'lucide-react';
import AdminServiceDesk from './AdminServiceDesk';
import AdminPulseAdmins from './AdminPulseAdmins';
import PermissionsMatrix from './PermissionsMatrix';
import GlobalUsersPanel from './GlobalUsersPanel';
import PeopleDirectory from './PeopleDirectory';
import UserDetailDrawer from './UserDetailDrawer';

const TABS = [
  { id: 'directory', label: 'Directory', icon: Users },
  { id: 'matrix', label: 'Permissions matrix', icon: Grid3x3 },
  { id: 'service-desk', label: 'Service Desk team', icon: UserCog },
  { id: 'pulse-admins', label: 'Pulse Master Admins', icon: KeyRound },
  { id: 'legacy-users', label: 'Legacy users panel', icon: FolderArchive },
];

const AdminRoles = ({ API, globalUsersProps }) => {
  const [tab, setTab] = useState('directory');
  const [selectedUser, setSelectedUser] = useState(null);

  // Iter 216h20 — When the operator clicks "Full edit in legacy panel"
  // inside the drawer, we close the drawer, flip the tab to the legacy
  // GlobalUsersPanel and bubble up a reload so the row is fresh.
  const openLegacyForUser = (u) => {
    setSelectedUser(null);
    setTab('legacy-users');
    if (globalUsersProps?.onReload) globalUsersProps.onReload();
    // Legacy panel already supports ?focus= via its parent — emit
    // an event so it can scroll/expand the row if it wants to.
    try {
      window.dispatchEvent(new CustomEvent('gymaxis:focus-legacy-user', { detail: { user_id: u?.id, email: u?.email } }));
    } catch { /* noop */ }
  };

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
          onOpenUser={(u) => setSelectedUser(u)}
        />
      )}
      {tab === 'matrix' && <PermissionsMatrix API={API} />}
      {tab === 'service-desk' && <AdminServiceDesk API={API} />}
      {tab === 'pulse-admins' && <AdminPulseAdmins API={API} />}
      {tab === 'legacy-users' && <GlobalUsersPanel {...(globalUsersProps || {})} />}

      {selectedUser && (
        <UserDetailDrawer
          user={selectedUser}
          onClose={() => setSelectedUser(null)}
          onOpenLegacyEdit={openLegacyForUser}
          onReload={globalUsersProps?.onReload}
        />
      )}
    </div>
  );
};

export default AdminRoles;
