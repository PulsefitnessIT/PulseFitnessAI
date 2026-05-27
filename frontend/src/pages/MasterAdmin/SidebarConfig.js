import {
  LayoutDashboard, CreditCard, Headphones, Mail, TrendingUp,
  PoundSterling, ArrowLeftRight, BarChart3, Timer, ShieldCheck, Sparkles,
  Banknote, Rocket, ListChecks, Users, Palette, Tag, Receipt, ShieldAlert,
  Wallet, Megaphone, Lock, FolderArchive, AlertCircle,
  Database, Image as ImageIcon, Activity, ScrollText, RotateCcw, RefreshCcw,
  Plug, MapPin, Building, Settings, BadgeCheck, Inbox, FileText, Globe,
  ShieldOff,
} from 'lucide-react';

/**
 * Master Admin sidebar nav model.
 *
 * Iter 216h17 — Phase 1 of the Master Admin redesign blueprint
 * (see /app/design_guidelines.json). Collapsed to **8 top-level
 * entries** with sub-tabs, replacing the previous 14 top-level + 23
 * sub-tabs spaghetti. The blueprint groups by user mental model
 * (People · Organisations · Sites · Finance · …) rather than by
 * engineering boundary.
 *
 * Section IDs are preserved verbatim from the legacy IA so the
 * MasterAdminPage `renderSection` switch and any deep-links keep
 * working unchanged. The renaming applies to LABELS only — the URL
 * `?section=...` keys remain compatible.
 *
 * Future phases will:
 *   P2 — wire the BrandContext into every sub-tab's data queries.
 *   P3 — collapse 4 People panels into one Directory page.
 *   P4 — collapse 3 Org panels into one Organisations page.
 *   P5 — collapse 5 Integration surfaces into one Integrations hub.
 */

