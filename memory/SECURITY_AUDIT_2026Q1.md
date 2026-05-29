# Pen-Test Readiness Audit — 2026 Q1

Scope: end-to-end review of GymAxis platform against OWASP Top 10
2021, OWASP LLM Top 10, and the original problem statement's specific
asks (API limits, Stripe idempotency, prompt-injection guardrails).

**Methodology**: static analysis of `/app/backend/{routes,utils,middleware}`,
`/app/backend/server.py`, and the new marketing autopilot endpoints
(Iter 220ad → 220bn). Cross-referenced with PRD.md history and existing
regression suite (1410 tests).

---

## 1. Already covered — no new work required

| # | OWASP / Topic | Where it lives | Status |
|---|---|---|---|
| 1 | A01 Broken Access Control | `utils/auth.py`, `_require_master_admin`, org-scoped queries, `security_plus.client_rate_key` | ✅ Covered |
| 2 | A02 Cryptographic Failures | bcrypt password hash, JWT HS256 with rotated secret, `secrets.token_urlsafe` for supplier tokens | ✅ Covered |
| 3 | A03 Injection (NoSQL/Command/LDAP) | All MongoDB queries use the parameterized API (no `eval()`, no string concat); `bleach`-based `sanitize_rich_text`; tag stripper for plain text | ✅ Covered |
| 4 | A05 Security Misconfiguration | CSP (`server.py:101`), HSTS (`server.py:123`), `X-Content-Type-Options`, `Referrer-Policy`, COOP/CORP, env-driven CORS allow-list | ✅ Covered |
| 5 | A07 Identity & Auth Failures | Account lockout, login rate limit (per-IP + per-account), JWT revocation with grace window (`security_plus.revoke_jwt`), bcrypt verify timing | ✅ Covered |
| 6 | A09 Logging & Monitoring | `record_trust_event` on 5xx + slow requests, `audit_required` fail-closed audit writer, slow-request ring buffer | ✅ Covered |
| 7 | A10 SSRF | No user-controlled URL fetches identified | ✅ Covered |
| 8 | Stripe **webhook** idempotency | `utils/stripe_idempotency.py` + `mark_event_processed` calls in every `/api/webhook/stripe` handler | ✅ Covered |
| 9 | Body size limit | `security_plus.body_size_guard` tri-tier middleware (default 2 MB / upload 25 MB / bulk-import 200 MB) | ✅ Covered |
| 10 | Per-user LLM budget | `check_and_record_llm_budget` (Ask Support Desk) — daily/monthly caps | ✅ Covered |
| 11 | DOM-XSS via stored rich text | `web_security.sanitize_rich_text` bleach allow-list | ✅ Covered |
| 12 | Open-redirect via `?next=` | `web_security.is_safe_next_url` | ✅ Covered |
| 13 | Email-recipient validation | `web_security.validate_email_recipient` (org-scope + CRM allow-list) | ✅ Covered |

## 2. Findings — gaps closed in this audit

### F-220bo-1 — HIGH · LLM-amplified privilege gap on `assistant_execute_action`

**Location**: `routes/marketing/assistant.py:312`

The endpoint is gated only by `get_current_user`, meaning **any
authenticated user** (Member tier, kiosk user, free-trial signup) can
POST `{"type":"clear_demo_data"}` and DELETE rows in
`marketing_audiences`, `marketing_campaigns`, `marketing_journeys`,
`marketing_creative_assets` for their org.

The damage is bounded to docs tagged `demo_tour` in the caller's own
org, so blast radius is limited, but:

* A successful prompt-injection in the chat surface (which suggests
  actions to the same user) could nudge a non-operator to one-click
  delete demo data they shouldn't be touching.
* The other action types (`navigate_tab`, `instantiate_template`)
  are UI-side-effect only, but `clear_demo_data` is a real DB mutate.

**Fix**: require operator/admin role on the execute endpoint
(`require_marketing_operator`). The chat suggestion surface stays
open to all users (read-only).

