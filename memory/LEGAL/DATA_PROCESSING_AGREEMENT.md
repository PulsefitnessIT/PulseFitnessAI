# GymAxis — Data Processing Agreement (DPA)

> **Status:** TEMPLATE — must be reviewed by a UK-qualified data-protection solicitor before binding any customer.
> **Effective date:** `<go-live date>`
> **Version:** 1.0
> **Governing law:** UK GDPR + Data Protection Act 2018

This Data Processing Agreement ("**DPA**") forms part of the [GymAxis Terms of Service](TERMS_OF_SERVICE.md) and applies whenever GymAxis processes Personal Data on behalf of the Customer in providing the Service.

In the event of conflict between the Terms and this DPA on data-protection topics, **this DPA prevails**.

---

## 1 · Definitions

Capitalised terms not defined here have the meaning given in the UK GDPR.

- **"Customer Personal Data"** — Personal Data relating to data subjects (typically gym members, instructors, CRM contacts, end customers of the Customer) that the Customer or its authorised users upload to or process through the Service.
- **"Processor"** — `<your company legal name>` (a.k.a. "Provider", "we", "us").
- **"Controller"** — the Customer entity identified on the Order Form.
- **"Sub-processor"** — any third party engaged by the Processor to process Customer Personal Data. See [SUB_PROCESSORS.md](SUB_PROCESSORS.md).
- **"Affiliate"** — any entity controlling, controlled by, or under common control with a party.

---

## 2 · Roles & subject-matter

2.1 The Customer is the **Controller**. The Provider is the **Processor**.

2.2 **Subject-matter of processing:** provision of the Service to the Controller.

2.3 **Duration:** for the term of the Terms + 60 days for data return / deletion.

2.4 **Nature & purpose:** hosting, storing, transmitting, querying and analysing Customer Personal Data so the Controller can operate its gym / fitness business.

2.5 **Types of Personal Data** (typical, non-exhaustive):
- Identification (name, email, phone, DOB, address, postcode)
- Membership & financial (member number, payment status, invoice line items, last 4 card digits)
- Operational (class attendance, booking history, instructor certifications, DBS expiry)
- Marketing (consent state, email open/click history)
- Health and biometric data **may** be processed (e.g. fitness goals, medical conditions, BMI). Customer is responsible for ensuring a lawful basis under Art. 9 UK GDPR.

2.6 **Categories of data subject:**
- The Controller's members, prospective members, instructors, contacts, leads and end customers.
- The Controller's own staff (operator users of the Service).

---

## 3 · Processor obligations

The Processor will:

3.1 **Process Customer Personal Data only on documented instructions from the Controller** — the Terms, this DPA, signed Order Forms, and use of the Service's UI / API are all "documented instructions". The Processor will notify the Controller if an instruction would, in its opinion, infringe UK GDPR or other data-protection law, and may refuse to act on it.

3.2 **Confidentiality** — ensure that persons authorised to process Customer Personal Data are bound by written confidentiality obligations or are under statutory confidentiality duties.

3.3 **Security** — implement the technical and organisational measures (TOMs) set out in **Annex A** below.

3.4 **Sub-processors** — only engage sub-processors listed in `SUB_PROCESSORS.md` or notified to the Controller per §4 below. Each sub-processor is bound by a written contract imposing data-protection obligations no less protective than this DPA.

3.5 **International transfers** — where Customer Personal Data is transferred outside the UK / EEA, the transfer is protected by Standard Contractual Clauses (SCCs), the UK International Data Transfer Addendum (IDTA), or an Adequacy Regulation, as applicable.

3.6 **Data subject rights** — provide the Controller with the tools needed to fulfil data-subject rights:
- **Access (Art. 15)** — Master Admin Database Viewer + (planned) `/api/gdpr/sar/export` endpoint.
- **Rectification (Art. 16)** — the Service UI allows the Controller to edit any record.
- **Erasure (Art. 17)** — the GDPR Erasure workflow in Master Admin and CRM Settings (see `OPS_RUNBOOK.md` § 4.6).
- **Restriction (Art. 18)** — Archive flag on the relevant record.
- **Portability (Art. 20)** — CSV/JSON export in each module.
- **Objection (Art. 21)** — opt-out helpers in the Marketing module.

3.7 **Personal data breach** — notify the Controller without undue delay and **within 72 hours** of becoming aware of a breach affecting their Customer Personal Data, providing as much detail as is then reasonably available, and continue providing updates as the investigation progresses.

