/**
 * GymAxis Memberships — Monthly class invoicing.
 *
 * Two use-cases in one tab:
 *   1. Pick a month → preview what each member would be invoiced for
 *      the classes they booked/attended → generate (and optionally
 *      email) invoices in one click.
 *   2. Browse all previously-generated invoices with status chips and
 *      a "Send" shortcut for drafts.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { FileText, Mail, Eye, CheckCircle2, Clock, XCircle, Send, RefreshCcw, Users, Calendar, Receipt, Link as LinkIcon, Zap } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import EmptyState from '@/components/shared/EmptyState';
import Button from '@/components/shared/Button';

const STATUS_STYLES = {
  draft: 'bg-zinc-500/15 text-zinc-300',
  sent: 'bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[color:var(--color-brand-cyan)]',
  paid: 'bg-emerald-500/15 text-emerald-300',
  void: 'bg-red-500/15 text-red-300',
};
const STATUS_ICON = { draft: Clock, sent: Send, paid: CheckCircle2, void: XCircle };

function currentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function formatPeriodLabel(p) {
  if (!p) return '';
  try {
    const [y, m] = p.split('-').map((s) => parseInt(s, 10));
    return new Date(y, m - 1, 1).toLocaleString('en-GB', { month: 'long', year: 'numeric' });
  } catch {
    return p;
  }
}

function Money({ pence }) {
  const v = typeof pence === 'number' ? pence : 0;
  return <span>£{(v / 100).toFixed(2)}</span>;
}

export default function InvoicingTab({ API, headers }) {
  const [period, setPeriod] = useState(currentPeriod());
  const [attendedOnly, setAttendedOnly] = useState(false);
  const [includeSmoothed, setIncludeSmoothed] = useState(true);
  const [defaultRate, setDefaultRate] = useState(''); // pounds
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [sendEmail, setSendEmail] = useState(false);
  const [invoices, setInvoices] = useState([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [siblingPct, setSiblingPct] = useState(0);
  const [siblingSaving, setSiblingSaving] = useState(false);
  const [autoPayMembers, setAutoPayMembers] = useState(new Set());

  // Load sibling-discount setting + auto-pay roster once on mount
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/billing/sibling-discount`, { headers });
        if (!cancel) setSiblingPct(Number(data?.pct || 0));
      } catch { /* non-fatal */ }
      try {
        const { data } = await axios.get(`${API}/memberships/billing/autopay/members`, { headers });
        if (!cancel) setAutoPayMembers(new Set((data?.members || []).map((m) => m.id)));
      } catch { /* non-fatal */ }
    })();
    return () => { cancel = true; };
  }, [API, headers]);

  const saveSibling = async () => {
    setSiblingSaving(true);
    try {
      const pct = Math.max(0, Math.min(50, Math.round(Number(siblingPct) || 0)));
      await axios.post(`${API}/memberships/billing/sibling-discount`, { pct }, { headers });
      setSiblingPct(pct);
      notify.success(pct === 0 ? 'Sibling discount disabled' : `Sibling discount set to ${pct}%`);
    } catch (e) {
      notifyApiError(notify, e, 'Could not save sibling discount');
    } finally {
      setSiblingSaving(false);
    }
  };

  const runPreview = useCallback(async () => {
    setLoading(true);
    setPreview(null);
    try {
      const payload = {
        period,
        include_attended_only: attendedOnly,
        include_smoothed: includeSmoothed,
      };
      if (defaultRate !== '') payload.default_per_class_pence = Math.round(Number(defaultRate) * 100);
      const { data } = await axios.post(`${API}/memberships/billing/monthly-invoice/preview`, payload, { headers });
      setPreview(data);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to run preview');
    } finally {
      setLoading(false);
    }
  }, [API, headers, period, attendedOnly, includeSmoothed, defaultRate]);

  const loadInvoices = useCallback(async () => {
    setInvoicesLoading(true);
    try {
      const { data } = await axios.get(`${API}/memberships/billing/invoices`, { headers });
      setInvoices(data.invoices || []);
    } catch {
      // silent — empty state is fine
    } finally {
      setInvoicesLoading(false);
    }
  }, [API, headers]);

  useEffect(() => { loadInvoices(); }, [loadInvoices]);
  useEffect(() => { runPreview();   }, [period]);

  const generate = async () => {
    if (!preview || !preview.invoices?.length) {
      notify.info('Nothing to invoice for this period');
      return;
    }
    setGenerating(true);
    try {
      const payload = {
        period,
        include_attended_only: attendedOnly,
        include_smoothed: includeSmoothed,
        send_email: sendEmail,
      };
      if (defaultRate !== '') payload.default_per_class_pence = Math.round(Number(defaultRate) * 100);
      const { data } = await axios.post(`${API}/memberships/billing/monthly-invoice/generate`, payload, { headers });
      const em = data.email || {};
      const emailBit = sendEmail
        ? ` · ${em.sent} emailed, ${em.skipped_no_email} without email, ${em.failed} failed`
        : '';
      notify.success(`Generated ${data.generated_count} invoice${data.generated_count === 1 ? '' : 's'}${emailBit}`);
      await loadInvoices();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate invoices');
    } finally {
      setGenerating(false);
    }
  };

  const sendOne = async (inv) => {
    try {
      await axios.post(`${API}/memberships/billing/invoices/${inv.id}/send`, {}, { headers });
      notify.success(`Sent to ${inv.member_email}`);
      await loadInvoices();
    } catch (e) {
      notifyApiError(notify, e, 'Send failed');
    }
  };

  const copyPayLink = async (inv) => {
    try {
      const { data } = await axios.post(`${API}/memberships/billing/invoices/${inv.id}/checkout`, {}, { headers });
      try { await navigator.clipboard.writeText(data.checkout_url); } catch { /* fall through */ }
      notify.success('Pay link copied to clipboard');
    } catch (e) {
      notifyApiError(notify, e, 'Could not create pay link');
    }
  };

  const setStatus = async (inv, status) => {
    try {
      await axios.patch(`${API}/memberships/billing/invoices/${inv.id}/status`, { status }, { headers });
      await loadInvoices();
    } catch (e) {
      notifyApiError(notify, e, 'Status update failed');
    }
  };

  // Month picker options — last 12 + current + next
  const periodOptions = useMemo(() => {
    const opts = [];
    const now = new Date();
    for (let i = -12; i <= 1; i += 1) {
      const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
      const v = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      opts.push({ v, label: formatPeriodLabel(v) });
    }
    return opts.reverse();
  }, []);

  return (
    <div data-testid="mbr-invoicing">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--theme-text-muted)]">Billing</div>
          <h2 className="mt-1 text-2xl font-black tracking-tight">Monthly class invoicing</h2>
          <p className="mt-1 text-sm text-[color:var(--theme-text-muted)] max-w-xl">
            Bill every member for the classes they booked or attended in a month in one click — or pro-rata an annual plan across 12 months for predictable monthly payments.
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="mt-6 rounded-xl border border-[color:var(--theme-border)] p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Period</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-2 text-sm"
            data-testid="mbr-invoicing-period">
            {periodOptions.map((p) => (<option key={p.v} value={p.v}>{p.label}</option>))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Default £/class (blank = auto)</span>
          <input type="number" step="0.01" value={defaultRate} onChange={(e) => setDefaultRate(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-2 text-sm"
            placeholder="Auto — lowest PAYG plan"
            data-testid="mbr-invoicing-rate" />
        </label>
        <label className="flex items-center gap-2 mt-5 text-sm">
          <input type="checkbox" checked={attendedOnly} onChange={(e) => setAttendedOnly(e.target.checked)}
            data-testid="mbr-invoicing-attended-only" />
          <span className="text-[color:var(--theme-text-muted)]">Attended classes only</span>
        </label>
        <label className="flex items-center gap-2 mt-5 text-sm">
          <input type="checkbox" checked={includeSmoothed} onChange={(e) => setIncludeSmoothed(e.target.checked)}
            data-testid="mbr-invoicing-smoothed" />
          <span className="text-[color:var(--theme-text-muted)]">Include pro-rata plan installments</span>
        </label>
      </div>

      {/* Summary + actions */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          variant="secondary" size="md" icon={RefreshCcw}
          loading={loading}
          onClick={runPreview} disabled={loading}
          data-testid="mbr-invoicing-refresh"
        >
          {loading ? 'Loading…' : 'Refresh preview'}
        </Button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)}
            data-testid="mbr-invoicing-send-email" />
          <span>Email invoices to members after generating</span>
        </label>
        {/* Iter 215z — Sibling discount setting */}
        <div className="flex items-center gap-2 text-sm sm:ml-2 sm:pl-3 sm:border-l border-[color:var(--theme-border)] flex-wrap"
          data-testid="mbr-invoicing-sibling-discount">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">
            Sibling discount
          </span>
          <input type="number" min="0" max="50" step="1" value={siblingPct}
            onChange={(e) => setSiblingPct(e.target.value)}
            className="w-16 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-1 text-sm text-right"
            data-testid="mbr-invoicing-sibling-input"
            title="Percent off each sibling beyond the 1st child in a family's monthly invoice" />
          <span className="text-xs text-[color:var(--theme-text-muted)]">%</span>
          <Button
            variant="secondary" size="sm"
            onClick={saveSibling} disabled={siblingSaving}
            data-testid="mbr-invoicing-sibling-save"
          >
            {siblingSaving ? 'Saving…' : 'Save'}
          </Button>
        </div>
        <div className="ml-auto">
          <Button
            variant="primary" size="md" icon={Receipt}
            loading={generating}
            onClick={generate} disabled={generating || !preview?.invoices?.length}
            data-testid="mbr-invoicing-generate"
          >
            {generating ? 'Generating…' : `Generate invoice${preview?.invoices?.length === 1 ? '' : 's'}`}
          </Button>
        </div>
      </div>

      {/* Preview table */}
      {preview && (
        <div className="mt-4 rounded-xl border border-[color:var(--theme-border)] overflow-hidden" data-testid="mbr-invoicing-preview">
          <div className="flex items-center gap-4 p-3 text-xs font-bold text-[color:var(--theme-text-muted)] bg-[rgb(var(--rgb-brand-cyan)/0.06)]">
            <div className="flex items-center gap-1.5"><Users size={12} />{preview.member_count} member{preview.member_count === 1 ? '' : 's'}</div>
            <div className="flex items-center gap-1.5"><Calendar size={12} />{formatPeriodLabel(preview.period)}</div>
            <div className="ml-auto flex items-center gap-1.5 text-[color:var(--color-brand-cyan)]">
              <FileText size={12} />Total: <Money pence={preview.total_pence} />
            </div>
          </div>
          {preview.invoices?.length === 0 ? (
            <div className="p-8 text-center text-sm text-[color:var(--theme-text-muted)]">
              No members have bookable activity in {formatPeriodLabel(preview.period)} yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[680px]">
                <thead>
                  <tr className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] border-b border-[color:var(--theme-border)]">
                    <th className="px-3 py-2 text-left">Member</th>
                    <th className="px-3 py-2 text-left">Email</th>
                    <th className="px-3 py-2 text-right">Classes</th>
                    <th className="px-3 py-2 text-right">Subtotal</th>
                    <th className="px-3 py-2 text-right">Smoothed</th>
                    <th className="px-3 py-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.invoices.map((row) => (
                    <React.Fragment key={row.member_id}>
                      <tr className="border-b border-[color:var(--theme-border)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.04)]"
                        data-testid={`mbr-invoicing-preview-row-${row.member_id}`}>
                        <td className="px-3 py-2 font-semibold">
                          <div className="flex items-center gap-1.5">
                            <span>{row.member_name}</span>
                            {autoPayMembers.has(row.member_id) && (
                              <span title="Auto-Bill enabled — will charge on the 1st"
                                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider bg-emerald-500/20 text-emerald-300"
                                data-testid={`mbr-invoicing-autopay-${row.member_id}`}>
                                <Zap size={9} />Auto
                              </span>
                            )}
                          </div>
                          {(row.attendees?.length || 0) > 1 && (
                            <div className="mt-1 flex flex-wrap gap-1" data-testid={`mbr-invoicing-attendees-${row.member_id}`}>
                              {row.attendees.filter((a) => a.attendee_kind !== 'smoothed').map((a) => (
                                <span key={a.attendee_name + (a.attendee_sub_profile_id || '')}
                                  className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/5">
                                  {a.attendee_name} · £{(a.subtotal_pence / 100).toFixed(2)}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-[color:var(--theme-text-muted)] text-xs">{row.member_email || '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{row.line_count}</td>
                        <td className="px-3 py-2 text-right tabular-nums"><Money pence={row.subtotal_pence} /></td>
                        <td className="px-3 py-2 text-right tabular-nums">{row.smoothed_pence ? <Money pence={row.smoothed_pence} /> : '—'}</td>
                        <td className="px-3 py-2 text-right font-extrabold tabular-nums"><Money pence={row.total_pence} /></td>
                      </tr>
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Generated invoices */}
      <div className="mt-10 flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--theme-text-muted)]">History</div>
          <h3 className="mt-1 text-xl font-black tracking-tight">Generated invoices</h3>
        </div>
        <button onClick={loadInvoices}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold border border-[color:var(--theme-border)]"
          data-testid="mbr-invoicing-history-refresh">
          <RefreshCcw size={12} /> Refresh
        </button>
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--theme-border)] overflow-hidden" data-testid="mbr-invoicing-history">
        {invoicesLoading ? (
          <div className="p-8 text-center text-sm text-[color:var(--theme-text-muted)]">Loading…</div>
        ) : invoices.length === 0 ? (
          <div className="p-2">
            <EmptyState
              icon={Receipt}
              title="No invoices generated yet"
              hint="Pick a period above and click Preview to see what each member owes for the classes they booked or attended. Generate in one click — emails optional."
              testId="mbr-invoicing-empty"
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
              <tr className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] border-b border-[color:var(--theme-border)]">
                <th className="px-3 py-2 text-left">Period</th>
                <th className="px-3 py-2 text-left">Member</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Lines</th>
                <th className="px-3 py-2 text-right">Total</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => {
                const Icon = STATUS_ICON[inv.status] || Clock;
                const expanded = expandedId === inv.id;
                return (
                  <React.Fragment key={inv.id}>
                    <tr className="border-b border-[color:var(--theme-border)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.04)]"
                      data-testid={`mbr-invoicing-inv-${inv.id}`}>
                      <td className="px-3 py-2 font-semibold">{formatPeriodLabel(inv.period)}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          <div className="font-semibold">{inv.member_name}</div>
                          {autoPayMembers.has(inv.member_id) && (
                            <span title="Auto-Bill enabled — will charge on the 1st"
                              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider bg-emerald-500/20 text-emerald-300"
                              data-testid={`mbr-invoicing-history-autopay-${inv.id}`}>
                              <Zap size={9} />Auto
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-[color:var(--theme-text-muted)]">{inv.member_email || '—'}</div>
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase ${STATUS_STYLES[inv.status] || 'bg-zinc-500/15'}`}>
                          <Icon size={10} />{inv.status}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{inv.lines?.length || 0}</td>
                      <td className="px-3 py-2 text-right font-extrabold tabular-nums"><Money pence={inv.total_pence} /></td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button onClick={() => setExpandedId(expanded ? null : inv.id)}
                            className="p-1.5 rounded hover:bg-white/10 text-[color:var(--theme-text-muted)]"
                            title={expanded ? 'Hide' : 'View lines'}
                            data-testid={`mbr-invoicing-view-${inv.id}`}>
                            <Eye size={12} />
                          </button>
                          {inv.status === 'draft' && inv.member_email && (
                            <button onClick={() => sendOne(inv)}
                              className="p-1.5 rounded hover:bg-white/10 text-[color:var(--color-brand-cyan)]"
                              title="Send by email"
                              data-testid={`mbr-invoicing-send-${inv.id}`}>
                              <Mail size={12} />
                            </button>
                          )}
                          {inv.status !== 'paid' && inv.status !== 'void' && (
                            <button onClick={() => copyPayLink(inv)}
                              className="p-1.5 rounded hover:bg-white/10 text-emerald-300"
                              title="Copy Stripe pay-link"
                              data-testid={`mbr-invoicing-paylink-${inv.id}`}>
                              <LinkIcon size={12} />
                            </button>
                          )}
                          {inv.status === 'sent' && (
                            <button onClick={() => setStatus(inv, 'paid')}
                              className="px-2 py-1 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
                              data-testid={`mbr-invoicing-mark-paid-${inv.id}`}>
                              Mark paid
                            </button>
                          )}
                          {inv.status !== 'paid' && inv.status !== 'void' && (
                            <button onClick={() => setStatus(inv, 'void')}
                              className="px-2 py-1 rounded text-[10px] font-bold bg-red-500/10 text-red-300 hover:bg-red-500/20"
                              data-testid={`mbr-invoicing-void-${inv.id}`}>
                              Void
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr>
                        <td colSpan={6} className="bg-[rgb(var(--rgb-brand-cyan)/0.03)] px-6 py-3">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-1">Line items</div>
                          {(inv.attendees && inv.attendees.filter((a) => a.attendee_kind !== 'smoothed').length > 1) ? (
                            (() => {
                              const groups = {};
                              (inv.lines || []).forEach((l) => {
                                const key = l.kind === 'class' ? (l.attendee_name || 'Account') : 'Account';
                                (groups[key] = groups[key] || []).push(l);
                              });
                              return Object.entries(groups).map(([name, rows]) => {
                                const sub = rows.reduce((s, r) => s + (r.amount_pence || 0), 0);
                                return (
                                  <div key={name} className="mt-2">
                                    <div className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-[color:var(--color-brand-cyan)] mb-1">
                                      {name} · £{(sub / 100).toFixed(2)}
                                    </div>
                                    {rows.map((l, idx) => (
                                      <div key={idx} className="flex justify-between text-xs py-1 border-b border-[color:var(--theme-border)] last:border-0 pl-3">
                                        <span>{l.description}</span>
                                        <span className="tabular-nums font-semibold"><Money pence={l.amount_pence} /></span>
                                      </div>
                                    ))}
                                  </div>
                                );
                              });
                            })()
                          ) : (
                            (inv.lines || []).map((l, idx) => (
                              <div key={idx} className="flex justify-between text-xs py-1 border-b border-[color:var(--theme-border)] last:border-0">
                                <span>{l.description}</span>
                                <span className="tabular-nums font-semibold"><Money pence={l.amount_pence} /></span>
                              </div>
                            ))
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        )}
      </div>
    </div>
  );
}