export const SIDEBAR_ITEMS = [
  // 1. Overview — landing page + system health
  {
    id: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'main',
    subTabs: [
      { id: 'overview',  label: 'Dashboard',     icon: LayoutDashboard },
      { id: 'trust',     label: 'System Health', icon: ShieldCheck },
      { id: 'tasks',     label: 'Setup checklist', icon: ListChecks },
    ],
  },
  // 2. People — SSoT for Pulse Admins, Owners, Staff, CRM contacts
  {
    id: 'roles', label: 'People', icon: Users, group: 'main',
    subTabs: [
      { id: 'roles',          label: 'Directory',         icon: Users },
      { id: 'staff-onboarding', label: 'Onboard staff',   icon: Rocket },
      { id: 'locked-staff',   label: 'Site-locked users', icon: Lock },
    ],
  },
  // 3. Organisations — SSoT for customers / orgs / multi-site groups.
  //    Iter 216h20 — restored "Customer onboarding" here. It was
  //    misfiled under People → "Staff onboarding" in iter 216h17 even
  //    though the hub creates *organisations* (Onboard Site / Head
  //    Office / Packets / Bulk Imports). Operator feedback:
  //    "we've lost Organisation Onboarding which was working perfectly".
  //    Iter 216h23 — added "All sites" cross-org sub-tab. Sites STILL
  //    belong to an Organisation (no SSoT duplication), but HQ ops now
  //    has a flat power-view across every org.
  {
    id: 'organizations', label: 'Organisations', icon: Building, group: 'main',
    subTabs: [
      { id: 'organizations',     label: 'List',                  icon: Building },
      { id: 'all-sites',         label: 'All sites',             icon: MapPin },
      { id: 'onboarding',        label: 'Customer onboarding',   icon: Rocket },
      { id: 'estate-rollup',     label: 'Module subscriptions',  icon: BarChart3 },
      { id: 'activation-funnel', label: 'Customer activation',   icon: TrendingUp },
    ],
  },
  // 4. Catalogue & Library — equipment master data (manufacturer
  //    catalogue, spec sheets, equipment images), marketing image
  //    library, social media library.
  //    Iter 216h23 — was misleadingly labelled "Sites". A "Site" is a
  //    physical location and lives inside an Organisation (drawer
  //    Sites tab + Organisations → All sites). The contents here are
  //    NOT sites — they're cross-org master data + brand assets.
  {
    id: 'catalogue', label: 'Catalogue & Library', icon: ImageIcon, group: 'main',
    subTabs: [
      { id: 'catalogue',         label: 'Equipment catalogue',  icon: ImageIcon },
      { id: 'custom-properties', label: 'Custom properties',    icon: ListChecks },
    ],
  },
  // 5. Finance — pricing, billing, payments, Stripe, CAPEX, refunds
  {
    id: 'finance', label: 'Finance', icon: Wallet, group: 'main',
    subTabs: [
      { id: 'pricing',       label: 'Pricing',        icon: Tag },
      { id: 'org-billing',   label: 'Org billing',    icon: Receipt },
      { id: 'collections',   label: 'Collections',    icon: AlertCircle },
      { id: 'payments',      label: 'Payments',       icon: CreditCard },
      { id: 'stripe-connect',label: 'Stripe',         icon: Banknote },
      { id: 'financial-ops', label: 'Financial ops',  icon: PoundSterling, gymaxisOnly: true },
      { id: 'refunds',       label: 'Refunds',        icon: RotateCcw, gymaxisOnly: true },
      { id: 'capex-config',  label: 'CAPEX',          icon: TrendingUp },
    ],
  },
  // 6. Growth — trials, marketing, sales insights, comms
  {
    id: 'growth', label: 'Growth', icon: Megaphone, group: 'main',
    subTabs: [
      // Iter 220ag — Growth Hub (aggregation of trials, SEO, outbound,
      // CRM pipeline + sales insights — GymAxis self-promotion lens).
      { id: 'marketing-studio', label: 'Growth Hub',   icon: Rocket },
      // Iter 220ad — SEO Autopilot (keyword research → article → publish)
      { id: 'seo-autopilot',    label: 'SEO Autopilot',      icon: Sparkles },
      { id: 'communications',  label: 'Communications inbox', icon: Inbox },
      { id: 'canned-replies',  label: 'Canned replies',   icon: FileText },
      { id: 'emails',          label: 'Outbound emails',  icon: Mail },
      { id: 'trials',          label: 'Trials',           icon: Timer },
      { id: 'sales-insights',  label: 'Sales insights',   icon: Sparkles },
      { id: 'pulse-sales',     label: 'Pulse Sales (CAPEX)', icon: TrendingUp },
    ],
  },
  // Iter 220ad — Analytics promoted from a Growth sub-tab to a top-level
  // entry. Operator feedback: "Global Analytics doesn't belong inside
  // Growth — it spans Finance, Service Ops, CRM, Marketing, Memberships
  // and Engineers. Surface it on the main rail."
  {
    id: 'analytics-section', label: 'Analytics', icon: BarChart3, group: 'main',
    subTabs: [
      { id: 'analytics', label: 'Global analytics', icon: BarChart3 },
    ],
  },
  // 7. Partner Engineers — promoted to top-level (iter 219).
  //    Was buried as a Growth sub-tab even though it's a primary revenue
  //    stream (£30/mo seat fees + 50%-first-month signup rewards +
  //    recurring referral commission). Operator feedback:
  //    "Move Partner Engineers into the main sidebar — it's too hidden
  //    away when this could be a main source of revenue."
  {
    id: 'partners', label: 'Partner Engineers', icon: BadgeCheck, group: 'main',
    subTabs: [
      { id: 'partners', label: 'Applications & partners', icon: BadgeCheck },
    ],
  },
  // 7. Integrations — Hub + sub-pages (Iter 216h22 — Hub is now default).
  {
    id: 'integrations-hub', label: 'Integrations', icon: Plug, group: 'main',
    subTabs: [
      { id: 'integrations-hub',    label: 'Hub',           icon: Plug },
      { id: 'integration-health',  label: 'Health',        icon: Activity },
      { id: 'orbit4',              label: 'Orbit 4',       icon: ArrowLeftRight },
      { id: 'sicon-integration',   label: 'Sicon Service', icon: ArrowLeftRight },
      { id: 'stripe-connect',      label: 'Stripe Connect', icon: Banknote },
    ],
  },
  // 8. Settings & Compliance — audit log, login events, database, backfills
  {
    id: 'settings-compliance', label: 'Settings & Compliance', icon: Settings, group: 'main',
    subTabs: [
      { id: 'audit-log',          label: 'Audit log',          icon: ScrollText },
      { id: 'audit-logs',         label: 'Compliance trail',   icon: ScrollText },
      { id: 'login-events',       label: 'Login events',       icon: ShieldAlert },
      { id: 'client-errors',      label: 'Client crashes',     icon: ShieldAlert },
      { id: 'documents',          label: 'Documents',          icon: FolderArchive },
      // Iter 216h59 — relocated from Overview. Archive is a data-
      // lifecycle / compliance concern (soft-deleted orgs, restore
      // tooling), so it sits naturally alongside the audit log and
      // database tooling rather than the operator dashboard.
      { id: 'archive',            label: 'Archive',            icon: FolderArchive },
      // Iter 220ao — GDPR Art. 17 Data Subject Erasure Requests
      { id: 'gdpr-erasure',       label: 'Data Subject Erasure', icon: ShieldOff },
      { id: 'ask-support',        label: 'Ask Support Desk',   icon: Sparkles },
      { id: 'support',            label: 'Support tools',      icon: Headphones },
      { id: 'db-viewer',          label: 'Database viewer',    icon: Database },
      { id: 'backfills',          label: 'Maintenance jobs',   icon: RefreshCcw },
      { id: 'design-system',      label: 'Design system',      icon: Palette, gymaxisOnly: true },
      { id: 'theme-settings',     label: 'Theme settings',     icon: Palette },
      { id: 'custom-domains',     label: 'Custom domains',     icon: Globe },
    ],
  },
];

