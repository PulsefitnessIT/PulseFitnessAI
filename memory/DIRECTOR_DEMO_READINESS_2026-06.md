# Director Demo — Full Release Readiness Report

> Prepared: 2026-06 · Author: E1 · Audience: Founder + Director demonstration
> Verdict summary at bottom. This is the single doc to read before the demo.

---

## 0. Executive verdict

**The platform is release-ready for a director demonstration.** The physical
equipment "moat" (the differentiator) works end-to-end and has been repeatedly
verified. Security posture is strong (33 pen-test findings closed + a Q1 hardening
pass). The **only true blockers are external-credential dependent** — live Stripe
key rotation and Sage/Sicon credentials — none of which are code defects.

| Area | State | Blocker? |
|---|---|---|
| Distribution golden path (quote→install→certificate→customer portal) | ✅ Verified E2E | No |
| Module independence (each sold & runs standalone) | ✅ Sound | No |
| Cross-module data flow (one system of record) | ✅ Sound | No |
| Security / pen-test readiness | ✅ Ready (33 findings closed) | No |
| Multi-tenant / multi-site isolation | ✅ Verified (403 on cross-site) | No |
| Public multi-currency pricing (GBP/EUR/USD) | ✅ Live in preview | No |
| Stripe checkout | ⚠️ TEST keys work; LIVE key must be rotated for prod | External cred |
| Sage 200 / Sicon live sync | ⚠️ Simulated; engine ready | External cred |

---

## 1. The "critical security flaw" from the prior session — RESOLVED / FALSE ALARM

The previous working session flagged `clear_demo_data` in
`routes/marketing/assistant.py` as an unauthenticated data-deletion hole. **This is
not the case.**

- The **AI chat** endpoint only *parses & suggests* an action as text (line ~291).
  It performs no database mutation.
- The **only** endpoint that actually deletes rows is
  `POST /api/marketing/assistant/execute-action` (line 354), which is guarded by
  `assert_role(["operator","owner","manager","admin","marketing_admin"])`.
- **Empirically confirmed**: a `role=logistics` user calling the endpoint receives
  `HTTP 403 {"detail":"This action requires one of: admin, manager, marketing_admin,
  operator, owner"}`. Master/Pulse admins bypass by design.
- This matches finding **F-220bo-1** in `SECURITY_AUDIT_2026Q1.md`, which is recorded
  as **closed** with exactly this fix. Blast radius was always bounded to the caller's
  own org and only docs tagged `demo_tour`.

**Conclusion: no security regression. No code change required.**

---

## 2. Process & data-flow map (how the modules work — singularly and together)

### 2.1 One system of record
Every module reads/writes shared canonical collections rather than duplicating data:
- `crm2_companies` — customers (one record; CRM, Distribution, Service Desk all point here)
- `db.equipment` — the asset register (one record per installed machine)
- `db.issues` — the fault store (Service Desk, Dealer desks, Engineer App share it)
- `organizations` / `db.users` — tenancy + identity
- `inv_*`, `dealer_*` — distribution/logistics lifecycle records

### 2.2 The distribution "golden path" (the differentiator) — VERIFIED E2E
```
CRM accepted quote
  → Send to Distribution (source='crm', idempotent)
  → Sage/manual/AI-invoice order → provisional equipment units
  → Warehouse fulfilment (release→pick→QC→pack→dispatch)
  → Dealer receipt (confirm/damage/missing serials) → dealer inventory
  → Allocate to customer → creates the ACTIVE ASSET in db.equipment
  → Schedule install (auto-links the customer's site survey + H&S + drawings)
  → On-site sign-off (customer signature + H&S ack)
      → warranty activated (equipment.status=active, warranty_expiry)
      → Installation Certificate PDF generated + stored + emailed (Resend)
      → machine auto-registered into the customer's linked Pulse Lite org
  → Customer sees Deliveries tab in their own portal (install + warranty + cert)
  → Customer can now log faults on that machine → Service Desk (one shared record)
```
No competitor (benchmarked against HubSpot) has this physical
install/warranty/asset lifecycle — it is the moat.

### 2.3 Module independence
- Each module (Operations, CRM, Marketing, Memberships, Service Desk,
  Inventory & Distribution) is a **first-class, separately-sellable** capability.
- Access is **per-user** (`is_inventory`, `is_service_desk`, module_overrides) and
  **per-org** (`enabled_modules`). A dealer with only Inventory never sees Pulse-side
  provisioning screens; module guards (`utils/module_access.py`, `require_module`)
  enforce this server-side, not just in the UI.
- **Sold separately** — "Pulse Fitness Pro" = the Operations module (flagship).
  There is no bundle SKU. The legacy equipment upgrade tier is now "Managed".

---

## 3. Security & pen-test readiness

- **33 risk-register findings (F-01→F-33) closed & regression-tested**
  (`SECURITY_AUDIT/PEN_TEST_READINESS_CHECKLIST.md`, verdict: READY FOR EXTERNAL TEST).
- **Q1 2026 hardening pass (F-220bo-1→5)** closed the LLM-amplified privilege gap,
  input length caps, Stripe outbound idempotency keys, autopilot rate limits, and
  prompt-injection delimiter wrapping.
- OWASP Top 10 + OWASP LLM Top 10 mapped and covered (`SECURITY_AUDIT_2026Q1.md §1`).
- Multi-tenant isolation: every operator route filters by `organization_id`;
  cross-tenant access returns 404 (indistinguishable from not-found). Multi-site:
  requesting a disallowed site via `?site_id=` → 403 `site_access_denied` (verified).
