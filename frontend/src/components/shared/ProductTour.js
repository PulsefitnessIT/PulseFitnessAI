import React, { useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Joyride, STATUS } from 'react-joyride';

const TOUR_KEY_GYMAXIS = 'gymaxis_tour_completed';
const TOUR_KEY_PULSE = 'pulse_tour_completed';
const TOUR_KEY_MEMBERSHIPS = 'memberships_tour_completed';
const TOUR_KEY_STAFFING = 'staffing_tour_completed';
const TOUR_KEY_CRM = 'crm_tour_completed';
const TOUR_KEY_MARKETING = 'marketing_tour_completed';

const VARIANT_KEY_MAP = {
  gymaxis:     TOUR_KEY_GYMAXIS,
  pulse:       TOUR_KEY_PULSE,
  memberships: TOUR_KEY_MEMBERSHIPS,
  staffing:    TOUR_KEY_STAFFING,
  crm:         TOUR_KEY_CRM,
  marketing:   TOUR_KEY_MARKETING,
};

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
    content: 'Your end-to-end gym operating system. Maintenance, memberships, classes, staff rotas, payroll, comms, and AI insights — all in one place. We\'ll show you the highlights in 60 seconds.',
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
    target: '[data-testid="lite-tab-staffing"]',
    title: 'Staffing & Rotas',
    content: 'Smart Rota, Time Clock, Shift Marketplace, HR profiles, AI rota builder, and Sage payroll exports — your full workforce ops in one tab.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-documents"]',
    title: 'Documents & Knowledge',
    content: 'Upload manuals, policies, and SOPs. Ask AI questions about any document \u2014 it finds the answer for you instantly.',
    disableBeacon: true,
    skipBeacon: true,
    placement: 'bottom',
  },
  {
    target: '[data-testid="lite-tab-reports"]',
    title: 'Reports & Insights',
    content: 'Comprehensive operational reports, weekly digest, and performance trends. Export to CSV, Excel, or PDF for finance and audits.',
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

// ============ Memberships Module Tour ============
const membershipsSteps = [
  {
    target: '[data-testid="memberships-app-header"]',
    title: 'Memberships & Bookings',
    content: 'Run your member base, plans, classes, timetable, family accounts, and instructor roster. Stripe-ready out of the box.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="mbr-tab-start"]',
    title: 'Start here',
    content: 'A guided checklist that walks you to your first member, plan, and class — in under 15 minutes.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="mbr-tab-members"]',
    title: 'Members directory',
    content: 'Add members one-by-one or import a CSV. De-dupes on email and links to Stripe automatically.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="mbr-tab-schedule"]',
    title: 'Classes & Timetable',
    content: 'Build your weekly class grid, edit any occurrence in place, take operator-initiated bookings, and run waitlists.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="mbr-tab-analytics"]',
    title: 'Analytics',
    content: 'Three role-shaped lenses — Manager (30d), Regional (60d), Director (90d). Revenue, churn, attendance, and instructor performance.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
];

// ============ Staffing Module Tour ============
const staffingSteps = [
  {
    target: '[data-testid="staffing-header"]',
    title: 'Staffing & Workforce Ops',
    content: 'Replace RotaCloud + Connecteam + a separate payroll tool. Rota, time clock, comms, tasks, HR, AI rota builder, and Sage payroll — all here.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-dashboard"]',
    title: 'Workforce Dashboard',
    content: 'On-shift right now, weekly cost, compliance flags, and AI-spotted patterns at a glance.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-rota"]',
    title: 'Drag-drop Rota',
    content: 'Build the week visually. Copy week-to-week, see live labour cost, and let AI flag overtime and 11-hour-rest breaches before you publish.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-timeclock"]',
    title: 'Time Clock & Attendance',
    content: 'Mobile or kiosk clock-in with GPS / geofence. Late minutes, overtime, and timesheets approved in two clicks.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-comms"]',
    title: 'Internal Comms Hub',
    content: 'Direct messages, channels, threaded announcements. Broadcast to a single shift or the whole team.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-operations"]',
    title: 'Tasks · Forms · Compliance',
    content: 'Shift-linked checklists, custom forms, and a certification expiry tracker that nags before lifeguard renewals lapse.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-hr"]',
    title: 'HR 2.0',
    content: 'Employee profiles, contracts & ID documents, disciplinary records (manager-only), and training history — one screen per staff member.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="staffing-tab-ai-rota"]',
    title: 'AI Rota & Sage Payroll',
    content: 'Claude Sonnet 4.5 builds a fair, compliant rota from your demand template. Plus absence-risk scoring and Sage 50 Payroll CSV exports.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
];

// ============ CRM Module Tour ============
const crmSteps = [
  {
    target: '[data-testid="crm-toolbar-staff-filter"]',
    title: 'CRM workspace',
    content: 'Contacts, companies, pipeline, deals, contracts and tenders. Switch between Leisure and Business modes from the toolbar.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="crm-global-search"]',
    title: 'Global search',
    content: 'Find any contact, company, or deal across the whole CRM in one place. Hit ⌘/Ctrl + K to focus from anywhere.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="quick-create-btn"]',
    title: 'Quick Create',
    content: 'Create contacts, companies, deals, or activities from anywhere — no need to navigate first.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="notifications-btn"]',
    title: 'Notifications',
    content: '@mentions, deal updates, and AI alerts land here. Mark read, jump to source, or snooze.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
];

// ============ Marketing Module Tour ============
const marketingSteps = [
  {
    target: '[data-testid="mkt-tabs-desktop"]',
    title: 'Marketing Suite',
    content: 'Audiences, campaigns, journeys, social, brand kit, and AI Creative Director. Everything that sends a member a message.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
  {
    target: '[data-testid="marketing-tab-start"]',
    title: 'Start here',
    content: 'A guided 5-step Campaign Wizard writes your first campaign — copy, audience, send time — in under 5 minutes.',
    disableBeacon: true, skipBeacon: true, placement: 'bottom',
  },
];

// ============ Tour Component ============
const ProductTour = forwardRef(({ variant = 'gymaxis' }, ref) => {
  const [run, setRun] = useState(false);
  const baseKey = VARIANT_KEY_MAP[variant] || TOUR_KEY_GYMAXIS;
  const tourKey = userScopedKey(baseKey);
  const steps = (() => {
    switch (variant) {
      case 'pulse':       return pulseProSteps;
      case 'memberships': return membershipsSteps;
      case 'staffing':    return staffingSteps;
      case 'crm':         return crmSteps;
      case 'marketing':   return marketingSteps;
      default:            return gymAxisSteps;
    }
  })();

  useEffect(() => {
    // Iter 216h49 — Auto-open disabled platform-wide per Lee's feedback
    // ("the tours need updating as they aren't pointing in the right
    // directions or buttons"). Manual triggers via `resetTour()` (the
    // "Start tour" button in the user menu) still work, so operators
    // who want a refresher can launch it on demand once the steps are
    // updated. Re-enable auto-open by flipping this flag to true.
    const AUTO_OPEN = false;
    if (!AUTO_OPEN) return undefined;
    // Iter 215bw — also honour the legacy non-scoped key, so an operator
    // who completed the tour before this change won't be re-prompted.
    const completed = localStorage.getItem(tourKey) || localStorage.getItem(baseKey);
    if (completed) return undefined;

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
  }, [tourKey, baseKey, variant]);

  const handleEvent = useCallback((event) => {
    const { type, status, action } = event || {};
    // Iter 216aj — persist the "seen" flag the MOMENT the tour ends by
    // ANY path (finish, skip, close-X, Esc, error). Previously CLOSED /
    // ERROR statuses slipped through and the operator got the tour again
    // on the next login. Also mirror into the legacy global key so
    // multi-tab sessions converge.
    const terminated = (
      type === 'tour:end' ||
      status === STATUS.FINISHED ||
      status === STATUS.SKIPPED ||
      status === STATUS.PAUSED ||
      action === 'close' ||
      action === 'skip' ||
      action === 'reset'
    );
    if (terminated) {
      try {
        localStorage.setItem(tourKey, 'true');
        // Also set the non-scoped legacy key so we hit the early-return
        // guard reliably on reload.
        if (baseKey && baseKey !== tourKey) localStorage.setItem(baseKey, 'true');
      } catch { /* quota exceeded / private mode — ignore */ }
      setRun(false);
    }
  }, [tourKey, baseKey]);

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

export const resetMembershipsTour = () => {
  localStorage.removeItem(TOUR_KEY_MEMBERSHIPS);
};

export const resetStaffingTour = () => {
  localStorage.removeItem(TOUR_KEY_STAFFING);
};

export const resetCrmTour = () => {
  localStorage.removeItem(TOUR_KEY_CRM);
};

export const resetMarketingTour = () => {
  localStorage.removeItem(TOUR_KEY_MARKETING);
};

/**
 * Reset every per-module tour for the current user. Useful as a single
 * "Replay all tours" button under Settings → Help.
 */
export const resetAllModuleTours = () => {
  Object.values(VARIANT_KEY_MAP).forEach((k) => localStorage.removeItem(k));
};

export default ProductTour;
