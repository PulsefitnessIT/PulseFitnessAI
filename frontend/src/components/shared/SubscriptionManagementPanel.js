import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { AlertTriangle, CheckCircle, XCircle, Loader2, RefreshCw, ArrowDownCircle } from 'lucide-react';

/**
 * SubscriptionManagementPanel (iter 215c1)
 * Self-serve cancel / reactivate / downgrade for the operator's org plan.
 * UK consumer-law requirement — every subscription must have a clear exit.
 */
const REASONS = [
  'Too expensive',
  'Switched to a different platform',
  'Not using it enough',
  'Missing a feature we need',
  'Pausing the business',
  'Other',
];

const DOWNGRADE_TIERS = [
  { id: 'memberships', name: 'Memberships only', price: 29 },
  { id: 'crm',         name: 'CRM only',         price: 49 },
  { id: 'marketing',   name: 'Marketing only',   price: 49 },
  { id: 'operations',  name: 'Operations only',  price: 59 },
];

const SubscriptionManagementPanel = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCancel, setShowCancel] = useState(false);
  const [showDowngrade, setShowDowngrade] = useState(false);
  const [reason, setReason] = useState(REASONS[0]);
  const [feedback, setFeedback] = useState('');
  const [target, setTarget] = useState(DOWNGRADE_TIERS[0].id);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const load = async () => {
    setLoading(true);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API}/account/billing/subscription`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(res.data);
    } catch (e) {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [API]); // eslint-disable-line

  const submitCancel = async () => {
    setBusy(true);
    setErrorMsg('');
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/account/billing/cancel`,
        { reason, feedback },
        { headers: { Authorization: `Bearer ${token}` } });
      setShowCancel(false);
      setReason(REASONS[0]); setFeedback('');
      load();
    } catch (e) {
      setErrorMsg(e?.response?.data?.detail || 'Cancellation failed');
    } finally {
      setBusy(false);
    }
  };

  const submitReactivate = async () => {
    setBusy(true);
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/account/billing/reactivate`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      load();
    } catch (e) {
      setErrorMsg(e?.response?.data?.detail || 'Reactivate failed');
    } finally {
      setBusy(false);
    }
  };

  const submitDowngrade = async () => {
    setBusy(true);
    setErrorMsg('');
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/account/billing/downgrade`,
        { target_tier: target },
        { headers: { Authorization: `Bearer ${token}` } });
      setShowDowngrade(false);
      load();
    } catch (e) {
      setErrorMsg(e?.response?.data?.detail || 'Downgrade failed');
    } finally {
      setBusy(false);
    }
  };

  const cancelDowngrade = async () => {
    setBusy(true);
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/account/billing/downgrade/cancel`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      load();
    } catch (e) { /* ignore */ } finally { setBusy(false); }
  };

  if (loading) {
    return (
      <div className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-5 flex items-center gap-2 text-sm" data-testid="sub-mgmt-loading">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading subscription…
      </div>
    );
  }
  if (!data) return null;

  const periodEnd = data.cancellation_effective_at || data.stripe?.current_period_end;
  const periodEndStr = periodEnd
    ? new Date(periodEnd).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
    : null;

  return (
    <div className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-6 shadow-sm" data-testid="sub-mgmt-panel">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-[var(--theme-text)]">Subscription</h3>
          <p className="text-xs text-[var(--color-text-muted)]">
            Plan: <span className="font-medium" data-testid="sub-current-plan">{data.plan}</span>
            {data.is_trial && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] uppercase tracking-wide">Trial</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          aria-label="Refresh"
          data-testid="sub-mgmt-refresh"
          className="text-[var(--color-text-muted)] hover:text-[var(--theme-text)]"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {data.billing_status === 'past_due' && (
        <div className="flex items-start gap-2 mb-4 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800" data-testid="sub-pastdue-banner">
          <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-red-900 dark:text-red-200">
            Your last payment failed. Update your card to avoid service interruption.
          </p>
        </div>
      )}

      {data.pending_cancellation && (
        <div className="flex items-start gap-2 mb-4 px-3 py-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800" data-testid="sub-pending-cancellation">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-xs font-medium text-amber-900 dark:text-amber-200">Cancellation scheduled</p>
            <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">
              Your access ends {periodEndStr ? `on ${periodEndStr}` : 'at the end of the current billing period'}.
            </p>
            <button
              type="button"
              onClick={submitReactivate}
              disabled={busy}
              data-testid="sub-reactivate-btn"
              className="mt-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700"
            >
              <CheckCircle className="w-3 h-3" /> Resume my subscription
            </button>
          </div>
        </div>
      )}

      {data.pending_downgrade_to && (
        <div className="flex items-start gap-2 mb-4 px-3 py-3 rounded-lg bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800" data-testid="sub-pending-downgrade">
          <ArrowDownCircle className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-xs font-medium text-blue-900 dark:text-blue-200">Plan change scheduled</p>
            <p className="text-xs text-blue-800 dark:text-blue-300 mt-0.5">
              Switching to <span className="font-semibold">{data.pending_downgrade_to}</span> at next renewal.
            </p>
            <button
              type="button"
              onClick={cancelDowngrade}
              disabled={busy}
              data-testid="sub-cancel-downgrade-btn"
              className="mt-2 text-xs text-blue-700 dark:text-blue-300 underline"
            >
              Keep current plan instead
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mt-4">
        {!data.pending_downgrade_to && !data.pending_cancellation && data.plan !== 'trial' && (
          <button
            type="button"
            onClick={() => setShowDowngrade(true)}
            data-testid="sub-downgrade-btn"
            className="text-xs px-3 py-1.5 rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-surface-hover)]"
          >
            Change plan
          </button>
        )}
        {!data.pending_cancellation && (
          <button
            type="button"
            onClick={() => setShowCancel(true)}
            data-testid="sub-cancel-btn"
            className="text-xs px-3 py-1.5 rounded-md border border-red-200 text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            Cancel subscription
          </button>
        )}
      </div>

      {/* Cancel modal */}
      {showCancel && (
        <div className="fixed inset-0 z-[100] bg-black/40 overflow-y-auto p-4" data-testid="sub-cancel-modal">
          <div className="min-h-full flex items-center justify-center">
            <div className="relative w-full max-w-md bg-[var(--theme-surface)] rounded-2xl shadow-xl flex flex-col my-4 border border-[var(--theme-border)]">
              <header className="flex-shrink-0 flex items-center justify-between px-5 py-4 border-b border-[var(--theme-border)]">
                <h4 className="text-base font-semibold text-[var(--theme-text)]">We're sorry to see you go</h4>
                <button onClick={() => setShowCancel(false)} aria-label="Close" data-testid="sub-cancel-close" className="w-7 h-7 rounded-full hover:bg-[var(--theme-surface-hover)] flex items-center justify-center">
                  <XCircle className="w-4 h-4 text-[var(--color-text-muted)]" />
                </button>
              </header>
              <div className="p-5 space-y-3">
                <p className="text-xs text-[var(--color-text-muted)]">
                  Your access continues until the end of your current billing period. We'll keep your data so you can resume any time.
                </p>
                <div>
                  <label className="text-xs font-medium text-[var(--theme-text)] block mb-1">Why are you cancelling?</label>
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    data-testid="sub-cancel-reason"
                    className="w-full text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] p-2 text-[var(--theme-text)]"
                  >
                    {REASONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-[var(--theme-text)] block mb-1">Tell us more (optional)</label>
                  <textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    rows={3}
                    maxLength={2000}
                    data-testid="sub-cancel-feedback"
                    className="w-full text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] p-2 text-[var(--theme-text)] resize-none"
                    placeholder="Anything you'd like us to know?"
                  />
                </div>
                {errorMsg && <p className="text-xs text-red-600" data-testid="sub-cancel-error">{errorMsg}</p>}
              </div>
              <footer className="flex-shrink-0 flex justify-end gap-2 px-5 py-4 border-t border-[var(--theme-border)]">
                <button onClick={() => setShowCancel(false)} className="text-xs px-3 py-1.5 rounded-md border border-[var(--theme-border)]">Keep my plan</button>
                <button
                  onClick={submitCancel}
                  disabled={busy}
                  data-testid="sub-cancel-confirm"
                  className="text-xs px-3 py-1.5 rounded-md bg-red-600 text-white font-medium hover:bg-red-700"
                >
                  {busy ? 'Cancelling…' : 'Cancel subscription'}
                </button>
              </footer>
            </div>
          </div>
        </div>
      )}

      {/* Downgrade modal */}
      {showDowngrade && (
        <div className="fixed inset-0 z-[100] bg-black/40 overflow-y-auto p-4" data-testid="sub-downgrade-modal">
          <div className="min-h-full flex items-center justify-center">
            <div className="relative w-full max-w-md bg-[var(--theme-surface)] rounded-2xl shadow-xl flex flex-col my-4 border border-[var(--theme-border)]">
              <header className="flex-shrink-0 flex items-center justify-between px-5 py-4 border-b border-[var(--theme-border)]">
                <h4 className="text-base font-semibold text-[var(--theme-text)]">Change your plan</h4>
                <button onClick={() => setShowDowngrade(false)} aria-label="Close" data-testid="sub-downgrade-close" className="w-7 h-7 rounded-full hover:bg-[var(--theme-surface-hover)] flex items-center justify-center">
                  <XCircle className="w-4 h-4 text-[var(--color-text-muted)]" />
                </button>
              </header>
              <div className="p-5 space-y-3">
                <p className="text-xs text-[var(--color-text-muted)]">
                  Your new plan starts at the next billing cycle. You keep all current features until then.
                </p>
                <div className="space-y-2">
                  {DOWNGRADE_TIERS.map(t => (
                    <label key={t.id} data-testid={`sub-downgrade-tier-${t.id}`} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition ${target === t.id ? 'border-[var(--color-brand-blue)] bg-[var(--color-brand-blue)]/5' : 'border-[var(--theme-border)]'}`}>
                      <input type="radio" checked={target === t.id} onChange={() => setTarget(t.id)} className="accent-[var(--color-brand-blue)]" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-[var(--theme-text)]">{t.name}</p>
                        <p className="text-xs text-[var(--color-text-muted)]">£{t.price}/month</p>
                      </div>
                    </label>
                  ))}
                </div>
                {errorMsg && <p className="text-xs text-red-600">{errorMsg}</p>}
              </div>
              <footer className="flex-shrink-0 flex justify-end gap-2 px-5 py-4 border-t border-[var(--theme-border)]">
                <button onClick={() => setShowDowngrade(false)} className="text-xs px-3 py-1.5 rounded-md border border-[var(--theme-border)]">Keep current plan</button>
                <button
                  onClick={submitDowngrade}
                  disabled={busy}
                  data-testid="sub-downgrade-confirm"
                  className="text-xs px-3 py-1.5 rounded-md bg-[var(--color-brand-blue)] text-white font-medium"
                >
                  {busy ? 'Saving…' : 'Schedule plan change'}
                </button>
              </footer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SubscriptionManagementPanel;
