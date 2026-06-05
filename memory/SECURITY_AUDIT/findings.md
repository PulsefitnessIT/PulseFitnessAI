# GymAxis — Security Findings (Single Source of Truth)

> This is the **canonical security register** for the platform. Every security
> review, fix and re-assessment is recorded here. When asked "are there security
> gaps?", read and update THIS file rather than re-deriving from scratch.
>
> Severity: 🔴 High · 🟠 Medium · 🟡 Low · 🟢 Resolved / Good
> Status: `OPEN` · `FIXED` · `MITIGATED` · `ACCEPTED` · `CONFIG` (deploy-time)

Last full review: **2026-06-05**

---

## Summary table

| ID | Severity | Title | Status |
|----|----------|-------|--------|
| SEC-001 | 🟠 Medium | Regex injection / ReDoS in Mongo `$regex` search | ✅ FIXED (2026-06-05) |
| SEC-002 | 🔴 High (prod) | CORS `*` wildcard with credentials | ✅ FIXED (config + audit) |
| SEC-003 | 🟠 Medium | Well-known default admin passwords in seeders | ✅ FIXED (fail-closed) |
| SEC-004 | 🟢 Good | Startup secrets audit (JWT/CORS/Stripe/admin-pw) | ✅ In place |
| SEC-005 | 🟢 Good | Admin recovery endpoint hardening | ✅ In place |
| SEC-006 | 🟡 Low | `libmagic` not loaded → upload type validation disabled | OPEN (env dep) |

---

## SEC-001 — Regex injection / ReDoS in Mongo `$regex` search 🟠
**Status:** ✅ FIXED — 2026-06-05

**Problem.** ~50+ authenticated, org-scoped search endpoints passed raw
user input straight into Mongo `{"$regex": <user_input>, "$options": "i"}`
**without `re.escape()`**. Impact:
- **ReDoS** — a crafted catastrophic-backtracking pattern can pin CPU.
- **Regex injection** — metacharacters (`.*`, `^`, `$`, `[`) change match
  semantics (still inside the caller's org filter, so no cross-tenant leak).

**Fix.** Added two central helpers in `utils/security_plus.py`:
- `safe_regex(value, options="i")` → escaped **substring** match.
- `safe_regex_exact(value, options="i")` → escaped **whole-string** (`^…$`) match.

Both `re.escape()` the input. Applied across every user-input `$regex` site.
Date prefixes (`^{today_iso}`), internal constants (integration prefixes), and
already-escaped sites (`re.escape`, `_re_escape`, `esc`, `safe`) were left as-is.

**Files updated (substring → `safe_regex`):** crm_v2, crm_core, crm_products,
crm_documents, crm_contracts, master_admin_communications, master_admin_ops,
master_admin_stats_audit, master_admin_documents_lib, master_admin_memberships,
incidents, client_errors, integration_hub, expiry_alerts, issue_helpers,
email_health, service_desk, marketing/contacts, memberships/members,
memberships/members_ops, svc/{inventory,parts,parts_catalogue,legacy_reports,
cases,engineer_equipment,engineer_customers}.

**Files updated (exact → `safe_regex_exact`):** purchase_orders, suppliers_catalogue,
partners (email lookups), crm_picklists, staffing, svc/legacy_reports.

**Files updated (inline `re.escape`):** trust.py (event_type prefix),
pulse_master_admin.py (email prefix/domain).

**Verification.** `tests/test_security_regex_hardening.py` (unit) + live curl:
benign, `.*+[`, and `(a+)+z$` ReDoS payloads all return HTTP 200 in <200ms and
are treated literally.

**Rule for new code:** NEVER write `{"$regex": <user value>, ...}`. Use
`safe_regex()` / `safe_regex_exact()` from `utils.security_plus`.

---

## SEC-002 — CORS `*` wildcard with credentials 🔴 (prod)
**Status:** ✅ FIXED — 2026-06-05

**Problem.** `backend/.env` had `CORS_ORIGINS="*"` while the app sets
`allow_credentials=True` (`server.py`). Wildcard + credentials is an invalid /
unsafe combination.

**Fix.**
- Preview `.env` `CORS_ORIGINS` locked to the explicit frontend origin.
- Production already protected: `utils/secrets_audit.py` flags `*` in prod and
  `server.py` aborts boot on critical findings (`APP_ENV=production`).
- `resolve_cors_origins()` falls back to brand domains in prod, never `*`.

**Deploy note:** set `CORS_ORIGINS` to the real customer domain(s) on every
production deployment.

---

## SEC-003 — Well-known default admin passwords in seeders 🟠
**Status:** ✅ FIXED — 2026-06-05

**Problem.** `routes/crm_auth.py` fell back to `MasterAdmin123!` /
`CRMAdmin123!` if the password env vars were unset — seeding a guessable admin
on any deploy that forgot to configure them. `bootstrap/seed.py` similarly
defaults the master password.

**Fix.** `_seed_crm_user()` is now **fail-closed**: if the password is empty it
logs a warning and skips seeding instead of using a hardcoded default. The
hardcoded fallback strings were removed from `crm_auth.py` (now `""`).

**Residual (prod):** `bootstrap/seed.py` still has a `MasterAdmin123!` default,
but `secrets_audit.py` flags that exact value as critical in production and
aborts boot — so it can never ship. ACCEPTED for dev convenience.

**Rule:** never hardcode a real/default password as an env fallback. Fail closed.

---

## SEC-004 — Startup secrets audit 🟢
**Status:** ✅ In place (`utils/secrets_audit.py`, run at startup in `server.py`)

Checks JWT_SECRET length+entropy, Stripe webhook presence, CORS `*` in prod,
and weak master-admin password. Aborts boot (`sys.exit(2)`) on any critical
finding when `APP_ENV=production`.

---

## SEC-005 — Admin recovery endpoint 🟢
**Status:** ✅ In place (`POST /api/auth/admin-recovery`)

Inert unless `ADMIN_RECOVERY_TOKEN` is set; constant-time token compare
(`secrets.compare_digest`); 1.5s delay on failure. Good break-glass design.

---

## SEC-006 — Upload content-type validation disabled 🟡
**Status:** OPEN (environment dependency)

`server.py` logs: file validation DISABLED because `python-magic` / `libmagic`
isn't loaded → uploads can fail with 415 and MIME sniffing is off. Install
`libmagic1 file` (see `backend/SYSTEM_DEPS.md`) in the deployment image.

---

## Already-good controls (no action needed) 🟢
- Strong 64-char `JWT_SECRET`; HS256 via `utils/auth.py`.
- MFA + compliance secrets Fernet-encrypted (`utils/mfa.py`); `*_enc` fields
  stripped from API responses (`sanitise_docs_for_response`).
- Rate limiting + Cloudflare Turnstile captcha on auth.
- Body-size guard middleware; master-admin IP allowlist (env-gated); SSRF denylist.
- No `eval` / `exec` / `os.system` / `subprocess` in routes or utils.
- JWT revocation (jti deny-list), per-org LLM budget, supplier-token rotation.

---

## How to extend this register
1. Add a new `SEC-00N` section with severity, status, problem, fix, verification.
2. Update the summary table.
3. Bump "Last full review" when you do a fresh sweep.
4. Reference fixes from `tests/` so they stay regression-covered.
