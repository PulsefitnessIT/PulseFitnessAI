import { useCallback, useEffect, useState } from 'react';
import { Plus, Search, FileCheck2, ListChecks, Tags, Download, Upload } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, gbp, downloadBlob, TYPE_LABEL, card, muted, inputStyle, primaryBtn } from './modQuotesApi';
import ModQuoteWizard from './ModQuoteWizard';
import ModQuoteGroup, { StatusChip } from './ModQuoteGroup';

const FILTERS = [
  ['', 'All'], ['draft', 'Drafts'], ['pending_approval', 'Awaiting approval'], ['approved', 'Approved'],
  ['published', 'Published'], ['customer_review', 'Customer reviewing'], ['authorisation_submitted', 'Authorisation submitted'],
  ['accepted', 'Accepted'], ['handed_over', 'Handed over'], ['historical', 'Historical'],
];

function GroupList({ onOpen, onNew }) {
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [data, setData] = useState({ groups: [], counts: {} });
  useEffect(() => {
    const t = setTimeout(() => mq.get('/groups', { params: { status, q } }).then((r) => setData(r.data)).catch((e) => notify.error(errText(e))), 200);
    return () => clearTimeout(t);
  }, [status, q]);
  return (
    <div data-testid="mq-list">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-full px-3 py-2 flex-1 min-w-[220px] max-w-md" style={inputStyle}>
          <Search size={16} style={muted} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer or reference" className="flex-1 bg-transparent outline-none text-sm" data-testid="mq-search" />
        </div>
        <button type="button" onClick={onNew} data-testid="mq-new-quotation" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-semibold ml-auto" style={primaryBtn}><Plus size={16} /> New Quotation</button>
      </div>
      <div className="flex flex-wrap gap-2 mt-4" data-testid="mq-filters">
        {FILTERS.map(([k, l]) => (
          <button key={k || 'all'} type="button" onClick={() => setStatus(k)} data-testid={`mq-filter-${k || 'all'}`}
            className="px-3 py-1.5 rounded-full text-xs font-semibold" style={status === k ? primaryBtn : { ...card, color: 'var(--theme-text-muted)' }}>
            {l}{k && data.counts[k] ? ` · ${data.counts[k]}` : ''}
          </button>
        ))}
      </div>
      <div className="mt-4 rounded-xl overflow-x-auto" style={card}>
        <table className="w-full text-sm">
          <thead><tr className="text-left" style={muted}><th className="p-3">Customer / site</th><th className="p-3">Options</th><th className="p-3">Created</th><th className="p-3">Creator</th><th className="p-3">Status</th></tr></thead>
          <tbody>
            {data.groups.map((g) => (
              <tr key={g.id} onClick={() => onOpen(g.id)} className="border-t cursor-pointer transition-colors hover:opacity-80" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mq-group-row-${g.id}`}>
                <td className="p-3 font-semibold">{g.customer?.name}<div className="text-xs font-normal" style={muted}>Revision {g.revision}</div></td>
                <td className="p-3">{g.quotes.map((x) => <div key={x.id} className="text-xs"><span className="font-semibold">{TYPE_LABEL[x.mod_quote_type]}</span> {x.quote_number} · net {gbp(x.subtotal)}</div>)}</td>
                <td className="p-3 text-xs" style={muted}>{new Date(g.created_at).toLocaleDateString('en-GB')}</td>
                <td className="p-3 text-xs">{g.created_by_name}</td>
                <td className="p-3"><StatusChip status={g.status} /></td>
              </tr>
            ))}
            {!data.groups.length && <tr><td colSpan={5} className="p-10 text-center" style={muted}>No quotations here yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Authorisations({ caps, onOpen }) {
  const [items, setItems] = useState([]);
  const [notes, setNotes] = useState({});
  const load = useCallback(() => mq.get('/authorisations', { params: { status: 'submitted' } }).then((r) => setItems(r.data.items)).catch((e) => notify.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);
  const verify = async (a, accept) => {
    if (accept && !window.confirm(`Accept ${a.quote_number} for ${a.site_name}? This hands the coverage to MOD Service Operations.`)) return;
    try { await mq.post(`/authorisations/${a.id}/verify`, { accept, notes: notes[a.id] || '' }); notify.success(accept ? 'Accepted and handed to Operations' : 'Returned to customer'); load(); } catch (e) { notify.error(errText(e)); }
  };
  return (
    <div className="space-y-3" data-testid="mq-auth-queue">
      {items.map((a) => (
        <div key={a.id} className="rounded-xl p-4" style={card} data-testid={`mq-auth-${a.id}`}>
          <div className="flex flex-wrap justify-between gap-2">
            <button type="button" className="font-semibold text-left" onClick={() => onOpen(a.group_id)}>{a.site_name} — {TYPE_LABEL[a.quote_type]} {a.quote_number} (v{a.quote_version})</button>
            <span className="text-xs" style={muted}>Submitted {new Date(a.submitted_at).toLocaleString('en-GB')} by {a.submitted_by_name}</span>
          </div>
          <div className="text-sm mt-1">PO {a.po_reference || '—'} · Authorised by {a.authorising_officer} on {a.authorisation_date}</div>
          {a.notes && <div className="text-sm mt-1" style={muted}>{a.notes}</div>}
          {a.evidence_path && <button type="button" className="text-sm mt-1 inline-flex items-center gap-1" style={{ color: 'var(--color-brand-cyan)' }} data-testid="mq-auth-evidence"
            onClick={() => downloadBlob(`/authorisations/${a.id}/evidence`, a.evidence_filename).catch((e) => notify.error(errText(e)))}><Download size={14} /> {a.evidence_filename}</button>}
          {caps.manager ? (
            <div className="flex flex-wrap gap-2 mt-3">
              <input value={notes[a.id] || ''} onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })} placeholder="Evidence checked / notes"
                className="flex-1 min-w-[200px] rounded-lg px-3 py-1.5 text-sm" style={inputStyle} data-testid="mq-auth-notes" />
              <button type="button" onClick={() => verify(a, true)} className="px-4 py-1.5 rounded-full text-sm font-semibold" style={primaryBtn} data-testid="mq-auth-accept">Verify & accept</button>
              <button type="button" onClick={() => verify(a, false)} className="px-4 py-1.5 rounded-full text-sm font-semibold" style={card} data-testid="mq-auth-reject">Not sufficient</button>
            </div>
          ) : <div className="text-xs mt-2" style={muted}>A MOD Sales Manager must verify this authorisation.</div>}
        </div>
      ))}
      {!items.length && <div className="rounded-xl p-10 text-center" style={{ ...card, color: 'var(--theme-text-muted)' }}>No customer authorisations awaiting review.</div>}
    </div>
  );
}

function Handovers({ caps, onOpen }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(null);
  const [start, setStart] = useState('');
  const load = useCallback(() => mq.get('/handovers').then((r) => setItems(r.data.items)).catch((e) => notify.error(errText(e))), []);
  useEffect(() => { load(); }, [load]);
  const show = (id) => mq.get(`/handovers/${id}`).then((r) => { setOpen(r.data); setStart(r.data.start_date || ''); }).catch((e) => notify.error(errText(e)));
  const setup = async () => {
    if (!start) { notify.error('Enter the contract commencement date'); return; }
    if (!window.confirm('Create the service records for this accepted quotation? The annual visit is proposed, not booked.')) return;
    try { await mq.post(`/handovers/${open.id}/setup`, { start_date: start }); notify.success('Service records created'); show(open.id); load(); } catch (e) { notify.error(errText(e)); }
  };
  return (
    <div className="grid lg:grid-cols-[1fr_1.4fr] gap-4" data-testid="mq-handovers">
      <div className="rounded-xl overflow-hidden" style={card}>
        {items.map((h) => (
          <button key={h.id} type="button" onClick={() => show(h.id)} className="w-full text-left p-3 border-b transition-opacity hover:opacity-80" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mq-handover-${h.id}`}>
            <div className="font-semibold text-sm">{h.mod_site_name} — {TYPE_LABEL[h.quote_type]} {h.source_quote_number}</div>
            <div className="text-xs" style={muted}>{h.status === 'setup_complete' ? 'Set up' : 'Awaiting Operations set-up'} · annual {gbp(h.annual_type_a_value)} · one-off {gbp(h.one_off_type_b_value)}</div>
          </button>
        ))}
        {!items.length && <div className="p-8 text-center text-sm" style={muted}>No accepted quotations yet.</div>}
      </div>
      {open && (
        <div className="rounded-xl p-4 space-y-3" style={card} data-testid="mq-handover-detail">
          <div className="flex justify-between gap-2"><div className="font-semibold">{open.mod_site_name}</div>
            <button type="button" className="text-xs" style={{ color: 'var(--color-brand-cyan)' }} onClick={() => onOpen(open.group_id)} data-testid="mq-handover-open-group">Open quotation</button></div>
          <div className="text-sm">{TYPE_LABEL[open.quote_type]} · {open.source_quote_number} · PO {open.authorisation?.po_reference || '—'} · authorised by {open.authorisation?.authorising_officer || '—'}</div>
          <div className="grid sm:grid-cols-2 gap-2 text-sm">
            <div>Annual Type A value <b>{gbp(open.annual_type_a_value)}</b></div><div>One-off Type B value <b>{gbp(open.one_off_type_b_value)}</b></div>
          </div>
          <table className="w-full text-xs"><thead><tr style={muted} className="text-left"><th>Cover</th><th>Item</th><th>Qty</th><th className="text-right">Total</th></tr></thead>
            <tbody>{open.coverage.map((c2, i) => <tr key={`${c2.item_code}-${i}`} className="border-t" style={{ borderColor: 'var(--theme-border)' }}><td>{c2.coverage}{c2.annual_obligation ? ' · annual' : ' · one-off'}</td><td>{c2.description}</td><td>{c2.qty}</td><td className="text-right">{c2.total.toFixed(2)}</td></tr>)}</tbody></table>
          {open.outstanding.length > 0 && <div className="text-xs" style={{ color: 'var(--color-warning)' }} data-testid="mq-handover-outstanding">Outstanding: {open.outstanding.join('; ')}</div>}
          {open.status === 'setup_complete' ? (
            <div className="text-sm" data-testid="mq-handover-done">Set up by {open.setup_by}: {(open.service_records || []).map((r) => `Type ${r.contract_type} (${r.status.replace(/_/g, ' ')})`).join(', ')}</div>
          ) : caps.manager ? (
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm" style={muted}>Commencement <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded px-2 py-1 ml-1" style={inputStyle} data-testid="mq-handover-start" /></label>
              <button type="button" onClick={setup} className="px-4 py-1.5 rounded-full text-sm font-semibold" style={primaryBtn} data-testid="mq-handover-setup">Set up service records</button>
            </div>
          ) : <div className="text-xs" style={muted}>A MOD Sales Manager completes set-up.</div>}
        </div>
      )}
    </div>
  );
}

