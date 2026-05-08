/**
 * ModuleAccessGate (Iter 238) — wraps a module's main route.
 *
 * Renders the children when the operator has access; otherwise shows an
 * upgrade screen tailored to the user's situation:
 *   • Lite org → "Upgrade to Pulse Pro" CTA + 3-day trial picker
 *   • Pro org without this bolt-on → "Start 3-day trial of {Module}"
 *   • Active trial expired → "Trial used. Subscribe £X/mo"
 *   • Master Admin disabled the module → "Contact your administrator"
 *
 * Pulls live state from /api/me/module-trials (no cache) so the screen
 * always reflects the current org state.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Lock, Sparkles, Crown, ArrowRight, CheckCircle2, Loader2,
  Calendar, Briefcase, Rocket, AlertCircle,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;
const MODULE_META = {
  memberships: {
    label: 'Memberships',
    icon: Calendar,
    accent: 'from-emerald-500 to-blue-500',
    blurb: 'Member portal, class booking, plans, kiosk check-in, and the Mobile App Builder.',
    price_monthly: 5900,
    bullets: [
      'Unlimited members + family accounts',
      'Class booking + waitlist',
      'Stripe-powered recurring plans',
      'QR kiosk check-in',
      'Mobile App Builder',
    ],
  },
  crm: {
    label: 'CRM',
    icon: Briefcase,
    accent: 'from-blue-500 to-violet-500',
    blurb: 'Lead pipeline, deal flow, tenders and AI-powered follow-up assistance.',
    price_monthly: 4900,
    bullets: [
      'Lead + deal pipeline',
      'Email + activity tracking',
      'AI assistant for follow-ups',
      'Reports & forecasting',
    ],
  },
  marketing: {
    label: 'Marketing',
    icon: Rocket,
    accent: 'from-fuchsia-500 to-rose-500',
    blurb: 'Email/SMS/push campaigns, automations, AI Director and AI Creative Studio.',
    price_monthly: 3900,
    bullets: [
      'Email + SMS + push + in-app journeys',
      'Audience segmentation + dynamic lists',
      'AI Creative Studio (Gemini Nano Banana)',
      'A/B testing + funnel attribution',
    ],
  },
};

const formatGBP = (pence) => `£${(pence / 100).toFixed(0)}`;


export default function ModuleAccessGate({ module, children }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = React.useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [state, setState] = useState({ loading: true });

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/me/module-trials`, { headers });
      setState({ loading: false, ...r.data });
    } catch (e) {
      setState({ loading: false, error: e.response?.data?.detail || 'Failed to check access' });
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (state.loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" data-testid={`module-gate-${module}-loading`}>
        <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)]" />
      </div>
    );
  }
  if (state.error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-zinc-600 dark:text-zinc-300 text-sm" data-testid={`module-gate-${module}-error`}>
        {state.error}
      </div>
    );
  }
  if (state.module_access?.[module]) {
    return children;
  }

  return <UpgradeScreen module={module} state={state} onChange={load} headers={headers} />;
}


function UpgradeScreen({ module, state, onChange, headers }) {
  const meta = MODULE_META[module] || { label: module, icon: Sparkles, accent: 'from-blue-500 to-violet-500', blurb: '', price_monthly: 0, bullets: [] };
  const Icon = meta.icon;
  const isLite = state.account_type === 'lite';
  const trialInfo = state.trials?.[module];
  const trialUsed = trialInfo?.status === 'used';
  const isOwner = state.is_owner;
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(() => new Set(state.bolt_on_modules || ['memberships', 'crm', 'marketing']));

  const toggle = (m) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(m)) n.delete(m); else n.add(m);
      return n;
    });
  };

  const startTrial = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/me/module-trials/start`, { module }, { headers });
      notify.success(`${meta.label} trial started — ${r.data.days_remaining} days remaining.`);
      onChange();
    } catch (e) {
      notifyApiError(notify, e, `Failed to start ${meta.label} trial`);
    } finally { setBusy(false); }
  };

  const upgradeToPro = async () => {
    if (!isOwner) {
      notify.error('Only the organisation owner can upgrade — please ask them.');
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/me/upgrade-to-pro`, { start_trials: Array.from(selected) }, { headers });
      const trials = r.data.trials_started || [];
      notify.success(
        'Upgraded to Pulse Pro',
        trials.length ? `Started ${trials.length} bolt-on trial${trials.length === 1 ? '' : 's'} — ${state.trial_duration_days} days each.` : 'You can now start any bolt-on trial.',
        { duration: 8000 },
      );
      onChange();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to upgrade');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 px-4 py-12" data-testid={`module-gate-${module}`}>
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-8">
          <div className={`w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br ${meta.accent} flex items-center justify-center text-white mb-4 shadow-lg`}>
            <Icon size={28} />
          </div>
          <h1 className="text-3xl font-extrabold pulse-font-heading text-zinc-900 dark:text-zinc-100">
            {isLite ? `Upgrade to unlock ${meta.label}` : trialUsed ? `${meta.label} trial used` : `Try ${meta.label} free for ${state.trial_duration_days} days`}
          </h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-300 mt-2 max-w-xl mx-auto">{meta.blurb}</p>
        </div>

        {isLite ? (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6" data-testid="module-gate-upgrade-card">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-amber-500 to-rose-500 flex items-center justify-center text-white shrink-0">
                <Crown size={18} />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">Step 1 · Upgrade to Pulse Pro</h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                  Pulse Lite covers Operations only. Memberships, CRM and Marketing are bolt-ons available on Pro.
                </p>
              </div>
            </div>
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950/50 p-4 mb-4">
              <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-2">Step 2 · Pick the bolt-ons to try free</p>
              <div className="space-y-2">
                {state.bolt_on_modules.map((m) => {
                  const mm = MODULE_META[m] || { label: m, price_monthly: 0 };
                  const used = state.trials?.[m]?.status === 'used';
                  return (
                    <label key={m} className={`flex items-center gap-3 p-2.5 rounded-md border ${selected.has(m) && !used ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)]' : 'border-zinc-200 dark:border-zinc-800'} cursor-pointer ${used ? 'opacity-50 cursor-not-allowed' : ''}`} data-testid={`module-gate-trial-${m}`}>
                      <input type="checkbox" checked={selected.has(m) && !used} disabled={used} onChange={() => toggle(m)} />
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{mm.label}</p>
                        <p className="text-[11px] text-zinc-500 dark:text-zinc-400">{formatGBP(mm.price_monthly)} / month after the {state.trial_duration_days}-day trial</p>
                      </div>
                      {used && <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-400">Trial used</span>}
                    </label>
                  );
                })}
              </div>
            </div>
            <button
              onClick={upgradeToPro}
              disabled={busy || !isOwner}
              className="w-full px-4 py-3 rounded-md bg-gradient-to-r from-amber-500 to-rose-500 text-white text-sm font-bold disabled:opacity-50 inline-flex items-center justify-center gap-2"
              data-testid="module-gate-upgrade-btn"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Crown size={14} />}
              Upgrade to Pulse Pro {selected.size > 0 ? `+ start ${selected.size} bolt-on trial${selected.size === 1 ? '' : 's'}` : ''}
              <ArrowRight size={14} />
            </button>
            {!isOwner && (
              <p className="mt-3 text-xs text-amber-600 dark:text-amber-400 inline-flex items-center gap-1.5" data-testid="module-gate-not-owner">
                <AlertCircle size={11} /> Only the organisation owner can upgrade — please ask them to start this for you.
              </p>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6" data-testid="module-gate-trial-card">
            <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
              <Sparkles size={16} className="text-fuchsia-500" />
              {trialUsed ? `Your free ${meta.label} trial has ended` : `Start your free ${meta.label} trial`}
            </h2>
            <ul className="space-y-1.5 mb-4">
              {meta.bullets.map((b, i) => (
                <li key={i} className="text-xs text-zinc-700 dark:text-zinc-200 flex items-start gap-1.5" data-testid={`module-gate-bullet-${i}`}>
                  <CheckCircle2 size={12} className="text-emerald-500 mt-0.5 shrink-0" />{b}
                </li>
              ))}
            </ul>
            {trialUsed ? (
              <div className="rounded-lg bg-zinc-100 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 p-4 text-center">
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{formatGBP(meta.price_monthly)} / month</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Contact your master admin to subscribe.</p>
              </div>
            ) : (
              <button
                onClick={startTrial}
                disabled={busy || !isOwner}
                className={`w-full px-4 py-3 rounded-md bg-gradient-to-r ${meta.accent} text-white text-sm font-bold disabled:opacity-50 inline-flex items-center justify-center gap-2`}
                data-testid="module-gate-start-trial-btn"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Start {state.trial_duration_days}-day free trial
                <ArrowRight size={14} />
              </button>
            )}
            {!isOwner && !trialUsed && (
              <p className="mt-3 text-xs text-amber-600 dark:text-amber-400 inline-flex items-center gap-1.5">
                <AlertCircle size={11} /> Only the organisation owner can start trials.
              </p>
            )}
          </div>
        )}

        <p className="text-center text-[10px] text-zinc-400 dark:text-zinc-500 mt-6 inline-flex items-center justify-center gap-1.5 w-full">
          <Lock size={9} /> Module access is enforced server-side. No card required for any trial.
        </p>
      </div>
    </div>
  );
}
