/**
 * PulseProUpgradeCta (Iter 238c) — operator-facing conversion card.
 *
 * Renders a hero "Try Pulse Pro free for 3 days" banner on the Lite
 * dashboard so operators can self-serve unlock Memberships + CRM +
 * Marketing in one click. Backed by `/api/me/upgrade-to-pro` which
 * starts a 3-day free trial of every bolt-on.
 *
 * Visibility:
 *   • Hidden once `user.account_type === 'pulse_pro'` or master admin.
 *   • Owners see the live CTA. Non-owners see "Ask your owner" copy
 *     with the same module preview so they understand what's locked.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import {
  Crown, Calendar, Briefcase, Rocket, Sparkles, ArrowRight,
  CheckCircle2, Loader2, Lock, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;

const BOLT_ONS = [
  {
    key: 'memberships',
    label: 'Memberships',
    icon: Calendar,
    accent: 'from-emerald-500 to-blue-500',
    blurb: 'Member portal, class booking, kiosk check-in.',
  },
  {
    key: 'marketing',
    label: 'Marketing',
    icon: Rocket,
    accent: 'from-fuchsia-500 to-rose-500',
    blurb: 'Email/SMS/push journeys + AI Creative Studio.',
  },
  {
    key: 'crm',
    label: 'CRM',
    icon: Briefcase,
    accent: 'from-blue-500 to-violet-500',
    blurb: 'Lead pipeline, deal flow, AI follow-ups.',
  },
];

// `inSettings` renders the same card inside Account settings → Plan & Billing,
// where it stays reachable after the dashboard banner has been closed.
export default function PulseProUpgradeCta({ inSettings = false }) {
  const { user, refreshMe } = useAuth();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [trial, setTrial] = useState(null);

  const accountType = (user?.account_type || '').toLowerCase();
  const eligible = !user?.is_master_admin && accountType === 'lite';
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = { Authorization: `Bearer ${token}` };

  useEffect(() => {
    if (!eligible) return;
    axios.get(`${API}/api/me/pro-trial`, { headers }).then((r) => setTrial(r.data)).catch(() => setTrial(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- headers rebuilt each render; token read at call time
  }, [eligible]);

  // Master admin / Pro orgs / non-Lite operators don't see this. Once the
  // organisation has used its one free trial the card disappears everywhere;
  // a closed banner only hides the dashboard copy.
  if (!eligible || !trial || !trial.available) return null;
  if (!inSettings && trial.banner_dismissed) return null;

  const isOwner = (user?.role || '').toLowerCase() === 'owner';

  const dismiss = async () => {
    setTrial({ ...trial, banner_dismissed: true });
    try {
      await axios.post(`${API}/api/me/pro-trial/dismiss-banner`, {}, { headers });
      notify.success('Banner closed', 'You can still start your free trial from Account settings → Plan & Billing.');
    } catch (e) { notifyApiError(notify, e, 'Could not close the banner'); }
  };

  const startTrial = async () => {
    if (!isOwner) {
      notify.error('Owner-only', 'Ask the organisation owner to start your free Pro trial.');
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/api/me/upgrade-to-pro`,
        { start_trials: ['memberships', 'crm', 'marketing'] },
        { headers },
      );
      const trials = r.data?.trials_started || [];
      notify.success(
        'Welcome to Pulse Pro',
        `Started ${trials.length} free trial${trials.length === 1 ? '' : 's'} — 3 days each. Tap any module in the switcher to dive in.`,
        { duration: 9000 },
      );
      setDone(true);
      // Refresh /api/auth/me so the rest of the app picks up the new
      // tier + module_access without a full reload.
      try { await refreshMe?.(); } catch (_) { /* fall back to reload */ }
      setTimeout(() => { window.location.reload(); }, 1200);
    } catch (e) {
      notifyApiError(notify, e, 'Could not start your free Pro trial');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={`on-dark relative overflow-hidden rounded-2xl border border-amber-500/30 bg-gradient-to-br from-zinc-950 via-zinc-900 to-violet-950/40 p-5 sm:p-6 ${inSettings ? '' : 'mb-6'}`}
      data-testid={inSettings ? 'pulse-pro-upgrade-cta-settings' : 'pulse-pro-upgrade-cta'}
    >
      {/* Subtle accent bloom */}
      <div className="pointer-events-none absolute -top-24 -right-24 w-72 h-72 rounded-full bg-gradient-to-br from-amber-500/30 to-rose-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -left-20 w-80 h-80 rounded-full bg-gradient-to-br from-fuchsia-500/20 to-blue-500/10 blur-3xl" />

      {!inSettings && (
        <button
          type="button"
          onClick={dismiss}
          aria-label="Close trial banner"
          className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full inline-flex items-center justify-center hover:bg-white/10"
          style={{ color: '#d4d4d8' }}
          data-testid="pulse-pro-cta-dismiss"
        >
          <X size={15} />
        </button>
      )}
      <div className={`relative flex flex-col gap-5 ${inSettings ? '' : 'lg:flex-row lg:items-center'}`}>
        <div className="flex-1 min-w-0">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-200 text-[10px] uppercase tracking-wider font-bold mb-3">
            <Crown size={11} /> Pulse Lite · 3 modules locked
          </div>
          <h2 className="pulse-font-heading text-2xl sm:text-3xl font-bold text-white leading-tight">
            Unlock everything for <span className="bg-gradient-to-r from-amber-300 to-rose-300 bg-clip-text text-transparent">3 days, free</span>.
          </h2>
          <p className="text-sm text-zinc-300 mt-2 max-w-xl">
            Memberships, Marketing and CRM activate instantly — no card, no commitment. After 3 days, keep what you use and disable the rest.
          </p>

          <div className={`grid grid-cols-1 gap-2 mt-4 ${inSettings ? '' : 'sm:grid-cols-3'}`}>
            {BOLT_ONS.map((b) => {
              const Icon = b.icon;
              return (
                <div
                  key={b.key}
                  className="flex items-start gap-2.5 p-2.5 rounded-lg"
                  style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }}
                  data-testid={`pulse-pro-cta-bolt-${b.key}`}
                >
                  <div className={`w-8 h-8 rounded-md bg-gradient-to-br ${b.accent} flex items-center justify-center text-white shrink-0`}>
                    <Icon size={14} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold leading-tight" style={{ color: '#ffffff' }}>{b.label}</p>
                    <p className="text-[10px] leading-snug" style={{ color: '#a1a1aa' }}>{b.blurb}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className={`flex flex-col gap-2 shrink-0 ${inSettings ? 'sm:w-64' : 'lg:w-56'}`}>
          {isOwner ? (
            <button
              onClick={startTrial}
              disabled={busy || done}
              className="group w-full px-5 py-3.5 rounded-xl bg-gradient-to-r from-amber-400 via-orange-400 to-rose-400 text-zinc-900 text-sm font-extrabold uppercase tracking-wider shadow-lg shadow-amber-500/20 hover:shadow-amber-500/40 transition-all disabled:opacity-60 inline-flex items-center justify-center gap-2"
              data-testid="pulse-pro-cta-start-btn"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : done ? <CheckCircle2 size={16} /> : <Sparkles size={16} />}
              {busy ? 'Starting…' : done ? 'Pro activated' : 'Try Pulse Pro free'}
              {!busy && !done && <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />}
            </button>
          ) : (
            <button
              disabled
              className="w-full px-5 py-3.5 rounded-xl bg-white/10 border border-white/15 text-white text-xs font-bold cursor-not-allowed"
              data-testid="pulse-pro-cta-not-owner"
            >
              Owner can start trial
            </button>
          )}
          <p className="text-[10px] text-zinc-400 inline-flex items-center justify-center gap-1.5">
            <Lock size={9} /> No card · 3-day free trial · one per organisation
          </p>
        </div>
      </div>
    </div>
  );
}