/** Reverse lookup: section id → parent group id. Used to highlight
 *  the right sidebar entry when an in-page sub-tab is active. */
export const SECTION_TO_GROUP = (() => {
  const map = {};
  for (const item of SIDEBAR_ITEMS) {
    if (item.subTabs) {
      for (const sub of item.subTabs) map[sub.id] = item.id;
    }
  }
  return map;
})();

/** Map: parent group id → list of sub-tabs (used by MasterAdminPage
 *  to render the sub-tab bar). */
export const GROUP_SUBTABS = (() => {
  const m = {};
  for (const item of SIDEBAR_ITEMS) {
    if (item.subTabs) m[item.id] = item.subTabs;
  }
  return m;
})();

/** Iter 216h17 — Legacy section IDs that no longer have a sidebar
 *  entry of their own (because they were merged into a group's
 *  sub-tabs). When a deep-link uses one of these IDs, the page still
 *  renders correctly via the existing switch — they just don't show
 *  up as a standalone nav. Keeping this map for documentation only. */
export const LEGACY_SECTION_REDIRECTS = {
  // No data routing changes in P1 — the renderSection switch
  // resolves each id directly. This map is here to make P3-P5
  // consolidations explicit and reviewable.
  'audit-log':          'settings-compliance',
  'login-events':       'settings-compliance',
  'client-errors':      'settings-compliance',
  'documents':          'settings-compliance',
  'archive':            'settings-compliance',
  'ask-support':        'settings-compliance',
  'support':            'settings-compliance',
  'db-viewer':          'settings-compliance',
  'backfills':          'settings-compliance',
  'design-system':      'settings-compliance',
  'theme-settings':     'settings-compliance',
  'custom-domains':     'settings-compliance',
  'locked-staff':       'roles',
  'staff-onboarding':   'roles',
  'onboarding':         'organizations',
  'estate-rollup':      'organizations',
  'activation-funnel':  'organizations',
  'catalogue':          'catalogue',
  'custom-properties':  'catalogue',
  'orbit4':             'integrations-hub',
  'integration-health': 'integrations-hub',
  'sicon-integration':  'integrations-hub',
  'stripe-connect':     'integrations-hub',
  'pricing':            'finance',
  'org-billing':        'finance',
  'collections':        'finance',
  'payments':           'finance',
  'financial-ops':      'finance',
  'refunds':            'finance',
  'capex-config':       'finance',
  'trials':             'growth',
  'sales-insights':     'growth',
  'pulse-sales':        'growth',
  'analytics':          'analytics-section',
  'marketing-studio':   'growth',
  'marketing-suite':    'growth',
  'seo-autopilot':      'growth',
  'communications':     'growth',
  'canned-replies':     'growth',
  'emails':             'growth',
  'trust':              'overview',
  'tasks':              'overview',
};

