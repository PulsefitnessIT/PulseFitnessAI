# PulseFitness.ai — Records of Processing Activities (RoPA) & Sub-Processor Register

**Controller:** Pulse Fitness Limited
**Owner:** Founder / DPO
**Prepared:** 2026-08-01 · **Review cadence:** quarterly and on any material change
**Legal framework:** UK GDPR / Data Protection Act 2018, Article 30 (records of processing)

> **Status:** WORKING DRAFT. Items marked **[CONFIRM]** require founder/DPO verification (contract terms, exact legal entities, retention specifics). Grounded in a code review of the live platform.

---

## 1. Records of Processing Activities (Art. 30)

| # | Processing activity | Data subjects | Personal data categories | Purpose | Lawful basis | Retention | Recipients / sub-processors |
|---|---|---|---|---|---|---|---|
| 1 | User accounts & authentication | Staff, customer users, engineers | Name, email, hashed password, role, MFA secret, login/audit metadata, IP | Provide access, security, audit | Contract (Art. 6(1)(b)); Legitimate interest (security) | Life of account; anonymised on erasure; audit trail retained | Emergent (hosting) |
| 2 | Organisation / site records | Customer orgs, MOD sites | Org name, addresses, contacts, site details | Deliver the service | Contract | Life of account + retention lifecycle (365-day archive→purge) | Emergent |
| 3 | Equipment & fault management | Customer/site staff | Machine details, serial numbers, fault descriptions, engineer notes | Service & maintenance workflow | Contract; Legitimate interest | Per retention lifecycle | Emergent |
| 4 | MOD service data | MOD site personnel | Site/asset data, service records, booking/gate-pass details | MOD service delivery | Contract | **[CONFIRM]** per MOD contract | Emergent; (Sicon/Sage 200 once live — **[CONFIRM]**) |
| 5 | Payments & subscriptions | Paying customers | Name, email, billing metadata, subscription/invoice records (**no raw card data** — handled by Stripe) | Billing, tax | Contract; Legal obligation (tax) | **Financial records retained ~6 years (HMRC)** — excluded from erasure | Stripe |
| 6 | Transactional & notification email | All users | Name, email, message content | Service comms, readiness/alerts | Contract; Legitimate interest | Per email provider logs | Resend |
| 7 | AI-assisted features (quote writer, matching, triage) | Users whose content is processed | Free-text that may contain personal data (fault notes, quote details) | AI assistance | Legitimate interest (with guardrails) | Prompt not persisted beyond request **[CONFIRM]** | LLM provider(s) via Emergent LLM key (OpenAI / Anthropic / Google) |
| 8 | Consent & compliance records | All users | Consent versions/timestamps, DSR requests, audit logs | Accountability | Legal obligation (Art. 5(2), 7, 30) | Retained as evidence | Emergent |
| 9 | Cookies / analytics | Website visitors | Cookie IDs, usage events | Product analytics | Consent | Per consent / provider | **[CONFIRM analytics provider — e.g. PostHog]** |

**Special-category / sensitive note:** The platform is not designed to process health or special-category data. MOD/defence context elevates confidentiality expectations — see data-residency confirmation (Gap #4). Avoid entering personal data into AI free-text where not necessary.

---

## 2. Sub-Processor Register (Art. 28)

| Sub-processor | Service | Data processed | Location / residency | DPA in place | Notes |
|---|---|---|---|---|---|
| **Emergent** | Managed cloud hosting (PaaS), database, compute | All platform data at rest/in transit | **[CONFIRM region — UK required for MOD]** | **[CONFIRM]** | Underlying infrastructure operator; see pen-test scope |
| **Stripe** | Payment processing | Billing identity, card data (held by Stripe, PCI-DSS), invoices | **[CONFIRM]** | Stripe DPA (standard) | No raw card data stored in PulseFitness.ai |
| **Resend** | Transactional email delivery | Recipient name/email, message content | **[CONFIRM]** | **[CONFIRM]** | Preview uses an invalid key (no live sends) |
| **LLM provider(s) via Emergent LLM key** — OpenAI / Anthropic / Google | AI text generation (quote writer, matching, triage) | Prompt content (may contain personal data) | **[CONFIRM]** | **[CONFIRM — via Emergent terms]** | Guardrails: prompt-injection sanitisation + output scrubbing (`ai_guardrails.py`) |
| **[CONFIRM: Analytics — e.g. PostHog / Cloudflare]** | Product analytics / edge | Usage events, cookie IDs, IP | **[CONFIRM]** | **[CONFIRM]** | Consent-gated via cookie banner |

**Action:** Ensure the customer-facing **Sub-Processors page** matches this register and links each provider's DPA. Notify customers of new/changed sub-processors per your DPA terms.

---

## 3. Data-subject rights coverage (implemented)

Access, Rectification, Erasure (anonymisation; financial records retained per Art. 17(3)(b)), Portability, Consent (versioned) — all live in `routes/compliance.py`. Objection/restriction of AI/marketing processing: **[CONFIRM process]**.

---

## 4. Outstanding confirmations for DPO

1. Emergent hosting **region / UK data residency** (critical for MOD) — get in writing.
2. Stripe / Resend / LLM-provider **DPAs** referenced and current.
3. LLM prompt **retention** by provider (persisted or not).
4. Analytics provider identity + consent handling.
5. MOD-contract-specific retention and handling obligations.

*This RoPA is a working record and must be kept current under Art. 30.*
