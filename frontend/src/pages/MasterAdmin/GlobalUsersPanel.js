/**
 * GlobalUsersPanel — Master Admin → Roles → Users (Iter 216h9).
 *
 * Cross-org user directory with full lifecycle actions:
 *   • Impersonate · Reset password · Edit details
 *   • Disable / Enable (revocable; preserves history)
 *   • Archive / Unarchive (soft-removal; keeps audit trail)
 *   • Hard-delete (gated by archive; one user row at a time)
 *   • Remove everywhere (purge-by-email; wipes all matching rows
 *     across the platform — for genuine leavers)
 *
 * Reuses the existing hook chain (`useMasterAdminActions`) and the
 * `HardDeleteUserDialog` from `AdminOrganizations.js`, so the data
 * model + audit log stay consistent.
 */
import { useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Search, Crown, User as UserIcon, Eye, KeyRound, Ban, Archive,
  Trash2, UserX, Filter, RefreshCw,
} from 'lucide-react';
import { HardDeleteUserDialog } from './AdminOrganizations';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'disabled', label: 'Disabled' },
  { id: 'archived', label: 'Archived' },
];

const GlobalUsersPanel = ({
  users = [], loading = false, onReload,
  onImpersonate, onResetPassword, onDisableUser,
  onArchiveUser, onHardDeleteUser,
}) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [hardDeleteTarget, setHardDeleteTarget] = useState(null);
  const [purgeBusy, setPurgeBusy] = useState(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) => {
      // Status filter — `archived` takes precedence over `disabled`.
      if (statusFilter === 'archived' && !u.archived) return false;
      if (statusFilter === 'disabled' && (!u.disabled || u.archived)) return false;
      if (statusFilter === 'active' && (u.disabled || u.archived)) return false;
      if (!q) return true;
      return (
        (u.full_name || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q) ||
        (u.organization_name || '').toLowerCase().includes(q) ||
        (u.role || '').toLowerCase().includes(q)
      );
    });
  }, [users, search, statusFilter]);

  const removeEverywhere = async (u) => {
    const email = (u.email || '').trim();
    if (!email) return;
    const sure = window.confirm(
      `REMOVE ${u.full_name || email} FROM EVERY ORG?\n\n`
      + `This permanently deletes every user row matching "${email}" `
      + `(and variants on the same domain) plus their invites, signup `
      + `drafts, journey jobs, and tour bookings.\n\n`
      + `Use this when someone has left the company entirely.\n\n`
      + `This cannot be undone.`
    );
    if (!sure) return;
    setPurgeBusy(u.id);
    try {
      const token = localStorage.getItem('token');
      const r = await axios.delete(
        `${API}/master-admin/purge-user-by-email`,
        { params: { email }, headers: { Authorization: `Bearer ${token}` } },
      );
      const d = r.data?.deleted || {};
      const total = Object.values(d).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0);
      if (total === 0) {
        // The email regex didn't match — the row probably exists with a
        // slightly different email format. Fall back to a hard-delete by
        // id, which is what the per-row Permanent-Delete button does.
        // Auto-archive first if needed since hard-delete is archive-gated.
        let fallbackDeleted = 0;
        try {
          if (!u.archived) {
            await onArchiveUser?.(u.id, true);
          }
          await onHardDeleteUser?.(u.id, email);
          fallbackDeleted = 1;
        } catch {
          // surface the original 0-match warning below
        }
        if (fallbackDeleted > 0) {
          toast.success(
            `${u.full_name || email} removed (fallback path used — email regex matched 0 rows but row deleted by id).`,
            { duration: 7000 },
          );
        } else {
          toast.warning(
            `No records matched "${email}" — the row's stored email may have hidden characters or a different format. Try Archive then Permanent Delete on the row.`,
            { duration: 9000 },
          );
        }
      } else {
        toast.success(
          `${u.full_name || email} removed everywhere — ${total} record(s) wiped across ${d.users || 0} user row(s)${d.crm_users ? ` and ${d.crm_users} CRM row(s)` : ''}.`,
          { duration: 7000 },
        );
      }
      onReload?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Couldn't remove user everywhere");
    }
    setPurgeBusy(null);
  };

  const total = users.length;
  const counts = useMemo(() => ({
    active: users.filter((u) => !u.disabled && !u.archived).length,
    disabled: users.filter((u) => u.disabled && !u.archived).length,
    archived: users.filter((u) => u.archived).length,
  }), [users]);

  return (
    <div className="space-y-4" data-testid="global-users-panel">
      {/* Toolbar */}
      <div className="flex flex-col md:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={14} />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, email, organisation, or role…"
            className="pl-9 h-9 text-sm"
            data-testid="global-users-search"
          />
        </div>
        <div className="flex items-center gap-1 bg-zinc-100 rounded-full p-1" data-testid="global-users-status-switch">
          {STATUS_FILTERS.map((s) => {
            const active = statusFilter === s.id;
            const count = s.id === 'all' ? total : counts[s.id];
            return (
              <button
                key={s.id}
                onClick={() => setStatusFilter(s.id)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  active ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500 hover:text-zinc-700'
                }`}
                data-testid={`global-users-filter-${s.id}`}
              >
                {s.label} <span className="ml-0.5 text-zinc-400">{count}</span>
              </button>
            );
          })}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onReload}
          disabled={loading}
          className="text-xs h-9"
          data-testid="global-users-refresh"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      {/* Leaver-removal hint */}
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-600 flex items-start gap-2" data-testid="global-users-leaver-hint">
        <Filter size={12} className="mt-0.5 text-zinc-400 shrink-0" />
        <p className="leading-relaxed">
          <strong className="text-zinc-800">Leaver workflow:</strong> Archive first (preserves history),
          then Permanent Delete to remove the single row. Use <strong>Remove everywhere</strong>
          when someone has left the company and you want them wiped from every org +
          invite / draft / booking in one click.
        </p>
      </div>

      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[840px]" data-testid="global-users-table">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="text-left p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">User</th>
                <th className="text-left p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">Organisation</th>
                <th className="text-left p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">Role</th>
                <th className="text-left p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">Status</th>
                <th className="text-left p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">Joined</th>
                <th className="text-right p-3 text-[10px] font-bold uppercase tracking-wider text-zinc-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => {
                const protectedRow = u.is_master_admin || (u.email || '').toLowerCase() === 'admin@pulsefitness.ai';
                return (
                  <tr key={u.id} className="border-b border-zinc-50 hover:bg-zinc-50 transition-colors" data-testid={`global-user-row-${u.id}`}>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-zinc-100 flex items-center justify-center shrink-0">
                          {u.is_master_admin ? <Crown size={13} className="text-amber-500" /> : <UserIcon size={13} className="text-zinc-500" />}
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-zinc-900 truncate" data-testid={`global-user-name-${u.id}`}>{u.full_name || 'Unnamed'}</p>
                          <p className="text-zinc-400 text-xs truncate">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="p-3 text-zinc-600 text-xs truncate max-w-[160px]" title={u.organization_name}>{u.organization_name || '—'}</td>
                    <td className="p-3">
                      <Badge className={u.role === 'owner' ? 'bg-amber-50 text-amber-700 border-amber-200 text-[10px]'
                        : u.role === 'manager' ? 'bg-blue-50 text-blue-700 border-blue-200 text-[10px]'
                        : 'bg-zinc-100 text-zinc-600 text-[10px]'}>
                        {u.display_role || u.role || 'member'}
                      </Badge>
                    </td>
                    <td className="p-3">
                      {u.archived ? (
                        <Badge className="bg-zinc-200 text-zinc-600 border-zinc-300 text-[10px]">Archived</Badge>
                      ) : u.disabled ? (
                        <Badge className="bg-red-50 text-red-600 border-red-200 text-[10px]">Disabled</Badge>
                      ) : (
                        <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">Active</Badge>
                      )}
                    </td>
                    <td className="p-3 text-zinc-400 text-xs">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                    <td className="p-3 text-right">
                      <div className="flex items-center justify-end gap-0.5 flex-wrap">
                        {onImpersonate && (
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-blue-600" onClick={() => onImpersonate(u.id)} title="Impersonate" data-testid={`global-user-impersonate-${u.id}`}>
                            <Eye size={13} />
                          </Button>
                        )}
                        {onResetPassword && (
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-amber-600" onClick={() => onResetPassword(u.id)} title="Reset password" data-testid={`global-user-reset-pwd-${u.id}`}>
                            <KeyRound size={13} />
                          </Button>
                        )}
                        {onDisableUser && !protectedRow && (
                          <Button size="sm" variant="ghost" className={`h-7 px-2 text-[11px] ${u.disabled ? 'text-emerald-600' : 'text-zinc-500 hover:text-red-600'}`} onClick={() => onDisableUser(u.id, !u.disabled)} title={u.disabled ? 'Enable' : 'Disable'} data-testid={`global-user-disable-${u.id}`}>
                            <Ban size={11} className="mr-0.5" /> {u.disabled ? 'Enable' : 'Disable'}
                          </Button>
                        )}
                        {onArchiveUser && !protectedRow && (
                          <Button size="sm" variant="ghost" className={`h-7 px-2 text-[11px] ${u.archived ? 'text-blue-600' : 'text-amber-600'}`} onClick={() => onArchiveUser(u.id, !u.archived)} title={u.archived ? 'Unarchive' : 'Archive (preserves history)'} data-testid={`global-user-archive-${u.id}`}>
                            <Archive size={11} className="mr-0.5" /> {u.archived ? 'Unarchive' : 'Archive'}
                          </Button>
                        )}
                        {onHardDeleteUser && u.archived && !protectedRow && (
                          <Button
                            size="sm" variant="ghost"
                            className="h-7 px-2 text-[11px] text-red-600 hover:bg-red-50"
                            onClick={() => setHardDeleteTarget(u)}
                            title="Permanently delete this single row"
                            data-testid={`global-user-hard-delete-${u.id}`}
                          >
                            <Trash2 size={11} className="mr-0.5" /> Delete
                          </Button>
                        )}
                        {!protectedRow && (
                          <Button
                            size="sm" variant="ghost"
                            className="h-7 px-2 text-[11px] text-red-700 hover:bg-red-600 hover:text-white border border-transparent hover:border-red-700"
                            onClick={() => removeEverywhere(u)}
                            disabled={purgeBusy === u.id}
                            title="Wipe this email from every org + invite / draft / booking. For leavers."
                            data-testid={`global-user-remove-everywhere-${u.id}`}
                          >
                            <UserX size={11} className="mr-0.5" /> Remove everywhere
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!loading && filtered.length === 0 && (
          <p className="text-center text-zinc-400 py-12 text-sm" data-testid="global-users-empty">No users match this filter.</p>
        )}
        {loading && (
          <p className="text-center text-zinc-400 py-12 text-sm">Loading…</p>
        )}
      </Card>

      <HardDeleteUserDialog
        open={!!hardDeleteTarget}
        user={hardDeleteTarget || {}}
        onClose={() => setHardDeleteTarget(null)}
        onConfirm={async (userId, confirmEmail) => {
          const ok = await onHardDeleteUser?.(userId, confirmEmail);
          if (ok) setHardDeleteTarget(null);
        }}
      />
    </div>
  );
};

export default GlobalUsersPanel;