- **Accepted limitations** (signed off, not defects): shared preview/prod secrets
  (platform tier constraint, mitigated by org segregation), Twilio SMS mocked,
  credential-blocked integrations (Sicon/DocuSign/Outlook) return `not_configured`.
- **Pre-prod env flags** to enable before the external test / GA are listed in the
  checklist §B (MFA, strict AV/SSRF, CORS allow-list, bcrypt≥12, DEBUG=false, etc.)
  via `scripts/toggle_pentest_flags.sh --on`.

**Pen-test verdict: internally ready — with one addendum below.**

### 3.1 Post-May-28 focused security audit (2026-06) — NEW SURFACES

The signed-off pack (Iter 220bg) predates the Inventory & Distribution module, the
Logistics/Dealer/Staff portals, Customer Deliveries and the public pricing page. A focused
read-only audit of those surfaces found and CLOSED the following:

- **SEC-001 (HIGH) — FIXED & VERIFIED.** Low-trust portal logins (role `dealer_user`,
  `logistics`, and staff/recruit portal accounts) were issued ordinary full-access platform
  JWTs; many operator endpoints only checked "is logged in?" not "what kind of account?",
  so a dealer contact or recruit could call e.g. `GET /api/equipment` and read the
  operator org's asset register (same-tenant privilege escalation / broken function-level
  authorization). FIX: `utils/auth.py` now splits auth into an operator-strict
  `get_current_user` (rejects portal identities via `is_portal_only_user`, 403) and a
  `get_current_user_portal` used only by the portals + `GET /auth/me`. VERIFIED by curl:
  dealer/logistics/staff → 403 on `/api/equipment`; owner still 200; all three portals'
  own endpoints + `/auth/me` still 200.
- **SEC-002 (MEDIUM) — BY DESIGN (documented).** The `logistics` role can start/complete
  an install (commission + warranty activation). This is INTENDED — Phase 2 pt2
  deliberately gave the install team a scoped, org-gated on-site sign-off write path
  (capturing the customer signature is the portal's purpose). The earlier Phase 2 pt1
  "read-only by construction" wording is superseded. Logistics is a WRITE-CAPABLE
  install role, confined to install start/complete within its own org. No change needed.
- **SEC-003 (LOW/P3) — FIXED.** The two `stripe.checkout.Session.create` calls in
  `routes/payments.py` now pass a short-lived, intent-scoped `idempotency_key`
  (10-min bucket) so a double-click/retry cannot create duplicate checkout sessions.
  VERIFIED: flex checkout still returns a valid `cs_test_` session.

**Action for the pen-test pack:** re-issue `PEN_TEST_READINESS_CHECKLIST.md` as v1.3 with
the new module coverage row (Inventory/Distribution, Logistics, Dealer, Staff, Customer
Deliveries, Payments) reflecting the SEC-001/002/003 outcomes above.

---

## 4. Sage 200 / Sicon integration status (evidence-based)

Full API audit in `SICON_API_AUDIT_2026-06.md`. Reality vs. expectation for a
5,000-customer / 300,000-equipment migration:

| Entity | Auto-import today? | Route |
|---|---|---|
| Customers + contacts | ✅ YES | Sicon CRM API / Sage Core WebAPI (paged, incremental via AmendedAfterDate) |
| Contracts | 🔴 Read NOT possible | Sicon Contracts API is **push-only** (no GET) → CSV import |
| Equipment (the 300k) | 🔴 NOT via API | No installed-asset list endpoint in any of 5 reviewed APIs → needs Sage export / Sicon Asset Mgmt API / CSV batch |

- The idempotent **import ENGINE already exists and runs** today via a "Simulate Sage
  feed" that exercises the exact same pipeline (`routes/inventory_sage_sync.py`).
  Live sync wires in the moment credentials are entered.
- **Honest demo message**: "Enter credentials → customers & contacts flow in live.
  Equipment (largest volume) and existing contracts come via a batched CSV/export
  pipeline because Sicon exposes no read API for them — this is a Sicon API limitation,
  not ours, and we've built the idempotent importer for it."

---

## 5. Known non-blockers / backlog (safe to mention or defer)

- Stripe: preview uses **TEST** keys (checkout works). Production needs a valid LIVE
  key rotated in the deploy env (old `sk_live` expired) OR Emergent-managed Stripe.
- SEO audit subagent timeout — a tooling timeout, not a codebase bug.
- `StaffOnboarding.js` (~935 lines) refactor — maintainability only; defer post-launch.
- Weekly "System Health digest" email — new feature pending founder approval.
- Interactive exploded-drawing hotspots; CSV cost-backfill wizard — P2 niceties.

---

## 6. Demo script (suggested 10-minute director flow)

1. **CRM** → open an accepted quote → *Send to Distribution* (show idempotency).
2. **Inventory & Distribution** → order appears with source badge → fulfilment pipeline.
3. **Logistics portal** (separate login `logi1@isodemo.com`) → Install pack (survey +
   H&S + drawings) → on-site *Complete & sign-off* with signature → warranty activates.
4. Show the **Installation Certificate PDF** + that the machine auto-registered into the
   customer's Pulse org.
5. **Customer portal** (`lite.docs@pulsedemo.test`) → Deliveries tab → warranty + cert,
   then log a fault → lands in Service Desk as one shared record.
6. **Public pricing** (`/pulse-pricing`) → toggle GBP/€/$ + monthly/annual, ROI
   calculator, FAQ. "Pulse Fitness Pro" = Operations flagship.
7. **Master Admin** → per-area impersonation + platform health + audit trail.
