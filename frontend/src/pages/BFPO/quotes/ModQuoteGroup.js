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
  const load = useCallback(() => mq.get(`/groups/${groupId}`).then((r) => { setG(r.data); setSel(r.data.quotes.map((q) => q.id)); })
    .catch((e) => notify.error(errText(e))), [groupId]);
  useEffect(() => { load(); }, [load]);
  if (!g) return <div className="p-8 text-center" style={muted}>Loading…</div>;

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); notify.success(ok); await load(); } catch (e) { notify.error(errText(e)); } finally { setBusy(false); }
  };
  const unverified = [...new Set(g.quotes.flatMap((q) => q.unverified_rate_lines || []))];
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
              onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, { approve: true, commercial_exception_reason: reason }), 'Quotations approved')}>Approve</Btn>
            <Btn icon={XCircle} disabled={busy} data-testid="mq-reject" onClick={() => act(() => mq.post(`/groups/${g.id}/approve`, { approve: false, notes: reason }), 'Returned to draft')}>Return to draft</Btn>
          </>
        )}
        {g.status === 'approved' && <Btn icon={Globe2} primary disabled={busy || !sel.length} data-testid="mq-publish"
          onClick={() => window.confirm(`Publish ${sel.length} quotation(s) to the MODService portal for ${c.name}?`) && act(() => mq.post(`/groups/${g.id}/publish`, { quote_ids: sel }), 'Published to MODService')}>Publish to MODService</Btn>}
        {g.quotes.some((q) => q.customer_visible) && <Btn icon={Mail} disabled={busy} data-testid="mq-notify"
          onClick={() => window.confirm(`Email ${c.contact_email || 'the customer'} that quotations are ready (PDFs attached)?`) && act(() => mq.post(`/groups/${g.id}/notify`, { resend: g.notified_revision === g.revision }), 'Customer notified')}>
          {g.notified_revision === g.revision ? 'Resend notification' : 'Notify customer'}</Btn>}
        <Btn icon={Archive} data-testid="mq-download-all" onClick={() => downloadBlob(`/groups/${g.id}/pdfs.zip`, `MOD-Quotations-${c.name}.zip`).catch((e) => notify.error(errText(e)))}>Download all PDFs</Btn>
        {!['accepted', 'handed_over', 'withdrawn'].includes(g.status) && <Btn icon={XCircle} disabled={busy} data-testid="mq-withdraw"
          onClick={() => window.confirm('Withdraw these quotations? Customers will no longer see them.') && act(() => mq.post(`/groups/${g.id}/withdraw`, { reason }), 'Withdrawn')}>Withdraw</Btn>}
      </div>
      {g.status === 'pending_approval' && caps.manager && (
        <div className="mt-3">
          {unverified.length > 0 && <div className="text-sm mb-1" style={{ color: 'var(--color-warning)' }} data-testid="mq-unverified">Unverified rates: {unverified.join('; ')} — a commercial exception reason is required.</div>}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Approval notes / commercial exception reason"
            className="w-full max-w-xl rounded-lg px-3 py-2 text-sm" style={inputStyle} data-testid="mq-approve-reason" />
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
            <div className="text-xs mt-2" style={muted}>Ref {q.quote_number} · v{q.version} <span title="Internal PulseFitness.ai reference — not a Sage quotation number">(internal ref)</span></div>
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
            {g.events.map((e) => <li key={e.id}><span className="font-medium">{e.kind.replace(/_/g, ' ')}</span> <span style={muted}>· {e.user_name} · {new Date(e.at).toLocaleString('en-GB')}{e.version ? ` · v${e.version}` : ''}</span></li>)}
          </ul>
        </div>
      </div>
    </div>
  );
}
