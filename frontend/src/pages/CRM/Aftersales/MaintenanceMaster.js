/**
 * Contract Management → Maintenance Master bridge (existing Contracts tab).
 * Upload (chunked) → reconciliation preview → authorised commit → edit with
 * audit → exports → deferred Sicon queue. Reuses the Aftersales panel styling.
 */
import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { UploadCloud, FileSpreadsheet, Download, Loader2, RotateCw, Save, History, Send } from 'lucide-react';
import { useCRM } from '../CRMApp';
import { RowResolution } from './MMResolution';
import { CoordinatorDailyView } from './CMDailyAndInvoice';

const CHUNK = 2 * 1024 * 1024;
const CLS = [
  ['', 'All rows'], ['new_contract', 'New contract'], ['matched_unchanged', 'Matched — unchanged'],
  ['matched_differences', 'Matched — differences'], ['duplicate_overlap', 'Duplicate / overlap'],
  ['missing_information', 'Missing information'], ['requires_review', 'Requires review'], ['held_mod', 'MOD (held)'],
];
const SYNC = {
  not_reconciled: 'Local only', awaiting_customer_mapping: 'Local only — Sage account needed',
  awaiting_sicon_matching: 'Awaiting verification', ready_for_sync: 'Ready for approval', held_for_sicon: 'Held for Sicon',
  changes_pending: 'Changes since last approval', conflict: 'Conflict — review', sync_failed: 'Failed',
  synced_verified: 'Synchronised (verified)',
};
const EDIT_FIELDS = [
  ['customer_name', 'Customer / site'], ['start_date', 'Start date'], ['end_date', 'Expiry date'],
  ['annual_value', 'Annual value (£)'], ['contract_amount', 'Contract amount (£)'], ['payment_frequency', 'Payment frequency'],
  ['direct_debit', 'Paid by Direct Debit'], ['visits_per_year', 'Services per year'], ['coordinator_name', 'Contract coordinator'],
  ['renewal_status', 'Renewal status'], ['next_action_date', 'Next action date'], ['next_action', 'Next action'],
  ['instalment_amount', 'Confirmed instalment amount (£)'], ['invoice_numbers', 'Invoice numbers'], ['sage_account_ref', 'Sage account'], ['comments', 'Comments'],
];
const val = (c, f) => (['start_date', 'end_date', 'annual_value', 'coordinator_name', 'visits_per_year', 'payment_frequency',
  'direct_debit', 'sicon_contract_id', 'sage_account_ref'].includes(f) ? c[f] : (c.mm || {})[f]) ?? '';

function download(API, headers, path, name) {
  return axios.get(`${API}${path}`, { headers: headers(), responseType: 'blob' }).then(r => {
    const url = URL.createObjectURL(r.data);
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
  }).catch(e => toast.error(e.response?.status === 400 ? 'Nothing committed yet' : 'Download failed'));
}

