import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, FileUp, Plus, Search, Trash2, Database, Save } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, gbp, TYPE_LABEL, TYPE_DESC, card, muted, inputStyle } from './modQuotesApi';
import { Btn, Banner } from './MqUi';

const STAGES = ['Customer & site', 'Equipment & options', 'Review & generate'];

function Stepper({ stage }) {
  return (
    <>
    <ol className="mq-steps mb-2 sm:mb-6" data-testid="mq-wizard-stepper" aria-label="Quotation steps">
      {STAGES.map((s, i) => (
        <li key={s} className="mq-step" data-state={i === stage ? 'current' : i < stage ? 'done' : 'todo'} aria-current={i === stage ? 'step' : undefined} data-testid={`mq-step-${i}`}>
          <span className="mq-step-n">{i < stage ? <Check size={14} /> : i + 1}</span><span className="mq-step-t">{s}</span>
        </li>
      ))}
    </ol>
    <div className="sm:hidden text-sm font-semibold mb-5" data-testid="mq-step-label">Step {stage + 1} of {STAGES.length} · {STAGES[stage]}</div>
    </>
  );
}

function CustomerStage({ customer, setCustomer }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const seq = useRef(0);
  useEffect(() => {
    const n = ++seq.current;
    const t = setTimeout(() => {
      mq.get('/customers', { params: { q } }).then((r) => { if (n === seq.current) setResults(r.data.customers); })
        .catch((e) => notify.error(errText(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  const field = (k, label, ph = '') => (
    <label className="block text-sm">
      <span style={muted}>{label}</span>
      <input data-testid={`mq-cust-${k}`} value={customer?.[k] || ''} placeholder={ph}
        onChange={(e) => setCustomer({ ...customer, [k]: e.target.value })}
        className="mt-1 w-full rounded-lg px-3 py-2" style={inputStyle} />
    </label>
  );
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="rounded-xl p-4" style={card}>
        <div className="flex items-center gap-2 rounded-lg px-3 py-2" style={inputStyle}>
          <Search size={16} style={muted} />
          <input data-testid="mq-customer-search" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search MOD establishment or site" className="flex-1 bg-transparent outline-none" />
        </div>
        <ul className="mt-3 max-h-96 overflow-y-auto divide-y" style={{ borderColor: 'var(--theme-border)' }}>
          {results.map((c) => (
            <li key={c.site_id}>
              <button type="button" data-testid={`mq-customer-${c.site_id}`} onClick={() => setCustomer({ ...c, delivery_lines: [], customer_reference: '' })}
                className="w-full text-left px-2 py-2.5 rounded-lg transition-colors hover:opacity-80"
                style={customer?.site_id === c.site_id ? { background: 'var(--theme-hover-bg)' } : undefined}>
                <div className="font-semibold">{c.name}</div>
                <div className="text-xs" style={muted}>{c.address_lines.join(', ') || 'No address held'} · {c.equipment_count} items on register</div>
              </button>
            </li>
          ))}
          {!results.length && <li className="py-6 text-sm text-center" style={muted}>No MOD sites match.</li>}
        </ul>
      </div>
      <div className="rounded-xl p-4 space-y-3" style={card} data-testid="mq-customer-details">
        {!customer ? <p className="text-sm" style={muted}>Select a MOD site to fill in the verified details.</p> : (
          <>
            <div className="text-lg font-semibold">{customer.name}</div>
            <label className="block text-sm">
              <span style={muted}>Billing address (one line each)</span>
              <textarea data-testid="mq-cust-address" rows={5} value={(customer.address_lines || []).join('\n')}
                onChange={(e) => setCustomer({ ...customer, address_lines: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
                className="mt-1 w-full rounded-lg px-3 py-2" style={inputStyle} />
            </label>
            <label className="block text-sm">
              <span style={muted}>Delivery address — leave blank for "As Above"</span>
              <textarea data-testid="mq-cust-delivery" rows={2} value={(customer.delivery_lines || []).join('\n')}
                onChange={(e) => setCustomer({ ...customer, delivery_lines: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
                className="mt-1 w-full rounded-lg px-3 py-2" style={inputStyle} />
            </label>
            <div className="grid sm:grid-cols-2 gap-3">
              {field('contact_name', 'Contact name')}
              {field('contact_email', 'Contact email')}
              {field('contact_phone', 'Contact telephone')}
              {field('account_ref', 'Customer account reference')}
              {field('customer_reference', 'Customer reference', 'If supplied')}
            </div>
            {!customer.address_lines?.length && <p className="text-xs" style={{ color: 'var(--color-warning)' }}>No address held — enter the verified address before publishing.</p>}
          </>
        )}
      </div>
    </div>
  );
}

function RowEditor({ row, catalogue, onChange, onRemove, showCoverage }) {
  const services = catalogue.filter((e) => e.kind === 'service');
  return (
    <tr className="border-t align-top" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mq-row-${row.row_id}`}>
      <td className="p-2 w-20 min-w-[76px]">
        <input type="number" min={0} aria-label="Quantity" value={row.qty} onChange={(e) => onChange({ ...row, qty: Math.max(0, parseInt(e.target.value || '0', 10)) })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid="mq-row-qty" />
      </td>
      <td className="p-2 min-w-[220px]">
        <select value={row.rate_card_id || ''} onChange={(e) => onChange({ ...row, rate_card_id: e.target.value || null, needs_review: false })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid="mq-row-sor">
          <option value="">— choose item code —</option>
          {services.map((e) => <option key={e.id} value={e.id}>{`${e.label}${e.sage_code_a ? ` (${e.sage_code_a.replace(/-A$/, '')})` : ''}`}</option>)}
        </select>
        {row.needs_review && <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }} data-testid="mq-row-review">Check this match{row.description ? ` for "${row.description}"` : ''}{row.match_confidence ? ` (${Math.round(row.match_confidence * 100)}%)` : ''}</div>}
        {row.serial && <div className="text-xs mt-1" style={muted}>S/N {row.serial}</div>}
      </td>
      <td className="p-2 min-w-[120px]">
        <input value={row.label} placeholder="Optional" onChange={(e) => onChange({ ...row, label: e.target.value })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid="mq-row-label" />
      </td>
      <td className="p-2 min-w-[110px]">
        <input value={row.location} onChange={(e) => onChange({ ...row, location: e.target.value })}
          className="w-full rounded px-2 py-1 text-sm" style={inputStyle} data-testid="mq-row-location" />
      </td>
      {showCoverage && (
        <td className="p-2 w-28">
          <div className="mq-seg" role="group" aria-label="Coverage type">
            {['A', 'B'].map((t) => (
              <button key={t} type="button" onClick={() => onChange({ ...row, coverage: t })} data-testid={`mq-row-cov-${t}`}
                aria-pressed={row.coverage === t}>{t}</button>
            ))}
          </div>
        </td>
      )}
      <td className="p-2 w-10">
        <button type="button" onClick={onRemove} aria-label="Remove row" data-testid="mq-row-remove"><Trash2 size={16} style={muted} /></button>
      </td>
    </tr>
  );
}

function EquipmentStage({ customer, rows, setRows, catalogue, options, children }) {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const showCov = options.includes('AB');
  const loadRegister = async () => {
    setBusy(true);
    try {
      const r = await mq.get(`/sites/${customer.site_id}/equipment`);
      setRows([...rows, ...r.data.rows]);
      notify.success(`${r.data.rows.length} items loaded from the equipment register`);
    } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const upload = async (f) => {
    if (!f) return;
    setBusy(true);
    const fd = new FormData();
    fd.append('file', f);
    try {
      const r = await mq.post('/import-equipment', fd);
      setRows([...rows, ...r.data.rows]);
      notify.success(`${r.data.rows.length} rows imported — check any highlighted matches`);
    } catch (e) { notify.error(errText(e)); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const addManual = () => setRows([...rows, { row_id: crypto.randomUUID(), description: '', qty: 1, rate_card_id: null, label: '', location: '', serial: '', coverage: null, source: 'manual' }]);
  const bulk = (mode) => setRows(rows.map((r) => ({ ...r, coverage: mode === 'suggest' ? (r.suggested_coverage || suggestFrom(r, catalogue)) : mode })));
  const reviewCount = rows.filter((r) => r.needs_review || !r.rate_card_id).length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Btn icon={Database} onClick={loadRegister} loading={busy} data-testid="mq-load-register">Load equipment register</Btn>
        <Btn icon={FileUp} onClick={() => fileRef.current?.click()} disabled={busy} data-testid="mq-upload-btn">Upload Excel / CSV</Btn>
        <input ref={fileRef} type="file" accept=".xlsx,.csv,.xlsm" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="mq-upload-input" />
        <Btn icon={Plus} onClick={addManual} data-testid="mq-add-row">Add item</Btn>
      </div>
      {children}
      {showCov && rows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="mq-bulk-coverage">
          <span style={muted}>Mixed quote coverage:</span>
          <Btn size="sm" onClick={() => bulk('A')} data-testid="mq-bulk-all-a">All Type A</Btn>
          <Btn size="sm" onClick={() => bulk('B')} data-testid="mq-bulk-all-b">All Type B</Btn>
          <Btn size="sm" onClick={() => bulk('suggest')} data-testid="mq-bulk-suggest">Suggest: cardio A, strength B</Btn>
          <span className="text-xs" style={muted}>Suggestions are a starting point — confirm each row.</span>
        </div>
      )}
      {reviewCount > 0 && <Banner testid="mq-review-count">{reviewCount} row(s) need a confirmed item code before you continue.</Banner>}
      <div className="mq-card overflow-x-auto">
        <table className="mq-table mq-table--dense">
          <thead><tr>
            <th className="p-2">Qty</th><th className="p-2">Item Code</th>
            <th className="p-2">Notes</th><th className="p-2">Location</th>{showCov && <th className="p-2">A/B</th>}<th />
          </tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <RowEditor key={r.row_id} row={r} catalogue={catalogue} showCoverage={showCov}
                onChange={(nr) => setRows(rows.map((x, j) => (j === i ? nr : x)))} onRemove={() => setRows(rows.filter((_, j) => j !== i))} />
            ))}
            {!rows.length && <tr><td colSpan={6} className="p-8 text-center" style={muted}>Load the register, upload a list or add items manually.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const CARDIO = ['treadmill', 'cross trainer', 'rowing', 'rowers', 'bike', 'stepper', 'climber', 'wave', 'spinning', 'grappler'];
function suggestFrom(row, catalogue) {
  const e = catalogue.find((c) => c.id === row.rate_card_id);
  return e && CARDIO.some((k) => (e.equipment_type || '').toLowerCase().includes(k)) ? 'A' : 'B';
}

function OptionCard({ t, on, toggle, preview }) {
  return (
    <button type="button" onClick={toggle} data-testid={`mq-option-${t}`} className="mq-option" aria-pressed={on}>
      <div className="flex items-center justify-between">
        <div className="font-semibold">{TYPE_LABEL[t]}</div>
        <span className="w-6 h-6 rounded-full flex items-center justify-center" style={on ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { border: '1px solid var(--theme-border)' }}>{on && <Check size={13} />}</span>
      </div>
      <div className="text-xs mt-0.5" style={muted}>{TYPE_DESC[t]}</div>
      {preview && on && (
        <div className="mq-totals" data-testid={`mq-option-${t}-totals`}>
          <div><span className="mq-muted">Net</span><span>{gbp(preview.net)}</span></div>
          <div><span className="mq-muted">VAT</span><span>{gbp(preview.vat)}</span></div>
          <div className="items-baseline"><span className="font-semibold">Gross</span><span className="mq-gross" data-testid={`mq-option-${t}-gross`}>{gbp(preview.gross)}</span></div>
          {preview.issues.length > 0 && <div className="text-xs pt-1" style={{ color: 'var(--color-danger)' }}>{preview.issues.length} issue(s) to resolve</div>}
          {preview.unverified_lines.length > 0 && <div className="text-xs" style={{ color: 'var(--color-warning)' }}>{preview.unverified_lines.length} line(s) on unverified rates</div>}
        </div>
      )}
    </button>
  );
}

function ReviewStage({ preview }) {
  const opts = Object.entries(preview || {});
  return (
    <div className="grid xl:grid-cols-3 gap-4" data-testid="mq-review">
      {opts.map(([t, p]) => (
        <div key={t} className="mq-card p-5" data-testid={`mq-review-${t}`}>
          <div className="font-semibold mb-2">{TYPE_LABEL[t]} <span className="text-xs font-normal" style={muted}>{TYPE_DESC[t]}</span></div>
          <table className="w-full text-xs">
            <thead><tr style={muted}><th className="text-left">Code</th><th className="text-left">Description</th><th>Qty</th><th className="text-right">Total</th></tr></thead>
            <tbody>{p.lines.map((ln) => (
              <tr key={ln.line_no} className="border-t align-top" style={{ borderColor: 'var(--theme-border)' }}>
                <td className="py-1 pr-2 whitespace-nowrap">{ln.item_code}</td><td className="py-1 pr-2">{ln.description}</td>
                <td className="py-1 text-center">{ln.qty}</td><td className="py-1 text-right">{ln.total.toFixed(2)}</td>
              </tr>))}</tbody>
          </table>
          <div className="mq-totals">
            <div><span className="mq-muted">Total net</span><span>{gbp(p.net)}</span></div>
            <div><span className="mq-muted">Total VAT</span><span>{gbp(p.vat)}</span></div>
            <div className="items-baseline"><span className="font-semibold">Total gross</span><span className="mq-gross" data-testid={`mq-review-${t}-gross`}>{gbp(p.gross)}</span></div>
          </div>
          {p.issues.map((i) => <div key={i} className="text-xs mt-1" style={{ color: 'var(--color-danger)' }}>{i}</div>)}
          {p.excluded_rows?.length > 0 && <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }} data-testid={`mq-excluded-${t}`}>Not quoted (quantity 0): {p.excluded_rows.join(', ')}</div>}
          {p.unverified_lines?.length > 0 && <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>Unverified rates on lines {p.unverified_lines.map((u) => u.line_no).join(', ')} — manager exception needed before publishing</div>}
        </div>
      ))}
    </div>
  );
}

export default function ModQuoteWizard({ group, onDone, onCancel }) {
  const [stage, setStage] = useState(group ? 1 : 0);
  const [customer, setCustomer] = useState(group?.customer || null);
  const [rows, setRows] = useState(group?.rows || []);
  const [options, setOptions] = useState(group?.options || ['A', 'B', 'AB']);
  const [calloutQty, setCalloutQty] = useState(group?.callout_qty ?? 1);
  const [catalogue, setCatalogue] = useState([]);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [idemKey] = useState(() => crypto.randomUUID());

  useEffect(() => { mq.get('/catalogue').then((r) => setCatalogue(r.data.entries)).catch((e) => notify.error(errText(e))); }, []);
  const payload = useMemo(() => ({ customer, rows, options, callout_qty: calloutQty, idempotency_key: group ? null : idemKey }), [customer, rows, options, calloutQty, group, idemKey]);
  useEffect(() => {
    if (!customer || !rows.length || !options.length) { setPreview(null); return undefined; }
    const t = setTimeout(() => mq.post('/preview', payload).then((r) => setPreview(r.data.options)).catch(() => setPreview(null)), 300);
    return () => clearTimeout(t);
  }, [payload, customer, rows.length, options.length]);

  const unmapped = rows.filter((r) => r.qty > 0 && !r.rate_card_id).length;
  const canNext = [!!customer?.site_id, rows.some((r) => r.qty > 0) && !unmapped && options.length > 0, true][stage];
  const toggle = (t) => setOptions(options.includes(t) ? options.filter((o) => o !== t) : [...options, t]);
  const save = async () => {
    setSaving(true);
    try {
      const r = group ? await mq.put(`/groups/${group.id}`, payload) : await mq.post('/groups', payload);
      notify.success(group ? 'Quotation group updated' : `${r.data.quotes.length} quotation(s) generated as drafts`);
      onDone(r.data);
    } catch (e) { notify.error(errText(e)); } finally { setSaving(false); }
  };

  return (
    <div data-testid="mq-wizard">
      <Btn variant="ghost" size="sm" icon={ArrowLeft} onClick={onCancel} className="mb-3 -ml-3" data-testid="mq-wizard-cancel">Back to quotations</Btn>
      <h2 className="text-2xl font-semibold pulse-font-heading mb-4" style={{ color: 'var(--theme-text)' }}>{group ? `Revise quotation group` : 'New MOD quotation'}</h2>
      <Stepper stage={stage} />
      {stage === 0 && <CustomerStage customer={customer} setCustomer={setCustomer} />}
      {stage === 1 && (
        <EquipmentStage customer={customer} rows={rows} setRows={setRows} catalogue={catalogue} options={options}>
          <div className="grid md:grid-cols-3 gap-4" data-testid="mq-options">{['A', 'B', 'AB'].map((t) => <OptionCard key={t} t={t} on={options.includes(t)} toggle={() => toggle(t)} preview={preview?.[t]} />)}</div>
          {options.includes('B') && (
            <label className="inline-flex items-center gap-2 text-sm">
              <span style={muted}>Type B call-outs</span>
              <input type="number" min={0} value={calloutQty} onChange={(e) => setCalloutQty(Math.max(0, parseInt(e.target.value || '0', 10)))}
                className="w-16 rounded px-2 py-1" style={inputStyle} data-testid="mq-callout-qty" />
            </label>
          )}
        </EquipmentStage>
      )}
      {stage === 2 && <ReviewStage preview={preview} />}
      <div className="mq-footer flex flex-wrap items-center justify-between gap-3" data-testid="mq-wizard-footer">
        <Btn icon={ArrowLeft} disabled={stage === 0} onClick={() => setStage(stage - 1)} data-testid="mq-wizard-back">Back</Btn>
        <div className="text-xs mq-muted text-center flex-1 min-w-0 hidden sm:block" data-testid="mq-wizard-summary">
          {customer?.name || 'No site selected'} · {rows.length} item(s) · {options.map((o) => TYPE_LABEL[o]).join(', ') || 'no options'}
          {stage < 2 && !canNext ? <span style={{ color: 'var(--color-warning)' }}> · {['Select a MOD site', !options.length ? 'Choose at least one quote type' : 'Add equipment and confirm every item code'][stage]}</span> : null}
        </div>
        {stage < 2 ? (
          <Btn variant="primary" disabled={!canNext} onClick={() => setStage(stage + 1)} data-testid="mq-wizard-next">Next <ArrowRight size={15} /></Btn>
        ) : (
          <Btn icon={Save} variant="primary" loading={saving} onClick={save} data-testid="mq-generate">{group ? 'Save revision' : 'Generate quotations (saved as drafts)'}</Btn>
        )}
      </div>
    </div>
  );
}
