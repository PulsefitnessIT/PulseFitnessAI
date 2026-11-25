import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Download, FileText, Send, CheckCircle2, Globe2, Mail, Pencil, XCircle, Archive } from 'lucide-react';
import { notify } from '@/components/notifications';
import { mq, errText, gbp, downloadBlob, TYPE_LABEL, TYPE_DESC, STATUS_LABEL, STATUS_TONE, card, muted, inputStyle, primaryBtn } from './modQuotesApi';

export function StatusChip({ status }) {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold" data-testid={`mq-status-${status}`}
      style={{ border: `1px solid ${STATUS_TONE[status] || 'var(--theme-border)'}`, color: STATUS_TONE[status] || 'var(--theme-text-muted)' }}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

const Btn = ({ icon: Icon, children, primary, ...p }) => (
  <button type="button" {...p} className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold disabled:opacity-40 transition-opacity"
    style={primary ? primaryBtn : card}><Icon size={14} /> {children}</button>
);

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
  if (!g) return <div className="p-8 text-center" style={muted}>Loading…</div>;

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); notify.success(ok); await load(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
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
    if (r.data.dry_run) notify.info?.('Test mode: no email was sent — notification recorded in history');
  }, 'Notification processed');
  const c = g.customer;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6" data-testid="mq-group-detail">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-sm mb-4" style={muted} data-testid="mq-group-back"><ArrowLeft size={14} /> All quotations</button>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }} data-testid="mq-group-customer">{c.name}</h2>
          <div className="text-sm mt-1" style={muted}>{(c.address_lines || []).join(', ')} · Revision {g.revision} · Created by {g.created_by_name}</div>
        </div>
        <StatusChip status={g.status} />
      </div>

      <div className="flex flex-wrap gap-2 mt-5" data-testid="mq-group-actions">
        {['draft', 'pending_approval', 'approved', 'published', 'customer_review'].includes(g.status) &&
          <Btn icon={Pencil} onClick={onEdit} disabled={busy} data-testid="mq-edit">{g.status === 'draft' || g.status === 'pending_approval' ? 'Edit draft' : 'Create revision'}</Btn>}
        {g.status === 'draft' && <Btn icon={Send} primary disabled={busy} data-testid="mq-submit" onClick={() => act(() => mq.post(`/groups/${g.id}/submit`), 'Submitted for approval')}>Submit for approval</Btn>}
        {g.status === 'pending_approval' && caps.manager && (
          <>
            <Btn icon={CheckCircle2} primary disabled={busy} data-testid="mq-approve"
              onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, approvePayload()), 'Quotations approved')}>Approve</Btn>
            <Btn icon={XCircle} disabled={busy} data-testid="mq-reject" onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, { approve: false, notes: reason }), 'Returned to draft')}>Return to draft</Btn>
          </>
        )}
        {g.status === 'approved' && <Btn icon={Globe2} primary disabled={busy || !sel.length} data-testid="mq-publish"
          onClick={() => window.confirm(`Publish ${sel.length} quotation(s) to the MODService portal for ${c.name}?`) && act(() => mq.post(`/groups/${g.id}/publish`, { quote_ids: sel }), 'Published to MODService')}>Publish to MODService</Btn>}
        {g.quotes.some((q) => q.customer_visible) && !['accepted', 'handed_over', 'withdrawn'].includes(g.status) && <Btn icon={Mail} disabled={busy} data-testid="mq-notify"
          onClick={() => { setNotifyForm({ to: c.contact_email || '', confirm_to: '', attach_pdfs: false }); setNotifyOpen(true); }}>
          {g.notified_revision === g.revision ? 'Resend notification' : 'Notify customer'}</Btn>}
        <Btn icon={Archive} data-testid="mq-download-all" onClick={() => downloadBlob(`/groups/${g.id}/pdfs.zip`, `MOD-Quotations-${c.name}.zip`).catch((e) => notify.error(errText(e)))}>Download all PDFs</Btn>
        {caps.manager && ['published', 'customer_review', 'authorisation_submitted'].includes(g.status) && <Btn icon={CheckCircle2} disabled={busy} data-testid="mq-extend" onClick={extend}>Extend validity</Btn>}
        {!['accepted', 'handed_over', 'withdrawn'].includes(g.status) && <Btn icon={XCircle} disabled={busy} data-testid="mq-withdraw"
          onClick={() => window.confirm('Withdraw these quotations? Customers will no longer see them.') && act(() => mq.post(`/groups/${g.id}/withdraw`, { reason }), 'Withdrawn')}>Withdraw</Btn>}
      </div>
      {g.status === 'pending_approval' && caps.manager && (
        <div className="mt-3">
          {unverified.length > 0 && (
            <div className="rounded-xl p-3 mb-2 space-y-2" style={card} data-testid="mq-unverified">
              <div className="text-sm font-semibold" style={{ color: 'var(--color-warning)' }}>{unverified.length} priced line(s) use rates that are not verified. Each needs a commercial exception, or revise the quotation.</div>
              {unverified.map((ln) => (
                <div key={excKey(ln)} className="grid md:grid-cols-[1fr_auto_auto] gap-2 items-center text-sm" data-testid={`mq-exc-${ln.line_no}`}>
                  <span>{ln.quote_number} · line {ln.line_no} · {ln.item_code} · {ln.description} · {gbp(ln.unit_price)}</span>
                  <input placeholder="Reason (min 10 characters)" value={exc[excKey(ln)]?.reason || ''} data-testid="mq-exc-reason"
                    onChange={(e) => setExc({ ...exc, [excKey(ln)]: { ...exc[excKey(ln)], reason: e.target.value } })} className="rounded px-2 py-1" style={inputStyle} />
                  <input type="date" aria-label="Exception valid until" value={exc[excKey(ln)]?.valid_until || ''} data-testid="mq-exc-valid"
                    onChange={(e) => setExc({ ...exc, [excKey(ln)]: { ...exc[excKey(ln)], valid_until: e.target.value } })} className="rounded px-2 py-1" style={inputStyle} />
                </div>
              ))}
            </div>
          )}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Notes (used when returning to draft)"
            className="w-full max-w-xl rounded-lg px-3 py-2 text-sm" style={inputStyle} data-testid="mq-approve-reason" />
        </div>
      )}

      {ext && (
        <div className="rounded-xl p-4 mt-4 flex flex-wrap items-end gap-2 max-w-2xl" style={card} data-testid="mq-extend-form">
          <label className="text-sm" style={muted}>New valid-until date<input type="date" min={new Date(Date.now() + 864e5).toISOString().slice(0, 10)} value={ext.valid_until} onChange={(e) => setExt({ ...ext, valid_until: e.target.value })} className="block rounded px-2 py-1 mt-1" style={inputStyle} data-testid="mq-extend-date" /></label>
          <label className="text-sm flex-1 min-w-[220px]" style={muted}>Reason (recorded in history)<input value={ext.reason} onChange={(e) => setExt({ ...ext, reason: e.target.value })} className="block w-full rounded px-2 py-1 mt-1" style={inputStyle} data-testid="mq-extend-reason" /></label>
          <Btn icon={CheckCircle2} primary disabled={busy || !ext.valid_until || ext.reason.trim().length < 10} onClick={saveExtend} data-testid="mq-extend-save">Extend</Btn>
          <Btn icon={XCircle} onClick={() => setExt(null)} data-testid="mq-extend-cancel">Cancel</Btn>
        </div>
      )}
      {notifyOpen && (
        <div className="rounded-xl p-4 mt-4 space-y-2 max-w-xl" style={card} data-testid="mq-notify-form">
          <div className="font-semibold text-sm">Tell the customer their quotations are ready in MODService</div>
          <input value={notifyForm.to} onChange={(e) => setNotifyForm({ ...notifyForm, to: e.target.value })} placeholder="Recipient email" className="w-full rounded px-3 py-2 text-sm" style={inputStyle} data-testid="mq-notify-to" />
          <input value={notifyForm.confirm_to} onChange={(e) => setNotifyForm({ ...notifyForm, confirm_to: e.target.value })} placeholder="Re-type recipient email to confirm" className="w-full rounded px-3 py-2 text-sm" style={inputStyle} data-testid="mq-notify-confirm" />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={notifyForm.attach_pdfs} onChange={(e) => setNotifyForm({ ...notifyForm, attach_pdfs: e.target.checked })} data-testid="mq-notify-attach" /> Also attach the quotation PDFs</label>
          <div className="flex gap-2">
            <Btn icon={Mail} primary disabled={busy} onClick={sendNotify} data-testid="mq-notify-send">Send notification</Btn>
            <Btn icon={XCircle} onClick={() => setNotifyOpen(false)} data-testid="mq-notify-cancel">Cancel</Btn>
          </div>
        </div>
      )}
      <div className="grid lg:grid-cols-3 gap-4 mt-6">
        {g.quotes.map((q) => (
          <div key={q.id} className="rounded-xl p-4" style={card} data-testid={`mq-quote-${q.mod_quote_type}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-semibold">{TYPE_LABEL[q.mod_quote_type]}</div>
                <div className="text-xs" style={muted}>{TYPE_DESC[q.mod_quote_type]}</div>
              </div>
              {g.status === 'approved' && <input type="checkbox" checked={sel.includes(q.id)} aria-label="Publish this option" data-testid={`mq-publish-select-${q.mod_quote_type}`}
                onChange={(e) => setSel(e.target.checked ? [...sel, q.id] : sel.filter((x) => x !== q.id))} />}
            </div>
            <div className="text-xs mt-2" style={muted}>Internal ref {q.quote_number} · v{q.version}{q.sage_quote_number ? ` · Sage ${q.sage_quote_number}` : ' · no Sage number recorded'}</div>
            {q.valid_until && <div className="text-xs" style={q.valid_until < new Date().toISOString().slice(0, 10) ? { color: 'var(--color-danger)' } : muted} data-testid={`mq-valid-${q.mod_quote_type}`}>Valid until {q.valid_until}</div>}
            {!q.published_pdf_path && !q.sage_quote_number && (
              <div className="flex gap-1 mt-2">
                <input placeholder="Sage quotation no." value={sageRef[q.id] || ''} onChange={(e) => setSageRef({ ...sageRef, [q.id]: e.target.value })} className="flex-1 rounded px-2 py-1 text-xs" style={inputStyle} data-testid={`mq-sage-${q.mod_quote_type}`} />
                <button type="button" className="text-xs px-2 rounded-full" style={card} data-testid={`mq-sage-save-${q.mod_quote_type}`}
                  onClick={() => window.confirm('Confirm this number was assigned by Sage?') && act(() => mq.post(`/quotes/${q.id}/sage-ref`, { sage_quote_number: sageRef[q.id] || '', verified: true }), 'Sage reference recorded')}>Save</button>
              </div>
            )}
            <div className="mt-3 text-sm space-y-0.5">
              <div className="flex justify-between"><span style={muted}>Net</span><span>{gbp(q.subtotal)}</span></div>
              <div className="flex justify-between"><span style={muted}>VAT</span><span>{gbp(q.vat_amount)}</span></div>
              <div className="flex justify-between font-semibold"><span>Gross</span><span data-testid={`mq-quote-${q.mod_quote_type}-gross`}>{gbp(q.total)}</span></div>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <StatusChip status={q.status} />
              <button type="button" className="inline-flex items-center gap-1 text-sm font-semibold" style={{ color: 'var(--color-brand-cyan)' }} data-testid={`mq-pdf-${q.mod_quote_type}`}
                onClick={() => downloadBlob(`/quotes/${q.id}/pdf`, `${q.quote_number}.pdf`).catch((e) => notify.error(errText(e)))}><Download size={14} /> PDF</button>
            </div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-6">
        <div className="rounded-xl p-4" style={card}>
          <div className="font-semibold mb-2">Shared equipment list ({g.rows.length})</div>
          <ul className="text-sm space-y-1 max-h-72 overflow-y-auto">
            {g.rows.map((r) => <li key={r.row_id} className="flex justify-between gap-2"><span>{r.description}{r.label ? ` (${r.label})` : ''}</span><span style={muted}>×{r.qty}{r.coverage ? ` · ${r.coverage}` : ''}</span></li>)}
          </ul>
          {g.superseded?.length > 0 && <div className="text-xs mt-3" style={muted} data-testid="mq-superseded">{g.superseded.length} superseded quotation(s) retained for audit.</div>}
        </div>
        <div className="rounded-xl p-4" style={card} data-testid="mq-history">
          <div className="font-semibold mb-2 flex items-center gap-2"><FileText size={14} /> History</div>
          <ul className="text-sm space-y-1.5 max-h-72 overflow-y-auto">
            {g.events.map((e) => <li key={e.id}><span className="font-medium">{e.kind.replace(/_/g, ' ')}{e.detail?.option ? ` — ${e.detail.option} ${e.detail.ref}` : ''}</span> <span style={muted}>· {e.user_name} · {new Date(e.at).toLocaleString('en-GB')}{e.version ? ` · v${e.version}` : ''}</span></li>)}
          </ul>
        </div>
      </div>
    </div>
  );
}
