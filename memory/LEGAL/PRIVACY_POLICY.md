# GymAxis — Privacy Policy

> **Status:** TEMPLATE — must be reviewed by a UK-qualified solicitor before publishing on the marketing site.
> **Effective date:** `<go-live date>`
> **Version:** 2.0 (supersedes the previous policy)
> **Reflecting:** Art. 17 erasure workflow (Iter 220ao, May 27 2026)

This Privacy Policy describes how **`<your company legal name>`** ("**GymAxis**", "**we**", "**us**") collects, uses and protects personal data when you visit our website, request a demo, sign up to a trial, or use the GymAxis platform as an end customer.

If you are a **gym operator** using GymAxis to manage your own customers, please refer to the [Data Processing Agreement](DATA_PROCESSING_AGREEMENT.md) which governs that relationship.

---

## 1 · Who we are

We are the **controller** of the personal data we collect through `gymaxisai.com` and our public marketing surfaces.

- **Registered office:** `<your registered address>`
- **Company number:** `<>`
- **Data Protection Officer:** `dpo@gymaxisai.com`
- **ICO registration number:** `<>` *(if applicable)*

---

## 2 · What we collect, and why

| Category | Examples | Lawful basis (UK GDPR Art. 6) |
|---|---|---|
| Account data | Name, email, password (hashed), workspace name | Contract performance |
| Billing data | Company name, billing address, VAT number, last 4 digits of card | Contract performance + legal obligation (HMRC records) |
| Usage telemetry | Pages visited, features used, errors encountered | Legitimate interest (improving the Service); Sentry has `send_default_pii=False` |
| Marketing | Demo-request submissions, newsletter sign-ups, opt-in state | Consent (Art. 6(1)(a)) for sales emails; PECR for electronic marketing |
| Cookies | Session token, CSRF token, analytics ID (if you accept analytics) | Strictly necessary OR consent (see §4) |

We do **not** intentionally collect special-category data through our marketing site.

---

## 3 · Where we get it from

- Directly from you (when you fill in a form, sign in, or message us).
- From our infrastructure (server logs, Sentry crash reports).
- Occasionally from sales tools (LinkedIn Sales Navigator, etc. — under their respective DPAs).

---

## 4 · Cookies

We use the following cookie classes:

| Class | Purpose | Consent required? |
|---|---|---|
| Strictly necessary | Auth session, CSRF | No |
| Functional | Theme preference, recently-viewed pages | No (legitimate interest) |
| Analytics | PostHog *(planned — anonymous events only)* | Yes |
| Marketing | None at present | n/a |

Our cookie banner offers granular consent on first visit. You can change it any time via `Privacy → Cookie preferences` in the footer.

---

## 5 · Who we share it with

We share Personal Data with the sub-processors listed in [SUB_PROCESSORS.md](SUB_PROCESSORS.md). The most important ones for marketing-site visitors are:

- **Emergent Labs** — hosting.
- **Resend** — sending the demo-request confirmation + sales follow-up emails.
- **Sentry** *(when enabled)* — error monitoring.

We do **not** sell Personal Data to third parties.

We may disclose Personal Data if required by law (court order, regulatory request), to protect our rights or property, or in connection with a merger, acquisition or corporate reorganisation (subject to the new entity assuming this Policy).

---

## 6 · International transfers

Some of our sub-processors are based outside the UK / EEA (notably OpenAI, Anthropic). These transfers are protected by the **UK International Data Transfer Addendum (IDTA)** or **Standard Contractual Clauses (SCCs)**, plus supplementary measures (encryption in transit, the providers' "no training on API data" assurance).

---

## 7 · How long we keep it

| Data | Retention |
|---|---|
| Account data (active customer) | Duration of subscription + 60 days |
| Account data (cancelled, no balance) | 30 days then deleted, except invoices kept 6 years (HMRC) |
| Demo-request leads | 24 months from last interaction |
| Newsletter list | Until you unsubscribe |
| Server logs | 30 days |
| Sentry crash reports | 90 days |
| Audit / login events | At least 12 months for security investigations |

If you ask us to delete your data, we will do so within 30 days, except where retention is required by law.

---

## 8 · Your rights

Under UK GDPR you have the right to:

- **Access** the personal data we hold about you (Art. 15).
- **Rectify** inaccurate data (Art. 16).
- **Erase** your data ("right to be forgotten") (Art. 17). We operationalise this through our [GDPR Erasure workflow](../OPS_RUNBOOK.md#46-gdpr-article-17-erasure-request) — a 30-day cooling-off window applies unless you explicitly request immediate action.
- **Restrict** our processing (Art. 18).
- **Port** your data to another provider (Art. 20).
- **Object** to processing based on legitimate interest, including direct marketing (Art. 21).
- **Not be subject** to a decision based solely on automated processing (Art. 22) — we currently do not make any decisions about you in this way.
- **Withdraw consent** at any time, where consent is the lawful basis.

To exercise any right, email **`dpo@gymaxisai.com`** with the subject "Data subject request". We will respond within 1 calendar month. We may need to verify your identity before acting.

You also have the right to **lodge a complaint** with the Information Commissioner's Office (`https://ico.org.uk/make-a-complaint/`). We'd rather you came to us first, but it's your right.

---

## 9 · Security

We protect Personal Data with the Technical & Organisational Measures set out in Annex A of our [DPA](DATA_PROCESSING_AGREEMENT.md), including encryption in transit, bcrypt password hashing, JWT auth, RBAC, audit logs, automated regression testing, and (planned) external penetration testing.

No system is 100% secure. If we suffer a personal-data breach affecting your data, we will notify the ICO within 72 hours where required, and you directly if the breach is likely to result in a high risk to your rights and freedoms.

---

## 10 · Children

The Service is for **business use** by gym operators and their staff. We do not knowingly collect data from children under 13 through our marketing site. Gym operators using the platform are responsible for any obligations triggered by their own member base including children (e.g. parental consent for junior gym sign-ups).

---

## 11 · Changes to this policy

We will update this Policy as our processing evolves. Material changes will be flagged on the website **at least 14 days** before they take effect; you may be asked to re-consent where appropriate.

---

## 12 · Contact

- **Privacy / DPO:** `dpo@gymaxisai.com`
- **Security:** `security@gymaxisai.com`
- **General:** `hello@gymaxisai.com`
- **ICO:** `casework@ico.org.uk` · `0303 123 1113`

---

*Template last updated Iter 220ap (May 27, 2026). Have a UK-qualified solicitor amend before publishing.*
