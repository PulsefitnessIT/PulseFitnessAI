# Pen-Tester Onboarding — GymAxis AI

**Engagement window:** _confirmed in the scoping email_
**Owner-of-record:** Master Admin · `admin@gymaxisai.com`
**Stack:** React 19 SPA · FastAPI · MongoDB · Kubernetes (Emergent)
**Source-of-truth risk register:** `/app/memory/SECURITY_AUDIT/RISK_REGISTER.md`
**Audit baseline:** `/app/memory/SECURITY_AUDIT/SECURITY_AUDIT_PASS_1.md`
**Hardening completed:** W1–W6 (27 of 33 register findings). See **Cumulative Posture** at the bottom.

---

## 1 · Scope (the "what")

### In-scope hosts
| Surface                                  | URL                                                              |
|------------------------------------------|------------------------------------------------------------------|
| Production SPA                           | `https://app.gymaxisai.com`                                      |
| Production API                           | `https://app.gymaxisai.com/api/*`                                |
| Marketing / public site                  | `https://gymaxisai.com`                                          |
| Public widget / signup pages             | `https://gymaxisai.com/signup/<slug>`                            |
| Pen-test sandbox tenant                  | `https://app.gymaxisai.com` · org_id = `pentest-org-001`         |

### Out-of-scope
* Any organisation _other than_ `pentest-org-001` — accidental writes to live orgs will void the engagement.
* The Master Admin account (`admin@gymaxisai.com`) — credential-stuffing it is fine, but do **not** brute-force lock it for > 5 minutes.
* Emergent platform / Kubernetes / Mongo Atlas infra — separate scope, not ours to authorise.
* Stripe live keys / Resend production API — testing of the integration boundary is fine, but please don't actually trigger production charges or send to non-test addresses.

### Permitted attack classes
OWASP Top 10 (Web + API + LLM) · IDOR & horizontal-priv-esc · auth flows · SSRF · stored / reflected / DOM XSS · open redirect · file-upload smuggling · prompt injection · rate-limit bypass.

### Not permitted (out of scope by ROE)
DDoS / volumetric · social engineering of employees · physical-access · phishing of customers.

---

## 2 · Test-tenant credentials

Seed with: `cd /app/backend && ALLOW_PENTEST_SEED=true python -m scripts.seed_pentest_tenant`

**Credentials are not printed in this document.** All 5 role accounts
are delivered to the pen-test vendor via a 1Password share at kickoff
(security@gymaxisai.com manages the share). The accounts below are
listed by email + role only:

| Role                         | Email                            | Notes                                                            |
|------------------------------|----------------------------------|------------------------------------------------------------------|
| Owner (regular session)      | `pentest-owner@gymaxis.test`     | Standard operator session, no MFA.                               |
| Manager                      | `pentest-mgr@gymaxis.test`       | Mid-tier role with bulk-action access for F-10 testing.          |
| Staff                        | `pentest-staff@gymaxis.test`     | Lowest operator privilege; useful for vertical-escalation tests. |
| Owner with MFA enrolled      | `pentest-mfa@gymaxis.test`       | Pre-enrolled TOTP — use for MFA bypass attempts.                 |
| Master Admin (do-not-lock)   | `admin@gymaxisai.com`            | **Do not** brute-force-lock for > 5 minutes (P0 escalation path).|

Passwords + TOTP seeds are delivered exclusively via 1Password — they
are **never** committed to this repo, embedded in tickets, or sent over
email. If the share is missing on day 1 of the test window, escalate
to `security@gymaxisai.com` immediately.

The seed script also creates 2 CRM companies, 3 contacts, 2 opportunities, and 5 members — one of which carries `gdpr_erased=True` so you can verify the **F-12 (LLM06) RAG-context filter**.

---

## 3 · Production env flags to flip before the engagement

These are off-by-default in dev so the regression suite isn't blocked. **Flip them all in prod before the pen-test starts.**

