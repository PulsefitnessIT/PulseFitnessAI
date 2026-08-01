# PulseFitness.ai — Personal Data Breach Notification Runbook

**Owner:** DPO / Founder · **Applies to:** all staff · **Prepared:** 2026-08-01
**Legal basis:** UK GDPR Articles 33 (notify ICO) & 34 (notify data subjects); DPA 2018
**Golden rule:** the **72-hour clock to notify the ICO starts when Pulse becomes *aware* of a breach** — not when it's fully understood. When in doubt, treat it as a breach and start the clock.

> A "personal data breach" = any breach of security leading to accidental or unlawful **destruction, loss, alteration, unauthorised disclosure of, or access to** personal data. This includes cross-tenant data exposure (e.g. one customer seeing another's data), lost devices, mis-sent emails, ransomware, and credential compromise.

---

## 1. Roles

| Role | Who | Responsibility |
|---|---|---|
| **Incident Lead** | Founder (or delegate) | Owns the response, decisions, comms |
| **DPO / Privacy** | [NAME] | ICO/data-subject notification calls, register |
| **Engineering** | [NAME] | Contain, investigate, remediate, preserve logs |
| **Hosting liaison** | Emergent support | Infra logs, containment at platform level |

**Emergency contacts:** [FILL IN — Founder, DPO, Eng on-call, Emergent support]

---

## 2. The 6 steps

### Step 1 — Detect & report (immediately)
Anyone who suspects a breach reports to the **Incident Lead** at **[email/phone]** immediately. Log the time you became aware — this starts the 72-hour clock.

### Step 2 — Contain (within hours)
- Revoke compromised credentials / sessions (JWT deny-list), rotate secrets.
- For cross-tenant exposure: disable/gate the affected endpoint or feature immediately (as done for the MOD Quote Writer, 2026-07-31).
- Ask Emergent to assist with any platform-level containment.
- **Preserve evidence**: capture logs (`/var/log/supervisor/*`, audit logs, access logs) before they rotate.

### Step 3 — Assess severity & risk (within 24–48h)
Record: what data, how many subjects, categories (any special/MOD-sensitive?), cause, and **risk to individuals** (identity theft, confidentiality, MOD security impact). Decide:
- **Notify ICO?** Required unless the breach is **unlikely to result in a risk** to individuals' rights and freedoms.
- **Notify data subjects?** Required if **high risk** to individuals (Art. 34).
- **Notify MOD / customer** per contract (defence data may have stricter/faster obligations — **[CONFIRM per contract]**).

### Step 4 — Notify (within 72h of awareness)
- **ICO** (if required): report at ico.org.uk or 0303 123 1113. If full details aren't ready, submit an initial notification and follow up — **do not wait past 72h**. Include: nature of breach, categories & approx. number of subjects/records, DPO contact, likely consequences, measures taken.
- **Affected individuals** (if high risk): plain-language notice — what happened, likely impact, what they should do, and how to contact you.
- **Customers/MOD** per contractual terms.
- If you notify **late**, document the reasons (required by Art. 33(1)).

### Step 5 — Remediate
Deploy the fix, verify with tests (e.g. run `tests/test_tenant_isolation_regression_jan2026.py`), and confirm closure. For production, ensure the fix is **redeployed** (preview fixes are not live until redeploy).

### Step 6 — Record & learn
- Log the incident in the **Breach Register** (Section 3) — **all** breaches, even those not reported to the ICO (Art. 33(5) requires an internal record).
- Post-incident review: root cause, what worked, preventive actions (e.g. add a regression test, tighten a gate), owner, due date.

---

## 3. Breach Register (template)

| ID | Date aware | Detected by | Description | Data & subjects affected | Risk assessment | ICO notified? (date) | Subjects notified? | Root cause | Remediation | Status |
|----|-----------|-------------|-------------|--------------------------|-----------------|----------------------|--------------------|------------|-------------|--------|
| BR-001 | | | | | | | | | | |

*(Example of the type of event this covers: the MOD Quote Writer cross-tenant exposure identified and fixed 2026-07-31 — assess whether any real customer data was actually accessed in production before deciding on notification.)*

---

## 4. Quick decision aid

```
Became aware of a possible breach?
        │
        ▼
Contain now + note the time (72h clock started)
        │
        ▼
Is it a personal data breach?  ── No ──▶ Record internally, close
        │ Yes
        ▼
Risk to individuals?  ── Unlikely ──▶ Record internally (no ICO notify), review
        │ Likely
        ▼
Notify ICO within 72h  ──  High risk? ──▶ Also notify affected individuals
        │
        ▼
Notify customer/MOD per contract → Remediate → Post-incident review
```

---

## 5. To finalise (DPO)
- Fill in named roles + emergency contacts.
- Confirm **MOD/customer contractual** breach-notification timelines (may be < 72h).
- Store this runbook where on-call staff can reach it 24/7; rehearse once.

*Review this runbook annually and after any incident.*
