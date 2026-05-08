import {
  BarChart3, LineChart, PieChart, FileText, ShieldCheck, Database, Sparkles,
  Wrench, Users, Calendar, Megaphone,
} from 'lucide-react';

export default {
  id: 'reporting',
  name: 'Reporting',
  color: '#2563EB',
  icon: BarChart3,

  heroLine1: 'See the whole',
  heroLine2: 'business.',
  heroSubtitle: 'Reporting is the analytics, audit and compliance layer of GymAxis. Cohort retention, LTV, capex pipeline, wage ratio, NPS, and a tamper-evident audit log built for SOC 2 evidence and operator transparency.',
  heroVisualHeadline: 'Business at a glance',
  heroVisualLines: [
    { label: 'MRR', value: '£148k' },
    { label: '6-mo retention', value: '78%' },
    { label: 'NPS', value: '+62' },
    { label: 'Equipment uptime', value: '98.6%' },
  ],

  problemHeadline: 'Five tools, five dashboards, none reconcile.',
  problemBody: 'Your finance team exports CSVs from the booking app, the engineer\'s portal, the email tool and the rota sheet — then spends Friday afternoon stitching them together in Excel. By Monday, the numbers are already stale.',
  solutionHeadline: 'One dataset. One dashboard. One audit trail.',
  solutionBody: 'Reporting reads directly from every other module. Cohort retention from Memberships, lead-source ROI from CRM, capex from Service, wage ratio from Staffing, campaign attribution from Marketing — all on the same timeline.',

  featuresHeadline: 'Everything Reporting can do.',
  features: [
    { icon: LineChart,   title: 'Cohort retention',     body: 'Joiners by month vs retention curves. Spot the cohort that\'s churning before it costs you a quarter.' },
    { icon: PieChart,    title: 'Revenue & LTV',        body: 'MRR, ARR, average LTV by plan, by site, by instructor, by lead source. Export to .xlsx for the board.' },
    { icon: BarChart3,   title: 'Operational KPIs',     body: 'Class fill, no-show rate, fault density, MTTR, wage ratio, marketing CPL — every number you need.' },
    { icon: FileText,    title: 'Weekly digest',        body: 'Auto-generated Friday digest: top wins, watch-outs, AI insights. Designed for the multi-site CEO.' },
    { icon: ShieldCheck, title: 'Audit log',            body: 'Tamper-evident master-admin audit trail with CSV export. Built for SOC 2 / ISO 27001 evidence and internal compliance.' },
    { icon: Database,    title: 'API + data export',    body: 'Read-only API for your data warehouse. CSV / Parquet exports nightly to S3 if you have a BI team.' },
  ],

  visualSections: [
    {
      eyebrow: 'Cohort retention',
      title: 'Spot churn before your accountant does.',
      body: 'Joiners-by-month vs retention curves give you 90 days of warning before MRR slips. Slice by site, plan, lead source or instructor. Export the underlying data, no questions asked.',
      bullets: [
        'Joiner cohorts overlaid by month',
        'AI surfaces the under-performing cohort weekly',
        'CSV / Parquet export for warehouse teams',
      ],
      visualHeadline: 'Cohorts · last 6 months',
      visualRows: [
        { l: 'Nov \'25 cohort · 6mo', r: '82%' },
        { l: 'Dec \'25 cohort · 5mo', r: '79%' },
        { l: 'Jan \'26 cohort · 4mo', r: '74%' },
        { l: 'Feb \'26 cohort · 3mo', r: '88%', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Audit log',
      title: 'Every master-admin action, immutable.',
      body: 'Login events, role changes, billing overrides, tenant switches, data wipes — captured with actor, target, timestamp and metadata. CSV export ready for your auditor or compliance team.',
      bullets: [
        'Append-only, tamper-evident',
        'Filter by actor, target, action',
        'CSV export with hash-chain verification',
      ],
      visualHeadline: 'Audit · today',
      visualRows: [
        { l: 'craig@ · invoice override', r: '14:02' },
        { l: 'lee@ · plan upgrade', r: '12:38' },
        { l: 'admin@ · tenant switch', r: '11:11' },
        { l: 'system · JWT rotation', r: '00:00', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that flags the number you should be looking at.',
  aiBody: 'Reporting\'s AI watches every metric for anomalies and writes you a Friday digest in plain English. "Yoga class fill dropped 12% week-over-week. Likely cause: instructor change. Suggested action: ..." — that level of clarity.',
  aiCapabilities: [
    { title: 'Anomaly detection', body: 'Flags metric outliers across every module — usually 7–14 days before they hit the P&L.' },
    { title: 'Plain-English digest', body: 'Friday email with top 3 wins, top 3 watch-outs, recommended actions. Read in 90 seconds.' },
    { title: 'Question-to-chart', body: 'Ask "show me yoga retention by instructor since January" — get a chart, not a Jira ticket.' },
  ],

  integrationsHeadline: 'Reporting is wired into the rest of GymAxis.',
  integrations: [
    { icon: Calendar,  name: 'Memberships', color: '#8B5CF6', to: '/platform/memberships', body: 'Class fills, retention, no-shows and Auto-Bill recovery flow in live.' },
    { icon: Users,     name: 'CRM',         color: '#6366F1', to: '/platform/crm',         body: 'Lead-source ROI, conversion funnels, NPS by segment.' },
    { icon: Wrench,    name: 'Service',     color: '#06B6D4', to: '/platform/service',     body: 'Fault density, MTTR, capex pipeline and supplier scorecards.' },
    { icon: Megaphone, name: 'Marketing',   color: '#D946EF', to: '/platform/marketing',   body: 'Campaign ROI rolled into the same revenue dashboard as plan upgrades.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '5×',    label: 'Faster end-of-month close' },
    { value: '0',     label: 'Tools to reconcile' },
    { value: 'SOC 2', label: 'Audit-ready out of the box' },
    { value: '< 90s', label: 'Friday digest read time' },
  ],

  ctaHeadline: 'Stop stitching dashboards together on a Friday.',
  ctaSubtitle: 'Get a single source of truth for every operational and financial number that matters.',
};
