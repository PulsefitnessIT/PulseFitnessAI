import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Download, FileText, Send, CheckCircle2, Globe2, Mail, Pencil, XCircle, Archive, CalendarPlus, AlertTriangle, Trash2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, gbp, downloadBlob, TYPE_LABEL, TYPE_DESC, muted } from './modQuotesApi';
import { Btn, StatusChip, Banner, Field } from './MqUi';

export { StatusChip };

export default function ModQuoteGroup({ groupId, caps, onBack, onEdit }) {
  const [g, setG] = useState(null);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState('');
  const [exc, setExc] = useState({});
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [notifyForm, setNotifyForm] = useState({ to: '', confirm_to: '', attach_pdfs: false });
  const [sageRef, setSageRef] = useState({});
  const [ext, setExt] = useState(null);
  const load = useCallback(() => mq.get(`/groups/${groupId}`).then((r) => { setG(r.data); setSel(r.data.quotes.map((q) => q.id)); })
    .catch((e) => notify.error(errText(e))), [groupId]);
  useEffect(() => { load(); }, [load]);
  if (!g) return <div className="p-8 text-center mq-muted" data-testid="mq-loading">Loading quotation…</div>;

  const act = async (fn, ok) => {
    setBusy(true);
    try { const msg = await fn(); if (msg !== false) notify.success(ok); await load(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const unverified = g.quotes.flatMap((q) => (q.unverified_rate_lines || []).map((ln) => ({ ...ln, quote_id: q.id, quote_number: q.quote_number })));
  const excKey = (ln) => `${ln.quote_id}:${ln.line_no}`;
  const approvePayload = () => ({
    approve: true,
    exceptions: unverified.filter((ln) => exc[excKey(ln)]?.reason).map((ln) => ({
      quote_id: ln.quote_id, line_no: ln.line_no, reason: exc[excKey(ln)].reason, original_rate: ln.unit_price,
      proposed_rate: ln.unit_price, valid_until: exc[excKey(ln)].valid_until || new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
    })),
  });
  const extend = () => setExt({ valid_until: '', reason: '' });
  const saveExtend = () => act(async () => { await mq.post(`/groups/${g.id}/extend-validity`, ext); setExt(null); }, 'Validity extended');
  const sendNotify = () => act(async () => {
    const r = await mq.post(`/groups/${g.id}/notify`, { ...notifyForm, resend: g.notified_revision === g.revision });
    setNotifyOpen(false);
    if (r.data.dry_run) { notify.info?.('Test mode: no email was sent — notification recorded in history'); return false; }
    return true;
  }, 'Notification sent');
  const c = g.customer;

  const closed = ['accepted', 'handed_over', 'withdrawn'].includes(g.status);
  const missingExc = unverified.filter((ln) => (exc[excKey(ln)]?.reason || '').trim().length < 10).length;
  const canNotify = g.quotes.some((q) => q.customer_visible) && !closed;
  const nextStep = {
    draft: 'Submit the draft for manager approval.',
    pending_approval: caps.manager ? 'Review pricing and approve, or return to draft.' : 'Waiting for a MOD Sales Manager to approve.',
    approved: 'Choose the options to publish to the customer in MODService.',
    published: 'Published — notify the customer when ready.',
    customer_review: 'The customer is reviewing in MODService.',
    authorisation_submitted: 'Customer authorisation received — verify it under Customer authorisations.',
    accepted: 'Accepted — set up the service records under Service handover.',
  }[g.status];

  return (
    <div data-testid="mq-group-detail">
      <Btn variant="ghost" size="sm" icon={ArrowLeft} onClick={onBack} className="mb-3 -ml-3" data-testid="mq-group-back">All quotations</Btn>
      <div className="mq-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-2xl font-semibold pulse-font-heading" data-testid="mq-group-customer">{c.name}</h2>
            <div className="text-sm mt-1 mq-muted">{(c.address_lines || []).join(', ') || 'No address held'}</div>
          </div>
          <StatusChip status={g.status} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
          <Field label="Revision">{g.revision}</Field>
          <Field label="Created by">{g.created_by_name}</Field>
          <Field label="Contact">{c.contact_name || '—'}{c.contact_email ? ` · ${c.contact_email}` : ''}</Field>
          <Field label="Options">{g.quotes.map((q) => TYPE_LABEL[q.mod_quote_type]).join(', ')}</Field>
        </div>
        {nextStep && <div className="text-sm mt-4 font-medium" data-testid="mq-next-step">Next step: <span className="mq-muted font-normal">{nextStep}</span></div>}
        <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid="mq-group-actions">
          {g.status === 'draft' && <Btn icon={Send} variant="primary" loading={busy} data-testid="mq-submit" onClick={() => act(() => mq.post(`/groups/${g.id}/submit`), 'Submitted for approval')}>Submit for approval</Btn>}
          {g.status === 'pending_approval' && caps.manager && (
            <>
              <Btn icon={CheckCircle2} variant="primary" loading={busy} data-testid="mq-approve" disabled={missingExc > 0}
                title={missingExc ? `${missingExc} unapproved line(s) still need an exception reason` : undefined}
                onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, approvePayload()), 'Quotations approved')}>Approve</Btn>
              <Btn icon={XCircle} disabled={busy} data-testid="mq-reject" onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, { approve: false, notes: reason }), 'Returned to draft')}>Return to draft</Btn>
            </>
          )}
          {g.status === 'approved' && <Btn icon={Globe2} variant="primary" loading={busy} disabled={!sel.length} data-testid="mq-publish"
            onClick={() => window.confirm(`Publish ${sel.length} quotation(s) to the MODService portal for ${c.name}?`) && act(() => mq.post(`/groups/${g.id}/publish`, { quote_ids: sel }), 'Published to MODService')}>Publish to MODService</Btn>}
          {canNotify && <Btn icon={Mail} variant={['published'].includes(g.status) && g.notified_revision !== g.revision ? 'primary' : 'secondary'} disabled={busy} data-testid="mq-notify"
            onClick={() => { setNotifyForm({ to: c.contact_email || '', confirm_to: '', attach_pdfs: true }); setNotifyOpen(true); }}>
            {g.notified_revision === g.revision ? 'Resend notification' : 'Notify customer'}</Btn>}
          {['draft', 'pending_approval', 'approved', 'published', 'customer_review'].includes(g.status) &&
            <Btn icon={Pencil} disabled={busy} onClick={onEdit} data-testid="mq-edit">{g.status === 'draft' || g.status === 'pending_approval' ? 'Edit draft' : 'Create revision'}</Btn>}
          <Btn icon={Archive} data-testid="mq-download-all" onClick={() => downloadBlob(`/groups/${g.id}/pdfs.zip`, `MOD-Quotations-${c.name}.zip`).catch((e) => notify.error(errText(e)))}>Download all PDFs</Btn>
          {caps.manager && ['published', 'customer_review', 'authorisation_submitted'].includes(g.status) && <Btn icon={CalendarPlus} disabled={busy} data-testid="mq-extend" onClick={extend}>Extend validity</Btn>}
          {caps.owner && !['accepted', 'handed_over', 'published', 'customer_review', 'authorisation_submitted'].includes(g.status) && <Btn icon={Trash2} variant="danger" disabled={busy} data-testid="mq-delete"
            onClick={async () => {
              if (!window.confirm(`Delete these quotations for ${c.name}? They leave the quotations list; a full copy of the quotes, approvals and history is kept in the audit archive.`)) return;
              try { await mq.delete(`/groups/${g.id}`); notify.success('Quotations deleted'); onBack(); } catch (e) { notify.error(errText(e)); }
            }}>Delete</Btn>}
          {!closed && <Btn icon={XCircle} variant="danger" disabled={busy} className="sm:ml-auto" data-testid="mq-withdraw"
            onClick={() => window.confirm('Recall these quotations? Customers will no longer see them.') && act(() => mq.post(`/groups/${g.id}/withdraw`, { reason }), 'Quotations recalled')}>Recall</Btn>}
        </div>
        {g.status === 'pending_approval' && caps.manager && missingExc > 0 && <div className="text-xs mt-3" style={{ color: 'var(--color-warning)' }} data-testid="mq-approve-blocked">Approve is unavailable: {missingExc} line(s) on unapproved rates need a commercial exception reason below, or revise the quotation.</div>}
        {g.status === 'pending_approval' && !caps.manager && <div className="text-xs mt-3 mq-muted" data-testid="mq-approve-manager-only">Approval is restricted to MOD Sales Managers.</div>}
      </div>
      {g.status === 'pending_approval' && caps.manager && (
        <div className="mq-card p-5 mt-4 space-y-3" data-testid="mq-approval-panel">
          <div className="font-semibold">Manager approval</div>
          {unverified.length > 0 ? (
            <div className="space-y-3" data-testid="mq-unverified">
              <Banner icon={AlertTriangle}>{unverified.length} priced line(s) use rates that are not approved. Each needs a commercial exception before approval, or revise the quotation.</Banner>
              {unverified.map((ln) => (
                <div key={excKey(ln)} className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,16rem)_10rem] gap-2 items-center text-sm" data-testid={`mq-exc-${ln.line_no}`}>
                  <span>{ln.quote_number} · line {ln.line_no} · {ln.item_code} · {ln.description} · <b>{gbp(ln.unit_price)}</b></span>
                  <input placeholder="Exception reason (min 10 characters)" aria-label="Exception reason" value={exc[excKey(ln)]?.reason || ''} data-testid="mq-exc-reason"
                    onChange={(e) => setExc({ ...exc, [excKey(ln)]: { ...exc[excKey(ln)], reason: e.target.value } })} className="mq-input h-10 px-3" />
                  <input type="date" aria-label="Exception valid until" value={exc[excKey(ln)]?.valid_until || ''} data-testid="mq-exc-valid"
                    onChange={(e) => setExc({ ...exc, [excKey(ln)]: { ...exc[excKey(ln)], valid_until: e.target.value } })} className="mq-input h-10 px-3" />
                </div>
              ))}
            </div>
          ) : <div className="text-sm mq-muted" data-testid="mq-all-verified">All priced lines use approved rates.</div>}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Notes (used when returning to draft)" aria-label="Approval notes"
            className="mq-input w-full max-w-xl h-10 px-3 text-sm" data-testid="mq-approve-reason" />
        </div>
      )}

      {ext && (
        <div className="mq-card p-5 mt-4 flex flex-wrap items-end gap-3 max-w-3xl" data-testid="mq-extend-form">
          <label className="text-sm"><span className="mq-label block mb-1">New valid-until date</span><input type="date" min={new Date(Date.now() + 864e5).toISOString().slice(0, 10)} value={ext.valid_until} onChange={(e) => setExt({ ...ext, valid_until: e.target.value })} className="mq-input h-10 px-3" data-testid="mq-extend-date" /></label>
          <label className="text-sm flex-1 min-w-[220px]"><span className="mq-label block mb-1">Reason (recorded in history)</span><input value={ext.reason} onChange={(e) => setExt({ ...ext, reason: e.target.value })} className="mq-input w-full h-10 px-3" data-testid="mq-extend-reason" /></label>
          <Btn variant="ghost" onClick={() => setExt(null)} data-testid="mq-extend-cancel">Cancel</Btn>
          <Btn icon={CheckCircle2} variant="primary" loading={busy} disabled={!ext.valid_until || ext.reason.trim().length < 10} onClick={saveExtend} data-testid="mq-extend-save">Extend</Btn>
        </div>
      )}
      {notifyOpen && (
        <div className="mq-card p-5 mt-4 space-y-3 max-w-xl" data-testid="mq-notify-form">
          <div className="font-semibold">Tell the customer their quotations are ready in MODService</div>
          <input value={notifyForm.to} onChange={(e) => setNotifyForm({ ...notifyForm, to: e.target.value })} placeholder="Recipient email" aria-label="Recipient email" className="mq-input w-full h-10 px-3 text-sm" data-testid="mq-notify-to" />
          <input value={notifyForm.confirm_to} onChange={(e) => setNotifyForm({ ...notifyForm, confirm_to: e.target.value })} placeholder="Re-type recipient email to confirm" aria-label="Confirm recipient email" className="mq-input w-full h-10 px-3 text-sm" data-testid="mq-notify-confirm" />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={notifyForm.attach_pdfs} onChange={(e) => setNotifyForm({ ...notifyForm, attach_pdfs: e.target.checked })} data-testid="mq-notify-attach" /> Attach the quotation PDFs (needed for customers without MODService)</label>
          <div className="flex gap-2 justify-end">
            <Btn variant="ghost" onClick={() => setNotifyOpen(false)} data-testid="mq-notify-cancel">Cancel</Btn>
            <Btn icon={Mail} variant="primary" loading={busy} onClick={sendNotify} data-testid="mq-notify-send">Send notification</Btn>
          </div>
        </div>
      )}
      {(g.chase_schedule || []).length > 0 && (
        <div className="mq-card p-5 mt-4" data-testid="mq-chase-schedule">
          <div className="font-semibold mb-2">Follow-ups</div>
          <div className="flex flex-wrap gap-2">
            {g.chase_schedule.map((c) => (
              <StatusChip key={c.n} status={['done', 'task_created'].includes(c.status) ? 'accepted' : c.status === 'cancelled' ? 'withdrawn' : 'pending_approval'}
                label={`${c.weeks} weeks · ${new Date(c.due).toLocaleDateString('en-GB')} · ${['done', 'task_created'].includes(c.status) ? 'chased' : c.status === 'cancelled' ? 'not needed' : 'scheduled'}`} />
            ))}
          </div>
        </div>
      )}
      <div className="grid lg:grid-cols-3 gap-4 mt-6" data-testid="mq-comparison">
        {g.quotes.map((q) => <QuoteCard key={q.id} q={q} g={g} sel={sel} setSel={setSel} sageRef={sageRef} setSageRef={setSageRef} act={act} />)}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-6">
        <div className="mq-card p-5">
          <div className="font-semibold mb-3">Shared equipment list ({g.rows.length})</div>
          <ul className="text-sm divide-y max-h-72 overflow-y-auto" style={{ borderColor: 'var(--theme-border)' }}>
            {g.rows.map((r) => <li key={r.row_id} className="flex justify-between gap-2 py-1.5" style={{ borderColor: 'var(--theme-border)' }}><span>{r.item_label || r.description}{r.label ? ` (${r.label})` : ''}</span><span className="mq-muted whitespace-nowrap">×{r.qty}{r.coverage ? ` · Type ${r.coverage}` : ''}</span></li>)}
          </ul>
          {g.superseded?.length > 0 && <div className="text-xs mt-3 mq-muted" data-testid="mq-superseded">{g.superseded.length} superseded quotation(s) retained for audit.</div>}
        </div>
        <div className="mq-card p-5" data-testid="mq-history">
          <div className="font-semibold mb-3 flex items-center gap-2"><FileText size={15} /> History</div>
          <ul className="text-sm space-y-2 max-h-72 overflow-y-auto">
            {g.events.map((e) => <li key={e.id}><span className="font-medium capitalize">{e.kind.replace(/_/g, ' ')}{e.detail?.option ? ` — ${e.detail.option} ${e.detail.ref}` : ''}</span> <span className="mq-muted">· {e.user_name || 'System'} · {new Date(e.at).toLocaleString('en-GB')}{e.version ? ` · v${e.version}` : ''}</span></li>)}
          </ul>
        </div>
      </div>
    </div>
  );
}

