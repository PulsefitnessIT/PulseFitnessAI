# Backup & Restore Runbook

> **Owner**: CTO · **Audience**: On-call engineer, ops lead.
> **Review cadence**: quarterly + after every restore drill.
> **Iter 220br** — split out of `SECURITY_OPS.md` for pen-test / audit
> readiness.

---

## 1 · Service-level commitments

| Metric | Target | Measured from |
|---|---|---|
| **RPO** (Recovery Point Objective) | ≤ 15 minutes | Last successful PITR snapshot to incident detection |
| **RTO** (Recovery Time Objective) | ≤ 4 hours for P0; ≤ 24 h for P1 | Decision-to-restore to read-only restored |
| **Backup retention** | 7-day continuous PITR · 30-day weekly snapshots · 1-year cold (Glacier) | — |
| **Drill cadence** | One full restore-into-staging drill **every quarter** | Calendar Q-end |

These match the public SLA at `/sla` (Annex A, "Data durability").

---

## 2 · Backup matrix

| Data class | Where | Backup method | Frequency | Retention |
|---|---|---|---|---|
| MongoDB primary (all collections) | Atlas cluster | Continuous PITR | every oplog write | 7 days |
| MongoDB weekly snapshot | Atlas cluster | Atlas snapshot | weekly Sunday 02:00 UTC | 30 days |
| MongoDB cold archive | S3 Glacier (eu-west-2) | Atlas → S3 export | monthly 1st | 1 year |
| Static uploads (logo, profile photos, invoice PDFs) | Object store (S3-compatible) | Versioning + cross-region replication | continuous | 30 days versioned + indefinite primary |
| Application code | GitHub `gymaxis/gymaxis-platform` | git history | per commit | indefinite |
| `.env` / secrets | 1Password Secrets Automation | platform-managed | versioned | indefinite, audit log on rotate |

---

## 3 · Pre-flight checks (do these BEFORE you start a restore)

1. **Declare the incident** — open the ticket in the ops channel, post the status-page banner (template in `INCIDENT_RESPONSE_PLAYBOOK.md`).
2. **Identify what is corrupt, not what is missing.** A "data missing" call is often a tenant-scope bug, not a backup case. Run:
   ```bash
   # Spot the row in question across every replica
   db.<collection>.find({"id": "<row-id>"}).pretty()
   ```
3. **Capture the live state first.** Snapshot the current cluster BEFORE restoring over it — you may need both for the post-mortem.
4. **Stop the producers.** If a bad migration / faulty webhook keeps writing corrupt data, pause it via supervisor:
   ```bash
   sudo supervisorctl stop backend
   ```
5. **Communicate the read-only window** to customers (template `T-002` in `INCIDENT_RESPONSE_PLAYBOOK.md` § 4).

---

## 4 · Recovery procedures

### 4.1 Point-in-time restore (PITR) — most common path

Use when corruption was introduced ≤ 7 days ago and the timestamp is known.

```text
1. Atlas → Backups → Continuous Cloud Backup → Restore.
2. Pick "Point in time" and dial back to ~5 minutes BEFORE the
   corruption was first observed.
3. Restore target:  NEW cluster (NEVER overwrite live in step 1).
   Name it gymaxis-restore-<YYYYMMDD>.
4. Wait for status = "Active" (typically 20–45 min for our size).
5. Connect read-only and verify:
   • Row counts on the affected collection match expectations.
   • Spot-check 5 representative records.
   • Run /app/backend/scripts/regression_smoke.sh against it.
6. Promote: stop the live cluster's writes (set ENVIRONMENT=maintenance,
   redeploy), then either:
   (a) Switch MONGO_URL to the restored cluster and deploy, or
   (b) Use Atlas live-migrate to overlay the restored cluster onto
       live (preferred — keeps cluster name stable).
7. Re-enable writes; tail logs for 60 minutes.
```

### 4.2 Weekly snapshot restore — for corruption > 7 days old

Same procedure but step 1 is **Atlas → Backups → Snapshots → Restore**.