function Btn({ children, onClick, disabled, testId, primary, c, title }) {
  return (
    <button onClick={onClick} disabled={disabled} data-testid={testId} title={title}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
            style={primary ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
      {children}
    </button>
  );
}

function UploadPreview({ API, headers, c, upload, canApprove, onChanged, startUnresolved }) {
  const [cls, setCls] = useState('');
  const [unresolved, setUnresolved] = useState(!!startUnresolved);
  const [issue, setIssue] = useState('');
  const [coord, setCoord] = useState('');
  const [q, setQ] = useState('');
  const [openRow, setOpenRow] = useState(null);
  const [reload, setReload] = useState(0);
  const [rows, setRows] = useState({ rows: [], count: 0 });
  const [rowsLoading, setRowsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [createCustomers, setCreateCustomers] = useState(false);
  const s = upload.summary || {};
  useEffect(() => {
    if (upload.state === 'parsing' || upload.state === 'classifying') return;
    setRowsLoading(true);
    setRows({ rows: [], count: 0 });
    const t = setTimeout(() => axios.get(`${API}/crm/v2/aftersales/maintenance-master/uploads/${upload.id}/rows`,
      { headers: headers(), params: { cls, unresolved, issue, coordinator: coord, q } })
      .then(r => setRows(r.data)).catch(() => setRows({ rows: [], count: 0 })).finally(() => setRowsLoading(false)), 250);
    return () => clearTimeout(t);
  }, [API, headers, upload.id, upload.state, cls, unresolved, issue, coord, q, reload]);
  const commit = async () => {
    const n = s.counts || {};
    const msg = `Commit this workbook into Contract Management?\n\nNew contracts: ${n.new_contract || 0}\nMatched (linked, CRM kept): ${(n.matched_unchanged || 0) + (n.matched_differences || 0)}\nMissing information (held in the review queue): ${n.missing_information || 0}\nRequires review (held until decided): ${n.requires_review || 0}\nDuplicates / overlaps (held): ${n.duplicate_overlap || 0}\n\n${createCustomers ? 'Unmatched customers WILL be created.' : 'Rows with unmatched customers will be held.'}\nNo visits, invoices, emails or Sicon writes are created.`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      await axios.post(`${API}/crm/v2/aftersales/maintenance-master/uploads/${upload.id}/commit`,
        { create_missing_customers: createCustomers }, { headers: headers() });
      toast.success('Commit started — progress updates below'); onChanged();
    } catch (e) { toast.error(e.response?.data?.detail || 'Commit failed'); }
    setBusy(false);
  };
  const decide = async (rid, action, company_id) => {
    try {
      await axios.post(`${API}/crm/v2/aftersales/maintenance-master/uploads/${upload.id}/rows/${rid}/decision`,
        { action, company_id, note: 'Chosen from the preview list' }, { headers: headers() });
      toast.success('Decision saved'); setCls(x => x);
      onChanged();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save'); }
  };
  const base = `/crm/v2/aftersales/maintenance-master/uploads/${upload.id}`;
  return (
    <div data-testid="mm-upload-preview" className="mt-3 space-y-3">
      <div className="text-xs" style={{ color: c.textDim }} data-testid="mm-upload-meta">
        {upload.filename} · SHA-256 {String(upload.sha256 || '').slice(0, 12)}… · {upload.state}
        {upload.same_file_as && ' · identical to an earlier upload'}
        {upload.commit?.progress && ` · created ${upload.commit.progress.created}, linked ${upload.commit.progress.linked}, updated ${upload.commit.progress.updated}, held ${upload.commit.progress.held}, failed ${upload.commit.progress.failed}`}
      </div>
      {s.totals && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="mm-totals">
            <thead><tr style={{ color: c.textDim }}>{['Sheet', 'Rows', 'Active', 'Expired', 'Future', 'Uncertain', 'Contract amount £', 'Stated annual £'].map(h => <th key={h} className="px-2 py-1 text-left">{h}</th>)}</tr></thead>
            <tbody>{Object.entries(s.totals).map(([k, t]) => (
              <tr key={k} style={{ color: c.text }}><td className="px-2 py-1">{k}</td><td className="px-2">{t.rows}</td><td className="px-2">{t.active}</td>
                <td className="px-2">{t.expired}</td><td className="px-2">{t.future}</td><td className="px-2">{t.uncertain}</td>
                <td className="px-2">{t.contract_amount.toLocaleString()}</td><td className="px-2">{t.annual_value.toLocaleString()}</td></tr>))}</tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap gap-2" data-testid="mm-classes">
        {CLS.map(([id, label]) => (
          <button key={id || 'all'} onClick={() => setCls(id)} data-testid={`mm-class-${id || 'all'}`}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium border"
                  style={{ borderColor: cls === id ? 'var(--color-brand-cyan)' : c.border, color: cls === id ? 'var(--color-brand-cyan)' : c.textDim }}>
            {label}{id && s.counts ? ` · ${s.counts[id] ?? (id === 'held_mod' ? s.held_mod : 0)}` : ''}
          </button>))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="mm-res-filters">
        <label className="inline-flex items-center gap-1" style={{ color: c.textDim }}>
          <input type="checkbox" checked={unresolved} onChange={e => setUnresolved(e.target.checked)} data-testid="mm-filter-unresolved" /> Unresolved only
        </label>
        <select value={issue} onChange={e => setIssue(e.target.value)} data-testid="mm-filter-issue" className="px-2 py-1 rounded-lg border" style={{ background: 'transparent', borderColor: c.border, color: c.text }}>
          <option value="">Any issue</option><option value="contract number">Contract number missing</option>
          <option value="date">Start / expiry date missing</option><option value="amount">Contract amount missing</option>
          <option value="more than one">Duplicate contract number</option><option value="overlap">Overlaps a CRM contract</option>
          <option value="name matches">Customer name only</option><option value="Sicon">Sicon ID conflict</option>
        </select>
        <input value={coord} onChange={e => setCoord(e.target.value)} placeholder="Coordinator" data-testid="mm-filter-coordinator"
               className="px-2 py-1 rounded-lg border w-32" style={{ background: 'transparent', borderColor: c.border, color: c.text }} />
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Customer / contract / account" data-testid="mm-filter-q"
               className="px-2 py-1 rounded-lg border w-48" style={{ background: 'transparent', borderColor: c.border, color: c.text }} />
      </div>
      <div className="rounded-xl border overflow-x-auto max-h-[32rem]" style={{ borderColor: c.border }}>
        <table className="w-full text-xs" data-testid="mm-rows">
          <thead><tr style={{ color: c.textDim }}>{['Sheet / row', 'Customer', 'Contract', 'Term', 'Status', 'Classification', 'Notes', ''].map(h => <th key={h} className="px-2 py-1 text-left">{h}</th>)}</tr></thead>
          <tbody>{rows.rows.map(r => (<Fragment key={r.id}>
            <tr className="border-t cursor-pointer" style={{ borderColor: c.border, color: c.text }} data-testid={`mm-row-${r.id}`}
                onClick={() => setOpenRow(o => (o === r.id ? null : r.id))}>
              <td className="px-2 py-1">{r.sheet} · {r.row}</td><td className="px-2">{r.mapped.customer_name}</td>
              <td className="px-2">{r.mapped.contract_number || '—'}</td><td className="px-2">{r.mapped.start_date || '?'} → {r.mapped.end_date || '?'}</td>
              <td className="px-2">{r.status}</td><td className="px-2">{(CLS.find(x => x[0] === r.cls) || [])[1] || r.cls}{r.state === 'committed' ? ' ✓' : ''}</td>
              <td className="px-2" style={{ color: c.textDim }}>{[...(r.problems || []), r.hold_reason, r.conflicts?.length ? `app kept: ${r.conflicts.join(', ')}` : ''].filter(Boolean).join('; ')}</td>
              <td className="px-2 whitespace-nowrap">
                {r.state === 'staged' && (r.match?.candidates || []).map(k => (
                  <button key={k.id} onClick={() => decide(r.id, 'link_company', k.id)} data-testid={`mm-link-${r.id}-${k.id}`}
                          className="mr-1 px-1.5 py-0.5 rounded border" style={{ borderColor: c.border }}
                          title={k.id}>Use {k.name}{k.ref ? ` (${k.ref})` : ` (no account ref · ${k.id.slice(0, 6)})`}</button>))}
                {r.state === 'staged' && r.match?.status === 'new' && (
                  <button onClick={() => decide(r.id, 'create_customer')} data-testid={`mm-create-${r.id}`}
                          className="px-1.5 py-0.5 rounded border" style={{ borderColor: c.border }}>New customer</button>)}
              </td>
            </tr>
            {openRow === r.id && <tr><td colSpan={8} className="p-2" onClick={e => e.stopPropagation()}>
              <RowResolution API={API} headers={headers} c={c} uploadId={upload.id} rowId={r.id} onChanged={() => { setReload(x => x + 1); onChanged(); }} />
            </td></tr>}
          </Fragment>))}</tbody>
        </table>
      </div>
      <div className="text-[11px]" style={{ color: c.textDim }} data-testid="mm-rows-count">
        {rowsLoading ? <><Loader2 size={11} className="inline animate-spin" /> Loading rows…</> : `${rows.count} rows in this view (first 50 shown).`}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Btn c={c} testId="mm-report-reconciliation" onClick={() => download(API, headers, `${base}/report?kind=reconciliation`, 'reconciliation.xlsx')}><Download size={13} /> Reconciliation report</Btn>
        <Btn c={c} testId="mm-report-unresolved" onClick={() => download(API, headers, `${base}/report?kind=unresolved`, 'unresolved.xlsx')}><Download size={13} /> Unresolved items</Btn>
        <Btn c={c} testId="mm-report-exceptions" onClick={() => download(API, headers, `${base}/report?kind=exceptions`, 'exceptions.xlsx')}><Download size={13} /> Exception report</Btn>
        <Btn c={c} testId="mm-original" onClick={() => download(API, headers, `${base}/original`, upload.filename)}><FileSpreadsheet size={13} /> Original workbook</Btn>
        {canApprove && ['ready', 'partial', 'commit_failed', 'committed'].includes(upload.state) && (<>
          <label className="text-xs inline-flex items-center gap-1" style={{ color: c.textDim }}>
            <input type="checkbox" checked={createCustomers} onChange={e => setCreateCustomers(e.target.checked)} data-testid="mm-create-customers" />
            Create unmatched customers
          </label>
          <Btn c={c} primary testId="mm-commit" disabled={busy} onClick={commit}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {upload.state === 'ready' ? 'Approve & commit' : 'Retry / continue commit'}</Btn>
        </>)}
      </div>
    </div>
  );
}

function ContractEditor({ API, headers, c, id, canApprove, onSaved }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({});
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const dirty = useRef(false);
  const load = useCallback((force) => axios.get(`${API}/crm/v2/aftersales/maintenance-master/contracts/${id}`, { headers: headers() })
    .then(r => {
      setData(r.data);
      if (force || !dirty.current) setForm(Object.fromEntries(EDIT_FIELDS.map(([f]) => [f, val(r.data.contract, f)])));
    }), [API, headers, id]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <Loader2 size={14} className="animate-spin" />;
  const ct = data.contract;
  const unsaved = EDIT_FIELDS.some(([f]) => String(form[f] ?? '') !== String(val(ct, f)));
  const save = async () => {
    const changes = Object.fromEntries(EDIT_FIELDS.map(([f]) => [f, form[f]]).filter(([f, v]) => String(v ?? '') !== String(val(ct, f))));
    if (!Object.keys(changes).length) { toast.info('No changes'); return; }
    try {
      await axios.patch(`${API}/crm/v2/aftersales/maintenance-master/contracts/${id}`, { revision: ct.revision, changes, reason },
        { headers: headers() });
      toast.success('Saved'); setReason(''); dirty.current = false; load(true); onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
      if (e.response?.status === 409) { dirty.current = false; load(true); }
    }
  };
  const addNote = async () => {
    try { await axios.post(`${API}/crm/v2/aftersales/maintenance-master/contracts/${id}/notes`, { text: note }, { headers: headers() }); setNote(''); load(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Note failed'); }
  };
  const queue = async () => {
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/maintenance-master/contracts/${id}/sicon-queue`, {}, { headers: headers() });
      toast.success(`Queued for Sicon (${r.data.state.replaceAll('_', ' ')}) — nothing sent`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Queue failed'); }
  };
  const inp = { background: 'transparent', borderColor: c.border, color: c.text };
  return (
    <div data-testid="mm-editor" className="mt-2 p-3 rounded-xl border space-y-3" style={{ borderColor: c.border }}>
      <div className="text-xs" style={{ color: c.textDim }}>
        Master record {ct.mm_record_key} · {ct.mm_source?.sheet} row {ct.mm_source?.row} · revision <span data-testid="mm-revision">{ct.revision}</span> ·
        Sicon: <span data-testid="mm-sync-state">{SYNC[ct.sicon_sync?.state] || '—'}</span>{ct.sicon_contract_id ? ` (${ct.sicon_contract_id})` : ''}
        {(ct.mm_exceptions || []).length > 0 && <div style={{ color: 'var(--color-warning-alt, #F59E0B)' }}>Missing / check: {ct.mm_exceptions.join('; ')}</div>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {EDIT_FIELDS.map(([f, label]) => (
          <label key={f} className="text-[11px]" style={{ color: c.textDim }}>{label}
            <input value={form[f] ?? ''} onChange={e => { dirty.current = true; setForm(x => ({ ...x, [f]: e.target.value })); }} data-testid={`mm-edit-${f}`}
                   className="mt-0.5 w-full text-xs px-2 py-1 rounded-md border" style={inp} />
          </label>))}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason for change / approval reference" data-testid="mm-edit-reason"
               className="text-xs px-2 py-1 rounded-md border w-72" style={inp} />
        <Btn c={c} primary testId="mm-edit-save" onClick={save}><Save size={13} /> Save changes</Btn>
        <span data-testid="mm-edit-state" className="text-[11px]" style={{ color: unsaved ? 'var(--color-warning-alt)' : c.textDim }}>
          {unsaved ? 'Unsaved changes' : `Saved · revision ${ct.revision}`}</span>
        {canApprove && <Btn c={c} testId="mm-sicon-queue" onClick={queue}><Send size={13} /> Approve for Sicon queue</Btn>}
      </div>
      <div className="flex gap-2 items-center">
        <input value={note} onChange={e => setNote(e.target.value)} placeholder="Add a note" data-testid="mm-note-input"
               className="text-xs px-2 py-1 rounded-md border flex-1" style={inp} />
        <Btn c={c} testId="mm-note-add" disabled={!note.trim()} onClick={addNote}>Add note</Btn>
      </div>
      <div data-testid="mm-history" className="max-h-48 overflow-y-auto text-[11px]" style={{ color: c.textDim }}>
        <div className="font-semibold mb-1 inline-flex items-center gap-1"><History size={12} /> Change history</div>
        {data.changes.length === 0 ? <div>No changes since migration.</div> : data.changes.map(h => (
          <div key={h.id}>{h.at.slice(0, 16).replace('T', ' ')} · {h.by} · {h.field}: {String(h.old ?? '—')} → {String(h.new ?? '—')}{h.reason ? ` (${h.reason})` : ''}</div>))}
      </div>
    </div>
  );
}

function ContractsList({ API, headers, c, canApprove, refreshKey, search }) {
  const [q, setQ] = useState('');
  useEffect(() => { if (search) setQ(search.q); }, [search]);
  const [status, setStatus] = useState('');
  const [exceptions, setExceptions] = useState(false);
  const [data, setData] = useState({ contracts: [], count: 0 });
  const [open, setOpen] = useState(null);
  const load = useCallback(() => axios.get(`${API}/crm/v2/aftersales/maintenance-master/contracts`, { headers: headers(), params: { q, status, exceptions } })
    .then(r => setData(r.data)).catch(() => setData({ contracts: [], count: 0 })), [API, headers, q, status, exceptions]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load, refreshKey]);
  const inp = { background: 'transparent', borderColor: c.border, color: c.text };
  return (
    <div data-testid="mm-contracts" className="mt-4">
      <div className="flex flex-wrap gap-2 items-center mb-2">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search customer, contract, Sage account…" data-testid="mm-contracts-search"
               className="text-xs px-2 py-1.5 rounded-lg border w-64" style={inp} />
        <select value={status} onChange={e => setStatus(e.target.value)} data-testid="mm-contracts-status" className="text-xs px-2 py-1.5 rounded-lg border" style={inp}>
          <option value="">All statuses</option><option value="active">Active</option><option value="expired">Expired</option>
          <option value="pending_start">Future</option><option value="draft">Uncertain</option>
        </select>
        <label className="text-xs inline-flex items-center gap-1" style={{ color: c.textDim }}>
          <input type="checkbox" checked={exceptions} onChange={e => setExceptions(e.target.checked)} data-testid="mm-contracts-exceptions" /> Missing information only
        </label>
        <span className="text-xs" style={{ color: c.textDim }} data-testid="mm-contracts-count">{data.count} imported contracts</span>
      </div>
      <div className="rounded-xl border overflow-x-auto" style={{ borderColor: c.border }}>
        <table className="w-full text-xs">
          <thead><tr style={{ color: c.textDim }}>{['Contract', 'Customer', 'Term', 'Annual £', 'DD', 'Coordinator', 'Status', 'Sicon'].map(h => <th key={h} className="px-2 py-1 text-left">{h}</th>)}</tr></thead>
          <tbody>{data.contracts.map(ct => (<Fragment key={ct.id}>
            <tr onClick={() => setOpen(o => (o === ct.id ? null : ct.id))} data-testid={`mm-contract-${ct.id}`}
                className="border-t cursor-pointer" style={{ borderColor: c.border, color: c.text }}>
              <td className="px-2 py-1 font-semibold">{ct.contract_number || '—'}</td><td className="px-2">{ct.company_name}</td>
              <td className="px-2">{ct.start_date || '?'} → {ct.end_date || '?'}</td><td className="px-2">{ct.annual_value ?? '—'}</td>
              <td className="px-2">{ct.direct_debit || '—'}</td><td className="px-2">{ct.coordinator_name || '—'}</td>
              <td className="px-2">{ct.status}{(ct.mm_exceptions || []).length ? ' ⚠' : ''}</td><td className="px-2">{SYNC[ct.sicon_sync?.state] || '—'}</td>
            </tr>
            {open === ct.id && <tr><td colSpan={8}><ContractEditor API={API} headers={headers} c={c} id={ct.id} canApprove={canApprove} onSaved={load} /></td></tr>}
          </Fragment>))}</tbody>
        </table>
      </div>
    </div>
  );
}

export function MaintenanceMasterPanel({ API, headers, c, isDark }) {
  const perms = useCRM().user?.crm_permissions || [];
  const canManage = perms.includes('contracts.manage');
  const canApprove = perms.includes('exceptions.approve');
  const [list, setList] = useState({ uploads: [] });
  const [progress, setProgress] = useState(null);
  const [tick, setTick] = useState(0);
  const [picked, setPicked] = useState('');
  const [search, setSearch] = useState(null);
  const [focusExceptions, setFocusExceptions] = useState(0);
  const fileRef = useRef(null);
  const load = useCallback(() => axios.get(`${API}/crm/v2/aftersales/maintenance-master/uploads`, { headers: headers() })
    .then(r => setList(r.data)).catch(() => setList({ uploads: [] })), [API, headers]);
  useEffect(() => { load(); }, [load, tick]);
  const latest = list.uploads.find(u => u.id === picked) || list.uploads[0];
  useEffect(() => {
    if (!latest || !['parsing', 'classifying', 'committing'].includes(latest.state)) return undefined;
    const t = setInterval(load, 3000); return () => clearInterval(t);
  }, [latest, load]);
  const upload = async (file) => {
    if (!file) return;
    const total = Math.max(1, Math.ceil(file.size / CHUNK));
    try {
      const { data } = await axios.post(`${API}/crm/v2/aftersales/maintenance-master/uploads`,
        { filename: file.name, size: file.size, total_chunks: total }, { headers: headers() });
      for (let n = 0; n < total; n += 1) {
        setProgress(Math.round((n / total) * 100));
        const part = await file.slice(n * CHUNK, (n + 1) * CHUNK).arrayBuffer();
        await axios.put(`${API}/crm/v2/aftersales/maintenance-master/uploads/${data.upload_id}/chunks/${n}`, part,
          { headers: { ...headers(), 'Content-Type': 'application/octet-stream' } });
      }
      setProgress(100);
      await axios.post(`${API}/crm/v2/aftersales/maintenance-master/uploads/${data.upload_id}/complete`, {}, { headers: headers() });
      toast.success('Uploaded — building the reconciliation preview'); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload failed — you can retry safely'); }
    setProgress(null);
    if (fileRef.current) fileRef.current.value = '';
  };
  const panel = { background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-50)', borderColor: c.border };
  return (
    <div data-testid="mm-panel" className="mb-6 p-4 rounded-xl border" style={panel}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold" style={{ color: c.text }}>Maintenance Master</h2>
          <p className="text-xs" style={{ color: c.textDim }}>
            Import the approved workbook, review the reconciliation, then work on the contracts here. Sicon writes are
            <span data-testid="mm-sicon-writes" className="font-semibold"> {list.sicon_writes_enabled ? 'ENABLED' : 'switched off'}</span>.
            {list.cutover && <span data-testid="mm-cutover"> Cut over {list.cutover.at.slice(0, 10)} — the app is the system of record.</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage && <>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={e => upload(e.target.files[0])} data-testid="mm-file-input" />
            <Btn c={c} primary testId="mm-upload" disabled={progress !== null} onClick={() => fileRef.current?.click()}>
              {progress !== null ? <><Loader2 size={13} className="animate-spin" /> {progress}%</> : <><UploadCloud size={13} /> Upload workbook</>}
            </Btn></>}
          <Btn c={c} testId="mm-export-current" onClick={() => download(API, headers, '/crm/v2/aftersales/maintenance-master/export/current', 'crm-contracts.xlsx')}><Download size={13} /> Current data (Excel)</Btn>
          <Btn c={c} testId="mm-export-master" title="Edits go into their original cells; fields with no column in the workbook are listed on its 'Pulse Fitness Pro changes' sheet" onClick={() => download(API, headers, '/crm/v2/aftersales/maintenance-master/export/master', 'Maintenance Master - updated.xlsx')}><FileSpreadsheet size={13} /> Updated Master workbook</Btn>
          <Btn c={c} testId="mm-refresh" onClick={() => setTick(t => t + 1)}><RotateCw size={13} /></Btn>
        </div>
      </div>
      <div className="mt-3"><CoordinatorDailyView API={API} headers={headers} c={c}
        onOpenContract={n => { setSearch({ q: n, t: Date.now() }); setTimeout(() => document.querySelector('[data-testid=mm-contracts]')?.scrollIntoView({ behavior: 'smooth' }), 100); }}
        onOpenExceptions={() => { setFocusExceptions(x => x + 1); setTimeout(() => document.querySelector('[data-testid=mm-res-filters]')?.scrollIntoView({ behavior: 'smooth' }), 100); }} /></div>
      {list.uploads.length > 1 && (
        <select value={latest?.id || ''} onChange={e => setPicked(e.target.value)} data-testid="mm-upload-picker"
                className="mt-3 text-xs px-2 py-1.5 rounded-lg border max-w-full" style={{ background: 'transparent', borderColor: c.border, color: c.text }}>
          {list.uploads.map(u => <option key={u.id} value={u.id}>{`${u.filename} · ${(u.created_at || '').slice(0, 16).replace('T', ' ')} · ${u.state}`}</option>)}
        </select>)}
      {latest ? <UploadPreview key={`${latest.id}-${focusExceptions}`} startUnresolved={focusExceptions > 0} API={API} headers={headers} c={c} upload={latest} canApprove={canApprove} onChanged={() => setTick(t => t + 1)} />
        : <div className="mt-3 text-xs" style={{ color: c.textDim }} data-testid="mm-empty">No workbook uploaded yet.</div>}
      <ContractsList API={API} headers={headers} c={c} canApprove={canApprove} refreshKey={tick} search={search} />
    </div>
  );
}
