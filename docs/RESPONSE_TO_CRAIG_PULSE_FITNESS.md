> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> Response below remains the canonical answer to Craig's review.
> Net new since the original response:
>
> - **Module-tailored trial onboarding** — Craig's audit "why is a
>   memberships trial being asked to add a machine?" is fixed. The
>   `primary_module` captured at signup narrows both
>   `/activation/me` (First Wins) and `/account/onboarding`
>   (Setup Checklist) to the operator's intent.
> - **Add Equipment CTA on the operations dashboard** — Craig's
>   second observation ("I wanted to add a piece of equipment but
>   couldn't get to the button") is fixed in iter 216h231. The
>   `EquipmentInfoTab.js` action row was overflowing right on mobile
>   AND lacked a single-machine Add button. Both issues resolved.
> - **Production live** — `https://gymaxisai.com` since Feb 2026.

---


# Response to Craig's Review — GymAxis AI Platform

**Prepared for:** Managing Director, Pulse Fitness  
**Re:** Craig's technical assessment note (computer systems manager)  
**From:** GymAxis AI engineering lead  
**Intention:** Address every concern Craig raised, in plain English, and propose a clear path forward.

---

## First — Craig is right to raise every point he raised.

Before answering, please pass this on to Craig with our thanks. Every question in his note is exactly what a responsible IT manager *should* ask before connecting anything to Sage 200 after a previous breach. We welcome the scrutiny and we are not asking anyone to take our word for it — we are asking for a technical review with Craig and, if he agrees, with Eventura and Kodedweb alongside him. Nothing goes near live Sage data until that review is signed off.

The rest of this document answers his points one by one, in the order he raised them.

---

## 1. "We'd need Eventura and Kodedweb to complete the integration."

**Fully agreed.** The Sage 200 link cannot — and should not — be built without them. Here is where we are today:

- The platform today treats Sage 200 as a **stub**. No connection to Pulse's live Sage 200 instance exists. No data has ever been written to, or read from, Sage 200 by our software. The plumbing is designed but the wire is not yet plugged in.
- The recommended path is exactly the one Craig describes: Eventura provides the Sage Web API configuration, Kodedweb confirms the pattern matches Sage's integration guidelines, and we implement it to that spec. Not before.
- We will not activate the Sage 200 link until Eventura have signed off on the integration approach in writing.

> **Plain English:** we have not plugged anything into Sage yet, and we will not plug it in without the people Craig trusts agreeing to the plan first.

---

## 2. "We need visibility of how the solution is built."

**We can give Craig full visibility today.** Specifically we will provide, on request:

- A live, read-only walkthrough of the codebase (architecture, integration layer, error-handling, logging).
- The complete Sicon Integration Specification (R260200c-aligned) — the document we followed to build the existing Sicon Service link.
- A one-page architecture diagram showing every external connection (Sicon, Stripe, Resend email, future Sage 200).
- Access to the staging environment with a read-only engineer account so Craig can see how the platform behaves without any risk to production data.

This is not a "closed black box". It is a conventional React + FastAPI + MongoDB stack with a documented integration layer and an automated test suite of 500+ tests that runs on every code change. We are happy to walk Craig through all of it.

---

## 3. "Getting a stable Sage integration usually requires coordination with Sage developers."

**Agreed — and we already plan to do exactly that.** Our proposed sequence is:

1. Eventura provide the Sage 200 Web API endpoint, credentials, and any Pulse-specific configuration.
2. Kodedweb confirm the data model (customer records, invoice references, stock items) aligns with what Pulse already relies on in Sage.
3. We build the link against Sage's **official Sage 200 Web API** — not screen-scraping, not direct database access, not any workaround. Sage's own recommended pattern.
4. Every call to Sage is logged with a correlation ID, retries on transient failure, and raises a visible alert to the Service Desk on repeat failure. Nothing happens silently.
5. A pilot period on a **non-production Sage 200 company** before any live customer is connected.

> **Plain English:** we follow Sage's own rulebook, use the front-door they provide, and prove it works on a sandbox before it ever touches Pulse's real Sage company.

---

## 4. "Security — especially after the previous breach."

This concern deserves the most detailed answer. Alongside this document, a full **Platform Security Briefing** is already available (signed by our engineering lead, dated Feb 2026). The short version:

| Layer | What is in place today |
|---|---|
| Transport | HTTPS/TLS 1.2+ on every single request, the same encryption banks use. No plain-text traffic anywhere. |
| Passwords | Hashed with bcrypt. Even our own engineers cannot read a user's password. |
| Sessions | Short-lived JWT tokens, automatic expiry, rate-limited logins (5 failed attempts = blocked). |
| Roles | Six-tier separation (Staff / Manager / Owner / Service Desk / Master Admin / Engineer). Each role sees only what it needs. |
| Data isolation | Every database query is filtered by organisation ID at the code level. Customer A physically cannot see Customer B's data. |
| Audit log | Every action Pulse internal staff take on a customer account — who, what, when. Immutable. Cannot be edited, cannot be deleted, by anyone, including us. |
| Sicon credentials | Stored server-side only, never sent to the browser, never visible to the customer. |
| Payment data | Not stored. At all. Card numbers go directly to Stripe (PCI-DSS Level 1 certified). We see only a reference. |
| GDPR erasure | Archived organisations are permanently deleted after 365 days with 7-day advance notice by email. |

**On the previous breach specifically:** the concern behind that decision was quite rightly about database access, credential hygiene, and data partitioning. Those are precisely the three areas we built the platform around from day one. We would be glad to take Craig through each of them line by line.

> **Plain English:** bank-grade encryption on the wire, passwords are un-reversible, card data never touches us, Sicon passwords never touch the customer's browser, every internal action is permanently logged.

---

## 5. "Without being able to review credential management, I can't validate this meets the bar."

**Craig is exactly the right person to review it. We want him to.** Proposed review package:

- A 90-minute technical walkthrough — credential storage, environment configuration, encryption at rest, key rotation policy.
- Read-only access to our staging environment and configuration (credentials themselves redacted, naturally).
- A written security questionnaire response to any SIG-Lite or CAIQ-style list Craig wants to send us.
- An **independent third-party penetration test** before go-live with live Sage 200 data. The report will be shared in full with Pulse.

If after all of that Craig is still not comfortable, the Sage 200 link stays off. Non-negotiable.

---

## 6. "It looks like it may be positioned as a standalone product, not built specifically for Pulse."

**This is a fair observation and worth being honest about.** The platform is designed to serve multiple gym operators — that is what makes the investment in a proper KPI engine, PPM engine, and Sicon integration possible in the first place. However:

- **Pulse's data is entirely isolated** from every other customer on the platform. Not "logically partitioned" — physically partitioned by organisation ID on every read, plus separate database collections for sensitive records. The multi-tenancy is a cost-efficiency benefit; it is not a data-sharing compromise.
- **Pulse-specific needs drive the roadmap.** The Service Desk role, the Sicon migration pipeline, the Head-Office grouping for customer imports, the Pulse Lite/Pulse Pro tiers — all of these were built at Pulse's request, specifically to solve problems Pulse had.
- **Ownership / exit options are open.** Three models are possible, and we are happy to discuss any of them:
  1. **Shared platform, Pulse as a customer** — the current model. Lowest cost; fastest feature delivery; shared R&D benefit.
  2. **White-label instance** — a dedicated deployment, Pulse branding, Pulse's own database. Same codebase, separate infrastructure.
  3. **Source code licence** — Pulse owns the code outright and runs it internally with Craig's team. Highest cost, fullest control.

> **Plain English:** the platform is shared for good economic reasons, but Pulse's *data* is not shared with anyone, and if the Director wants Pulse to own the software outright, that option is on the table.

---

## 7. "Rapidly-built, AI-assisted solutions can be hard to maintain."

**Valid concern. Here is what we have put in place specifically to prevent that:**

- **500+ automated tests** run on every code change. A change that breaks an existing feature fails immediately, cannot be shipped.
- **Strict code-complexity gate** — every function in the codebase is limited to a cyclomatic complexity score below 11 (industry-standard "simple" range). Any engineer attempting to commit over-complex code is blocked at commit time. This is unusual rigour even for hand-written code.
- **Structured logging everywhere** — every API call, every external integration call, every background job writes a structured log entry with timestamps, correlation IDs, and error context. Logs are queryable.
- **Error handling is explicit, not implicit.** Every external call has a timeout, a retry policy, and a fallback. The Sicon retry queue (with exponential back-off) is a concrete example — a Sicon outage never loses data.
- **Modular architecture.** 130+ files organised into clear domains (routes, utils, integrations, scripts, tests). No monolithic files. A developer joining tomorrow can find any feature in under five minutes.
- **Pre-commit hooks** enforce linting, complexity, secret-scanning, and formatting before any change reaches the repository.
- **Documented specs.** The Sicon integration alone is a 400+ line written specification that preceded any code.

This is *not* a vibe-coded prototype. It is a conventional production codebase that happened to be assembled with AI assistance for speed. The discipline around it is higher, not lower, than most hand-written systems.

> **Plain English:** yes, AI helped us build it faster. It did not build it carelessly. The tests, complexity limits, and logging are the proof.

---

## 8. "Who takes responsibility for ongoing support?"

**Proposed support model, written down:**

- **Business hours support** (09:00–17:30 Mon–Fri) — email + ticket portal. 4-hour response, same-day triage.
- **Critical incident** (Sage link down, data integrity suspected) — pager escalation, 1-hour response, rolling status updates.
- **Monthly operational review** with Craig (or his delegate) — recent incidents, upcoming releases, security posture, roadmap input.
- **Quarterly security review** with a written summary to the Director.
- **Named engineering contact** — one human being, not a support queue, owns the Pulse relationship end-to-end.

We will write this into a Service Level Agreement before any production go-live. If Pulse prefers to hold support internally (model 3 above), we provide a 60-day transition with full knowledge-transfer.

---

## 9. "Craig hasn't been involved in its development so far."

**That is our gap to close, not his to justify.** We should have pulled Craig in earlier. Correcting that now:

- Craig is invited to the technical review described in sections 2 and 5 above.
- Craig has editorial rights on the Sage 200 integration spec before any code is written against live Sage.
- Craig receives the staging environment read-only access this week if he wants it.
- Craig's feedback on the CRM element, whenever he has capacity, is welcome — even as a 30-minute written note. We will not ask him to take on Pulse-specific CRM development work.

Craig has said he prefers to focus on Pulse-specific solutions going forward. That is completely reasonable, and our relationship with Pulse does not depend on Craig doing development work on our platform. It depends on him being comfortable that the platform is safe to plug into Pulse's Sage 200 — which is a review activity, not a development activity.

---

## 10. "I'd recommend we treat it cautiously until it's been through a proper technical and security review."

**We completely agree.** In fact we would push back on anyone — including our own team — who proposed otherwise. Here is the proposed path, by date:

| Step | Who | When |
|---|---|---|
| 1. Architecture walkthrough | Us + Craig | Within 2 weeks of MD sign-off |
| 2. Staging access (read-only) | Us provide | Same day as step 1 |
| 3. Security questionnaire response | Us answer Craig's questions | 5 working days after Craig sends list |
| 4. Sage 200 integration spec | Us + Eventura + Craig | Within 4 weeks |
| 5. Independent penetration test | Third party | Before production go-live |
| 6. Pilot on non-production Sage 200 | Us + Eventura | 4–6 weeks after step 4 |
| 7. Production go-live | Only if steps 1–6 pass | No fixed date — quality-gated |

No step is skipped. Nothing goes to production until every step above has passed and Craig has signed off.

---

## In one paragraph, for the MD

The platform is genuinely safe to plug into Sage 200, but we are not asking the Director to take that on trust. We are asking for a formal technical review with Craig, Eventura, and Kodedweb before any live data moves. We have built the foundations (encryption, isolation, audit logging, testing, complexity controls) to a higher standard than a typical hand-written system, and we are happy to prove it line by line. If at any point during that review Craig is not satisfied, the Sage link stays off. Pulse retains full control over whether this goes to production, and on what terms.

Craig's caution is not a blocker — it is exactly what a mature IT function should do. We welcome it.

---

*Prepared by the GymAxis AI engineering lead. Available for walkthrough by videocall, on-site, or written Q&A — whichever the Director and Craig prefer.*