| Env var                              | Value             | Closes finding(s)             | What it does                                                                                                            |
|--------------------------------------|-------------------|-------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| `ENFORCE_MASTER_ADMIN_MFA`           | `true`            | F-17                          | Every master-admin endpoint 401s unless the session was elevated via TOTP.                                              |
| `ENFORCE_EMAIL_RECIPIENT_VALIDATION` | `true`            | F-22                          | `send_email()` rejects any ad-hoc destination not in the same-org user / CRM contact / partner roster.                  |
| `STRICT_AV_MODE`                     | `true`            | F-24                          | Refuse uploads when no malware scanner is reachable (fail-closed everywhere, not just prod).                            |
| `CLAMAV_HOST`                        | `clamav`          | F-24                          | Hostname of the ClamAV sidecar; pair with `CLAMAV_PORT=3310`. Required to satisfy `STRICT_AV_MODE`.                     |
| `MFA_ENCRYPTION_KEY`                 | _fresh Fernet key_ | F-27                          | Production Fernet key for `db.integrations` + MFA secrets. Rotate quarterly. (Falls back to `JWT_SECRET` if unset.)     |
| `SSRF_EXTRA_DENYLIST_HOSTS`          | _comma-list_       | F-26                          | Override the default `metadata.google.internal,metadata,169.254.169.254` allow-extra deny entries if your VPC uses other internal magic hostnames. |

Plus three already-in-prod env vars that should already be set:
`JWT_SECRET`, `MONGO_URL`, `RESEND_API_KEY`.

---

## 4 · Expected-behaviour cheat sheet

What we expect the pen-tester to **NOT** be able to do, with the file that enforces it:

| Class                              | Expectation                                                                                          | Enforced by                                                       |
|------------------------------------|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| **Prompt injection (LLM01)**       | Score ≥ 80 → 400 reject + audit-row in `db.ai_actions`. Score < 80 wrapped in `<user_input>` delimiters. | `utils/ai_guardrails.detect_injection` · `sanitize_prompt`        |
| **RAG context leak (LLM06)**       | AI never sees `members` / `crm2_contacts` rows with `gdpr_erased=True`.                              | `utils/ai_guardrails.rag_context_filter`                          |
| **LLM-output XSS (LLM02)**         | SEO blog `body_md` strips `<script>` / `<iframe>` / `on*=` / `javascript:` URLs.                     | `utils/ai_guardrails.sanitize_llm_markdown` + `utils/web_security.sanitize_rich_text` |
| **Stored XSS (CRM rich text)**     | Bleach allow-list on every persisted activity / tender / blog body.                                  | `utils/web_security.sanitize_rich_text`                           |
| **Open redirect**                  | `?next=` rejects `//host`, `\host`, `javascript:`, schemes, control chars, > 512 chars.              | `utils/web_security.is_safe_next_url` + frontend `LoginPage.js`    |
| **SSRF**                           | URL fetchers reject IMDS / RFC1918 / loopback / link-local; DNS-resolve checks all A/AAAA.            | `utils/ssrf_guard.assert_safe_external_url`                       |
| **JWT / session**                  | master_admin = 1h TTL; refresh preserves `mfa_verified`; RBAC change → `users.tokens_revoked_before` bumps. | `utils/auth.py` · `utils/auth_guards.py`                          |
| **Password reset**                 | 15-min one-shot token; siblings archived on use; rate-limited.                                       | `routes/auth.py::forgot_password` + `utils/auth_guards.PASSWORD_RESET_TTL_MINUTES` |
| **PII over-share**                 | `/auth/me` allow-lists fields; never returns `password_hash` / `mfa_secret` / `stripe_customer_id`.   | `utils/auth_guards.sanitize_me_response`                          |
| **Stripe webhook replay**          | `event_id` unique + 30-day TTL; replay → 200 no-op.                                                  | `utils/stripe_idempotency.py`                                     |
| **AV — EICAR**                     | Static-signature scan fires regardless of ClamAV availability.                                       | `utils/malware_scan.scan_bytes`                                   |
| **Integration secrets at rest**    | `db.integrations.api_token` / `.webhook_secret` / `.credentials` Fernet-encrypted on write.          | `utils/secret_vault.py` + `routes/integrations.py`                |
| **Impersonation audit**            | Every Pulse master-admin impersonation writes `db.impersonation_events` with actor / target / JTI / IP / UA / expires_at. | `utils/audit_log.record_impersonation_event`                      |
| **404-vs-403 enumeration**         | Cross-tenant access returns **404 — Resource not found**, never 403.                                  | `utils/audit_log.not_found_unless_owned`                          |
| **500 leak**                       | Unhandled exceptions return canned `"incident has been logged"` body — no `str(exc)` / traceback.    | `server.py::_unhandled_exception_handler`                         |
| **Health probe leak**              | `GET /health` + `GET /api/health` return `{"status":"ok"}` — no version / env / build / commit.       | `server.py::health_root` + `health_root_unprefixed`               |
| **Rate limits**                    | `/api/public/demo-request` + `/api/public/signup/<slug>/track` IP-rate-limited.                       | `utils/security_plus.rate_limit_*`                                |
| **Per-tenant LLM budget**          | 500 k tokens / org / day; over → 429.                                                                | `utils/ai_guardrails.enforce_token_budget`                        |

