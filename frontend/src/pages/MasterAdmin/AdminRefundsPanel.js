import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { RotateCcw, Search, Loader2, AlertTriangle, CheckCircle2, PoundSterling } from 'lucide-react';

/**
 * AdminRefundsPanel (iter 215c9)
 * Master-admin view to issue Stripe refunds + see recent refund history.
 * Drop-in; currently mounted inside Finance → Refunds in Master Admin.
 */
const AdminRefundsPanel = () => {
  const { API } = useAuth();
  const [list, setList] = useState(null);
  const [days, setDays] = useState(90);
  const [query, setQuery] = useState('');
  const [lookingUp, setLookingUp] = useState(false);
  const [matches, setMatches] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ amount_pence: '', reason: 'requested_by_customer', notes: '' });
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const token = () => localStorage.getItem('token');

  const loadList = async () => {
    try {
      const res = await axios.get(`${API}/admin/refunds`, {
        headers: { Authorization: `Bearer ${token()}` },
        params: { days },
      });
      setList(res.data);
    } catch {
      setList({ items: [], count: 0, total_refunded: 0 });
    }
  };
  useEffect(() => { loadList(); }, [API, days]); // eslint-disable-line

  const lookup = async (e) => {
    e?.preventDefault?.();
    if (!query.trim()) return;
    setLookingUp(true); setSelected(null); setFeedback(null);
    try {
      const res = await axios.get(`${API}/admin/refunds/lookup`, {
        headers: { Authorization: `Bearer ${token()}` },
        params: { query: query.trim() },
      });
      setMatches(res.data.matches || []);
    } catch {
      setMatches([]);
    } finally {
      setLookingUp(false);
    }
  };

  const issue = async () => {
    if (!selected) return;
    setSubmitting(true); setFeedback(null);
    try {
      const body = {
        charge_id: selected.id,
        reason: form.reason,
        notes: form.notes,
      };
      if (form.amount_pence) body.amount_pence = parseInt(form.amount_pence, 10);
      const res = await axios.post(`${API}/admin/refunds`, body, {
        headers: { Authorization: `Bearer ${token()}` },
      });
      setFeedback({ type: 'ok', message: `Refund £${(res.data.refund.amount_pence/100).toFixed(2)} issued.` });
      setSelected(null); setMatches([]); setQuery('');
      setForm({ amount_pence: '', reason: 'requested_by_customer', notes: '' });
      loadList();
    } catch (err) {
      setFeedback({ type: 'err', message: err?.response?.data?.detail || 'Refund failed' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-refunds-panel">
      {/* Issue-refund card */}
      <div className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-brand-blue)]/10 flex items-center justify-center">
            <RotateCcw className="w-5 h-5 text-[var(--color-brand-blue)]" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-[var(--theme-text)]">Issue a refund</h3>
            <p className="text-xs text-[var(--color-text-muted)]">Find a Stripe charge by email, charge id (ch_…), or PaymentIntent (pi_…) and refund full or partial.</p>
          </div>
        </div>

        <form onSubmit={lookup} className="flex gap-2 mb-4">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="customer@email.com, ch_xxx, or pi_xxx"
              data-testid="refunds-lookup-input"
              className="w-full pl-9 pr-3 py-2 rounded-md text-sm border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-blue)]"
            />
          </div>
          <button
            type="submit"
            disabled={lookingUp}
            data-testid="refunds-lookup-btn"
            className="px-4 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-medium hover:opacity-90 flex items-center gap-1.5"
          >
            {lookingUp ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Find
          </button>
        </form>

        {matches.length > 0 && (
          <ul className="border border-[var(--theme-border)] rounded-lg divide-y divide-[var(--theme-border)] mb-4 max-h-64 overflow-y-auto" data-testid="refunds-lookup-matches">
            {matches.map((m) => (
              <li key={m.id} className="p-3 hover:bg-[var(--theme-surface-hover)]">
                <button
                  type="button"
                  onClick={() => setSelected(m)}
                  data-testid={`refunds-match-${m.id}`}
                  className={`w-full text-left ${selected?.id === m.id ? 'text-[var(--color-brand-blue)]' : 'text-[var(--theme-text)]'}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold tabular-nums">
                      £{(m.amount_pence/100).toFixed(2)} {m.currency.toUpperCase()}
                    </span>
                    <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${m.refunded ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-700'}`}>
                      {m.refunded ? 'Refunded' : m.status}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--color-text-muted)] mt-0.5 flex flex-wrap gap-x-3">
                    <span>{m.customer_email || 'no email'}</span>
                    <span>··· {m.last4 || '????'}</span>
                    <span>{m.id}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}

        {selected && (
          <div className="rounded-lg border-2 border-[var(--color-brand-blue)] p-4 space-y-3" data-testid="refunds-issue-form">
            <p className="text-xs font-semibold text-[var(--theme-text)]">
              Refunding <span className="tabular-nums">£{(selected.amount_pence/100).toFixed(2)}</span> · {selected.id}
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs text-[var(--color-text-muted)]">Amount (pence, blank = full)</span>
                <input
                  type="number"
                  min="1"
                  max={selected.amount_pence - selected.amount_refunded_pence}
                  value={form.amount_pence}
                  onChange={(e) => setForm({ ...form, amount_pence: e.target.value })}
                  data-testid="refunds-amount-pence"
                  placeholder={`${selected.amount_pence - (selected.amount_refunded_pence||0)}`}
                  className="w-full mt-1 px-2 py-1.5 text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)]"
                />
              </label>
              <label className="block">
                <span className="text-xs text-[var(--color-text-muted)]">Reason</span>
                <select
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  data-testid="refunds-reason"
                  className="w-full mt-1 px-2 py-1.5 text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)]"
                >
                  <option value="requested_by_customer">Requested by customer</option>
                  <option value="duplicate">Duplicate charge</option>
                  <option value="fraudulent">Fraudulent</option>
                  <option value="other">Other</option>
                </select>
              </label>
            </div>
            <label className="block">
              <span className="text-xs text-[var(--color-text-muted)]">Internal notes</span>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={2}
                maxLength={1000}
                placeholder="Ticket #, context…"
                data-testid="refunds-notes"
                className="w-full mt-1 px-2 py-1.5 text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] resize-none"
              />
            </label>
            <div className="flex items-start gap-2 p-2 rounded-md bg-amber-50 dark:bg-amber-900/30 text-[11px] text-amber-900 dark:text-amber-200">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>Refunds are irreversible. Stripe will notify the customer automatically.</span>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setSelected(null)} className="text-xs px-3 py-1.5 rounded-md border border-[var(--theme-border)]">Cancel</button>
              <button
                onClick={issue}
                disabled={submitting}
                data-testid="refunds-issue-btn"
                className="text-xs px-3 py-1.5 rounded-md bg-red-600 text-white font-medium hover:bg-red-700 inline-flex items-center gap-1.5"
              >
                {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />} Issue refund
              </button>
            </div>
          </div>
        )}

        {feedback && (
          <div
            role="status"
            data-testid="refunds-feedback"
            className={`mt-3 flex items-start gap-2 px-3 py-2 rounded-md text-xs ${
              feedback.type === 'ok'
                ? 'bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200'
                : 'bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-900 dark:text-red-200'
            }`}
          >
            {feedback.type === 'ok' ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0" />}
            <span>{feedback.message}</span>
          </div>
        )}
      </div>

      {/* Refund history */}
      <div className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-6 shadow-sm">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--theme-text)]">Recent refunds</h3>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5 inline-flex items-center gap-1">
              <PoundSterling className="w-3 h-3" /> {list?.count ?? 0} refunds · £{list?.total_refunded?.toFixed(2) ?? '0.00'} total
            </p>
          </div>
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value, 10))}
            data-testid="refunds-history-window"
            className="text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] px-2 py-1"
          >
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>12 months</option>
          </select>
        </div>

        {!list || list.count === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]" data-testid="refunds-history-empty">No refunds issued in this window.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="refunds-history-table">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] border-b border-[var(--theme-border)]">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Amount</th>
                  <th className="pb-2 pr-4">Linked org</th>
                  <th className="pb-2 pr-4">Charge</th>
                  <th className="pb-2 pr-4">Reason</th>
                  <th className="pb-2 pr-4">By</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--theme-border)]">
                {list.items.map((r) => (
                  <tr key={r.id} data-testid={`refund-row-${r.id}`}>
                    <td className="py-2 pr-4 text-[var(--color-text-muted)] whitespace-nowrap">{(r.created_at || '').slice(0, 10)}</td>
                    <td className="py-2 pr-4 tabular-nums font-medium">£{(r.amount_pence/100).toFixed(2)}</td>
                    <td className="py-2 pr-4">
                      {r.organization_name
                        ? <span className="text-[var(--theme-text)]" data-testid={`refund-org-${r.id}`}>{r.organization_name}</span>
                        : r.organization_id
                          ? <span className="text-[var(--color-text-muted)] font-mono text-[11px]">{r.organization_id.slice(0, 10)}…</span>
                          : <span className="text-[var(--color-text-muted)]">—</span>}
                    </td>
                    <td className="py-2 pr-4 text-[var(--color-text-muted)] font-mono text-[11px]">{r.charge_id?.slice(0, 20)}…</td>
                    <td className="py-2 pr-4 capitalize">{(r.reason || '').replace(/_/g, ' ')}</td>
                    <td className="py-2 pr-4 text-[var(--color-text-muted)]">{r.issued_by_email}</td>
                    <td className="py-2">
                      <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${r.status === 'succeeded' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{r.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminRefundsPanel;
