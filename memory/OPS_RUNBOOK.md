# GymAxis — Operations Runbook

> **Status:** Working draft. Iter 220ap (May 27, 2026).
> **Owner:** Master Admin / CTO. Review quarterly + after every incident.
> **Audience:** On-call engineer, customer-success lead, founder.

This is the "what do I do when X breaks" playbook. Anything more elaborate goes into `/app/memory/CODE_REVIEW.md` or `PRODUCTION_READINESS.md`.

---

## 1 · On-call rota

| Day | Primary | Secondary | Phone hours |
|---|---|---|---|
| Mon–Fri 09:00–18:00 UK | Founder / CTO | — | Standard business |
| Mon–Fri OOH | Founder / CTO | — | Best-effort |
| Weekend | Founder / CTO | — | Best-effort |

> **Scale-up trigger:** First paid enterprise contract (>£1k/mo) — formalise a 2-person on-call rota with PagerDuty or Opsgenie.

**Contact channels:**

- Slack: `#gymaxis-ops` (private)
- Phone (P0 only): `<your number>`
- Email: `ops@<your-domain>.com`

---

## 2 · Severity matrix

| Sev | Definition | Response time | Examples |
|---|---|---|---|
| **P0** | Full platform outage OR data leak OR live payment failure for >50% of customers | **< 30 min** ack, status-page update within 60 min | API 500s storm, login broken, customer can see another tenant's data |
| **P1** | Major feature down, no workaround, single tenant affected | **< 2 hr** ack | One org can't load CRM, single-customer Stripe sync stuck |
| **P2** | Feature degraded, workaround available | **< 1 business day** | Slow report queries, broken UI on one screen |
| **P3** | Cosmetic / non-blocking | Next sprint | Typo, misaligned button |

---

## 3 · Detection & monitoring

| Signal | Source | Threshold | Action |
|---|---|---|---|
| Backend up | `GET /api/health` | 200 within 5 s | UptimeRobot every 1 min |
| Frontend reachable | `https://<domain>/` | 200 within 5 s | UptimeRobot every 1 min |
| LLM endpoint health | `GET /api/help/health` | 200 + AI key present | UptimeRobot every 5 min |
| Stripe webhook delivery | Stripe Dashboard → Webhooks | 0 failed deliveries | Manual daily check |
| Email send error rate | `db.email_send_events`, status="failed" | > 5% over 1 h | Master Admin → Email Health pill |
| Client crash rate | `db.client_errors` | > 10 in 1 h | Master Admin → Client crashes panel |
| Sentry | `<sentry-project>` issues > 0 unresolved | New issue, severity ≥ "error" | Sentry email alert |

> **Action item:** Wire UptimeRobot (free tier, 50 monitors) — 15 min of config. See `PRODUCTION_READINESS.md`.

---

## 4 · Common failure modes — diagnosis & fix

### 4.1 Backend not serving traffic (P0)

**Symptoms:** `/api/health` returns 502/503, frontend shows "Network error" on every action.

```bash
# 1. Check supervisor state
sudo supervisorctl status backend

# 2. Tail the most recent logs
tail -200 /var/log/supervisor/backend.err.log
tail -200 /var/log/supervisor/backend.out.log

# 3. Common causes
#    - Bad env var (missing MONGO_URL, malformed RESEND_API_KEY)
#    - MongoDB unreachable (check VPC peering / cluster status in Emergent dashboard)
#    - Module-level import error in a recently-deployed route
#    - Memory pressure (top -p $(pgrep -f uvicorn))

# 4. Restart sequence
sudo supervisorctl restart backend
# Wait 30 s, re-check health:
curl -fsS https://<domain>/api/health | jq
```

**Rollback:** If a recent deploy broke things and you can't fix forward in <15 min, use the **Emergent rollback button** in the chat input (or the `/rollback` slash in the Emergent dashboard) to revert to the last known-good checkpoint.

### 4.2 MongoDB unreachable (P0)

**Symptoms:** Backend logs `pymongo.errors.ServerSelectionTimeoutError`, every API call 500s after ~5 s.

1. **Confirm scope:** Is it our cluster or a platform-wide Emergent incident? Check `https://status.emergent.sh` (or equivalent).
2. **If platform-wide:** Post in status page, post to Slack `#gymaxis-ops`, monitor.
3. **If our cluster only:** Open a P0 ticket with Emergent Support immediately. Provide tenant ID, time of first failure, expected resolution.
4. **Customer comms:** Push a banner on the marketing site within 15 min ("We're investigating a database connectivity issue — your data is safe.").

