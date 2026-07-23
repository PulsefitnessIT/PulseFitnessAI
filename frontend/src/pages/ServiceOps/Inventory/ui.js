import { Loader2 } from 'lucide-react';
import { statusLabel } from './api';

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 text-slate-500 py-8 justify-center" data-testid="inv-spinner">
      <Loader2 className="animate-spin" size={18} /> {label || 'Loading…'}
    </div>
  );
}

export function Card({ children, className = '', testId }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`} data-testid={testId}>
      {children}
    </div>
  );
}

export function StatCard({ label, value, tone = 'navy', testId }) {
  const tones = {
    navy: 'text-[#0B3D91]',
    amber: 'text-amber-600',
    green: 'text-emerald-600',
    red: 'text-rose-600',
    slate: 'text-slate-700',
  };
  return (
    <Card className="p-4" testId={testId}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${tones[tone] || tones.navy}`}>{value}</p>
    </Card>
  );
}

const TONE_MAP = {
  provisional: 'slate', serial_pending: 'amber', serial_assigned: 'blue', reserved: 'blue',
  needs_validation: 'amber', awaiting_stock: 'amber', partially_available: 'amber',
  fully_available: 'green', dispatched: 'blue', in_transit: 'blue', received_by_dealer: 'green',
  completed: 'green', cancelled: 'red', on_hold: 'red', quality_issue: 'red',
  ready: 'green', ready_with_warnings: 'amber', blocked: 'red',
};

export function StatusBadge({ status, className = '' }) {
  const tone = TONE_MAP[status] || 'slate';
  const styles = {
    slate: 'bg-slate-100 text-slate-700',
    amber: 'bg-amber-100 text-amber-800',
    blue: 'bg-blue-100 text-blue-800',
    green: 'bg-emerald-100 text-emerald-800',
    red: 'bg-rose-100 text-rose-800',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${styles[tone]} ${className}`}>
      {statusLabel(status)}
    </span>
  );
}

export function Btn({ children, variant = 'primary', className = '', ...props }) {
  const base = 'inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const variants = {
    primary: 'inv-cta text-white',
    secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'bg-red-600 text-white hover:bg-red-700',
    ai: 'border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100',
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Field({ label, children, hint, required }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-slate-600">
        {label}{required ? <span className="text-rose-500"> *</span> : null}
      </span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-slate-400">{hint}</span> : null}
    </label>
  );
}

export const inputCls = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-[#0B3D91] focus:outline-none focus:ring-1 focus:ring-[#0B3D91]';
