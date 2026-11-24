/** Maintenance Master — Import Exception Resolution: one flagged row, its original
 * workbook cells, confirmed corrections, customer search and audited decisions. */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Loader2, Search } from 'lucide-react';

const FIX_FIELDS = [
  ['contract_number', 'Contract number'], ['start_date', 'Start date (YYYY-MM-DD)'], ['end_date', 'Expiry date (YYYY-MM-DD)'],
  ['contract_amount', 'Contract amount (£)'], ['payment_frequency', 'Payment frequency'], ['coordinator_name', 'Contract coordinator'],
];

export function RowResolution({ API, headers, c, uploadId, rowId, onChanged }) {
  const base = `${API}/crm/v2/aftersales/maintenance-master/uploads/${uploadId}/rows/${rowId}`;
  const [row, setRow] = useState(null);
  const [fix, setFix] = useState({});
  const [reason, setReason] = useState('');
  const [q, setQ] = useState('');
  const [found, setFound] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = () => axios.get(base, { headers: headers() }).then(r => setRow(r.data)).catch(() => toast.error('Could not load row'));
  useEffect(() => { load(); }, [rowId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return undefined; }
    const t = setTimeout(() => axios.get(`${API}/crm/v2/aftersales/maintenance-master/customers`, { headers: headers(), params: { q } })
      .then(r => setFound(r.data.customers || [])).catch(() => setFound([])), 300);
    return () => clearTimeout(t);
  }, [q, API, headers]);
  if (!row) return <Loader2 size={14} className="animate-spin" />;
  const staged = row.state === 'staged';
  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); await load(); onChanged(); } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    setBusy(false);
  };
  const correct = () => act(() => axios.post(`${base}/correct`, { fields: Object.fromEntries(Object.entries(fix).filter(([, v]) => String(v).trim())), reason },
    { headers: headers() }).then(() => { setFix({}); setReason(''); }), 'Correction saved — exceptions recalculated');
  const decide = (action, extra = {}) => act(() => axios.post(`${base}/decision`, { action, note: reason, ...extra }, { headers: headers() })
    .then(() => setReason('')), 'Decision recorded');
  const inp = { background: 'transparent', borderColor: c.border, color: c.text };
  return (
    <div data-testid="mm-resolution" className="p-3 rounded-xl border space-y-3 text-xs" style={{ borderColor: c.border, color: c.text }}>
      <div>
        <b>{row.sheet} · row {row.row}</b> · {row.record_key} · <span data-testid="mm-res-class">{row.cls}</span>
        {row.state !== 'staged' && <> · {row.state}</>}
        <div className="mt-1" style={{ color: 'var(--color-warning-alt)' }} data-testid="mm-res-problems">
          {[...(row.problems || []), row.hold_reason].filter(Boolean).join(' · ') || 'No open problems'}
        </div>
        {row.match?.basis && <div style={{ color: c.textDim }}>Customer: {row.match.basis}</div>}
      </div>
      <details open>
        <summary className="cursor-pointer font-semibold">Original workbook data (unchanged)</summary>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-0.5 mt-1" data-testid="mm-res-raw">
          {Object.entries(row.raw || {}).map(([k, v]) => (
            <div key={k} className="truncate" title={`${k}: ${v}`}><span style={{ color: c.textDim }}>{k}:</span> {String(v)}</div>))}
        </div>
      </details>
      {Object.keys(row.corrections || {}).length > 0 && (
        <div data-testid="mm-res-corrections" style={{ color: c.textDim }}>
          Corrections: {Object.entries(row.corrections).map(([k, v]) => `${k} → ${v.value} (${v.by}: ${v.reason})`).join(' · ')}
        </div>)}
      {staged && (<>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {FIX_FIELDS.map(([f, label]) => (
            <label key={f} style={{ color: c.textDim }}>{label}
              <input value={fix[f] ?? ''} placeholder={String(row.effective?.[f] ?? '')} onChange={e => setFix(x => ({ ...x, [f]: e.target.value }))}
                     data-testid={`mm-res-fix-${f}`} className="mt-0.5 w-full px-2 py-1 rounded-md border" style={inp} />
            </label>))}
        </div>
        <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why — e.g. checked against signed agreement / Sage (required)"
               data-testid="mm-res-reason" className="w-full px-2 py-1 rounded-md border" style={inp} />
        <div className="flex flex-wrap gap-2">
          <button disabled={busy || !reason.trim() || !Object.values(fix).some(v => String(v).trim())} onClick={correct} data-testid="mm-res-correct"
                  className="px-3 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>Save correction</button>
          {row.cls === 'duplicate_overlap' && (
            <button disabled={busy || !reason.trim()} onClick={() => decide('accept_duplicate')} data-testid="mm-res-accept-dup"
                    className="px-3 py-1 rounded-lg border disabled:opacity-50" style={{ borderColor: c.border }}>Not a duplicate — keep</button>)}
          <button disabled={busy || !reason.trim()} onClick={() => decide('skip')} data-testid="mm-res-skip"
                  className="px-3 py-1 rounded-lg border disabled:opacity-50" style={{ borderColor: c.border }}>Do not import this row</button>
          {row.decision && <button disabled={busy} onClick={() => decide('reset')} data-testid="mm-res-reset"
                                   className="px-3 py-1 rounded-lg border" style={{ borderColor: c.border, color: c.textDim }}>Undo decision</button>}
        </div>
        <div className="flex items-center gap-2">
          <Search size={12} style={{ color: c.textDim }} />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Find CRM customer by name or Sage account" data-testid="mm-res-customer-search"
                 className="flex-1 px-2 py-1 rounded-md border" style={inp} />
        </div>
        {found.map(k => (
          <div key={k.id} className="flex items-center justify-between">
            <span>{k.name}{k.sage_account ? ` · ${k.sage_account}` : ''}{k.postcode ? ` · ${k.postcode}` : ''}</span>
            <button onClick={() => decide('link_company', { company_id: k.id })} data-testid={`mm-res-link-${k.id}`}
                    className="px-2 py-0.5 rounded border" style={{ borderColor: c.border }}>Use this customer</button>
          </div>))}
      </>)}
      {(row.decision_log || []).length > 0 && (
        <div data-testid="mm-res-log" style={{ color: c.textDim }}>
          {row.decision_log.map((d, i) => <div key={i}>{(d.at || '').slice(0, 16).replace('T', ' ')} · {d.by} · {d.action}{d.note || d.reason ? ` — ${d.note || d.reason}` : ''}</div>)}
        </div>)}
    </div>
  );
}