function QuoteCard({ q, g, sel, setSel, sageRef, setSageRef, act }) {
  const expired = q.valid_until && q.valid_until < new Date().toISOString().slice(0, 10);
  const selectable = g.status === 'approved';
  return (
    <div className="mq-option flex flex-col" data-selected={selectable && sel.includes(q.id)} data-testid={`mq-quote-${q.mod_quote_type}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-lg">{TYPE_LABEL[q.mod_quote_type]}</div>
          <div className="text-xs mq-muted">{TYPE_DESC[q.mod_quote_type]}</div>
        </div>
        {selectable ? (
          <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
            <input type="checkbox" checked={sel.includes(q.id)} aria-label="Publish this option" data-testid={`mq-publish-select-${q.mod_quote_type}`}
              onChange={(e) => setSel(e.target.checked ? [...sel, q.id] : sel.filter((x) => x !== q.id))} /> Publish
          </label>
        ) : <StatusChip status={q.status} />}
      </div>
      <div className="mq-totals">
        <div><span className="mq-muted">Net</span><span>{gbp(q.subtotal)}</span></div>
        <div><span className="mq-muted">VAT</span><span>{gbp(q.vat_amount)}</span></div>
        <div className="items-baseline"><span className="font-semibold">Gross</span><span className="mq-gross" data-testid={`mq-quote-${q.mod_quote_type}-gross`}>{gbp(q.total)}</span></div>
      </div>
      <div className="text-xs mt-3 space-y-1">
        <div className="mq-muted">Internal ref {q.quote_number} · v{q.version}</div>
        <div className={q.sage_quote_number ? '' : 'mq-muted'}>{q.sage_quote_number ? `Sage ${q.sage_quote_number}` : 'No Sage number recorded'}</div>
        {q.valid_until && <div style={expired ? { color: 'var(--color-danger)' } : muted} data-testid={`mq-valid-${q.mod_quote_type}`}>{expired ? 'Expired' : 'Valid until'} {q.valid_until}</div>}
        {(q.unverified_rate_lines || []).length > 0 && <div style={{ color: 'var(--color-warning)' }}>{q.unverified_rate_lines.length} line(s) on unapproved rates</div>}
      </div>
      {!q.published_pdf_path && !q.sage_quote_number && (
        <div className="flex gap-2 mt-3">
          <input placeholder="Sage quotation no." aria-label="Sage quotation number" value={sageRef[q.id] || ''} onChange={(e) => setSageRef({ ...sageRef, [q.id]: e.target.value })} className="mq-input flex-1 min-w-0 h-8 px-2 text-xs" data-testid={`mq-sage-${q.mod_quote_type}`} />
          <Btn size="sm" data-testid={`mq-sage-save-${q.mod_quote_type}`} disabled={!(sageRef[q.id] || '').trim()}
            onClick={() => window.confirm('Confirm this number was assigned by Sage?') && act(() => mq.post(`/quotes/${q.id}/sage-ref`, { sage_quote_number: sageRef[q.id] || '', verified: true }), 'Sage reference recorded')}>Save</Btn>
        </div>
      )}
      <div className="mt-auto pt-4">
        <Btn icon={Download} size="sm" className="w-full" data-testid={`mq-pdf-${q.mod_quote_type}`}
          onClick={() => downloadBlob(`/quotes/${q.id}/pdf`, `${q.quote_number}.pdf`).catch((e) => notify.error(errText(e)))}>Download PDF</Btn>
      </div>
    </div>
  );
}
