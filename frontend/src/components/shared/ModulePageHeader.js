/**
 * ModulePageHeader — ONE unified page header used identically across every
 * module (Operations, Memberships, CRM, Marketing, Comms Centre) so the top of
 * every module page looks the same right across the platform.
 *
 * Pattern (matches the existing Operations / Comms Centre headers):
 *   <Module name>  · <Tenant company>            <long-form date>
 *   <one-line description>                        [optional action slot]
 *
 * The module NAME carries the brand accent (gradient for neutral/GymAxis
 * tenants, brand-blue for Pulse-branded tenants); the tenant name is muted.
 */
import { format } from 'date-fns';

export const ModulePageHeader = ({
  moduleName,
  tenantName,
  subtitle,
  date,
  actionSlot,
  icon,
  isPulseBranded = false,
}) => {
  let today = date;
  if (!today) {
    try { today = format(new Date(), 'EEEE, d MMMM yyyy'); }
    catch { today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }); }
  }
  return (
    <header data-testid="module-page-header" className="mb-8">
      <div className="flex flex-col gap-4 md:flex-row md:justify-between md:items-start">
        <div className="min-w-0">
          <h1
            data-testid="module-title"
            className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight flex flex-wrap items-center gap-x-2.5 gap-y-1"
            style={{ color: 'var(--theme-text)' }}
          >
            {icon ? <span className="shrink-0 flex items-center">{icon}</span> : null}
            <span className={isPulseBranded ? '' : 'gx-grad-text'}>{moduleName}</span>
            {tenantName ? (
              <span
                data-testid="tenant-name"
                className="text-base sm:text-lg font-normal pulse-font-body"
                style={{ color: 'var(--theme-text-muted)' }}
              >
                · {tenantName}
              </span>
            ) : null}
          </h1>
          {subtitle ? (
            <p
              data-testid="module-subtitle"
              className="text-sm md:text-base font-medium pulse-font-body max-w-2xl"
              style={{ color: 'var(--theme-text-muted)' }}
            >
              {subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex flex-row items-center justify-between w-full gap-4 md:w-auto md:flex-col md:items-end md:justify-start md:gap-2 shrink-0">
          {actionSlot ? (
            <div data-testid="module-action-slot" className="order-2 md:order-1">{actionSlot}</div>
          ) : null}
          <p
            data-testid="module-date"
            className="text-sm font-semibold whitespace-nowrap order-1 md:order-2"
            style={{ color: 'var(--theme-text-muted)' }}
          >
            {today}
          </p>
        </div>
      </div>
    </header>
  );
};

export default ModulePageHeader;
