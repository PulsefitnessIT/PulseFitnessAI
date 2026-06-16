/**
 * KpiTile — canonical KPI card used across Pulse Fitness (full) and Pulse
 * Lite portals so every reports / overview / supplier / docs surface
 * shares the same atomic stat card.
 *
 * Iter 216o — extracted from the inline KpiTile in AllSitesOverview
 * and the variants in OverviewTab, LiteOverviewTab, SupplierDashboardTab
 * and PulseReportsTab.
 *
 *   <KpiTile
 *     icon={AlertTriangle}
 *     label="Open faults"
 *     value={42}
 *     tone="warning"           // optional, accent on icon + value
 *     trend="2 overdue"        // optional, small subtext beneath value
 *     onClick={() => …}        // optional, makes the card clickable
 *     testId="kpi-open-faults"
 *   />
 *
 * Tones map to the brand semantic palette:
 *   default | brand | success | warning | danger | accent
 *
 * Layout (matches the AllSitesOverview tile we already shipped):
 *   ┌──────────────────────────┐
 *   │ LABEL UPPERCASE   [icon] │
 *   │ 42                       │
 *   │ small trend hint         │
 *   └──────────────────────────┘
 */
import { Card } from '@/components/ui/card';

const TONE_MAP = {
  default: { icon: 'var(--theme-text-muted)',         value: 'var(--theme-text)'         },
  brand:   { icon: 'var(--color-brand-blue)',         value: 'var(--theme-text)'         },
  cyan:    { icon: 'var(--color-brand-cyan-hover)',   value: 'var(--theme-text)'         },
  success: { icon: 'var(--color-success-alt-2)',      value: 'var(--color-success-alt-2)'},
  warning: { icon: 'var(--color-warning)',            value: 'var(--color-warning)'      },
  danger:  { icon: 'var(--color-danger)',             value: 'var(--color-danger)'       },
  accent:  { icon: 'var(--color-brand-cyan-hover)',   value: 'var(--color-brand-cyan-hover)' },
};

const KpiTile = ({
  icon: Icon,
  label,
  value,
  trend,
  tone = 'brand',
  onClick,
  testId,
  className = '',
}) => {
  const palette = TONE_MAP[tone] || TONE_MAP.brand;
  const interactive = typeof onClick === 'function';
  return (
    <Card
      className={`p-4 flex flex-col gap-1 border transition-colors ${interactive ? 'cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)]' : ''} ${className}`}
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid={testId}
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } } : undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className="text-[10px] uppercase tracking-wider font-bold truncate"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid={testId ? `${testId}-label` : undefined}
        >
          {label}
        </span>
        {Icon ? (
          <Icon size={14} style={{ color: palette.icon }} className="shrink-0" />
        ) : null}
      </div>
      <div
        className="text-2xl sm:text-3xl font-bold tabular-nums tracking-tight"
        style={{ color: palette.value }}
        data-testid={testId ? `${testId}-value` : undefined}
      >
        {value}
      </div>
      {trend ? (
        <div
          className="text-[11px]"
          style={{ color: 'var(--theme-text-muted)' }}
          data-testid={testId ? `${testId}-trend` : undefined}
        >
          {trend}
        </div>
      ) : null}
    </Card>
  );
};

export default KpiTile;
