import React from 'react';
import { Loader2 } from 'lucide-react';

export const PRIORITY = {
  p1: { label: 'P1 · Critical', cls: 'bg-red-100 text-red-700 border-red-200' },
  p2: { label: 'P2 · High', cls: 'bg-orange-100 text-orange-700 border-orange-200' },
  p3: { label: 'P3 · Medium', cls: 'bg-amber-100 text-amber-700 border-amber-200' },
  p4: { label: 'P4 · Low', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
};

export const STATUS_LABEL = {
  new: 'New', triaged: 'Triaged', assigned: 'Allocated', en_route: 'En route',
  on_site: 'On site', paused_parts: 'Waiting for parts', paused_customer: 'On hold',
  repaired: 'Repaired', awaiting_sign_off: 'Awaiting sign-off', closed: 'Completed',
  invoiced: 'Completed', rejected: 'Rejected',
};

export const HEALTH = {
  normal: { label: 'Normal', dot: 'bg-emerald-500', cls: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  attention: { label: 'Attention Required', dot: 'bg-amber-500', cls: 'text-amber-700 bg-amber-50 border-amber-200' },
  critical: { label: 'Critical', dot: 'bg-red-500', cls: 'text-red-700 bg-red-50 border-red-200' },
};

export function Card({ className = '', children, ...rest }) {
  return <div className={`bg-white border border-slate-200 rounded-2xl shadow-sm ${className}`} {...rest}>{children}</div>;
}

export function Badge({ children, className = '', ...rest }) {
  return <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${className}`} {...rest}>{children}</span>;
}

export function PriorityBadge({ p, testid }) {
  const cfg = PRIORITY[p] || PRIORITY.p3;
  return <Badge className={cfg.cls} data-testid={testid}>{cfg.label}</Badge>;
}

export function Btn({ children, variant = 'primary', className = '', full, ...rest }) {
  const base = 'inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.99]';
  const variants = {
    primary: 'bg-cyan-600 hover:bg-cyan-700 text-white',
    dark: 'bg-slate-900 hover:bg-slate-800 text-white',
    ghost: 'bg-slate-100 hover:bg-slate-200 text-slate-700',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
    outline: 'border border-slate-300 hover:bg-slate-50 text-slate-700 bg-white',
  };
  return (
    <button className={`${base} ${variants[variant]} px-4 py-3 text-sm ${full ? 'w-full' : ''} ${className}`} {...rest}>
      {children}
    </button>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slate-400" data-testid="bfpo-loading">
      <Loader2 className="w-5 h-5 animate-spin" /> {label || 'Loading…'}
    </div>
  );
}

export function Empty({ icon: Icon, title, sub, testid }) {
  return (
    <div className="text-center py-16 px-6" data-testid={testid}>
      {Icon && <Icon className="w-10 h-10 mx-auto text-slate-300 mb-3" />}
      <p className="font-semibold text-slate-700">{title}</p>
      {sub && <p className="text-sm text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </label>
  );
}

export const inputCls = 'w-full rounded-xl border border-slate-300 px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent';

export const ROLE_LABEL = {
  engineer: 'MOD / BFPO Engineer',
  lead: 'MOD / BFPO Lead Engineer',
  staff: 'Pulse MOD Service Staff',
};

export const PULSE_LOGO = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';

export function localTime(iso, tz) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      timeZone: tz || undefined, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return String(iso).slice(0, 16).replace('T', ' '); }
}
