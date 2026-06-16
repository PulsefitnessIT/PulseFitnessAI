import CompareLayout from './CompareLayout';

const competitor = {
  name: 'ClubReady', slug: 'clubready',
  tagline: 'Sales-CRM-led club management',
  founded: 2008, hq: 'Saint Louis, MO', focus: 'Lead-to-member CRM + billing',
};
const hero = {
  headline: 'Pulse Fitness vs ClubReady — sales pipeline that doesn\'t leak operations.',
  subheadline:
    'ClubReady is sales-pipeline-strong. Pulse Fitness matches it on CRM AND adds operations, service desk, contracts and a Sage 200 link. One tool replaces ClubReady + your service tool + your accounting bridge.',
};
const matrix = [
  { feature: 'Lead capture + sales pipeline',         gymaxis: true,  competitor: true },
  { feature: 'Recurring billing + ACH/Direct Debit',  gymaxis: 'Stripe + Sage', competitor: 'Native ACH' },
  { feature: 'Member portal + check-in',              gymaxis: true,  competitor: true },
  { feature: 'Equipment register + serial-tracking',  gymaxis: true,  competitor: false },
  { feature: 'Service desk (cases, parts, engineers)',gymaxis: true,  competitor: false },
  { feature: 'AI fault triage + photo classify',      gymaxis: true,  competitor: false },
  { feature: 'Multi-site contracts + renewal alerts', gymaxis: true,  competitor: 'Limited' },
  { feature: 'Sicon + Sage 200 outbox sync',          gymaxis: true,  competitor: false },
  { feature: 'Engineer mobile PWA (offline)',         gymaxis: true,  competitor: false },
  { feature: 'Self-serve trial',                      gymaxis: '3-day, all modules', competitor: 'Sales-led' },
];
const winsForPulseFitness = [
  { title: 'Operations + sales in one console', body: 'Service-desk faults, contract renewals and pipeline are all on the same data layer. ClubReady tells you who to sell to; Pulse Fitness also tells you which equipment is about to fail.' },
  { title: 'UK + EU first', body: 'GBP / EUR pricing, Sage 200 hand-off, MOD-ready data residency, and multi-currency reporting out of the box. ClubReady is built for the US club market.' },
  { title: 'AI that grounds in your data', body: 'Claude Sonnet returns priority + fault code + likely-parts grounded in YOUR catalogue and YOUR past fixes — not a generic taxonomy.' },
  { title: 'Tamper-evident audit log', body: 'Append-only master-admin audit with hash-chain verification. Evidence-grade for SOC 2 and pentests.' },
];
const whenCompetitorWins = [
  { title: 'US-only chain doing high-volume ACH', body: 'ClubReady\'s native ACH rail is hard to beat for US-only operators with thousands of monthly recurring members. We use Stripe for live payments.' },
];
const faqs = [
  { q: 'Can I migrate my ClubReady pipeline?', a: 'Yes — CSV import lands leads + opportunities + stage history. We map ClubReady\'s pipeline stages to the Pulse Fitness CRM stages on import.' },
  { q: 'Is your CRM as deep as ClubReady\'s?', a: 'Yes — territories, sharing rules, field-level security, forecasting & quotas, manager commit-call workflow, audit log. Plus a Marketing module ClubReady doesn\'t have.' },
  { q: 'What about ACH / direct debit?', a: 'Stripe today (covers cards + Bacs Direct Debit in the UK). GoCardless ACH on the roadmap.' },
  { q: 'How long is implementation?', a: 'Most operators are live on day 1 (Memberships + CRM) and on day 7 (Service Desk + Sage outbox). No professional services SOW required.' },
];

export default function CompareClubReady() {
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
