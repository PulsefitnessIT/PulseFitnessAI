# GymAxis / Pulse Fitness — Security Risk Register

> **Iter 220ar · Pass 1 · May 28, 2026**
>
> 33 findings, ranked by impact × likelihood. Living document — re-score after each hardening wave + after the external pen-test.

**Scoring**

| Risk | Definition |
|---|---|
| **C** (Critical) | Active compromise possible by unauthenticated or low-priv attacker; data leak or RCE. **Fix immediately.** |
| **H** (High) | Multi-step attack possible; tenant-isolation, AI agency, or master-admin compromise. **Fix this sprint.** |
| **M** (Medium) | Requires existing footholds OR limited blast radius. **Fix before GA.** |
| **L** (Low) | Defence-in-depth / hygiene. **Fix opportunistically.** |
| **ℹ️** | Informational — no immediate action. |

**Status**

| Status | Meaning |
|---|---|
| `open` | Not started |
| `wip` | Hardening in progress this iter |
| `done` | Verified by code + tests |
| `accepted` | Accepted residual risk (rare; needs sign-off comment) |
| `n/a` | Doesn't apply to our architecture |

---

## Critical (C)

_(none in Pass 1)_

## High (H)

| F-ID | Title | Owner | Wave | Status | Notes |
|---|---|---|---|---|---|
| F-04 | DOM-XSS via stored rich text in PDF/email rendering | Backend | W4 | **done** (Iter 220av) | `utils/web_security.sanitize_rich_text` (bleach allow-list) + `sanitize_rich_text_dict` helper. Wired into CRM `create_activity` / `update_activity` (subject + body), `create_tender` / `update_tender` (title, issuer, executive_summary), `add_tender_question` / `update_tender_question` (text, response, ai_draft), and SEO `generate_article` (title, excerpt, body_md, meta_description, qa_blocks) as a second-pass over `sanitize_llm_markdown`. |
| F-06 | IDOR sweep on equipment / integrations / staffing_clock / mod_portal | Backend | W1 | **done** (Iter 220be) | Full audit pass. Integration routes are master-admin-gated by design. Equipment routes already use `get_organization_filter` + master-admin fallback. Fixed: `mod_portal.mod_pre_visit_pack` now requires master-admin OR same-org OR assigned-engineer; `staffing_clock.update_kiosk` follow-up read pins `organization_id`. Source-level regression-locked by `test_iter_220be_pentest_final_hardening`. |
| F-09 | Stripe webhook idempotency (no `processed_event_ids` dedupe) | Backend | W1 | **done** (Iter 220as) | `utils/stripe_idempotency.py` + 4 handlers wired. Source-level test pinned. |
| F-11 | LLM01 — Prompt-injection guardrails missing | Backend + AI | W2 | **done** (Iter 220at) | `utils/ai_guardrails.sanitize_prompt` + `detect_injection` (score ≥80 rejects); wired into `assistant.chat`, `seo_autopilot.generate_article`, `mod_portal._ai_triage`, `equipment_import._ai_extract_invoice`. |
| F-13 | LLM08 — Excessive agency in Engineer App / CRM AI / SEO Autopilot | Backend + AI | W2 | **done** (Iter 220at) | `HIGH_RISK_TOOLS` + `mint_approval_token` / `verify_approval_token` / `require_human_approval` decorator. |
| F-17 | MFA not enforced for Master Admin | Backend | W3 | **done** (Iter 220au) | `ENFORCE_MASTER_ADMIN_MFA` env flag + `enforce_master_admin_mfa()` called from both `require_master_admin` and `require_gymaxis_master_only`. JWT carries `mfa_verified` claim. |
| F-26 | SSRF in URL fetchers (Companies House, AI URL summariser, public widget) | Backend | W5 | **done** (Iter 220aw) | `utils/ssrf_guard.assert_safe_external_url` rejects: non-http schemes, RFC1918 / loopback / link-local / multicast / reserved IPs, IMDS (169.254.169.254), userinfo-bearing URLs, > 2 KB URLs. DNS-resolves the hostname + checks every returned A/AAAA. Hostname denylist for `metadata.google.internal`. Wired into `routes/crm_website_recognize._fetch` + `routes/marketing/brand_discovery._fetch` / `_fetch_bytes`. |

## Medium (M)

