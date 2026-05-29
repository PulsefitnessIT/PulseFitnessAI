# GymAxis / Pulse Fitness — Residual-Risk Summary

> **Iter 220bf · May 28, 2026 · v1.0**
>
> **Audience:** External pen-test vendor + board / procurement review.
> **Purpose:** Single-page snapshot of where we stand on risk the day
> before the external engagement begins.

---

## Headline

* **All 33** risk-register findings (F-01 – F-33) are **closed** and
  regression-tested. See `RISK_REGISTER.md` for the per-finding
  detail.
* **No known open High or Critical risks** remain before the external
  test begins.
* External testing is still **expected to challenge** every
  implemented control. Internal regression tests prove the control
  *exists*; the vendor's job is to prove it *holds* under real-world
  attack tooling.
* Some **accepted limitations** remain by design — each has an owner
  and a documented rationale (§C below).

---

## A · Fixed and verified

All 33 findings landed across W1–W8 + Iter 220be. Each carries:

* A code-level fix (file path noted in `RISK_REGISTER.md`).
* At least one source-level regression test under
  `/app/backend/tests/`.
* No outstanding production / preview environment delta.

Full audit trail: see `RISK_REGISTER.md`.

---

## B · Implemented but awaiting external verification

The following controls are in code and pass our internal tests, but
we want the external tester to **actively try to defeat them** with
real-world tooling — not just confirm the code exists.

