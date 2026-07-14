import { Loader2 } from 'lucide-react';

export const money = (v, ccy = 'GBP') => {
  const n = Number(v || 0);
  try {
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: ccy, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `£${n.toLocaleString()}`;
  }
};

const STATUS_TONES = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  imported: 'bg-slate-100 text-slate-600 border-slate-200',
  awaiting_approval: 'bg-amber-50 text-amber-700 border-amber-200',
  approved: 'bg-blue-50 text-blue-700 border-blue-200',
  dispatched: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  partially_received: 'bg-violet-50 text-violet-700 border-violet-200',
  received: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  cancelled: 'bg-red-50 text-red-600 border-red-200',
  in_stock: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  low_stock: 'bg-amber-50 text-amber-700 border-amber-200',
  out_of_stock: 'bg-red-50 text-red-600 border-red-200',
};

export const StatusBadge = ({ status }) => (
  <span
    data-testid={`dp-status-${status}`}
    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border capitalize ${STATUS_TONES[status] || 'bg-slate-100 text-slate-600 border-slate-200'}`}
  >
    {String(status || '').replace(/_/g, ' ')}
  </span>
);

export const StatCard = ({ label, value, tone = 'slate', testid }) => {
  const tones = {
    slate: 'from-slate-50 to-white border-slate-200',
    brand: 'from-[var(--gx-brand-from)]/10 to-white border-[var(--gx-brand-from)]/20',
    emerald: 'from-emerald-50 to-white border-emerald-200',
    amber: 'from-amber-50 to-white border-amber-200',
    red: 'from-red-50 to-white border-red-200',
  };
  return (
    <div
      data-testid={testid}
      className={`rounded-xl border bg-gradient-to-br ${tones[tone]} p-4 transition-all hover:shadow-md`}
    >
      <div className="text-[10px] uppercase tracking-[0.14em] font-semibold text-slate-400">{label}</div>
      <div className="text-2xl font-bold text-slate-900 mt-1 tabular-nums">{value}</div>
    </div>
  );
};

export const Spinner = () => (
  <div className="flex items-center justify-center py-16 text-slate-400 text-sm">
    <Loader2 size={16} className="mr-2 animate-spin" /> Loading…
  </div>
);

export const Modal = ({ open, onClose, title, children, footer, testid }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid={testid}>
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-black/40" />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl leading-none" aria-label="Close dialog">×</button>
        </div>
        <div className="px-6 py-4 overflow-y-auto flex-1">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

export const Field = ({ label, children }) => (
  <label className="block mb-3">
    <span className="text-xs font-semibold text-slate-500 mb-1 block">{label}</span>
    {children}
  </label>
);

export const input = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--gx-brand-from)]/30';