### 4.3 Email not delivering (P1)

**Symptoms:** Users report not receiving password reset / receipt / engineer assignment emails.

```bash
# 1. Confirm Resend key is set
grep RESEND_API_KEY /app/backend/.env

# 2. Tail email-send events
# (or open Master Admin → Settings & Compliance → Email health)
```

In Mongo:
```python
db.email_send_events.find({"status": "failed"}).sort({"created_at": -1}).limit(20)
```

Common causes:
- **Resend key revoked / quota exceeded** → Log into Resend → API Keys → confirm active. Quota: usage tab.
- **Domain SPF/DKIM broken** → Resend → Domains → confirm green.
- **Recipient bounced** → Look at `error` field on the event.

### 4.4 Stripe webhook deliveries failing (P0/P1)

**Symptoms:** Payments succeed in Stripe but subscription state in our DB is stale.

1. Stripe Dashboard → Webhooks → check failed deliveries.
2. Endpoint should be `https://<domain>/api/payments/stripe/webhook` (or similar — verify in `stripe_routes.py`).
3. Manually re-send failed events from Stripe dashboard once root cause is fixed.

### 4.5 Cross-tenant data leak (P0 — Critical)

**Symptoms:** Customer reports seeing another org's data. Could be in any list endpoint.

1. **Immediate:** Disable the affected endpoint via a feature flag if available, OR roll back the most recent deploy.
2. **Confirm scope:** Run the data-isolation grep:
   ```bash
   cd /app/backend && grep -rn "\.find(" routes/ | grep -v "find_one_and_update" \
     | grep -v "organization_id\|owner_id\|tenant" | head -50
   ```
   Any line without an org filter is suspect.
3. **ICO 72-hour clock starts now.** Notify your DPO.
4. **Customer comms:** Direct email to the affected tenant within 4 hr. Public statement only if more than 1 tenant.
5. **Post-mortem:** Mandatory. Within 5 working days.

### 4.6 GDPR Article 17 erasure request

The platform has a full workflow at **Master Admin → Settings & Compliance → Data Subject Erasure** (or **CRM Settings → Privacy & GDPR**).

1. Receive the request via email (`<your-dpo-email>@<domain>`).
2. **Verify identity** of the data subject (e.g. reply from the registered email + supplementary check — never trust an inbound email alone).
3. In the GDPR Erasure panel, click **+ New erasure request**.
4. Select subject type (Member / Instructor / CRM Contact), paste their UUID from the relevant module, click **Preview**.
5. Confirm the planned PII scrub matches what you'd describe to the subject.
6. File the request. By default a 30-day cooling-off window is enforced — this is your safety net.
7. If the subject demands immediate erasure (their right under Art. 17), open the request and click **Force execute (skip cooling-off)**.
8. After execution, send the data subject a confirmation email + the `scrub_summary` (already saved on the request).
9. **Erased rows are hidden from list endpoints** but the `id` survives so invoices / bookings / audit logs stay referentially intact (Art. 17(3)(b)).

### 4.7 GDPR Article 15 — Subject Access Request

> **Not yet automated.** Process today is manual.

1. Receive request → verify identity.
2. Within 1 month, return a JSON / PDF dump of all PII held about that subject.
3. Use the Master Admin Database Viewer to extract.
4. **TODO (roadmap):** Build `/api/gdpr/sar/export` endpoint to automate.

---

## 5 · Deployment workflow

### 5.1 Standard deploy (Emergent platform)

1. Author changes in Emergent chat / IDE.
2. Wait for auto-commit. The hot-reload picks up most changes within seconds.
3. For `.env` or dependency changes: `sudo supervisorctl restart backend|frontend`.
4. Smoke-test:
   - `curl -fsS https://<domain>/api/health`
   - Open the app, sign in as Master Admin, hit one CRM endpoint.

### 5.2 Rollback

> **Always prefer rollback over fixing-forward when a P0 lands.**

1. Open the Emergent rollback panel.
2. Pick the last known-good checkpoint (one before the breaking change).
3. Confirm. Hot-reload picks it up.
4. Verify via `curl /api/health`.
5. Post in `#gymaxis-ops`.

### 5.3 Database migrations

Currently MongoDB collections are schema-less. **No formal migration system.** If you need to backfill:

1. Write the script in `/app/backend/scripts/backfill_<thing>.py`.
2. Wrap in `if __name__ == "__main__"` so it never runs at import time.
3. Test against a single tenant first (`organization_id` filter).
4. Run from inside the pod: `cd /app/backend && python3 scripts/backfill_<thing>.py --dry-run` first.

