import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;

export const CAT = {
  new_customer_organisation: { label: 'New customer (LITE)', tone: 'emerald' },
  existing_update_proposed: { label: 'Existing — update proposed', tone: 'sky' },
  existing_unchanged: { label: 'Existing — unchanged', tone: 'zinc' },
  branch_merged_into_head_office: { label: 'Branch → head office', tone: 'sky' },
  new_business_contact: { label: 'New business contact', tone: 'emerald' },
  existing_contact_update_proposed: { label: 'Existing contact — update', tone: 'sky' },
  existing_contact_unchanged: { label: 'Existing contact — unchanged', tone: 'zinc' },
  unresolved_contact: { label: 'Awaiting Sage account', tone: 'amber' },
  ambiguous_contact: { label: 'Ambiguous contact', tone: 'red' },
  ambiguous_organisation: { label: 'Ambiguous organisation', tone: 'red' },
  conflicting_duplicate: { label: 'Conflicting duplicate', tone: 'red' },
  circular_relationship: { label: 'Circular head office', tone: 'red' },
  invalid_relationship: { label: 'Invalid head office', tone: 'red' },
  duplicate_source_row: { label: 'Duplicate source row', tone: 'zinc' },
  invalid: { label: 'Invalid record', tone: 'red' },
  hidden_sage_account: { label: 'Hidden Sage account', tone: 'amber' },
  uncertain_range: { label: 'Confirm data range', tone: 'amber' },
  excluded_suspected_example: { label: 'Looks like Sage sample', tone: 'amber' },
  excluded_example: { label: 'Template example', tone: 'zinc' },
  template_metadata: { label: 'Template metadata', tone: 'zinc' },
  excluded_by_admin: { label: 'Excluded by admin', tone: 'zinc' },
};

const TONE = { emerald: 'bg-emerald-100 text-emerald-800', sky: 'bg-sky-100 text-sky-800', amber: 'bg-amber-100 text-amber-800',
  red: 'bg-red-100 text-red-800', zinc: 'bg-zinc-100 text-zinc-700' };

const Badge = ({ cat }) => {
  const c = CAT[cat] || { label: cat, tone: 'zinc' };
  return <span className={`text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap ${TONE[c.tone]}`}>{c.label}</span>;
};

const nameOf = (r) => r.record?.org?.name || [r.record?.contact?.first_name, r.record?.contact?.last_name].filter(Boolean).join(' ') || '—';

const RowControls = ({ r, decide, locked }) => {
  const o = r.outcome || {};
  const d = r.decision || {};
  if (locked || !r.record || r.role === 'metadata' || r.role === 'example' || r.record.errors?.length) return null;
  const included = o.category !== 'excluded_by_admin' && !['hidden_sage_account', 'uncertain_range', 'excluded_suspected_example'].includes(o.category);
  return (
    <div className="flex flex-col gap-1 text-[11px]">
      <label className="flex items-center gap-1"><input type="checkbox" checked={included} onChange={(e) => decide({ include: e.target.checked })} data-testid={`ci-row-include-${r.row}`} />Include</label>
      {o.relationship?.head_office_ref && o.relationship?.head_office_org_id !== undefined && o.category !== 'circular_relationship' && (
        <select className="border rounded px-1 py-0.5" value={d.relationship || o.relationship.mode || 'merge'} onChange={(e) => decide({ relationship: e.target.value })} data-testid={`ci-row-rel-${r.row}`}>
          <option value="separate">Separate customer (link to {o.relationship.head_office_ref} awaits verification)</option>
          <option value="merge">Merge into head office {o.relationship.head_office_ref} — I have verified it</option>
        </select>
      )}
      {o.conflicts && Object.keys(o.conflicts).length > 0 && (
        <label className="flex items-center gap-1"><input type="checkbox" checked={!!d.apply_changes} onChange={(e) => decide({ apply_changes: e.target.checked })} data-testid={`ci-row-apply-${r.row}`} />Apply changes</label>
      )}
      {o.category === 'ambiguous_contact' && (
        <button type="button" className="text-left underline text-sky-700" onClick={() => decide({ contact_mode: 'new' })} data-testid={`ci-row-newcontact-${r.row}`}>Create as new contact</button>
      )}
    </div>
  );
};

