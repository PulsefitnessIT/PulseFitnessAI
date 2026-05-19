import CompareLayout from './CompareLayout';

const competitor = {
  name: 'Glofox', slug: 'glofox',
  tagline: 'Boutique gym management',
  founded: 2014, hq: 'Dublin, IE', focus: 'Bookings + member retention',
};
const hero = {
  headline: 'GymAxis vs Glofox — boutique polish meets operations depth.',
  subheadline:
    'Glofox is great for boutique studio bookings and brand consistency. GymAxis adds the operations + service desk + Sage / Sicon link multi-site operators need to stop juggling tools.',
};
const matrix = [
  { feature: 'Branded member PWA',                     gymaxis: true,  competitor: true },
  { feature: 'Class booking + waitlists',              gymaxis: true,  competitor: true },
  { feature: 'Lead capture + marketing automation',    gymaxis: true,  competitor: 'Limited' },
  { feature: 'Equipment register + serial-tracking',   gymaxis: true,  competitor: false },
  { feature: 'Service desk (cases, parts, engineers)', gymaxis: true,  competitor: false },
  { feature: 'AI triage with parts allocation',        gymaxis: true,  competitor: false },
  { feature: 'Multi-site contracts (Sicon link)',      gymaxis: true,  competitor: false },
  { feature: 'Sage 200 invoice + quote outbox',        gymaxis: true,  competitor: false },
  { feature: 'Master-admin tamper-evident audit log',  gymaxis: true,  competitor: 'No' },
  { feature: 'Self-serve trial',                       gymaxis: '3-day, all modules', competitor: 'Sales-led' },
];
const winsForGymAxis = [
  { title: 'One platform, not three subscriptions', body: 'Operations + Memberships + Marketing + CRM Lite are bundled. Glofox + a service tool + a CRM is three vendors and three contracts.' },
  { title: 'Service desk and engineer mobile', body: 'Operators triage, dispatch and bill chargeable repairs in-app. Field engineers work offline-first on the PWA. Glofox has no equivalent.' },
  { title: 'Sage 200 hand-off built-in', body: 'Every chargeable case auto-drafts a Sage SLQuote on the outbox at intake. Glofox stops at Stripe.' },
  { title: 'UK multi-site fluent', body: 'Site-scoped roles, tamper-evident audit, MOD-ready data residency story. Glofox is a single-site default.' },
];
const whenCompetitorWins = [
  { title: 'Single-location boutique with no equipment', body: 'If you don\'t need a service desk and brand-perfect booking is your one priority, Glofox\'s template gallery is a fast track.' },
];
const faqs = [
  { q: 'Can I match my Glofox brand?', a: 'Yes — the member PWA inherits your primary colour, logo, hero image and CTA copy via the Brand Kit. Every tenant ships with its own PWA manifest so "Add to Home Screen" lands the right icon and name on every member device.' },
  { q: 'Do you handle pre-paid class packs?', a: 'Yes — 10-class packs, monthly unlimited, annual unlimited, free-trial passes. Credits, expiry rules, and rebook flows all built in.' },
  { q: 'What if I outgrow Glofox\'s service ticket workflow?', a: 'That\'s exactly when GymAxis pays for itself. The service desk + engineer mobile replaces 2-3 separate tools (ticketing, parts, dispatch) with one.' },
  { q: 'How is your AI different?', a: 'We use Claude Sonnet for triage, photo classification and case summarisation grounded in your real parts catalogue — not generic LLM guesses.' },
];

export default function CompareGlofox() {
  return (
    <CompareLayout
      competitor={competitor}
      hero={hero}
      matrix={matrix}
      winsForGymAxis={winsForGymAxis}
      whenCompetitorWins={whenCompetitorWins}
      faqs={faqs}
    />
  );
}
