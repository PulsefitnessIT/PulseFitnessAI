import {
  UserCog, Calendar as CalIcon, ClipboardCheck, BadgeCheck, Repeat, FileText,
  Wrench, Users, Calendar, Megaphone,
} from 'lucide-react';

export default {
  id: 'staffing',
  name: 'Staffing',
  color: '#A855F7',
  icon: UserCog,

  heroLine1: 'Run the gym',
  heroLine2: 'floor.',
  heroSubtitle: 'Staffing is the rota, performance and live-floor layer of Pulse Fitness. From a 4-person studio to a 60-instructor multi-site, every shift, swap, time-off request, payroll line and live attendance event in one place.',
  heroVisualHeadline: 'On the floor right now',
  heroVisualLines: [
    { label: 'Staff on shift', value: '7' },
    { label: 'Open shifts (week)', value: '3' },
    { label: 'Swap requests', value: '2' },
    { label: 'Payroll (mo-to-date)', value: '£18.4k' },
  ],

  problemHeadline: 'Rotas in spreadsheets, swaps in WhatsApp, payroll in tears.',
  problemBody: 'Most operators run their team off a Google Sheet with tabs for each week. Swaps happen in WhatsApp. Time-off lives in someone\'s inbox. Payroll is a 4-hour copy-paste exercise the manager dreads. Mistakes cost wages, morale and licences.',
  solutionHeadline: 'One rota. One marketplace. One payroll export.',
  solutionBody: 'Publish a rota in two minutes. Staff claim open shifts from the marketplace. Time-off goes through approval flow. Payroll exports to your accounting tool with one click — and your gym floor view tells you who\'s actually on right now.',

  featuresHeadline: 'Everything Staffing can do.',
  features: [
    { icon: CalIcon,        title: 'Rota optimiser',         body: 'Drag-and-drop weekly rota with cost forecast, conflict detection, and AI-suggested coverage.' },
    { icon: Repeat,         title: 'Shift marketplace',      body: 'Open shifts go to a marketplace. Eligible staff claim, the rota updates, the manager confirms.' },
    { icon: ClipboardCheck, title: 'Time-off + approvals',   body: 'Holiday, sick, training requests with multi-tier approval and visible balances per staff member.' },
    { icon: BadgeCheck,     title: 'Instructor profiles',    body: 'Public bios, member ratings, certifications, pay-per-class agreements, and class history.' },
    { icon: FileText,       title: 'Payroll export',         body: 'Pay-per-class, hourly, salaried — exports to Xero / QuickBooks in one click.' },
    { icon: UserCog,        title: 'Live gym floor',         body: 'Real-time view of who\'s clocked in, who\'s teaching, who\'s on break — perfect for duty managers.' },
  ],

  visualSections: [
    {
      eyebrow: 'Rota canvas',
      title: 'Build a rota that actually balances cost and cover.',
      body: 'Drag staff onto shifts. The optimiser flags double-bookings, overtime risks, and certifications gaps before you publish. Costs forecast live so you never blow the wage budget.',
      bullets: [
        'Cost-aware suggestions per shift',
        'Certification + skill matching',
        'One-click publish + staff notify',
      ],
      visualHeadline: 'Week 18 · cost £4.2k',
      visualRows: [
        { l: 'Open shifts', r: '3' },
        { l: 'Conflicts', r: '0' },
        { l: 'Forecast vs budget', r: '−£140' },
        { l: 'Coverage gaps', r: 'Tue 18:00', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Live floor',
      title: 'Know who\'s on without walking the floor.',
      body: 'Duty managers see every staff member\'s status — clocked in, teaching, on break, finished — in real time. Tap any name for the day\'s schedule, certifications and last 30-day attendance.',
      bullets: [
        'Mobile-first for duty managers',
        'Tap-to-call and tap-to-message',
        'Auto-flags no-shows for HR follow-up',
      ],
      visualHeadline: 'Floor · 14:32',
      visualRows: [
        { l: 'Aiden · Yoga studio', r: 'Teaching' },
        { l: 'Lee · Gym floor', r: 'On shift' },
        { l: 'Maya · Front desk', r: 'On break' },
        { l: 'Tom · Studio 2', r: 'Late', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that runs the rota, not just stores it.',
  aiBody: 'Staffing\'s AI rebalances the rota when sickness comes in, suggests the cheapest qualified swap, and flags when your wage-to-revenue ratio starts trending the wrong way.',
  aiCapabilities: [
    { title: 'Auto-rebalance', body: 'Sickness call-out at 06:00? AI offers the marketplace to qualified staff and re-publishes within 60 seconds.' },
    { title: 'Wage ratio alerts', body: 'Flags overstaffed quiet hours and understaffed peaks — usually saves 6-9% on wage cost.' },
    { title: 'Shift fit scoring', body: 'When a member books a PT slot, AI suggests the best instructor based on attendance history and rating.' },
  ],

  integrationsHeadline: 'Staffing is wired into the rest of Pulse Fitness.',
  integrations: [
    { icon: Calendar,  name: 'Memberships', color: '#8B5CF6', to: '/platform/memberships', body: 'Class instructors auto-publish to the rota. PT sessions take qualified staff out of the open pool.' },
    { icon: Users,     name: 'CRM',         color: '#6366F1', to: '/platform/crm',         body: 'Member-instructor ratings feed CRM and shape staffing decisions for VIP members.' },
    { icon: Wrench,    name: 'Operations',     color: '#06B6D4', to: '/platform/service',     body: 'Engineers visiting the site appear on the live floor view alongside your staff.' },
    { icon: Megaphone, name: 'Marketing',   color: '#D946EF', to: '/platform/marketing',   body: 'Instructor profiles power class previews and public booking pages.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '−27%', label: 'Time spent building rotas' },
    { value: '6–9%', label: 'Avg wage cost saved per site' },
    { value: '< 60s',label: 'Average shift-cover replacement' },
    { value: '92%',  label: 'Marketplace fill rate' },
  ],

  ctaHeadline: 'Get your team off the spreadsheet.',
  ctaSubtitle: 'Publish your first rota in 10 minutes. Your staff will install the app the same day.',
};
