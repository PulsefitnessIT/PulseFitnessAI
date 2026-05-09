/**
 * LockedStaffPanel — Iter 216bm.
 *
 * Read-only audit table for Master Admin → Security → Locked staff.
 * Lists every user with a non-empty `allowed_site_ids`, joined to
 * their organisation name + the names of their assigned sites.
 *
 * Designed for SOC 2 / compliance review — not for editing. Click a
 * row to deep-link into the org's user editor where the actual
 * permission change can be made.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Lock, RefreshCcw, Star, MapPin, Loader2, AlertCircle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const fmtTs = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
};

const RoleBadge = ({ role, isMaster }) => {
  if (isMaster) return <Badge className="bg-amber-500/15 text-amber-300 border-amber-500/30 text-[10px]">Master</Badge>;
  const cls = {
    owner: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    manager: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    staff: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  }[role] || 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30';
  return <Badge className={`${cls} text-[10px] capitalize`}>{role}</Badge>;
};

const LockedStaffPanel = () => {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const r = await axios.get(`${API}/master-admin/users/locked-sites`, { headers: auth() });
      setRows(r.data?.locked_staff || []);
      setTotal(r.data?.total || 0);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load locked staff');
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-4" data-testid="locked-staff-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Lock size={18} className="text-blue-400" /> Locked staff
          </h2>
          <p className="text-xs text-[var(--color-text-muted)] mt-1 max-w-2xl">
            Every user with a per-staff site restriction. Owners and master admins always see every site regardless and are not listed here.
            Useful for SOC 2 / audit reviews — confirm each restriction matches the role.
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={load} className="text-xs text-[var(--color-text-muted)] hover:text-white" data-testid="locked-staff-refresh">
          <RefreshCcw size={12} className="mr-1.5" /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)] p-6">
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : error ? (
        <Card className="bg-red-500/10 border-red-500/30 p-4 flex items-center gap-2 text-sm text-red-300" data-testid="locked-staff-error">
          <AlertCircle size={14} /> {error}
        </Card>
      ) : total === 0 ? (
        <Card className="bg-[var(--theme-surface)] border-white/10 p-8 text-center" data-testid="locked-staff-empty">
          <Lock size={28} className="mx-auto text-[var(--color-text-muted)] mb-2" />
          <p className="text-sm text-white font-medium">No locked staff yet</p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">
            Per-staff site restrictions will appear here. Operators set them under Pulse Settings → Team.
          </p>
        </Card>
      ) : (
        <Card className="bg-[var(--theme-surface)] border-white/10 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-white/10 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold">
            {total} restricted {total === 1 ? 'user' : 'users'}
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-white/10">
                  <th className="px-4 py-2 font-semibold">User</th>
                  <th className="px-4 py-2 font-semibold">Role</th>
                  <th className="px-4 py-2 font-semibold">Organisation</th>
                  <th className="px-4 py-2 font-semibold">Locked to</th>
                  <th className="px-4 py-2 font-semibold">Last changed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.user_id}
                    className="border-b border-white/5 hover:bg-white/5 transition-colors"
                    data-testid={`locked-staff-row-${row.user_id}`}
                  >
                    <td className="px-4 py-3 align-top">
                      <p className="text-white font-medium">{row.full_name}</p>
                      <p className="text-[11px] text-[var(--color-text-muted)] truncate max-w-[200px]">{row.email}</p>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <RoleBadge role={row.role} isMaster={row.is_master_admin} />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <p className="text-white text-xs truncate max-w-[180px]">{row.organization_name}</p>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex flex-wrap gap-1 max-w-md">
                        {row.sites.map((s) => (
                          <span
                            key={s.id}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-blue-500/10 border border-blue-500/30 text-blue-300"
                            data-testid={`locked-staff-site-${row.user_id}-${s.id}`}
                          >
                            {s.is_head_office
                              ? <Star size={9} className="text-amber-400" />
                              : <MapPin size={9} />}
                            {s.name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top text-[11px] text-[var(--color-text-muted)] whitespace-nowrap">
                      {fmtTs(row.permissions_updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};

export default LockedStaffPanel;