export default function ImportRowsTable({ job, headers, setJob, locked }) {
  const [cat, setCat] = useState('');
  const [q, setQ] = useState('');
  const [data, setData] = useState({ total: 0, rows: [] });
  const seq = useRef(0);
  const load = useCallback(async () => {
    const mine = ++seq.current;  // ignore responses that arrive after a newer request
    const { data: d } = await axios.get(`${API}/jobs/${job.id}/rows`, { headers, params: { category: cat || undefined, search: q || undefined, limit: 200 } });
    if (mine === seq.current) setData(d);
  }, [job.id, headers, cat, q]);
  useEffect(() => { load().catch(() => {}); }, [load, job.evaluated_at, job.status]);
  const decide = (row) => async (patch) => {
    let { data: j } = await axios.post(`${API}/jobs/${job.id}/decisions`, { decisions: [{ row, ...patch }] }, { headers });
    setJob(j);
    while (j.status === 'analysing') {
      await new Promise((r) => setTimeout(r, 800));
      ({ data: j } = await axios.get(`${API}/jobs/${job.id}`, { headers }));
    }
    setJob(j);
  };
  return (
    <div data-testid="ci-rows">
      <div className="flex flex-wrap gap-2 mb-2">
        <select className="border rounded-md px-2 py-1 text-sm" value={cat} onChange={(e) => setCat(e.target.value)} data-testid="ci-filter-category">
          <option value="">All outcomes ({Object.values(job.preview || {}).reduce((a, b) => a + b, 0)})</option>
          {Object.entries(job.preview || {}).map(([k, v]) => <option key={k} value={k}>{CAT[k]?.label || k} ({v})</option>)}
        </select>
        <Input className="h-8 w-64" placeholder="Search account or name" value={q} onChange={(e) => setQ(e.target.value)} data-testid="ci-filter-search" />
        <span className="text-xs text-zinc-500 self-center">Showing {data.rows.length} of {data.total}</span>
      </div>
      <div className="max-h-[480px] overflow-auto border rounded-lg">
        <table className="w-full text-xs">
          <thead className="bg-zinc-50 sticky top-0"><tr className="text-left text-zinc-500">
            <th className="p-2">Row</th><th className="p-2">Account</th><th className="p-2">Name</th><th className="p-2">Outcome</th>
            <th className="p-2">Details</th><th className="p-2">Decision</th></tr></thead>
          <tbody>
            {data.rows.map((r) => {
              const o = r.outcome || {};
              return (
                <tr key={r.row} className="border-t align-top" data-testid={`ci-row-${r.row}`}>
                  <td className="p-2 tabular-nums">{r.row}</td>
                  <td className="p-2 font-mono">{r.record?.account_ref || ''}</td>
                  <td className="p-2">{nameOf(r)}{o.org_name && o.org_name !== nameOf(r) ? <span className="block text-zinc-400">matched: {o.org_name}</span> : null}</td>
                  <td className="p-2"><Badge cat={o.category} />{r.commit_status === 'done' && (job.status === 'rolled_back' ? <span className="block text-zinc-500 mt-1">undone</span> : <span className="block text-emerald-700 mt-1">imported</span>)}{r.commit_status === 'failed' && <span className="block text-red-600 mt-1">{r.error}</span>}</td>
                  <td className="p-2 space-y-0.5 max-w-md">
                    {(r.record?.errors || []).map((e) => <p key={e} className="text-red-600">{e}</p>)}
                    {o.action && <p className="text-amber-700">{o.action}</p>}
                    {(o.warnings || []).map((w) => <p key={w} className="text-zinc-500">{w}</p>)}
                    {Object.entries(o.conflicts || {}).map(([k, v]) => <p key={k} className="text-sky-800">{k}: “{v.current}” → “{v.proposed}”</p>)}
                    {Object.keys(o.fills || {}).length > 0 && <p className="text-zinc-500">Fills blanks: {Object.keys(o.fills).join(', ')}</p>}
                    {r.record?.status?.on_hold && <p className="text-amber-700">Sage: on hold</p>}
                  </td>
                  <td className="p-2"><RowControls r={r} decide={decide(r.row)} locked={locked} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
