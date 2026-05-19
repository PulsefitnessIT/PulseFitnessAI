/**
 * Master Admin — Per-org Billing ledger.
 *
 * Renders inside the Organisations section as a drill-down. Master
 * admin picks an org → opens this panel → can:
 *   • See the bill-to-date balance + recent invoices/payments
 *   • Activate / update the org's manual subscription
 *   • Generate the next invoice from the active modules
 *   • Record a manual payment (BACS, cheque, wire)
 *   • Download an invoice as PDF
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  Loader2, FileText, Download, CheckCircle2, Banknote, CreditCard,
  Mail, X, ChevronLeft, Sparkles, FolderArchive, Receipt, Send,
  Bell, AlarmClock,
} from 'lucide-react';
import DocumentsPanel from './DocumentsPanel';
import HelpHint from '@/components/HelpHint';

const CCY_SYM = { GBP: '£', EUR: '€', USD: '$' };
const MODULE_LABELS = {
  operations: 'Operations',
  memberships: 'Memberships',
  crm: 'CRM',
  marketing: 'Marketing',
  bundle_all: 'All-in-one Bundle',
};

export default function OrgBillingPanel({ org, onBack }) {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showActivate, setShowActivate] = useState(false);
  const [showPay, setShowPay] = useState(null); // invoice obj if paying against one
  const [showSend, setShowSend] = useState(null); // invoice obj if "Send to client"
  const [tab, setTab] = useState('ledger'); // 'ledger' | 'documents'

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/orgs/${org.id}/billing`, { headers });
      setData(r.data);
    } catch (e) {
      notify.error('Failed to load billing');
    } finally {
      setLoading(false);
    }
  }, [API, headers, org.id]);

  useEffect(() => { load(); }, [load]);

  const generateInvoice = async () => {
    try {
      await axios.post(`${API}/master-admin/orgs/${org.id}/billing/invoice`, {}, { headers });
      notify.success('Invoice generated');
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate invoice');
    }
  };

  const downloadPdf = async (invoice) => {
    try {
      const r = await axios.get(
        `${API}/master-admin/orgs/${org.id}/billing/invoice/${invoice.id}/pdf`,
        { headers, responseType: 'blob' },
      );
      const blob = new Blob([r.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${invoice.number}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      notify.error('PDF download failed');
    }
  };

  const remindInvoice = async (invoice) => {
    try {
      const r = await axios.post(
        `${API}/master-admin/orgs/${org.id}/billing/invoice/${invoice.id}/remind`,
        {},
        { headers },
      );
      if (r.data?.delivered) {
        notify.success(`Reminder sent to ${r.data.recipient}`);
      } else {
        notify.info('Reminder share link created — email delivery is currently disabled.');
      }
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to send reminder');
    }
  };

  const runDunningSweep = async () => {
    try {
      const r = await axios.post(
        `${API}/master-admin/billing/dunning/run`,
        {},
        { headers },
      );
      const sent = r.data?.summary?.sent || 0;
      const skipped = r.data?.summary?.skipped || 0;
      if (sent === 0 && skipped === 0) {
        notify.info('Nothing to chase right now — no invoices are past due.');
      } else {
        notify.success(`Dunning sweep complete · ${sent} sent · ${skipped} skipped`);
      }
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Dunning sweep failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }
  if (!data) return null;

  const sub = data.organization.subscription || {};
  const ledger = data.ledger || { invoiced: 0, paid: 0, balance: 0 };
  const ccy = data.organization.currency || 'GBP';
  const sym = CCY_SYM[ccy] || '';

  return (
    <div data-testid="org-billing-panel" className="space-y-6">
      {/* Back */}
      {onBack && (
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900"
          data-testid="org-billing-back"
        >
          <ChevronLeft size={14} /> Back to organisations
        </button>
      )}

      {/* ── Sub-tab strip ── */}
      <div className="flex items-center gap-1 border-b border-zinc-200" role="tablist" data-testid="org-billing-tabs">
        <SubTabBtn
          active={tab === 'ledger'}
          onClick={() => setTab('ledger')}
          icon={Receipt}
          label="Ledger"
          testid="org-billing-tab-ledger"
        />
        <SubTabBtn
          active={tab === 'documents'}
          onClick={() => setTab('documents')}
          icon={FolderArchive}
          label="Documents"
          testid="org-billing-tab-documents"
        />
      </div>

      {tab === 'documents' ? (
        <DocumentsPanel orgId={org.id} />
      ) : (
      <>
      {/* ── Header / org summary ── */}
      <div className="rounded-xl border border-zinc-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-zinc-400">Org · {data.organization.brand}</div>
            <h2 className="text-xl font-bold text-zinc-900 flex items-center gap-1.5">
              {data.organization.name}
              <HelpHint guideId="admin-org-billing" testId="help-hint-org-billing" />
            </h2>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {sub.active_modules ? (
                sub.active_modules.map((m) => (
                  <span key={m} className="px-2 py-0.5 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.1)] text-[var(--color-teal-deep)] font-semibold">
                    {MODULE_LABELS[m] || m}
                  </span>
                ))
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-500">No active subscription</span>
              )}
              {sub.billing_cycle && (
                <span className="px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600">
                  {sub.billing_cycle} · {sub.sites || 1} site{(sub.sites || 1) === 1 ? '' : 's'} · {ccy}
                </span>
              )}
              {sub.manual_billing && (
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-semibold">
                  Manual billing
                </span>
              )}
            </div>
            {sub.next_renewal_at && (
              <div className="text-xs text-zinc-500 mt-1">
                Next renewal {sub.next_renewal_at.slice(0, 10)}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowActivate(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900"
              data-testid="org-billing-activate-btn"
            >
              <Sparkles size={13} /> {sub.active_modules ? 'Update subscription' : 'Activate subscription'}
            </button>
            <button
              onClick={generateInvoice}
              disabled={!sub.active_modules}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white disabled:opacity-40"
              data-testid="org-billing-generate-invoice-btn"
            >
              <FileText size={13} /> Generate invoice
            </button>
            <button
              onClick={runDunningSweep}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
              title="Email reminders for every overdue invoice (7 / 14 / 28 day stages)"
              data-testid="org-billing-run-dunning-btn"
            >
              <AlarmClock size={13} /> Run dunning
            </button>
          </div>
        </div>

        {/* Ledger cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
          <LedgerCard label="Invoiced to date" value={ledger.invoiced} ccy={ccy} testid="ledger-invoiced" />
          <LedgerCard label="Received" value={ledger.paid} ccy={ccy} testid="ledger-paid" tone="ok" />
          <LedgerCard
            label={ledger.balance >= 0 ? 'Bill to date' : 'Credit on account'}
            value={Math.abs(ledger.balance)}
            ccy={ccy}
            testid="ledger-balance"
            tone={ledger.balance > 0 ? 'warn' : 'ok'}
          />
        </div>
      </div>

      {/* ── Invoices ── */}
      <Section title="Invoices" empty="No invoices yet. Activate a subscription and click Generate invoice.">
        {(data.invoices || []).map((inv) => {
          const isOverdue = inv.status !== 'paid' && inv.status !== 'void' && new Date(inv.due_at) < new Date();
          const daysOverdue = isOverdue ? Math.floor((Date.now() - new Date(inv.due_at).getTime()) / 86400000) : 0;
          const reminderCount = (inv.reminders || []).length;
          return (
          <div key={inv.id} className="flex items-center gap-3 p-3 border-b border-zinc-100 last:border-b-0" data-testid={`invoice-row-${inv.number}`}>
            <div className={`w-2 h-10 rounded ${
              inv.status === 'paid' ? 'bg-emerald-500' :
              inv.status === 'void' ? 'bg-zinc-300' :
              isOverdue ? 'bg-rose-500' : 'bg-amber-400'
            }`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-zinc-900">{inv.number}</span>
                {isOverdue && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-rose-100 text-rose-700"
                        data-testid={`invoice-overdue-${inv.number}`}>
                    {daysOverdue}d overdue
                  </span>
                )}
                {reminderCount > 0 && (
                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700"
                        title={`Last reminded ${(inv.reminders[reminderCount - 1].sent_at || '').slice(0, 10)}`}
                        data-testid={`invoice-reminded-${inv.number}`}>
                    <Bell size={10} /> Reminded ×{reminderCount}
                  </span>
                )}
              </div>
              <div className="text-xs text-zinc-500">
                {inv.period_start?.slice(0, 10)} → {inv.period_end?.slice(0, 10)} · {inv.line_items?.length || 0} line{inv.line_items?.length === 1 ? '' : 's'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-zinc-900">{sym}{(inv.total / 100).toFixed(2)}</div>
              <div className="text-[10px] uppercase tracking-wider font-bold mt-0.5"
                   style={{ color: inv.status === 'paid' ? '#059669' : inv.status === 'void' ? '#999' : '#b45309' }}>
                {inv.status}
              </div>
            </div>
            <div className="flex items-center gap-1 ml-3">
              <button
                onClick={() => downloadPdf(inv)}
                className="p-1.5 rounded-md hover:bg-zinc-100"
                title="Download PDF"
                data-testid={`invoice-pdf-${inv.number}`}
              >
                <Download size={14} />
              </button>
              {inv.status !== 'void' && (
                <button
                  onClick={() => setShowSend(inv)}
                  className="p-1.5 rounded-md hover:bg-sky-50 text-zinc-500 hover:text-sky-600"
                  title="Send to client"
                  data-testid={`invoice-send-${inv.number}`}
                >
                  <Send size={14} />
                </button>
              )}
              {inv.status !== 'paid' && inv.status !== 'void' && isOverdue && (
                <button
                  onClick={() => remindInvoice(inv)}
                  className="p-1.5 rounded-md hover:bg-amber-50 text-amber-600 hover:text-amber-700"
                  title="Send reminder"
                  data-testid={`invoice-remind-${inv.number}`}
                >
                  <Bell size={14} />
                </button>
              )}
              {inv.status !== 'paid' && inv.status !== 'void' && (
                <button
                  onClick={() => setShowPay(inv)}
                  className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider rounded bg-emerald-500 text-white hover:bg-emerald-600"
                  data-testid={`invoice-pay-${inv.number}`}
                >
                  Record payment
                </button>
              )}
            </div>
          </div>
          );
        })}
      </Section>

      {/* ── Payments ── */}
      <Section title="Payments received" empty="No manual payments recorded yet.">
        {(data.payments || []).map((p) => (
          <div key={p.id} className="flex items-center gap-3 p-3 border-b border-zinc-100 last:border-b-0" data-testid={`payment-row-${p.id}`}>
            <PaymentMethodIcon method={p.method} />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-zinc-900 capitalize">{p.method}</div>
              <div className="text-xs text-zinc-500">
                {p.paid_at?.slice(0, 10)}
                {p.reference ? ` · ${p.reference}` : ''}
                {p.invoice_id ? ' · against invoice' : ' · on account'}
              </div>
              {p.notes && <div className="text-xs text-zinc-400 mt-0.5 italic">{p.notes}</div>}
            </div>
            <div className="text-sm font-bold text-emerald-600">+{sym}{(p.amount / 100).toFixed(2)}</div>
          </div>
        ))}
      </Section>
      </>
      )}

      {showActivate && (
        <ActivateDialog
          org={data.organization}
          available={data.available_modules}
          supportedCurrencies={data.supported_currencies}
          API={API}
          headers={headers}
          onClose={() => setShowActivate(false)}
          onDone={() => { setShowActivate(false); load(); }}
        />
      )}
      {showPay && (
        <RecordPaymentDialog
          invoice={showPay}
          orgId={org.id}
          API={API}
          headers={headers}
          onClose={() => setShowPay(null)}
          onDone={() => { setShowPay(null); load(); }}
        />
      )}
      {showSend && (
        <SendInvoiceDialog
          invoice={showSend}
          org={data.organization}
          API={API}
          headers={headers}
          onClose={() => setShowSend(null)}
          onDone={() => { setShowSend(null); load(); }}
        />
      )}
    </div>
  );
}


/* ─────────────────── Bits ─────────────────── */

function SubTabBtn({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      data-testid={testid}
      className={`-mb-px inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold border-b-2 transition ${
        active
          ? 'border-[var(--color-brand-cyan)] text-zinc-900'
          : 'border-transparent text-zinc-500 hover:text-zinc-900'
      }`}
    >
      <Icon size={14} /> {label}
    </button>
  );
}

function Section({ title, empty, children }) {
  const isEmpty = !React.Children.count(children) || (Array.isArray(children) && children.length === 0);
  return (
    <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-100 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
        {title}
      </div>
      {isEmpty ? (
        <div className="p-8 text-center text-sm text-zinc-400">{empty}</div>
      ) : (
        children
      )}
    </div>
  );
}

function LedgerCard({ label, value, ccy, tone, testid }) {
  const sym = CCY_SYM[ccy] || '';
  const colour = tone === 'ok' ? 'text-emerald-600' : tone === 'warn' ? 'text-amber-600' : 'text-zinc-900';
  return (
    <div className="rounded-lg border border-zinc-200 p-4 bg-zinc-50/60" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</div>
      <div className={`text-2xl font-extrabold mt-1 ${colour}`}>
        {sym}{(value / 100).toFixed(2)}
      </div>
    </div>
  );
}

function PaymentMethodIcon({ method }) {
  if (method === 'bacs' || method === 'wire') return <Banknote size={18} className="text-emerald-600" />;
  if (method === 'cheque') return <Mail size={18} className="text-zinc-500" />;
  if (method === 'stripe') return <CreditCard size={18} className="text-violet-500" />;
  return <CheckCircle2 size={18} className="text-zinc-400" />;
}


/* ─────────────────── Activate dialog ─────────────────── */

function ActivateDialog({ org, available, supportedCurrencies, API, headers, onClose, onDone }) {
  const sub = org.subscription || {};
  const [modules, setModules] = useState(sub.active_modules || ['operations']);
  const [cycle, setCycle] = useState(sub.billing_cycle || 'monthly');
  const [currency, setCurrency] = useState(sub.billing_currency || 'GBP');
  const [sites, setSites] = useState(sub.sites || 1);
  const [saving, setSaving] = useState(false);

  const toggle = (m) => {
    setModules((prev) => prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]);
  };

  const submit = async () => {
    if (modules.length === 0) {
      notify.error('Select at least one module');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/master-admin/orgs/${org.id}/billing/activate`, {
        active_modules: modules,
        billing_cycle: cycle,
        billing_currency: currency,
        sites: Number(sites) || 1,
        manual_billing: true,
        status: 'active',
      }, { headers });
      notify.success('Subscription activated');
      onDone();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to activate subscription');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog title="Activate subscription" onClose={onClose} testid="activate-sub-dialog">
      <div className="space-y-4 text-sm">
        <div>
          <div className="text-[11px] uppercase tracking-wider font-bold text-zinc-500 mb-2">Modules</div>
          <div className="grid grid-cols-2 gap-2">
            {(available || []).map((m) => (
              <label key={m} className="flex items-center gap-2 px-3 py-2 rounded border border-zinc-200 cursor-pointer hover:border-[var(--color-brand-cyan)]">
                <input type="checkbox" checked={modules.includes(m)} onChange={() => toggle(m)} data-testid={`activate-mod-${m}`} />
                <span className="text-sm font-medium">{MODULE_LABELS[m] || m}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Billing cycle</span>
            <select value={cycle} onChange={(e) => setCycle(e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200 bg-white" data-testid="activate-cycle">
              <option value="monthly">Monthly</option>
              <option value="annual">Annual</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Currency</span>
            <select value={currency} onChange={(e) => setCurrency(e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200 bg-white" data-testid="activate-currency">
              {(supportedCurrencies || ['GBP', 'EUR', 'USD']).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="block col-span-2">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Number of sites</span>
            <input type="number" min={1} value={sites} onChange={(e) => setSites(e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200" data-testid="activate-sites" />
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
          <button
            onClick={submit}
            disabled={saving}
            className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50"
            data-testid="activate-confirm-btn"
          >
            {saving ? 'Activating…' : 'Activate'}
          </button>
        </div>
      </div>
    </Dialog>
  );
}


/* ─────────────────── Record payment dialog ─────────────────── */

function RecordPaymentDialog({ invoice, orgId, API, headers, onClose, onDone }) {
  const [amount, setAmount] = useState((invoice.total / 100).toFixed(2));
  const [method, setMethod] = useState('bacs');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/master-admin/orgs/${orgId}/billing/payment`, {
        invoice_id: invoice.id,
        amount: Math.round(Number(amount) * 100),
        currency: invoice.currency,
        method,
        reference,
        notes,
      }, { headers });
      notify.success('Payment recorded');
      onDone();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to record payment');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog title={`Record payment · ${invoice.number}`} onClose={onClose} testid="record-payment-dialog">
      <div className="space-y-3 text-sm">
        <label className="block">
          <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Amount ({invoice.currency})</span>
          <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200" data-testid="payment-amount" />
        </label>
        <label className="block">
          <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Method</span>
          <select value={method} onChange={(e) => setMethod(e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200 bg-white" data-testid="payment-method">
            <option value="bacs">BACS</option>
            <option value="wire">Wire transfer</option>
            <option value="cheque">Cheque</option>
            <option value="stripe">Stripe (manual)</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Reference</span>
          <input type="text" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. BACS ref TGLC-Apr26" className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200" data-testid="payment-ref" />
        </label>
        <label className="block">
          <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Notes (optional)</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200" data-testid="payment-notes" />
        </label>
        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
          <button onClick={submit} disabled={saving} className="px-4 py-1.5 text-sm font-semibold rounded bg-emerald-600 text-white disabled:opacity-50" data-testid="payment-confirm-btn">
            {saving ? 'Recording…' : 'Record payment'}
          </button>
        </div>
      </div>
    </Dialog>
  );
}


/* ─────────────────── Send invoice dialog ─────────────────── */

function SendInvoiceDialog({ invoice, org, API, headers, onClose, onDone }) {
  const defaultEmail = (org?.primary_contact_email || org?.primary_contact?.email || '').trim();
  const [toEmail, setToEmail] = useState(defaultEmail);
  const [message, setMessage] = useState('');
  const [ttlDays, setTtlDays] = useState(30);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async () => {
    if (!toEmail || toEmail.indexOf('@') < 0) {
      notify.error('A recipient email is required');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/master-admin/orgs/${org.id}/billing/invoice/${invoice.id}/send`,
        { to_email: toEmail, message, ttl_days: Number(ttlDays) || 30 },
        { headers },
      );
      setResult(r.data);
      if (r.data?.delivered_via_email) {
        notify.success(`Invoice sent to ${toEmail}`);
      } else {
        notify.info('Share link created — email delivery is currently disabled, copy the link below to share.');
      }
    } catch (e) {
      notifyApiError(notify, e, 'Failed to send invoice');
    } finally {
      setSaving(false);
    }
  };

  const copyLink = async () => {
    if (!result?.share_url) return;
    try {
      await navigator.clipboard.writeText(result.share_url);
      notify.success('Link copied');
    } catch (e) {
      notify.error('Copy failed');
    }
  };

  return (
    <Dialog title={`Send ${invoice.number} to client`} onClose={onClose} testid="send-invoice-dialog">
      {result ? (
        <div className="space-y-3 text-sm" data-testid="send-invoice-result">
          <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-emerald-800">
            {result.delivered_via_email
              ? `Email delivered to ${result.recipient}.`
              : `Share link created for ${result.recipient}. Email delivery was unavailable — copy the link below.`}
          </div>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Public download link</span>
            <div className="mt-1 flex gap-2">
              <input
                type="text"
                readOnly
                value={result.share_url || ''}
                className="flex-1 px-2 py-1.5 rounded border border-zinc-200 bg-zinc-50 text-xs font-mono"
                data-testid="send-invoice-share-url"
              />
              <button
                onClick={copyLink}
                className="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-900 text-white"
                data-testid="send-invoice-copy-link"
              >
                Copy
              </button>
            </div>
          </label>
          <div className="text-xs text-zinc-500">
            Link expires {result.expires_at ? result.expires_at.slice(0, 10) : '—'}.
          </div>
          <div className="flex justify-end pt-3 border-t border-zinc-100">
            <button
              onClick={onDone}
              className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900"
              data-testid="send-invoice-done"
            >
              Done
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Recipient email</span>
            <input
              type="email"
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              placeholder="finance@client.example"
              className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
              data-testid="send-invoice-email"
            />
            {defaultEmail && toEmail !== defaultEmail && (
              <div className="text-[11px] text-zinc-400 mt-1">
                Pre-filled from primary contact: <button type="button" className="underline" onClick={() => setToEmail(defaultEmail)}>{defaultEmail}</button>
              </div>
            )}
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Message (optional)</span>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Hi Sarah, please find this month's invoice attached. Payment due in 14 days. — Lee"
              className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
              data-testid="send-invoice-message"
            />
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Link valid for (days)</span>
            <input
              type="number"
              min={1}
              max={180}
              value={ttlDays}
              onChange={(e) => setTtlDays(e.target.value)}
              className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
              data-testid="send-invoice-ttl"
            />
          </label>
          <div className="text-xs text-zinc-500 leading-relaxed">
            We'll attach the PDF to the email <em>and</em> include a public download
            link, so the recipient can re-fetch it later even if the attachment is
            stripped.
          </div>
          <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
            <button
              onClick={submit}
              disabled={saving}
              className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50"
              data-testid="send-invoice-confirm"
            >
              {saving ? 'Sending…' : 'Send invoice'}
            </button>
          </div>
        </div>
      )}
    </Dialog>
  );
}


/* ─────────────────── Dialog shell ─────────────────── */

function Dialog({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" data-testid={testid}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <h3 className="text-base font-semibold text-zinc-900">{title}</h3>
          <button onClick={onClose} className="p-1 hover:bg-zinc-100 rounded">
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
