import {
  Megaphone, Mail, Workflow, Image as ImageIcon, BarChart, Zap, Sparkles,
  Wrench, Users, Calendar, BarChart3,
} from 'lucide-react';

export default {
  id: 'marketing',
  name: 'Marketing',
  color: '#D946EF',
  icon: Megaphone,

  heroLine1: 'Campaigns that',
  heroLine2: 'actually convert.',
  heroSubtitle: 'Marketing is the AI-powered growth engine of Pulse Fitness. Email, SMS, social, win-back, referral, and Instagram-ready class previews — written, designed and scheduled by AI in minutes.',
  heroVisualHeadline: 'Campaign performance · 30d',
  heroVisualLines: [
    { label: 'Sent', value: '8 412' },
    { label: 'Open rate', value: '42%' },
    { label: 'CTR', value: '11.8%' },
    { label: 'Revenue attrib.', value: '£9.2k' },
  ],

  problemHeadline: 'Your marketing tool doesn\'t know your members.',
  problemBody: 'Generic ESPs treat every member as an email address. Your front-desk knows Sarah just took her 50th class. Your booking app knows John\'s membership is freezing next week. Your marketing tool? It\'s sending them both the same generic newsletter.',
  solutionHeadline: 'Marketing that lives inside your operations data.',
  solutionBody: 'Audiences are pulled live from CRM and Memberships. The AI writer drafts campaigns grounded in your brand voice, your latest class data, your churn signals. Win-backs trigger from real cancellations. Referrals reward real members.',

  featuresHeadline: 'Everything Marketing can do.',
  features: [
    { icon: Mail,       title: 'Email + SMS broadcast', body: 'Domain-verified Resend for email, Twilio-ready for SMS. Open/click tracking, A/B test, deliverability dashboard.' },
    { icon: Workflow,   title: 'Journey canvas',        body: 'Visual builder for multi-step automations — welcome, onboarding, win-back, referral, no-show recovery.' },
    { icon: ImageIcon,  title: 'Creative studio',       body: 'AI-generated visuals (Nano Banana), brand kit, Instagram-ready class preview cards rendered server-side.' },
    { icon: Zap,        title: 'AI Director',           body: 'One prompt: "Win-back lapsed yoga members." AI builds the segment, writes the copy, schedules the send.' },
    { icon: BarChart,   title: 'Performance + attribution', body: 'Per-campaign revenue attribution back to bookings + plan upgrades. ROI by channel, not just opens.' },
    { icon: Sparkles,   title: 'Form + page builder',   body: 'Lead capture forms, public landing pages, embed snippets — all branded, all fed straight into CRM.' },
  ],

  visualSections: [
    {
      eyebrow: 'AI Director',
      title: 'Describe the goal. Ship the campaign.',
      body: '"Win back lapsed pilates members from the last 60 days, offer them a £15 drop-in, send Tuesday 10am." The AI Director does the segment, the copy, the design, the send time, and the success measurement.',
      bullets: [
        'Pulls audience from live CRM segments',
        'Brand voice grounded in your last 10 sends',
        'Undo-launch banner — 5-minute safety net',
      ],
      visualHeadline: 'New campaign · auto-built',
      visualRows: [
        { l: 'Segment', r: '147 members' },
        { l: 'Subject', r: '"We miss you on the mat"' },
        { l: 'Send time', r: 'Tue 10:00' },
        { l: 'Forecast revenue', r: '£1.6k', tone: 'mute' },
      ],
    },
    {
      eyebrow: 'Shareable class previews',
      title: 'Every class is an Instagram post in waiting.',
      body: 'Share a class link to WhatsApp, Instagram or Facebook and get a 1200×630 server-rendered preview card with your brand colours, capacity, time and a "Book now" CTA.',
      bullets: [
        'OG image cached server-side (S3) — fast scrape',
        'Brand-coloured, instructor-aware',
        'Auto-updates when capacity or time changes',
      ],
      visualHeadline: 'Open Flow Yoga · Tue 07:00',
      visualRows: [
        { l: 'Spots left', r: '4 of 12' },
        { l: 'Instructor', r: 'Aiden Rowe' },
        { l: 'Share link copied', r: 'Yes' },
        { l: 'Preview cached', r: 'CDN-served', tone: 'mute' },
      ],
    },
  ],

  aiHeadline: 'AI that writes, designs, and ships campaigns for you.',
  aiBody: 'Marketing\'s AI is grounded in your brand voice, your member data, and your last 90 days of campaign performance. It writes copy, generates visuals, picks send times — and lets you undo any launch within 5 minutes.',
  aiCapabilities: [
    { title: 'Copy generation', body: 'Subject + preheader + body, on-brand, segment-aware. Not the "Hi {first_name}" generic stuff.' },
    { title: 'Image generation', body: 'Nano Banana renders campaign hero images and Instagram tiles in your brand palette.' },
    { title: 'Send-time intelligence', body: 'Picks the best send time per segment, based on historical engagement.' },
  ],

  integrationsHeadline: 'Marketing is wired into the rest of Pulse Fitness.',
  integrations: [
    { icon: Users,     name: 'CRM',         color: '#6366F1', to: '/platform/crm',         body: 'CRM segments are your live audiences. No CSV exports, no list rot.' },
    { icon: Calendar,  name: 'Memberships', color: '#8B5CF6', to: '/platform/memberships', body: 'Class data + capacity + bookings power the auto-generated campaign creative.' },
    { icon: Wrench,    name: 'Operations',     color: '#06B6D4', to: '/platform/service',     body: 'Resolved equipment fault triggers a "we listened" social post automatically.' },
    { icon: BarChart3, name: 'Reporting',   color: '#2563EB', to: '/platform/reporting',   body: 'Campaign ROI rolled into the platform-wide revenue dashboard.' },
  ],

  resultsHeadline: 'Real numbers from real operators.',
  results: [
    { value: '42%',  label: 'Avg email open rate' },
    { value: '7×',   label: 'Faster campaign-to-launch time' },
    { value: '£11k', label: 'Avg attributable revenue / month' },
    { value: '24%',  label: 'Win-back recovery rate' },
  ],

  ctaHeadline: 'Stop sending generic newsletters.',
  ctaSubtitle: 'Run AI-built, data-grounded marketing campaigns in minutes — not weeks.',
};