### F-220bo-2 — MEDIUM · Unbounded user input to LLM (`/marketing/assistant/chat`)

**Location**: `routes/marketing/assistant.py:171`

`message = (body.get("message") or "").strip()` enforces non-empty
but has no max length. A 100k-char message would burn through the
caller's LLM budget in a single request and inflate context cost.

**Fix**: hard cap at 4000 chars (well above any reasonable Q&A
prompt) with a 400 response if exceeded.

### F-220bo-3 — MEDIUM · Stripe SDK calls missing `idempotency_key`

**Location**:

* `routes/partners.py:1474` — `Subscription.modify` (tier swap)
* `routes/partners.py:2144` — `checkout.Session.create` (partner plan)
* `routes/master_admin_trials.py:284` — `checkout.Session.create`
* `routes/crm_modes.py:150` — `checkout.Session.create`

Stripe **webhook** idempotency is solid (`utils/stripe_idempotency.py`).
But the **outbound** Stripe API write calls don't pass
`idempotency_key=...`. If the client double-clicks "Subscribe" or the
network retries on a 5xx, Stripe will happily create two checkout
sessions / two subscription modifications (cost = duplicate charges
in a real failure mode).

**Fix**: pass a deterministic `idempotency_key` (uuid v4 derived from
caller + intent) into every Stripe SDK write call. Wraps the SDK in
a tiny helper so all future call-sites pick up the pattern.

### F-220bo-4 — MEDIUM · No per-user rate limit on Autopilot generate endpoints

**Location**:

* `POST /api/marketing/social-autopilot/generate`
* `POST /api/marketing/social-autopilot/run-now`
* `POST /api/marketing/social-autopilot/posts/{id}/generate-video`
* `POST /api/marketing/seo/articles/generate`
* `POST /api/marketing/seo/keywords/research`

All five are master-admin-only and trigger expensive LLM /
Nano-Banana / Sora 2 calls. A compromised master-admin token
(phishing, leaked dev console) could burn through the EMERGENT_LLM
budget in seconds.

**Fix**: layer `rate_limit_async` (Mongo-backed sliding window,
multi-replica safe) on top of the existing master-admin auth check:

* generate / run-now → 20 per hour per user
* generate-video → 5 per hour per user (Sora 2 is ~$/clip)
* keywords/research → 30 per hour per user

### F-220bo-5 — LOW · No delimiter-wrap on user input feeding LLM prompts

**Location**: `assistant.py:256`, `seo_autopilot.py:276`

User-supplied `message` / `seed_topic` is concatenated into the
prompt as plain text. OWASP LLM01 (Prompt Injection) recommends
wrapping untrusted input in delimited blocks and instructing the
model to treat content inside the delimiters as data, not
instructions.

**Fix**: wrap user input in `<<<USER_INPUT>>> … <<<END>>>` and append
a system-level instruction reminding the model to ignore any
"instructions" inside that block. Cheap defence; doesn't eliminate
prompt injection but materially raises the bar.

## 3. Out-of-scope for this audit (tracked separately)

* SSO / SAML hardening — not on roadmap until enterprise tier.
* WAF / DDoS at edge — outside app boundary; provided by Cloudflare.
* SAST in CI pipeline (Semgrep, CodeQL) — future ticket.
* Pen-test report sign-off — done by external tester post-deployment.

## 4. Verification plan

1. Net-new tests in `test_iter_220bp_security_hardening.py`:
   * `assistant_execute_action` rejects non-operator users with 403.
   * `/marketing/assistant/chat` rejects `message > 4000` chars with 400.
   * `social-autopilot/generate` rate-limits to 20/hour.
   * Stripe SDK wrapper passes `idempotency_key` (mock asserts).
   * Prompt-wrap helper produces the expected envelope.
2. Existing `make regression` still 1410+ passing.
3. Manual smoke: log in as master admin, hit Run-today → expect 200;
   hit it 25× in a row → expect 429.

---

*Author: E1 · 2026-02-29 · scope: pen-test readiness audit closing
gaps F-220bo-1 through F-220bo-5*
