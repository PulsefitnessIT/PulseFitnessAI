import CompareLayout from './CompareLayout';

const competitor = {
  name: 'Mindbody', slug: 'mindbody',
  tagline: 'Bookings-first SaaS for studios and wellness',
  founded: 2001, hq: 'San Luis Obispo, CA', focus: 'Class booking + payments',
};
const hero = {
  headline: 'Pulse Fitness vs Mindbody — built for operators, not just bookings.',
  subheadline:
    'Mindbody is the default for studio class booking. Pulse Fitness is the default when your business is also asset-heavy — treadmills break, contracts renew, engineers visit. We added the operations + service-desk layer Mindbody never had.',
};
const matrix = [
  { feature: 'Class booking + payments',           gymaxis: true,  competitor: true },
  { feature: 'Member portal + branded PWA',        gymaxis: true,  competitor: true },
  { feature: 'Equipment register + serial-tracking', gymaxis: true, competitor: false },
  { feature: 'Service desk + engineer mobile',     gymaxis: true,  competitor: false },
  { feature: 'AI fault triage (Claude Sonnet)',    gymaxis: true,  competitor: false },
  { feature: 'Sage 200 invoice / quote outbox',    gymaxis: true,  competitor: 'Limited (Stripe only)' },
  { feature: 'Sicon CRM-Service link',             gymaxis: true,  competitor: false },
  { feature: 'Multi-site with master-admin audit', gymaxis: true,  competitor: 'Bolted-on' },
  { feature: 'Marketing + CRM Lite included',      gymaxis: true,  competitor: 'Add-on subscription' },
  { feature: 'Self-serve trial (no sales call)',   gymaxis: '3-day, all modules', competitor: 'Sales-led demo first' },
];
const winsForPulseFitness = [
  { title: 'Asset-aware from day one', body: 'Every fault, contract, quote and invoice is tied to a specific machine + serial. Mindbody treats equipment as a footnote.' },
  { title: 'Service desk + engineer mobile', body: 'Operators triage, schedule and complete jobs on a single platform — including offline-capable engineer PWA. Mindbody has nothing in this lane.' },
  { title: 'AI triage that actually maps to parts', body: 'Claude Sonnet returns priority + fault code + likely-parts grounded in your real catalogue, not a generic taxonomy.' },
  { title: 'Sicon + Sage outbox ready', body: 'Every chargeable case auto-drafts an SLQuote on the Sage outbox. Mindbody invoices via Stripe only — no link to UK accounting stacks.' },
];
const whenCompetitorWins = [
  { title: 'Studios with zero asset complexity', body: 'If you only run yoga / pilates / barre with no equipment to maintain, Mindbody\'s booking polish is hard to beat — you don\'t need our service desk.' },
  { title: 'You sell into the US wellness ecosystem', body: 'Mindbody\'s consumer marketplace drives organic discovery in US zip codes. We focus on UK gym + multi-site operations.' },
];
const faqs = [
  { q: 'Can I migrate my Mindbody members?', a: 'Yes — CSV import lands members + plans + recurring payments. We support a side-by-side period so renewals keep flowing while you cut over.' },
  { q: 'Do you handle class booking like Mindbody?', a: 'Yes. The Memberships module covers timetables, instructor pay, member PWA with rotating QR check-in, waitlists and bookings.' },
  { q: 'What about payments?', a: 'Stripe Connect for live payments today. Sage 200 outbox for the UK accounting hand-off. Direct Debit via GoCardless on the roadmap.' },
  { q: 'How long is the trial?', a: '3 days, all modules unlocked, no card required. Most operators decide on day 2.' },
];

export default function CompareMindbody() {
  return (
    <CompareLayout
      competitor={competitor}
      hero={hero}
      matrix={matrix}
      winsForPulseFitness={winsForPulseFitness}
      whenCompetitorWins={whenCompetitorWins}
      faqs={faqs}
    />
  );
}
