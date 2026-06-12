/**
 * ServiceProviderUpgrade — Iter 258.
 *
 * Self-serve conversion of a Service Provider trial onto the paid monthly
 * Service Desk plan via Stripe Checkout. Doubles as the success-return
 * page: when Stripe redirects back with ?status=success&session_id=..., it
 * polls the backend until the payment is confirmed, then routes to the desk.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Check, Loader2, ArrowRight, ShieldCheck, Headset, CheckCircle2, XCircle,
} from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';

const PERKS = [
  'Unlimited engineers & cases',
  'Drag-and-drop scheduler + phone intake',
  'SLA compliance, utilisation & revenue analytics',
  'CSV/Excel migration import with AI mapping',
  'Engineer mobile app + customer tracking links',
  'Quotes, invoicing & audit log',
];

export default function ServiceProviderUpgrade() {
  const { API, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState(
    () => (params.get('status') === 'cancelled' ? 'cancelled' : 'plan'),
  ); // plan | verifying | success | cancelled
  const sessionId = params.get('session_id');
  const returnStatus = params.get('status');

  const loadPlan = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/service-provider/plan`);
      setPlan(data);
      if (data.is_converted) setPhase('success');
    } catch { /* non-provider or error — page guard handles it */ }
  }, [API]);

  // Poll the payment status after returning from Stripe.
  const verify = useCallback(async (sid, attempt = 0) => {
    setPhase('verifying');
    try {
      const { data } = await axios.get(`${API}/service-provider/upgrade/status/${sid}`);
      if (data.payment_status === 'paid') {
        await refreshUser();
        setPhase('success');
        notify.success('You\'re subscribed!', 'Welcome to Service Desk Pro.');
        return;
      }
      if (data.status === 'expired' || attempt >= 6) {
        setPhase('plan');
        notify.error('Payment not completed', 'Your session expired — please try again.');
        return;
      }
      setTimeout(() => verify(sid, attempt + 1), 2000);
    } catch {
      setPhase('plan');
      notify.error('Could not verify payment', 'Please refresh or contact support.');
    }
  }, [API, refreshUser]);

  useEffect(() => {
    if (returnStatus === 'success' && sessionId) {
      verify(sessionId);
    } else {
      loadPlan();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const subscribe = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/service-provider/upgrade/checkout`,
        { origin_url: window.location.origin });
      window.location.href = data.url; // → Stripe Checkout
    } catch (e) {
      notify.error('Could not start checkout', e.response?.data?.detail || '');
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-orange-50/40 flex items-center justify-center p-4" data-testid="sp-upgrade-page">
      <Card className="w-full max-w-lg p-8">
        {phase === 'verifying' && (
          <div className="text-center py-8" data-testid="sp-upgrade-verifying">
            <Loader2 className="mx-auto animate-spin text-orange-500 mb-4" size={32} />
            <h1 className="text-xl font-semibold text-slate-900">Confirming your subscription…</h1>
            <p className="text-sm text-slate-500 mt-1">This only takes a moment.</p>
          </div>
        )}

        {phase === 'success' && (
          <div className="text-center py-6" data-testid="sp-upgrade-success">
            <CheckCircle2 className="mx-auto text-emerald-500 mb-4" size={40} />
            <h1 className="text-2xl font-bold text-slate-900">You're all set 🎉</h1>
            <p className="text-sm text-slate-500 mt-2 mb-6">
              Your Service Desk is now on the Pro plan. Your trial banner is gone and everything's unlocked.
            </p>
            <Button onClick={() => navigate('/service-desk')} className="bg-orange-500 hover:bg-orange-600 text-white" data-testid="sp-upgrade-to-desk">
              Go to my desk <ArrowRight size={15} className="ml-1.5" />
            </Button>
          </div>
        )}

        {(phase === 'plan' || phase === 'cancelled') && plan && (
          <div data-testid="sp-upgrade-plan">
            {phase === 'cancelled' && (
              <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-5" data-testid="sp-upgrade-cancelled">
                <XCircle size={15} /> Checkout cancelled — no charge was made.
              </div>
            )}
            <span className="inline-flex items-center gap-2 rounded-full bg-orange-100 text-orange-700 px-3 py-1 text-xs font-bold uppercase tracking-wider">
              <Headset size={12} /> Service Desk
            </span>
            <h1 className="mt-4 text-2xl font-bold text-slate-900">{plan.plan.name}</h1>
            <p className="text-sm text-slate-500 mt-1">{plan.plan.blurb}</p>
            <div className="mt-5 flex items-baseline gap-1">
              <span className="text-4xl font-black text-slate-900" data-testid="sp-upgrade-price">{plan.price_display.split('/')[0]}</span>
              <span className="text-slate-400 font-semibold">/{plan.plan.interval}</span>
            </div>
            <ul className="mt-6 space-y-2.5">
              {PERKS.map((p) => (
                <li key={p} className="flex items-start gap-2.5 text-sm text-slate-700">
                  <Check size={16} className="text-emerald-500 mt-0.5 flex-shrink-0" /> {p}
                </li>
              ))}
            </ul>
            <Button onClick={subscribe} disabled={busy} className="w-full mt-7 bg-orange-500 hover:bg-orange-600 text-white h-11" data-testid="sp-upgrade-subscribe">
              {busy ? <Loader2 className="animate-spin" size={16} /> : <>Subscribe — {plan.price_display} <ArrowRight size={15} className="ml-1.5" /></>}
            </Button>
            <p className="mt-3 text-xs text-slate-400 text-center flex items-center justify-center gap-1.5">
              <ShieldCheck size={13} /> Secure checkout by Stripe · cancel anytime
            </p>
            <button onClick={() => navigate('/service-desk')} className="w-full mt-3 text-xs text-slate-500 hover:text-slate-700" data-testid="sp-upgrade-back">
              Back to my desk
            </button>
          </div>
        )}

        {(phase === 'plan' || phase === 'cancelled') && !plan && (
          <div className="text-center py-8"><Loader2 className="mx-auto animate-spin text-slate-300" size={28} /></div>
        )}
      </Card>
    </div>
  );
}
