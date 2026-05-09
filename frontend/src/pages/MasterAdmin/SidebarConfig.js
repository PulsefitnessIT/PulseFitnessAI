import React from 'react';
import {
  LayoutDashboard, Building2, CreditCard, Headphones, Mail, TrendingUp,
  PoundSterling, ArrowLeftRight, BarChart3, Timer, ShieldCheck, Sparkles,
  Banknote, Rocket, ListChecks, Users, Palette, Tag, Receipt, ShieldAlert,
  Wallet, Megaphone, LifeBuoy, Lock, FolderArchive, AlertCircle, AlertOctagon, Database, Image as ImageIcon, Activity, ScrollText, RotateCcw,
} from 'lucide-react';

/**
 * Master Admin sidebar nav model.
 *
 * Iter 209: collapsed from 21 entries to ~11 to stop the sidebar from
 * dwarfing the content area at 1280px. Related concerns are bundled
 * under a single sidebar item and switched via in-page sub-tabs:
 *
 *   • "Finance"  → Pricing, Org Billing, Payments, Stripe, Financial Ops, CAPEX
 *   • "Security" → Login Events, Trust & Reliability
 *   • "Growth"   → Marketing Suite, Trial Management
 *   • "Support"  → Ask Support Desk, Support Tools, Emails
 *
 * The legacy section ids ("payments", "trust", etc.) are still the
 * source of truth for ``renderSection``; the consolidation purely
 * changes which entries are surfaced in the sidebar and adds the
 * `subTabs` array that drives the in-page bar.
 */

export const SIDEBAR_ITEMS = [
  // — Top-level platform —
  { id: 'overview',         label: 'Overview',         icon: LayoutDashboard, group: 'main' },
  { id: 'tasks',            label: 'Tasks',            icon: ListChecks,      group: 'main' },
  { id: 'onboarding',       label: 'Onboarding',       icon: Building2,       group: 'main' },
  { id: 'analytics',        label: 'Global Analytics', icon: BarChart3,       group: 'main' },
  // 'settings' removed (iter 215eg) — those are tenant-level org settings
  // (Team & Org, Suppliers, White Label, Fault Templates, Sicon, Onboarding)
  // and don't belong in the Master Admin platform sidebar. Deep-links to
  // ?section=settings now fall through to Overview via the default branch.
  // — Consolidated groups —
  {
    id: 'finance', label: 'Finance', icon: Wallet, group: 'main',
    subTabs: [
      { id: 'pricing',       label: 'Pricing',       icon: Tag },
      { id: 'org-billing',   label: 'Org Billing',   icon: Receipt },
      { id: 'estate-rollup', label: 'Estate Rollup', icon: BarChart3 },
      { id: 'collections',   label: 'Collections',   icon: AlertCircle },
      { id: 'payments',      label: 'Payments',      icon: CreditCard },
      { id: 'stripe-connect',label: 'Stripe',        icon: Banknote },
      { id: 'financial-ops', label: 'Fin. Ops',      icon: PoundSterling, gymaxisOnly: true },
      { id: 'refunds',       label: 'Refunds',       icon: RotateCcw, gymaxisOnly: true },
      { id: 'capex-config',  label: 'CAPEX',         icon: TrendingUp },
    ],
  },
  {
    id: 'security', label: 'Security', icon: Lock, group: 'main',
    subTabs: [
      { id: 'trust',        label: 'Trust & Reliability', icon: ShieldCheck },
      { id: 'audit-log',    label: 'Audit log',        icon: ScrollText },
      { id: 'login-events', label: 'Login events',     icon: ShieldAlert },
    ],
  },
  {
    id: 'growth', label: 'Growth', icon: Megaphone, group: 'main',
    subTabs: [
      { id: 'trials',             label: 'Trial Management',   icon: Timer },
      { id: 'activation-funnel',  label: 'Activation funnel',  icon: TrendingUp },
      { id: 'sales-insights',     label: 'Sales Insights',     icon: Sparkles },
    ],
  },
  {
    id: 'support-hub', label: 'Support', icon: LifeBuoy, group: 'main',
    subTabs: [
      { id: 'ask-support', label: 'Ask Support Desk', icon: Sparkles },
      { id: 'support',     label: 'Support Tools',    icon: Headphones },
      { id: 'documents',   label: 'Documents',        icon: FolderArchive },
      { id: 'emails',      label: 'Emails',           icon: Mail },
    ],
  },
  // — Integrations —
  { id: 'orbit4',            label: 'Orbit 4',       icon: ArrowLeftRight, group: 'integrations' },
  { id: 'sicon-integration', label: 'Sicon Service', icon: ArrowLeftRight, group: 'integrations' },
  // — Tools (low-frequency) —
  { id: 'roles',         label: 'Roles',         icon: Users,   group: 'tools', gymaxisOnly: true },
  { id: 'design-system', label: 'Design System', icon: Palette, group: 'tools', gymaxisOnly: true },
  { id: 'db-viewer',     label: 'Database',      icon: Database, group: 'tools' },
  { id: 'catalogue',     label: 'Image Catalogue', icon: ImageIcon, group: 'tools' },
  { id: 'custom-properties', label: 'Custom Properties', icon: ListChecks, group: 'tools' },
];

