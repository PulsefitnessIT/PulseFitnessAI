/**
 * Iter 216h19 — People Directory (Phase 3 of the Master Admin
 * redesign blueprint).
 *
 * Single source of truth for every human on the platform. Replaces
 * the 3 legacy panels (AdminUsers + GlobalUsersPanel + AdminPulseAdmins
 * + AdminCRMUsers — 4 surfaces collapsing into 1) with:
 *
 *   • Top stats strip       — totals + breakdown by category.
 *   • Filter pill row       — Pulse Admins · Owners · Staff · CRM contacts · Archived.
 *   • Search box            — name / email / org.
 *   • Brand-aware list      — already brand-filtered by the parent
 *                             MasterAdminPage.loadData (iter 216h18).
 *   • Row "portals" chips   — Service Portal · CRM · Pulse Platform.
 *   • Row drawer            — opens existing UserEditDialog (Profile +
 *                             Sites + Permissions tabs already exist).
 *
 * The backend feed is the existing /api/master-admin/users payload
 * which already returns a deduped, brand-scoped, org-enriched merge
 * of users + crm_users + pulse-admin memberships. No new endpoint
 * needed.
 */
import { useMemo, useState } from 'react';
import { Search, Users, ShieldCheck, Briefcase, UserCog, Archive, AlertTriangle, ChevronRight, Clock, Wrench } from 'lucide-react';
import { useBrandContext } from './BrandContext';

const PILLS = [
  { id: 'all', label: 'Everyone', icon: Users, accent: '#0A0A0A' },
  { id: 'pulse_admins', label: 'Pulse Admins', icon: ShieldCheck, accent: '#0055FF' },
  { id: 'owners', label: 'Owners', icon: UserCog, accent: '#7C3AED' },
  { id: 'staff', label: 'Staff & Managers', icon: Briefcase, accent: '#10B981' },
  { id: 'partner_engineers', label: 'Partner Engineers', icon: Wrench, accent: '#4F46E5' },
  { id: 'crm_only', label: 'CRM contacts', icon: Users, accent: '#F59E0B' },
  { id: 'archived', label: 'Archived', icon: Archive, accent: '#71717A' },
];

const classifyUser = (u) => {
  if (u.is_partner_engineer || u.role === 'engineer_partner' || u.display_role === 'Partner Engineer') return 'partner_engineers';
  if (u.is_pulse_master_admin || u.role === 'pulse_master_admin' || u.user_type === 'pulse_master_admin') return 'pulse_admins';
  if (u.role === 'owner') return 'owners';
  if (u.role === 'manager' || u.role === 'staff') return 'staff';
  if (Array.isArray(u.portals) && u.portals.length === 1 && u.portals[0] === 'crm') return 'crm_only';
  return 'staff';
};

const PortalBadge = ({ portal }) => {
  const styles = {
    service_portal: { bg: 'rgba(16,185,129,0.12)', fg: '#047857', label: 'Service Portal' },
    engineer_app:   { bg: 'rgba(79,70,229,0.12)',  fg: '#4338CA', label: 'Engineer App' },
    crm:            { bg: 'rgba(245,158,11,0.14)', fg: '#B45309', label: 'CRM' },
    pulse_platform: { bg: 'rgba(0,85,255,0.12)',   fg: '#0055FF', label: 'Pulse Platform' },
  }[portal] || { bg: 'rgba(113,113,122,0.12)', fg: '#52525B', label: portal };
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide"
      style={{ background: styles.bg, color: styles.fg }}
      data-testid={`people-portal-badge-${portal}`}
    >
      {styles.label}
    </span>
  );
};

