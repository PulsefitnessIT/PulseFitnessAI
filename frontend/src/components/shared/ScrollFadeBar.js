import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

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
    </div>
  );
};

export default ScrollFadeBar;
