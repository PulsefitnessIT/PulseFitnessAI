/**
 * GuidedTour — generic, event-driven, Joyride-based walkthrough host.
 *
 * Mount once at the App root. Anywhere in the app (including the Help
 * Centre's "Start walkthrough" button) fires a CustomEvent:
 *
 *   window.dispatchEvent(new CustomEvent('gymaxis:start-tour', {
 *     detail: { tourId: 'service-log-fault', steps: [...], onFinish: 'navigate-to:/pulse' },
 *   }));
 *
 * The host picks it up and runs the steps. Finish/skip marks the tour
 * complete in localStorage (`gymaxis_walkthroughs_done`) so the Setup
 * Checklist knows the user has done it. Unlike the existing ProductTour,
 * this component:
 *   - doesn't auto-run on mount;
 *   - accepts ad-hoc steps per event (no hard-coded corpus);
 *   - co-exists with ProductTour (different localStorage keys).
 *
 * Step format mirrors Joyride: { target, title, content, placement? }.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Joyride, STATUS } from 'react-joyride';
import { useNavigate } from 'react-router-dom';

const DONE_KEY = 'gymaxis_walkthroughs_done';

const styles = {
  tooltip: {
    borderRadius: '16px',
    padding: '20px',
    fontSize: '14px',
    boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
    border: '1px solid rgba(255,255,255,0.08)',
  },
  tooltipTitle: { fontSize: '16px', fontWeight: 700, marginBottom: '6px' },
  tooltipContent: { fontSize: '13px', lineHeight: 1.6, padding: '4px 0' },
  buttonNext: { borderRadius: '10px', fontSize: '13px', fontWeight: 600, padding: '8px 20px', border: 'none' },
  buttonBack: { fontSize: '13px', marginRight: '8px' },
  buttonSkip: { fontSize: '12px' },
  spotlight: { borderRadius: '12px' },
};

function markDone(tourId) {
  if (!tourId) return;
  try {
    const done = JSON.parse(localStorage.getItem(DONE_KEY) || '[]');
    if (!done.includes(tourId)) {
      done.push(tourId);
      localStorage.setItem(DONE_KEY, JSON.stringify(done));
    }
    // Let the Setup Checklist re-render without a full reload.
    window.dispatchEvent(new CustomEvent('gymaxis:walkthrough-done', { detail: { tourId } }));
  } catch { /* ignore */ }
}

export default function GuidedTour() {
  const [active, setActive] = useState(null); // { tourId, steps, initialRoute, onFinish }
  const [run, setRun] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e) => {
      const d = e.detail || {};
      if (!Array.isArray(d.steps) || d.steps.length === 0) return;
      // Hard-disable any concurrent tour so we don't stack overlays.
      setRun(false);
      setActive(d);
      // If the caller needs us on a different route first, navigate
      // there and wait for the DOM to settle before kicking the tour.
      if (d.initialRoute && typeof window !== 'undefined' && window.location.pathname !== d.initialRoute) {
        navigate(d.initialRoute);
      }
      // Give React a moment to paint the target DOM nodes.
      setTimeout(() => setRun(true), 600);
    };
    window.addEventListener('gymaxis:start-tour', handler);
    return () => window.removeEventListener('gymaxis:start-tour', handler);
  }, [navigate]);

  const handleEvent = useCallback((event) => {
    const { type, status } = event;
    if (type === 'tour:end' || status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      if (status === STATUS.FINISHED) markDone(active?.tourId);
      setRun(false);
      setActive(null);
    }
  }, [active]);

  if (!active) return null;

  return (
    <Joyride
      steps={active.steps}
      run={run}
      continuous
      scrollToFirstStep
      disableScrollParentFix
      disableScrolling
      showProgress
      showSkipButton
      options={{
        arrowColor: 'var(--color-ink)',
        backgroundColor: 'var(--color-ink)',
        primaryColor: 'var(--color-brand-cyan)',
        textColor: 'var(--color-neutral-50)',
        overlayColor: 'rgba(0, 0, 0, 0.65)',
        zIndex: 10000,
      }}
      styles={styles}
      onEvent={handleEvent}
      locale={{ back: 'Back', close: 'Close', last: 'Finish', next: 'Next', skip: 'Skip walkthrough' }}
      floaterProps={{ disableAnimation: true }}
    />
  );
}

/** Helper — used by Help Centre "Start walkthrough" button and others. */
export function startWalkthrough({ tourId, steps, initialRoute }) {
  window.dispatchEvent(new CustomEvent('gymaxis:start-tour', {
    detail: { tourId, steps, initialRoute },
  }));
}

/** List of tour IDs the current device has finished. */
export function getCompletedWalkthroughs() {
  try { return JSON.parse(localStorage.getItem(DONE_KEY) || '[]'); }
  catch { return []; }
}
