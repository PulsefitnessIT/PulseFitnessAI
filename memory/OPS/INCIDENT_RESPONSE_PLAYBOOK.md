# Incident Response Playbook

> **Owner**: CTO · **Audience**: On-call engineer, customer-success, founder.
> **Review cadence**: quarterly + post-mortem of every P0/P1.
> **Iter 220br** — formalises what was previously sprinkled across
> `OPS_RUNBOOK.md` and `SECURITY_OPS.md`. The OPS runbook stays the
> deep "how to diagnose specific failures" reference; this doc is the
> **process** — severity, comms ladder, post-mortem.

---

## 1 · Severity matrix

| Severity | Definition | Response time (acknowledge) | First-update cadence | Examples |
|---|---|---|---|---|
| **P0 — Critical** | Customer-facing platform down OR confirmed data leak / cross-tenant exposure | **15 min** | every 30 min until resolved | Backend 500s on all traffic · Stripe charged the wrong tenant · Data subject sees another org's data |
| **P1 — High** | Major feature broken OR security control compromised (no leak yet) | **1 h** during work hours, **2 h** OOH | every 60 min | Login broken · MFA bypass · Webhook backlog > 1 h · GDPR Auto-Executor stalled > 48 h |
| **P2 — Medium** | Non-critical degradation affecting one workflow | **next working day** | daily | One CRM picklist not saving · Email open-tracking broken · Slow-loading dashboard |
| **P3 — Low** | Cosmetic / single-customer · no SLA impact | **next sprint** | as fixed | Typo · misaligned button · stale doc |

> **Auto-escalate P2 → P1** if it affects > 5 organisations OR the affected
> org is on the Enterprise tier.

## 2 · Notification ladder

```
Detection
  └─ Auto: Datadog / status-page integration / Trust Backbone webhook
  └─ Manual: customer ticket / support agent flag
       │
       ▼
On-call engineer  (PagerDuty / phone / Slack-bot)
       │
       ▼  P0/P1
CTO + Founder    (SMS + Slack #incidents)
       │
       ▼  P0 only, or P1 > 4 h
Customer-success lead
       │
       ▼  P0 confirmed data leak
DPO  →  ICO 72-hour clock starts (UK GDPR Art. 33)
```

## 3 · Incident lifecycle

```
1. DETECT     →  Open incident ticket, assign IC (incident commander).
                 P0/P1: post status-page banner (T-001) within 15 min.
2. CONTAIN    →  Stop the bleeding. Most common: kill the bad deploy,
                 pause the affected background loop, or rate-limit the
                 abusive caller. NEVER troubleshoot before contain.
3. INVESTIGATE→  Pull logs, run reproducers in staging. IC keeps the
                 ticket updated every cadence.
4. ERADICATE  →  Ship the fix. Code change goes through normal PR
                 review + CI even during P0 (no merge-without-review
                 except for revert-only emergency rollback).
5. RECOVER    →  Verify in prod. Tail logs for at least the same
                 duration as the incident lasted.
6. POST-MORTEM→  Blame-free write-up within 5 working days (template
                 in § 5). Publish customer-facing version to
                 /trust/post-mortems.
```

## 4 · Customer-facing comms templates

### T-001 — Active incident (status page banner)
> **Active incident** — *<service>* is experiencing degraded
> performance starting ~*<time>*. We're investigating. First update at
> *<time + 30 min>*. **Your data is safe.**

### T-002 — Read-only maintenance window
> **Planned maintenance** — between *<start>* and *<end>* the platform
> will be **read-only** while we complete a restore. Logins still work;
> writes will queue and replay automatically.

### T-003 — Single-tenant restore complete
> *<Org name>*, your *<collection>* data has been restored from a
> *<timestamp>* snapshot. *N* rows were recovered. If anything still
> looks wrong, reply to this email and we'll re-investigate.

### T-004 — Resolved (status page)
> **Resolved (*<time>*)** — The incident affecting *<service>* between
> *<start>* and *<end>* is fully resolved. A post-mortem will be
> published within 5 working days at
> https://gymaxisai.com/trust/post-mortems.

### T-005 — Personal data breach (Art. 33/34 UK GDPR)
> *<Customer/Data Subject name>*, we are writing to inform you that
> between *<start>* and *<end>* personal data of yours was *<scope>*.
> No action is required from you at this time. We have already taken
> the following steps: *<contained / patched / audited>*. The
> Information Commissioner's Office has been notified.
>
> If you have questions, contact our Data Protection Officer at
> dpo@gymaxisai.com.

## 5 · Post-mortem template (blameless)

```markdown
# Post-mortem · YYYY-MM-DD · <one-line title>

**Severity**: P0/P1/P2  
**Detected**: 14:23 UTC by <Datadog alert | customer ticket>  
**Mitigated**: 14:51 UTC  
**Resolved**: 15:42 UTC  
**Customer impact**: <N orgs · M users · X minutes>  
**Data impact**: <none | listed below>

## Timeline
| UTC | Event |
|---|---|
| 14:23 | Datadog alert: backend 5xx rate > 1 % |
| 14:24 | On-call paged; CTO ACK'd |
| …     | … |
| 15:42 | All-clear posted to /status |

## Root cause
*One paragraph. Cause, not symptom. Cite the commit / migration / config change.*

## Why didn't we catch it earlier?
*Be honest. The point of this section is to learn, not to blame.*

## What went well
*At least 3 items. Recognition matters.*

## What went badly
*At least 3 items. Be specific.*

## Action items (with owners + due dates)
- [ ] <thing> — @owner — by YYYY-MM-DD
- [ ] <thing> — @owner — by YYYY-MM-DD

## Customer-facing summary
*<2-3 sentences that will go up at /trust/post-mortems/YYYY-MM-DD>*
```

## 6 · Standing playbooks for known scenarios

For step-by-step diagnostic flows, see:
* `OPS_RUNBOOK.md` § 4 — Backend down / Mongo unreachable / Email
  not delivering / Stripe webhook failing / Cross-tenant leak / GDPR
  request.
* `BACKUP_RESTORE_RUNBOOK.md` — anything requiring data recovery.
* `EMAIL_DELIVERABILITY_RUNBOOK.md` — bounce-rate or spam-folder issues.
* `DOMAIN_CUTOVER_RUNBOOK.md` — DNS / certificate / brand handover.

## 7 · External contacts (for P0)

| Service | Contact | When |
|---|---|---|
| MongoDB Atlas support | Atlas console → Support → "Create case" (24/7 P1) | DB layer outage |
| Stripe support | dashboard.stripe.com/support — pick "Webhook delivery" or "Payment dispute" | Payment platform outage |
| Resend support | help@resend.com — P1 channel | Email delivery halted |
| Emergent platform support | help@emergent.sh | Platform-level outage |
| ICO breach line | 0303 123 1113 (work hours) / report.ico.org.uk | Personal data breach (Art. 33) |
| Cyber-insurance broker | *<add when policy purchased>* | Suspected ransomware / data exfil |

## 8 · After every P0/P1

1. Publish the post-mortem within 5 working days.
2. Add a regression test that would have caught it.
3. Update the relevant runbook with the new failure mode.
4. Walk the team through it at the next ops review.
