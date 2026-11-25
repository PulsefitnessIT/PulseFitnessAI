import { useCallback, useEffect, useState } from 'react';
import { Plus, Search, FileCheck2, ListChecks, Tags, Download, Upload, FileText, Truck, AlertTriangle, ShieldCheck, ShieldAlert, PhoneCall, CheckCircle2, Mail } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, gbp, downloadBlob, TYPE_LABEL } from './modQuotesApi';
import { Btn, StatusChip, Banner, Empty, Skeleton, Field } from './MqUi';
import ModQuoteWizard from './ModQuoteWizard';
import ModQuoteGroup from './ModQuoteGroup';
import FollowupEmailWording from './FollowupEmailWording';

const FILTERS = [
  ['', 'All'], ['draft', 'Drafts'], ['pending_approval', 'Awaiting approval'], ['approved', 'Approved'],
  ['published', 'Published'], ['customer_review', 'Customer reviewing'], ['authorisation_submitted', 'Authorisation submitted'],
  ['accepted', 'Accepted'], ['handed_over', 'Handed over'], ['historical', 'Historical'],
];
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-GB') : '—');

function GroupRow({ g, onOpen }) {
  const valid = g.quotes.map((x) => x.valid_until).filter(Boolean).sort()[0];
  return (
    <tr className="mq-row" tabIndex={0} onClick={() => onOpen(g.id)} onKeyDown={(e) => e.key === 'Enter' && onOpen(g.id)} data-testid={`mq-group-row-${g.id}`}>
      <td><div className="font-semibold">{g.customer?.name}</div><div className="text-xs mq-muted">Revision {g.revision}</div></td>
      <td>
        {g.quotes.map((x) => (
          <div key={x.id} className="text-xs flex flex-wrap gap-x-2 leading-5">
            <span className="font-semibold w-24">{TYPE_LABEL[x.mod_quote_type]}</span>
            <span className="mq-muted">{x.sage_quote_number || x.quote_number}</span>
            <span className="mq-num">net {gbp(x.subtotal)}</span>
          </div>
        ))}
      </td>
      <td className="text-xs whitespace-nowrap">{fmtDate(g.created_at)}<div className="mq-muted">{g.created_by_name}</div></td>
      <td className="text-xs whitespace-nowrap">{valid ? fmtDate(valid) : <span className="mq-muted">On publication</span>}</td>
      <td><StatusChip status={g.status} /></td>
    </tr>
  );
}

