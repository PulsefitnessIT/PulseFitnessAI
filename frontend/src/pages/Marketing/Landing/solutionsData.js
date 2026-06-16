/**
 * solutionsData.js — content for the programmatic /solutions/* SEO pages.
 *
 * Each entry targets one head/mid-tail keyword a gym operator or service
 * engineer actually searches. Keep the `slug` list in sync with
 * SOLUTION_SLUGS in backend/routes/seo_public.py so pages enter the
 * dynamic sitemap.
 *
 * Content is intentionally substantive (intro + pains + capabilities +
 * FAQ) so these are genuine landing pages, not thin doorway pages.
 */
export const SOLUTIONS = [
  {
    slug: 'gym-maintenance-software',
    eyebrow: 'Maintenance',
    keyword: 'gym equipment maintenance software',
    metaTitle: 'Gym Equipment Maintenance Software | Pulse Fitness AI',
    metaDescription:
      'Track faults, dispatch engineers, allocate parts and prove compliance with Pulse Fitness — purpose-built gym equipment maintenance software for multi-site operators.',
    h1: 'Gym equipment maintenance software that keeps every machine on the floor.',
    intro:
      'Downtime kills member experience and revenue. Pulse Fitness gives operators one place to log faults, triage them with AI, dispatch field engineers, allocate the right parts and evidence every repair — across one site or fifty.',
    audience: 'For operations managers, facilities teams and service engineers.',
    pains: [
      { title: 'Faults reported in five different places', body: 'WhatsApp, spreadsheets, a clipboard at reception, an email to the supplier. Nothing is tracked and nothing is owned.' },
      { title: 'No view of engineer workload', body: 'You can\'t see who is where, what\'s overdue, or which sites are carrying the most downtime this month.' },
      { title: 'Parts chaos', body: 'Vans are over- or under-stocked, the right part is never on board, and you can\'t tell warranty from chargeable.' },
      { title: 'Compliance you can\'t prove', body: 'When an inspector or insurer asks for the service history of a machine, you\'re digging through emails.' },
    ],
    features: [
      { title: 'Fault logging with AI triage', body: 'Staff or members report a fault in seconds. Claude-powered triage classifies severity, suggests likely causes and pre-allocates the probable parts.' },
      { title: 'Engineer mobile, offline-first', body: 'Field engineers work the job on a PWA that keeps working in a plant room with no signal, then syncs when back online.' },
      { title: 'Planned preventive maintenance (PPM)', body: 'Schedule recurring service visits per asset or contract; the next visit auto-queues the moment the last one is closed.' },
      { title: 'Parts & van stock control', body: 'Catalogue, van and warehouse stock, transfers, min/max reorder and stock-takes — with warranty vs chargeable cover built in.' },
      { title: 'Proof of work', body: 'Photos, signatures, GPS arrival/departure and a return-visit brief, all folded into a single service report PDF.' },
      { title: 'Compliance-ready history', body: 'Every machine carries a full, time-stamped service and inspection trail you can export on demand.' },
    ],
    faqs: [
      { q: 'Can it handle multiple sites?', a: 'Yes — Pulse Fitness is multi-site by default with site-scoped roles, per-site dashboards and a portfolio view across the whole estate.' },
      { q: 'Do engineers need a signal to work?', a: 'No. The engineer app is offline-first; jobs, photos and parts usage queue locally and sync automatically when connectivity returns.' },
      { q: 'Can I tell warranty from chargeable repairs?', a: 'Yes. Every part allocation is classified against the asset\'s contract cover, so chargeable work is flagged for billing automatically.' },
      { q: 'Does it integrate with our finance system?', a: 'Pulse Fitness drafts Sage 200 quotes/invoices for chargeable work and maps van-stock movements to Sage stock (Sicon WebAPI) where available.' },
      { q: 'How fast can we go live?', a: 'Most operators import their asset register and start logging faults within days. A free 3-day trial unlocks every module.' },
    ],
    relatedSolutions: ['ppm-software-for-gym-equipment', 'gym-equipment-asset-management', 'fitness-equipment-service-management'],
    showManufacturers: true,
  },
  {
    slug: 'ppm-software-for-gym-equipment',
    eyebrow: 'Planned maintenance',
    keyword: 'PPM software for gym equipment',
    metaTitle: 'PPM Software for Gym Equipment | Planned Preventive Maintenance — Pulse Fitness',
    metaDescription:
      'Automate planned preventive maintenance for treadmills, bikes and strength kit. Pulse Fitness schedules PPM per asset and contract, auto-queues the next visit and proves compliance.',
    h1: 'PPM software that makes planned maintenance run itself.',
    intro:
      'Reactive-only maintenance is expensive and risky. Pulse Fitness turns planned preventive maintenance into a self-driving cadence: schedule visits per asset or contract, and the next PPM is created automatically the moment the engineer closes the current one.',
    audience: 'For facilities and service managers running scheduled maintenance.',
    pains: [
      { title: 'PPM lives in a spreadsheet', body: 'Schedules drift, visits get missed, and nobody notices until something breaks.' },
      { title: 'Manual re-scheduling', body: 'Every completed visit means someone has to remember to book the next one.' },
      { title: 'No link to the contract', body: 'The maintenance cadence isn\'t tied to what the customer actually pays for.' },
    ],
    features: [
      { title: 'Schedules per asset & contract', body: 'Define service intervals (e.g. every 90 days) at the asset or contract level. Activating a contract seeds the PPM schedule automatically.' },
      { title: 'Self-driving rollover', body: 'A background worker creates the next PPM case the instant the current one is completed — no manual re-booking.' },
      { title: 'Engineer-ready job packs', body: 'Each PPM visit arrives on the engineer app with the checklist, asset history and likely parts.' },
      { title: 'Coverage dashboards', body: 'See overdue, due-soon and on-track PPM across every site at a glance.' },
      { title: 'Audit-grade evidence', body: 'Each visit is signed, photographed and reported — ready for insurers and inspectors.' },
    ],
    faqs: [
      { q: 'How are schedules created?', a: 'Set an interval on the asset or contract; activating/signing a contract auto-seeds the schedule and first PPM case. You can also create them manually.' },
      { q: 'What happens when a visit is completed?', a: 'The rollover worker automatically queues the next PPM case based on the schedule interval — the cadence never stalls.' },
      { q: 'Can different assets have different intervals?', a: 'Yes — intervals are per asset/contract, so cardio, strength and specialist kit can each follow their own cadence.' },
      { q: 'Is reactive maintenance handled too?', a: 'Yes. PPM and reactive faults share the same service desk, engineer app, parts and reporting.' },
    ],
    relatedSolutions: ['gym-maintenance-software', 'fitness-equipment-service-management', 'gym-equipment-asset-management'],
    showManufacturers: true,
  },
  {
    slug: 'gym-equipment-asset-management',
    eyebrow: 'Asset register',
    keyword: 'gym equipment asset management',
    metaTitle: 'Gym Equipment Asset Management Software | Pulse Fitness AI',
    metaDescription:
      'A live, QR-tagged register of every machine across every site — with service history, warranty, depreciation and replacement planning. Pulse Fitness asset management for gyms.',
    h1: 'Know every machine you own — and exactly what it costs you.',
    intro:
      'You can\'t maintain, budget for or replace what you can\'t see. Pulse Fitness keeps a single live register of every asset across the estate, each with its full service history, warranty position and lifecycle status.',
    audience: 'For operations leaders, finance and asset owners.',
    pains: [
      { title: 'No single source of truth', body: 'Asset lists live in different spreadsheets per site and are out of date the day they\'re made.' },
      { title: 'Warranty leakage', body: 'Chargeable repairs slip through on machines that were still under warranty.' },
      { title: 'Reactive capex', body: 'Replacement decisions are made in a panic, not from data on cost-to-maintain and age.' },
    ],
    features: [
      { title: 'QR-tagged asset register', body: 'Every machine carries a QR code — scan to see its history, raise a fault or log a service on the spot.' },
      { title: 'Full lifecycle history', body: 'Purchase, warranty, every fault, every PPM, every part fitted — all on one asset record.' },
      { title: 'Warranty & contract cover', body: 'Each asset knows its cover, so warranty vs chargeable is decided automatically at the point of repair.' },
      { title: 'Cost-to-maintain insight', body: 'See which machines are draining the budget so replacement and capex decisions are data-led.' },
      { title: 'Bulk import & manufacturer catalogue', body: 'Import your estate in minutes and enrich it with a manufacturer product catalogue for accurate models and images.' },
    ],
    faqs: [
      { q: 'How do staff identify a machine?', a: 'Each asset gets a QR code. Scanning it opens the asset record to view history, report a fault or log work.' },
      { q: 'Can I import our existing asset list?', a: 'Yes — bulk import from spreadsheet, then enrich models and images from the built-in manufacturer catalogue.' },
      { q: 'Does it help with replacement planning?', a: 'Yes. Cost-to-maintain and age data make it obvious which assets to refurbish, replace or redeploy.' },
      { q: 'Is service history kept per machine?', a: 'Every fault, PPM visit and part fitted is recorded against the individual asset for its full lifecycle.' },
    ],
    relatedSolutions: ['gym-maintenance-software', 'ppm-software-for-gym-equipment', 'leisure-centre-management-software'],
    showManufacturers: true,
  },
  {
    slug: 'gym-crm-software',
    eyebrow: 'CRM',
    keyword: 'gym CRM software',
    metaTitle: 'Gym CRM Software | Sales, Contracts & Service in One — Pulse Fitness',
    metaDescription:
      'Gym CRM software that joins sales to service: track leads and contracts, then auto-onboard won deals into operations. Pulse Fitness CRM for multi-site fitness operators.',
    h1: 'A gym CRM that doesn\'t stop at the sale.',
    intro:
      'Most gym CRMs end the moment a deal is won. Pulse Fitness carries the customer straight through to delivery — a signed contract automatically seeds the maintenance schedule, the asset cover and the first service visit.',
    audience: 'For sales, account management and operations leaders.',
    pains: [
      { title: 'Sales and service are siloed', body: 'The CRM and the operations system don\'t talk, so won deals get re-keyed by hand.' },
      { title: 'Contracts lost in inboxes', body: 'Renewals, cover levels and SLAs live in PDFs nobody can find.' },
      { title: 'No single customer identity', body: 'The same customer exists three times across sales, service and finance.' },
    ],
    features: [
      { title: 'Leads, pipeline & contracts', body: 'Track opportunities through to signed contracts with cover levels, SLAs and renewal dates.' },
      { title: 'Sales-to-service onboarding', body: 'Activating a contract auto-creates the PPM schedule, asset cover and first service case — zero re-keying.' },
      { title: 'One customer identity', body: 'Canonical customer links join CRM, service ops and finance so everyone sees the same account.' },
      { title: 'Companies House enrichment', body: 'New companies are verified and enriched from Companies House on the way in.' },
      { title: 'Quote & contract documents', body: 'Generate branded quotes and contracts, and draft the matching Sage 200 records on the finance outbox.' },
    ],
    faqs: [
      { q: 'What makes this different from a generic CRM?', a: 'It\'s joined to operations. A won contract automatically becomes a live maintenance schedule and service cover — the deal turns into delivery without manual handover.' },
      { q: 'Can it manage renewals and SLAs?', a: 'Yes — contracts carry cover levels, SLAs and renewal dates, with the service desk enforcing them on every case.' },
      { q: 'Does it avoid duplicate customer records?', a: 'Yes. Canonical customer links unify the same account across CRM, service and finance.' },
      { q: 'Is finance integrated?', a: 'Chargeable work and quotes draft into Sage 200 via the finance outbox, keeping sales and finance aligned.' },
    ],
    relatedSolutions: ['leisure-centre-management-software', 'gym-maintenance-software'],
    showManufacturers: false,
  },
  {
    slug: 'leisure-centre-management-software',
    eyebrow: 'Leisure & multi-site',
    keyword: 'leisure centre management software',
    metaTitle: 'Leisure Centre Management Software | Pulse Fitness AI',
    metaDescription:
      'Run multi-site leisure centres from one platform: assets, maintenance, contracts, compliance and finance hand-off. Pulse Fitness leisure centre management software.',
    h1: 'One platform to run leisure centres at scale.',
    intro:
      'Leisure operators and trusts juggle dozens of sites, hundreds of assets and strict compliance. Pulse Fitness brings asset management, maintenance, contracts, compliance evidence and finance hand-off into a single, site-scoped platform.',
    audience: 'For leisure trusts, operators and multi-site facilities teams.',
    pains: [
      { title: 'Estate-wide blind spots', body: 'No portfolio view of downtime, compliance or maintenance spend across sites.' },
      { title: 'Tool sprawl', body: 'A different system for assets, tickets, parts, contracts and finance at every site.' },
      { title: 'Compliance pressure', body: 'Inspectors, insurers and funders expect evidence you can produce instantly.' },
    ],
    features: [
      { title: 'Site-scoped, estate-wide', body: 'Per-site roles and dashboards, plus a portfolio view across the whole estate.' },
      { title: 'Assets, maintenance & PPM', body: 'A live register, reactive faults and self-driving planned maintenance in one place.' },
      { title: 'Compliance evidence', body: 'Tamper-evident audit trails and per-asset service history ready for inspection.' },
      { title: 'Contracts & finance hand-off', body: 'Manage contracts and SLAs, and draft Sage 200 records for chargeable work automatically.' },
      { title: 'Engineer & supplier portals', body: 'In-house engineers and third-party suppliers collaborate on the same cases.' },
    ],
    faqs: [
      { q: 'Is it built for multiple sites?', a: 'Yes — site-scoped roles and dashboards with a portfolio view make it native to multi-site leisure estates.' },
      { q: 'Can third-party suppliers be involved?', a: 'Yes. A supplier portal lets external contractors take and update assigned cases without full system access.' },
      { q: 'How does it help with compliance?', a: 'Every asset carries a complete, tamper-evident service and inspection history you can export for inspectors and insurers.' },
      { q: 'Does it connect to finance?', a: 'Chargeable work and quotes draft into Sage 200 via the outbox, with van-stock movements mapped to Sage stock where available.' },
    ],
    relatedSolutions: ['gym-crm-software', 'gym-equipment-asset-management', 'gym-maintenance-software'],
    showManufacturers: true,
  },
  {
    slug: 'fitness-equipment-service-management',
    eyebrow: 'Service desk',
    keyword: 'fitness equipment service management software',
    metaTitle: 'Fitness Equipment Service Management Software | Pulse Fitness AI',
    metaDescription:
      'A complete service desk for fitness equipment: cases, AI triage, engineer dispatch, parts and SLAs — with a finance hand-off. Pulse Fitness service management software.',
    h1: 'A service desk built for fitness equipment, not generic tickets.',
    intro:
      'Generic helpdesks don\'t understand machines, parts or engineers. Pulse Fitness is a service desk designed for fitness equipment — from member-reported fault to dispatched engineer to billed repair, with SLAs enforced throughout.',
    audience: 'For service desks, dispatchers and field engineering teams.',
    pains: [
      { title: 'Generic tickets, no context', body: 'A standard helpdesk has no concept of an asset, a part or an engineer\'s van stock.' },
      { title: 'Manual dispatch', body: 'Matching the right engineer to the right job and site is a daily juggling act.' },
      { title: 'SLAs slip silently', body: 'Without enforcement, breaches are only noticed when a customer complains.' },
    ],
    features: [
      { title: 'Asset-aware cases', body: 'Every case is linked to the machine, its history, cover and likely parts.' },
      { title: 'AI triage & summarisation', body: 'Claude classifies severity, suggests causes and summarises long case threads for the next engineer.' },
      { title: 'Dispatch & engineer mobile', body: 'Assign jobs by site and skill; engineers work them offline-first with proof of work.' },
      { title: 'Parts & SLA enforcement', body: 'Allocate parts against cover and track SLA timers so breaches surface before customers notice.' },
      { title: 'Finance hand-off', body: 'Chargeable cases auto-draft Sage 200 quotes/invoices on the outbox.' },
    ],
    faqs: [
      { q: 'How is this different from a generic helpdesk?', a: 'It\'s asset- and parts-aware. Cases link to the specific machine, its cover and the engineer\'s van stock — not just a free-text ticket.' },
      { q: 'Does it enforce SLAs?', a: 'Yes — SLA timers run on every case and surface due-soon and breached work before customers escalate.' },
      { q: 'Can engineers raise and bill repairs?', a: 'Engineers record parts and work in the field; chargeable cases auto-draft Sage 200 quotes/invoices for billing.' },
      { q: 'Is AI involved?', a: 'Yes — Claude powers triage, photo classification and case summarisation, grounded in your real parts catalogue.' },
    ],
    relatedSolutions: ['gym-maintenance-software', 'ppm-software-for-gym-equipment', 'gym-equipment-asset-management'],
    showManufacturers: true,
  },
];

export const getSolution = (slug) => SOLUTIONS.find((s) => s.slug === slug);