| Area | Control implemented | What we want the tester to attempt |
|---|---|---|
| **AI prompt injection** (F-11, F-13, F-16) | `utils/ai_guardrails.py` runs every LLM round-trip; jailbreak / instruction-override patterns rejected before send; output is sanitised. | Direct (`ignore previous instructions`) + indirect (payload embedded in CRM notes, OCR'd photos, uploaded tender docs) injection. Multi-turn obfuscation. Base64- / unicode-wrapped instructions. |
| **AI excessive agency** (F-13) | `HIGH_RISK_TOOLS` registry + `mint_approval_token` / `verify_approval_token`. Tools that send email, change pricing, delete records require an explicit human approval token. | Attempt to chain low-risk tool calls into a high-risk effect without an approval token. Confirm the approval token cannot be replayed across tenants. |
| **AI output sanitisation** (F-16) | All AI output passes through `web_security.html_sanitize` (bleach) before reaching the UI. | Inject HTML / SVG / event handlers via the model. Inject Markdown links that open external scripts. |
| **AI token-budget caps** (F-14) | Per-tenant + per-user budgets enforced in `utils/ai_guardrails.token_budget_gate`. | Repeated prompt-stuffing attacks; very-long-context attacks; jailbreak attempts that try to escape the budget gate. |
| **Public widget brute-force** (F-21) | 256-bit tokens + 60/min/IP cap + per-attempt audit log. | Distributed scanning across 100+ IPs. `X-Forwarded-For` spoofing. Timing oracles on the 404 path. |
| **Engineer App horizontal access** (F-29) | 11 surfaces patched in W6. Each filters by the calling engineer's `engineer_id`. | Cross-engineer reads on edge surfaces — file streams, presigned URLs, AI-context queries, partials. |
| **DOM-XSS in PDF / email rendering** (F-04) | `bleach` allow-list + `wkhtmltopdf` rendered server-side with no JS. | Exotic payloads — SVG with embedded ECMAScript, MathML, content-type confusion, data:URI in PDF, polyglot files. |
| **Multi-tenant isolation edge cases** | Every operator route filters by `organization_id`; 404 (not 403) on cross-tenant access (F-33). | Pick any record ID from one tenant and attempt every CRUD verb against it from another tenant's session. Confirm error shapes are indistinguishable from "not found". |

For each area, the internal regression suite catches the obvious
shape of the attack. The external test is what proves these controls
hold under sustained pressure.

---

## C · Accepted limitations

These are known weaknesses that we have deliberately **not** closed —
each is signed-off with an owner and rationale.

### C-1 · `/api/health/deep` exposes version + build info

* **Why it exists:** Required for ops alerting (Pingdom, status page)
  + the master-admin "system status" tile. Allows quickly
  distinguishing "the deployment is healthy" from "the deployment is
  alive but broken".
* **What it exposes:** Application version, build hash, environment
  name (`preview` or `production`), DB ping status, AI-provider
  latency. **No secrets, credentials, env values, or per-tenant
  data.** The build hash is already public via static-asset URLs.
* **Owner:** Ops · sign-off date: **27 May 2026**.
* **Access:** Endpoint is **public** intentionally — uptime
  monitors call it from outside the cluster. If a tester surfaces a
  way to escalate from `/api/health/deep` to a credential / secret /
  per-tenant view, that's a finding (file as F-34+).

### C-2 · Public sub-processor list at `/sub-processors`

* **Why it's public:** UK / EU GDPR Article 28 § 2 requires
  customers to be able to review a current list of sub-processors.
* **What it exposes:** Names of third-party processors (Stripe,
  Resend, OpenAI, etc.), data categories, transfer mechanism, change-
  notice obligation. **No credentials, per-tenant secrets, or
  customer-specific configuration.**
* **Owner:** DPO · sign-off date: **28 May 2026**.

### C-3 · Engineer App offline cache

* **Why it exists:** Field engineers work in basements, plant rooms
  and rural sites with intermittent connectivity. Without offline
  cache they cannot complete a job mid-route.
* **What it stores:** Job metadata (site, address, asset type,
  prior fault history) for the engineer's currently-assigned jobs
  only. Photos uploaded offline queue locally until reconnect.
* **Scope:** Cache key is derived from the engineer's JWT — clearing
  the JWT (logout / token expiry / revoke) clears the cache via the
  PWA service-worker `clearOnLogout` hook.
* **What it does NOT store:** Other engineers' jobs. Other tenants'
  data. Credentials. MFA secrets.
* **Owner:** Product · sign-off date: **28 May 2026**.

### C-4 · Shared preview + production environment values

* **What:** Preview and production currently share `MONGO_URL`,
  `JWT_SECRET`, `STRIPE_SECRET_KEY` and similar via the Emergent
  platform's "one project, two URLs" model.
* **Why accepted:** Platform constraint at our current tier.
* **Mitigation:** Every collection carries `organization_id` and
  every operator route filters by it; the master-admin audit log
  records every cross-tenant probe attempt; the `pentest_*` test
  tenant is data-isolated by id even when secrets are shared.
* **Recommended future improvement:** Separate prod / staging
  secret pools when the Emergent platform offers per-env vaults.
* **Owner:** DevOps · sign-off date: **28 May 2026**.

### C-5 · Twilio SMS mocked

* **Why:** No live SMS provider wired yet; awaiting investment
  decision.
* **Effect on pen-test:** No real SMS will be sent during the
  engagement regardless of what is triggered. Testers should
  **not** treat the absence of SMS delivery as a security defect.
* **Owner:** Product · revisit date: **next quarterly review**.

### C-6 · Credential-blocked integrations (DocuSign, Outlook, Sicon)

* **Why:** The integration requires customer-provided OAuth /
  API credentials. Until the customer onboards them, the
  integration UI shows a "Connect …" CTA and the backend returns
  a `not_configured` shape.
* **Effect on pen-test:** Vendor will encounter "integration not
  configured" responses. This is **expected** — please **do not
  log it as a finding**. Test the integration auth-callback paths
  (CSRF / state-token / redirect-uri) against the configured
  integrations only.
* **Owner:** CRM Module Lead · revisit per customer-onboarding.

---

## D · Open risks

> **None currently identified before external test.**

Any finding the external vendor raises will be logged as **F-34** and
onward in `RISK_REGISTER.md` and prioritised by severity per the
post-pen-test process documented in
`PEN_TEST_READINESS_CHECKLIST.md` §G.

---

*Prepared Iter 220bf (May 28, 2026) — Craig Henshall, sign-off.*
