/**
 * Memberships console shared UI atoms.
 *
 * Iter 215bv — extracted from `MembershipsConsole.js` (was >2,000 lines).
 * Houses the small re-usable presentational components used throughout
 * the operator console + its modals: input field, select, modal shell,
 * action row, KPI tile, status pill, capacity bar, and friendly "no
 * data" placeholders. Logic lives in the parent tabs/modals; this file
 * is presentation-only.
 */
import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export function Header() {
  return null;
}

export function Kpi({ label, value, color = 'neutral' }) {
  // slate-200 hairline + rounded-2xl + soft shadow + brand-aligned tinted
  // backgrounds. Inside `theme-gymaxis` the cyan tone resolves to
  // brand-navy via the global token swap; outside, it stays cyan.
  const tones = {
    cyan: 'border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-[rgb(var(--rgb-brand-cyan)/0.05)]',
    emerald: 'border-emerald-500/30 bg-emerald-500/5',
    amber: 'border-amber-500/30 bg-amber-500/5',
    violet: 'border-violet-500/30 bg-violet-500/5',
    neutral: 'border-slate-200 bg-white',
  }[color];
  return (
    <div
      className={`rounded-2xl border p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)] transition-shadow ${tones}`}
      data-testid={`mbr-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`}
    >
      <div className="text-[10px] uppercase tracking-[0.14em] font-semibold text-[color:var(--theme-text-muted)]">{label}</div>
      <div className="text-2xl font-bold tracking-tight mt-1" style={{ letterSpacing: '-0.02em', color: 'var(--theme-text)' }}>{value}</div>
    </div>
  );
}