### 4.3 Cold archive restore (Glacier) — last-resort

```text
1. AWS console → S3 → Glacier vault gymaxis-mongo-cold.
2. Initiate retrieval (Standard tier: 3–5 h; Expedited: 1–5 min).
3. Download the .archive file when notified.
4. mongorestore --uri "$ATLAS_RESTORE_URI" --archive=<file> --gzip
5. Promote per § 4.1 step 5–7.
```

### 4.4 Single-tenant restore (only one org's data is corrupt)

This is the most common real-world case — a bad bulk import wiped one
org's `crm2_contacts`.

```text
1. PITR restore to a staging cluster (§ 4.1 steps 1-5).
2. Export the affected collection FROM staging FOR THAT ORG ONLY:
   mongoexport --uri="$STAGING_URI" \
     --collection=crm2_contacts \
     --query='{"organization_id":"<org-id>"}' \
     --out=/tmp/org-restore.json
3. On the live cluster, delete the corrupt rows for that org:
   db.crm2_contacts.deleteMany({"organization_id":"<org-id>",
                                "_corrupted_marker": true})
4. mongoimport the staging export back into live.
5. Audit:  await audit_required("ops_restore_audit", {...}).
6. Notify the org via T-003 (single-tenant restore complete).
```

### 4.5 Object-store restore (uploads, invoice PDFs, photos)

```text
1. Identify affected keys (logs/audit will tell you).
2. S3 console → bucket → Versions → restore the prior version.
3. For bulk: use `aws s3api list-object-versions` + a script to flip
   the IsLatest pointer back.
```

---

## 5 · Quarterly restore drill

The drill is the only thing that proves the backups actually work.
Skipping it for two consecutive quarters is a P1 ops incident.

### Drill protocol

1. Pick a Friday morning (low traffic). Notify ops + customer-success.
2. Restore the latest weekly snapshot into a fresh staging cluster
   (§ 4.2).
3. Point a staging-only deploy at the restored cluster.
4. Run the full regression:
   ```bash
   cd /app && make regression
   ```
5. Manually verify:
   * Login flows
   * Stripe checkout (test mode)
   * One GDPR Erasure end-to-end
   * SEO + Social autopilot run-once
6. Record metrics in the drill log (`/app/memory/OPS/DRILL_LOG.md`):
   * Restore start time
   * Restore complete time (= recorded RTO)
   * Snapshot age (= recorded RPO)
   * Regression pass count
   * Any anomalies found
7. Destroy the staging cluster.

### Drill log template

```markdown
## Q1 2026 restore drill — 2026-03-29
- Snapshot used: 2026-03-29 02:00 UTC (snapshot ID xxx)
- Restore start: 09:14 UTC
- Restore complete: 09:51 UTC (RTO observed: 37 min — well inside 4 h)
- Snapshot age: 7 h 14 min (RPO observed — within 15-min target since
  PITR was active and would have been used in a real incident)
- Regression: 1434 / 1434 pass
- Anomalies: none
- Notes: …
```

---

## 6 · Failure modes the team has seen before

| Symptom | Likely cause | Fix |
|---|---|---|
| Atlas restore stuck "Pending" > 60 min | Atlas-side throttling | Open a P1 ticket with MongoDB support; do NOT cancel — re-queueing resets the position |
| `mongorestore` skipped many indexes silently | Source had `background:true` indexes the target rejects | Run `db.<coll>.reIndex()` post-restore |
| PITR target time in the future | Server-time drift on the workstation | Use Atlas UI, not CLI |
| Object-store version listed but `404` on fetch | Glacier-class object, must restore first | Run `s3api restore-object` with `Days=1` before download |

---

## 7 · References

* `SECURITY_OPS.md` § 3 — backup configuration in Atlas.
* `INCIDENT_RESPONSE_PLAYBOOK.md` — comms templates.
* `/sla` (public) — what we promise customers.
* `/sub-processors` (public) — where backups physically live.