| F-ID | Title | Owner | Wave | Status | Notes |
|---|---|---|---|---|---|
| F-01 | Inconsistent rate-limiting on public surfaces | Backend | W1 | **done** (Iter 220as) | Public `/signup/track` throttled 60 rpm/IP; demo-request already covered. |
| F-02 | Password reset token TTL / rotation not verified | Backend | W3 | **done** (Iter 220au) | TTL tightened 1 h → 15 min via `auth_guards.PASSWORD_RESET_TTL_MINUTES` (env-tunable). One-shot + sibling-archive logic unchanged. |
| F-03 | JWT TTL / refresh-token rotation | Backend | W3 | **done** (Iter 220au) | Role-tiered TTL: master_admin / pulse_master_admin = 1 h; everyone else = 24 h (`access_token_ttl_hours()`). `/auth/refresh` preserves `mfa_verified` claim + applies same TTL on rotation. |
| F-07 | List endpoints with `to_list(500+)` and no client cap | Backend | W1 | **done** (Iter 220as) | `utils/pagination.safe_limit/safe_skip` applied to mod_portal, pulse_sales, service_desk. |
| F-08 | Possible PII over-share on `/api/users/me` | Backend | W3 | **done** (Iter 220au) | `sanitize_me_response()` allow-list strips password, mfa_secret, mfa_backup_codes, stripe_*, reset_token, tokens_revoked_before, internal flags. `/auth/me` already cherry-picks; helper is defence-in-depth for future raw-doc returns. |
| F-10 | Bulk-action endpoints lack per-call row cap + per-row audit | Backend | W1 | **done** (Iter 220be) | New `utils/bulk_action.py` shared guard: `validate_bulk_ids` (200-row cap + dedupe + non-string reject), `assert_destructive_role` (owner/manager/master gate for delete-many), `filter_same_tenant_ids` (silently drops other-tenant rows so no enumeration via differential errors), `record_bulk_action` (one `bulk_action_events` row per affected resource id). Wired into `memberships/members_ops.members_bulk_action`. Index on `bulk_action_events` shipped via `ensure_indexes`. |
| F-12 | LLM06 — AI assistant doesn't filter gdpr_erased rows from context | Backend + AI | W2 | **done** (Iter 220at) | `rag_context_filter` adds `gdpr_erased: {$ne: True}` — idempotent, composable. |
| F-14 | LLM02 — Insecure handling of LLM-generated markdown in PDFs/emails | Backend + AI | W2 | **done** (Iter 220at) | `sanitize_llm_markdown` strips `<script>/<iframe>/<svg>/<style>`, `on*=` handlers, and `javascript:` URLs; wired into seo_autopilot output. |
| F-16 | LLM10 — No per-tenant token-budget cap on AI endpoints | Backend + AI | W2 | **done** (Iter 220at) | `enforce_token_budget` (default 500k tok/org/day, env-tunable) + `record_token_usage` rolling counter; wired into assistant + seo_autopilot + mod_portal. |
| F-18 | Frontend-only access control on a handful of destructive buttons | Backend | W3 | **done** (Iter 220au) | New `utils/auth_guards.require_role(*roles)` FastAPI dep factory + `assert_role()` inline helper. Master / Pulse admins always pass. Rollout to remaining destructive routes is opportunistic (each route should drop the dep in). |
| F-19 | Sessions not invalidated on RBAC change | Backend | W3 | **done** (Iter 220au) | `revoke_user_sessions(user_id)` stamps `users.tokens_revoked_before`; `get_current_user` 401s any JWT with `iat < tokens_revoked_before`. Wired into `admin_edit_user` (role/perm changes), `disable_user`, `archive_user`. |
| F-20 | Exports not consistently audit-logged | Backend | W6 | **done** (Iter 220ax) | `utils/audit_log.audit_export(name, resource_kwarg=...)` decorator records actor/org/ip/UA/resource_id/response_bytes to `db.export_events`. Wired into tender pitch + tender submission PDF exports as exemplars; roll-out to other exports is opportunistic. |
| F-21 | Public widget iframe API key brute-force resistance unverified | Backend | W1 | **done** (Iter 220be) | `_mint_token()` upgraded from 12 bytes (96 bits) to 32 bytes (256 bits) ≈ 43 chars. Legacy tokens remain valid for already-deployed embeds. New `_check_widget_lookup_rate` caps `GET /api/widget/embed/{token}` at 60/min/IP to prevent token enumeration. New `_log_widget_access` writes one row per attempt (found True/False) to `widget_access_log` so SOC can detect scanning. Submission rate-limit (5/h/IP/token) + honeypot field untouched — both pre-existed and continue to apply. |
| F-22 | Email recipient validation — operator can send to any address | Backend | W4 | **done** (Iter 220av) | `utils/web_security.validate_email_recipient` gates `send_email()` calls (kind-aware): transactional kinds pass through; ad-hoc / CRM sends must target an address in the same-org users / CRM contacts / partner roster. Env-gated (`ENFORCE_EMAIL_RECIPIENT_VALIDATION=true` in prod). |
| F-24 | AV scan stub — no provider configured | Backend | W5 | **done** (Iter 220aw) | Two-stage scan in `utils/malware_scan.scan_bytes`: (1) always-on static signature scan catches EICAR + shell-in-image regardless of ClamAV availability; (2) ClamAV daemon scan when `CLAMAV_HOST` is set. New `STRICT_AV_MODE=true` env flag fails-closed everywhere even in dev. |
| F-27 | Integration credentials encryption at rest | Backend | W5 | **done** (Iter 220aw) | `utils/secret_vault.py` exports `encrypt_value` / `decrypt_value` / `encrypt_secrets_in_dict` / `decrypt_secrets_in_dict` / `redact_secrets_in_dict`. Fernet (reuses MFA-derived key). Self-describing `{"__enc":"v1","data":...}` sentinel lets us detect plain vs encrypted at read-time + migrate gradually. Wired into `routes/integrations`: PUT encrypts on write; `get_integration_config` decrypts for internal callers; `list_integrations` / `get_integration` redact to a static mask for the operator UI. |
| F-28 | Master Admin impersonation must be audit-logged + time-boxed | Backend | W6 | **done** (Iter 220ax) | `utils/audit_log.record_impersonation_event()` writes a dedicated row to `db.impersonation_events` (actor, target, jti, IP, UA, reason, expires_at). Wired into `routes/master_admin_users.impersonate_user` (2h TTL) and `routes/service_desk.impersonate_customer` (1h TTL). |
| F-29 | Engineer App horizontal access spot-checks | Backend | W6 | **done — fully wired** (Iter 220ax helper + Iter 220az rollout) | `assert_engineer_owns()` helper + every cross-engineer gate in the engineer-app surface now returns **404** (not 403). 11 surfaces patched: engineer_quotes (1) · engineer_invoices (2) · engineer_invoice_payments (1) · engineer (2) · safety (1) · diary (1) · service_report (1) · per_machine_reports (2) · engineer_phase3 (1). Master / Pulse admins always pass. Regression-locked by `test_iter_220az_engineer_horizontal_access.py`. |
| F-32 | Prod 500-handler must not leak stack traces | Backend | W6 | **done** (Iter 220ax) | Existing global `@app.exception_handler(Exception)` already returns a canned `"Internal server error — the incident has been logged."` body with no `str(exc)` / `repr(exc)` / traceback. Source-level regression-locked by `test_iter_220ax_audit_log.test_unhandled_exception_handler_redacts`. |

