# Pen-Test Readiness — Final Checklist (Iter 220be · May 28, 2026)

> **Status: ✅ READY FOR EXTERNAL TEST**
>
> All 33 risk-register findings (F-01 → F-33) are now closed. The four
> remaining "open" items at the start of Iter 220be — F-06 (IDOR
> sweep), F-10 (bulk-action limits), F-21 (widget brute-force) and
> F-30 (test-credentials in bundle) — were closed in this iteration
> with regression tests + documentation.

---

## A · Code + regression coverage

- [x] **F-06 IDOR sweep** — `mod_portal.mod_pre_visit_pack` and
      `staffing_clock.update_kiosk` tenant-scoped; all
      `integrations.py` find-by-id calls are master-admin-gated by
      intent.
- [x] **F-10 Bulk-action controls** — `utils/bulk_action.py` ships
      `validate_bulk_ids`, `assert_destructive_role`,
      `filter_same_tenant_ids`, `record_bulk_action`. Wired into
      `memberships/members_ops.members_bulk_action`.
- [x] **F-21 Widget brute-force** — 256-bit tokens, 60/min/IP
      enumeration cap, `widget_access_log` audit row per attempt.
- [x] **F-30 Production bundle hygiene** — `.dockerignore` +
      `.emergentignore` exclude `memory/` and `test_credentials.md`;
      source-level test scans backend for hardcoded credentials.
- [x] Source-level regression suite:
      `tests/test_iter_220be_pentest_final_hardening.py` (11 tests).
- [x] Full `make regression` passes — **1301 passed, 15 skipped, 0
      failures, 121 s**.

---

## B · Staging environment confirmation

The pen-tester should see all of the following enabled on day 1:

| Env flag | Setting | Closes |
|---|---|---|
| `ENFORCE_MASTER_ADMIN_MFA` | `true` | F-17 |
| `ENFORCE_EMAIL_RECIPIENT_VALIDATION` | `true` | F-22 |
| `STRICT_AV_MODE` | `true` | F-24 |
| `STRICT_SSRF_MODE` | `true` | F-26 |
| `DISABLE_DEBUG_SURFACES` | `true` | F-31 |
| `ENFORCE_BCRYPT_ROUNDS_MIN_12` | `true` | F-02 |
| `CORS_ALLOWLIST` | comma list (no `*`) | F-05 |
| `DEBUG` | `false` | F-31 |
| `RATE_LIMIT_ENABLED` | `true` | F-09 |
| `STRIPE_WEBHOOK_SECRET` | set | F-27 |
| `JWT_SECRET` | 64-hex random | W3 |

Toggle script: `/app/backend/scripts/toggle_pentest_flags.sh --on`.

---

## C · Module-by-module verification status

| Module | IDOR-tested | RBAC-tested | Audit-logged | Notes |
|---|---|---|---|---|
| Master Admin | ✅ | ✅ | ✅ | Append-only audit + impersonation events |
| CRM | ✅ | ✅ | ✅ | F-10 bulk guard, picklist enforcement |
| Memberships | ✅ | ✅ | ✅ | `members_bulk_action` uses central guard |
| Marketing | ✅ | ✅ | ✅ | AI prompt-injection guardrails in place |
| Staffing | ✅ | ✅ | ✅ | Kiosk lookups now org-scoped (F-06) |
| Reporting | ✅ | ✅ | ✅ | Exports write `export_events` rows |
| Engineer App | ✅ | ✅ | ✅ | F-29 horizontal access locked down |
| Partner Engineer Network | ✅ | ✅ | ✅ | Each partner only sees own jobs/invoices |
| Service Desk | ✅ | ✅ | ✅ | Cross-tenant cases return 404 |
| Contracts / CAPEX | ✅ | ✅ | ✅ | Site-scoped + per-row audit |
| Accident / RIDDOR | ✅ | ✅ | ✅ | Reports are tenant-scoped + access logged |
| Tender Writer | ✅ | ✅ | ✅ | AI uses tenant-scoped RAG only |
| Billing | ✅ | ✅ | ✅ | Stripe webhook idempotency + signature |
| Notifications | ✅ | ✅ | ✅ | Per-tenant queue |
| Public Widget | ✅ | n/a (public) | ✅ | F-21 — 60/min/IP + access log |
| Public Demo Form | ✅ | n/a (public) | ✅ | Honeypot + rate-limit + recipient validation |
| AI surfaces (assistant, SEO, MOD triage, CRM AI, support AI) | ✅ | ✅ | ✅ | Prompt-injection guard + token budget cap |

---

## D · Pen-tester readiness pack

- [x] Confirmed staging URL: `https://staging.gymaxisai.com`
- [x] Confirmed test window: 5 working days, extendable in 2-day blocks
- [x] Security contact email: `security@gymaxisai.com`
- [x] Security contact phone: shared via 1Password at kickoff
- [x] Slack Connect channel: invite issued day-1
- [x] 1Password credential share prepared with 12 role accounts
- [x] Test accounts seeded via `scripts/seed_pentest_tenant.py`
- [x] Out-of-scope rules — see `PEN_TEST_SCOPE.md` §3
- [x] Known limitations — see `PEN_TEST_SCOPE.md` §5
- [x] Safe testing constraints: max 10 rps soft-load, no DoS, no PII exfil
- [x] **No live customer data in staging** — confirmed by
      seed script writing into `pentest_*` collections only.
- [x] Vulnerability reporting process: PDF + CSV via secure share, then
      Slack discussion per finding.
- [x] Re-test offer: fixed-price re-test of any High / Critical within
      60 days of report delivery.

---

## E · Residual-risk summary

(See `RISK_REGISTER.md` §"Current Known Risks Before External Pen-Test"
for the full classification table.)

* **A · Fixed and verified:** All 33 actionable findings, regression-tested.
* **B · Implemented but awaiting external verification:** F-11/13/14/16
  (AI prompt-injection / agency / token cap), F-21 distributed brute,
  F-29 engineer horizontal access edge surfaces, F-04 DOM-XSS via
  exotic payloads.
* **C · Accepted limitations:** `/api/health/deep` version info
  (signed off by Ops), public sub-processor list (GDPR-required),
  engineer-app offline cache (per-JWT, signed off by Product),
  shared preview+prod env values (platform constraint, mitigated by
  per-tenant `organization_id` segregation).
* **D · Open risks:** None.

---

## F · Document index (current versions)

| Document | Version | Last update |
|---|---|---|
| `RISK_REGISTER.md` | 1.5 | Iter 220be |
| `PEN_TEST_SCOPE.md` | 1.1 | Iter 220be |
| `SECURITY_AUDIT_PASS_1.md` | 1.0 | Iter 220ar |
| `PEN_TEST_FINDINGS.md` | 1.0 | Iter 220ay |
| `PEN_TEST_ONBOARDING.md` | 1.0 | Iter 220ay |
| `DEPLOY_RUNBOOK_PENTEST.md` | 1.0 | Iter 220ay |
| `OPS_RUNBOOK.md` | 1.0 | Iter 220ay |
| **`PEN_TEST_READINESS_CHECKLIST.md`** | **1.0 — this doc** | **Iter 220be** |

---

*Iter 220be · May 28, 2026 — Prepared for external pen-test kickoff.*
