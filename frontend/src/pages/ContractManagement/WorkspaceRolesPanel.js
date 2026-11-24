import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useCRM } from '@/pages/CRM/CRMApp';

const AUTO = '__auto__';

function RoleRow({ u, roles, onSave, c }) {
  const [val, setVal] = useState(u.explicit_role || AUTO);
  const [busy, setBusy] = useState(false);
  const dirty = val !== (u.explicit_role || AUTO);
  const derivedLabel = (roles.find((r) => r.id === u.derived_role) || {}).label || u.derived_role;
  const save = async () => { setBusy(true); await onSave(u.id, val === AUTO ? null : val); setBusy(false); };
  return (
    <tr className="border-t" style={{ borderColor: c.border }} data-testid={`cm-role-row-${u.id}`}>
      <td className="py-2.5 pr-3">
        <div className="text-sm font-semibold" style={{ color: c.text }}>{u.full_name}</div>
        <div className="text-xs" style={{ color: c.textMuted }}>{u.email}</div>
      </td>
      <td className="py-2.5 pr-3 text-sm" style={{ color: c.text }} data-testid={`cm-role-effective-${u.id}`}>{u.effective_role_label}</td>
      <td className="py-2.5 pr-3">
        <select value={val} onChange={(e) => setVal(e.target.value)} data-testid={`cm-role-select-${u.id}`}
          className="text-sm rounded-lg px-2 py-1.5 border max-w-[240px]" style={{ background: c.inputBg, color: c.text, borderColor: c.border }}>
          <option value={AUTO}>Match platform role ({derivedLabel})</option>
          {roles.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </select>
      </td>
      <td className="py-2.5 text-right">
        <button onClick={save} disabled={!dirty || busy} data-testid={`cm-role-save-${u.id}`}
          className="px-3 py-1.5 rounded-full text-xs font-bold transition-opacity disabled:opacity-40"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--pulse-black)' }}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </td>
    </tr>
  );
}

/** Admin-only: assign each Pulse Fitness staff member's workspace role. */
export default function WorkspaceRolesPanel() {
  const { API, headers, c } = useCRM();
  const [data, setData] = useState(null);
  const [q, setQ] = useState('');
  const load = useCallback(() => {
    axios.get(`${API}/crm/workspace/roles`, { headers: headers() })
      .then((r) => setData(r.data))
      .catch((e) => setData({ users: [], roles: [], error: e.response?.data?.detail || 'Could not load roles' }));
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);
  const save = async (userId, role) => {
    try {
      const r = await axios.put(`${API}/crm/workspace/roles/${userId}`, { role }, { headers: headers() });
      toast.success(`Role updated — now ${r.data.effective_role_label}`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not update role'); }
  };
  if (!data) return <Loader2 className="animate-spin" size={18} style={{ color: 'var(--color-brand-cyan)' }} />;
  if (data.error) return <p className="text-sm text-red-500" data-testid="cm-roles-error">{data.error}</p>;
  const rows = data.users.filter((u) => !q || `${u.full_name} ${u.email}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="cm-roles-panel">
      <p className="text-xs mb-3" style={{ color: c.textMuted }}>
        Coordinators, Finance and Service &amp; Aftersales Managers get Contract Management. Sales Managers keep CRM. Changes are recorded in an audit history.
      </p>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search staff…" data-testid="cm-roles-search"
        className="mb-3 w-full max-w-xs text-sm rounded-lg px-3 py-2 border" style={{ background: c.inputBg, color: c.text, borderColor: c.border }} />
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead><tr className="text-[11px] uppercase tracking-wider" style={{ color: c.textMuted }}>
            <th className="pb-2">Staff member</th><th className="pb-2">Current role</th><th className="pb-2">Assign</th><th />
          </tr></thead>
          <tbody>{rows.map((u) => <RoleRow key={u.id} u={u} roles={data.roles} onSave={save} c={c} />)}</tbody>
        </table>
      </div>
    </div>
  );
}