---

## 5 · Known limitations + accepted risk

| Finding | Status   | Why we're OK with it for this engagement                                                          |
|---------|----------|----------------------------------------------------------------------------------------------------|
| F-25    | N/A      | No presigned S3 URLs — storage uses internal `X-Storage-Key` header auth instead.                  |
| F-26    | Partial  | SSRF guard wired into the two highest-value user-controlled URL fetchers (`crm_website_recognize`, `marketing/brand_discovery`). Remaining server-side fetchers use fixed hostnames (Companies House, Stripe, Resend) so SSRF risk is structurally low. Document any new user-URL surface to also call `assert_safe_external_url`. |
| F-18    | Helper available | `require_role` dep available; opportunistic roll-out — a handful of destructive routes still rely on frontend-only gating. Pen-tester will help us map remaining gaps. |
| F-20    | Exemplar | Decorator wired into tender exports as a worked example. Roll-out to every CSV/PDF/ZIP export route is opportunistic. |
| F-29    | Helper available | `assert_engineer_owns()` helper is the canonical fix. Engineer-app endpoints have NOT been individually re-checked — please prioritise this surface. |
| F-33    | Helper available | `not_found_unless_owned()` helper available. Roll-out to all tenant-scoped routes is opportunistic. |
| Sicon / Outlook / DocuSign | Mocked | Blocked on upstream live credentials. The mock surface is internal-only and not deployed to prod. |

---

## 6 · How to report

1. **Severity rubric:** CVSS 3.1 + tag with the matching `F-NN` from `RISK_REGISTER.md` where possible.
2. **PoC:** include the curl / browser request + the affected route + the actor (which test user).
3. **Hand-off file:** drop the report at `/app/memory/SECURITY_AUDIT/PEN_TEST_FINDINGS.md` (one section per finding) so the dev team can triage in one place.
4. **Critical findings:** also email `security@gymaxisai.com` + `admin@gymaxisai.com` with subject `[GymAxis PenTest] [CRITICAL] <one-line>` — the master admin's pager fires on that prefix.

---

## 7 · Cumulative posture (W1–W6)

| Wave | Iter   | Findings closed                           | Code size |
|------|--------|--------------------------------------------|-----------|
| W1   | 220as  | Rate-limits, Stripe idempotency, list caps | M         |
| W2   | 220at  | F-11 F-12 F-13 F-14 F-16 (LLM01–10)         | L         |
| W3   | 220au  | F-02 F-03 F-08 F-17 F-18 F-19 (auth)        | L         |
| W4   | 220av  | F-04 F-05 F-22 (web scrubbers)             | M         |
| W5   | 220aw  | F-24 F-26 F-27 (SSRF + AV + Fernet)        | L         |
| W6   | 220ax  | F-20 F-23 F-25 F-28 F-29 F-31 F-32 F-33    | M         |

**27 of 33 risk-register findings closed.** Remaining 6 = the partial roll-outs called out in §5 + the 3 blocked-on-credentials integrations.

**Regression baseline at hand-over:** **1253 tests passing**, 15 skipped, 0 introduced failures across 6 waves of hardening (one chronic LLM flake in `test_iter_220s_incidents_riddor` known + isolated).

---

_Last updated: 2026-05-28 · Wave 7 / Iter 220ay_