export const sectionTitles = {
  overview: 'Dashboard Overview',
  tasks: 'Setup checklist',                     // Iter 216h17 — terminology cleanup
  pricing: 'Pricing',
  'org-billing': 'Org billing',
  'estate-rollup': 'Module subscriptions',      // Iter 216h17 — clearer than "Estate Rollup"
  collections: 'Collections',
  'login-events': 'Login events',
  'client-errors': 'Client crashes',
  'audit-log': 'Audit log',
  'locked-staff': 'Site-locked users',          // Iter 216h17 — terminology cleanup
  trust: 'System health',                       // Iter 216h17 — was "Trust & Reliability Engine"
  archive: 'Archive',                           // Iter 216h53 — relocated from Service Desk
  'ask-support': 'Ask Support Desk',
  payments: 'Payments & subscriptions',
  onboarding: 'Customer onboarding',             // Iter 216h20 — restored from People/"Staff onboarding". The hub creates customer organisations, not staff.
  trials: 'Trials',
  'activation-funnel': 'Customer activation',   // Iter 216h17 — terminology cleanup
  'sales-insights': 'Sales insights',
  communications: 'Communications inbox',
  'canned-replies': 'Canned replies',
  analytics: 'Global analytics',
  'marketing-suite': 'Marketing suite',
  'marketing-studio': 'GymAxis Growth Hub',
  orbit4: 'Orbit 4',
  'sicon-integration': 'Sicon Service',
  'integrations-hub': 'Integrations hub',
  roles: 'People directory',                    // Iter 216h17 — was "Roles & Access"
  'staff-onboarding': 'Onboard staff',
  'stripe-connect': 'Stripe Connect',
  support: 'Support tools',
  emails: 'Outbound emails',
  documents: 'Documents library',
  'capex-config': 'CAPEX configuration',
  'financial-ops': 'Financial operations',
  'refunds': 'Refunds',
  'design-system': 'Design system',
  'theme-settings': 'Theme settings',
  'custom-domains': 'Custom domains',
  'db-viewer': 'Database viewer',
  catalogue: 'Equipment catalogue & spec sheets',
  'all-sites': 'All sites',
  'integration-health': 'Integration health',
  'custom-properties': 'Custom properties',
  organizations: 'Organisations',
  backfills: 'Maintenance jobs',                // Iter 216h17 — terminology cleanup
  partners: 'Partner Engineers',                // Iter 219 — promoted to top-level
  // Group-level titles when no sub-tab is yet selected
  finance: 'Finance',
  security: 'Security',
  growth: 'Growth',
  'analytics-section': 'Analytics',
  'support-hub': 'Support',
  'settings-compliance': 'Settings & Compliance',
};

