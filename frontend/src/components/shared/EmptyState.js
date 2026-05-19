/**
 * EmptyState — Iter 215bt
 *
 * Reusable empty-state used across operator screens (CRM, Memberships,
 * Marketing, Operations) so a brand-new tenant sees a friendly "get
 * started" prompt with a primary CTA instead of a wall of "No data yet".
 *
 * Usage:
 *   <EmptyState
 *     icon={Users}
 *     title="No members yet"
 *     hint="Add your first member or import a CSV to get started."
 *     primaryAction={{ label: 'Add member', onClick: () => setAdding(true), testId: 'mbr-empty-add' }}
 *     secondaryAction={{ label: 'Bulk import', onClick: openImport }}
 *   />
 */

export const EmptyState = ({
  icon: Icon,
  title,
  hint,
  primaryAction,
  secondaryAction,
  testId,
  className = '',
}) => (
  <div
    className={`flex flex-col items-center justify-center text-center px-6 py-12 rounded-2xl border border-dashed border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)]/40 ${className}`}
    data-testid={testId || 'empty-state'}
  >
    {Icon && (
      <div className="w-14 h-14 rounded-2xl bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] flex items-center justify-center mb-4 shadow-sm">
        <Icon size={26} className="text-[color:var(--theme-text-muted)]" strokeWidth={1.5} />
      </div>
    )}
    <h3 className="text-base font-extrabold tracking-tight text-[color:var(--theme-text)] mb-1">{title}</h3>
    {hint && (
      <p className="text-sm text-[color:var(--theme-text-muted)] max-w-md leading-relaxed">{hint}</p>
    )}
    {(primaryAction || secondaryAction) && (
      <div className="flex flex-wrap items-center justify-center gap-2 mt-5">
        {primaryAction && (
          <button
            type="button"
            onClick={primaryAction.onClick}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-extrabold transition-colors"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid={primaryAction.testId || 'empty-state-primary'}
          >
            {primaryAction.label}
          </button>
        )}
        {secondaryAction && (
          <button
            type="button"
            onClick={secondaryAction.onClick}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-bold border border-[color:var(--theme-border)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] transition-colors"
            data-testid={secondaryAction.testId || 'empty-state-secondary'}
          >
            {secondaryAction.label}
          </button>
        )}
      </div>
    )}
  </div>
);

export default EmptyState;
