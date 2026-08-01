# PulseFitness.ai — Compliance Gap Register

**Owner:** Founder / DPO
**Prepared:** 2026-08-01
**Scope:** PulseFitness.ai SaaS platform (multi-tenant CRM + MOD service portal), hosted on Emergent managed cloud (PaaS). UK GDPR / DPA 2018, with elevated expectations for MOD/defence customer data.
**Basis:** Founder-level review grounded in a code walkthrough (auth, tenant isolation, data-subject rights, retention, security headers, AI guardrails, legal pages).

---

## 1. Summary

The platform's compliance foundations are **strong and genuinely implemented** (not decorative): full data-subject rights, versioned consent, retention lifecycle, MFA, encryption of secrets at rest, security headers, AI guardrails, and a full legal-pages set. The items below are **hardening and governance gaps**, not missing foundations. P0 code items have been actioned; P1/P2 require founder/DPO decisions or scoped work.

---

## 2. Controls already in place (verified in code)

| Area | Control | Evidence |
|---|---|---|
| Right of access | `GET /api/compliance/my-data` | `routes/compliance.py` |
| Portability | `GET /api/compliance/my-data/download` | `routes/compliance.py` |
| Right to erasure | `POST /api/compliance/delete-account` (anonymisation, preserves audit integrity) | `routes/compliance.py` |
| Consent records | Versioned Terms/Privacy consent (`/consent`, `/consent/status`) | `routes/compliance.py` |
| Retention lifecycle | Archive → 7-day warning → purge at 365 days + daily PII job | `archive_lifecycle.py`, sicon poller |
| Authentication | bcrypt hashing, JWT with revocation deny-list (TTL), refresh tokens | `utils/auth.py`, `utils/security_plus.py` |
| MFA / 2FA | TOTP; mandatory for master-admin & MOD HQ tiers | `utils/mfa.py` |
| Secrets at rest | Fernet-encrypted secret vault | `utils/secret_vault.py` |
| Web security | CSP, HSTS (preload), X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy | `server.py`, `frontend/public/_headers` |
| AI safety | Prompt-injection sanitisation + output scrubbing (OWASP LLM01/02) | `utils/ai_guardrails.py` |
| Tenant isolation | Org-scoped queries; MOD Quote Writer restricted to operator org | `routes/*`, hardened 2026-07-31 |
| Legal pages | Privacy, Terms, DPA, DPIA, SLA, Sub-Processors, cookie consent | `frontend/src/pages/legal/*` |

---

## 3. Gap register

Legend — **Status:** ✅ Done · 🟡 Open · 🔵 In progress. **Priority:** P0 (pre-pen-test) · P1 (governance) · P2 (maturity).

| # | Priority | Gap | Risk if unaddressed | Recommended action | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | P0 | Password policy too weak (min 8, no symbol/breach check) | Account takeover; pen-test finding | Raised to 12 chars + upper/lower/digit/symbol + common-password blocklist + **live HIBP breach check** (fail-open) | Eng | ✅ Done 2026-08-01 |
| 2 | P0 | MFA only mandatory for master-admin | Privileged-account compromise | Role-based enforcement via `MFA_REQUIRED_ROLES` env (built; **flip on in prod** after briefing staff) | Founder | 🟡 Ready — enable in prod |
| 3 | P0 | CSP `script-src 'unsafe-inline'` | Weakens XSS defence | Prod CSP already excludes `unsafe-eval`; removing `unsafe-inline` needs nonce/hash injection = **scoped project** (CRA static limitation) | Eng | 🟡 Scoped separately |
| 4 | P1 | **Data residency unconfirmed** | MOD contracts likely require UK-only data sovereignty | Confirm hosting region with Emergent in writing; document in DPA & pen-test scope | Founder/DPO | 🟡 Open |
| 5 | P1 | Erasure vs statutory financial retention | Deleting invoice/tax data breaches HMRC 6-yr retention | Org hard-delete now **excludes** financial collections (invoices, payments, stripe_charges, payment_transactions, purchase_orders, po_defaults, revenue_distributions, reserve_transactions); retained under Art.17(3)(b) + logged | DPO/Eng | ✅ Done 2026-08-01 |
| 6 | P1 | Sub-processor list completeness | Undisclosed processors = GDPR Art. 28 gap | Confirm Sub-Processors page lists **Emergent (hosting), Stripe (payments), Resend (email), and LLM providers (OpenAI/Anthropic/Google via Emergent)** with DPAs referenced; note AI processing of PII | DPO | 🟡 Open |
| 7 | P1 | AI processing of personal data | Special-category/defence data sent to LLMs without record | Confirm guardrails redact PII before prompts where applicable; add LLM processing to RoPA & DPIA | DPO/Eng | 🟡 Open |
| 8 | P2 | Breach-notification runbook | Miss 72-hour GDPR notification deadline | Document an incident-response runbook (detect → assess → notify ICO within 72h → notify subjects) | DPO | 🟡 Open |
| 9 | P2 | Backup / DR RPO/RTO undocumented | Unclear recovery guarantees | Obtain Mongo backup cadence & restore RPO/RTO from Emergent; document | Founder | 🟡 Open |
| 10 | P2 | Consent version bump process | Stale consent when policies change | Process to increment `CURRENT_TERMS_VERSION`/`CURRENT_PRIVACY_VERSION` and force re-consent | Eng/DPO | 🟡 Open |
| 11 | P2 | Tenant-isolation regression guard | Future feature reintroduces a cross-org leak | Standing tenant-isolation test suite added (`tests/test_tenant_isolation_regression_jan2026.py`, 6 checks); wire into CI | Eng | ✅ Done 2026-08-01 |
| 12 | P2 | Frontend password-hint copy | Minor UX inconsistency (fixed) | Signup/reset hints updated to "12 characters" | Eng | ✅ Done 2026-08-01 |
| 13 | 🔵 | Independent penetration test | External assurance | Stripe OLT pen test being scoped (scoping doc prepared) | Founder | 🔵 In progress |

---

## 4. Data-subject rights (DSR) status — GDPR Ch. III

| Right | Article | Implemented | Notes |
|---|---|---|---|
| Access | 15 | ✅ | `/compliance/my-data` |
| Rectification | 16 | ✅ | Profile/account editing |
| Erasure | 17 | ✅ | Anonymisation; **reconcile with financial retention (Gap #5)** |
| Portability | 20 | ✅ | `/compliance/my-data/download` |
| Consent | 7 | ✅ | Versioned; **add re-consent trigger (Gap #10)** |
| Objection/Restriction | 18/21 | 🟡 | Confirm process for marketing/AI processing objections |

---

## 5. Recommended next actions (priority order)

1. **Enable role-based MFA in production** — set `MFA_REQUIRED_ROLES=admin,logistics` after briefing those users (Gap #2).
2. **Confirm & document data residency** with Emergent (UK sovereignty for MOD) (Gap #4).
3. **Reconcile erasure with 6-year financial retention** and document the boundary (Gap #5).
4. **Complete the Sub-Processors register + RoPA**, including LLM providers (Gaps #6, #7).
5. **Write the 72-hour breach runbook and capture backup RPO/RTO** (Gaps #8, #9).
6. **Complete the independent pen test** and remediate findings (Gap #13).
7. **Add a CI tenant-isolation test** and schedule the CSP nonce project (Gaps #11, #3).

---

*This register is a working document. Review quarterly and after any material feature, processor, or hosting change.*
