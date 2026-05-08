import {
  Wrench, AlertTriangle, ClipboardList, QrCode, ShieldCheck, FileBarChart,
  ClipboardCheck, Users, Megaphone, BarChart3, Calendar,
} from 'lucide-react';

export default {
  id: 'service',
  name: 'Operations',
  color: '#06B6D4',
  icon: Wrench,

  heroLine1: 'Run a safer,',
  heroLine2: 'smoother gym floor.',
  heroSubtitle: 'Operations is the asset-aware, risk-aware floor management layer of GymAxis. Track every machine from purchase to retirement, triage faults in seconds, run risk assessments on a schedule, and never lose another £20k treadmill to "we forgot to log a ticket".',
  heroVisualHeadline: 'Live floor health',
  heroVisualLines: [
    { label: 'Open faults', value: '4' },
    { label: 'Awaiting parts', value: '2' },
    { label: 'PPM due (7d)', value: '11' },
    { label: 'Risk assessments due', value: '3' },
  ],

  problemHeadline: 'A clipboard, a WhatsApp group, and a £100k blind spot.',
  problemBody: 'Most gyms have no asset register, no cost log, no warranty visibility, and no audit trail when an inspector asks for the latest risk assessment. Faults sit in a WhatsApp group, parts are ordered from memory, capex runs on gut feel, and members ride the same broken bike for three weeks before a manager notices.',
  solutionHeadline: 'One asset register. One fault flow. One source of truth.',
  solutionBody: 'GymAxis Operations makes every piece of equipment a first-class object — QR scan, fault history, supplier link, warranty expiry, scheduled risk assessments, lifecycle cost, and predictive replacement timing. Your engineers, suppliers, finance team and HSE auditors all see the same screen.',

  featuresHeadline: 'Everything Operations can do.',
  features: [
    { icon: ClipboardList,  title: 'Asset register',         body: 'Every machine with serial, supplier, warranty, install date, lifecycle cost, and full history in one place.' },
    { icon: AlertTriangle,  title: 'Fault triage',           body: 'AI-assisted severity, auto-routing to the right engineer, supplier email triggered the moment it leaves the gym.' },
    { icon: QrCode,         title: 'QR scan to fault',       body: 'Members and staff scan a sticker — fault logged in 7 seconds, photo + description attached.' },
    { icon: ShieldCheck,    title: 'Warranty tracking',      body: 'Auto-flags faults still in warranty so suppliers pay, not you. Saved one site £8 200 in Q1.' },
    { icon: ClipboardCheck, title: 'Risk Assessment reports',body: 'Schedule per-zone or per-asset risk assessments, capture findings inline, generate a PDF audit report on demand.' },
    { icon: FileBarChart,   title: 'Capex & lifecycle',      body: 'Replacement-cost forecasts based on age, usage and fault frequency. Plan capex, not panic.' },
  ],

  visualSections: [
    {
      eyebrow: 'Fault inbox',
      title: 'Triage built for the gym floor.',
      body: 'Faults land sorted by severity. One tap escalates to a supplier with the warranty contract attached. Two taps marks resolved with a parts cost.',
      bullets: [
        'AI suggests likely cause from the description',
        'Auto-pause member access for unsafe machines',
        'Side-by-side supplier response times',
      ],
      visualEyebrow: 'Today',
      visualHeadline: 'Open faults · 4',
      visualRows: [
        { l: 'Treadmill #14 · won\'t calibrate', r: 'Critical' },
        { l: 'Lat pulldown · cable fray', r: 'High' },
        { l: 'Bike #3 · loose pedal', r: 'Med' },
        { l: 'Dumbbell rack #2 · missing 12kg', r: 'Low', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Risk Assessment reports',
      title: 'Every machine and every zone — auditor-ready.',
      body: 'Schedule risk assessments per-asset or per-zone (free-weight area, studio, pool deck), capture photos and findings inline on a phone, and export an HSE-ready PDF report on demand. Findings auto-create work orders so nothing slips.',
      bullets: [
        'Templates for free-weights, cardio, studio, pool, sauna',
        'Findings auto-spawn work orders + assigned owner',
        'Signed PDF export, including timestamps and auditor signature',
      ],
      visualHeadline: 'RA · April',
      visualRows: [
        { l: 'Free-weight area', r: 'Passed' },
        { l: 'Studio 1 · cabling', r: 'Action req.' },
        { l: 'Pool deck · slip risk', r: 'Action req.' },
        { l: 'Cardio zone', r: 'Passed', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Asset detail',
      title: 'Every machine has a story.',
      body: 'Tap any equipment to see the full timeline — purchases, faults, parts, costs, warranty status, and projected end-of-life. Auditable, exportable, kind to your accountant.',
      bullets: [
        'Lifecycle cost per asset with depreciation',
        'Warranty windows highlighted in green',
        'Photo + serial + supplier in one click',
      ],
      visualHeadline: 'Treadmill #14',
      visualRows: [
        { l: 'Installed', r: 'Sep 2023' },
        { l: 'Faults YTD', r: '3' },
        { l: 'Parts cost', r: '£412.00' },
        { l: 'Warranty', r: 'Until 2026', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that diagnoses before you call out an engineer.',
  aiBody: 'Operations\' built-in AI reads fault descriptions, photos, and historical patterns to suggest cause, parts needed, and which supplier handled it last. Most reactive jobs are now resolved without a billable visit.',
  aiCapabilities: [
    { title: 'Fault diagnosis', body: 'Photo + free text in, suggested cause + part numbers out — typically within seconds.' },
    { title: 'Predictive replacement', body: 'Flags machines whose fault frequency has crossed the "replace, don\'t repair" line.' },
    { title: 'Supplier response scoring', body: 'Auto-ranks suppliers by responsiveness, fix-rate and price — surface the laggards before contract renewal.' },
  ],

  integrationsHeadline: 'Operations is wired into the rest of GymAxis.',
  integrations: [
    { icon: Users,     name: 'CRM',         color: '#6366F1', to: '/platform/crm',         body: 'Faults on a member\'s favourite machine trigger a personal apology email + retention nudge.' },
    { icon: Calendar,  name: 'Memberships', color: '#8B5CF6', to: '/platform/memberships', body: 'Critical fault on a class machine? Memberships auto-relocates the affected booking.' },
    { icon: Megaphone, name: 'Marketing',   color: '#D946EF', to: '/platform/marketing',   body: 'Resolved fault triggers a "we listened" post for the studio\'s social channel.' },
    { icon: BarChart3, name: 'Reporting',   color: '#2563EB', to: '/platform/reporting',   body: 'Fault density, MTTR, capex pipeline and supplier scorecards on one dashboard.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '2.4×',   label: 'Faster fault resolution' },
    { value: '£8.2k',  label: 'Avg warranty recovered per site / year' },
    { value: '37%',    label: 'Lower reactive-engineer spend' },
    { value: '98.6%',  label: 'Equipment uptime (30-day)' },
  ],

  ctaHeadline: 'Stop paying for downtime.',
  ctaSubtitle: 'Set up your asset register and first risk assessment in under an hour. Your engineers, members and HSE auditor will thank you.',
};
