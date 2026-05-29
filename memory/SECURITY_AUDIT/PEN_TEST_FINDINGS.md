# Pen-Test Findings — Triage Log

**Engagement:** _to be filled in by ops_
**Window:** _start date_ → _end date_
**Tester / Vendor:** _name + contact_
**Sandbox:** `pentest-org-001` on `https://app.gymaxisai.com`
**Baseline doc:** `/app/memory/SECURITY_AUDIT/PEN_TEST_ONBOARDING.md`
**Risk register:** `/app/memory/SECURITY_AUDIT/RISK_REGISTER.md`

---

## How to use this file

The pen-tester appends one section per finding, in the order they're
reported. The dev team triages each (severity, affected route, root
cause, fix iter) in the same section so this file becomes the single
source of truth for the engagement.

### Severity rubric
| Tier      | CVSS 3.1 |  SLA to acknowledge | SLA to ship fix |
|-----------|----------|---------------------|-----------------|
| Critical  | 9.0–10.0 | 2 hours             | 24 hours        |
| High      | 7.0–8.9  | 24 hours            | 1 week          |
| Medium    | 4.0–6.9  | 1 week              | 4 weeks         |
| Low       | 0.1–3.9  | next sprint         | next quarter    |

### Finding template (copy-paste below)

```
### F-PT-NN — <one-line title>

| Field            | Value                                              |
|------------------|----------------------------------------------------|
| **Severity**     | Critical / High / Medium / Low                     |
| **CVSS 3.1**     | 0.0 (CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N) |
| **OWASP class**  | API1 / API2 / … / LLM01 / …                        |
| **Tied to**      | F-NN from RISK_REGISTER.md (if any)                |
| **Reporter**     | <pen-tester name>                                  |
| **Reported at**  | YYYY-MM-DD HH:MM TZ                                |
| **Affected URL** | `/api/...` or `https://...`                        |
| **Actor**        | `pentest-owner@gymaxis.test` (role=owner)          |

**Description**

_Plain-English description of the issue, ≤ 5 lines._

**Reproduction (PoC)**

```bash
# Step 1 — login (credentials shared via 1Password, not committed here)
curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"pentest-owner@gymaxis.test","password":"<from 1Password>"}'

# Step 2 — trigger the bug
curl -s ...
```

**Expected vs actual**

* Expected: …
* Actual: …

**Impact**

_Worst-case data exposure / privilege escalation / availability impact._

**Suggested remediation**

_Pen-tester's recommendation. Dev team adds the actual fix below._

---

#### Triage (dev team only)

| Field          | Value                              |
|----------------|------------------------------------|
| **Owner**      | _engineer name_                    |
| **Triage at**  | YYYY-MM-DD                         |
| **Decision**   | confirm / dispute / accepted-risk  |
| **Fix iter**   | e.g. `Iter 220az`                  |
| **Fix commit** | _git sha or PR link_               |
| **Verified**   | _yes/no + tester confirmation_     |

**Root cause (post-fix)**

_One-line root cause to feed back into the threat model._
```

---

## 1 · Findings

_No findings reported yet — pen-test has not started._

<!-- Pen-tester: append new findings below this line in the order they're discovered. -->

---

## 2 · Engagement debrief (filled in post-engagement)

* **Total findings:**
* **Critical / High / Medium / Low split:**
* **Mean time-to-triage:**
* **Mean time-to-fix:**
* **New risk-register rows added:**
* **Existing risk-register rows reopened:**
* **Themes (for next quarter's hardening cycle):**
