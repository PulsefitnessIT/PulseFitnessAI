/**
 * PageHeader — canonical title + subtitle + actions strip used across
 * GymAxis (full) and Pulse Lite portals so every sub-page (Faults,
 * Reports, Suppliers, Documents, Staffing) shares the same visual
 * architecture.
 *
 * Iter 216o — extracted from inline patterns in SupplierDashboardTab,
 * StaffingConsole and DashboardPage so we have a single, themed source
 * of truth for the per-tab header chrome.
 *
 *   <PageHeader
 *     title="Faults"
 *     subtitle="Reactive faults and planned maintenance"
 *     icon={AlertCircle}
 *     helpId="service-log-fault"
 *     actions={<Button>Log fault</Button>}
 *     testId="faults-header"
 *   />
 *
 * The component is intentionally small — it never wraps the page
 * content, only the heading row. Use it inside the existing
 * `space-y-*` flow at the top of each tab.
 */
import HelpHint from '@/components/HelpHint';

const PageHeader = ({
  title,
  subtitle,
  icon: Icon,
  helpId,
  actions,
  badge,
  testId,
  className = '',
}) => {
  return (
    <div
      className={`flex items-start justify-between gap-3 flex-wrap mb-4 ${className}`}
      data-testid={testId || 'page-header'}
    >
      <div className="min-w-0 flex-1">
        <h2
          className="text-xl sm:text-2xl font-semibold tracking-tight pulse-font-heading flex items-center gap-2"
          style={{ color: 'var(--theme-text)' }}
          data-testid={testId ? `${testId}-title` : 'page-header-title'}
        >
          {Icon ? (
            <Icon
              size={20}
              className="shrink-0"
              style={{ color: 'var(--color-brand-cyan-hover)' }}
            />
          ) : null}
          <span className="truncate">{title}</span>
          {helpId ? (
            <HelpHint
              guideId={helpId}
              testId={testId ? `${testId}-help` : 'page-header-help'}
              className="ml-1 shrink-0"
            />
          ) : null}
          {badge ? <span className="ml-1 shrink-0">{badge}</span> : null}
        </h2>
        {subtitle ? (
          <p
            className="text-sm pulse-font-body mt-0.5"
            style={{ color: 'var(--theme-text-muted)' }}
            data-testid={testId ? `${testId}-subtitle` : 'page-header-subtitle'}
          >
            {subtitle}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div
          className="flex items-center gap-2 shrink-0 mt-1"
          data-testid={testId ? `${testId}-actions` : 'page-header-actions'}
        >
          {actions}
        </div>
      ) : null}
    </div>
  );
};

export default PageHeader;
