# GymAxis — Service Level Agreement (SLA)

> **Status:** TEMPLATE — must be reviewed by your solicitor before binding any customer. Replace `<>` placeholders before use.
> **Effective date:** `<go-live date>`
> **Version:** 1.0

This SLA forms part of the [GymAxis Terms of Service](TERMS_OF_SERVICE.md) and applies to all paid plans unless a signed Order Form modifies it.

---

## 1 · Definitions

- **"Service"** — the GymAxis web application, including the Master Admin, CRM, Memberships, Service Desk, Engineer App and Public Marketing Site, accessed via `<your-domain>.com` and any sub-domains operated by us.
- **"Uptime"** — the percentage of minutes in a calendar month during which the Service responds to a `GET /api/health` request with HTTP 200 within 5 seconds.
- **"Excluded Time"** — scheduled maintenance announced at least 48 hours in advance; downtime caused by Customer-side issues (Customer's network, credentials, third-party integrations they connect themselves); Force Majeure as defined in §10 of the ToS.
- **"Incident"** — a continuous period of more than 5 minutes during which the Service is below the Uptime threshold.

---

## 2 · Uptime commitments

| Plan tier | Monthly Uptime target | Measurement window |
|---|---|---|
| **Starter** | 99.0% | Calendar month |
| **Growth** | 99.5% | Calendar month |
| **Enterprise** | 99.9% | Calendar month, OOH support included |

> The single-pod preview environment currently used by trials is **not covered** by this SLA. Production deployments only.

---

## 3 · Service credits

If we miss the Uptime target in a calendar month, the Customer is entitled to a **service credit** against the next monthly invoice, calculated against the **affected workload's** monthly fee:

| Monthly Uptime measured | Credit (Starter) | Credit (Growth) | Credit (Enterprise) |
|---|---|---|---|
| ≥ Target | — | — | — |
| Below target, ≥ 95.0% | 10% | 15% | 20% |
| ≥ 90.0%, < 95.0% | 25% | 30% | 35% |
| < 90.0% | 50% | 50% | 75% |

- Service credits are the Customer's **sole and exclusive remedy** for failure to meet the Uptime target.
- Maximum credit in any calendar month: **100%** of that month's affected workload fee.
- Credits do not accumulate beyond the month earned and have no cash value.
- Customer must submit a credit request within **30 days** of the end of the affected month, in writing to `<billing@your-domain.com>`, with reasonable supporting evidence (timestamps, screenshots, request IDs).

---

## 4 · Support response times

| Severity | Definition | Response (initial ack) | Update cadence |
|---|---|---|---|
| **P0 — Critical** | Service unavailable, data leak, or live payment failure for the Customer's tenant | ≤ 30 min (24×7 for Enterprise; UK business hours otherwise) | Every 60 min until resolved |
| **P1 — Major** | Major feature unusable, no workaround | ≤ 2 hr (UK business hours) | Every 4 hr |
| **P2 — Minor** | Feature degraded, workaround available | ≤ 1 business day | Daily |
| **P3 — Cosmetic** | Non-blocking | Next sprint | On request |

Support channel: `support@<your-domain>.com` (all tiers) · Slack Connect (Growth + Enterprise) · Phone (Enterprise only, OOH for P0 only).

---

## 5 · Scheduled maintenance

- GymAxis will publish maintenance windows on `https://status.<your-domain>.com` at least **48 hours** in advance.
- Routine maintenance is targeted at **02:00–05:00 UK time**, max **once per calendar month**, max **4 hours** per window.
- Emergency maintenance (e.g. critical security patch) may be performed with **shorter notice**; this time IS counted toward Excluded Time.

---

## 6 · Backup & restore commitments

- **RPO (Recovery Point Objective):** ≤ 1 hour for Growth + Enterprise; ≤ 24 hours for Starter. (Subject to Emergent Ops confirmation — see `EMERGENT_OPS_EMAIL.md`.)
- **RTO (Recovery Time Objective):** ≤ 4 hours during UK business hours, ≤ 12 hours OOH (Enterprise: 24×7 4-hour RTO).
- Backups are retained for **30 days** rolling.
- A restore drill is conducted at least **annually**; Enterprise customers may request to observe.

---

## 7 · Incident communication

Customers will be notified of any incident affecting their tenant via:

1. **Status page** (`https://status.<your-domain>.com`) — within 15 minutes of detection.
2. **Email** to the primary technical contact for P0/P1 incidents.
3. **Post-mortem** published within 5 working days for any P0 or any P1 lasting > 4 hours.

---

## 8 · Security incident notification

A confirmed personal-data breach affecting Customer Personal Data triggers the breach-notification obligations defined in our [Data Processing Agreement](DATA_PROCESSING_AGREEMENT.md). We will notify the Customer **without undue delay and within 72 hours** of becoming aware (UK ICO clock).

---

## 9 · Modifications

GymAxis may modify this SLA with **60 days' written notice**. If the modification is materially adverse, the Customer may terminate the affected workload at the end of the notice period without penalty.

---

## 10 · Contact

- Service credits: `billing@<your-domain>.com`
- Support: `support@<your-domain>.com`
- Status page: `https://status.<your-domain>.com`
- Security: `security@<your-domain>.com`
- Data Protection Officer: `dpo@<your-domain>.com`

---

*Template last updated Iter 220ap (May 27, 2026). Have your solicitor amend before signing customer contracts.*
