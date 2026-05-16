/**
 * EngineerInvoiceBuilder — create / edit / send invoices.
 *
 * Iter 216h130. Mirrors EngineerQuoteBuilder. Locks after paid/void.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Receipt, Send, FileDown, Plus, Trash2, Save, Loader2, Mail,
  CheckCircle2, XCircle, Copy, AlertTriangle,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const KIND_OPTIONS = [
  { id: 'labour',  label: 'Labour' }, { id: 'part',    label: 'Part' },
  { id: 'travel',  label: 'Travel' }, { id: 'callout', label: 'Callout' },
  { id: 'other',   label: 'Other' },
];
const emptyLine = (kind = 'labour') => ({ kind, description: '', quantity: 1, unit_price: 0, notes: '' });
const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function computeTotals(lines, vatRate, discountPct) {
  const sub = lines.reduce((a, ln) => a + (Number(ln.quantity) || 0) * (Number(ln.unit_price) || 0), 0);
  const disc = Number(discountPct) > 0 ? sub * (Number(discountPct) / 100) : 0;
  const subA = sub - disc;
  const vat = subA * (Number(vatRate) / 100);
  return {
    subtotal: Math.round(sub * 100) / 100,
    discountAmount: Math.round(disc * 100) / 100,
    vatAmount: Math.round(vat * 100) / 100,
    total: Math.round((subA + vat) * 100) / 100,
  };
}

export default function EngineerInvoiceBuilder() {
  const navigate = useNavigate();
  const { id: invoiceId } = useParams();
  const isNew = !invoiceId;

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [showEmail, setShowEmail] = useState(false);

  const [form, setForm] = useState({
    customer_name: '', customer_email: '', customer_phone: '',
    site_name: '', site_address: '', asset_name: '', asset_serial: '',
    description_of_work: '',
    lines: [emptyLine('labour')],
    vat_rate: 20, discount_pct: 0, payment_terms_days: 14,
    payment_method: 'BACS', payment_instructions: '',
    bank_name: '', bank_account_name: '',
    bank_sort_code: '', bank_account_number: '',
    notes: '', terms: '', status: 'draft',
  });
  const [emailBody, setEmailBody] = useState({ to: '', message: '' });

  const load = useCallback(async () => {
    if (isNew) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/invoices/${invoiceId}`, auth());
      setForm({ ...r.data, lines: r.data.lines?.length ? r.data.lines : [emptyLine('labour')] });
      setEmailBody({ to: r.data.customer_email || '', message: '' });
    } catch (e) {
      notify.error('Failed to load invoice', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [invoiceId, isNew]);

  useEffect(() => { load(); }, [load]);

  const totals = useMemo(
    () => computeTotals(form.lines, form.vat_rate, form.discount_pct),
    [form.lines, form.vat_rate, form.discount_pct],
  );

  const readOnly = !isNew && ['paid', 'void'].includes(form.status);

  const lineChange = (i, k, v) => setForm(f => ({ ...f, lines: f.lines.map((ln, idx) => idx === i ? { ...ln, [k]: v } : ln) }));
  const addLine = (kind = 'labour') => setForm(f => ({ ...f, lines: [...f.lines, emptyLine(kind)] }));
  const removeLine = (i) => setForm(f => ({ ...f, lines: f.lines.length > 1 ? f.lines.filter((_, idx) => idx !== i) : f.lines }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...form, lines: form.lines.filter(ln => (ln.description || '').trim()) };
      if (!payload.customer_name) { notify.error('Customer name required'); return; }
      if (!payload.lines.length) { notify.error('Add at least one line item'); return; }
      if (isNew) {
        const r = await axios.post(`${API}/svc/engineer/invoices`, payload, auth());
        notify.success(`Invoice ${r.data.invoice_number} created`);
        navigate(`/svc/engineer/invoices/${r.data.id}`, { replace: true });
      } else {
        const r = await axios.patch(`${API}/svc/engineer/invoices/${invoiceId}`, payload, auth());
        setForm({ ...r.data, lines: r.data.lines || [] });
        notify.success('Invoice saved');
      }
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    setSending(true);
    try {
      await axios.post(`${API}/svc/engineer/invoices/${invoiceId}/send`,
        { to: emailBody.to || form.customer_email, message: emailBody.message }, auth());
      notify.success(`Invoice emailed to ${emailBody.to || form.customer_email}`);
      setShowEmail(false);
      load();
    } catch (e) {
      notify.error('Send failed', e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  const handlePdf = async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/invoices/${invoiceId}.pdf`,
        { ...auth(), responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `${form.invoice_number || 'invoice'}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) {
      notify.error('Download failed');
    }
  };

  const handleMark = async (status) => {
    try {
      await axios.post(`${API}/svc/engineer/invoices/${invoiceId}/mark`, { status }, auth());
      notify.success(`Marked as ${status}`);
      load();
    } catch (e) {
      notify.error('Update failed');
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
      <Loader2 className="animate-spin mr-2" size={18} /> Loading invoice…
    </div>;
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-invoice-builder">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => navigate('/svc/engineer/invoices')} className="p-2 rounded-full border border-slate-200 bg-white" data-testid="invoice-builder-back">
              <ArrowLeft size={16} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">GymAxis Invoice</p>
              <h1 className="text-xl font-extrabold text-slate-900 truncate">{isNew ? 'New invoice' : form.invoice_number}</h1>
              {!isNew && <p className="text-xs text-slate-500 capitalize">{form.status}{form.due_date ? ` · Due ${form.due_date}` : ''}</p>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isNew && (
              <>
                <button onClick={handlePdf} className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold" data-testid="invoice-builder-pdf-btn">
                  <FileDown size={14} /> PDF
                </button>
                <button onClick={() => setShowEmail(true)} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow" data-testid="invoice-builder-send-btn">
                  <Send size={14} /> Send
                </button>
              </>
            )}
            {!readOnly && (
              <button onClick={handleSave} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold disabled:opacity-50" data-testid="invoice-builder-save-btn">
                {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
                {isNew ? 'Create' : 'Save'}
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-24 space-y-4">
        {!isNew && (
          <div className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center flex-wrap gap-3" data-testid="invoice-builder-status-bar">
            <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">Update status</p>
            <button disabled={form.status === 'paid'} onClick={() => handleMark('paid')} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs font-bold disabled:opacity-40" data-testid="invoice-mark-paid">
              <CheckCircle2 size={12} /> Mark paid
            </button>
            <button disabled={form.status === 'overdue'} onClick={() => handleMark('overdue')} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-amber-200 bg-amber-50 text-amber-700 text-xs font-bold disabled:opacity-40" data-testid="invoice-mark-overdue">
              <AlertTriangle size={12} /> Overdue
            </button>
            <button disabled={form.status === 'void'} onClick={() => handleMark('void')} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-rose-200 bg-rose-50 text-rose-700 text-xs font-bold disabled:opacity-40" data-testid="invoice-mark-void">
              <XCircle size={12} /> Void
            </button>
            {form.linked_quote_number && (
              <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 text-xs font-bold">
                <Copy size={12} /> From quote {form.linked_quote_number}
              </span>
            )}
          </div>
        )}

        <Section title="Customer">
          <div className="grid md:grid-cols-2 gap-3">
            <Text label="Customer name *" v={form.customer_name} on={v => setForm(f => ({ ...f, customer_name: v }))} testid="ib-customer-name" ro={readOnly} />
            <Text label="Customer email" v={form.customer_email} on={v => setForm(f => ({ ...f, customer_email: v }))} testid="ib-customer-email" ro={readOnly} />
            <Text label="Site name" v={form.site_name} on={v => setForm(f => ({ ...f, site_name: v }))} testid="ib-site-name" ro={readOnly} />
            <Text label="Site address" v={form.site_address} on={v => setForm(f => ({ ...f, site_address: v }))} testid="ib-site-address" ro={readOnly} />
          </div>
        </Section>

        <Section title="Description of work">
          <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2" rows={3}
            value={form.description_of_work} disabled={readOnly}
            onChange={e => setForm(f => ({ ...f, description_of_work: e.target.value }))}
            data-testid="ib-description" />
        </Section>

        <Section title="Line items">
          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-sm">
              <thead><tr className="text-slate-500 text-xs border-b border-slate-200">
                <th className="text-left py-2 pr-2">Type</th>
                <th className="text-left py-2 pr-2">Description</th>
                <th className="text-right py-2 pr-2 w-20">Qty</th>
                <th className="text-right py-2 pr-2 w-28">Unit £</th>
                <th className="text-right py-2 pr-2 w-28">Total £</th>
                <th className="w-8"></th>
              </tr></thead>
              <tbody>
                {form.lines.map((ln, i) => {
                  const total = (Number(ln.quantity) || 0) * (Number(ln.unit_price) || 0);
                  return (
                    <tr key={i} className="border-b border-slate-100" data-testid={`ib-line-${i}`}>
                      <td className="py-1.5 pr-2">
                        <select className="text-xs border border-slate-200 rounded px-1.5 py-1 bg-white" value={ln.kind} disabled={readOnly} onChange={e => lineChange(i, 'kind', e.target.value)} data-testid={`ib-line-${i}-kind`}>
                          {KIND_OPTIONS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5 pr-2">
                        <input className="w-full text-sm border border-slate-200 rounded px-2 py-1 bg-white" value={ln.description} disabled={readOnly} onChange={e => lineChange(i, 'description', e.target.value)} data-testid={`ib-line-${i}-desc`} />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input type="number" step="0.5" className="w-full text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={ln.quantity} disabled={readOnly} onChange={e => lineChange(i, 'quantity', e.target.value)} data-testid={`ib-line-${i}-qty`} />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input type="number" step="0.01" className="w-full text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={ln.unit_price} disabled={readOnly} onChange={e => lineChange(i, 'unit_price', e.target.value)} data-testid={`ib-line-${i}-unit`} />
                      </td>
                      <td className="py-1.5 pr-2 text-right font-semibold text-slate-700 tabular-nums">£{total.toFixed(2)}</td>
                      <td className="py-1.5">
                        {!readOnly && <button onClick={() => removeLine(i)} className="p-1 text-slate-400 hover:text-rose-600" aria-label="Remove" data-testid={`ib-line-${i}-remove`}><Trash2 size={14} /></button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!readOnly && (
            <div className="flex gap-2 flex-wrap mt-3" data-testid="ib-add-line-bar">
              {KIND_OPTIONS.map(k => (
                <button key={k.id} onClick={() => addLine(k.id)} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-slate-700 text-xs font-bold hover:bg-slate-50" data-testid={`ib-add-line-${k.id}`}>
                  <Plus size={12} /> {k.label}
                </button>
              ))}
            </div>
          )}
        </Section>

        <Section title="Totals">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">VAT %</label>
                <input type="number" step="0.5" className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={form.vat_rate} disabled={readOnly} onChange={e => setForm(f => ({ ...f, vat_rate: Number(e.target.value) }))} data-testid="ib-vat-rate" />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">Discount %</label>
                <input type="number" step="0.5" className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={form.discount_pct} disabled={readOnly} onChange={e => setForm(f => ({ ...f, discount_pct: Number(e.target.value) }))} data-testid="ib-discount-pct" />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">Terms (days)</label>
                <input type="number" className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={form.payment_terms_days} disabled={readOnly} onChange={e => setForm(f => ({ ...f, payment_terms_days: Number(e.target.value) }))} data-testid="ib-payment-terms-days" />
              </div>
            </div>
            <div className="space-y-1.5 text-sm bg-slate-50 rounded-xl p-4" data-testid="ib-totals-summary">
              <div className="flex justify-between text-slate-600"><span>Subtotal</span><span className="tabular-nums">{fmtGBP(totals.subtotal)}</span></div>
              {totals.discountAmount > 0 && (
                <div className="flex justify-between text-rose-600"><span>Discount ({form.discount_pct}%)</span><span className="tabular-nums">-{fmtGBP(totals.discountAmount)}</span></div>
              )}
              <div className="flex justify-between text-slate-600"><span>VAT ({form.vat_rate}%)</span><span className="tabular-nums">{fmtGBP(totals.vatAmount)}</span></div>
              <div className="border-t border-slate-200 pt-2 flex justify-between text-lg font-extrabold text-slate-900"><span>Total due</span><span className="tabular-nums text-blue-700">{fmtGBP(totals.total)}</span></div>
            </div>
          </div>
        </Section>

        <Section title="Payment instructions">
          <div className="grid md:grid-cols-2 gap-3">
            <Text label="Method" v={form.payment_method} on={v => setForm(f => ({ ...f, payment_method: v }))} testid="ib-pay-method" ro={readOnly} />
            <Text label="Bank name" v={form.bank_name} on={v => setForm(f => ({ ...f, bank_name: v }))} testid="ib-bank-name" ro={readOnly} />
            <Text label="Account name" v={form.bank_account_name} on={v => setForm(f => ({ ...f, bank_account_name: v }))} testid="ib-bank-account-name" ro={readOnly} />
            <Text label="Sort code" v={form.bank_sort_code} on={v => setForm(f => ({ ...f, bank_sort_code: v }))} testid="ib-bank-sort-code" ro={readOnly} />
            <Text label="Account number" v={form.bank_account_number} on={v => setForm(f => ({ ...f, bank_account_number: v }))} testid="ib-bank-account-number" ro={readOnly} />
            <Text label="Reference / notes" v={form.payment_instructions} on={v => setForm(f => ({ ...f, payment_instructions: v }))} testid="ib-pay-instructions" ro={readOnly} fullWidth />
          </div>
        </Section>

        <Section title="Notes &amp; terms">
          <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Notes</label>
          <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 mb-3" rows={2} disabled={readOnly} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} data-testid="ib-notes" />
          <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Terms</label>
          <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2" rows={3} disabled={readOnly} value={form.terms} onChange={e => setForm(f => ({ ...f, terms: e.target.value }))} data-testid="ib-terms" />
        </Section>
      </main>

      {showEmail && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-4" data-testid="ib-email-modal">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl border border-slate-200">
            <div className="flex items-center gap-2 mb-3">
              <Mail size={18} className="text-blue-600" />
              <h3 className="text-base font-bold text-slate-900">Email this invoice</h3>
            </div>
            {connect && !connect.ready ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 mb-3 text-xs text-amber-900" data-testid="ib-email-no-card-warning">
                <p className="font-bold mb-0.5">No "Pay by card" link will be attached</p>
                <p>
                  {connect.connected
                    ? 'Finish Stripe onboarding to start taking card payments.'
                    : 'Connect your Stripe account to add a secure pay-now link to every invoice.'}
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/svc/engineer/payouts')}
                  className="mt-2 inline-flex items-center gap-1 px-3 py-1 rounded-full bg-amber-600 text-white text-[11px] font-bold"
                  data-testid="ib-email-go-payouts-btn"
                >
                  {connect.connected ? 'Continue onboarding' : 'Connect Stripe'}
                </button>
              </div>
            ) : null}
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">To</label>
            <input type="email" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3" value={emailBody.to} onChange={e => setEmailBody(b => ({ ...b, to: e.target.value }))} data-testid="ib-email-to" />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Personal message (optional)</label>
            <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-4" rows={3} value={emailBody.message} onChange={e => setEmailBody(b => ({ ...b, message: e.target.value }))} data-testid="ib-email-message" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowEmail(false)} className="px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm font-bold" data-testid="ib-email-cancel">Cancel</button>
              <button onClick={handleSend} disabled={sending || !emailBody.to} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="ib-email-send">
                {sending ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const Section = ({ title, children }) => (
  <section className="bg-white rounded-2xl border border-slate-200 p-5">
    <h2 className="text-sm font-bold text-slate-900 mb-3" dangerouslySetInnerHTML={{ __html: title }} />
    {children}
  </section>
);

const Text = ({ label, v, on, testid, ro, fullWidth }) => (
  <div className={fullWidth ? 'md:col-span-2' : ''}>
    <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">{label}</label>
    <input type="text" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white disabled:bg-slate-50" value={v || ''} readOnly={ro} onChange={e => on(e.target.value)} data-testid={testid} />
  </div>
);