export function StatusPill({ status }) {
  const tone = {
    active: 'bg-emerald-500/15 text-emerald-300',
    frozen: 'bg-amber-500/15 text-amber-300',
    cancelled: 'bg-zinc-500/15 text-zinc-300',
    expired: 'bg-zinc-500/15 text-zinc-300',
    pending_payment: 'bg-amber-500/15 text-amber-300',
    booked: 'bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)]',
    waitlist: 'bg-violet-500/15 text-violet-300',
    attended: 'bg-emerald-500/15 text-emerald-300',
    no_show: 'bg-red-500/15 text-red-300',
    late_cancel: 'bg-orange-500/15 text-orange-300',
  }[status] || 'bg-white dark:bg-zinc-900/10 text-[color:var(--theme-text-muted)]';
  return <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${tone}`}>{(status || '—').replace('_', ' ')}</span>;
}

export function CapacityBar({ bookings, capacity }) {
  const pct = capacity > 0 ? Math.min(100, (bookings / capacity) * 100) : 0;
  const colour = pct >= 90 ? 'var(--color-danger)' : pct >= 60 ? 'var(--color-warning)' : 'var(--color-success)';
  return (
    <div className="flex items-center gap-2 shrink-0">
      <div className="w-20 h-1.5 bg-white dark:bg-zinc-900/10 rounded overflow-hidden">
        <div className="h-full" style={{ width: `${pct}%`, background: colour }} />
      </div>
      <div className="text-xs text-[color:var(--theme-text-muted)] font-bold w-10 text-right">{bookings}/{capacity}</div>
    </div>
  );
}

export function Loading() {
  return <div className="text-center text-[color:var(--theme-text-muted)] py-16 text-sm">Loading…</div>;
}

export function Empty({ text }) {
  return <div className="rounded-xl border border-[color:var(--theme-border)] bg-white dark:bg-zinc-900/[0.02] p-5 text-center text-[color:var(--theme-text-muted)] text-sm">{text}</div>;
}

export function Input({ label, value, onChange, onBlur, type = 'text', required, testid, hint, placeholder, list }) {
  return (
    <label className="block">
      {label !== null && label !== undefined && (
        <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">{label}{required ? ' *' : ''}</span>
      )}
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} placeholder={placeholder}
        list={list}
        className={`${label !== null && label !== undefined ? 'mt-1 ' : ''}w-full rounded-lg bg-[color:var(--theme-surface-hover)] border border-[color:var(--theme-border)] px-3 py-2 text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]`}
        required={required} data-testid={testid} />
      {hint && <span className="block mt-1 text-[10px] text-[color:var(--theme-text-muted)]">{hint}</span>}
    </label>
  );
}

export function Select({ label, value, onChange, options, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}
        className="mt-1 w-full rounded-lg bg-[color:var(--theme-surface-hover)] border border-[color:var(--theme-border)] px-3 py-2 text-sm text-[color:var(--theme-text)] focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]">
        {options.map((o) => <option key={o.value} value={o.value} className="bg-[color:var(--theme-surface)]">{o.label}</option>)}
      </select>
    </label>
  );
}

/**
 * Page-scroll modal shell. Outer page scrolls so the header is always
 * reachable from the top; the body has NO internal overflow on purpose
 * (iter 215bp fix to prevent header clipping for long forms).
 */
export function ModalShell({ title, eyebrow, testId, children, onClose, wide }) {
  React.useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  // Iter 215d6.2 — render into document.body via React portal so the
  // modal escapes any transformed ancestor (e.g. `.module-fade-in`).
  // Without this, position:fixed would be relative to <main> (1984px
  // tall) instead of the 844px viewport on mobile.
  if (typeof document === 'undefined') return null;
  return createPortal((
    // Iter 215d6 — on mobile the modal lives in the safe zone between the
    // fixed Navbar (h-16) and the MobileBottomNav (h-16–20). The outer
    // backdrop still covers the full viewport (bg-black/40) but the
    // content area is inset to `top-16 bottom-16` so the card never hides
    // behind the navs. Inside the card we use a flex-column layout so the
    // header stays pinned, the body scrolls, and the action footer (the
    // Save/Cancel children render last) is naturally at the bottom.
    <div
      className="fixed inset-0 z-[100] bg-black/40"
      onClick={onClose}
      data-testid={testId}
    >
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex items-stretch sm:items-center justify-center p-3 sm:p-4">
        <div
          className={`relative w-full ${wide ? 'max-w-2xl' : 'max-w-md'} h-full sm:h-auto sm:max-h-[calc(100vh-6rem)] bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] rounded-2xl shadow-xl flex flex-col overflow-hidden`}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-labelledby={`${testId || 'modal'}-title`}
        >
          <div className="flex-shrink-0 px-5 py-4 border-b border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] rounded-t-2xl flex items-start justify-between gap-3">
            <div className="min-w-0">
              {eyebrow && <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">{eyebrow}</div>}
              <h3 id={`${testId || 'modal'}-title`} className="font-extrabold text-lg mt-1 truncate" style={{ color: 'var(--theme-text)' }}>{title}</h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="h-9 w-9 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] bg-[color:var(--theme-bg,transparent)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-[color:var(--color-brand-cyan)] focus:ring-offset-1 transition-colors shrink-0"
              aria-label="Close"
              data-testid={`${testId || 'modal'}-close`}
            >
              <X size={18} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">{children}</div>
        </div>
      </div>
    </div>
  ), document.body);
}

export function ModalActions({ onCancel, onSave, saving, testId }) {
  // Iter 215d6 — `mt-auto` pushes the action row to the bottom of the
  // flex-column body when the form is short; `sticky bottom-0` keeps it
  // pinned when the form is long enough to scroll. Negative margins
  // cancel ModalShell's body padding so the footer hits the card edges.
  return (
    <div className="mt-auto sticky bottom-0 -mx-5 -mb-5 px-5 py-3 bg-[color:var(--theme-surface)] border-t border-[color:var(--theme-border)] flex gap-2">
      <button onClick={onSave} disabled={saving} className="flex-1 rounded-lg py-2.5 text-sm font-extrabold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid={testId}>
        {saving ? 'Saving…' : 'Save'}
      </button>
      <button onClick={onCancel} className="rounded-lg px-4 py-2.5 text-sm font-bold border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:bg-black/[0.04] dark:hover:bg-white dark:bg-zinc-900/5">Cancel</button>
    </div>
  );
}