function Pricing() {
  const [preview, setPreview] = useState(null);
  const [lists, setLists] = useState([]);
  const [eff, setEff] = useState(new Date().toISOString().slice(0, 10));
  const loadLists = useCallback(() => mq.get('/rates/price-lists').then((r) => setLists(r.data.items)).catch(() => {}), []);
  useEffect(() => { loadLists(); }, [loadLists]);
  const upload = async (f) => {
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f);
    try { setPreview((await mq.post('/rates/import-preview', fd)).data); } catch (e) { notify.error(errText(e)); }
  };
  const approve = async () => {
    if (!window.confirm(`Replace the live Schedule of Rates from ${eff}? Existing quotations keep their pricing snapshot.`)) return;
    try { await mq.post(`/rates/${preview.price_list_id}/approve`, { effective_from: eff, confirm: true }); notify.success('Schedule of Rates is now live'); setPreview(null); loadLists(); } catch (e) { notify.error(errText(e)); }
  };
  return (
    <div className="space-y-4" data-testid="mq-pricing">
      <label className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold cursor-pointer" style={card}>
        <Upload size={14} /> Import Schedule B workbook
        <input type="file" accept=".xlsx" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="mq-sor-upload" />
      </label>
      {preview && (
        <div className="rounded-xl p-4" style={card}>
          {preview.issues.length > 0 && (
            <ul className="text-sm mb-3 space-y-1" data-testid="mq-sor-issues">
              {preview.issues.map((i) => <li key={i.message} style={{ color: 'var(--color-warning)' }}>{i.message}</li>)}
            </ul>
          )}
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-xs">
              <thead><tr className="text-left" style={muted}><th className="p-1">ID</th><th className="p-1">Item</th><th className="p-1">Sage code</th><th className="p-1">Schedule B ref</th><th className="p-1 text-right">Current</th><th className="p-1 text-right">New</th><th className="p-1">Change</th></tr></thead>
              <tbody>{preview.rows.map((r) => (
                <tr key={r.uid} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                  <td className="p-1">{r.uid}</td><td className="p-1">{r.name}</td><td className="p-1">{r.sage_code}{r.ambiguous_sage_code ? ' ⚠' : ''}</td><td className="p-1">{r.tl_ref}</td>
                  <td className="p-1 text-right">{r.current_price ?? '—'}</td><td className="p-1 text-right">{r.is_poa ? 'POA' : r.price}</td><td className="p-1">{r.change}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <span className="text-sm" style={muted}>Effective from</span>
            <input type="date" value={eff} onChange={(e) => setEff(e.target.value)} className="rounded px-2 py-1 text-sm" style={inputStyle} data-testid="mq-sor-effective" />
            <button type="button" onClick={approve} className="px-4 py-1.5 rounded-full text-sm font-semibold" style={primaryBtn} data-testid="mq-sor-approve">Approve & make live</button>
          </div>
        </div>
      )}
      <div className="rounded-xl p-4" style={card}>
        <div className="font-semibold mb-2">Price list history</div>
        <ul className="text-sm space-y-1">{lists.map((l) => <li key={l.id}>{l.filename} · {l.status}{l.version ? ` · ${l.version}` : ''} <span style={muted}>· {l.uploaded_by}</span></li>)}</ul>
      </div>
    </div>
  );
}

export default function ModQuotations() {
  const [tab, setTab] = useState('quotes');
  const [mode, setMode] = useState(() => {
    const gid = new URLSearchParams(window.location.search).get('quote_group');
    return gid ? { view: 'group', id: gid } : { view: 'list' };
  });
  const [caps, setCaps] = useState({ manager: false, pricing: false });
  useEffect(() => { mq.get('/me').then((r) => setCaps(r.data)).catch(() => {}); }, []);

  if (mode.view === 'wizard') {
    return <ModQuoteWizard group={mode.group} onCancel={() => setMode(mode.group ? { view: 'group', id: mode.group.id } : { view: 'list' })}
      onDone={(g) => setMode({ view: 'group', id: g.id })} />;
  }
  if (mode.view === 'group') {
    return <ModQuoteGroup key={mode.id} groupId={mode.id} caps={caps} onBack={() => setMode({ view: 'list' })}
      onEdit={() => mq.get(`/groups/${mode.id}`).then((r) => setMode({ view: 'wizard', group: r.data }))} />;
  }
  const tabs = [['quotes', 'Quotations', ListChecks], ['auth', 'Customer authorisations', FileCheck2], ['handover', 'Service handover', ListChecks], ...(caps.pricing ? [['pricing', 'Schedule of Rates', Tags]] : [])];
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6" data-testid="mod-quotations">
      <div className="flex flex-wrap gap-2 mb-5">
        {tabs.map(([k, l, Icon]) => (
          <button key={k} type="button" onClick={() => setTab(k)} data-testid={`mq-tab-${k}`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold" style={tab === k ? { ...card, outline: '2px solid var(--color-brand-cyan)' } : { ...card, color: 'var(--theme-text-muted)' }}>
            <Icon size={14} /> {l}
          </button>
        ))}
      </div>
      {tab === 'quotes' && <GroupList onOpen={(id) => setMode({ view: 'group', id })} onNew={() => setMode({ view: 'wizard' })} />}
      {tab === 'auth' && <Authorisations caps={caps} onOpen={(id) => setMode({ view: 'group', id })} />}
      {tab === 'handover' && <Handovers caps={caps} onOpen={(id) => setMode({ view: 'group', id })} />}
      {tab === 'pricing' && <Pricing />}
    </div>
  );
}