3.8 **Assistance** — assist the Controller (at the Controller's cost beyond what is reasonably included in the Service) with:
- DPIAs (Art. 35);
- prior consultation with the ICO (Art. 36);
- security obligations (Art. 32);
- responding to data subjects (Art. 12–22).

3.9 **Deletion / return** — on termination or at the Controller's written request, the Processor will delete or return all Customer Personal Data within **60 days**, except where retention is required by law (e.g. HMRC 6-year invoice records).

3.10 **Audit** — make available all information necessary to demonstrate compliance, and allow for audits, including inspections, conducted by the Controller or its mandated auditor, **once per 12-month period**, on **30 days' written notice**, at the Controller's expense, during normal business hours, and subject to reasonable confidentiality undertakings. Where a recent third-party audit (e.g. SOC 2, ISO 27001, pen-test report) is available, the Processor may provide that in lieu of an in-person audit.

---

## 4 · Sub-processors

4.1 The Controller authorises the Processor to engage the sub-processors listed in [`SUB_PROCESSORS.md`](SUB_PROCESSORS.md) as at the Effective Date.

4.2 The Processor will provide at least **30 days' written notice** before adding, replacing, or materially changing a sub-processor.

4.3 The Controller may object in writing within the notice period. The parties will work in good faith to address the objection. If it cannot be resolved within a further 30 days, the Controller may terminate the affected workload without penalty.

4.4 The Processor remains liable to the Controller for the acts and omissions of its sub-processors as if those acts or omissions were its own.

---

## 5 · Liability

Each party's liability under this DPA is subject to the limitations set out in §9 of the Terms.

---

## 6 · Term & survival

6.1 This DPA takes effect on the Effective Date and continues for the term of the Terms.

6.2 §§3.7, 3.9 and 3.10 survive termination as required by law.

---

## 7 · Governing law

This DPA is governed by **English law** and subject to the exclusive jurisdiction of the courts of **England & Wales**.

---

## Annex A — Technical & Organisational Measures (TOMs)

> Aligned with UK GDPR Art. 32 and the ICO's Accountability Framework. Annex sections below describe the controls **in place today**; flagged items are planned and dated.

### A.1 Pseudonymisation & encryption

- TLS 1.2+ enforced for all client → server traffic.
- MongoDB-at-rest encryption (managed by Emergent Labs).
- Passwords stored using **bcrypt** with per-user salt.
- Email addresses anonymised on GDPR erasure (`erased+{sha8}@gdpr.local`).
- JWT secrets stored only in environment variables, never committed.
- Sentry SDK initialised with `send_default_pii=False`.

### A.2 Confidentiality, integrity, availability and resilience

- Single sign-on per tenant; role-based access control with Master Admin / Operator / Engineer / Member tiers.
- All API endpoints behind authentication except documented public surfaces (`/api/public/demo-request`, marketing pages, public widget iframes).
- 53 compound MongoDB indexes for query performance.
- Sliding-window rate limiter on LLM and authentication endpoints.
- Pluggable feature flags so blast radius can be contained per tenant.
- Backups + restore covered by `EMERGENT_OPS_EMAIL.md` request — **RTO ≤ 4 hr, RPO ≤ 1 hr** target.

### A.3 Ability to restore availability and access

- Automated container restart via Kubernetes supervisor.
- Hot-reload deploy via Emergent platform.
- One-click rollback to previous known-good checkpoint.
- Disaster-recovery drill: **annually** (next: <date>).

### A.4 Testing and assessment

- 1,100+ pytest regression suite, run on every commit.
- ESLint `--max-warnings 0`, Ruff, Bandit, Xenon, pip-audit clean.
- Penetration test scheduled **<date>** with **<vendor>** *(see roadmap)*.

### A.5 Access control

- Master Admin actions logged in `db.audit_log_entries` with actor, timestamp, action, before/after.
- All operator actions on tenant data logged in `db.crm2_audit_log`.
- Failed login events captured in `db.login_events` for ≥ 90 days.
- Two-factor authentication (TOTP) available; mandatory for Master Admin (planned, target <date>).

### A.6 Data minimisation

- PII fields explicitly catalogued in `_SUBJECT_SPEC` in `routes/gdpr_erasure.py`.
- GDPR-erased rows are **excluded from operator list endpoints** while retaining row identity for financial / legal records (Art. 17(3)(b)).
- LLM prompts include only the fields needed to perform the task; AI providers asserted to not train on API data.

### A.7 Personnel

- All personnel processing Customer Personal Data are bound by written confidentiality obligations.
- Founder / on-call engineer cleared by reference check.
- *(Planned)* mandatory annual data-protection training.

### A.8 Incident response

- See `OPS_RUNBOOK.md` § 4.5 (cross-tenant data leak) and § 6.4 (personal-data breach template).
- 72-hour notification commitment per §3.7 of this DPA.

---

## Annex B — Sub-processors

See [SUB_PROCESSORS.md](SUB_PROCESSORS.md), which is incorporated into this DPA by reference and may be updated per §4.

---

## Annex C — Notices

- **Provider DPO / contact:** `dpo@gymaxisai.com` · `Craig Henshall` · phone available on request
- **ICO** (regulator): `casework@ico.org.uk` · `0303 123 1113`

---

*Template last updated Iter 220ap (May 27, 2026). Have a UK-qualified data-protection solicitor amend before binding any customer.*
