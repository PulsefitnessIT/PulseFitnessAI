import {
  Calendar, CreditCard, Users2, Smartphone, RefreshCcw, Wallet,
  Wrench, Users, Megaphone, BarChart3,
} from 'lucide-react';

export default {
  id: 'memberships',
  name: 'Memberships',
  color: '#8B5CF6',
  icon: Calendar,

  heroLine1: 'Classes, plans,',
  heroLine2: 'walk-ins.',
  heroSubtitle: 'Memberships is the booking, billing and member-experience layer of Pulse Fitness. Built equally well for boutique studios, dance schools and multi-site chains — six selling models, family billing, and Auto-Bill that quietly pays itself.',
  heroVisualHeadline: 'Today\'s timetable',
  heroVisualLines: [
    { label: 'Classes today', value: '14' },
    { label: 'Booked seats', value: '136' },
    { label: 'Waitlist', value: '8' },
    { label: 'Auto-Bill due', value: '£4.2k' },
  ],

  problemHeadline: 'Boutique tools don\'t scale. Big-box tools don\'t humanise.',
  problemBody: 'Studios outgrow their booking app the day they hire a second instructor. Multi-site chains drown members in clunky portals from 2009. And dance schools end up running termly invoices on a spreadsheet.',
  solutionHeadline: 'One Memberships engine. Six selling models. Studio Mode for new operators.',
  solutionBody: 'Recurring, fixed-term, class packs (with credits + expiry), pay-as-you-go, courses (with pro-rata holiday smoothing), bundles. Studio Mode trims 16 tabs to 7 for solo operators. Family Auto-Bill charges the parent on the 1st of the month off-session.',

  featuresHeadline: 'Everything Memberships can do.',
  features: [
    { icon: Calendar,   title: 'Timetable + bookings',  body: 'Live class schedule with capacity, waitlist auto-promote, family sub-profiles, and embeddable iframe.' },
    { icon: CreditCard, title: 'Family Auto-Bill',      body: 'Parent saves a card once. We charge the previous month\'s invoice off-session on the 1st. Dunning ladder if it declines.' },
    { icon: Wallet,     title: 'Family Wallet',         body: 'Pre-paid balance per parent. Auto-Bill checks the wallet first — fewer card declines, better cash-flow signal.' },
    { icon: Users2,     title: 'Family + sub-profiles', body: 'One parent, multiple kids, sibling discount auto-applied at invoice time. Termly billing supported.' },
    { icon: RefreshCcw, title: 'Course builder',        body: 'Drag a 12-week dance term into a course — auto-skips bank holidays and pro-rates the monthly invoice.' },
    { icon: Smartphone, title: 'PWA Member app',        body: 'Add-to-home-screen, branded per studio, offline-capable shell. Members feel like you built them an app.' },
  ],

  visualSections: [
    {
      eyebrow: 'Auto-Bill',
      title: 'Cash-flow on autopilot.',
      body: 'On the 1st of every month, every Auto-Bill member gets charged off-session. If it declines, the dunning ladder kicks in (gentle reminder → stern → final notice) so you don\'t have to chase parents personally.',
      bullets: [
        'Stripe SetupIntent — PCI-out-of-scope',
        '3-step dunning ladder, brand-aware emails',
        'Wallet applied first → fewer declines',
      ],
      visualHeadline: 'Auto-Bill cycle · 1 May',
      visualRows: [
        { l: 'Members on Auto-Bill', r: '142' },
        { l: 'Charged successfully', r: '139' },
        { l: 'Wallet-only (no card)', r: '14' },
        { l: 'Failed → retrying', r: '3', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Studio Mode',
      title: 'Set up in 10 minutes, not 10 weeks.',
      body: 'Solo operators flip Studio Mode on and the console trims 16 tabs to 7. The 4-step quickstart wizard creates a drop-in plan, a monthly unlimited, a weekly class template + 8 occurrences, and hands them a public booking URL.',
      bullets: [
        '4-step wizard with sensible UK defaults',
        'Public booking page in one tap',
        'Toggle off any time to unlock the full console',
      ],
      visualHeadline: 'Quickstart · Step 4 / 4',
      visualRows: [
        { l: 'Plan: £15 drop-in', r: 'Created' },
        { l: 'Plan: £65/mo unlimited', r: 'Created' },
        { l: 'Class: Mon 18:00 (8 weeks)', r: 'Created' },
        { l: 'Public URL', r: 'Copied', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that knows your members better than you do.',
  aiBody: 'Memberships uses Claude to predict churn 14 days early, recommend the right plan to each member based on attendance pattern, and rewrite cancellation emails to recover members on the way out.',
  aiCapabilities: [
    { title: 'Churn prediction', body: 'Flags members whose booking pattern is about to drop. Gives you 14–28 days to intervene.' },
    { title: 'Plan recommendation', body: 'Tells the member they\'re overpaying or underpaying based on real usage. Honest tool. Saves cancellations.' },
    { title: 'Win-back drafts', body: 'Auto-drafts a personalised win-back email for every cancellation, ready for one-click send.' },
  ],

  integrationsHeadline: 'Memberships is wired into the rest of Pulse Fitness.',
  integrations: [
    { icon: Users,     name: 'CRM',       color: '#6366F1', to: '/platform/crm',       body: 'Every booking, freeze and family invoice lands on the contact timeline automatically.' },
    { icon: Megaphone, name: 'Marketing', color: '#D946EF', to: '/platform/marketing', body: 'Member segments ("no class in 14d") are one-click campaign audiences.' },
    { icon: Wrench,    name: 'Operations',   color: '#06B6D4', to: '/platform/service',   body: 'Equipment fault on a class machine? Booking auto-relocates and members are notified.' },
    { icon: BarChart3, name: 'Reporting', color: '#2563EB', to: '/platform/reporting', body: 'LTV, retention curves, no-show rates and Auto-Bill recovery on one screen.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '+27%',  label: 'Class fill rate' },
    { value: '94%',   label: 'Auto-Bill success rate' },
    { value: '32%',   label: 'Lower churn after 6 months' },
    { value: '< 10m', label: 'Studio set-up time' },
  ],

  ctaHeadline: 'Take bookings, payments and family invoicing off your plate.',
  ctaSubtitle: 'Studios up and running in under an hour. Multi-site chains in two weeks.',
};
