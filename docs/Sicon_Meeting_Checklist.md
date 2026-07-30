# Pulse Fitness AI × Sicon — Meeting Checklist

**Date:** June 2026  ·  **Prepared by:** Pulse Fitness AI (pulsefitness.ai)
**Purpose:** Confirm the open technical + data questions so we can complete an automated, scalable migration (≈5,000 customers · ≈300,000 equipment).

---

## Status at a glance

| Domain | Read/List API today? | Status |
|---|---|---|
| Customers / contacts | ✅ Yes (Sage Core + Sicon CRM, paged, delta) | Ready to automate |
| Service cases / appts / notes | ✅ Yes (live, push + poll) | Built |
| Contracts | 🔴 Push-only (no GET) | Interim CSV — needs read API |
| **Equipment (300k)** | 🔴 **No list endpoint** | **Blocked — primary ask** |

Specs re-verified June 2026 — all 5 unchanged (Service R260200c, CRM R221200c, Contracts R260200c, CoreWebAPI R260200c, Projects R260200c). Auth confirmed: HTTP Basic over TLS + `companyId` per call.

---

## A. Routing / API-shape (from our client integration)

- [ ] **A1 — Appointment routes.** Our client now targets the spec's `/~/api/v2/TEntity/api/Service/Appointments` (create/get/update) and `/~/api/v2/TEntity/{id}` (delete). **Confirm the `/~/api/v2/TEntity/…` prefix is the real production route** (and that `~` resolves to the WebAPI site root).
- [ ] **A2 — Appointments by case.** There is no case-scoped appointment list in the spec. **How should we poll all appointments for a given `SiSMCaseID`?** (Filter on `/~/api/v2/TEntity`? A missing endpoint?)
- [ ] **A3 — Priorities lookup.** The Service spec exposes **no priorities endpoint**. **Is there a priorities list anywhere**, or do we hard-map `PriorityID` via config only?

## B. Equipment — highest priority (300k assets)

- [ ] **B1 — List/search API.** Is there any endpoint to **list/search the installed Equipment / Service Asset register** per company — ideally paged with a "changed since" filter for delta sync?
- [ ] **B2 — Generic reader.** If not dedicated, can Equipment be read via the Service `GET /~/api/v2/TEntity` paged reader? If so, **what is the entity type/identifier for Equipment**, and which fields are returned?
- [ ] **B3 — Export fallback.** If no API exists, can you provide a **one-time SQL/CSV export** per company with: `SiconEquipmentID`, serial, make/model/type, install date, warranty/contract cover, linked customer (`SLCustomerAccountID`), site/sub-location? (Our importer is ready.)

## C. Contracts

- [ ] **C1 — Read endpoint.** Is a **GET/list endpoint for Service Contracts + contract lines** available or planned (so we can migrate existing contracts and read state back)? If not, can you provide a CSV/DB export?
- [ ] **C2 — Coverage linkage.** How is the link between an **equipment asset ↔ its site/sub-location ↔ its covering contract** exposed for reading?

## D. Operational

- [ ] **D1 — Limits.** Recommended **rate limits / page sizes** for bulk reads at our scale (5k customers / 300k assets)?
- [ ] **D2 — Change feed.** Any **webhooks / change notifications**, or is scheduled polling (`AmendedAfterDate` / updated-since) the expected pattern?
- [ ] **D3 — Endpoints.** Confirm the **production base URL pattern** per customer instance and any **IP allow-listing** needs.

---

## Our asks / next steps
1. Unblock **Equipment** (B1–B3) — the single largest domain and main migration blocker.
2. Confirm **contract read** path (C1) so we can drop the CSV interim.
3. Confirm **routing** (A1–A3) so our built integration validates against a live instance.
4. On receipt of **Base URL + WebAPI username/password + `companyId`**, we run a live connection test (Ping) same day.
