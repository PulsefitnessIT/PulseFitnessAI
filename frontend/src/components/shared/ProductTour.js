import React, { useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Joyride, STATUS } from 'react-joyride';

const TOUR_KEY_GYMAXIS = 'gymaxis_tour_completed';
const TOUR_KEY_PULSE = 'pulse_tour_completed';

/**
 * Iter 215bw — derive a per-user tour key so different operators on the
 * same shared browser each see the tour exactly once. Falls back to the
 * legacy global key when no user id is decodable (offline / pre-auth).
 */
function userScopedKey(baseKey) {
  if (typeof window === 'undefined') return baseKey;
  try {
    const token = localStorage.getItem('token') || localStorage.getItem('crm_token');
    if (!token) return baseKey;
    const payload = JSON.parse(atob(token.split('.')[1]));
    const id = payload?.user_id || payload?.sub;
    if (id) return `${baseKey}:${id}`;
  } catch { /* malformed token — fall back */ }
  return baseKey;
}

// Custom tooltip style overrides (CSS-level only, colors go as Joyride props)
const tourStyles = {
  tooltip: {
    borderRadius: '16px',
    padding: '20px',
    fontSize: '14px',
    boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
    border: '1px solid rgba(255,255,255,0.08)',
  },
  tooltipTitle: {
    fontSize: '16px',
    fontWeight: 700,
    marginBottom: '6px',
  },
  tooltipContent: {
    fontSize: '13px',
    lineHeight: 1.6,
    padding: '4px 0',
  },
  buttonNext: {
    borderRadius: '10px',
    fontSize: '13px',
    fontWeight: 600,
    padding: '8px 20px',
    border: 'none',
  },
  buttonBack: {
    fontSize: '13px',
    marginRight: '8px',
  },
  buttonSkip: {
    fontSize: '12px',
  },
  spotlight: {
    borderRadius: '12px',
  },
};

// ============ GymAxis AI Tour Steps (variant="gymaxis" only — NOT shown to Pulse users) ============
const gymAxisSteps = [
  {
    target: '[data-testid="dashboard-header"]',
    title: 'Welcome to GymAxis AI',
    content: 'Your central command centre for gym equipment management. This dashboard gives you a real-time overview of every asset across your facility.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-overview"]',
    title: 'Dashboard Overview',
    content: 'Your at-a-glance health score, open faults, recent audits, and maintenance tasks. Start here every day to see what needs attention.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-equipment"]',
    title: 'Equipment Register',
    content: 'Your complete equipment database \u2014 serial numbers, warranty dates, service history, and lifecycle alerts. Import via CSV or add manually.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-issues"]',
    title: 'Fault Management',
    content: 'Log equipment faults with AI-powered triage. Get instant repair steps, part numbers, and supplier routing \u2014 all from your uploaded manuals.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-maintenance"]',
    title: 'Check Sheets',
    content: 'Daily, weekly, and monthly maintenance checklists. Track compliance, assign tasks, and generate reports for auditors.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-diagnosis"]',
    title: 'AI Fault Diagnosis',
    content: 'Chat with AI about equipment problems. It draws from your uploaded manuals, past fixes, and manufacturer data to give expert-level guidance.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-documents"]',
    title: 'Document Library',
    content: 'Upload manuals, certificates, and service guides. AI indexes everything so you can search across all documents with natural language questions.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="tab-reports"]',
    title: 'Reports & CAPEX',
    content: 'Generate audit reports, CAPEX recommendations, and equipment lifecycle intelligence. Export PDF reports for management and board meetings.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="doc-qa-fab"]',
    title: 'Ask Your Documents',
    content: 'This floating button lets you ask questions to your uploaded manuals from anywhere. Try "What torque spec for a treadmill belt?" \u2014 AI finds the answer instantly.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'left',
  },
  {
    target: '[data-testid="nav-user-menu-btn"]',
    title: 'Account & Settings',
    content: 'Access your profile, organisation settings, team management, supplier config, and white-label branding from here. You\'re all set \u2014 happy maintaining!',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom-end',
  },
];

