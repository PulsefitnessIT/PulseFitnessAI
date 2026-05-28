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
| F-04 | DOM-XSS via stored rich text in PDF/email rendering | Backend | W4 | open | Add `bleach` allowlist on write for CRM notes / activities / tender drafts / blog body. Cache cleaned HTML. |
| F-06 | IDOR sweep on equipment / integrations / staffing_clock / mod_portal | Backend | W1 | open | 25+ `find_one({id})` without org filter. Audit each, add org scope or master-admin gate. |
| F-09 | Stripe webhook idempotency (no `processed_event_ids` dedupe) | Backend | W1 | **done** (Iter 220as) | `utils/stripe_idempotency.py` + 4 handlers wired. Source-level test pinned. |
| F-11 | LLM01 — Prompt-injection guardrails missing | Backend + AI | W2 | **done** (Iter 220at) | `utils/ai_guardrails.sanitize_prompt` + `detect_injection` (score ≥80 rejects); wired into `assistant.chat`, `seo_autopilot.generate_article`, `mod_portal._ai_triage`, `equipment_import._ai_extract_invoice`. |
| F-13 | LLM08 — Excessive agency in Engineer App / CRM AI / SEO Autopilot | Backend + AI | W2 | **done** (Iter 220at) | `HIGH_RISK_TOOLS` + `mint_approval_token` / `verify_approval_token` / `require_human_approval` decorator. |
| F-17 | MFA not enforced for Master Admin | Backend | W3 | open | `require_mfa(role="master_admin")` decorator on every master-admin endpoint. 401 if MFA not enabled. |
| F-26 | SSRF in URL fetchers (Companies House, AI URL summariser, public widget) | Backend | W5 | open | CIDR allowlist; block IMDS + RFC1918 + loopback + link-local. |

## Medium (M)

| F-ID | Title | Owner | Wave | Status | Notes |
|---|---|---|---|---|---|
| F-01 | Inconsistent rate-limiting on public surfaces | Backend | W1 | **done** (Iter 220as) | Public `/signup/track` throttled 60 rpm/IP; demo-request already covered. |
| F-02 | Password reset token TTL / rotation not verified | Backend | W3 | open | Confirm ≤15 min one-shot; invalidate on use. |
| F-03 | JWT TTL / refresh-token rotation | Backend | W3 | open | Verify `exp` ≤ 1 h for access, refresh rotation pattern. |
| F-07 | List endpoints with `to_list(500+)` and no client cap | Backend | W1 | **done** (Iter 220as) | `utils/pagination.safe_limit/safe_skip` applied to mod_portal, pulse_sales, service_desk. |
| F-08 | Possible PII over-share on `/api/users/me` | Backend | W3 | open | Audit projection — strip `password`, `mfa_secret`, `stripe_customer_id`. |
| F-10 | Bulk-action endpoints lack per-call row cap + per-row audit | Backend | W1 | open | Cap at 200/call; audit row id for each. |
| F-12 | LLM06 — AI assistant doesn't filter gdpr_erased rows from context | Backend + AI | W2 | **done** (Iter 220at) | `rag_context_filter` adds `gdpr_erased: {$ne: True}` — idempotent, composable. |
| F-14 | LLM02 — Insecure handling of LLM-generated markdown in PDFs/emails | Backend + AI | W2 | **done** (Iter 220at) | `sanitize_llm_markdown` strips `<script>/<iframe>/<svg>/<style>`, `on*=` handlers, and `javascript:` URLs; wired into seo_autopilot output. |
| F-16 | LLM10 — No per-tenant token-budget cap on AI endpoints | Backend + AI | W2 | **done** (Iter 220at) | `enforce_token_budget` (default 500k tok/org/day, env-tunable) + `record_token_usage` rolling counter; wired into assistant + seo_autopilot + mod_portal. |
| F-18 | Frontend-only access control on a handful of destructive buttons | Backend | W3 | open | Server-side `require_role` on every delete/export route. |
| F-19 | Sessions not invalidated on RBAC change | Backend | W3 | open | Revoke all JWTs for that user_id on role/perm change. |
| F-20 | Exports not consistently audit-logged | Backend | W6 | open | Single decorator `@audit_export(kind="invoice_pdf")` wrapping every export route. |
| F-21 | Public widget iframe API key brute-force resistance unverified | Backend | W1 | open | Confirm widget keys are 32+ char random + per-org + rate-limited. |
| F-22 | Email recipient validation — operator can send to any address | Backend | W4 | open | Whitelist transactional senders; otherwise enforce same-org / known-contact. |
| F-24 | AV scan stub — no provider configured | Backend | W5 | open | Document as known limitation OR wire ClamAV / S3-AV. |
| F-27 | Integration credentials encryption at rest | Backend | W5 | open | Confirm all `db.organization_integrations` secrets use Fernet field-level encryption. |
| F-28 | Master Admin impersonation must be audit-logged + time-boxed | Backend | W6 | open | If impersonation flow exists → enforce log + 1-hour TTL + reason field. |
| F-29 | Engineer App horizontal access spot-checks | Backend | W6 | open | Pen-test will hit this. Pre-fix any `engineer_id`-less `find_one()`. |
| F-32 | Prod 500-handler must not leak stack traces | Backend | W6 | open | Add register on FastAPI exception_handler(500); redact in prod. |

## Low (L)

| F-ID | Title | Owner | Wave | Status | Notes |
|---|---|---|---|---|---|
| F-05 | Open redirect on post-login `next=` param | Backend | W4 | open | Allowlist same-origin only. |
| F-23 | Confirm every email send writes to `email_send_events` | Backend | W6 | open | Single point of write in `utils/email.send()`. |
| F-25 | Signed-URL TTL ≤ 1h on downloaded reports | Backend | W6 | open | Audit current TTLs in `routes/docs_export.py`. |
| F-30 | `test_credentials.md` not in production bundle | DevOps | W7 | open | Confirm `.dockerignore` / `.emergentignore`. |
| F-31 | Health endpoint must not leak commit hash | Backend | W6 | open | `/api/health` returns `{"ok": true}` only. |
| F-33 | 404 vs 403 disambiguation to prevent org-ID enumeration | Backend | W6 | open | Always return 404 for unauthorised resource (don't reveal "exists but you can't access"). |

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
| W7 | 220ay | Pen-test scope doc + isolated test tenant + sample data | S |

---

## Re-scoring cadence

- After each wave: mark covered findings `done` (with the iter that closed them).
- After external pen-test: incorporate any new findings as F-34+ and re-score.
- Quarterly: revisit Low + Informational rows to catch any silent drift.

---

*Maintained alongside `SECURITY_AUDIT_PASS_1.md`. Re-evaluated quarterly + after every pen-test cycle.*
