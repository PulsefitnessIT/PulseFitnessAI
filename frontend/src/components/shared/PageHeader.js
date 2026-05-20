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
 * Iter 216h244 — title + subtitle render path now suppressed
 * platform-wide (sub-header sweep). Component still accepts the
 * props for back-compat but only renders the actions strip. See the
 * inline comment in the function body for rationale.
 */

const PageHeader = ({
  actions,
  testId,
  className = '',
  // Iter 216h244 — title / subtitle / icon / helpId / badge are
  // intentionally absorbed and discarded. The platform-wide sub-header
  // sweep dropped the H2+description render path; props remain on the
  // caller API for back-compat so we don't have to edit ~30 tabs.
  ...rest
}) => {
  void rest;  // satisfies the linter — see comment above.
  // If the caller passes `actions`, render JUST a right-aligned action
  // strip so "Log fault", "Upload", "Add staff" etc. keep working.
  // If no actions, return null entirely so the now-redundant header
  // is invisible AND collapses any surrounding margin.
  if (!actions) return null;
  return (
    <div
      className={`flex items-center justify-end gap-2 flex-wrap ${className}`}
      data-testid={testId || 'page-header'}
    >
      <div
        className="flex items-center gap-2 shrink-0"
        data-testid={testId ? `${testId}-actions` : 'page-header-actions'}
      >
        {actions}
      </div>
    </div>
  );
};

export default PageHeader;
