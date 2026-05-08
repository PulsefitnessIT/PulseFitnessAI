/**
 * Generic horizontal sub-tab bar for consolidated Master Admin sections.
 *
 * Used by Finance / Security / Growth / Support to render multiple panels
 * under a single sidebar entry. Applies a ResizeObserver-driven edge-fade
 * so users see there's more content off-screen when the row overflows.
 */
import React from 'react';

export default function ConsolidatedTabsBar({ tabs, active, onChange, testid }) {
  const wrapRef = React.useRef(null);
  const [scrollable, setScrollable] = React.useState(false);

  React.useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const check = () => setScrollable(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [tabs?.length]);

  return (
    <div
      ref={wrapRef}
      className="mb-6 -mx-4 sm:mx-0 px-4 sm:px-0 overflow-x-auto scrollbar-hide scroll-smooth"
      data-testid={testid || 'consolidated-tabs'}
      data-scrollable={scrollable ? 'true' : 'false'}
      style={{
        WebkitOverflowScrolling: 'touch',
        maskImage: scrollable
          ? 'linear-gradient(to right, transparent 0, black 18px, black calc(100% - 18px), transparent 100%)'
          : undefined,
        WebkitMaskImage: scrollable
          ? 'linear-gradient(to right, transparent 0, black 18px, black calc(100% - 18px), transparent 100%)'
          : undefined,
      }}
    >
      <div className="inline-flex items-center gap-1 bg-slate-100/70 border border-slate-200 rounded-full p-1 whitespace-nowrap">
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onChange(t.id)}
              className={`flex-shrink-0 inline-flex items-center gap-1.5 px-3 sm:px-4 py-1.5 text-xs sm:text-sm font-semibold rounded-full transition-all ${
                isActive
                  ? 'bg-white text-slate-900 shadow-[0_2px_8px_-2px_rgba(15,23,42,0.12)] ring-1 ring-slate-200'
                  : 'text-slate-500 hover:text-slate-900'
              }`}
              data-testid={`consolidated-tab-${t.id}`}
            >
              {Icon && <Icon size={13} className={isActive ? 'text-[var(--gx-brand-from)]' : ''} />}
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