const RoleChip = ({ user }) => {
  const role = (user.display_role || user.role || 'staff').toLowerCase();
  const map = {
    'pulse_master_admin':    { label: 'Pulse Admin', bg: '#EFF6FF', fg: '#1D4ED8' },
    'pulse platform admin':  { label: 'Pulse Admin', bg: '#EFF6FF', fg: '#1D4ED8' },
    'owner':                 { label: 'Owner',       bg: '#FAF5FF', fg: '#7C3AED' },
    'manager':               { label: 'Manager',     bg: '#ECFDF5', fg: '#047857' },
    'staff':                 { label: 'Staff',       bg: '#F4F4F5', fg: '#3F3F46' },
    'partner engineer':      { label: 'Partner Engineer', bg: '#EEF2FF', fg: '#4338CA' },
    'master_admin':          { label: 'Master Admin', bg: '#FFEDD5', fg: '#C2410C' },
  };
  const tone = map[role] || map.staff;
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
      style={{ background: tone.bg, color: tone.fg }}
      data-testid={`people-role-chip-${user.id}`}
    >
      {tone.label}
    </span>
  );
};

const StatTile = ({ label, value, hint, icon: Icon, accent }) => (
  <div className="rounded-lg border bg-white p-4" style={{ borderColor: '#E4E4E7' }} data-testid={`people-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
    <div className="flex items-start justify-between mb-1">
      <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{label}</span>
      {Icon && <Icon size={14} style={{ color: accent || '#71717A' }} />}
    </div>
    <div className="text-2xl font-bold" style={{ color: accent || '#0A0A0A' }}>{value}</div>
    {hint && <div className="text-[10px] text-zinc-500 mt-0.5">{hint}</div>}
  </div>
);

const PeopleDirectory = ({ users = [], onOpenUser }) => {
  const { brandLabel } = useBrandContext();
  const [activePill, setActivePill] = useState('all');
  const [search, setSearch] = useState('');

  // Iter 216h19 — classify once for cheap re-filtering on pill change.
  const classified = useMemo(() => {
    return users.map((u) => ({ ...u, _category: classifyUser(u) }));
  }, [users]);

  const stats = useMemo(() => {
    const c = { total: classified.length, pulse_admins: 0, owners: 0, staff: 0, partner_engineers: 0, crm_only: 0, archived: 0, mismatch: 0, invite_pending: 0 };
    for (const u of classified) {
      if (u.status === 'archived' || u.is_archived) { c.archived += 1; continue; }
      c[u._category] = (c[u._category] || 0) + 1;
      if (u.invited_role && u.invited_role !== u.role) c.mismatch += 1;
      if (u.invite_pending) c.invite_pending += 1;
    }
    return c;
  }, [classified]);

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return classified.filter((u) => {
      // Pill filter
      const isArchived = u.status === 'archived' || u.is_archived;
      if (activePill === 'archived') {
        if (!isArchived) return false;
      } else if (activePill === 'all') {
        if (isArchived) return false; // hide archived from "Everyone"
      } else {
        if (isArchived) return false;
        if (u._category !== activePill) return false;
      }
      // Search filter
      if (s) {
        const hay = `${u.full_name || ''} ${u.email || ''} ${u.organization_name || ''}`.toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
  }, [classified, activePill, search]);

  return (
    <div className="space-y-5" data-testid="people-directory">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 tracking-tight">People directory</h2>
          <p className="text-sm text-zinc-500 mt-0.5">Single source of truth — Pulse Admins, Owners, Staff and CRM contacts in one list. Brand context: <span className="font-semibold text-zinc-700">{brandLabel}</span>.</p>
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3" data-testid="people-stats-strip">
        <StatTile label="Total active" value={stats.total - stats.archived} icon={Users} accent="#0A0A0A" hint={stats.archived ? `${stats.archived} archived` : ''} />
        <StatTile label="Pulse admins" value={stats.pulse_admins} icon={ShieldCheck} accent="#0055FF" />
        <StatTile label="Owners" value={stats.owners} icon={UserCog} accent="#7C3AED" />
        <StatTile label="Staff / Managers" value={stats.staff} icon={Briefcase} accent="#10B981" />
        <StatTile label="Partner Engineers" value={stats.partner_engineers} icon={Wrench} accent="#4F46E5" />
        <StatTile label="CRM only" value={stats.crm_only} icon={Users} accent="#F59E0B" />
        <StatTile label="Role mismatches" value={stats.mismatch} icon={AlertTriangle} accent={stats.mismatch ? '#DC2626' : '#71717A'} hint={stats.mismatch ? 'invited ≠ current' : 'all aligned'} />
        <StatTile label="Invites pending" value={stats.invite_pending} icon={Clock} accent={stats.invite_pending ? '#B45309' : '#71717A'} hint={stats.invite_pending ? '72h links unredeemed' : 'all redeemed'} testId="people-stat-invite-pending" />
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-2 items-center" data-testid="people-pills">
        {PILLS.map((p) => {
          const active = activePill === p.id;
          const count = stats[p.id] !== undefined ? stats[p.id] : (p.id === 'all' ? stats.total - stats.archived : 0);
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => setActivePill(p.id)}
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                borderColor: active ? p.accent : '#E4E4E7',
                background: active ? `${p.accent}14` : 'transparent',
                color: active ? p.accent : '#3F3F46',
                fontWeight: active ? 600 : 500,
              }}
              data-testid={`people-pill-${p.id}`}
            >
              <p.icon size={12} />
              {p.label}
              <span className="text-[10px] font-semibold opacity-70">{count}</span>
            </button>
          );
        })}
        <div className="ml-auto relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email or org..."
            className="pl-7 pr-3 py-1.5 rounded-full border bg-white text-xs"
            style={{ borderColor: '#E4E4E7', width: 280 }}
            data-testid="people-search-input"
          />
        </div>
      </div>

      {/* Results table */}
      <div className="rounded-lg border bg-white overflow-hidden" style={{ borderColor: '#E4E4E7' }} data-testid="people-table">
        {filtered.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm text-zinc-500" data-testid="people-empty">
            No people match the current filter.
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: '#F4F4F5' }}>
            {filtered.map((u) => (
              <button
                key={`${u.id}-${u.organization_id || ''}`}
                type="button"
                onClick={() => onOpenUser?.(u)}
                className="w-full text-left flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 transition-colors"
                data-testid={`people-row-${u.id}`}
              >
                {u.avatar_url ? (
                  <img src={u.avatar_url} alt="" className="w-9 h-9 rounded-full object-cover flex-shrink-0" />
                ) : (
                  <div className="w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-sm font-bold" style={{ background: '#F4F4F5', color: '#52525B' }}>
                    {(u.full_name || u.email || '?').slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-zinc-900 truncate">{u.full_name || u.email}</span>
                    <RoleChip user={u} />
                    {u.invite_pending && (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5"
                        title={`Invite expires ${new Date(u.invite_pending.expires_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}`}
                        data-testid={`people-invite-pending-${u.id}`}
                      >
                        <Clock size={9} />
                        {u.invite_pending.hours_left}h left
                      </span>
                    )}
                    {u.invited_role && u.invited_role !== u.role && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-red-700 bg-red-50 border border-red-200 rounded px-1.5 py-0.5" data-testid={`people-mismatch-${u.id}`}>
                        <AlertTriangle size={10} />
                        invited as {u.invited_role}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5 truncate flex items-center gap-1.5 flex-wrap">
                    <span>{u.email}</span>
                    {u.organization_name && u.organization_name !== 'N/A' && (<>
                      <span className="text-zinc-300">·</span>
                      <span className="font-medium text-zinc-600">{u.organization_name}</span>
                    </>)}
                    {Array.isArray(u.portals) && u.portals.map((p) => <PortalBadge key={p} portal={p} />)}
                    {(u.allowed_site_ids && u.allowed_site_ids.length > 0) && (
                      <span className="text-[10px] text-zinc-500 italic">{u.allowed_site_ids.length} site(s) pinned</span>
                    )}
                  </div>
                </div>
                <ChevronRight size={16} className="text-zinc-400 flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>
      {filtered.length > 0 && (
        <p className="text-[11px] text-zinc-500 text-right" data-testid="people-count">
          Showing {filtered.length} of {stats.total - stats.archived} active {stats.archived ? `· ${stats.archived} archived` : ''}
        </p>
      )}
    </div>
  );
};

export default PeopleDirectory;