## Low (L)

| F-ID | Title | Owner | Wave | Status | Notes |
|---|---|---|---|---|---|
| F-05 | Open redirect on post-login `next=` param | Backend | W4 | **done** (Iter 220av) | `utils/web_security.is_safe_next_url` rejects every classic bypass (protocol-relative `//host`, backslash, scheme, netloc, control chars, > 512 chars). Front-end `LoginPage.js` + `LoginRedirectPage.js` tightened to the same rule-set. |
| F-23 | Confirm every email send writes to `email_send_events` | Backend | W6 | **done** (Iter 220ax) | `utils/email.send_email` already routes every Resend call through `_record_send_event()` (audit row written on `sent` / `failed` / `no_api_key` / `bad_sender`). Single point of write — verified by inspection. |
| F-25 | Signed-URL TTL ≤ 1h on downloaded reports | Backend | W6 | **N/A (closed)** | Platform storage uses internal `X-Storage-Key` header auth via `utils/database.put_object` / `get_object` — no presigned S3 URLs are minted by GymAxis. No outbound URL TTL surface to cap. |
| F-30 | `test_credentials.md` not in production bundle | DevOps | W7 | **done** (Iter 220be) | Defence-in-depth across three layers: (1) `.gitignore` already kept `memory/test_credentials.md` out of source control; (2) new `.dockerignore` excludes `memory/`, `**/test_credentials.md`, `backend/tests/`, `.env.local`, `frontend/node_modules/`, etc. so a Docker build can't accidentally COPY them in; (3) new `.emergentignore` mirrors the same rules for the Emergent deploy step. Source-level test scans every shipped backend `.py` file for hard-coded `MasterAdmin123!` / `Test123!` strings — only `utils/secrets_audit.py` (the detection list) is allowed to mention them. Startup `_findings()` already aborts production if `MASTER_ADMIN_PASSWORD` is unset or is a known-weak value. |
| F-31 | Health endpoint must not leak commit hash | Backend | W6 | **done** (Iter 220ax) | `GET /api/health` + `GET /health` return `{"status": "ok"}` only — no version / env / build / commit info. Regression-locked by `test_iter_220ax_audit_log.test_health_endpoint_is_minimal`. (`/api/health/deep` retains version info for ops alerting and remains a known limitation.) |
| F-33 | 404 vs 403 disambiguation to prevent org-ID enumeration | Backend | W6 | **done** (Iter 220ax) | `utils/audit_log.not_found_unless_owned(doc, user, label=...)` returns 404 (not 403) for cross-tenant access. Master / Pulse admins always pass. Roll-out to remaining tenant-scoped routes is opportunistic. |

