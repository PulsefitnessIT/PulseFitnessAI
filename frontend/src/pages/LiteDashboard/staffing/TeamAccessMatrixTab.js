/**
 * TeamAccessMatrixTab — "Who can see what".
 *
 * Read-only, org-wide matrix of every login user and their EFFECTIVE module
 * access (Operations, Memberships, Marketing, CRM, Service Desk, Inventory,
 * Engineer App, Staff Portal). Lets a manager spot a mis-set permission at a
 * glance — before anyone hits a 403. Backed by GET /staffing/team/module-matrix.
 * To change access, open the person in the HR tab.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, Check, Minus, Search, RefreshCw, ShieldCheck } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TeamAccessMatrixTab({ headers }) {
  const [data, setData] = useState(null);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/staffing/team/module-matrix`, { headers })
      .then((r) => setData(r.data))
      .catch(() => setData({ columns: [], rows: [], count: 0 }))
      .finally(() => setLoading(false));
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    const list = data?.rows || [];
    const term = q.trim().toLowerCase();
    if (!term) return list;
    return list.filter((r) =>
      (r.name || '').toLowerCase().includes(term)
      || (r.email || '').toLowerCase().includes(term)
      || (r.role || '').toLowerCase().includes(term));
  }, [data, q]);

  if (!data) {
    return <div className="p-6"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} /></div>;
  }
  const columns = data.columns || [];

  const Cell = ({ on, privileged }) => (
    <td className="px-2 py-2.5 text-center">
      {on ? (
        <span
          className="inline-flex items-center justify-center w-6 h-6 rounded-full"
          style={{ background: privileged ? '#6366f11f' : '#10b9811f', color: privileged ? '#6366f1' : '#059669' }}
          title={privileged ? 'Granted (admin — sees everything)' : 'Granted'}
        >
          <Check size={14} strokeWidth={3} />
        </span>
      ) : (
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full"
          style={{ background: 'var(--theme-bg)', color: 'var(--theme-text-muted)' }} title="No access">
          <Minus size={14} />
        </span>
      )}
    </td>
  );

  return (
    <div className="space-y-4" data-testid="team-access-matrix-tab">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
            Everyone's effective module access. To change it, open the person in <span style={{ fontWeight: 600 }}>HR</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, email, role…"
              data-testid="team-matrix-search"
              className="pl-9 pr-3 py-2 rounded-lg text-sm w-full sm:w-64"
              style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
            />
          </div>
          <button
            onClick={load}
            data-testid="team-matrix-refresh"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium"
            style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="rounded-xl overflow-hidden overflow-x-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <table className="w-full text-sm" data-testid="team-matrix-table">
          <thead>
            <tr style={{ background: 'var(--theme-bg)', borderBottom: '1px solid var(--theme-border)' }}>
              <th className="px-4 py-3 text-left font-semibold sticky left-0 z-10"
                style={{ color: 'var(--theme-text)', background: 'var(--theme-bg)', minWidth: 200 }}>
                Person
              </th>
              {columns.map((c) => (
                <th key={c.key} className="px-2 py-3 text-center font-semibold whitespace-nowrap"
                  style={{ color: 'var(--theme-text-muted)', minWidth: 92 }}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.user_id} data-testid={`team-matrix-row-${r.user_id}`}
                style={{ borderBottom: '1px solid var(--theme-border)' }}>
                <td className="px-4 py-2.5 sticky left-0 z-10" style={{ background: 'var(--theme-surface)' }}>
                  <div className="flex items-center gap-2">
                    <div className="min-w-0">
                      <div className="font-medium truncate flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
                        {r.name}
                        {r.is_privileged && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full"
                            style={{ background: '#6366f11f', color: '#6366f1' }} title="Sees everything">
                            <ShieldCheck size={10} /> {r.privilege_label || 'Admin'}
                          </span>
                        )}
                      </div>
                      <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>
                        {r.email}{r.role && r.role !== '—' ? ` · ${r.role}` : ''}
                      </div>
                    </div>
                  </div>
                </td>
                {columns.map((c) => (
                  <Cell key={c.key} on={!!r.modules?.[c.key]} privileged={r.is_privileged} />
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={columns.length + 1} className="px-4 py-8 text-center text-sm"
                style={{ color: 'var(--theme-text-muted)' }}>No people match your search.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full" style={{ background: '#10b9811f', color: '#059669' }}><Check size={11} strokeWidth={3} /></span>
          Granted
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full" style={{ background: '#6366f11f', color: '#6366f1' }}><Check size={11} strokeWidth={3} /></span>
          Granted via admin/owner (sees everything)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text-muted)' }}><Minus size={11} /></span>
          No access
        </span>
        <span>· {data.count} {data.count === 1 ? 'person' : 'people'}</span>
      </div>
    </div>
  );
}
