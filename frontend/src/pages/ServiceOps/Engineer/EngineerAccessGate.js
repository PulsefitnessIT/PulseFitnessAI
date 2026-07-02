/**
 * EngineerAccessGate — iter 216h77.
 *
 * Rendered in place of the Engineer Home when the backend returns a
 * 402 "engineer_app_blocked". Different CTAs per reason so the engineer
 * always knows the exact next step — never an opaque error toast.
 */
import { Link } from 'react-router-dom';
import {
  Lock, CreditCard, ClipboardEdit, Clock, AlertTriangle, Sparkles,
} from 'lucide-react';

const REASON_CONFIG = {
  needs_application: {
    icon: ClipboardEdit, color: '#0e7490',
    title: 'Apply to the Partner Engineer Network',
    sub:   'Take jobs through the Engineer App and earn commission on every gym you refer.',
    cta:   { label: 'Apply now', to: '/partners/engineers/apply' },
  },
  application_pending: {
    icon: Clock, color: '#d97706',
    title: 'Your application is under review',
    sub:   "We aim to respond within 2 working days. We'll email you the moment your application is approved.",
    cta:   { label: 'View status', to: '/partner-engineer' },
  },
  application_rejected: {
    icon: AlertTriangle, color: '#dc2626',
    title: 'Application not approved',
    sub:   'Update your details and resubmit — most approvals are quick once the missing info is in.',
    cta:   { label: 'Update & resubmit', to: '/partners/engineers/apply' },
  },
  suspended: {
    icon: AlertTriangle, color: '#dc2626',
    title: 'Engineer App access suspended',
    sub:   'Your Partner Engineer access has been suspended. Contact Pulse Fitness support to discuss next steps.',
    cta:   null,
  },
  needs_subscription: {
    icon: CreditCard, color: '#0e7490',
    title: 'Activate the Engineer App',
    sub:   'Start the £30/mo Partner Engineer Plan to unlock the Engineer App. Auto-discounts: £15/mo at 5 active referrals · free at 10+.',
    cta:   { label: 'Start subscription', to: '/partner-engineer' },
  },
};

export default function EngineerAccessGate({ detail }) {
  const reason = detail?.reason || 'needs_subscription';
  const config = REASON_CONFIG[reason] || REASON_CONFIG.needs_subscription;
  const Icon = config.icon;

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-zinc-50 via-white to-purple-50 dark:from-zinc-950 dark:via-zinc-900 dark:to-purple-950/40"
      data-testid={`engineer-access-gate-${reason}`}>
      <div className="max-w-md w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-8 shadow-sm">
        <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-wider mb-4" style={{ color: config.color }}>
          <Lock size={11} /> Engineer App access
        </div>

        <div className="rounded-xl p-4 mb-5"
          style={{ background: `${config.color}15`, border: `1px solid ${config.color}40` }}>
          <Icon size={32} style={{ color: config.color }} />
        </div>

        <h1 className="text-2xl font-black text-zinc-900 dark:text-zinc-100 mb-2"
          data-testid="engineer-access-title">
          {config.title}
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-6 leading-relaxed">
          {config.sub}
        </p>

        {config.cta && (
          <Link to={config.cta.to}
            className="block w-full text-center px-5 py-3 rounded-lg text-white text-sm font-bold transition"
            style={{ background: config.color }}
            data-testid="engineer-access-cta">
            {config.cta.label}
          </Link>
        )}

        <div className="mt-6 pt-5 border-t border-zinc-100 dark:border-zinc-800 text-[11px] text-zinc-500 dark:text-zinc-400 flex items-start gap-2">
          <Sparkles size={11} className="mt-0.5 shrink-0 text-zinc-400" />
          <span>
            Need to discuss a specific job? Ask the gym/customer who hired you to add you directly from their Service Desk — they can grant you access to that case without you needing the subscription.
          </span>
        </div>
      </div>
    </div>
  );
}
