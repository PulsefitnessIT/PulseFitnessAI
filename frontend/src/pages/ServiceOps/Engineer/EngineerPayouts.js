/**
 * EngineerPayouts — Stripe Connect onboarding & status panel for engineers.
 *
 * Iter 216h132. Light-mode GymAxis brand. The engineer connects their
 * own Stripe account here so invoice card payments settle directly
 * into their balance — the platform never touches the funds.
 *
 * Behaviour:
 *  • If not connected → "Connect Stripe" CTA opens hosted onboarding in same tab.
 *  • If onboarding incomplete → "Continue onboarding" CTA + requirements list.
 *  • If fully ready → green badge + "Open Stripe dashboard" + "Refresh status".
 *  • `?onboarding=return` triggers an automatic status refresh on mount.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, ShieldCheck, CreditCard, ExternalLink, Loader2,
  CheckCircle2, AlertTriangle, RefreshCw, Banknote,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import StripeConnectErrorBanner from '@/components/shared/StripeConnectErrorBanner';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function EngineerPayouts() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [onboarding, setOnboarding] = useState(false);
  const [dashboarding, setDashboarding] = useState(false);
  const [connectError, setConnectError] = useState(null);

  const load = useCallback(async ({ refresh = false } = {}) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/stripe/connect/status`, {
        ...auth(),
        params: refresh ? { refresh: true } : undefined,
      });
      setStatus(r.data);
    } catch (e) {
      notify.error('Could not load payouts status');
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load({ refresh: false }); }, [load]);

  // After Stripe redirects back to /svc/engineer/payouts?onboarding=return
  // we resync against Stripe so the engineer sees the live state.
  useEffect(() => {
    if (params.get('onboarding') === 'return') {
      load({ refresh: true });
      const next = new URLSearchParams(params);
      next.delete('onboarding');
      setParams(next, { replace: true });
    }
  }, [params, load, setParams]);

  const startOnboarding = useCallback(async () => {
    setOnboarding(true);
    setConnectError(null);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/stripe/connect/onboarding`, {}, auth(),
      );
      if (r.data?.url) {
        window.location.href = r.data.url;
      } else {
        notify.error('Unable to start Stripe onboarding');
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      const code = (typeof detail === 'object' && detail) ? detail.code : null;
      // Platform-level Connect blockers → persistent banner with a fix link.
      if (code === 'stripe_connect_profile_incomplete' || code === 'stripe_connect_not_enabled') {
        setConnectError(detail);
      }
      let msg = (typeof detail === 'string')
        ? detail : (detail?.message || 'Stripe onboarding failed — try again');
      if (code === 'stripe_connect_not_enabled') {
        msg = 'Stripe Connect is not yet enabled on the GymAxis platform. ' +
              'We have notified our team — please try again shortly.';
      }
      notify.error(msg);
    } finally {
      setOnboarding(false);
    }
  }, []);

  const openDashboard = useCallback(async () => {
    setDashboarding(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/stripe/connect/login-link`, {}, auth(),
      );
      if (r.data?.url) window.open(r.data.url, '_blank', 'noopener');
    } catch {
      notify.error('Could not open Stripe dashboard');
    } finally {
      setDashboarding(false);
    }
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="engineer-payouts-page">
      <header className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="p-2 rounded-full hover:bg-slate-100"
            aria-label="Back"
            data-testid="engineer-payouts-back"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
              Engineer · Payouts
            </p>
            <h1 className="text-lg font-bold text-slate-900">Card payments &amp; payouts</h1>
          </div>
          <button
            type="button"
            onClick={() => load({ refresh: true })}
            aria-label="Refresh status"
            className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
            data-testid="engineer-payouts-refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {loading && !status ? (
          <div className="text-center py-16 text-slate-400">
            <Loader2 className="animate-spin mx-auto mb-2" size={20} />
            Loading your payout settings…
          </div>
        ) : (
          <>
            <StripeConnectErrorBanner error={connectError} />
            <StatusCard
              status={status}
              onConnect={startOnboarding}
              onContinue={startOnboarding}
              onDashboard={openDashboard}
              onboarding={onboarding}
              dashboarding={dashboarding}
            />

            <div className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="engineer-payouts-explainer">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
                How card payments work
              </p>
              <ul className="space-y-2 text-sm text-slate-600">
                <ExplainerRow icon={ShieldCheck} text="You connect your own Stripe account (Express). KYC takes ~3 minutes." />
                <ExplainerRow icon={CreditCard}  text="A 'Pay now by card' link is added to every invoice you send." />
                <ExplainerRow icon={Banknote}    text="Payments settle into YOUR Stripe balance — GymAxis never touches the funds." />
                <ExplainerRow icon={CheckCircle2} text="No application fee. Stripe's standard processing rates apply." />
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const ExplainerRow = ({ icon: Icon, text }) => (
  <li className="flex items-start gap-2">
    <Icon size={16} className="text-blue-600 mt-0.5 shrink-0" />
    <span>{text}</span>
  </li>
);

function StatusCard({ status, onConnect, onContinue, onDashboard, onboarding, dashboarding }) {
  const state = useMemo(() => {
    if (!status?.connected) return 'not_connected';
    if (status.charges_enabled) return 'ready';
    return 'incomplete';
  }, [status]);

  if (state === 'not_connected') {
    return (
      <div
        className="rounded-2xl p-6 text-white shadow-md"
        style={{ background: 'linear-gradient(135deg, #1d4ed8 0%, #6366f1 60%, #8b5cf6 100%)' }}
        data-testid="payouts-state-not-connected"
      >
        <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">Stripe · Not connected</p>
        <h2 className="text-2xl font-extrabold mt-1">Accept card payments on your invoices</h2>
        <p className="text-sm opacity-90 mt-1 max-w-xl">
          Connect your Stripe account in ~3 minutes. Every invoice you send will include a secure
          "Pay by card" link that settles straight into your balance.
        </p>
        <button
          type="button"
          onClick={onConnect}
          disabled={onboarding}
          className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-white text-blue-700 text-sm font-bold hover:bg-slate-100 disabled:opacity-60"
          data-testid="payouts-connect-stripe-btn"
        >
          {onboarding ? <Loader2 size={14} className="animate-spin" /> : <CreditCard size={14} />}
          Connect Stripe
        </button>
      </div>
    );
  }

  if (state === 'incomplete') {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5" data-testid="payouts-state-incomplete">
        <div className="flex items-start gap-3">
          <AlertTriangle size={22} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-amber-700">
              Stripe · Onboarding incomplete
            </p>
            <h2 className="text-lg font-extrabold text-amber-900 mt-1">
              Finish Stripe verification to start taking card payments
            </h2>
            <p className="text-sm text-amber-800 mt-1">
              Stripe still needs a few details before you can charge cards. This usually means
              ID verification or bank details.
            </p>
            {status?.requirements_currently_due?.length ? (
              <ul className="text-xs text-amber-800 mt-2 list-disc list-inside space-y-0.5" data-testid="payouts-requirements-list">
                {status.requirements_currently_due.slice(0, 6).map(r => (
                  <li key={r}><code className="bg-amber-100 px-1 rounded">{r}</code></li>
                ))}
              </ul>
            ) : null}
            <button
              type="button"
              onClick={onContinue}
              disabled={onboarding}
              className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-600 text-white text-sm font-bold hover:bg-amber-700 disabled:opacity-60"
              data-testid="payouts-continue-onboarding-btn"
            >
              {onboarding ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
              Continue Stripe onboarding
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ready
  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5" data-testid="payouts-state-ready">
      <div className="flex items-start gap-3">
        <CheckCircle2 size={22} className="text-emerald-600 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-emerald-700">
            Stripe · Connected
          </p>
          <h2 className="text-lg font-extrabold text-emerald-900 mt-1">
            You're ready to accept card payments
          </h2>
          <p className="text-sm text-emerald-800 mt-1">
            Every invoice you send now includes a secure pay link. Funds settle into your
            Stripe balance and pay out on your default schedule.
          </p>
          <div className="flex gap-2 mt-3 flex-wrap">
            <button
              type="button"
              onClick={onDashboard}
              disabled={dashboarding}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-600 text-white text-sm font-bold hover:bg-emerald-700 disabled:opacity-60"
              data-testid="payouts-open-stripe-dashboard-btn"
            >
              {dashboarding ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
              Open Stripe dashboard
            </button>
            <span
              className="inline-flex items-center gap-1 px-3 py-2 rounded-full bg-white border border-emerald-200 text-emerald-700 text-xs font-bold"
              data-testid="payouts-payouts-flag"
            >
              {status?.payouts_enabled ? 'Payouts enabled' : 'Payouts pending'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
