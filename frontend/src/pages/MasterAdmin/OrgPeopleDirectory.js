/**
 * Org People directory (Master Admin → People → Org People).
 *
 * One row per person showing JOB TITLE + which MODULES they can access
 * (Operations · CRM · Memberships · Marketing) at a glance — the entitlement
 * view that complements the contact-centric "Directory" tab.
 *
 * Feed: the existing /api/master-admin/users payload, now enriched with
 * `job_title` and `module_access` (see master_admin_users._enrich_with_module_access).
 */
import { useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Search, Check, Minus, Download, Briefcase, ChevronRight, Pencil, Loader2 } from 'lucide-react';

const MODULES = [
  { key: 'operations', label: 'Operations', color: '#0055FF' },
  { key: 'crm', label: 'CRM', color: '#B45309' },
  { key: 'memberships', label: 'Memberships', color: '#047857' },
  { key: 'marketing', label: 'Marketing', color: '#7C3AED' },
];

const roleLabel = (u) => {
  const r = (u.display_role || u.role || 'staff').toLowerCase();
  const map = {
    pulse_master_admin: 'Pulse Admin', 'pulse platform admin': 'Pulse Admin',
    master_admin: 'Master Admin', owner: 'Owner', manager: 'Manager', staff: 'Staff',
    'partner engineer': 'Partner Engineer', engineer_partner: 'Partner Engineer',
  };
  return map[r] || (u.display_role || u.role || 'Staff');
};

const ModuleCell = ({ on, color }) => (
  <td className="px-2 py-3 text-center">
    {on
      ? <Check size={15} className="inline" style={{ color }} aria-label="Has access" />
      : <Minus size={14} className="inline text-zinc-300" aria-label="No access" />}
  </td>
);