/** Reverse lookup: section id → parent group id. Used to highlight the right sidebar entry when an in-page sub-tab is active. */
export const SECTION_TO_GROUP = (() => {
  const map = {};
  for (const item of SIDEBAR_ITEMS) {
    if (item.subTabs) {
      for (const sub of item.subTabs) map[sub.id] = item.id;
    }
  }
  return map;
})();

/** Map: parent group id → list of sub-tabs (used by MasterAdminPage to render the sub-tab bar). */
export const GROUP_SUBTABS = (() => {
  const m = {};
  for (const item of SIDEBAR_ITEMS) {
    if (item.subTabs) m[item.id] = item.subTabs;
  }
  return m;
})();

export const sectionTitles = {
  overview: 'Dashboard Overview',
  tasks: 'Tasks',
  pricing: 'Pricing',
  'org-billing': 'Org Billing',
  'estate-rollup': 'Estate Module Rollup',
  collections: 'Collections',
  'login-events': 'Login Events',
  'audit-log': 'Audit Log',
  trust: 'Trust & Reliability Engine',
  'ask-support': 'Ask Support Desk (Pulse Fitness + GymAxis)',
  payments: 'Payments & Subscriptions',
  onboarding: 'Onboarding',
  trials: 'Trial Management',
  'activation-funnel': 'Activation Funnel',
  'sales-insights': 'Sales Insights — prospect chat themes',
  analytics: 'Global Analytics',
  'marketing-suite': 'Marketing Suite',
  orbit4: 'Orbit 4 Integration',
  'sicon-integration': 'Sicon Service Integration',
  roles: 'Roles & Access',
  'stripe-connect': 'Stripe Connection',
  support: 'Support Tools',
  emails: 'Email Log',
  documents: 'Documents library',
  'capex-config': 'CAPEX Configuration',
  'financial-ops': 'Financial Operations',
  'refunds': 'Refunds',
  'design-system': 'GymAxis Design System',
  'db-viewer': 'Database',
  catalogue: 'Equipment Image Catalogue',
  'integration-health': 'Integration Health',
  // Group-level titles when no sub-tab is yet selected
  finance: 'Finance',
  security: 'Security',
  growth: 'Growth',
  'support-hub': 'Support',
};

export const sectionDescriptions = {
  overview: 'High-level platform metrics — Operations Portal & CRM',
  tasks: 'Setup checklist — auto-ticks itself as integrations + bulk imports complete',
  pricing: 'Module + bundle prices for both brands. Edits flow live to public homepages.',
  'org-billing': 'Per-org subscriptions, manual invoices, BACS payments, bill-to-date balance.',
  'estate-rollup': 'Module entitlements across every org — license audit, trial expiry, orphan accounts.',
  collections: 'Aging buckets, top overdue accounts and dunning telemetry — your AR control room.',
  'login-events': 'Security timeline — every login, MFA challenge, failed attempt and brute-force signal.',
  'audit-log': 'Unified timeline of every platform-wide security event — logins, wallet activity, Auto-Bill charges, retry-ladder escalations. CSV export for SOC 2 / pentest evidence packets.',
  trust: 'Platform health, security events, and integration status — detect before customers do',
  'ask-support': 'Human-escalated AI support cases, CSAT trends, and deflection analytics',
  payments: 'Revenue tracking and subscription management',
  analytics: 'Cross-gym analytics and trends',
  'marketing-suite': 'Marketing Suite — plans, subscriptions, platform-wide KPIs',
  onboarding: 'Onboard a new site, send shareable packets, or bulk-load CSV rosters',
  trials: 'Track active trials, extend deadlines, convert to paid',
  'activation-funnel': 'Conversion funnel — what % of orgs hit each milestone, where they drop off.',
  'sales-insights': 'Top sales objections + AI-spotted themes from the public marketing chat — turn prospect questions into homepage / pricing-page improvements.',
  roles: 'Service Desk Members + Pulse Master Admins — provision delegated platform staff',
  'stripe-connect': 'Connect Pulse Fitness to Stripe via OAuth, tune the platform fee, preview profit per customer',
  support: 'Tools for customer support',
  emails: 'Outbound email audit trail',
  documents: 'Auto-captured PDFs (invoices, audits) + manual uploads (DPAs, contracts, NDAs).',
  'capex-config': 'CAPEX scoring thresholds and defaults',
  'financial-ops': 'Revenue reserves, cost centres, and auto-top-up',
  'refunds': 'Issue and track Stripe refunds',
  'design-system': 'Living reference gallery — every button, tab pill, and input in one place',
  'db-viewer': 'Read-only Mongo collection browser — search, paginate, and export. Sensitive fields auto-redacted.',
  catalogue: 'Combined surface: cached manufacturer images, uploaded Pulse spec sheets, and per-machine photo overrides — powers the Equipment auto-find feature.',
  'recent-errors': 'Frontend-caught exceptions and API 4xx/5xx errors observed by real operators in the last 24 hours. (Merged into Trust & Reliability · iter 215ai.)',
  'integration-health': 'Live status of every third-party service (DB, Stripe, Resend, Storage, LLM). Master-admin diagnostic dashboard. (Merged into Trust & Reliability · iter 215ai.)',
  finance: 'Pricing, billing, payments, Stripe and CAPEX in one place.',
  security: 'Login events plus the platform-health & trust dashboard.',
  growth: 'Marketing Suite plus active-trial conversion tracking.',
  'support-hub': 'Help desk escalations, ad-hoc support tools, and outbound email audit.',
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
