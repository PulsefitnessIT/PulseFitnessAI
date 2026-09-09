import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Wraps a horizontally-scrollable pill/tab row and shows a subtle edge
 * fade ONLY when the row actually overflows — so users on narrow screens
 * can tell there are more options one swipe away. The fade hides again
 * once that edge is reached, and never renders on a row that fits.
 *
 * Props:
 *   className      classes for the inner scroll element (e.g. "subtab-bar")
 *   wrapperClassName classes for the outer positioning wrapper (margins etc.)
 *   variant        "pill" (rounded, inset — for .subtab-bar) | "flat" (edge-to-edge)
 *   fadeColor      CSS colour the content fades into (match the row's background)
 *   scrollRef      optional ref that also points at the scroll element
 *   showChevrons   render tappable left/right paging buttons at the overflow edges
 *   testId         data-testid for the scroll element
 *   ...rest        spread onto the scroll element (style, role, etc.)
 */
export const ScrollFadeBar = ({
  children,
  className = '',
  wrapperClassName = '',
  variant = 'pill',
  fadeColor = 'var(--theme-surface)',
  scrollRef,
  showChevrons = false,
  testId,
  ...rest
}) => {
  const barRef = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const setRefs = useCallback((node) => {
    barRef.current = node;
    if (scrollRef) scrollRef.current = node;
  }, [scrollRef]);

  const measure = useCallback(() => {
    const el = barRef.current;
    if (!el) return;
    const maxScroll = el.scrollWidth - el.clientWidth;
    setEdges({
      left: el.scrollLeft > 1,
      right: maxScroll > 1 && el.scrollLeft < maxScroll - 1,
    });
  }, []);

  useLayoutEffect(() => { measure(); }, [measure, children]);

  useEffect(() => {
    const el = barRef.current;
    if (!el) return undefined;
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    let ro;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(measure);
      ro.observe(el);
    }
    window.addEventListener('resize', measure);
    return () => {
      el.removeEventListener('scroll', measure);
      if (ro) ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [measure]);

  const fadeStyle = { '--sfb-color': fadeColor };

  const page = (dir) => {
    const el = barRef.current;
    if (!el) return;
    const amount = Math.max(140, Math.floor(el.clientWidth * 0.7));
    el.scrollBy({ left: dir * amount, behavior: 'smooth' });
  };

  return (
    <div className={`sfb-wrap sfb-wrap-${variant} ${wrapperClassName}`}>
      <div ref={setRefs} className={className} data-testid={testId} {...rest}>
        {children}
      </div>
      {edges.left && (
        <span className={`sfb-fade sfb-fade-${variant} sfb-fade-left`} style={fadeStyle} aria-hidden="true" />
      )}
      {edges.right && (
        <span className={`sfb-fade sfb-fade-${variant} sfb-fade-right`} style={fadeStyle} aria-hidden="true" data-testid="subtab-scroll-hint-right" />
      )}
      {showChevrons && edges.left && (
        <button
          type="button"
          aria-label="Scroll tabs left"
          onClick={() => page(-1)}
          className={`sfb-chev sfb-chev-${variant} sfb-chev-left`}
          data-testid={testId ? `${testId}-chev-left` : 'sfb-chev-left'}
        >
          <ChevronLeft size={16} />
        </button>
      )}
      {showChevrons && edges.right && (
        <button
          type="button"
          aria-label="Scroll tabs right"
          onClick={() => page(1)}
          className={`sfb-chev sfb-chev-${variant} sfb-chev-right`}
          data-testid={testId ? `${testId}-chev-right` : 'sfb-chev-right'}
        >
          <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
};

export default ScrollFadeBar;
