/**
 * PillTabBar — canonical options bar used by every main module
 * (Memberships, CRM, Marketing, Operations). Renders a horizontally
 * scrolling pill row that:
 *
 *   1. Auto-scrolls the active pill into view (desktop AND mobile) so
 *      the last options never hide behind the rounded border.
 *   2. Fades the left/right edges via CSS mask when the row overflows,
 *      giving users a visual hint more content exists.
 *   3. Shows subtle chevron buttons the user can click to page left or
 *      right through the tabs when overflow is present.
 *
 * The component is headless with respect to the actual pill look — the
 * caller renders any markup they like (same flex children as before).
 * That keeps the per-module pill styling (icons, accent colour, active
 * state) untouched while fixing the shared overflow UX in one place.
 */
import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function PillTabBar({
  children,
  activeId,
  className = '',
  testId,
  ariaLabel,
}) {
  const trackRef = useRef(null);
  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(false);

  const update = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    const scrollable = el.scrollWidth > el.clientWidth + 1;
    el.dataset.scrollable = scrollable ? 'true' : 'false';
    setShowLeft(scrollable && el.scrollLeft > 4);
    setShowRight(scrollable && el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  // Track layout: update on mount, resize, content change.
  useLayoutEffect(() => {
    update();
    const el = trackRef.current;
    if (!el) return;
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('resize', update);
    return () => { ro.disconnect(); window.removeEventListener('resize', update); };
  }, [update]);

  // Scroll active pill into view whenever it changes.
  useEffect(() => {
    const el = trackRef.current;
    if (!el || !activeId) return;
    // The pill is looked up by data-pill-id so the parent doesn't need
    // to forward refs for every tab. Caller must add
    // `data-pill-id={id}` to the pill button.
    const pill = el.querySelector(`[data-pill-id="${window.CSS.escape(String(activeId))}"]`);
    if (pill && typeof pill.scrollIntoView === 'function') {
      pill.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    }
    // Recompute chevron visibility after the scroll settles.
    const t = setTimeout(update, 320);
    return () => clearTimeout(t);
  }, [activeId, update]);

  const page = (dir) => {
    const el = trackRef.current;
    if (!el) return;
    const amount = Math.max(160, Math.floor(el.clientWidth * 0.6));
    el.scrollBy({ left: dir * amount, behavior: 'smooth' });
  };

  return (
    <div className={`pill-tab-bar ${className}`} data-testid={testId}>
      <button
        type="button"
        aria-label="Scroll tabs left"
        data-show={showLeft}
        onClick={() => page(-1)}
        className="pill-tab-bar__chev pill-tab-bar__chev--left"
        data-testid={testId ? `${testId}-chev-left` : undefined}
      >
        <ChevronLeft size={14} />
      </button>
      <nav
        ref={trackRef}
        onScroll={update}
        aria-label={ariaLabel}
        className="pill-tab-bar__track"
      >
        {children}
      </nav>
      <button
        type="button"
        aria-label="Scroll tabs right"
        data-show={showRight}
        onClick={() => page(1)}
        className="pill-tab-bar__chev pill-tab-bar__chev--right"
        data-testid={testId ? `${testId}-chev-right` : undefined}
      >
        <ChevronRight size={14} />
      </button>
    </div>
  );
}
