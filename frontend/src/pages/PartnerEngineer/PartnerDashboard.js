/**
 * Partner Engineer Dashboard — iter 216h75 (Phase 1).
 *
 * Self-service hub for an approved engineer partner:
 *   • Referral link / code (one-click copy)
 *   • Active referred customers + status counts
 *   • Commission ledger (accrued / approved / paid / clawed back)
 *   • App-fee tier (£30 → £15 → free)
 *   • CTA to the Engineer App (/svc/engineer) for actual jobs
 *
 * Hard scope: this page MUST NOT surface CRM, full Operations,
 * Memberships, or Marketing data. Read-only commercial summary only.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Copy, ExternalLink, Wrench, Users, PoundSterling, Sparkles, Loader2,
  CheckCircle2, AlertTriangle, CreditCard, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import PartnerComplianceCard from './PartnerComplianceCard';
import PartnerActivationChecklist from './PartnerActivationChecklist';
import PartnerCollateralCard from './PartnerCollateralCard';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_BADGE = {
  draft:     { label: 'Draft',      cls: 'bg-zinc-200 text-zinc-700' },
  pending:   { label: 'Pending review', cls: 'bg-amber-100 text-amber-800' },
  approved:  { label: 'Approved',   cls: 'bg-emerald-100 text-emerald-800' },
  rejected:  { label: 'Rejected',   cls: 'bg-rose-100 text-rose-800' },
  suspended: { label: 'Suspended',  cls: 'bg-zinc-300 text-zinc-800' },
};

export default function PartnerDashboard() {
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [data, setData] = useState({ partner: null, referrals: [], commission: null });
  const [loading, setLoading] = useState(true);
  const [subBusy, setSubBusy] = useState(false);
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [meRes, refRes, commRes] = await Promise.all([
        axios.get(`${API}/api/partners/me`, { headers }),
        axios.get(`${API}/api/partners/me/referrals`, { headers }).catch(() => ({ data: { referrals: [] } })),
        axios.get(`${API}/api/partners/me/commission`, { headers }).catch(() => ({ data: null })),
      ]);
      setData({
        partner: meRes.data?.partner,
        referral_link: meRes.data?.referral_link,
        referrals: refRes.data?.referrals || [],
        commission: commRes.data || null,
      });
    } catch {
      /* tolerated */
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  // Handle the post-Stripe-checkout return.
  useEffect(() => {
    const status = params.get('subscription');
    if (status === 'success') {
      notify.success('Subscription active — welcome to the Partner Engineer Plan');
      params.delete('subscription'); params.delete('session_id');
      setParams(params, { replace: true });
      load();
    } else if (status === 'cancelled') {
      notify.error('Checkout cancelled — no charge made');
      params.delete('subscription');
      setParams(params, { replace: true });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [params]);

  const startSubscription = async () => {
    setSubBusy(true);
    try {
      const r = await axios.post(`${API}/api/partners/me/subscription/checkout`,
        { origin_url: window.location.origin }, { headers });
      if (r.data?.url) {
        window.location.href = r.data.url;
        return;
      }
    } catch (e) {
      notifyApiError(notify, e, 'Could not start subscription');
    } finally {
      setSubBusy(false);
    }
  };

  const cancelSubscription = async () => {
    if (!window.confirm('Cancel your Partner Plan? You\'ll keep access until the end of the current billing period.')) return;
    setSubBusy(true);
    try {
      await axios.post(`${API}/api/partners/me/subscription/cancel`, {}, { headers });
      notify.success('Subscription cancellation scheduled for the end of this period');
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Could not cancel');
    } finally {
      setSubBusy(false);
    }
  };

  const resumeSubscription = async () => {
    setSubBusy(true);
    try {
      await axios.post(`${API}/api/partners/me/subscription/resume`, {}, { headers });
      notify.success('Subscription resumed');
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Could not resume');
    } finally {
      setSubBusy(false);
    }
  };

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); notify.success('Copied to clipboard'); }
    catch { notify.error('Clipboard unavailable'); }
  };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen text-zinc-500 text-sm gap-2">
      <Loader2 className="animate-spin" size={14} /> Loading partner dashboard…
    </div>;
  }

  const partner = data.partner;
  if (!partner) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-2xl font-black">Become a Partner Engineer</h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Earn commission on every gym you refer to GymAxis and take jobs through the Engineer App.
          </p>
          <Link to="/partners/engineers/apply"
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-md bg-purple-600 hover:bg-purple-700 text-white text-sm font-bold"
            data-testid="partner-apply-cta">
            Apply now <ExternalLink size={13} />
          </Link>
        </div>
      </div>
    );
  }

  const badge = STATUS_BADGE[partner.status] || STATUS_BADGE.draft;
  const totals = data.commission?.totals || { accrued: 0, approved: 0, paid: 0, clawed_back: 0 };
  const tier = partner.app_fee_tier || {};
  const activeCount = partner.active_referral_count || 0;
  const nextThreshold = activeCount < 5 ? 5 : activeCount < 10 ? 10 : null;
  const referralLink = data.referral_link || '';

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 py-10 px-4">
      <div className="max-w-5xl mx-auto space-y-5" data-testid="partner-dashboard">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider font-extrabold text-purple-500 flex items-center gap-1.5">
              <Sparkles size={11} /> Partner Engineer
            </div>
            <h1 className="text-2xl font-black">Hi {(partner.full_name || '').split(' ')[0] || 'there'}</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className={'px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ' + badge.cls}
              data-testid="partner-status-badge">{badge.label}</span>
            <Link to="/svc/engineer"
              className="px-3 py-2 text-sm font-bold rounded-md bg-zinc-900 dark:bg-white dark:text-zinc-900 text-white inline-flex items-center gap-1.5"
              data-testid="partner-open-engineer-app">
              <Wrench size={13} /> Engineer App
            </Link>
          </div>
        </div>

        {/* Status banner */}
        {partner.status !== 'approved' && (
          <div className="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-900/30 p-3 text-xs text-amber-800 dark:text-amber-100 flex items-start gap-2"
            data-testid="partner-status-banner">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <div>
              {partner.status === 'pending' && 'Your application is under review. We aim to respond within 2 working days. You can still complete jobs your customers have assigned you while we review.'}
              {partner.status === 'rejected' && (
                <>Your application was not approved. {partner.rejected_reason ? <span className="block mt-1 italic">"{partner.rejected_reason}"</span> : null}{' '}
                <Link to="/partners/engineers/apply" className="underline font-bold">Update your details and resubmit.</Link></>
              )}
              {partner.status === 'suspended' && 'Your partner access is suspended. Contact GymAxis support to discuss next steps.'}
            </div>
          </div>
        )}

        {/* Referral block */}
        <Card title="Your referral link" icon={Users} testId="partner-referral-card">
          <div className="flex items-center gap-2 flex-wrap">
            <code className="font-mono text-sm px-3 py-2 rounded-md bg-zinc-100 dark:bg-zinc-800 break-all flex-1"
              data-testid="partner-referral-link-value">{referralLink || '(unavailable)'}</code>
            <button onClick={() => copy(referralLink)} disabled={!referralLink}
              className="px-3 py-2 text-xs font-bold rounded-md border border-zinc-200 dark:border-zinc-700 inline-flex items-center gap-1.5 disabled:opacity-50"
              data-testid="partner-copy-link"><Copy size={11} /> Copy</button>
            <button onClick={() => copy(partner.referral_code)} disabled={!partner.referral_code}
              className="px-3 py-2 text-xs font-bold rounded-md border border-zinc-200 dark:border-zinc-700 inline-flex items-center gap-1.5 disabled:opacity-50"
              data-testid="partner-copy-code"><Copy size={11} /> Copy code: {partner.referral_code}</button>
          </div>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-2">
            Share with gym owners — when they sign up via this link, we'll automatically attribute their account and start your commission clock once their first Operations payment clears.
          </p>
        </Card>

        {/* Subscription card — iter 216h76 */}
        <SubscriptionCard
          partner={partner} tier={tier} activeCount={activeCount}
          busy={subBusy} onStart={startSubscription}
          onCancel={cancelSubscription} onResume={resumeSubscription}
        />

        {/* Iter 216h283 — Gap 4: gym-entry compliance docs (DBS, RTW,
            Safeguarding, Public Liability). Shown to approved partners
            only — the panel hides itself silently for any other status. */}
        {partner.status === 'approved' && <PartnerComplianceCard />}

        {/* Iter 216h284 — Gap 5: first-7-days activation checklist.
            Renders only for approved partners; once 100% complete the
            component swaps to a compact trophy banner the user can
            dismiss for the session. */}
        {partner.status === 'approved' && (
          <PartnerActivationChecklist
            onCopyLink={() => copy(referralLink)}
            onSubscribeClick={() => {
              const el = document.querySelector('[data-testid="partner-subscription-card"]');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }}
            onComplianceClick={() => {
              const el = document.querySelector('[data-testid="partner-compliance-card"]');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }}
          />
        )}

        {/* Iter 216h285 — Gap 6: referral collateral kit (QR poster,
            social card, PDF pitch). Closes the loop on "Copy your link"
            with something the engineer actually wants to share. */}
        {partner.status === 'approved' && <PartnerCollateralCard />}

        {/* Stat grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat label="Active referrals" value={activeCount} testId="partner-stat-active"
            sub={nextThreshold ? `${nextThreshold - activeCount} more to ${nextThreshold === 5 ? '£15/mo' : 'free'}` : 'Free tier unlocked'} />
          <Stat label="App fee" value={tier.price_gbp === 0 ? 'Free' : `£${tier.price_gbp}/mo`} sub={tier.label}
            testId="partner-stat-app-fee" />
          <Stat label="Pending payout" value={`£${(totals.approved + totals.accrued).toFixed(2)}`}
            sub={`£${totals.accrued.toFixed(2)} accrued + £${totals.approved.toFixed(2)} approved`}
            testId="partner-stat-pending" />
          <Stat label="Paid lifetime" value={`£${totals.paid.toFixed(2)}`}
            sub={totals.clawed_back ? `£${totals.clawed_back.toFixed(2)} clawed back` : 'No claw-backs'}
            testId="partner-stat-paid" />
        </div>

        {/* Referred customers */}
        <Card title="Referred customers" icon={Users} testId="partner-referrals-card">
          {data.referrals.length === 0 ? (
            <p className="text-xs text-zinc-500">No referrals yet — share your link to get started.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200 dark:border-zinc-800">
                    <th className="text-left py-2 pr-3">Org ID</th>
                    <th className="text-left py-2 pr-3">Status</th>
                    <th className="text-left py-2 pr-3">First paid</th>
                    <th className="text-right py-2">Recurring earned</th>
                  </tr>
                </thead>
                <tbody>
                  {data.referrals.map((r) => (
                    <tr key={r.id} className="border-b border-zinc-100 dark:border-zinc-900" data-testid={`partner-referral-row-${r.id}`}>
                      <td className="py-2 pr-3 text-xs font-mono text-zinc-600 dark:text-zinc-300 truncate max-w-[200px]">{r.referred_organization_id}</td>
                      <td className="py-2 pr-3 text-xs font-bold">{r.status}</td>
                      <td className="py-2 pr-3 text-xs text-zinc-500">{r.first_paid_at ? new Date(r.first_paid_at).toLocaleDateString() : '—'}</td>
                      <td className="py-2 text-right text-xs">£{(r.recurring_total_paid_gbp || 0).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Ledger */}
        <Card title="Commission ledger" icon={PoundSterling} testId="partner-ledger-card">
          {!(data.commission?.ledger || []).length ? (
            <p className="text-xs text-zinc-500">No commission yet — accrues on your referred customers' first Operations payment.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200 dark:border-zinc-800">
                    <th className="text-left py-2 pr-3">Date</th>
                    <th className="text-left py-2 pr-3">Kind</th>
                    <th className="text-left py-2 pr-3">Status</th>
                    <th className="text-right py-2">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.commission?.ledger || []).map((row) => (
                    <tr key={row.id} className="border-b border-zinc-100 dark:border-zinc-900" data-testid={`partner-ledger-row-${row.id}`}>
                      <td className="py-2 pr-3 text-xs text-zinc-500">{new Date(row.created_at).toLocaleDateString()}</td>
                      <td className="py-2 pr-3 text-xs font-bold">{row.kind === 'signup_reward' ? 'Signup reward' : 'Recurring'}</td>
                      <td className="py-2 pr-3 text-xs">{row.status === 'paid' ? <span className="text-emerald-600 inline-flex items-center gap-1"><CheckCircle2 size={11} /> Paid</span> : row.status}</td>
                      <td className="py-2 text-right text-xs font-mono font-bold">£{row.amount_gbp.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, icon: Icon, children, testId }) {
  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5" data-testid={testId}>
      <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon size={14} className="text-purple-500" />}
        <h3 className="text-sm font-extrabold uppercase tracking-wider text-zinc-700 dark:text-zinc-200">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, sub, testId }) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</div>
      <div className="text-2xl font-black mt-1 text-zinc-900 dark:text-zinc-100">{value}</div>
      {sub && <div className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1">{sub}</div>}
    </div>
  );
}

function SubscriptionCard({ partner, tier, activeCount, busy, onStart, onCancel, onResume }) {
  const sub = partner.subscription || {};
  const isActive = sub.status === 'active' || sub.status === 'trialing';
  const willCancel = !!sub.cancel_at_period_end;
  const periodEnd = sub.current_period_end ? new Date(sub.current_period_end) : null;
  const freeTier = tier.price_gbp === 0;

  if (partner.status !== 'approved') {
    return null; // hide until application is approved
  }

  return (
    <Card title="Partner plan subscription" icon={CreditCard} testId="partner-subscription-card">
      {freeTier ? (
        <div className="rounded-lg bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-900 p-3 text-sm text-emerald-800 dark:text-emerald-100 flex items-start gap-2"
          data-testid="partner-sub-free-tier">
          <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-bold">Free tier active — {activeCount} active referrals</div>
            <div className="text-[12px] mt-0.5 text-emerald-700 dark:text-emerald-200">
              You've unlocked free Engineer App access. {sub.cancel_at_period_end && periodEnd
                ? <>Your paid subscription will lapse on {periodEnd.toLocaleDateString()}.</>
                : null}
            </div>
          </div>
        </div>
      ) : !isActive ? (
        <div className="flex items-start justify-between gap-3 flex-wrap"
          data-testid="partner-sub-cta">
          <div className="text-sm text-zinc-700 dark:text-zinc-200">
            <div className="font-bold">Start your Partner Engineer Plan</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              £{tier.price_gbp}/mo · auto-discounts to £15/mo at 5 active referrals and free at 10+. Cancel any time.
            </div>
          </div>
          <button onClick={onStart} disabled={busy}
            className="px-4 py-2 text-sm font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
            data-testid="partner-sub-start">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <CreditCard size={13} />}
            Start subscription
          </button>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3 flex-wrap"
          data-testid="partner-sub-active">
          <div className="text-sm text-zinc-700 dark:text-zinc-200 min-w-0">
            <div className="font-bold inline-flex items-center gap-1.5">
              {willCancel
                ? <span className="text-amber-600 dark:text-amber-300">Cancels {periodEnd ? periodEnd.toLocaleDateString() : 'at period end'}</span>
                : <><CheckCircle2 size={13} className="text-emerald-500" /> Active · £{tier.price_gbp}/mo</>}
            </div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              {periodEnd && !willCancel
                ? <>Next charge {periodEnd.toLocaleDateString()}</>
                : willCancel ? 'No future charges scheduled.' : 'Billing in progress…'}
            </div>
          </div>
          <div className="flex gap-2">
            {willCancel ? (
              <button onClick={onResume} disabled={busy}
                className="px-3 py-1.5 text-xs font-bold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-1 disabled:opacity-50"
                data-testid="partner-sub-resume">
                {busy ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                Resume
              </button>
            ) : (
              <button onClick={onCancel} disabled={busy}
                className="px-3 py-1.5 text-xs font-bold rounded-md border border-rose-300 dark:border-rose-700 text-rose-700 dark:text-rose-300 inline-flex items-center gap-1 disabled:opacity-50"
                data-testid="partner-sub-cancel">
                {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
