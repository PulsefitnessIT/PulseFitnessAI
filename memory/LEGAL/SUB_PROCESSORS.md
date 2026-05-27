# Sub-processors

> **Effective date:** May 27, 2026 — Version 1.0
>
> **Notice obligation:** GymAxis will provide customers at least **30 days' notice** before adding, replacing, or materially changing a sub-processor. Customers may object in writing; if the objection cannot be resolved within 30 days the customer may terminate the affected workload without penalty.

This page lists every third-party processor that may handle Customer Personal Data under GymAxis's [Data Processing Agreement](DATA_PROCESSING_AGREEMENT.md).

---

## 1 · Infrastructure & hosting

| Sub-processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| **Emergent Labs** | Platform hosting (compute, container orchestration, network ingress) | All Customer Data at rest + in transit | UK / EU (confirm with Emergent Ops — see `EMERGENT_OPS_EMAIL.md`) | UK GDPR / EU SCCs (if any non-UK/EEA) |
| **MongoDB** *(via Emergent-managed cluster)* | Primary application database | All Customer Data at rest | UK / EU (confirm) | Sub-processor of Emergent Labs |

---

## 2 · Communications

| Sub-processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| **Resend** | Transactional + marketing email delivery (password resets, receipts, campaign emails) | Recipient name, email, subject line, message body | US-based, EU-Frankfurt option available | SCCs · UK IDTA |
| **Twilio** *(planned, currently MOCKED)* | SMS dispatch | Recipient phone number, message body | US | SCCs · UK IDTA |

---

## 3 · Payments

| Sub-processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| **Stripe Payments Europe Ltd / Stripe Inc.** | Card processing, subscription billing, Stripe Connect for engineer payouts | Cardholder name + last 4 digits, billing address, transaction amount + currency | UK / Ireland / US | SCCs · UK IDTA · Stripe's standard DPA |

---

## 4 · AI / LLM providers

GymAxis uses Large Language Models for the **AI Assistant**, **SEO Autopilot article generation**, **Tender drafting**, and **CRM insights**. Provider selection happens via the Emergent LLM Key proxy.

| Sub-processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| **OpenAI** | Text generation (GPT-4o, GPT-5.2), image generation (GPT Image 1), Whisper STT | Customer-authored prompts + any data the operator includes in them | US | SCCs · OpenAI standard DPA · "no training on API data" assurance |
| **Anthropic** | Text generation (Claude Sonnet 4.5) | Same as above | US / EU | SCCs · Anthropic standard DPA |
| **Google (Gemini)** | Text generation, image generation (Nano Banana) | Same as above | US / EU | SCCs · Google standard DPA |

> **Operator obligation:** Do not paste raw special-category data (health, biometric, criminal) into AI prompts. Use the redact-before-prompt pattern documented in the Help Centre.

---

## 5 · Observability & analytics

| Sub-processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| **Sentry** *(enabled when `SENTRY_DSN` is set)* | Server + client error tracking | Stack traces, URL, user-agent, **no PII** (`send_default_pii=False`) | US / EU options | SCCs · UK IDTA |
| **PostHog** *(planned)* | Product analytics | Anonymous event metadata, page views, feature usage | EU-Frankfurt option | SCCs |

---

## 6 · Integrations enabled per-tenant (NOT default)

These sub-processors only receive data if the customer **explicitly enables** the integration in their workspace:

| Sub-processor | Triggered by | Data categories |
|---|---|---|
| **Microsoft (Outlook Calendar)** | Tenant connects Microsoft 365 account | Calendar events, meeting attendees |
| **DocuSign** | Tenant sends a CRM quote for signature | Recipient name + email, document content |
| **Sage 200** | Tenant maps Sage company in `/master-admin/integrations` | Invoice + customer ledger data |
| **Sicon (Service Manager)** | Tenant connects Sicon credentials | Equipment service history |
| **Google Calendar** *(if used via Emergent Auth)* | Tenant connects Google account | Calendar events |
| **Meta (Instagram Graph API)** *(planned)* | Tenant connects IG Business account | Post content + media |

---

## 7 · Audit & legal

GymAxis itself acts as **data processor** when handling Customer Personal Data on behalf of a Tenant. Where Tenant Personal Data ends up in our **paid sub-processors above**, we have a written DPA in place with each.

A list of executed DPAs is available on request: `dpo@<your-domain>.com`.

---

## 8 · Changes to this list

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-27 | Initial publication |

To subscribe to sub-processor change notifications, email `dpo@<your-domain>.com` with the subject "subscribe sub-processor".

---

*This document is provided as a template. Have your legal counsel and DPO review before publishing. Country / region values and effective dates must be verified against the actual contracts in force.*
