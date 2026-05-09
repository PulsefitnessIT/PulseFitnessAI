# Security Operations Runbook

**Audience**: DevOps / Platform engineers preparing GymAxis for Pulse-Fitness-grade enterprise rollout.

This document covers controls that are **operational** (not code-level). The code-level controls are documented inline in `/app/memory/PRD.md` and surfaced publicly at `/security`.

---

## 1. Prod environment variables (authoritative list)

Set these in production `.env` / secret manager. **Unset dev overrides** before going live.

### Core (must set)
```bash
MONGO_URL=mongodb+srv://...            # prod MongoDB Atlas cluster
DB_NAME=gymaxis_prod
JWT_SECRET=<64-char urandom hex>
ENVIRONMENT=production                 # triggers CORS fail-fast
CORS_ORIGINS=https://app.gymaxis.ai,https://pulse.gymaxis.ai
MASTER_ADMIN_EMAIL=admin@gymaxis.ai
MASTER_ADMIN_PASSWORD=<generated, 24+ chars, stored in 1Password>
```

### Security hardening (must set)
```bash
MFA_ENCRYPTION_KEY=<python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'>
MASTER_ADMIN_IP_ALLOWLIST=203.0.113.0/24,198.51.100.5   # your office / VPN ranges
CAPTCHA_PROVIDER=turnstile                              # or hcaptcha
CAPTCHA_SECRET=<from provider dashboard>
CAPTCHA_SITE_KEY=<from provider dashboard>
PASSWORD_MAX_AGE_DAYS=180
PII_RETENTION_DAYS=365
```

### Dev-only (MUST be unset in prod)
These are permissive overrides for the test harness. If they appear in prod, rate-limiting is effectively disabled:
```bash
LOGIN_RATE_LIMIT_MAX=                  # code default: 5 / 300 s
LOGIN_RATE_LIMIT_WINDOW=
REGISTER_RATE_LIMIT_MAX=               # code default: 3 / 3 600 s
REGISTER_RATE_LIMIT_WINDOW=
```

---

## 2. Web Application Firewall (WAF)

We do not ship a WAF in-app — it belongs at the edge. Use one of:

### 2a. Cloudflare (recommended)

1. Add your prod domain to Cloudflare, proxy orange-cloud ON.
2. Enable **OWASP Core Rule Set** (Security → WAF → Managed Rules → "Cloudflare OWASP Core Ruleset"). Action: **Block**, Paranoia: 2.
3. Enable **Cloudflare Managed Ruleset**. Action: **Block**.
4. Add **Custom rules** for:
   - `(http.request.uri.path contains "/api/auth/login" and cf.threat_score gt 30) → Block`
   - `(http.request.uri.path contains "/api/master-admin/" and ip.src ne <office IPs>) → Block` (defence in depth alongside our app-level allowlist)
   - `(http.request.method eq "POST" and http.request.uri.path eq "/api/support/ask" and rate(1m) > 10) → Challenge`
5. Turn on **Bot Fight Mode** (or the Enterprise Bot Management if you have it).
6. Turn on **Under Attack Mode** only during active incidents.
7. Lock down `api.gymaxis.ai` certificate to **Full (strict)**.

### 2b. AWS WAF (if hosted on AWS)

Attach a WebACL to your ALB / CloudFront with:
- `AWSManagedRulesCommonRuleSet`
- `AWSManagedRulesKnownBadInputsRuleSet`
- `AWSManagedRulesSQLiRuleSet`
- `AWSManagedRulesATPRuleSet` (Account Takeover Prevention — works against our `/api/auth/login` path)
- Custom rate-based rule: 200 req / 5 min per IP at ALB level.

---

## 3. Backup & disaster recovery

### MongoDB Atlas
- Enable **Continuous Backup** with 7-day PITR (point-in-time restore).
- Weekly snapshot retention: 30 days.
- Monthly cold snapshot to S3 Glacier: 1 year.
- Quarterly **restore drill**: restore latest snapshot into a staging cluster, run the full pytest suite against it, confirm all security tests still pass.

