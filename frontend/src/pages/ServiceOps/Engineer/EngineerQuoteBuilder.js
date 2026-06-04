/**
 * EngineerQuoteBuilder — create / edit / send a quote.
 *
 * Iter 216h129. Light-mode GymAxis brand.
 *
 * Routes: /svc/engineer/quotes/new        (create)
 *         /svc/engineer/quotes/:id        (view/edit)
 *
 * Backend:
 *   POST  /api/svc/engineer/quotes
 *   GET   /api/svc/engineer/quotes/:id
 *   PATCH /api/svc/engineer/quotes/:id
 *   GET   /api/svc/engineer/quotes/:id.pdf
 *   POST  /api/svc/engineer/quotes/:id/send
 *   POST  /api/svc/engineer/quotes/:id/mark
 *   POST  /api/svc/engineer/quotes/:id/duplicate
 *   POST  /api/svc/engineer/quotes/:id/convert-to-job
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Send, FileDown, Plus, Trash2, Save,
  CheckCircle2, XCircle, Copy, Briefcase, Loader2, Mail, Search, BookmarkPlus,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { outboxPost } from '@/utils/engineerOutbox';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const KIND_OPTIONS = [
  { id: 'labour',  label: 'Labour' },
  { id: 'part',    label: 'Part' },
  { id: 'travel',  label: 'Travel' },
  { id: 'callout', label: 'Callout' },
  { id: 'other',   label: 'Other' },
];

const emptyLine = (kind = 'labour') => ({
  kind, description: '', quantity: 1, unit_price: 0, notes: '',
});

// Iter 220cr — labels for default-rate prefill so the engineer
// can see WHICH preset filled the line.
const DEFAULT_DESCRIPTIONS = {
  callout: 'Callout fee',
  labour:  'Labour',
  travel:  'Mileage',
};

function computeTotals(lines, vatRate, discountPct) {
  const subtotal = lines.reduce((acc, ln) => acc + (Number(ln.quantity) || 0) * (Number(ln.unit_price) || 0), 0);
  const discountAmount = Number(discountPct) > 0 ? subtotal * (Number(discountPct) / 100) : 0;
  const subAfter = subtotal - discountAmount;
  const vatAmount = subAfter * (Number(vatRate) / 100);
  const total = subAfter + vatAmount;
  return {
    subtotal: Math.round(subtotal * 100) / 100,
    discountAmount: Math.round(discountAmount * 100) / 100,
    vatAmount: Math.round(vatAmount * 100) / 100,
    total: Math.round(total * 100) / 100,
  };
}

export default function EngineerQuoteBuilder() {
  const navigate = useNavigate();
  const { id: quoteId } = useParams();
  const [params] = useSearchParams();
  const isNew = !quoteId;
  const caseHint = params.get('case_id');
  // Iter 220p1 — localization (currency + tax vocabulary). Defaults to UK.
  const loc = useLocalization();
  const fmtGBP = useCallback((n) => formatMoney(n, loc), [loc]);
  const sym = loc.currency_symbol || '£';

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [showEmail, setShowEmail] = useState(false);

  const [form, setForm] = useState({
    case_id: caseHint || null,
    customer_name: '',
    customer_email: '',
    customer_phone: '',
    site_name: '',
    site_address: '',
    asset_name: '',
    asset_serial: '',
    // Iter 220cr — engineer can attach multiple machines to one
    // quote (legacy `asset_name` / `asset_serial` stays for back-compat
    // and is auto-populated from machines[0] on save).
    machines: [],
    description_of_work: '',
    lines: [emptyLine('labour')],
    vat_rate: 20,
    discount_pct: 0,
    valid_days: 30,
    valid_until: '',
    notes: '',
    terms: '',
    status: 'draft',
  });
  const [_serverState, setServerState] = useState(null);
  // Iter 220cr — partner-set pricing defaults. Pulled on mount,
  // applied when the engineer picks a `callout`/`labour`/`travel`
  // line kind so the £ auto-populates from Account Settings.
  const [rates, setRates] = useState({
    callout_fee: 0, labour_rate_per_hour: 0, mileage_rate: 0,
  });

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/partners/me`, auth())
      .then((r) => {
        const r2 = r?.data?.partner?.rates || {};
        if (alive) {
          setRates({
            callout_fee: Number(r2.callout_fee || 0),
            labour_rate_per_hour: Number(r2.labour_rate_per_hour || 0),
            mileage_rate: Number(r2.mileage_rate || 0),
          });
        }
      })
      .catch(() => { /* rates default to 0 — no auto-fill */ });
    return () => { alive = false; };
  }, []);

  // Iter 220cr — once rates land on a fresh "new quote" form, prefill
  // the lonely default labour line so engineers don't have to retype.
  useEffect(() => {
    if (!isNew) return;
    setForm((f) => {
      if (f.lines.length !== 1) return f;
      const ln = f.lines[0];
      if (ln.kind !== 'labour' || ln.description || Number(ln.unit_price) > 0) return f;
      if (rates.labour_rate_per_hour <= 0) return f;
      return {
        ...f,
        lines: [{
          ...ln,
          description: DEFAULT_DESCRIPTIONS.labour,
          unit_price: rates.labour_rate_per_hour,
        }],
      };
    });
  }, [rates.labour_rate_per_hour, isNew]);

  const [emailBody, setEmailBody] = useState({ to: '', message: '' });

  // Load existing quote
  const load = useCallback(async () => {
    if (isNew) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/quotes/${quoteId}`, auth());
      setForm({
        ...r.data,
        lines: r.data.lines?.length ? r.data.lines : [emptyLine('labour')],
      });
      setServerState(r.data);
      setEmailBody({ to: r.data.customer_email || '', message: '' });
    } catch (e) {
      notify.error('Failed to load quote', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [quoteId, isNew]);

  useEffect(() => { load(); }, [load]);

  // Iter 216h259 — pre-fill from Lite CRM ?customer_id=...&name=...
  useEffect(() => {
    if (!isNew) return;
    const cid = params.get('customer_id');
    const name = params.get('name');
    if (!cid && !name) return;
    setForm((f) => ({
      ...f,
      customer_name: name || f.customer_name,
      customer_email: params.get('email') || f.customer_email,
      customer_phone: params.get('phone') || f.customer_phone,
      site_name: params.get('site_name') || f.site_name,
      site_address: params.get('site_address') || f.site_address,
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew]);

  const totals = useMemo(
    () => computeTotals(form.lines, form.vat_rate, form.discount_pct),
    [form.lines, form.vat_rate, form.discount_pct],
  );

  const handleLineChange = (idx, key, value) => {
    setForm(f => ({
      ...f,
      lines: f.lines.map((ln, i) => {
        if (i !== idx) return ln;
        const next = { ...ln, [key]: value };
        // Iter 220cr — when the engineer switches a line to
        // callout / labour / travel and the line is still at its
        // default (£0 + no description), auto-fill from saved rates.
        if (key === 'kind') {
          const isUntouched = (
            (!ln.description || ln.description === DEFAULT_DESCRIPTIONS[ln.kind])
            && (Number(ln.unit_price) || 0) === 0
          );
          if (isUntouched) {
            if (value === 'callout' && rates.callout_fee > 0) {
              next.description = DEFAULT_DESCRIPTIONS.callout;
              next.unit_price = rates.callout_fee;
              next.quantity = 1;
            } else if (value === 'labour' && rates.labour_rate_per_hour > 0) {
              next.description = DEFAULT_DESCRIPTIONS.labour;
              next.unit_price = rates.labour_rate_per_hour;
            } else if (value === 'travel' && rates.mileage_rate > 0) {
              next.description = DEFAULT_DESCRIPTIONS.travel;
              next.unit_price = rates.mileage_rate;
            }
          }
        }
        return next;
      }),
    }));
  };
  const handleAddLine = (kind = 'labour') => {
    setForm(f => {
      const line = emptyLine(kind);
      // Same prefill on a brand-new line so engineers can spam
      // "Add line → Labour" and get sensible defaults each time.
      if (kind === 'callout' && rates.callout_fee > 0) {
        line.description = DEFAULT_DESCRIPTIONS.callout;
        line.unit_price = rates.callout_fee;
      } else if (kind === 'labour' && rates.labour_rate_per_hour > 0) {
        line.description = DEFAULT_DESCRIPTIONS.labour;
        line.unit_price = rates.labour_rate_per_hour;
      } else if (kind === 'travel' && rates.mileage_rate > 0) {
        line.description = DEFAULT_DESCRIPTIONS.travel;
        line.unit_price = rates.mileage_rate;
      }
      return { ...f, lines: [...f.lines, line] };
    });
  };
  const handleRemoveLine = (idx) => {
    setForm(f => ({
      ...f,
      lines: f.lines.length > 1 ? f.lines.filter((_, i) => i !== idx) : f.lines,
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        lines: form.lines.filter(ln => (ln.description || '').trim()),
      };
      if (!payload.customer_name) {
        notify.error('Customer name required');
        return;
      }
      if (!payload.lines.length) {
        notify.error('Add at least one line item');
        return;
      }
      if (isNew) {
        // Iter 220ea·35 — offline-safe create. Route through the engineer
        // outbox: if there's no signal the quote is queued and replayed on
        // reconnect. A stable Idempotency-Key (reused on every replay)
        // guarantees the server never creates a duplicate.
        const idemKey = (window.crypto?.randomUUID?.() || `q-${Date.now()}-${Math.random().toString(36).slice(2)}`);
        const r = await outboxPost(`${API}/svc/engineer/quotes`, payload, {
          headers: { ...auth().headers, 'Idempotency-Key': idemKey },
          kind: 'quote-create',
          label: `Quote for ${payload.customer_name}`,
        });
        if (r.queued) {
          notify.success('Saved offline', 'This quote will sync automatically when you\u2019re back online.');
          navigate('/svc/engineer/quotes', { replace: true });
          return;
        }
        notify.success(`Quote ${r.data.quote_number} created`);
        navigate(`/svc/engineer/quotes/${r.data.id}`, { replace: true });
      } else {
        const r = await axios.patch(`${API}/svc/engineer/quotes/${quoteId}`, payload, auth());
        setForm({ ...r.data, lines: r.data.lines || [] });
        setServerState(r.data);
        notify.success('Quote saved');
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
      await axios.post(
        `${API}/svc/engineer/quotes/${quoteId}/send`,
        { to: emailBody.to || form.customer_email, message: emailBody.message },
        auth(),
      );
      notify.success(`Quote emailed to ${emailBody.to || form.customer_email}`);
      setShowEmail(false);
      load();
    } catch (e) {
      notify.error('Send failed', e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  const handleDownloadPdf = async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/quotes/${quoteId}.pdf`, {
        ...auth(), responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${form.quote_number || 'quote'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      notify.error('Download failed', e?.response?.data?.detail || e.message);
    }
  };

  const handleMark = async (status) => {
    try {
      await axios.post(`${API}/svc/engineer/quotes/${quoteId}/mark`, { status }, auth());
      notify.success(`Marked as ${status}`);
      load();
    } catch (e) {
      notify.error('Update failed', e?.response?.data?.detail || e.message);
    }
  };

  const handleDuplicate = async () => {
    try {
      const r = await axios.post(`${API}/svc/engineer/quotes/${quoteId}/duplicate`, {}, auth());
      notify.success(`Duplicated as ${r.data.quote_number}`);
      navigate(`/svc/engineer/quotes/${r.data.id}`);
    } catch (e) {
      notify.error('Duplicate failed');
    }
  };

  const handleConvert = async () => {
    try {
      const r = await axios.post(`${API}/svc/engineer/quotes/${quoteId}/convert-to-job`, {}, auth());
      notify.success(`Converted to job ${r.data.case_reference}`);
      load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Convert failed');
    }
  };

  const handleInvoiceFromQuote = async () => {
    try {
      const r = await axios.post(`${API}/svc/engineer/invoices/from-quote/${quoteId}`, {}, auth());
      notify.success(`Invoice ${r.data.invoice_number} created`);
      navigate(`/svc/engineer/invoices/${r.data.id}`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Invoice creation failed');
    }
  };

  const readOnly = !isNew && !['draft', 'sent'].includes(form.status);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        <Loader2 className="animate-spin mr-2" size={18} /> Loading quote…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-quote-builder">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/quotes')}
              className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              data-testid="quote-builder-back"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">GymAxis Quote</p>
              <h1 className="text-xl font-extrabold text-slate-900 truncate">
                {isNew ? 'New quote' : form.quote_number}
              </h1>
              {!isNew && (
                <p className="text-xs text-slate-500 capitalize">
                  {form.status}
                  {form.sent_at ? ` · Sent ${new Date(form.sent_at).toLocaleDateString('en-GB')}` : ''}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isNew && (
              <>
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold hover:bg-slate-50"
                  data-testid="quote-builder-pdf-btn"
                >
                  <FileDown size={14} /> PDF
                </button>
                <button
                  type="button"
                  onClick={() => setShowEmail(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow"
                  data-testid="quote-builder-send-btn"
                >
                  <Send size={14} /> Send
                </button>
              </>
            )}
            {!readOnly && (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold disabled:opacity-50"
                data-testid="quote-builder-save-btn"
              >
                {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
                {isNew ? 'Create' : 'Save'}
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-24 space-y-4">
        {/* Status / quick actions */}
        {!isNew && (
          <div className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center flex-wrap gap-3" data-testid="quote-builder-status-bar">
            <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">Update status</p>
            <button
              type="button"
              disabled={form.status === 'accepted'}
              onClick={() => handleMark('accepted')}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs font-bold disabled:opacity-40"
              data-testid="quote-builder-mark-accepted"
            >
              <CheckCircle2 size={12} /> Accepted
            </button>
            <button
              type="button"
              disabled={form.status === 'declined'}
              onClick={() => handleMark('declined')}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-rose-200 bg-rose-50 text-rose-700 text-xs font-bold disabled:opacity-40"
              data-testid="quote-builder-mark-declined"
            >
              <XCircle size={12} /> Declined
            </button>
            <button
              type="button"
              onClick={handleDuplicate}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-slate-700 text-xs font-bold"
              data-testid="quote-builder-duplicate"
            >
              <Copy size={12} /> Duplicate
            </button>
            {form.status === 'accepted' && !form.converted_case_id && (
              <button
                type="button"
                onClick={handleConvert}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 text-xs font-bold"
                data-testid="quote-builder-convert-to-job"
              >
                <Briefcase size={12} /> Convert to job
              </button>
            )}
            {/* Iter 216h257 — surface "Convert to invoice" for both
                sent + accepted quotes (the backend already accepts both)
                so the engineer doesn't have to jump back and mark the
                quote accepted before invoicing. */}
            {(form.status === 'accepted' || form.status === 'sent') && !form.linked_invoice_id && (
              <button
                type="button"
                onClick={handleInvoiceFromQuote}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs font-bold"
                data-testid="quote-builder-invoice-from-quote"
              >
                <CheckCircle2 size={12} /> Convert to invoice
              </button>
            )}
            {form.linked_invoice_number && (
              <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs font-bold">
                Invoiced as {form.linked_invoice_number}
              </span>
            )}
            {form.converted_case_id && (
              <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-violet-200 bg-violet-50 text-violet-700 text-xs font-bold">
                <Briefcase size={12} /> Converted → {form.converted_case_reference}
              </span>
            )}
          </div>
        )}

        {/* Customer + Site */}
        <Section title="Customer &amp; Site">
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
            <TextField label="Customer name *" value={form.customer_name} onChange={v => setForm(f => ({ ...f, customer_name: v }))} testid="qb-customer-name" readOnly={readOnly} />
            <TextField label="Customer email" type="email" value={form.customer_email} onChange={v => setForm(f => ({ ...f, customer_email: v }))} testid="qb-customer-email" readOnly={readOnly} />
            <TextField label="Customer phone" value={form.customer_phone} onChange={v => setForm(f => ({ ...f, customer_phone: v }))} testid="qb-customer-phone" readOnly={readOnly} />
            <TextField label="Site name" value={form.site_name} onChange={v => setForm(f => ({ ...f, site_name: v }))} testid="qb-site-name" readOnly={readOnly} />
            <TextField label="Site address" value={form.site_address} onChange={v => setForm(f => ({ ...f, site_address: v }))} testid="qb-site-address" readOnly={readOnly} fullWidth />
          </div>
        </Section>

        {/* Machines — Iter 220cr: engineers can attach multiple
            machines to a single quote (legacy asset_name / serial
            fields below stay editable for back-compat). */}
        <Section title="Machines">
          <MachinesEditor
            machines={form.machines || []}
            onChange={(list) => setForm((f) => ({
              ...f,
              machines: list,
              // Mirror first row into legacy single-asset fields so
              // the PDF + Sicon push still has something to work with.
              asset_name:   (list[0]?.name || f.asset_name) ?? '',
              asset_serial: (list[0]?.serial || f.asset_serial) ?? '',
            }))}
            readOnly={readOnly}
          />
          <div className="grid md:grid-cols-2 gap-3 mt-3">
            <TextField label="Asset name (legacy)" value={form.asset_name} onChange={v => setForm(f => ({ ...f, asset_name: v }))} testid="qb-asset-name" readOnly={readOnly} />
            <TextField label="Serial number (legacy)" value={form.asset_serial} onChange={v => setForm(f => ({ ...f, asset_serial: v }))} testid="qb-asset-serial" readOnly={readOnly} />
          </div>
        </Section>

        {/* Description */}
        <Section title="Description of work">
          <textarea
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-blue-400 focus:outline-none"
            rows={3}
            placeholder="What work is being quoted for?"
            value={form.description_of_work}
            disabled={readOnly}
            onChange={e => setForm(f => ({ ...f, description_of_work: e.target.value }))}
            data-testid="qb-description"
          />
        </Section>

        {/* Lines */}
        <Section title="Line items">
          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200 text-xs">
                  <th className="text-left py-2 pr-2">Type</th>
                  <th className="text-left py-2 pr-2">Description</th>
                  <th className="text-right py-2 pr-2 w-20">Qty</th>
                  <th className="text-right py-2 pr-2 w-28">Unit {sym}</th>
                  <th className="text-right py-2 pr-2 w-28">Total {sym}</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody>
                {form.lines.map((ln, i) => {
                  const lineTotal = (Number(ln.quantity) || 0) * (Number(ln.unit_price) || 0);
                  return (
                    <tr key={i} className="border-b border-slate-100" data-testid={`qb-line-${i}`}>
                      <td className="py-1.5 pr-2">
                        <select
                          className="text-xs border border-slate-200 rounded px-1.5 py-1 bg-white"
                          value={ln.kind}
                          disabled={readOnly}
                          onChange={e => handleLineChange(i, 'kind', e.target.value)}
                          data-testid={`qb-line-${i}-kind`}
                        >
                          {KIND_OPTIONS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="text"
                          className="w-full text-sm border border-slate-200 rounded px-2 py-1 bg-white"
                          value={ln.description}
                          disabled={readOnly}
                          onChange={e => handleLineChange(i, 'description', e.target.value)}
                          placeholder="e.g. Treadmill belt replacement"
                          data-testid={`qb-line-${i}-desc`}
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="number" step="0.5"
                          className="w-full text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums"
                          value={ln.quantity}
                          disabled={readOnly}
                          onChange={e => handleLineChange(i, 'quantity', e.target.value)}
                          data-testid={`qb-line-${i}-qty`}
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="number" step="0.01"
                          className="w-full text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums"
                          value={ln.unit_price}
                          disabled={readOnly}
                          onChange={e => handleLineChange(i, 'unit_price', e.target.value)}
                          data-testid={`qb-line-${i}-unit`}
                        />
                      </td>
                      <td className="py-1.5 pr-2 text-right font-semibold text-slate-700 tabular-nums">
                        {fmtGBP(lineTotal)}
                      </td>
                      <td className="py-1.5">
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => handleRemoveLine(i)}
                            className="p-1 text-slate-400 hover:text-rose-600"
                            aria-label="Remove line"
                            data-testid={`qb-line-${i}-remove`}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!readOnly && (
            <div className="flex gap-2 flex-wrap mt-3" data-testid="qb-add-line-bar">
              {KIND_OPTIONS.map(k => (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => handleAddLine(k.id)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-slate-700 text-xs font-bold hover:bg-slate-50"
                  data-testid={`qb-add-line-${k.id}`}
                >
                  <Plus size={12} /> {k.label}
                </button>
              ))}
            </div>
          )}
        </Section>

        {/* Totals + VAT + Discount */}
        <Section title="Totals">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">{loc.tax_label} rate %</label>
                <input
                  type="number" step="0.5"
                  className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums"
                  value={form.vat_rate}
                  disabled={readOnly}
                  onChange={e => setForm(f => ({ ...f, vat_rate: Number(e.target.value) }))}
                  data-testid="qb-vat-rate"
                />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">Discount %</label>
                <input
                  type="number" step="0.5"
                  className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums"
                  value={form.discount_pct}
                  disabled={readOnly}
                  onChange={e => setForm(f => ({ ...f, discount_pct: Number(e.target.value) }))}
                  data-testid="qb-discount-pct"
                />
              </div>
              {isNew && (
                <div className="flex items-center gap-3">
                  <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 w-28">Valid (days)</label>
                  <input
                    type="number"
                    className="w-24 text-sm text-right border border-slate-200 rounded px-2 py-1 bg-white tabular-nums"
                    value={form.valid_days}
                    onChange={e => setForm(f => ({ ...f, valid_days: Number(e.target.value) }))}
                    data-testid="qb-valid-days"
                  />
                </div>
              )}
            </div>
            <div className="space-y-1.5 text-sm bg-slate-50 rounded-xl p-4" data-testid="qb-totals-summary">
              <div className="flex justify-between text-slate-600">
                <span>Subtotal</span><span className="tabular-nums">{fmtGBP(totals.subtotal)}</span>
              </div>
              {totals.discountAmount > 0 && (
                <div className="flex justify-between text-rose-600">
                  <span>Discount ({form.discount_pct}%)</span>
                  <span className="tabular-nums">-{fmtGBP(totals.discountAmount)}</span>
                </div>
              )}
              <div className="flex justify-between text-slate-600">
                <span>{loc.tax_label} ({form.vat_rate}%)</span><span className="tabular-nums">{fmtGBP(totals.vatAmount)}</span>
              </div>
              <div className="border-t border-slate-200 pt-2 flex justify-between text-lg font-extrabold text-slate-900">
                <span>Total</span><span className="tabular-nums text-blue-700">{fmtGBP(totals.total)}</span>
              </div>
            </div>
          </div>
        </Section>

        {/* Notes + terms */}
        <Section title="Notes &amp; terms">
          <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Notes (internal/customer)</label>
          <textarea
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 mb-3"
            rows={2}
            disabled={readOnly}
            value={form.notes}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            data-testid="qb-notes"
          />
          <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Terms &amp; conditions</label>
          <textarea
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900"
            rows={3}
            disabled={readOnly}
            value={form.terms}
            onChange={e => setForm(f => ({ ...f, terms: e.target.value }))}
            placeholder="e.g. Quote valid 30 days. Payment terms net 14."
            data-testid="qb-terms"
          />
        </Section>
      </main>

      {/* Email send modal */}
      {showEmail && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-4" data-testid="qb-email-modal">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl border border-slate-200">
            <div className="flex items-center gap-2 mb-3">
              <Mail size={18} className="text-blue-600" />
              <h3 className="text-base font-bold text-slate-900">Email this quote</h3>
            </div>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">To</label>
            <input
              type="email"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3"
              value={emailBody.to}
              onChange={e => setEmailBody(b => ({ ...b, to: e.target.value }))}
              data-testid="qb-email-to"
            />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Personal message (optional)</label>
            <textarea
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-4"
              rows={3}
              value={emailBody.message}
              onChange={e => setEmailBody(b => ({ ...b, message: e.target.value }))}
              placeholder="Hi Daniel, please find attached the quote we discussed…"
              data-testid="qb-email-message"
            />
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setShowEmail(false)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm font-bold"
                data-testid="qb-email-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={sending || !emailBody.to}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50"
                data-testid="qb-email-send"
              >
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

const TextField = ({ label, value, onChange, type = 'text', testid, readOnly, fullWidth }) => (
  <div className={fullWidth ? 'md:col-span-2' : ''}>
    <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">{label}</label>
    <input
      type={type}
      className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-blue-400 focus:outline-none disabled:bg-slate-50"
      value={value || ''}
      readOnly={readOnly}
      onChange={e => onChange(e.target.value)}
      data-testid={testid}
    />
  </div>
);


// Iter 216h259 — Lite CRM autocomplete for Customer & Site
// Iter 216h261 — auto-suggest "Save this customer?" banner
function CustomerPicker({ customer, onPick, onSaveCurrent }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [open, setOpen] = useState(false);
  const [suggestState, setSuggestState] = useState({ found: null, dismissed: false, saving: false });

  useEffect(() => {
    if (!q || q.length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const id = setTimeout(async () => {
      setLoadingResults(true);
      try {
        const r = await axios.get(`${API}/svc/engineer/customers/search`, {
          ...auth(),
          params: { q, limit: 8 },
        });
        if (!cancelled) {
          setResults(r.data?.results || []);
          setOpen(true);
        }
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setLoadingResults(false);
      }
    }, 220);
    return () => { cancelled = true; clearTimeout(id); };
  }, [q]);

  // Debounced lookup probe so we know whether to nudge "Save?"
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
    <div className="relative mb-3" data-testid="qb-customer-picker">
      <div className="flex items-stretch gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => q.length >= 2 && setOpen(true)}
            placeholder="Search saved customers…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:border-blue-400 focus:outline-none"
            data-testid="qb-customer-search"
          />
        </div>
        <button
          type="button"
          onClick={onSaveCurrent}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50"
          title="Save current customer details to Lite CRM"
          data-testid="qb-customer-save"
        >
          <BookmarkPlus size={14} /> Save
        </button>
      </div>
      {open && (results.length > 0 || loadingResults) ? (
        <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto"
             data-testid="qb-customer-results">
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
              data-testid={`qb-customer-result-${c.id}`}
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
          data-testid="qb-customer-suggest"
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
              data-testid="qb-customer-suggest-save"
            >
              {suggestState.saving ? <Loader2 size={12} className="animate-spin" /> : <BookmarkPlus size={12} />}
              Save
            </button>
            <button
              type="button"
              onClick={() => setSuggestState((s) => ({ ...s, dismissed: true }))}
              className="inline-flex items-center justify-center w-6 h-6 rounded-md border border-blue-200 bg-white hover:bg-blue-100 text-blue-700"
              data-testid="qb-customer-suggest-dismiss"
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


// ─── MachinesEditor ──────────────────────────────────────────────
// Iter 220cr. Lets the engineer attach multiple machines to a
// single quote (the legacy `asset_name` / `asset_serial` pair stays
// editable below for back-compat with the PDF + Sicon payload).
function MachinesEditor({ machines, onChange, readOnly }) {
  const add = () => onChange([...(machines || []), { name: '', serial: '', notes: '' }]);
  const update = (i, key, val) => onChange(
    machines.map((m, idx) => idx === i ? { ...m, [key]: val } : m),
  );
  const remove = (i) => onChange(machines.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-2" data-testid="qb-machines">
      {machines.length === 0 && (
        <p className="text-[11px] text-slate-500 italic">
          No machines attached. Add one or more — each will be listed on the quote PDF.
        </p>
      )}
      {machines.map((m, i) => (
        <div
          key={i}
          className="grid grid-cols-12 gap-2 items-center bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5"
          data-testid={`qb-machine-${i}`}
        >
          <input
            type="text"
            value={m.name || ''}
            onChange={(e) => update(i, 'name', e.target.value)}
            placeholder="Machine name (e.g. Treadmill #4)"
            disabled={readOnly}
            className="col-span-5 text-sm border border-slate-200 rounded px-2 py-1 bg-white"
            data-testid={`qb-machine-${i}-name`}
          />
          <input
            type="text"
            value={m.serial || ''}
            onChange={(e) => update(i, 'serial', e.target.value)}
            placeholder="Serial"
            disabled={readOnly}
            className="col-span-3 text-sm border border-slate-200 rounded px-2 py-1 bg-white font-mono"
            data-testid={`qb-machine-${i}-serial`}
          />
          <input
            type="text"
            value={m.notes || ''}
            onChange={(e) => update(i, 'notes', e.target.value)}
            placeholder="Notes (optional)"
            disabled={readOnly}
            className="col-span-3 text-sm border border-slate-200 rounded px-2 py-1 bg-white"
            data-testid={`qb-machine-${i}-notes`}
          />
          {!readOnly && (
            <button
              type="button"
              onClick={() => remove(i)}
              className="col-span-1 p-1.5 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 inline-flex items-center justify-center"
              aria-label="Remove machine"
              data-testid={`qb-machine-${i}-remove`}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      ))}
      {!readOnly && (
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-slate-300 bg-white text-xs font-bold text-slate-600 hover:bg-slate-50"
          data-testid="qb-machine-add"
        >
          <Plus size={12} /> Add machine
        </button>
      )}
    </div>
  );
}
