import React from 'react';

export const meta = {
  slug: 'gym-manager-metrics',
  title: 'The 5 metrics every gym manager should track (and why most don\'t)',
  excerpt: 'Revenue per member is table stakes. These five operational metrics are what separate a gym that scales from one that stalls at three sites.',
  publishedAt: '2026-02-08',
  readingMinutes: 6,
  author: 'Marcus T.',
  tags: ['Reporting', 'Operations', 'KPIs'],
  hero: '/brand/hero-dashboard.jpg',
};

export const body = (
  <>
    <p>
      Ask ten gym managers what they track daily and you&rsquo;ll hear nine
      of them say &ldquo;MRR and churn.&rdquo; Those matter — but they&rsquo;re
      lagging indicators. The metrics that actually predict whether your
      next site will be profitable live in operations, not finance. Here
      are the five we put front-and-centre on the GymAxis dashboard.
    </p>

    <h2>1. First-time fix rate (FTFR)</h2>
    <p>
      Of the service cases closed this week, what percentage were closed
      on the first engineer visit? If it&rsquo;s below 85% you&rsquo;re
      leaking engineer-hours and member trust. GymAxis tracks this per
      engineer, per equipment-type, and per site so you can see where the
      leak is.
    </p>

    <h2>2. SLA compliance %</h2>
    <p>
      Every service contract has SLA targets (response + resolve). Your
      compliance percentage tells you whether you can actually honour the
      contracts you sold. Below 95% and your renewals get awkward.
    </p>

    <h2>3. Equipment per engineer per day</h2>
    <p>
      Not cases — equipment. A good engineer closes 6-8 machines per
      day if they&rsquo;re routed intelligently and the right parts
      are in the van. Below 4 and your tie-break logic is bad or your
      van stock is bad. GymAxis scheduler scores both.
    </p>

    <h2>4. Parts-stock turnover</h2>
    <p>
      Stock sitting in your warehouse longer than 60 days is a working
      capital leak. The GymAxis inventory report surfaces slow-mover
      SKUs so you can return them to supplier or re-allocate to a site
      where the equipment model is more common.
    </p>

    <h2>5. Chargeable capture rate</h2>
    <p>
      Of the cases on out-of-contract equipment, what percentage
      actually resulted in an invoice? Most gyms lose 20-30% of
      chargeable revenue because the quote was drafted on paper and
      forgotten. The GymAxis auto-draft-to-Sage-outbox flow ties
      capture rate to 100% — the quote exists the moment the
      intake is saved.
    </p>

    <h2>Why most gyms don&rsquo;t track these</h2>
    <p>
      They&rsquo;re all operational. Finance tools can&rsquo;t see them;
      booking tools can&rsquo;t see them; spreadsheets can&rsquo;t pull
      them live. You need a platform that touches intake → dispatch →
      parts → sign-off → billing — which is exactly why we built one.
    </p>

    <p>
      Want the dashboard pre-configured for your brand?
      <a href="/pricing"> Start a trial</a> — it&rsquo;s all there on
      day 1.
    </p>
  </>
);