const OrgPeopleDirectory = ({ users = [], API, onReload, onOpenUser }) => {
  const [search, setSearch] = useState('');
  const [moduleFilter, setModuleFilter] = useState('');
  const [edits, setEdits] = useState({});       // userId → saved title (optimistic)
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState('');
  const [savingId, setSavingId] = useState(null);

  const titleOf = (u) => (edits[u.id] !== undefined ? edits[u.id] : (u.job_title || ''));

  const startEdit = (e, u) => {
    e.stopPropagation();
    setEditingId(u.id);
    setDraft(titleOf(u));
  };
  const cancelEdit = () => { setEditingId(null); setDraft(''); };
  const saveTitle = async (u) => {
    const next = draft.trim();
    if (next === (titleOf(u) || '')) { cancelEdit(); return; }
    setSavingId(u.id);
    try {
      await axios.put(`${API}/master-admin/users/${u.id}/edit`, { job_title: next }, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      setEdits((m) => ({ ...m, [u.id]: next }));
      toast.success('Job title updated');
      onReload?.();
      cancelEdit();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not update job title');
    } finally { setSavingId(null); }
  };

  const active = useMemo(
    () => users.filter((u) => !(u.status === 'archived' || u.is_archived)),
    [users],
  );

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return active.filter((u) => {
      if (moduleFilter && !(u.module_access || {})[moduleFilter]) return false;
      if (s) {
        const hay = `${u.full_name || ''} ${u.email || ''} ${u.organization_name || ''} ${u.job_title || ''}`.toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
  }, [active, search, moduleFilter]);

  const exportCsv = () => {
    const head = ['Name', 'Email', 'Job title', 'Organisation', 'Role', ...MODULES.map((m) => m.label)];
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = filtered.map((u) => [
      u.full_name || '', u.email || '', titleOf(u), u.organization_name || '', roleLabel(u),
      ...MODULES.map((m) => ((u.module_access || {})[m.key] ? 'Yes' : 'No')),
    ].map(esc).join(','));
    const csv = [head.map(esc).join(','), ...lines].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'org-people.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4" data-testid="org-people-directory">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 tracking-tight flex items-center gap-2">
            <Briefcase size={18} className="text-[var(--color-brand-blue)]" /> Org People
          </h2>
          <p className="text-sm text-zinc-500 mt-0.5">Every person with their job title and the modules they can access — one row each.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, job title, org…"
              className="pl-7 pr-3 py-1.5 rounded-full border bg-white text-xs"
              style={{ borderColor: '#E4E4E7', width: 240 }}
              data-testid="org-people-search"
            />
          </div>
          <select
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="px-3 py-1.5 rounded-full border bg-white text-xs font-medium text-zinc-700"
            style={{ borderColor: '#E4E4E7' }}
            data-testid="org-people-module-filter"
          >
            <option value="">All modules</option>
            {MODULES.map((m) => <option key={m.key} value={m.key}>Has {m.label}</option>)}
          </select>
          <button
            type="button"
            onClick={exportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border bg-white text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
            style={{ borderColor: '#E4E4E7' }}
            data-testid="org-people-export-csv"
          >
            <Download size={13} /> CSV
          </button>
        </div>
      </div>

      <div className="rounded-lg border bg-white overflow-x-auto" style={{ borderColor: '#E4E4E7' }} data-testid="org-people-table">
        {filtered.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm text-zinc-500" data-testid="org-people-empty">No people match the current filter.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: '#E4E4E7' }}>
                <th className="text-left px-4 py-2.5 font-semibold text-zinc-600 min-w-[220px]">Person</th>
                <th className="text-left px-3 py-2.5 font-semibold text-zinc-600 min-w-[150px]">Job title</th>
                <th className="text-left px-3 py-2.5 font-semibold text-zinc-600 min-w-[140px]">Organisation</th>
                <th className="text-left px-3 py-2.5 font-semibold text-zinc-600">Role</th>
                {MODULES.map((m) => (
                  <th key={m.key} className="px-2 py-2.5 text-center font-medium text-zinc-600 min-w-[92px]" data-testid={`org-people-col-${m.key}`}>
                    {m.label}
                  </th>
                ))}
                <th className="px-2" />
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: '#F4F4F5' }}>
              {filtered.map((u) => (
                <tr
                  key={`${u.id}-${u.organization_id || ''}`}
                  onClick={() => onOpenUser?.(u)}
                  className="hover:bg-zinc-50 transition-colors cursor-pointer"
                  data-testid={`org-people-row-${u.id}`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold" style={{ background: '#F4F4F5', color: '#52525B' }}>
                        {(u.full_name || u.email || '?').slice(0, 1).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold text-zinc-900 truncate">{u.full_name || u.email}</div>
                        <div className="text-[11px] text-zinc-500 truncate">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                    {editingId === u.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          autoFocus
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') saveTitle(u); if (e.key === 'Escape') cancelEdit(); }}
                          onBlur={() => saveTitle(u)}
                          placeholder="Job title"
                          className="px-2 py-1 rounded border text-xs w-36"
                          style={{ borderColor: '#CBD5E1' }}
                          data-testid={`org-people-title-input-${u.id}`}
                        />
                        {savingId === u.id && <Loader2 size={13} className="animate-spin text-zinc-400" />}
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={(e) => startEdit(e, u)}
                        className="group inline-flex items-center gap-1.5 text-zinc-700 hover:text-[var(--color-brand-blue)]"
                        title="Edit job title"
                        data-testid={`org-people-title-${u.id}`}
                      >
                        {titleOf(u) || <span className="text-zinc-400 italic">Add title</span>}
                        <Pencil size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-3 text-zinc-600 truncate">{u.organization_name && u.organization_name !== 'N/A' ? u.organization_name : <span className="text-zinc-400">—</span>}</td>
                  <td className="px-3 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-zinc-100 text-zinc-600">{roleLabel(u)}</span>
                  </td>
                  {MODULES.map((m) => (
                    <ModuleCell key={m.key} on={!!(u.module_access || {})[m.key]} color={m.color} />
                  ))}
                  <td className="px-2 text-right"><ChevronRight size={15} className="text-zinc-400 inline" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-zinc-500">
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1"><Check size={12} className="text-emerald-500" /> Has access</span>
          <span className="flex items-center gap-1"><Minus size={12} className="text-zinc-300" /> No access</span>
        </span>
        <span data-testid="org-people-count">Showing {filtered.length} of {active.length} people</span>
      </div>
    </div>
  );
};

export default OrgPeopleDirectory;
