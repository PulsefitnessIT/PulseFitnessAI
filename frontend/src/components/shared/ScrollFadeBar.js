import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

/**
 * Wraps a horizontally-scrollable `.subtab-bar` pill row and shows a
 * subtle edge fade ONLY when the row actually overflows — so users on
 * narrow screens can tell there are more options one swipe away. The
 * fade hides again once that edge is reached, and never renders on a
 * row that fits (avoids fading the last pill on short bars).
 */
export const ScrollFadeBar = ({ children, className = '', wrapperClassName = '', testId, ...rest }) => {
  const barRef = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });

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

  return (
    <div className={`subtab-scroll-wrap ${wrapperClassName}`}>
      <div ref={barRef} className={`subtab-bar ${className}`} data-testid={testId} {...rest}>
        {children}
      </div>
      {edges.left && <span className="subtab-fade subtab-fade-left" aria-hidden="true" />}
      {edges.right && <span className="subtab-fade subtab-fade-right" aria-hidden="true" data-testid="subtab-scroll-hint-right" />}
    </div>
  );
};

export default ScrollFadeBar;
