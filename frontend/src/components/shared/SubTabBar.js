/**
 * SubTabBar — the canonical secondary / "lateral options" menu used across
 * every module. It wraps the shared PillTabBar (auto-scroll + edge fade +
 * chevrons) and renders the standard cyan pill buttons so every module's
 * sub-navigation looks identical to the CRM / Memberships top nav.
 *
 * Usage:
 *   <SubTabBar
 *     tabs={[{ id, label, icon }]}
 *     active={tab}
 *     onChange={setTab}
 *     testId="afs-subnav"
 *   />
 *
 * Keeps every module consistent without each page re-implementing pill markup.
 */
import PillTabBar from './PillTabBar';

const ACTIVE_STYLE = {
  background: 'var(--color-brand-cyan)',
  color: 'var(--color-ink)',
  boxShadow: '0 6px 16px -6px rgba(25, 205, 255, 0.35)',
};
const INACTIVE_STYLE = { color: 'var(--theme-text-muted)', background: 'transparent' };

export default function SubTabBar({
  tabs,
  active,
  onChange,
  testId,
  ariaLabel = 'Sections',
  className = '',
  idKey = 'id',
  labelKey = 'label',
  size = 'md',
}) {
  const pad = size === 'sm' ? 'px-3.5 py-2 text-xs' : 'px-4 py-2.5 text-sm';
  const iconSize = size === 'sm' ? 13 : 14;
  return (
    <PillTabBar
      className={`mb-5 pulse-font-body ${className}`}
      activeId={active}
      testId={testId}
      ariaLabel={ariaLabel}
    >
      {tabs.map((t) => {
        const id = t[idKey];
        const label = t[labelKey];
        const Icon = t.icon;
        const isActive = active === id;
        return (
          <button
            key={id}
            type="button"
            data-pill-id={id}
            data-testid={t.testId || (testId ? `${testId}-${id}` : undefined)}
            onClick={() => onChange(id)}
            className={`flex-shrink-0 inline-flex items-center gap-2 rounded-full font-semibold whitespace-nowrap transition-all ${pad}`}
            style={isActive ? ACTIVE_STYLE : INACTIVE_STYLE}
          >
            {Icon ? <Icon size={iconSize} className="shrink-0" /> : null}
            <span>{label}</span>
          </button>
        );
      })}
    </PillTabBar>
  );
}
