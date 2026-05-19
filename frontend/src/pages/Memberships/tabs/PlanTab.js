/**
 * Iter 216h173 — PlanTab extracted from MemberPortal.js for lazy-loading.
 *
 * Owns the plans list + the CheckoutModal (promo / waiver / Stripe).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { API, CenterLoader, EmptyCard, Pill } from '../portalShared';

export default function PlanTab({ headers, member }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyPlan] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p] = await Promise.all([
        axios.get(`${API}/member/plans`, { headers }),
        axios.get(`${API}/member-auth/me`, { headers }),
      ]);
      setPlans(p.data.plans || []);
    } catch { notify.error('Failed to load plans'); }
    finally { setLoading(false); }
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const [checkoutPlan, setCheckoutPlan] = useState(null);
  const startCheckout = (plan) => setCheckoutPlan(plan);

  return (
    <div data-testid="member-plan">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Your plan</h2>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 mb-6" data-testid="member-plan-current">
        <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Current status</div>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-bold text-white">{member.status === 'active' ? 'Active member' : 'No active plan'}</div>
            <div className="text-xs text-white/50 mt-0.5">{member.email}</div>
          </div>
          <Pill tone={member.status === 'active' ? 'emerald' : 'amber'}>{member.status}</Pill>
        </div>
      </div>
      <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">{member.status === 'active' ? 'Top up or change' : 'Choose a plan'}</h3>
      {loading ? <CenterLoader /> : plans.length === 0 ? <EmptyCard text="No plans available yet." /> : (
        <div className="space-y-2">
          {plans.map((p) => (
            <div key={p.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4" data-testid={`member-plan-${p.id}`}
              style={{ borderLeft: `3px solid ${p.colour || 'var(--color-brand-cyan)'}` }}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-bold text-white text-sm flex items-center gap-2 flex-wrap">
                    {p.name}
                    {p.trial_days > 0 && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase">
                        {p.trial_days}-day trial
                      </span>
                    )}
                    {p.kind === 'course' && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 uppercase">
                        {p.course_session_count}-week course
                      </span>
                    )}
                    {p.kind === 'bundle' && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-fuchsia-500/20 text-fuchsia-300 uppercase">Bundle</span>
                    )}
                  </div>
                  <div className="text-xs text-white/60 mt-0.5 capitalize">{p.kind.replace('_', ' ')} · {p.billing_cycle}</div>
                  <div className="text-[11px] text-white/50 mt-1">
                    {p.included_classes === 'unlimited' ? 'Unlimited classes' :
                     p.credits_count ? `${p.credits_count} credits${p.pack_expiry_days ? ` · expire in ${p.pack_expiry_days}d` : ''}` : 'Credits only'}
                    {p.pt_credits_count ? ` · ${p.pt_credits_count} PT credits` : ''}
                    {p.freeze_allowed ? ' · freezable' : ''}
                    {p.cancel_notice_days > 0 ? ` · ${p.cancel_notice_days}d notice` : ''}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xl font-extrabold tracking-tight">£{(p.price_pence / 100).toFixed(2)}</div>
                  <div className="text-[10px] text-white/50 uppercase tracking-wider">{p.billing_cycle === 'oneoff' ? 'one-off' : `per ${p.billing_cycle === 'annual' ? 'year' : 'month'}`}</div>
                </div>
              </div>
              <button onClick={() => startCheckout(p)} disabled={!!busyPlan}
                className="mt-3 w-full rounded-lg py-2.5 text-xs font-extrabold uppercase tracking-wider disabled:opacity-60"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
                data-testid={`member-plan-buy-${p.id}`}>
                {busyPlan === p.id ? '…' : (p.trial_days > 0 ? `Start ${p.trial_days}-day free trial` : 'Subscribe / Buy')}
              </button>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-white/40 mt-5 leading-relaxed">Pay securely via Stripe — your details never touch our servers. Have a promo code? You can apply it at the next step.</p>
      {checkoutPlan && (
        <CheckoutModal API={API} headers={headers} plan={checkoutPlan} member={member}
          onClose={() => setCheckoutPlan(null)} />
      )}
    </div>
  );
}

function CheckoutModal({ API, headers, plan, member, onClose }) {
  const [code, setCode] = useState('');
  const [validating, setValidating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);

  const validate = async () => {
    if (!code.trim()) { setPreview(null); setError(null); return; }
    setValidating(true); setError(null);
    try {
      const { data } = await axios.post(`${API}/memberships/promo-codes/validate`,
        { code: code.trim(), plan_id: plan.id, member_id: member.id },
        { headers });
      setPreview(data);
    } catch (e) {
      setPreview(null);
      setError(e.response?.data?.detail || 'Invalid promo code');
    }
    setValidating(false);
  };

  const [waiverDue, setWaiverDue] = useState(false);
  const [waiverName, setWaiverName] = useState('');
  const [waiverAck, setWaiverAck] = useState(false);
  const [signingWaiver, setSigningWaiver] = useState(false);

  const proceed = async () => {
    if (plan.waiver_required && !waiverDue && !(preview && preview._waiver_cleared)) {
      try {
        const r = await axios.get(`${API}/member/waivers/me`, { headers });
        const signed = (r.data?.waivers || []).some((w) => w.plan_id === plan.id);
        if (!signed) {
          setWaiverDue(true);
          return;
        }
      } catch { /* if we can't check, fall through — backend will enforce */ }
    }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/memberships/checkout`, {
        plan_id: plan.id,
        origin_url: window.location.origin,
        ...(preview?.code ? { promo_code: preview.code } : {}),
      }, { headers });
      if (data?.url) {
        window.location.href = data.url;
      } else {
        notify.error('Checkout could not start');
        setBusy(false);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Checkout failed');
      setBusy(false);
    }
  };

  const signWaiver = async () => {
    if (!waiverName.trim() || !waiverAck) return;
    setSigningWaiver(true);
    try {
      await axios.post(`${API}/member/waivers`, {
        plan_id: plan.id,
        signature_name: waiverName.trim(),
        acknowledged: true,
      }, { headers });
      notify.success('Waiver signed');
      setWaiverDue(false);
      setTimeout(() => proceed(), 100);
    } catch (e) {
      notifyApiError(notify, e, 'Signing failed');
    } finally {
      setSigningWaiver(false);
    }
  };

  const finalPence = preview?.discounted_pence ?? plan.price_pence;
  const savingsPence = preview?.savings_pence || 0;

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-[color:var(--theme-surface)] dark:bg-zinc-900 border border-white/10 rounded-2xl p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}
        data-testid="member-checkout-modal">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Confirm purchase</p>
            <h3 className="text-xl font-extrabold tracking-tight text-white mt-1">{plan.name}</h3>
            <p className="text-xs text-white/50 mt-0.5 capitalize">{plan.kind.replace('_', ' ')} · {plan.billing_cycle}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white/10 text-white/60" data-testid="member-checkout-close">✕</button>
        </div>

        {plan.trial_days > 0 && (
          <div className="mt-3 rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-3 py-2">
            <p className="text-xs font-bold text-emerald-300">
              {plan.trial_days}-day free trial — your card won't be charged for {plan.trial_days} days.
            </p>
          </div>
        )}

        <div className="mt-4">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider font-bold text-white/50">Promo code (optional)</span>
            <div className="flex gap-2 mt-1">
              <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
                onBlur={validate}
                onKeyDown={(e) => e.key === 'Enter' && validate()}
                placeholder="SUMMER25"
                className="flex-1 px-3 py-2 rounded-md text-sm font-mono uppercase border border-white/10 bg-white/5 text-white focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="member-checkout-promo-input" />
              <button onClick={validate} disabled={validating || !code.trim()}
                className="px-3 py-2 rounded-md text-xs font-bold border border-white/15 text-white/80 hover:bg-white/10 disabled:opacity-50"
                data-testid="member-checkout-promo-apply">
                {validating ? '…' : 'Apply'}
              </button>
            </div>
          </label>
          {error && <p className="text-xs text-red-400 mt-2" data-testid="member-checkout-promo-error">{error}</p>}
          {preview && (
            <p className="text-xs text-emerald-400 mt-2" data-testid="member-checkout-promo-success">
              Promo applied · saving £{(savingsPence / 100).toFixed(2)} ({preview.duration === 'once' ? 'first invoice' : preview.duration === 'forever' ? 'every invoice' : 'first ' + preview.duration_in_months + ' months'})
            </p>
          )}
        </div>

        <div className="mt-4 rounded-lg bg-white/5 border border-white/10 p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-white/60">Plan price</span>
            <span className={savingsPence > 0 ? 'line-through text-white/40' : 'text-white font-bold'}>
              £{(plan.price_pence / 100).toFixed(2)}
            </span>
          </div>
          {savingsPence > 0 && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-emerald-300">Discount</span>
              <span className="text-emerald-300 font-bold">−£{(savingsPence / 100).toFixed(2)}</span>
            </div>
          )}
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-white/10">
            <span className="text-white/80 text-sm font-bold">Total today</span>
            <span className="text-2xl font-extrabold text-white" data-testid="member-checkout-final-price">
              £{(finalPence / 100).toFixed(2)}
            </span>
          </div>
        </div>

        {waiverDue ? (
          <div className="mt-4 space-y-2" data-testid="member-waiver-gate">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-amber-400">Waiver required</p>
            <div className="max-h-40 overflow-y-auto rounded-lg border border-white/10 bg-white/5 p-2.5 text-xs text-white/80 whitespace-pre-wrap" data-testid="member-waiver-text">
              {plan.waiver_text || 'By signing, you acknowledge the risks of participating in this class and confirm you are medically fit to take part.'}
            </div>
            <input type="text" placeholder="Type your full name to sign"
              value={waiverName} onChange={(e) => setWaiverName(e.target.value)}
              className="w-full h-10 rounded-lg border border-white/10 bg-transparent px-3 text-sm text-white"
              data-testid="member-waiver-name" />
            <label className="flex items-start gap-2 text-xs text-white/70">
              <input type="checkbox" className="mt-0.5" checked={waiverAck} onChange={(e) => setWaiverAck(e.target.checked)}
                data-testid="member-waiver-ack" />
              I acknowledge and accept the terms above.
            </label>
            <button onClick={signWaiver} disabled={!waiverName.trim() || !waiverAck || signingWaiver}
              className="mt-2 w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="member-waiver-sign">
              {signingWaiver ? 'Signing…' : 'Sign & continue to payment'}
            </button>
          </div>
        ) : (
          <>
            <button onClick={proceed} disabled={busy}
              className="mt-4 w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="member-checkout-proceed">
              {busy ? 'Redirecting to Stripe…' : 'Pay securely with Stripe'}
            </button>
            <p className="text-[10px] text-white/40 mt-3 text-center">Secured by Stripe · we never see your card details.</p>
          </>
        )}
      </div>
    </div>
  );
}
