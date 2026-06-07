# GymAxisAI — Build Value & Replacement Cost

*One-page estimate of what it would cost to build the GymAxisAI platform from scratch with a human team. Prepared June 2026.*

> This is a **build/replacement cost** estimate (what an agency or team would charge to recreate the platform as it exists today). For ongoing **monthly running cost** (hosting, email, AI, Stripe fees), see [`/app/memory/COST_BREAKDOWN.md`](../memory/COST_BREAKDOWN.md).

---

## What GymAxisAI actually is

Not a website — a **multi-tenant enterprise SaaS product** spanning:

- **CRM** — sales pipeline, companies/contacts, quotes/CPQ, price lists, territories, role-based permissions
- **Operations** — equipment register, fault logging, check sheets, asset health scoring
- **Memberships** — members, classes & timetable, plans, billing, member app
- **Marketing** — email campaigns, A/B testing, journeys, audiences, AI-generated content
- **Service Ops (supplier side)** — engineer mobile app, service desk, van stock, parts catalogue, job invoicing
- **Platform** — multi-tenant data isolation, auth & permissions, Stripe payments, AI integrations, MOD/white-label portals, audit & security tooling

A simple "gym website" costs £3k–£15k. **This is roughly 50–100× that.**

---

## Replacement cost (build to today's state)

| Approach | Timeline | Cost (GBP) |
|---|---|---|
| Freelance web designer | ❌ Not feasible — wrong skillset | — |
| Solo senior full-stack developer | 3–5+ years | £250k–£500k (opportunity cost) |
| Small agency / team (3–5 people) | 18–30 months | **£600k–£1.5M+** |
| Full London product team (PM, 3–4 devs, designer, QA) | 2–3 years | **£1.5M–£3M+** |

**Realistic agency replacement cost today: £700k–£2M+, delivered over 2–3 years with a team.**

---

## Why the cost is what it is

- The expensive part isn't the visible screens — it's the **invisible engineering**: multi-tenant data isolation, authentication & permissions, payment flows, third-party integrations, edge cases, and keeping eight interconnected modules working as the product changes.
- Documentation, testing, security hardening and CI/CD are a large slice of real-world cost and are already in place here.

## Ongoing team cost (if maintained by an agency)

A team capable of maintaining and extending a platform of this size typically runs **£15k–£40k / month**.

---

## Bottom line

To commission what exists today from an agency, you would realistically be **£700k–£2M+ deep over 2–3 years** — plus ongoing maintenance. The biggest saving achieved here is on the heavy backend architecture and engineering work, which is the genuinely expensive part of any platform like this.

*Figures are indicative UK market estimates for justifying pricing, partnerships and investment conversations — not a formal valuation.*