### Secrets
- All `.env` values in a secret manager (Vault, AWS Secrets Manager, or 1Password Secrets Automation).
- Rotate `JWT_SECRET` + `MFA_ENCRYPTION_KEY` every 90 days. **Note**: rotating JWT_SECRET invalidates every session (by design). Schedule during low-traffic windows.

---

## 4. Monitoring & alerting

Forward FastAPI + MongoDB logs to a SIEM (Datadog / CloudWatch / Splunk). Minimum alerts:

| Signal | Severity | Trigger |
|---|---|---|
| `event=mfa.verify.fail` rate > 5/min for a single user | P2 | Likely brute force |
| HTTP 429 rate > 100/min globally | P2 | Rate limiter tripped — investigate |
| 5xx rate > 1% over 5 min | P1 | Apply standard incident response |
| `event=pii.retention.purged` | P3 info | Weekly sanity check |
| Absent heartbeat on `/api/health` for 60 s | P1 | Page on-call |

---

## 5. Static + supply-chain scans (CI)

Add these jobs to your GitHub Actions workflow:

```yaml
# .github/workflows/security.yml
name: Security
on: [push, pull_request]
jobs:
  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit pip-audit
      - run: cd backend && python scripts/security_scan.py --strict
  codeql:
    uses: github/codeql-action/.github/workflows/codeql.yml@v3
```

Dependabot weekly updates are configured in `/.github/dependabot.yml`.

---

## 6. Incident response — MFA lockout

If a master admin loses their MFA device:

1. Another master admin runs:
   ```python
   # Mongo shell
   db.user_mfa.deleteOne({user_id: "<user-id>"})
   ```
2. The locked-out admin re-enrols on next login.
3. The event is audit-logged automatically (`mfa.disabled` + subsequent `mfa.enabled`).
4. Review `security_audit_log` collection for any anomalous activity in the 24 h prior.

---

## 7. SSO (SAML/OIDC) — on-demand roadmap

Not yet implemented. Ship when a customer (likely Pulse Fitness) names their IdP. Typical scope:
- Add Authlib / python-saml dependency.
- Introduce `/api/auth/sso/{provider}` + `/api/auth/sso/callback` endpoints.
- Allow-list IdPs per org (stored on `organizations.sso` object).
- Mint JWT after successful IdP assertion; bypass password + MFA checks (trust the IdP).
- Audit-log every SSO login with provider name.
- Estimated: 2–3 engineering days per provider.


---

## 8. Static analysis baseline (ruff + bandit)

Run locally or in CI:
```bash
bash /app/backend/scripts/security-scan.sh
```

What runs:
- **ruff** — pycodestyle (E/W), pyflakes (F), pyupgrade (UP), bugbear (B), simplify (SIM), mccabe complexity. Config: `backend/pyproject.toml`.
- **bandit** — Python security linter. Severity threshold: **Medium+** (Low is intentionally noisy on `try/except/pass` storage paths). Config: `backend/pyproject.toml` (`[tool.bandit]`).

**Baseline (2026-02):**
- ruff: 0 errors.
- bandit: 0 High, 0 Medium, 94 Low (all reviewed).

**Why the bandit skips?**
Each entry in `[tool.bandit].skips` is justified inline in `pyproject.toml`:
- `B101` asserts → pytest fixtures.
- `B311` `random` → jitter / sampling, never crypto.
- `B404/B603/B607` subprocess → fixed argv, no shell strings.
- `B105/B106/B107` hardcoded password → false-positive on field names like `password_hash`. We rely on `.env` discipline + `purge_test_artefacts.py` review.

**XML parsing**: All untrusted XML (manufacturer sitemaps) goes through `defusedxml.ElementTree` — see `utils/manufacturer_catalogue.py`.

**Adding a new dependency that pulls in `subprocess.shell=True`, `eval`, `pickle.loads`, or untrusted XML?** Add a `# nosec BXXX -- <reason>` comment **and** mention it in this section so the next reviewer doesn't have to re-investigate.
