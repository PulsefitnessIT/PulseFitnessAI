import React from 'react';

export const fmtMoney = (pence) => {
  if (pence == null) return '£0';
  const v = Math.round(Number(pence) / 100);
  return `£${v.toLocaleString()}`;
};

export const fmtPct = (n) => `${(Number(n) || 0).toFixed(1)}%`;

export const StatCard = ({ label, value, hint, color = 'text-zinc-900 dark:text-zinc-100', bg = 'bg-zinc-50 dark:bg-zinc-800/60', icon: Icon, testid }) => (
  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-3 lg:p-5 shadow-sm" data-testid={testid}>
    <div className="flex items-center gap-2 lg:justify-between">
      {Icon && (
        <div className={`w-8 h-8 lg:w-10 lg:h-10 rounded-lg ${bg} flex items-center justify-center flex-shrink-0 lg:order-2`}>
          <Icon size={16} className={`${color} lg:w-5 lg:h-5`} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[10px] lg:text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 leading-tight">{label}</p>
        <p className="text-xl lg:text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
        {hint && <p className="text-[10px] lg:text-xs text-zinc-600 dark:text-zinc-400 mt-1 truncate">{hint}</p>}
      </div>
    </div>
  </div>
);

export const SectionCard = ({ title, action, children, className = '' }) => (
  <div className={`bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg shadow-sm p-4 lg:p-5 ${className}`}>
    <div className="flex items-center justify-between mb-3 lg:mb-4">
      <h3 className="text-base lg:text-lg font-semibold text-zinc-900 dark:text-zinc-100">{title}</h3>
      {action}
    </div>
    {children}
  </div>
);

export const Pill = ({ tone = 'zinc', children, testid }) => {
  const map = {
    zinc: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
    green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    red: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    blue: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    violet: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${map[tone]}`} data-testid={testid}>
      {children}
    </span>
  );
};

export const severityTone = (sev) => {
  if (sev === 'high') return 'red';
  if (sev === 'medium') return 'amber';
  return 'blue';
};
