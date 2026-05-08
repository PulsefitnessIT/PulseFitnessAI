/**
 * PullToRefresh — native-feel pull-to-refresh for mobile.
 *
 * Iter 215d8 — gives the operator surface a "feels like a real app"
 * gesture: pull down from the top of any scrollable surface to refresh
 * the current view. Desktop is untouched (wheel scrolling never
 * triggers the gesture). iOS Safari rubber-banding is respected — we
 * only engage once the user is at `scrollTop === 0` AND still pulling
 * downward.
 *
 * Contract:
 *   <PullToRefresh onRefresh={async () => { await reload(); }}>
 *     ... any scrollable content ...
 *   </PullToRefresh>
 *
 * `onRefresh` is awaited — the spinner stays visible until the promise
 * resolves. Thresholds: ACTIVATE = 72px, MAX = 120px. Feedback:
 * translate-y follows the finger with a 0.45 resistance curve, and the
 * embedded indicator rotates its chevron into a spinner at the
 * activation point.
 */
import React, { useRef, useState, useCallback } from 'react';
import { Loader2, ArrowDown } from 'lucide-react';

const ACTIVATE_DISTANCE = 72;
const MAX_DISTANCE = 120;
const RESISTANCE = 0.45;

export default function PullToRefresh({ onRefresh, children, disabled = false, className = '' }) {
  const ref = useRef(null);
  const startY = useRef(null);
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const reset = useCallback(() => {
    startY.current = null;
    setPull(0);
  }, []);

  const onTouchStart = useCallback((e) => {
    if (disabled || refreshing) return;
    // Only engage at the very top of the scroll container. We walk up to
    // `window` because pages frequently let <body> or <html> scroll.
    const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
    if (scrollTop > 0) return;
    startY.current = e.touches[0].clientY;
  }, [disabled, refreshing]);

  const onTouchMove = useCallback((e) => {
    if (startY.current === null) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy <= 0) return; // upward swipe — ignore
    // Apply resistance so the user "feels" the pull getting harder.
    const dampened = Math.min(MAX_DISTANCE, dy * RESISTANCE);
    setPull(dampened);
  }, []);

  const onTouchEnd = useCallback(async () => {
    if (startY.current === null) return;
    const hit = pull >= ACTIVATE_DISTANCE;
    if (hit && onRefresh) {
      setRefreshing(true);
      setPull(ACTIVATE_DISTANCE);
      try { await onRefresh(); }
      finally {
        setRefreshing(false);
        reset();
      }
    } else {
      reset();
    }
  }, [pull, onRefresh, reset]);

  const showIndicator = pull > 4 || refreshing;
  const activated = pull >= ACTIVATE_DISTANCE || refreshing;

  return (
    <div
      ref={ref}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={onTouchEnd}
      className={`relative ${className}`}
      data-testid="pull-to-refresh"
      data-refreshing={refreshing ? 'true' : 'false'}
    >
      {/* Indicator — lives above the content, revealed by the pull */}
      {showIndicator && (
        <div
          className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-center transition-opacity"
          style={{
            transform: `translateY(${Math.max(0, pull - 36)}px)`,
            opacity: Math.min(1, pull / 40),
          }}
          data-testid="pull-to-refresh-indicator"
          aria-hidden="true"
        >
          <div
            className="h-9 w-9 rounded-full border shadow-sm flex items-center justify-center bg-[color:var(--theme-surface)] border-[color:var(--theme-border)]"
            style={{ color: activated ? 'var(--color-brand-blue)' : 'var(--theme-text-muted)' }}
          >
            {refreshing ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <ArrowDown
                size={16}
                className="transition-transform"
                style={{ transform: activated ? 'rotate(180deg)' : 'rotate(0deg)' }}
              />
            )}
          </div>
        </div>
      )}
      {/* Content — follows the finger */}
      <div
        className="will-change-transform"
        style={{
          transform: `translate3d(0, ${pull}px, 0)`,
          transition: startY.current === null ? 'transform 260ms cubic-bezier(0.22, 1, 0.36, 1)' : 'none',
        }}
      >
        {children}
      </div>
    </div>
  );
}
