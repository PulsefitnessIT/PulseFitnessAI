
export const meta = {
  slug: 'service-desk-sla-explained',
  title: 'Service-desk SLAs explained for fitness operators',
  excerpt: 'What SLA targets actually mean, how to price them, and why most gym service contracts under-commit on response and over-commit on resolve.',
  publishedAt: '2026-02-01',
  readingMinutes: 5,
  author: 'Dominic F.',
  tags: ['Service Desk', 'Contracts', 'SLA'],
  hero: '/brand/hero-engineer.jpg',
};

export const body = (
  <>
    <p>
      &ldquo;4-hour response, 24-hour resolve&rdquo; sounds reassuring on a
      contract. In practice it&rsquo;s either a lie, a loss-leader, or both.
      Let&rsquo;s unpack what SLAs actually mean — and how to write ones
      that protect you and the customer.
    </p>

    <h2>Response vs resolve</h2>
    <p>
      <strong>Response</strong> = time from case logged to first human
      action (triage, customer contact, or engineer dispatched).
      <strong>Resolve</strong> = time from case logged to fault cleared
      and equipment back on floor. They move independently and need
      separate SLAs.
    </p>

    <h2>The four priority bands we recommend</h2>
    <table>
      <thead>
        <tr><th>Priority</th><th>Response</th><th>Resolve</th><th>Example</th></tr>
      </thead>
      <tbody>
        <tr><td>P1 — Critical</td><td>1h</td><td>4h</td><td>Cardio bank offline, safety hazard</td></tr>
        <tr><td>P2 — High</td><td>4h</td><td>24h</td><td>Single treadmill with belt wear</td></tr>
        <tr><td>P3 — Standard</td><td>8h</td><td>72h</td><td>Cosmetic damage, minor squeak</td></tr>
        <tr><td>P4 — Low</td><td>24h</td><td>7d</td><td>Scheduled PPM catch-up</td></tr>
      </tbody>
    </table>

    <h2>How to price each band</h2>
    <p>
      Every tier down, halve the response time and you roughly double
      the operational cost. A P1 commitment means someone is on-call
      24/7. A P4 commitment means you can batch the work. If a customer
      wants P1 on their entire fleet, price it accordingly (or walk
      away).
    </p>

    <h2>What breaks most contracts</h2>
    <p>
      <strong>Weekend clauses.</strong> A &ldquo;24-hour resolve&rdquo;
      that ignores Saturday / Sunday isn&rsquo;t a 24-hour resolve. Spell
      out working hours explicitly.
    </p>
    <p>
      <strong>Parts-dependency exclusions.</strong> If the part is out
      of stock, the SLA pauses. Make that crystal clear — customers
      accept it when told upfront, resent it when discovered mid-breach.
    </p>
    <p>
      <strong>Chargeable vs covered scope.</strong> Every contract
      should spell out which fault categories are in-cover vs
      chargeable. GymAxis tags each case with a cover type at intake
      so there&rsquo;s never a billing surprise.
    </p>

    <h2>Measuring yourself</h2>
    <p>
      The GymAxis reporting module shows SLA compliance % per priority
      band per site. If your P2 compliance is below 95%, you&rsquo;re
      either under-pricing the tier or under-resourcing it.
    </p>

    <p>
      <a href="/platform/service">See how the service desk enforces SLAs</a>
      — or <a href="/contact">book a contracts-review workshop</a>.
    </p>
  </>
);
