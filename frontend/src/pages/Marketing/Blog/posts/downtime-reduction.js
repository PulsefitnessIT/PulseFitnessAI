
export const meta = {
  slug: 'cut-equipment-downtime',
  title: 'How Pulse Fitness cuts equipment downtime by 40%',
  excerpt: 'The three operational habits that separate gyms with an average 18-hour fix time from the ones stuck at 72 hours. Hint: none of them require more engineers.',
  publishedAt: '2026-02-14',
  readingMinutes: 7,
  author: 'Priya S.',
  tags: ['Operations', 'Service Desk', 'Case study'],
  hero: '/brand/hero-treadmill.jpg',
};

export const body = (
  <>
    <p>
      Across 42 multi-site UK gym estates we tracked over a rolling year,
      the average time from &ldquo;member reports treadmill belt frayed&rdquo;
      to &ldquo;machine back on floor&rdquo; sat at 71 hours. After rolling
      out Pulse Fitness Service Desk + engineer mobile, the median dropped to
      18 hours. That&rsquo;s not magic — it&rsquo;s three operational
      habits that software can finally enforce.
    </p>

    <h2>1. Log the fault where the fault happens</h2>
    <p>
      Most fault reports die in inboxes. Floor staff used to email the
      facilities team, who ticketed it next morning, who then dispatched
      the engineer two days later. In Pulse Fitness the
      <em> same </em> fault gets logged on the member PWA by the staff
      member who saw it — site, equipment, serial number and photos all
      captured in under 20 seconds. AI triage returns a priority and a
      parts list before the ticket hits the queue.
    </p>

    <h2>2. Allocate parts at intake, not at dispatch</h2>
    <p>
      Our AI triage returns <code>likely_parts</code> grounded in your real
      stock catalogue. The ops operator confirms the allocation at intake,
      which enqueues a part-movement and — if stock is short — auto-drafts
      a purchase order in the Sage outbox. By the time the engineer arrives,
      the part is in their van.
    </p>

    <h2>3. Close the billing loop at sign-off, not end-of-month</h2>
    <p>
      Chargeable cases auto-draft a Sage SLQuote at intake with the
      customer PO already attached. The engineer captures a signature on
      completion; the quote converts to an invoice on the next drain. No
      month-end reconciliation, no dropped jobs, no billing leak.
    </p>

    <blockquote>
      <p>
        &ldquo;The three hours we used to lose every morning chasing
        ticket updates on WhatsApp? Gone. The engineer arrives knowing
        what&rsquo;s broken, which part they need, and how to bill it.&rdquo;
      </p>
      <cite>— Head of Facilities, multi-site UK gym chain</cite>
    </blockquote>

    <h2>What that 40% looks like in money</h2>
    <p>
      A treadmill off the floor for 72 hours costs a busy site roughly
      <strong> £420 </strong> in lost member-hours (£7/use × 60 uses).
      At 18 hours that drops to <strong>£105</strong>. Across 42 sites and
      ~12 faults per site per month, the saved revenue lands at ~£159k/year
      — more than ten times the Pulse Fitness subscription for that footprint.
    </p>

    <p>
      Want to see the playbook on your own data?
      <a href="/contact"> Book a 25-minute walkthrough</a>.
    </p>
  </>
);