function GroupList({ onOpen, onNew }) {
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [data, setData] = useState(null);
  useEffect(() => {
    const t = setTimeout(() => mq.get('/groups', { params: { status, q } }).then((r) => setData(r.data)).catch((e) => { notify.error(errText(e)); setData({ groups: [], counts: {} }); }), 200);
    return () => clearTimeout(t);
  }, [status, q]);
  const counts = data?.counts || {};
  return (
    <div data-testid="mq-list">
      <div className="flex flex-wrap items-center gap-3">
        <label className="mq-input flex items-center gap-2 rounded-full px-4 h-10 flex-1 min-w-[220px] max-w-md">
          <Search size={16} className="mq-muted" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer, site or reference" aria-label="Search quotations"
            className="flex-1 bg-transparent outline-none text-sm" data-testid="mq-search" />
        </label>
        <Btn icon={Plus} variant="primary" onClick={onNew} className="ml-auto" data-testid="mq-new-quotation">New quotation</Btn>
      </div>
      <div className="flex gap-2 mt-4 overflow-x-auto pb-1" data-testid="mq-filters" role="group" aria-label="Filter by status">
        {FILTERS.map(([k, l]) => (
          <button key={k || 'all'} type="button" onClick={() => setStatus(k)} aria-pressed={status === k} className="mq-chip-btn" data-testid={`mq-filter-${k || 'all'}`}>
            {l}{k && counts[k] ? ` · ${counts[k]}` : ''}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {!data ? <Skeleton rows={4} /> : !data.groups.length ? (
          <Empty icon={FileText} testid="mq-list-empty" title={q || status ? 'No quotations match' : 'No MOD quotations yet'}
            sub={q || status ? 'Try another search or status filter.' : 'Start a quotation from a MOD site and its equipment register — Type A, Type B and Mix options are prepared together.'}
            action={!q && !status && <Btn icon={Plus} variant="primary" onClick={onNew} data-testid="mq-empty-new">New quotation</Btn>} />
        ) : (
          <div className="mq-card overflow-x-auto">
            <table className="mq-table">
              <thead><tr><th>Customer / site</th><th>Options</th><th>Created</th><th>Valid until</th><th>Status</th></tr></thead>
              <tbody>{data.groups.map((g) => <GroupRow key={g.id} g={g} onOpen={onOpen} />)}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AuthCard({ a, caps, onOpen, onDone }) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const verify = async (accept) => {
    if (accept && !window.confirm(`Accept ${a.quote_number} for ${a.site_name}? This hands the coverage to MOD Service Operations.`)) return;
    setBusy(true);
    try { await mq.post(`/authorisations/${a.id}/verify`, { accept, notes }); notify.success(accept ? 'Accepted and handed to Operations' : 'Returned to customer'); onDone(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mq-card p-5" data-testid={`mq-auth-${a.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button type="button" className="font-semibold text-left hover:underline" onClick={() => onOpen(a.group_id)} data-testid="mq-auth-open">{a.site_name}</button>
          <div className="text-xs mq-muted mt-0.5">Submitted {new Date(a.submitted_at).toLocaleString('en-GB')} by {a.submitted_by_name}</div>
        </div>
        <StatusChip status="submitted" label="Awaiting review" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
        <Field label="Quotation">{a.quote_number} (v{a.quote_version})</Field>
        <Field label="Selected option">{TYPE_LABEL[a.quote_type]}</Field>
        <Field label="Purchase order">{a.po_reference || '—'}</Field>
        <Field label="Authorised by">{a.authorising_officer} · {a.authorisation_date}</Field>
      </div>
      {a.notes && <div className="text-sm mt-3 mq-muted">“{a.notes}”</div>}
      <div className="mt-3">
        {a.evidence_path ? (
          <Btn icon={Download} size="sm" data-testid="mq-auth-evidence" onClick={() => downloadBlob(`/authorisations/${a.id}/evidence`, a.evidence_filename).catch((e) => notify.error(errText(e)))}>{a.evidence_filename}</Btn>
        ) : <span className="text-xs" style={{ color: 'var(--color-warning)' }}>No supporting evidence attached</span>}
      </div>
      {caps.manager ? (
        <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Evidence checked / notes" aria-label="Review notes"
            className="mq-input flex-1 min-w-[200px] h-10 px-3 text-sm" data-testid="mq-auth-notes" />
          <Btn variant="danger" loading={busy} onClick={() => verify(false)} data-testid="mq-auth-reject">Not sufficient</Btn>
          <Btn icon={ShieldCheck} variant="primary" loading={busy} onClick={() => verify(true)} data-testid="mq-auth-accept">Verify &amp; accept</Btn>
        </div>
      ) : <div className="text-xs mt-4 mq-muted" data-testid="mq-auth-manager-only">Only a MOD Sales Manager can verify this authorisation.</div>}
    </div>
  );
}

function Authorisations({ caps, onOpen }) {
  const [items, setItems] = useState(null);
  const load = useCallback(() => mq.get('/authorisations', { params: { status: 'submitted' } }).then((r) => setItems(r.data.items)).catch((e) => { notify.error(errText(e)); setItems([]); }), []);
  useEffect(() => { load(); }, [load]);
  if (!items) return <Skeleton />;
  return (
    <div className="space-y-3" data-testid="mq-auth-queue">
      {items.map((a) => <AuthCard key={a.id} a={a} caps={caps} onOpen={onOpen} onDone={load} />)}
      {!items.length && <Empty icon={FileCheck2} testid="mq-auth-empty" title="No authorisations awaiting review" sub="When a MOD customer authorises a published quotation in MODService it appears here for manager verification." />}
    </div>
  );
}

const coverKind = (h) => (h.quote_type === 'AB' ? 'Mixed coverage' : h.quote_type === 'A' ? 'Type A annual coverage' : 'Type B one-off service');

function HandoverDetail({ open, caps, onOpen, onSaved }) {
  const [start, setStart] = useState(open.start_date || '');
  const [busy, setBusy] = useState(false);
  const setup = async () => {
    if (!start) { notify.error('Enter the contract commencement date'); return; }
    if (!window.confirm('Create the service records for this accepted quotation? The annual visit is proposed, not booked.')) return;
    setBusy(true);
    try { await mq.post(`/handovers/${open.id}/setup`, { start_date: start }); notify.success('Service records created'); onSaved(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mq-card p-5 space-y-4" data-testid="mq-handover-detail">
      <div className="flex flex-wrap justify-between gap-2">
        <div><div className="font-semibold text-lg">{open.mod_site_name}</div><div className="text-sm mq-muted">{coverKind(open)}</div></div>
        <Btn size="sm" variant="ghost" icon={FileText} onClick={() => onOpen(open.group_id)} data-testid="mq-handover-open-group">Open quotation</Btn>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Field label="Quotation">{TYPE_LABEL[open.quote_type]} · {open.source_quote_number}</Field>
        <Field label="Purchase order">{open.authorisation?.po_reference || '—'}</Field>
        <Field label="Annual Type A">{gbp(open.annual_type_a_value)}</Field>
        <Field label="One-off Type B">{gbp(open.one_off_type_b_value)}</Field>
      </div>
      <div className="overflow-x-auto">
        <table className="mq-table mq-table--dense text-xs">
          <thead><tr><th>Cover</th><th>Item</th><th className="mq-num">Qty</th><th className="mq-num">Total</th></tr></thead>
          <tbody>{open.coverage.map((c2, i) => (
            <tr key={`${c2.item_code}-${i}`}>
              <td><StatusChip status={c2.annual_obligation ? 'accepted' : 'customer_review'} label={`Type ${c2.coverage} · ${c2.annual_obligation ? 'annual' : 'one-off'}`} /></td>
              <td>{c2.description}</td><td className="mq-num">{c2.qty}</td><td className="mq-num">{gbp(c2.total)}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {open.outstanding.length > 0 && <Banner icon={AlertTriangle} testid="mq-handover-outstanding"><b>Missing set-up information:</b> {open.outstanding.join('; ')}</Banner>}
      {open.status === 'setup_complete' ? (
        <Banner tone="ok" icon={ShieldCheck} testid="mq-handover-done">Set up by {open.setup_by}: {(open.service_records || []).map((r) => `Type ${r.contract_type} (${r.status.replace(/_/g, ' ')})`).join(', ')}</Banner>
      ) : caps.manager ? (
        <div className="flex flex-wrap items-end gap-3 pt-4 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          <label className="text-sm"><span className="mq-label block mb-1">Commencement date</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="mq-input h-10 px-3" data-testid="mq-handover-start" /></label>
          <Btn variant="primary" icon={Truck} loading={busy} onClick={setup} data-testid="mq-handover-setup">Set up service records</Btn>
        </div>
      ) : <div className="text-xs mq-muted">A MOD Sales Manager completes set-up.</div>}
    </div>
  );
}

function Handovers({ caps, onOpen }) {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => mq.get('/handovers').then((r) => setItems(r.data.items)).catch((e) => { notify.error(errText(e)); setItems([]); }), []);
  useEffect(() => { load(); }, [load]);
  const show = (id) => mq.get(`/handovers/${id}`).then((r) => setOpen(r.data)).catch((e) => notify.error(errText(e)));
  if (!items) return <Skeleton />;
  if (!items.length) return <Empty icon={Truck} testid="mq-handovers" title="No accepted quotations yet" sub="Accepted quotations are handed to MOD Service Operations here for contract set-up." />;
  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)] gap-4 items-start" data-testid="mq-handovers">
      <div className="mq-card overflow-hidden">
        {items.map((h) => (
          <button key={h.id} type="button" onClick={() => show(h.id)} aria-current={open?.id === h.id}
            className="mq-row w-full text-left p-4 border-b last:border-b-0 block" style={{ borderColor: 'var(--theme-border)', background: open?.id === h.id ? 'var(--theme-hover-bg)' : undefined }} data-testid={`mq-handover-${h.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="font-semibold text-sm">{h.mod_site_name}</div>
              <StatusChip status={h.status === 'setup_complete' ? 'setup_complete' : 'awaiting_setup'} label={h.status === 'setup_complete' ? 'Set up' : 'Awaiting set-up'} />
            </div>
            <div className="text-xs mq-muted mt-1">{coverKind(h)} · {h.source_quote_number}</div>
            <div className="text-xs mt-1">Annual {gbp(h.annual_type_a_value)} · one-off {gbp(h.one_off_type_b_value)}</div>
          </button>
        ))}
      </div>
      {open ? <HandoverDetail key={open.id + open.status} open={open} caps={caps} onOpen={onOpen} onSaved={() => { show(open.id); load(); }} />
        : <div className="mq-card p-8 text-center text-sm mq-muted">Select an accepted quotation to review its hand-over.</div>}
    </div>
  );
}

const EMAIL_STATE = {
  sent: ['ok', 'Customer email sent with PDFs'], awaiting_approval: ['warn', 'Customer email not sent — held for manager review'],
  ready: ['warn', 'Customer email queued to send'], sending: ['warn', 'Customer email sending'],
  failed: ['bad', 'Customer email failed'], not_applicable: ['neutral', 'No customer email for this follow-up'],
  cancelled: ['neutral', 'Customer email cancelled'],
};

function FollowupCard({ f, caps, onOpen, onDone }) {
  const [outcome, setOutcome] = useState('');
  const [busy, setBusy] = useState(false);
  const [tone, label] = EMAIL_STATE[f.email_status] || ['neutral', f.email_status || '—'];
  const decide = async (action) => {
    setBusy(true);
    try { await mq.post(`/followups/${f.id}/email`, { action }); notify.success(action === 'release' ? 'Customer email released for sending' : 'Customer email cancelled'); onDone(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const overdue = f.due < new Date().toISOString().slice(0, 10);
  const save = async () => {
    setBusy(true);
    try { await mq.post(`/followups/${f.id}/done`, { outcome }); notify.success('Follow-up recorded'); onDone(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mq-card p-5" data-testid={`mq-followup-${f.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button type="button" className="font-semibold text-left hover:underline" onClick={() => onOpen(f.group_id)} data-testid="mq-followup-open">{f.customer_name}</button>
          <div className="text-xs mq-muted mt-0.5">Follow-up {f.chase_no} of 3 · {f.weeks} weeks after publication · due {new Date(f.due).toLocaleDateString('en-GB')}</div>
        </div>
        <StatusChip status={overdue ? 'expired' : 'pending_approval'} label={overdue ? 'Overdue' : 'Due'} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
        <Field label="Quotation">{(f.quote_refs || []).join(', ') || '—'}</Field>
        <Field label="Contact">{f.contact_name || '—'}</Field>
        <Field label="Email">{f.contact_email || '—'}</Field>
        <Field label="Owner">{f.assigned_name || '—'}</Field>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="mq-followup-email-status">
        <StatusChip status={tone === 'ok' ? 'accepted' : tone === 'bad' ? 'declined' : tone === 'warn' ? 'pending_approval' : 'draft'} label={label} />
        {f.email_sent_at && <span className="text-xs mq-muted">sent {new Date(f.email_sent_at).toLocaleString('en-GB')} to {f.contact_email}</span>}
        {f.email_reason && f.email_status !== 'sent' && <span className="text-xs mq-muted">{f.email_reason}</span>}
        {caps?.manager && ['awaiting_approval', 'failed'].includes(f.email_status) && (
          <>
            <Btn size="sm" disabled={busy} onClick={() => decide('release')} data-testid="mq-followup-release">Release email</Btn>
            <Btn size="sm" variant="ghost" disabled={busy} onClick={() => decide('cancel')} data-testid="mq-followup-cancel-email">Don't send</Btn>
          </>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t" style={{ borderColor: 'var(--theme-border)' }}>
        <input value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="What happened? e.g. Spoke to Sgt Smith — PO expected next week" aria-label="Chase outcome"
          className="mq-input flex-1 min-w-[220px] h-10 px-3 text-sm" data-testid="mq-followup-outcome" />
        <Btn icon={CheckCircle2} variant="primary" loading={busy} disabled={outcome.trim().length < 3} onClick={save} data-testid="mq-followup-done">Record &amp; close</Btn>
      </div>
    </div>
  );
}

function Followups({ caps, onOpen }) {
  const [items, setItems] = useState(null);
  const [everyone, setEveryone] = useState(false);
  const [running, setRunning] = useState(false);
  const load = useCallback(() => mq.get('/followups', { params: { everyone } }).then((r) => setItems(r.data.items)).catch((e) => { notify.error(errText(e)); setItems([]); }), [everyone]);
  useEffect(() => { load(); }, [load]);
  const runNow = async () => {
    setRunning(true);
    try { const r = await mq.post('/followups/run'); notify.success(`${r.data.processed} follow-up(s) raised${r.data.live_email ? ` · ${r.data.emails_sent} customer email(s) sent` : ' — customer emails are switched off, nothing was sent'}`); if (r.data.processed) setEveryone(true); load(); } catch (e) { notify.error(errText(e)); } finally { setRunning(false); }
  };
  return (
    <div className="space-y-3" data-testid="mq-followups">
      <FollowupEmailWording />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1" />
        {caps.manager && (
          <>
            <button type="button" className="mq-chip-btn" aria-pressed={everyone} onClick={() => setEveryone(!everyone)} data-testid="mq-followups-everyone">Everyone's follow-ups</button>
            <Btn icon={PhoneCall} size="sm" loading={running} onClick={runNow} data-testid="mq-followups-run">Check for due follow-ups now</Btn>
          </>
        )}
      </div>
      {!items ? <Skeleton /> : items.map((f) => <FollowupCard key={f.id} f={f} caps={caps} onOpen={onOpen} onDone={load} />)}
      {items && !items.length && <Empty icon={Mail} testid="mq-followups-empty" title="No follow-ups due" sub="Follow-ups appear here 2, 4 and 6 weeks after a quotation is published, until it is authorised, accepted or withdrawn." />}
    </div>
  );
}

const RATE_LABEL = { 'n/a': 'Not applicable', verified: 'Approved', unverified: 'Not approved', test_data: 'Test data', poa: 'POA', historical: 'Historical — confirm', expired: 'Expired', placeholder: 'Placeholder' };

function RateCell({ r }) {
  return (
    <td>
      <div className="mq-num font-semibold">{r.status === 'poa' ? 'POA' : r.price == null ? '—' : gbp(r.price)}</div>
      <div className="text-xs mq-muted">{[r.sage_code, r.code].filter(Boolean).join(' · ') || '—'}</div>
      <div className="mt-1"><StatusChip status={r.status} label={RATE_LABEL[r.status]} /></div>
    </td>
  );
}

function CurrentRates({ data, master }) {
  const live = data.live_price_list;
  const s = data.summary || {};
  return (
    <div className="space-y-3" data-testid="mq-sor-current">
      {data.customer_ready ? (
        <Banner tone="ok" icon={ShieldCheck} testid="mq-sor-ready">Approved Schedule of Rates in use · effective {live.effective_from ? new Date(live.effective_from).toLocaleDateString('en-GB') : '—'}{master && live.version ? ` · ${live.version} · approved by ${live.approved_by}` : ''}.</Banner>
      ) : (
        <Banner tone="bad" icon={ShieldAlert} testid="mq-sor-not-approved">
          <b>Not an approved live price list.</b> {live ? (live.synthetic ? 'The current list is test data.' : '') : 'No Schedule of Rates is live.'}{' '}
          {s.test_data ? `${s.test_data} rate(s) come from test data. ` : ''}{s.unverified ? `${s.unverified} rate(s) are not approved. ` : ''}{s.historical ? `${s.historical} rate(s) are historical only. ` : ''}
          Quotations can be drafted and compared internally, but publishing to customers is blocked until every line uses an approved rate or a manager-approved exception.
        </Banner>
      )}
      <div className="mq-card overflow-x-auto max-h-[32rem]">
        <table className="mq-table mq-table--dense">
          <thead><tr><th>Item</th><th>Equipment</th><th>Type A</th><th>Type B</th><th>Effective</th>{master && <th>Source</th>}</tr></thead>
          <tbody>{data.rows.map((r) => (
            <tr key={r.id} data-testid={`mq-sor-row-${r.item_no}`}>
              <td className="font-semibold">{r.item_no}</td><td>{r.label}{r.kind === 'call_out' ? <div className="text-xs mq-muted">Call-out</div> : null}</td>
              <RateCell r={r.a} /><RateCell r={r.b} />
              <td className="text-xs whitespace-nowrap">{fmtDate(r.a.effective_from || r.b.effective_from)}{(r.a.expires_on || r.b.expires_on) ? <div className="mq-muted">to {fmtDate(r.a.expires_on || r.b.expires_on)}</div> : null}</td>
              {master && <td className="text-xs mq-muted max-w-[16rem]">{r.a.source || r.b.source || '—'}{r.price_list_version ? <div>{r.price_list_version}</div> : null}</td>}
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

function Pricing({ master }) {
  const [preview, setPreview] = useState(null);
  const [lists, setLists] = useState([]);
  const [current, setCurrent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [eff, setEff] = useState(new Date().toISOString().slice(0, 10));
  const reload = useCallback(() => {
    if (master) mq.get('/rates/price-lists').then((r) => setLists(r.data.items)).catch(() => {});
    mq.get('/rates/current').then((r) => setCurrent(r.data)).catch((e) => notify.error(errText(e)));
  }, [master]);
  useEffect(() => { reload(); }, [reload]);
  const upload = async (f) => {
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f);
    setBusy(true);
    try { setPreview((await mq.post('/rates/import-preview', fd)).data); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const approve = async () => {
    if (!window.confirm(`Replace the live Schedule of Rates from ${eff}? Existing quotations keep their pricing snapshot.`)) return;
    setBusy(true);
    try { await mq.post(`/rates/${preview.price_list_id}/approve`, { effective_from: eff, confirm: true }); notify.success('Schedule of Rates is now live'); setPreview(null); reload(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6" data-testid="mq-pricing">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><div className="font-semibold">Current Schedule of Rates</div><div className="text-sm mq-muted">Type A and Type B are approved separately. Only approved rates can reach customers.</div></div>
        <label className="mq-btn cursor-pointer" data-testid="mq-sor-upload-label">
          {busy ? <span className="mq-spin" aria-hidden /> : <Upload size={15} aria-hidden />} Import price list workbook
          <input type="file" accept=".xlsx" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} data-testid="mq-sor-upload" />
        </label>
      </div>
      {preview && (
        <div className="mq-card p-5 space-y-3" data-testid="mq-sor-preview">
          <div className="font-semibold">Import preview — not live until approved{preview.price_year ? ` · using Year ${preview.price_year} prices` : ''}</div>
          {preview.synthetic && <Banner tone="bad" icon={ShieldAlert} testid="mq-sor-synthetic">This workbook is marked <b>SYNTHETIC TEST DATA</b>. It cannot replace the live Schedule of Rates.</Banner>}
          {preview.issues.length > 0 && (
            <Banner icon={AlertTriangle} testid="mq-sor-issues"><ul className="space-y-1">{preview.issues.map((i) => <li key={i.message}>{i.message}</li>)}</ul></Banner>
          )}
          <div className="overflow-x-auto max-h-96">
            <table className="mq-table mq-table--dense text-xs">
              <thead><tr>{master && <th>ID</th>}<th>Item</th><th>Sage code</th>{master && <th>Schedule B ref</th>}<th>Updates</th><th className="mq-num">Current</th><th className="mq-num">New</th><th>Change</th></tr></thead>
              <tbody>{preview.rows.map((r) => (
                <tr key={r.uid}>
                  {master && <td>{r.uid}</td>}<td>{r.name}{r.extended_description ? <div className="mq-muted">{r.extended_description}</div> : null}</td><td>{r.sage_code}{r.ambiguous_sage_code ? ' (shared)' : ''}</td>{master && <td>{r.tl_ref}</td>}<td className="mq-muted">{(r.matched || []).join(', ') || 'New rate-card entry'}</td>
                  <td className="mq-num">{r.current_price ?? '—'}</td><td className="mq-num">{r.is_poa ? 'POA' : r.price}</td>
                  <td><StatusChip status={r.change === 'changed' ? 'pending_approval' : r.change === 'new' ? 'approved' : 'draft'} label={r.change} /></td>
                </tr>))}</tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm"><span className="mq-label block mb-1">Effective from</span>
              <input type="date" value={eff} onChange={(e) => setEff(e.target.value)} className="mq-input h-10 px-3" data-testid="mq-sor-effective" /></label>
            <Btn variant="ghost" onClick={() => mq.delete(`/rates/${preview.price_list_id}`).catch(() => {}).finally(() => setPreview(null))} data-testid="mq-sor-discard">Discard</Btn>
            <Btn variant="primary" loading={busy} disabled={preview.synthetic} onClick={approve} data-testid="mq-sor-approve">Approve &amp; make live</Btn>
          </div>
        </div>
      )}
      {current ? <CurrentRates data={current} master={master} /> : <Skeleton rows={5} />}
      {master && <div className="mq-card p-5" data-testid="mq-sor-history">
        <div className="font-semibold mb-3">Price list history</div>
        <ul className="text-sm divide-y" style={{ borderColor: 'var(--theme-border)' }}>
          {lists.map((l) => (
            <li key={l.id} className="py-2 flex flex-wrap items-center gap-2" style={{ borderColor: 'var(--theme-border)' }}>
              <StatusChip status={l.status} /><span className="font-medium">{l.version || l.filename}</span>
              <span className="mq-muted text-xs">{l.filename} · uploaded by {l.uploaded_by}{l.effective_from ? ` · effective ${l.effective_from}` : ''}</span>
              {l.synthetic && <StatusChip status="test_data" label="Test data" />}
            </li>
          ))}
          {!lists.length && <li className="py-2 mq-muted">No Schedule B imports yet.</li>}
        </ul>
      </div>}
    </div>
  );
}

const SECTIONS = {
  quotes: ['All quotations', ListChecks, 'Prepare, approve and publish MOD service quotations.'],
  auth: ['Customer authorisations', FileCheck2, 'Customer purchase-order authorisations awaiting manager verification.'],
  followups: ['Follow-ups', PhoneCall, 'Each published quotation is chased 2, 4 and 6 weeks after publication. The quote owner gets a reminder here, and once the wording below is approved and sending is switched on, the customer is emailed the quotation PDFs.'],
  handover: ['Service handover', Truck, 'Accepted quotations passed to MOD Service Operations for contract set-up.'],
  pricing: ['Schedule of Rates', Tags, 'The approved price list used for every MOD quotation.'],
};

export default function ModQuotations() {
  const [tab, setTab] = useState('quotes');
  const [mode, setMode] = useState(() => {
    const gid = new URLSearchParams(window.location.search).get('quote_group');
    return gid ? { view: 'group', id: gid } : { view: 'list' };
  });
  const [caps, setCaps] = useState({ manager: false, pricing: false });
  useEffect(() => { mq.get('/me').then((r) => setCaps(r.data)).catch(() => {}); }, []);

  let body;
  if (mode.view === 'wizard') {
    body = <ModQuoteWizard group={mode.group} onCancel={() => setMode(mode.group ? { view: 'group', id: mode.group.id } : { view: 'list' })}
      onDone={(g) => setMode({ view: 'group', id: g.id })} />;
  } else if (mode.view === 'group') {
    body = <ModQuoteGroup key={mode.id} groupId={mode.id} caps={caps} onBack={() => setMode({ view: 'list' })}
      onEdit={() => mq.get(`/groups/${mode.id}`).then((r) => setMode({ view: 'wizard', group: r.data }))} />;
  } else {
    const keys = ['quotes', 'followups', 'auth', 'handover', ...(caps.pricing ? ['pricing'] : [])];
    const [, , desc] = SECTIONS[tab];
    body = (
      <>
        <div className="mq-tabs" role="tablist" aria-label="Quotation workspace sections">
          {keys.map((k) => {
            const [label, Icon] = SECTIONS[k];
            return (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className="mq-tab" data-testid={`mq-tab-${k}`}>
                <Icon size={15} aria-hidden /> {label}
              </button>
            );
          })}
        </div>
        <p className="text-sm mq-muted mt-3 mb-5" data-testid="mq-section-desc">{desc}</p>
        {tab === 'quotes' && <GroupList onOpen={(id) => setMode({ view: 'group', id })} onNew={() => setMode({ view: 'wizard' })} />}
        {tab === 'followups' && <Followups caps={caps} onOpen={(id) => setMode({ view: 'group', id })} />}
        {tab === 'auth' && <Authorisations caps={caps} onOpen={(id) => setMode({ view: 'group', id })} />}
        {tab === 'handover' && <Handovers caps={caps} onOpen={(id) => setMode({ view: 'group', id })} />}
        {tab === 'pricing' && <Pricing master={caps.master} />}
      </>
    );
  }
  return <div className="mq-scope max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6" data-testid="mod-quotations">{body}</div>;
}
