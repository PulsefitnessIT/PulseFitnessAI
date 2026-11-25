import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { ShieldCheck, History, Loader2, X } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/staffing/system-access`;
const STATUS = {
  ok: ['Configured correctly', 'var(--color-success)'], needs_review: ['Needs review', 'var(--color-warning)'],
  no_login: ['No login', 'var(--theme-text-muted)'], inactive: ['Login inactive', 'var(--theme-text-muted)'],
  not_authorised: ['Access not authorised', 'var(--theme-text-muted)'],
};
const hdr = (h) => (typeof h === 'function' ? h() : h);
const title = (v) => (v ? String(v).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—');
const sel = 'h-8 px-2 rounded-md text-xs border';
const selStyle = { background: 'var(--theme-input-bg)', borderColor: 'var(--theme-input-border)', color: 'var(--theme-text)' };

function Chip({ status }) {
  const [label, color] = STATUS[status] || [status, 'var(--theme-text-muted)'];
  return <span className="text-[11px] font-semibold whitespace-nowrap" style={{ color }} data-testid={`sa-status-${status}`}>● {label}</span>;
}

function AuditDrawer({ row, headers, onClose }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    axios.get(`${API}/${row.user_id}/audit`, { headers: hdr(headers) }).then((r) => setItems(r.data.history)).catch(() => setItems([]));
  }, [row.user_id, headers]);
  return (
    <div className="rounded-lg border p-3 mt-2 text-xs" style={{ borderColor: 'var(--theme-border)' }} data-testid="sa-audit">
      <div className="flex justify-between font-semibold mb-2"><span>Access history — {row.name}</span>
        <button type="button" onClick={onClose} aria-label="Close history" data-testid="sa-audit-close"><X size={14} /></button></div>
      {!items ? <Loader2 size={14} className="animate-spin" /> : !items.length ? <div style={{ color: 'var(--theme-text-muted)' }}>No access changes recorded.</div> : (
        <ul className="space-y-1">{items.map((h, i) => (
          <li key={`${h.at}-${i}`}>{new Date(h.at).toLocaleString('en-GB')} · {title(h.kind || 'contracts_role')}: {JSON.stringify(h.from ?? h.from_role ?? null)} → {JSON.stringify(h.to ?? h.to_role ?? null)} · by {h.by || h.actor}</li>
        ))}</ul>
      )}
    </div>
  );
}

function Row({ r, meta, headers, onSaved, onAudit }) {
  const [busy, setBusy] = useState(false);
  const save = async (patch, label) => {
    if (!window.confirm(`${label} for ${r.name}? This is recorded in their access history.`)) return;
    setBusy(true);
    try { await axios.put(`${API}/${r.user_id}`, patch, { headers: hdr(headers) }); notify.success('Access updated — takes effect on their next page load'); onSaved(); } catch (e) { notify.error(e?.response?.data?.detail || 'Could not update access'); } finally { setBusy(false); }
  };
  const can = !!r.user_id && !busy;
  return (
    <tr className="border-t align-top" style={{ borderColor: 'var(--theme-border)' }} data-testid={`sa-row-${r.user_id || r.staff_id}`}>
      <td className="p-2"><div className="font-semibold">{r.name}</div><div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{title(r.job_title)} · {r.department || 'No department'}</div></td>
      <td className="p-2"><Chip status={r.status} />{r.issues.map((i) => <div key={i} className="text-[11px] mt-0.5" style={{ color: 'var(--color-warning)' }}>{i}</div>)}</td>
      <td className="p-2">
        <select className={sel} style={selStyle} disabled={!can} value={r.contracts_role_source === 'explicit' ? r.contracts_role : ''} data-testid="sa-contracts-role"
          onChange={(e) => save({ contracts_role: e.target.value || null }, e.target.value ? `Set Contracts role to ${meta.contracts_roles.find((x) => x.id === e.target.value)?.label}` : 'Remove the explicit Contracts role')}>
          <option value="">{r.contracts_role_source === 'explicit' ? 'Remove role' : `Not assigned (${r.contracts_role_label})`}</option>
          {meta.contracts_roles.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
        {r.contracts_access && (
          <div className="flex flex-wrap gap-2 mt-1">{meta.extra_permissions.map((x) => (
            <label key={x.id} className="text-[11px] inline-flex items-center gap-1">
              <input type="checkbox" disabled={!can} checked={r.extra_permissions.includes(x.id)} data-testid={`sa-extra-${x.id}`}
                onChange={(e) => save({ extra_permissions: e.target.checked ? [...r.extra_permissions, x.id] : r.extra_permissions.filter((p) => p !== x.id) }, `${e.target.checked ? 'Grant' : 'Remove'} "${x.label}"`)} />{x.label}
            </label>))}</div>
        )}
      </td>
      <td className="p-2">
        <label className="text-xs inline-flex items-center gap-1.5"><input type="checkbox" disabled={!can} checked={r.mod_operations_access} data-testid="sa-mod-ops"
          onChange={(e) => save({ mod_operations: e.target.checked }, `${e.target.checked ? 'Grant' : 'Remove'} MOD Operations access`)} /> MOD Operations</label>
        {r.mod_operations_access && (
          <select className={`${sel} mt-1 block`} style={selStyle} disabled={!can} value={r.mod_quote_role} data-testid="sa-mod-role"
            onChange={(e) => save({ mod_quote_role: e.target.value }, `Set MOD quotation permission to ${meta.mod_roles.find((x) => x.id === e.target.value)?.label}`)}>
            {meta.mod_roles.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        )}
      </td>
      <td className="p-2">{r.user_id && <button type="button" className="text-xs inline-flex items-center gap-1" onClick={() => onAudit(r)} data-testid="sa-history"><History size={12} /> History</button>}</td>
    </tr>
  );
}

export function SystemAccessPanel({ headers, onClose }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [dept, setDept] = useState('');
  const [status, setStatus] = useState('');
  const [role, setRole] = useState('');
  const [audit, setAudit] = useState(null);
  const load = useCallback(() => axios.get(API, { headers: hdr(headers) }).then((r) => setData(r.data)).catch((e) => setErr(e?.response?.data?.detail || 'Could not load System Access')), [headers]);
  useEffect(() => { load(); }, [load]);
  const rows = useMemo(() => (data?.rows || []).filter((r) => (!dept || r.department === dept) && (!status || r.status === status) && (!role || r.contracts_role === role)), [data, dept, status, role]);
  const depts = useMemo(() => [...new Set((data?.rows || []).map((r) => r.department).filter(Boolean))].sort(), [data]);
  const s = data?.summary || {};
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="system-access-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-bold"><ShieldCheck size={16} /> System Access</div>
        <button type="button" onClick={onClose} className="text-xs" data-testid="system-access-close">Close</button>
      </div>
      <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>Who can use Contract Management and MOD Operations. Job titles never grant access — every role here is an explicit, audited assignment.</p>
      {err ? <div className="text-sm mt-3" style={{ color: 'var(--color-danger)' }} data-testid="system-access-error">{err}</div> : !data ? <Loader2 size={16} className="animate-spin mt-3" /> : (
        <>
          <div className="flex flex-wrap gap-3 text-xs mt-3" data-testid="system-access-summary">
            <span>{s.total} people</span><span>{s.linked} linked to a login</span><span>{s.contracts_roles} with Contracts access</span>
            <span>{s.mod_operations} with MOD Operations</span><span style={{ color: 'var(--color-warning)' }}>{s.needs_review} need review</span>
            <span>{s.no_login} without a login</span><span>{s.duplicates} duplicate identities</span>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <select className={sel} style={selStyle} value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Filter by department" data-testid="sa-filter-dept">
              <option value="">All departments</option>{depts.map((d) => <option key={d}>{d}</option>)}</select>
            <select className={sel} style={selStyle} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status" data-testid="sa-filter-status">
              <option value="">All statuses</option>{Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select>
            <select className={sel} style={selStyle} value={role} onChange={(e) => setRole(e.target.value)} aria-label="Filter by Contracts role" data-testid="sa-filter-role">
              <option value="">All Contracts roles</option><option value="none">No workspace role</option>{data.contracts_roles.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select>
          </div>
          {audit && <AuditDrawer row={audit} headers={headers} onClose={() => setAudit(null)} />}
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase" style={{ color: 'var(--theme-text-muted)' }}>
                <th className="p-2">Person</th><th className="p-2">Status</th><th className="p-2">Contracts workspace</th><th className="p-2">MOD Operations</th><th className="p-2" /></tr></thead>
              <tbody>{rows.map((r) => <Row key={r.user_id || r.staff_id} r={r} meta={data} headers={headers} onSaved={load} onAudit={setAudit} />)}</tbody>
            </table>
            {!rows.length && <div className="text-sm p-4 text-center" style={{ color: 'var(--theme-text-muted)' }}>No staff match these filters.</div>}
          </div>
        </>
      )}
    </div>
  );
}
