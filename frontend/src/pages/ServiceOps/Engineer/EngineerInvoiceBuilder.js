/**
 * EngineerInvoiceBuilder — create / edit / send invoices.
 *
 * Iter 216h130. Mirrors EngineerQuoteBuilder. Locks after paid/void.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Send, FileDown, Plus, Trash2, Save, Loader2, Mail,
  CheckCircle2, XCircle, Copy, AlertTriangle, Search, BookmarkPlus,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { outboxPost } from '@/utils/engineerOutbox';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const KIND_OPTIONS = [
  { id: 'labour',  label: 'Labour' }, { id: 'part',    label: 'Part' },
  { id: 'travel',  label: 'Travel' }, { id: 'callout', label: 'Callout' },
  { id: 'other',   label: 'Other' },
];
const emptyLine = (kind = 'labour') => ({ kind, description: '', quantity: 1, unit_price: 0, notes: '' });

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
  // Iter 220p1 — localization (currency + tax vocabulary). Defaults to UK.
  const loc = useLocalization();
  const fmt = useCallback((n) => formatMoney(n, loc), [loc]);
  const sym = loc.currency_symbol || '£';
  // Iter 220ct — quote → invoice continuity. When the engineer
  // taps "Create invoice" from a job, we land here with ?case_id=…
  // and pull labour / mileage / parts directly from the case.
  const caseHint = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '').get('case_id');

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
  // Iter 216h226 — Stripe Connect onboarding state for the email modal
  // warning. Loaded lazily when we open the modal so a missing token
  // (engineer hasn't connected yet) doesn't block invoice editing.
  const [connect, setConnect] = useState(null);

  // Iter 220p1 — for a brand-new invoice, seed the tax rate from the org's
  // market default (e.g. 0% for the US where tax is a manual line). Only
  // applies before the engineer has touched the field.
  const [taxTouched, setTaxTouched] = useState(false);
  useEffect(() => {
    if (isNew && !taxTouched && loc && typeof loc.default_tax_rate === 'number') {
      setForm((f) => ({ ...f, vat_rate: loc.default_tax_rate }));
    }
  }, [isNew, taxTouched, loc]);

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

  // Iter 220ct — prefill from case (labour/mileage/parts). Runs once
  // on mount when ?case_id=… is present and we're creating a new
  // invoice. Never overwrites manual input — only fires on isNew.
  useEffect(() => {
    if (!isNew || !caseHint) return;
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/svc/engineer/jobs/${caseHint}/invoice-prefill`,
          auth(),
        );
        if (!alive) return;
        const d = r.data || {};
        setForm((f) => ({
          ...f,
          case_id: d.case_id || caseHint,
          customer_name:  d.customer_name  || f.customer_name,
          customer_email: d.customer_email || f.customer_email,
          customer_phone: d.customer_phone || f.customer_phone,
          site_name:      d.site_name      || f.site_name,
          site_address:   d.site_address   || f.site_address,
          asset_name:     d.asset_name     || f.asset_name,
          asset_serial:   d.asset_serial   || f.asset_serial,
          description_of_work: d.description_of_work || f.description_of_work,
          lines: Array.isArray(d.lines) && d.lines.length ? d.lines : f.lines,
        }));
        const meta = d.totals_meta || {};
        const bits = [];
        if (meta.on_site_hours > 0) bits.push(`${meta.on_site_hours}h labour`);
        if (meta.miles > 0)         bits.push(`${meta.miles} mi`);
        if (meta.parts_count > 0)   bits.push(`${meta.parts_count} part${meta.parts_count === 1 ? '' : 's'}`);
        notify.success(
          'Pre-filled from job',
          bits.length ? `Loaded ${bits.join(' · ')} — review before sending.` : 'Job details loaded.',
        );
      } catch (e) {
        // Soft fail — engineer can still fill in manually.
        notify.error('Could not prefill from job', e?.response?.data?.detail || e?.message);
      }
    })();
    return () => { alive = false; };
  }, [isNew, caseHint]);

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
        // Iter 220ea·36 — offline-safe create via the engineer outbox; a
        // stable Idempotency-Key (reused on replay) prevents duplicates.
        const idemKey = (window.crypto?.randomUUID?.() || `inv-${Date.now()}-${Math.random().toString(36).slice(2)}`);
        const r = await outboxPost(`${API}/svc/engineer/invoices`, payload, {
          headers: { ...auth().headers, 'Idempotency-Key': idemKey },
          kind: 'invoice-create',
          label: `Invoice for ${payload.customer_name}`,
        });
        if (r.queued) {
          notify.success('Saved offline', 'This invoice will sync automatically when you\u2019re back online.');
          navigate('/svc/engineer/invoices', { replace: true });
          return;
        }
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
                <button
                  onClick={async () => {
                    setShowEmail(true);
                    try {
                      const r = await axios.get(`${API}/svc/engineer/payouts/connect/status`, auth());
                      setConnect(r.data);
                    } catch {
                      setConnect({ ready: false, connected: false });
                    }
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow"
                  data-testid="invoice-builder-send-btn"
                >
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
          {!readOnly ? (
            <CustomerPicker
              customer={{
                name: form.customer_name,
                email: form.customer_email,
                phone: form.customer_phone,
                site_name: form.site_name,
                site_address: form.site_address,
              }}
              onPick={(c) => setForm((f) => ({
                ...f,
                customer_name: c.name || f.customer_name,
                customer_email: c.email || f.customer_email,
                customer_phone: c.phone || f.customer_phone,
                site_name: c.site_name || f.site_name,
                site_address: c.site_address || f.site_address,
              }))}
              onSaveCurrent={async () => {
                if (!form.customer_name.trim()) {
                  notify.error('Enter a customer name first');
                  return;
                }
                try {
                  const r = await axios.post(`${API}/svc/engineer/customers`, {
                    name: form.customer_name,
                    email: form.customer_email || null,
                    phone: form.customer_phone || null,
                    site_name: form.site_name || null,
                    site_address: form.site_address || null,
                  }, auth());
                  notify.success(r.data?.merged ? 'Customer updated in Lite CRM' : 'Customer saved to Lite CRM');
                  return r.data;
                } catch (err) {
                  notify.error('Could not save customer', err?.response?.data?.detail || err?.message);
                  throw err;
                }
              }}
            />
          ) : null}
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
                <th className="text-right py-2 pr-2 w-28">Unit {sym}</th>
                <th className="text-right py-2 pr-2 w-28">Total {sym}</th>
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
                      <td className="py-1.5 pr-2 text-right font-semibold text-slate-700 tabular-nums">{fmt(total)}</td>
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
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">{loc.tax_label} %</label>
                <input type="number" step="0.5" className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums" value={form.vat_rate} disabled={readOnly} onChange={e => { setTaxTouched(true); setForm(f => ({ ...f, vat_rate: Number(e.target.value) })); }} data-testid="ib-vat-rate" />
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
              <div className="flex justify-between text-slate-600"><span>Subtotal</span><span className="tabular-nums">{fmt(totals.subtotal)}</span></div>
              {totals.discountAmount > 0 && (
                <div className="flex justify-between text-rose-600"><span>Discount ({form.discount_pct}%)</span><span className="tabular-nums">-{fmt(totals.discountAmount)}</span></div>
              )}
              <div className="flex justify-between text-slate-600"><span>{loc.tax_label} ({form.vat_rate}%)</span><span className="tabular-nums">{fmt(totals.vatAmount)}</span></div>
              <div className="border-t border-slate-200 pt-2 flex justify-between text-lg font-extrabold text-slate-900"><span>Total due</span><span className="tabular-nums text-blue-700">{fmt(totals.total)}</span></div>
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


// Iter 216h259 — Lite CRM autocomplete for Invoice Customer block
// Iter 216h261 — auto-suggest "Save this customer?" banner
function CustomerPicker({ customer, onPick, onSaveCurrent }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [open, setOpen] = useState(false);
  const [suggestState, setSuggestState] = useState({ found: null, dismissed: false, saving: false });

  useEffect(() => {
    if (!q || q.length < 2) { setResults([]); return; }
    let cancelled = false;
    const id = setTimeout(async () => {
      setLoadingResults(true);
      try {
        const r = await axios.get(`${API}/svc/engineer/customers/search`, {
          ...auth(), params: { q, limit: 8 },
        });
        if (!cancelled) { setResults(r.data?.results || []); setOpen(true); }
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setLoadingResults(false);
      }
    }, 220);
    return () => { cancelled = true; clearTimeout(id); };
  }, [q]);

  const email = customer?.email?.trim();
  const phone = customer?.phone?.trim();
  const name = customer?.name?.trim();
  useEffect(() => {
    setSuggestState((s) => ({ ...s, dismissed: false }));
  }, [email, phone]);
  useEffect(() => {
    if (!name || (!email && !phone)) {
      setSuggestState((s) => ({ ...s, found: null }));
      return undefined;
    }
    let cancelled = false;
    const id = setTimeout(async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/customers/lookup`, {
          ...auth(),
          params: { email: email || undefined, phone: phone || undefined },
        });
        if (!cancelled) setSuggestState((s) => ({ ...s, found: !!r.data?.found }));
      } catch {
        if (!cancelled) setSuggestState((s) => ({ ...s, found: null }));
      }
    }, 600);
    return () => { cancelled = true; clearTimeout(id); };
  }, [name, email, phone]);

  const showSuggestion =
    !!name && (!!email || !!phone)
    && suggestState.found === false
    && !suggestState.dismissed;

  return (
    <div className="relative mb-3" data-testid="ib-customer-picker">
      <div className="flex items-stretch gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => q.length >= 2 && setOpen(true)}
            placeholder="Search saved customers…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:border-blue-400 focus:outline-none"
            data-testid="ib-customer-search"
          />
        </div>
        <button
          type="button"
          onClick={onSaveCurrent}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50"
          title="Save current customer details to Lite CRM"
          data-testid="ib-customer-save"
        >
          <BookmarkPlus size={14} /> Save
        </button>
      </div>
      {open && (results.length > 0 || loadingResults) ? (
        <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto"
             data-testid="ib-customer-results">
          {loadingResults ? (
            <p className="px-3 py-2 text-xs text-slate-400 flex items-center gap-1.5">
              <Loader2 size={12} className="animate-spin" /> Searching…
            </p>
          ) : results.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => { onPick(c); setQ(''); setOpen(false); setResults([]); }}
              className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b border-slate-100 last:border-b-0"
              data-testid={`ib-customer-result-${c.id}`}
            >
              <p className="text-sm font-semibold text-slate-900">{c.name}</p>
              <p className="text-[11px] text-slate-500 truncate">
                {[c.site_name, c.email, c.phone].filter(Boolean).join(' · ') || '—'}
              </p>
            </button>
          ))}
        </div>
      ) : null}
      {showSuggestion ? (
        <div
          className="mt-2 flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-blue-200 bg-blue-50"
          data-testid="ib-customer-suggest"
        >
          <p className="text-xs text-blue-900 flex items-center gap-2">
            <BookmarkPlus size={14} className="text-blue-600" />
            <span>
              Save <b>{name}</b> to your Lite CRM so you can reuse them later?
            </span>
          </p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={async () => {
                setSuggestState((s) => ({ ...s, saving: true }));
                try {
                  await onSaveCurrent();
                  setSuggestState({ found: true, dismissed: false, saving: false });
                } catch {
                  setSuggestState((s) => ({ ...s, saving: false }));
                }
              }}
              disabled={suggestState.saving}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold disabled:opacity-50"
              data-testid="ib-customer-suggest-save"
            >
              {suggestState.saving ? <Loader2 size={12} className="animate-spin" /> : <BookmarkPlus size={12} />}
              Save
            </button>
            <button
              type="button"
              onClick={() => setSuggestState((s) => ({ ...s, dismissed: true }))}
              className="inline-flex items-center justify-center w-6 h-6 rounded-md border border-blue-200 bg-white hover:bg-blue-100 text-blue-700"
              data-testid="ib-customer-suggest-dismiss"
              aria-label="Dismiss"
              title="Dismiss"
            >
              <span className="text-xs">×</span>
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
