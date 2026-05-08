import {
  Users, UserPlus, Filter, MessageSquare, Sparkles, TrendingUp, Workflow,
  Wrench, Calendar, Megaphone, BarChart3,
} from 'lucide-react';

export default {
  id: 'crm',
  name: 'CRM',
  color: '#6366F1',
  icon: Users,

  heroLine1: 'Turn leads',
  heroLine2: 'into members.',
  heroSubtitle: 'CRM is the relationship engine of GymAxis. Every enquiry, tour, free trial, paying member and lapsed cancellation in one timeline — with AI deciding who to call next.',
  heroVisualHeadline: 'Pipeline today',
  heroVisualLines: [
    { label: 'New leads', value: '14' },
    { label: 'Tours booked', value: '6' },
    { label: 'Won (week)', value: '11' },
    { label: 'Forecast (mo)', value: '£18.4k' },
  ],

  problemHeadline: 'Sticky notes are not a sales pipeline.',
  problemBody: 'Front-desk teams juggle Excel, the gym\'s booking app, the marketing tool\'s contacts, and personal phone books. Half the leads from last week\'s open day were never followed up. The other half got three emails from three different staff members.',
  solutionHeadline: 'One pipeline. One contact record. One next action.',
  solutionBody: 'CRM unifies every touchpoint — web form, social DM, walk-in, referral, won-back churned member — into a single contact card with a clear next step. Pipeline stages mirror your real sales motion, not a generic SaaS template.',

  featuresHeadline: 'Everything CRM can do.',
  features: [
    { icon: UserPlus,       title: 'Unified contacts',       body: 'Every lead, member, family group and ex-member with the full timeline — no more duplicate records.' },
    { icon: Workflow,       title: 'Custom pipelines',       body: 'Configure stages per goal: cold lead → tour → trial → joined. Drag-and-drop the canvas to your motion.' },
    { icon: Filter,         title: 'Dynamic lists',          body: 'Build saved segments ("Joined < 30 days, no class booked yet") that refresh in real time.' },
    { icon: MessageSquare,  title: 'Activity timeline',      body: 'Calls, emails, classes, payments, support — everything a member did, on one screen.' },
    { icon: TrendingUp,     title: 'Revenue forecasting',    body: 'Pipeline-weighted forecast with confidence bands. Know your next month\'s bookings before they happen.' },
    { icon: Sparkles,       title: 'AI lead scoring',        body: 'Hot/Warm/Cold scoring trained on your historical conversions, plus the suggested next action per lead.' },
  ],

  visualSections: [
    {
      eyebrow: 'Pipeline view',
      title: 'See your whole motion at a glance.',
      body: 'Drag deals across stages, watch the conversion funnel update live, and let AI flag the leads slipping through the cracks. Pipeline-aware bulk actions mean you can email an entire stage in two clicks.',
      bullets: [
        'Pipeline canvas with deal value totals',
        'AI surfaces stalled leads daily',
        'One-click bulk email or SMS to a stage',
      ],
      visualHeadline: 'Pipeline · this month',
      visualRows: [
        { l: 'New', r: '24 · £6.0k' },
        { l: 'Tour booked', r: '11 · £4.4k' },
        { l: 'Trial', r: '7 · £3.2k' },
        { l: 'Won', r: '11 · £4.8k', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Contact card',
      title: 'The whole relationship, on one screen.',
      body: 'Class history, email opens, payment status, family group, last conversation, NPS — everything front-desk needs to feel like they remember every member by name.',
      bullets: [
        'Family-group view collapses parent + kids',
        'Notes sync to AI for contextual replies',
        'Custom properties — tag anything, segment by it',
      ],
      visualHeadline: 'Sarah Walker · Member',
      visualRows: [
        { l: 'Joined', r: '12 Jan 2026' },
        { l: 'Last class', r: '2 days ago' },
        { l: 'NPS', r: '9 / 10' },
        { l: 'Lifetime value', r: '£612', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that closes more leads, with less front-desk effort.',
  aiBody: 'Every CRM screen has Claude grounded against your data. Ask "who hasn\'t booked a class in 14 days?" and get an instant segment with a one-click email campaign attached.',
  aiCapabilities: [
    { title: 'Lead scoring', body: 'Hot/Warm/Cold scoring, retrained weekly on your won/lost outcomes.' },
    { title: 'Reply assistant', body: 'Drafts contextual replies grounded in the member\'s class history and last conversation.' },
    { title: 'Churn early-warning', body: 'Flags members whose attendance pattern matches historical cancellations 14–28 days before they ask to leave.' },
  ],

  integrationsHeadline: 'CRM is wired into the rest of GymAxis.',
  integrations: [
    { icon: Calendar,  name: 'Memberships', color: '#8B5CF6', to: '/platform/memberships', body: 'Bookings, freezes, family invoices feed the contact timeline automatically.' },
    { icon: Megaphone, name: 'Marketing',   color: '#D946EF', to: '/platform/marketing',   body: 'Pipeline segments are valid audiences. Send a campaign to "Tour booked, no follow-up" in one click.' },
    { icon: Wrench,    name: 'Service',     color: '#06B6D4', to: '/platform/service',     body: 'Member-reported faults appear in their CRM timeline and trigger automatic apologies.' },
    { icon: BarChart3, name: 'Reporting',   color: '#2563EB', to: '/platform/reporting',   body: 'Cohort retention, lead-source ROI, LTV by segment — all in one dashboard.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '+38%', label: 'Lead-to-member conversion' },
    { value: '4.2hr', label: 'Avg first-response time saved' },
    { value: '£14k',  label: 'Annual revenue lift per site' },
    { value: '32%',   label: 'Lower 6-month churn' },
  ],

  ctaHeadline: 'Stop losing members you\'ve already won.',
  ctaSubtitle: 'Pull every contact, lead and member into a single, AI-powered timeline this week.',
};