// ============ Pulse Fitness Pro Tour Steps ============
const pulseProSteps = [
  {
    target: '[data-testid="pulse-dashboard-header"]',
    title: 'Welcome to Pulse Fitness Pro',
    content: 'Your self-service maintenance portal. Everything you need to keep your gym equipment running \u2014 with AI-powered diagnostics at your fingertips.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-overview"]',
    title: 'Dashboard Overview',
    content: 'Your daily snapshot \u2014 health score, open faults, recent activity, and maintenance tasks. Start here to see what needs attention today.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-equipment"]',
    title: 'Equipment Register',
    content: 'All your gym equipment in one place \u2014 serial numbers, warranty dates, and service history. Track every asset across your facility.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-faults"]',
    title: 'Fault Logging',
    content: 'Report equipment problems with photo evidence. AI instantly triages the fault, suggests repair steps, and routes to the right supplier.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-check-sheets"]',
    title: 'Check Sheets',
    content: 'Daily and weekly maintenance checklists. Complete checks, track compliance, and keep a full audit trail for inspections.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-documents"]',
    title: 'Documents',
    content: 'Upload and access equipment manuals, certificates, and guides. Ask AI questions about any document \u2014 it finds the answer for you.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-reports"]',
    title: 'Reports',
    content: 'Generate comprehensive audit reports and track your maintenance performance over time.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="doc-qa-fab"]',
    title: 'Ask Your Documents',
    content: 'This floating button lets you ask questions about your equipment manuals from any tab. Try asking about maintenance schedules or spare parts.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'left',
  },
];

// ============ Tour Component ============
const ProductTour = forwardRef(({ variant = 'gymaxis' }, ref) => {
  const [run, setRun] = useState(false);
  const tourKey = userScopedKey(variant === 'pulse' ? TOUR_KEY_PULSE : TOUR_KEY_GYMAXIS);
  const steps = variant === 'pulse' ? pulseProSteps : gymAxisSteps;

  useEffect(() => {
    // Iter 215bw — also honour the legacy non-scoped key, so an operator
    // who completed the tour before this change won't be re-prompted.
    const legacyKey = variant === 'pulse' ? TOUR_KEY_PULSE : TOUR_KEY_GYMAXIS;
    const completed = localStorage.getItem(tourKey) || localStorage.getItem(legacyKey);
    if (completed) return;

    // Iter 216o-6 — Wait for the WelcomeHero onboarding card to be
    // dismissed before launching the product tour. Showing both at once
    // overwhelms first-time users (the tour spotlight overlays the
    // setup card so they can't see "Start setup"). We poll for the
    // card's presence: as soon as it's gone (dismissed via X, or never
    // rendered because onboarding is already complete), the tour kicks
    // off. Cap the wait at 30s so a stale localStorage state can't
    // block the tour forever.
    let cancelled = false;
    let started = false;
    const launchTour = () => {
      if (cancelled || started) return;
      started = true;
      setRun(true);
    };
    const tick = () => {
      if (cancelled || started) return;
      const card = document.querySelector('[data-testid="welcome-hero-card"]');
      if (!card) {
        // No welcome hero in the DOM — safe to launch. We give a short
        // grace so the dashboard tabs (which the tour targets) have
        // mounted, and mid-render flickers don't restart the tour.
        setTimeout(launchTour, 800);
      }
    };
    tick();
    const intervalId = setInterval(tick, 600);
    const safetyId  = setTimeout(launchTour, 30_000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
      clearTimeout(safetyId);
    };
  }, [tourKey, variant]);

  const handleEvent = useCallback((event) => {
    const { type, status } = event;
    if (type === 'tour:end' || status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      localStorage.setItem(tourKey, 'true');
      setRun(false);
    }
  }, [tourKey]);

  const resetTour = useCallback(() => {
    localStorage.removeItem(tourKey);
    setRun(false);
    setTimeout(() => setRun(true), 300);
  }, [tourKey]);

  useImperativeHandle(ref, () => ({
    resetTour,
  }), [resetTour]);

  return (
    <Joyride
      steps={steps}
      run={run}
      continuous
      scrollToFirstStep
      disableScrollParentFix
      disableScrolling
      options={{
        arrowColor: 'var(--color-neutral-950-alt)',
        backgroundColor: 'var(--color-neutral-950-alt)',
        primaryColor: 'var(--color-brand-blue)',
        textColor: 'var(--color-neutral-50)',
        overlayColor: 'rgba(0, 0, 0, 0.6)',
        zIndex: 10000,
        showProgress: true,
        buttons: ['back', 'close', 'primary', 'skip'],
      }}
      styles={tourStyles}
      onEvent={handleEvent}
      locale={{
        back: 'Back',
        close: 'Close',
        last: 'Finish',
        next: 'Next',
        skip: 'Skip tour',
      }}
      floaterProps={{
        disableAnimation: true,
      }}
    />
  );
});

ProductTour.displayName = 'ProductTour';

export const resetGymAxisTour = () => {
  localStorage.removeItem(TOUR_KEY_GYMAXIS);
};

export const resetPulseTour = () => {
  localStorage.removeItem(TOUR_KEY_PULSE);
};

export default ProductTour;
