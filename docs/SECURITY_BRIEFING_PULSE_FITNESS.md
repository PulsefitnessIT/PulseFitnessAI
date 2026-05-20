> **📋 Status — Iter 216h232 (Feb 19, 2026)**
>
> Briefing below remains accurate. Additional defence-in-depth
> measures added since the original briefing:
>
> - **CI Quality Gates** — every push runs Ruff + Bandit (high-
>   severity SAST) + ESLint (0-warning budget) + pip-audit + gitleaks
>   + pytest security suite. Workflow files: `.github/workflows/ci.yml`
>   + `.github/workflows/quality-gate.yml`. Tool versions pinned to
>   prevent silent drift.
> - **Activation event bus** — every CRM/Marketing/Operations
>   write that creates a "first" milestone fires via best-effort
>   `try/except` wrappers — a failed activation write NEVER blocks
>   the primary operation, eliminating a class of side-effect
>   DoS opportunities.
> - **MongoDB sidecar in CI** — `python-quality` job spins up
>   `mongo:7` so regression tests don't silently silently pass
>   against a missing DB (which would mask issues).
> - **`html, body { overflow-x: hidden }` below `lg:`** prevents a
>   rogue absolute-positioned element from triggering horizontal
>   scroll on mobile, which is sometimes used as a tap-jacking
>   attack vector.
>
> Live production: `https://gymaxisai.com` (deployed Feb 2026).

---


# Pulse Fitness — Platform Security Briefing

**Prepared for the Director, Pulse Fitness**  
**Subject:** How GymAxis keeps Pulse Fitness customer data, and the link to Sicon Service, safe.

---

## 1. In one sentence

Customer data lives in a private, encrypted database behind multi-layer authentication; the Sicon link uses credentials that never leave our server and travel only over encrypted channels.

---

## 2. What "Emergent" actually does for us

Emergent is our **deployment platform** — the place the application runs. Think of it as the landlord of the building our software lives in.

- Every customer request reaches the application **only** over HTTPS (TLS 1.2+), the same encryption used by online banking.
- The application runs in an **isolated container** — other Emergent customers on the same hardware cannot see our traffic, memory, or files.
- Emergent provides the network perimeter, DDoS protection, and the certificate infrastructure that secures the URL bar for every Pulse customer.

> **Important:** Emergent does not have access to our customer data, passwords, or Sicon credentials. They host the container; we control what runs inside.

---

## 3. How customer access is controlled

| Layer | What it does |
|---|---|
| **HTTPS everywhere** | Every page load, API call, and file upload is encrypted in transit. |
| **Password hashing (bcrypt)** | Passwords are never stored as readable text. Even our own engineers cannot see a customer's password. |
| **JWT session tokens** | Each login produces a short-lived signed token. Stolen tokens expire automatically. |
| **Rate-limited logins** | A brute-force attempt on any account is blocked after 5 failures. |
| **Role separation** | Owner / Manager / Staff / Service Desk / Master Admin — each role can only see what it needs. A customer staff account cannot see any other customer's data. |
| **Per-organisation data isolation** | Every database query is filtered by `organisation_id` at the code level. A Pulse Oxford user can never accidentally see Pulse Leeds data. |
| **Audit log (Service Desk actions)** | Every action Pulse Fitness internal staff take on a customer account is recorded with who, what, when, and cannot be edited or deleted. |
| **GDPR right-to-erasure** | Archived organisations are permanently deleted after 365 days; the customer's primary contact is notified 7 days before deletion. |

---

## 4. The Sicon Service link — specifically

The integration with Sicon Service is the single biggest concern customers raise, so here is exactly what happens:

1. **Sicon credentials live on our server, in our environment variables — never in the browser.** A customer using the Pulse app never sees, and never can see, the Sicon password.
2. **Every call to Sicon is HTTPS-only**, with certificate validation. No data ever crosses the internet in plain text.
3. **Basic Auth over TLS** — the authentication method Sicon themselves recommend. The username and password are transmitted only inside the encrypted tunnel.
4. **Scoped per-organisation** — each Pulse customer's Sicon config is stored separately. A fault reported by Pulse Oxford reaches Sicon with *Oxford's* company ID only; it cannot touch Leeds' tickets or vice versa.
5. **One-way push** for new faults — we send Pulse faults to Sicon, we poll Sicon for case updates every 5 minutes. We never expose any Sicon endpoint directly to the customer's browser.
6. **Failure mode is safe** — if the Sicon connection drops, faults queue locally and retry automatically. No data is lost; no sensitive information is exposed trying to reconnect.

> **The plain-English summary:** a customer reporting a treadmill fault in their gym will see "Sent to Sicon ✓" — but the credentials that authenticated that call never left our server and never touched their device.

---

## 5. Payment and financial data

We use **Stripe** for every card transaction. Stripe holds PCI-DSS Level 1 certification — the strictest standard in the industry. No card number, CVV, or full billing detail is ever stored on the Pulse platform. We only ever see a Stripe customer reference.

---

## 6. What a breach would actually look like — worst case

Even if an attacker bypassed every perimeter layer and reached our application:

- **Passwords are useless to them** — bcrypt-hashed, practically un-reversible.
- **Card details do not exist to steal** — they live only at Stripe.
- **Sicon credentials are encrypted at rest** in environment configuration; not sitting in the application database.
- **Customer data is partitioned** — compromising one customer's account cannot by itself expose another customer's data.
- **Audit log** means every Service Desk action is permanently recorded. Insider misuse is traceable to an individual within hours.

---

## 7. What we commit to do next

These are items already on the roadmap; putting them in writing here makes the commitment explicit:

- **Independent penetration test** — an external security firm to attempt a full breach of the production environment before any customer go-live with real equipment data.
- **Two-factor authentication (2FA)** for all Pulse Fitness internal staff and any customer owner who opts in.
- **SSO / SAML** integration for enterprise customers who want to federate with their existing identity provider.
- **Quarterly security reviews** with a written summary shared with our Director.

---

## 8. Single point of contact

Any question from the Director's team can come directly to our engineering lead. We will respond inside one working day and share what we can without revealing anything that could itself weaken the platform.

---

*Document version 1.0 — prepared {DATE} for the Director of Pulse Fitness. For internal use only.*