---

## 6 · Customer-facing communication templates

### 6.1 Active incident (status page banner)

> **Active incident** — *<service>* is experiencing degraded performance. We're investigating. First update at *<time + 30 min>*. Your data is safe.

### 6.2 Incident resolved

> **Resolved (<time>)** — The incident affecting *<service>* between *<start>* and *<end>* is fully resolved. A post-mortem will be published within 5 working days at `<post-mortems URL>`.

### 6.3 Tenant-specific outage

```
Subject: GymAxis service interruption — <date>

Hi <name>,

Between <start> and <end> UK time on <date>, your GymAxis account experienced
<symptom>. We've identified the root cause as <one sentence> and shipped a fix.

What we're doing:
- <action 1>
- <action 2>

What you don't need to do: nothing was lost — your data is intact, and no
action is required from you.

If you have any questions, reply directly to this email and I'll come back to
you the same day.

— <your name>, GymAxis
```

### 6.4 Personal data breach (Art. 33/34 UK GDPR)

> **Do not improvise this.** Hand to your DPO / legal counsel within 1 hour of confirmed leak. ICO 72-hour clock is non-negotiable. Use the ICO template at https://ico.org.uk/.

---

## 7 · Regular maintenance jobs

| Cadence | Job | Owner | Where |
|---|---|---|---|
| Daily | Eyeball `Master Admin → Overview → Platform issues 24h` | On-call | Web UI |
| Daily | SEO Autopilot daily article + social publish | Automated (server.py asyncio loop) | Backend |
| Weekly | Review `db.client_errors` for new patterns | On-call | Mongo |
| Weekly | Check Stripe failed webhook deliveries | On-call | Stripe dash |
| Monthly | Partner Engineer monthly reputation report | Automated | Backend |
| Monthly | Test the GDPR erasure workflow on a dummy account | On-call | UI |
| Quarterly | Review + rotate API keys (Resend, Stripe, OpenAI, Emergent LLM) | CTO | `.env` |
| Quarterly | Restore drill — request from Emergent Ops | CTO | Email |
| Quarterly | Update `OPS_RUNBOOK.md` with new failure modes seen | On-call | Repo |

---

## 8 · Useful endpoints

| Purpose | Endpoint |
|---|---|
| Health probe | `GET /api/health` |
| Email health pill | Master Admin → Email Health |
| Sentry issues | `<sentry-project>` |
| Status page | `https://status.<your-domain>.com` *(TODO — set up Cachet / Statuspage / BetterStack)* |
| Mongo viewer | Master Admin → Settings & Compliance → Database viewer |
| Audit log | Master Admin → Settings & Compliance → Compliance trail |
| GDPR erasure | Master Admin → Settings & Compliance → Data Subject Erasure |
| Archive (soft-delete) | Master Admin → Settings & Compliance → Archive |
| Login events | Master Admin → Settings & Compliance → Login events |

---

## 9 · Escalation contacts (fill in)

| Role | Name | Email | Phone |
|---|---|---|---|
| Founder / CTO | `<>` | `<>` | `<>` |
| DPO | `<>` | `<>` | — |
| Legal counsel | `<>` | `<>` | `<>` |
| Insurance broker (cyber) | `<>` | `<>` | `<>` |
| Emergent Ops | — | `support@emergent.sh` | — |
| Stripe support | — | via dashboard | — |
| Resend support | — | `support@resend.com` | — |
| MongoDB Atlas support *(if direct)* | — | via Atlas | — |
| ICO (UK regulator) | — | `casework@ico.org.uk` | `0303 123 1113` |

---

## 10 · Post-incident review (mandatory for P0/P1)

Within 5 working days of any P0/P1, file a post-mortem in `/app/memory/post-mortems/<date>-<slug>.md` using this template:

```markdown
# Post-mortem: <one-line title>

**Date of incident:** <date + time UK>
**Duration:** <minutes>
**Severity:** P0 / P1
**Tenants affected:** <count or "all">

## What happened (timeline)

- HH:MM — <event>
- HH:MM — <event>

## Root cause

<one paragraph>

## How we detected it

<one paragraph>

## How we fixed it

<one paragraph>

## What went well

- <bullet>

## What didn't

- <bullet>

## Action items

| # | Action | Owner | Due |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
```

---

*Maintained alongside the codebase. Last updated Iter 220ap (May 27, 2026).*
