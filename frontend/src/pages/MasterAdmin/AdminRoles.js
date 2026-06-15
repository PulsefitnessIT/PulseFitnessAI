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
import { Users, Grid3x3, UserCog, KeyRound, FolderArchive, Briefcase } from 'lucide-react';
import AdminServiceDesk from './AdminServiceDesk';
import AdminPulseAdmins from './AdminPulseAdmins';
import PermissionsMatrix from './PermissionsMatrix';
import GlobalUsersPanel from './GlobalUsersPanel';
import PeopleDirectory from './PeopleDirectory';
import OrgPeopleDirectory from './OrgPeopleDirectory';
import UserDetailDrawer from './UserDetailDrawer';

const TABS = [
  { id: 'directory', label: 'Directory', icon: Users },
  { id: 'org-people', label: 'Org People', icon: Briefcase },
  { id: 'matrix', label: 'Permissions matrix', icon: Grid3x3 },
  { id: 'service-desk', label: 'Service Desk team', icon: UserCog },
  { id: 'pulse-admins', label: 'Pulse Master Admins', icon: KeyRound },
  { id: 'legacy-users', label: 'Legacy users panel', icon: FolderArchive },
];

const AdminRoles = ({ API, globalUsersProps, isPulseAdmin }) => {
  const [tab, setTab] = useState('directory');
  const [selectedUser, setSelectedUser] = useState(null);

  // Iter 222 — Pulse Master Admins no longer need the standalone "Pulse
  // Master Admins" provisioning tab or the "Legacy users panel": that
  // information now lives in the Directory + Organisations. They stay
  // available to the full GymAxis platform Master Admin.
  const visibleTabs = TABS.filter(
    (t) => !isPulseAdmin || (t.id !== 'pulse-admins' && t.id !== 'legacy-users'),
  );

  // Iter 216h25 — Listen for cross-section "jump to user" requests
  // fired by the Staff Onboarding wizard's 409 toast. The wizard
  // dispatches `gymaxis:focus-user` with {user_id, email} after
  // pushing ?section=roles&focus_user=... to the URL. We resolve the
  // user from the latest props.users list and open the drawer.
  React.useEffect(() => {
    const resolveAndOpen = (refId) => {
      if (!refId) return;
      const list = globalUsersProps?.users || [];
      const u = list.find((x) => x.id === refId) || list.find((x) => (x.email || '').toLowerCase() === String(refId).toLowerCase());
      if (u) {
        setTab('directory');
        setSelectedUser(u);
        setTimeout(() => {
          const row = document.querySelector(`[data-testid="people-row-${u.id}"]`);
          if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 200);
      }
    };
    // Honour focus_user on mount
    try {
      const refId = new URLSearchParams(window.location.search).get('focus_user');
      if (refId) {
        resolveAndOpen(refId);
        const params = new URLSearchParams(window.location.search);
        params.delete('focus_user');
        const qs = params.toString();
        window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname);
      }
    } catch { /* noop */ }

    const onFocus = (e) => resolveAndOpen(e.detail?.user_id || e.detail?.email);
    window.addEventListener('gymaxis:focus-user', onFocus);
    return () => window.removeEventListener('gymaxis:focus-user', onFocus);
  }, [globalUsersProps?.users]);

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
        {visibleTabs.map(({ id, label, icon: Icon }) => (
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
      {tab === 'org-people' && (
        <OrgPeopleDirectory
          users={globalUsersProps?.users || []}
          onOpenUser={(u) => setSelectedUser(u)}
        />
      )}
      {tab === 'matrix' && <PermissionsMatrix API={API} />}
      {tab === 'service-desk' && <AdminServiceDesk API={API} isPulseAdmin={isPulseAdmin} />}
      {tab === 'pulse-admins' && <AdminPulseAdmins API={API} />}
      {tab === 'legacy-users' && <GlobalUsersPanel {...(globalUsersProps || {})} />}

      {selectedUser && (
        <UserDetailDrawer
          user={selectedUser}
          onClose={() => setSelectedUser(null)}
          onOpenLegacyEdit={isPulseAdmin ? undefined : openLegacyForUser}
          onReload={globalUsersProps?.onReload}
        />
      )}
    </div>
  );
};

export default AdminRoles;