export const sectionDescriptions = {
  overview: 'High-level platform metrics — Operations Portal & CRM',
  tasks: 'Auto-ticks itself as integrations + bulk imports complete',
  pricing: 'Module + bundle prices for both brands. Edits flow live to public homepages.',
  'org-billing': 'Per-org subscriptions, manual invoices, BACS payments, bill-to-date balance.',
  'estate-rollup': 'Module entitlements across every org — license audit, trial expiry, orphan accounts.',
  collections: 'Aging buckets, top overdue accounts and dunning telemetry — your AR control room.',
  'login-events': 'Security timeline — every login, MFA challenge, failed attempt and brute-force signal.',
  'client-errors': 'Front-end render crashes captured by ModalErrorBoundary — see the stack & component-stack to debug what broke for a user.',
  'audit-log': 'Unified timeline of every platform-wide security event — logins, wallet activity, Auto-Bill charges, retry-ladder escalations. CSV export for SOC 2 / pentest evidence packets.',
  'locked-staff': 'Read-only audit view of every user with a per-site restriction set. Joins org name + site names + last-changed timestamp.',
  trust: 'Platform health, security events, and integration status — detect before customers do',
  'ask-support': 'Human-escalated AI support cases, CSAT trends, and deflection analytics',
  payments: 'Revenue tracking and subscription management',
  analytics: 'Cross-gym analytics and trends',
  'marketing-suite': 'Marketing Suite — plans, subscriptions, platform-wide KPIs',
  'marketing-studio': 'GymAxis Growth Hub — funnel view across trials, SEO, outbound, CRM pipeline and sales insights.',
  onboarding: 'Onboard a new customer organisation, send shareable packets, or bulk-load CSV rosters',
  trials: 'Track active trials, extend deadlines, convert to paid',
  'activation-funnel': 'Conversion funnel — what % of orgs hit each milestone, where they drop off.',
  'sales-insights': 'Top sales objections + AI-spotted themes from the public marketing chat.',
  'pulse-sales': 'Internal Pulse Fitness sales pipeline auto-generated from customer CAPEX state. Tenant-restricted — customers never see this view.',
  communications: 'Every sales enquiry from the public marketing site — triage, reply via Resend, attach internal notes.',
  'canned-replies': 'Manage the global library of reusable reply templates surfaced in the Communications inbox composer.',
  roles: 'Pulse Admins · Customer Owners · Customer Staff · CRM contacts — all in one directory.',
  'staff-onboarding': '5-step wizard to invite a new platform admin or org-scoped staff member. Generates a 72h invite link — the user sets their own password.',
  'stripe-connect': 'Connect Pulse Fitness to Stripe via OAuth, tune the platform fee, preview profit per customer',
  support: 'Tools for customer support',
  emails: 'Outbound email audit trail',
  documents: 'Auto-captured PDFs (invoices, audits) + manual uploads (DPAs, contracts, NDAs).',
  'capex-config': 'CAPEX scoring thresholds and defaults',
  'financial-ops': 'Revenue reserves, cost centres, and auto-top-up',
  'refunds': 'Issue and track Stripe refunds',
  'design-system': 'Living reference gallery — every button, tab pill, and input in one place',
  'theme-settings': 'GymAxis vs Pulse Fitness design-token isolation audit + per-tenant brand overrides.',
  'custom-domains': 'Point a tenant\'s own domain (e.g. join.acmegym.com) at a specific member-facing surface — sign-up, branded app, brag page or public timetable.',
  'db-viewer': 'Read-only Mongo collection browser — search, paginate, and export.',
  catalogue: 'Manufacturer catalogue, spec sheets, equipment image library and brand assets — all the master data reused across every org and every site.',
  'all-sites': 'Every physical site across every organisation. Filter by brand, org, or site type. Click any row to drill into the parent organisation&apos;s Sites drawer.',
  'integration-health': 'Live status of every third-party service.',
  'integrations-hub': 'All third-party connections in one screen — Stripe Connect, Sicon, Orbit 4 and Sage 200. Click any card to manage.',
  organizations: 'Customer organisations — Pulse Fitness, GymAxis. Click any row for a full drawer.',
  backfills: 'One-off maintenance jobs — preview, then commit. Powers data clean-up.',
  partners: 'Approve incoming partner engineer applications, manage active partners, and queue commission payouts — a core revenue stream.',
  finance: 'Pricing, billing, payments, Stripe and CAPEX in one place.',
  security: 'Login events plus the platform-health & trust dashboard.',
  growth: 'Marketing Suite plus active-trial conversion tracking.',
  'support-hub': 'Help desk escalations, ad-hoc support tools, and outbound email audit.',
  'settings-compliance': 'Audit logs, login events, database, maintenance jobs and design system — every compliance + admin tool in one place.',
};

/** Pill-style sub-tab bar used across the Overview and Analytics sections. */
export const SubTabBar = ({ tabs, active, onChange }) => (
  <div className="subtab-bar mb-6 flex-wrap" data-testid="sub-tab-bar">
    {tabs.map(tab => (
      <button
        key={tab.id}
        type="button"
        onClick={() => onChange(tab.id)}
        className={`subtab-pill ${active === tab.id ? 'is-active' : ''}`}
        data-testid={`sub-tab-${tab.id}`}
      >
        {tab.label}
      </button>
    ))}
  </div>
);