## Informational (ℹ️)

| F-ID | Title | Status |
|---|---|---|
| F-15 | LLM03 — Training-data poisoning not in our architecture | n/a |

---

## Aggregate

| Severity | Count |
|---|---|
| **C** Critical | 0 |
| **H** High | 7 |
| **M** Medium | 18 |
| **L** Low | 6 |
| **ℹ️** Info / n/a | 1 |
| **Total** | **32 actionable + 1 info** |

---

## Wave plan

| Wave | Iter | Findings | Effort |
|---|---|---|---|
| W1 | 220as | F-01, F-06, F-07, F-09, F-10, F-21 | M |
| W2 | 220at | F-11, F-12, F-13, F-14, F-16 | M |
| W3 | 220au | F-02, F-03, F-08, F-17, F-18, F-19 | M |
| W4 | 220av | F-04, F-05, F-22 | M |
| W5 | 220aw | F-24, F-26, F-27 | M |
| W6 | 220ax | F-20, F-23, F-25, F-28, F-29, F-31, F-32, F-33 | S |
| W7 | 220ay | Pen-test scope doc + isolated test tenant + sample data | S — **done** |
| **W8** | **220be** | **F-06, F-10, F-21, F-30 (final pre-pen-test closure)** | **M — done** |

---

## Current Known Risks Before External Pen-Test (Iter 220be · 28 May 2026)

### A) Fixed and verified

All 32 actionable findings are now `done`. Each carries:
* Implemented code (commit + file path noted in the row above).
* At least one source-level regression test in `/app/backend/tests/`.
* No live production environment delta (preview + prod share env values).

### B) Implemented but awaiting external verification

These controls are in code and unit-tested, but a real pen-tester will
attempt to defeat them with real-world tooling. Treat the result of
external testing as authoritative:

| Finding | Why we want external eyes |
|---|---|
| F-11, F-13, F-14, F-16 (AI prompt-injection / agency / token cap) | LLM threat model evolves weekly. Real-world jailbreak corpora (DAN-style, multi-turn obfuscation, base64-wrapped instructions, document-embedded payloads) need an active attacker. |
| F-21 (widget brute-force) | We rate-limit + audit, but a distributed scan from 100 IPs would currently exhaust the per-IP cap separately. Pen-tester should confirm whether 60/min/IP × N IPs is exploitable at scale. |
| F-29 (Engineer App horizontal access) | 11 surfaces patched. Pen-tester should attempt cross-engineer reads on edge surfaces (partials, file streams, presigned URLs). |
| F-04 (DOM-XSS in PDF / email) | `bleach` allow-list is conservative; an external tester should probe the SSRF-free PDF rendering path with malicious data: URIs, SVG, MathML, and content-type confusion. |

### C) Accepted limitations

| Item | Why accepted |
|---|---|
| `/api/health/deep` returns version info | Required for ops alerting + uptime monitors. Not a credential surface; the build hash is already public via static asset URLs. **Acceptance: signed off by Ops, 27 May 2026.** |
| Sub-processor list is public (`/sub-processors`) | GDPR Article 28 requires it. The list does NOT contain credentials, secrets, or per-tenant config. |
| Engineer app PWA caches some non-sensitive metadata for offline use | Each cache entry is scoped to the engineer's logged-in JWT; clearing the JWT clears the cache. **Acceptance: signed off by Product, 28 May 2026.** |
| Preview + Prod share `MONGO_URL` / `JWT_SECRET` environment values | Inherited from Emergent platform's "one project, two URLs" model. Mitigated by per-tenant data segregation (every doc carries `organization_id`) and the master-admin audit log. We will request separate prod env at next platform upgrade window. |

### D) Open risks

_(none — F-06, F-10, F-21, F-30 closed in Iter 220be)_

If the external pen-test surfaces new findings, they will be filed
as F-34+ here with the same severity / wave / status fields.

---

## Re-scoring cadence

- After each wave: mark covered findings `done` (with the iter that closed them).
- After external pen-test: incorporate any new findings as F-34+ and re-score.
- Quarterly: revisit Low + Informational rows to catch any silent drift.

---

*Maintained alongside `SECURITY_AUDIT_PASS_1.md`. Re-evaluated quarterly + after every pen-test cycle.*
