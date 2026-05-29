# Pre-Launch Go / No-Go Checklist

> **Owner**: CTO · **Audience**: Founder, ops lead, board.
> **Iter 220br** — single source of truth a non-technical decision-maker
> can sign off on before each public-facing launch (new region, new
> brand, enterprise customer onboarding, pen-test invitation, ICO
> audit).
>
> **Use**: print this, walk through it, tick each box, sign at the
> bottom. **Any unchecked P0 line = launch is NOT cleared.**

---

## P0 — Hard gates (launch is blocked if any of these fail)

### Security
- [ ] `make regression` returns **0 failures** on the deploy commit
- [ ] OWASP Top 10 review signed off — see `SECURITY_AUDIT_2026Q1.md`
- [ ] All P0/P1 findings from the latest pen test are closed
- [ ] `MASTER_ADMIN_PASSWORD` rotated within last 90 days, stored in 1Password
- [ ] `JWT_SECRET` is the production value (NOT the dev default), 64+ hex chars
- [ ] `MFA_ENCRYPTION_KEY` is set in prod env
- [ ] `CORS_ORIGINS` env var is set to **only** the production brand domains
- [ ] `ENVIRONMENT=production` so CORS fail-fast triggers
- [ ] CSP / HSTS / X-Content-Type-Options headers verified live (`curl -I https://<domain>/`)
- [ ] Cloudflare WAF (or equivalent) enabled, OWASP Core Ruleset = Block
- [ ] Bot Fight Mode on at the edge
- [ ] No dev-override rate-limit env vars set in prod (`LOGIN_RATE_LIMIT_*`, etc.)

### Data & GDPR
- [ ] `/privacy`, `/terms`, `/legal/dpa`, `/legal/dpia`, `/sla`,
      `/sub-processors`, `/refunds` all return 200 in prod
- [ ] Sub-processors list at `/sub-processors` matches reality (every
      vendor on this list has a signed DPA on file)
- [ ] GDPR Article 17 auto-executor confirmed running in prod
      (boot log: `[gdpr-erasure] auto-executor started`)
- [ ] PII retention purge confirmed running (env `PII_RETENTION_DAYS` set)
- [ ] At least one quarterly restore drill completed within last 90 days
      — log entry in `DRILL_LOG.md`
- [ ] Data Processing Records (`ROPA`) up to date — see `LEGAL/DATA_PROCESSING_AGREEMENT.md` § Annex C
- [ ] DPO contact (`dpo@gymaxisai.com` or equivalent) is monitored

### Ops / availability
- [ ] On-call rota in place and someone is paged-up tonight
- [ ] PagerDuty / phone numbers in `INCIDENT_RESPONSE_PLAYBOOK.md` § 7 are current
- [ ] Status page (`/status`) reachable and tested
- [ ] Atlas continuous PITR enabled (7-day window)
- [ ] Atlas weekly snapshots enabled (30-day retention)
- [ ] Atlas monthly cold-archive enabled (1-year retention)
- [ ] Backup/restore runbook reviewed within last 90 days
- [ ] Incident-response playbook reviewed within last 90 days
- [ ] Bounce monitoring + DMARC pass rate ≥ 95 % over last 7 days

### Commercial / legal
- [ ] Terms of Service version stamp matches the dated-version on `LEGAL/TERMS_OF_SERVICE.md`
- [ ] SLA (`/sla`) language matches what's in any signed enterprise contract
- [ ] Refund policy linked from every paid checkout flow
- [ ] Cookie banner on first-visit, "Essential only" works without account
- [ ] Customer-facing email footer mentions company name, registered address, VAT number

## P1 — Soft gates (launch ok, but fix within 30 days)

- [ ] Quarterly restore drill — drill due before next quarter ends
- [ ] DPIA refreshed if any new processing surface launched
- [ ] Pen-test report scheduled — date booked with external tester
- [ ] CodeQL / Semgrep added to CI quality-gate
- [ ] Datadog (or equivalent) APM in place; baseline alerts firing on staging
- [ ] All blocking 3rd-party integrations have a "live credentials" path documented (DocuSign, Outlook, Sicon, Twilio)
- [ ] Branding pass complete on every legal page (footer logo + colours match)

## P2 — Nice-to-have

- [ ] Customer-facing post-mortem catalogue at `/trust/post-mortems` populated
- [ ] SOC 2 Type I evidence collection started
- [ ] ISO 27001 gap analysis kicked off
- [ ] Bug-bounty programme (HackerOne / Intigriti) live

---

## Document inventory — every link customers / auditors will request

| Document | Public URL | Memory source | Last reviewed |
|---|---|---|---|
| Privacy Policy | `/privacy` | `LEGAL/PRIVACY_POLICY.md` | _fill in_ |
| Terms of Service | `/terms` | `LEGAL/TERMS_OF_SERVICE.md` | _fill in_ |
| Refund & Cancellation | `/refunds` | `LEGAL/REFUND_POLICY.md` (if separate) | _fill in_ |
| DPA | `/legal/dpa` | `LEGAL/DATA_PROCESSING_AGREEMENT.md` | _fill in_ |
| DPIA | `/legal/dpia` | `LEGAL/DPIA.md` (if separate) | _fill in_ |
| SLA | `/sla` | `LEGAL/SLA.md` | _fill in_ |
| Sub-processors | `/sub-processors` | `LEGAL/SUB_PROCESSORS.md` | _fill in_ |
| Security & Trust | `/security`, `/trust` | `SECURITY_OPS.md`, `SECURITY_AUDIT_2026Q1.md` | _fill in_ |
| Status page | `/status` | live data | continuous |
| Operations runbook | _internal_ | `OPS_RUNBOOK.md` | _fill in_ |
| Backup / restore runbook | _internal_ | `OPS/BACKUP_RESTORE_RUNBOOK.md` | _fill in_ |
| Incident response playbook | _internal_ | `OPS/INCIDENT_RESPONSE_PLAYBOOK.md` | _fill in_ |
| Email deliverability runbook | _internal_ | `OPS/EMAIL_DELIVERABILITY_RUNBOOK.md` | _fill in_ |
| Domain cutover runbook | _internal_ | `DOMAIN_CUTOVER_RUNBOOK.md` | _fill in_ |
| Security audit (current) | _internal_ | `SECURITY_AUDIT_2026Q1.md` | _fill in_ |
| Production readiness | _internal_ | `PRODUCTION_READINESS.md` | _fill in_ |

---

## Sign-off

I confirm every **P0** box above is ticked. Outstanding **P1/P2**
items have owners and due dates logged in our project tracker.

* Founder · _____________________ · _____ / _____ / _____
* CTO · _____________________ · _____ / _____ / _____
* DPO · _____________________ · _____ / _____ / _____
