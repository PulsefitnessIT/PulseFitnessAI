# Emergent Ops — Backup & Restore Confirmation Request

**Status:** Draft — copy/paste into your email client, fill in `<>` placeholders, send.

**To:** `support@emergent.sh` (or your dedicated Emergent Ops contact)
**Cc:** Your co-founder / CTO
**Subject:** GymAxis (preview env: maintenance-hub-357) — MongoDB backup cadence + restore drill request — pre-launch

---

Hi team,

We're about three weeks from soft-launching **GymAxis** to paying UK fitness operators (preview env: `maintenance-hub-357.preview.emergentagent.com`, custom domain landing on `<your-domain>.com`).

Before we take a card, I need written confirmation of a few operational guarantees that I cannot derive from the platform docs. Can you reply with the following:

### 1. MongoDB backup cadence (RPO)

- What is the snapshot frequency on our cluster? *(Hourly / 6-hourly / daily?)*
- How many days of snapshots are retained?
- Is point-in-time recovery available, and if so, to what granularity?
- Are backups stored in a separate region from primary?

**Our target:** RPO ≤ 1 hour. Please confirm whether the current plan meets this or whether we need to upgrade tier.

### 2. Restore time (RTO)

- In a worst-case scenario (e.g. cluster lost, app pod corrupted), what's your typical wall-clock from "we open a ticket" to "service restored from latest snapshot"?
- Is there a self-serve restore option in the dashboard or is every restore ticket-driven?

**Our target:** RTO ≤ 4 hours during UK business hours, ≤ 12 hours OOH.

### 3. Restore drill

- Can we book a **practice restore** in the next 2 weeks against a staging snapshot? We need this for our ICO compliance evidence pack (we're holding gym-member PII — UK GDPR) and to seed our internal runbook.
- If self-serve isn't available, please quote effort + lead time.

### 4. Region / data residency

- Where is our MongoDB cluster physically located? *(UK-South / EU-West / other?)*
- Where are backups stored?
- We need this in writing for our DPA + sub-processor list.

### 5. SLA / uptime

- What uptime % do you commit to for the underlying infrastructure?
- What's the credit schedule for downtime?
- Where's the published status page we can point our customers to?

### 6. Incident notification

- If you detect a security incident affecting our tenant (or the broader platform) that touches our data, what's the notification SLA?
- We are bound by the **UK ICO 72-hour clock** for any personal-data breach. We need your detection-to-notification time to fit inside that window.

### 7. Account contacts on file

Please confirm the following are on your records for breach / billing escalation:

- **Primary technical contact:** `<full name>`, `<email>`, `<phone>`
- **Billing contact:** `<full name>`, `<email>`
- **Data Protection contact (DPO or equivalent):** `<full name>`, `<email>`

---

If any of the above isn't available on our current tier, please quote the upgrade. We'd rather pay for the right tier than discover the gap after a real incident.

Happy to jump on a 20-minute call this week if it's faster than email.

Thanks,
`<your name>`
GymAxis · Founder / CTO
`<email>` · `<phone>`
