# Sicon READ-side integration (Sicon → Pulse) — implementation notes

## Hardening — concurrency lock + 111k-scale indexes (DONE 2026-09-28)
Customer estate is ~111,000 equipment lines, so a full sync is a long
multi-minute job. Two hardening changes:

1. **Per-org concurrency lock** (`utils/sicon_import.py`): `acquire_sync_lock`
   / `touch_sync_lock` / `release_sync_lock` on `db.sicon_sync_locks`
   (unique `(organization_id, entity)`). `run_equipment_sync` and
   `run_case_sync` acquire before running; a second run (e.g. nightly cron
   overlapping a manual "Sync") is recorded as `status:"skipped_locked"` and
   does nothing. Heartbeat bumped each page; a lock with no heartbeat for
   `LOCK_STALE_MINUTES` (120) is taken over so a crashed process can't wedge
   the integration. Lock released in a `finally`. Run docs now UPSERT by id
   (was `insert_one`) so the route's pre-seeded "queued" doc no longer
   duplicates.

2. **Read-side import indexes** (`bootstrap/indexes.py`): the classifier hit a
   collection scan per record (no index on `equipment.sicon_equipment_id`,
   `equipment.id`, `issues.sicon_case_id`, `issues.id`) → O(n²) at 111k =
   hours. Added `equipment (org, sicon_equipment_id)`, `(org, serial_number)`,
   `id`; `issues (org, sicon_case_id)`, `id`; `sicon_sync_locks` unique;
   `sicon_sync_runs.id` + `(org, entity, started_at)`;
   `sicon_import_conflicts (org, entity, status)`. Verified present.

Rough runtime for a 111k initial sync WITH these indexes: dominated by Sicon
API round-trips — at page_size 50 that's ~2,220 sequential calls. Raise
`SICON_PAGE_SIZE` env (e.g. 200) to cut it to ~550 calls. Expect roughly
15–45 min end-to-end depending on LAN latency; nightly re-runs cost the same
(read side has no modifiedSince filter). Tests: `test_concurrent_sync_is_locked_out`
added; full Sicon offline suite now 25 green.

---

# Sicon READ-side integration (Sicon → Pulse) — implementation notes (original)

Spec: customer's "PulseFitness-Sicon.zip / FINAL PROVEN READ-SIDE" (2026-09-24).
Live Sicon (`http://localhost:51080`, companyId=2) is only reachable on the
customer network, so everything here is built + unit-tested offline (httpx
MockTransport). The customer runs the live acceptance tests on their side.

## Increment C — CaseSearch → Service Desk + mapping screens (DONE 2026-09-24)
Case engine in `utils/sicon_import.py`; endpoints in `routes/sicon.py`; UI
`frontend/src/pages/SiconMappings.js` as the "Data Mapping" tab + Cases
preview/sync on the dashboard.

- CaseSearch → `db.issues` (existing Service Desk), idempotent by **siSMCaseId**
  (link table ENTITY_CASE + issues.sicon_case_id). classify_case → linked|new.
- Reference data is CONFIGURABLE per-org on sicon_config: `tracking_status_mapping`,
  `priority_mapping`, `case_type_mapping` (Sicon id-or-name → Pulse value). No
  hardcoded `if name=="High"` logic (§13). Fallbacks: status 'open', severity
  'operational_fault'.
- Customer/site resolved via the link table (ENTITY_CUSTOMER by customerId →
  crm2_company; ENTITY_SITE by siconSubLocationDbKey → crm2_site). Stored once,
  reused every import (§11). Endpoints: GET/POST /sicon/read/customer-mappings.
- Endpoints: /read/cases/preview, /read/cases/sync (+ /read/sync-runs),
  /read/reference (GET live lookups + current maps; PUT save maps, owner-only).
- Contract cover (§14, potential improvement): GET
  /read/equipment/{id}/cover returns an HONEST `cover_status:
  "pending_sicon_verification"` — never guesses cover from project/case text.
  The real Sicon contract route is still unproven → extension point only.
- Contract/SLA/appointment/engineer remain inactive extension points (§14/§15).
- Tests: `tests/test_sicon_case_engine.py` — 5 offline tests green (idempotent,
  reference mapping applied, unmapped fallback, customer+site link resolved,
  failure isolation). Total Sicon offline tests now 22, all green.

## Increment B — import preview + matching + conflict queue + dashboard (DONE 2026-09-24)
Engine `utils/sicon_import.py`, read-side endpoints in `routes/sicon.py`
(`/api/sicon/read/*`), dashboard UI `frontend/src/pages/SiconDashboard.js`
wired as the first tab of the existing `SiconIntegrationTab` (Settings → Sicon).

Matching (§10/§11): `classify_equipment` → linked | match | conflict | new.
- linked: siconEquipmentId already in link table OR on an asset → update/sync.
- match: unique exact serial-number hit → link + update.
- conflict: >1 asset shares the serial → conflict queue, never merge.
- new: no match → create asset.
Serial is the ONLY auto-link signal (item code/customer/model are shared across
units → left as extension points).

Field ownership (§19/§20): `_sicon_update_set` writes only Sicon-synced fields
(serial, install/warranty/service dates) + external ids; never manufacturer
(§9 — `sicon_make_raw` kept raw); never overwrites a populated Pulse field with
a null/empty Sicon value.

Idempotency: link table + `sicon_equipment_id` mean re-running never duplicates.
Sync (`run_equipment_sync`) is background (POST returns run_id; poll
`/read/equipment/sync/{run_id}`), per-record failure isolation, checkpoint on
`db.sicon_sync_runs`. Conflicts in `db.sicon_import_conflicts`; resolve via
`/read/conflicts/{external_id}/resolve` (link | create_new | ignore).

Dashboard endpoints: `/read/dashboard` (connection + equipment/case stats),
`/read/api-health` (times Ping/Equipment/CaseType/CaseSearch), `/read/conflicts`,
`/read/equipment/preview` (classify-only, writes nothing), `/read/equipment/sync`.
All gated to owner/manager/admin.

Also fixed a pre-existing platform gap: the org Settings dialog (host of the
Sicon section) had no header opener since iter202 — restored a `nav-settings-btn`
(+ mobile `mobile-settings-btn`) in `components/shared/Navbar.js` for
owner/manager/admin, and wired the previously-ignored `onOpenSettings` prop.

Tests: `tests/test_sicon_import_engine.py` — 6 offline DB-backed tests green
(idempotent no-dupe, null-doesn't-erase + make≠manufacturer, ambiguous→conflict,
existing-id→same record, failed-record isolation, preview writes nothing).
Testing agent: 7/7 endpoint tests pass; dashboard renders in not-configured
state (badges, stat cards, disabled buttons + helper, API health, empty
conflicts). Report: iteration_sicon_readside_dashboard_incrementB_jan2026.json.

## Next (Increment C)
CaseSearch → Service Desk inbound mapping + configurable reference-data
(CaseType/Priority/TrackingStatus) + customer/site mapping screens. Contract/
SLA/appointment/engineer stay inactive extension points (§14/§15).

## Increment A — foundation (DONE 2026-09-24)
All in the ONE central client (`utils/sicon_client.py`) — no parallel client.

Proven read methods added (spec §4):
- `svc_get_case_types()`   → GET /api/v1/SiconService/CaseType
- `svc_get_priorities()`   → GET /api/v1/SiconService/Priority
- `svc_get_tracking_statuses()` → GET /api/v1/SiconService/TrackingStatus
- `svc_get_equipment_page(skip,max_)` → GET /Equipment  (paged)
- `svc_get_equipment_one(id)`         → GET /Equipment/{siconEquipmentId}
- `svc_get_casesearch_page(skip,max_)`→ GET /CaseSearch (paged)
- `svc_get_casesearch_one(siSMCaseId)`→ GET /CaseSearch/{siSMCaseId}  (permanent key)
- `svc_paginate("equipment"|"cases")` async generator, advances by
  skip=(page-1)*size, stops when `nextPage is None` (not fixed totalPages).

CRITICAL pagination (§5/§30): `build_page_query()` produces
`query=$skip=0%26$max=50`. `_svc_get()` sets the URL query as **raw bytes**
via `httpx.URL.copy_with(query=...encode())` so the inner `%26` reaches Sicon
un-decoded (httpx would otherwise re-encode). Verified on the wire in tests:
`query=$skip=0%26$max=50`, no `%2526`, decodes to a single `query` param,
`$max` never leaks as a top-level param. Page 2 → `$skip=50%26$max=50`.

Write-guard (§18/§35): `_guard_write()` is called at the top of BOTH `_request`
and `_svc_request`, so ANY POST/PUT/PATCH/DELETE raises SiconAPIError(403) when
`allow_writes` is false. `allow_writes` comes ONLY from env `SICON_ALLOW_WRITES`
(default off) — cannot be enabled per-org by accident.

Auth (§3): `_svc_get` auto re-authenticates ONCE on 401/403 (clears cached
bearer, re-auths, retries). Bearer never persisted to DB, never sent to client.

Config/env (`utils/sicon_common.py`):
- `get_sicon_client(org_id)` uses DB `sicon_config`, else falls back to
  `get_sicon_client_from_env()`.
- env vars: SICON_BASE_URL, SICON_COMPANY_ID, SICON_USERNAME, SICON_PASSWORD,
  SICON_ALLOW_WRITES (default false), SICON_PAGE_SIZE (default 50).
  NOT set in preview — set them on the customer's environment for live tests.

External-ID link table (§7) — `utils/sicon_links.py`, collection
`db.sicon_external_links`, UNIQUE (integration_source, external_entity_type,
external_id) → makes every sync idempotent. Helpers: get_link/get_pulse_id/
upsert_link/set_status/counts_by_status. Index added in bootstrap/indexes.py.

Tests: `tests/test_sicon_readside.py` — 11 offline tests, all green
(pagination encoding, skip calc, paginate-until-null no-dupes, GetOne paths,
reference lookups, re-auth on expiry, writes blocked when flag false, write
sent when flag true). Run: `export $(grep JWT_SECRET .env|xargs) && python -m pytest tests/test_sicon_readside.py -q`.

## Reuse map (do NOT duplicate — §32/§33)
- Existing OUTBOUND write path (Pulse→Sicon) stays as-is but is now gated by the
  central write-guard (SICON_ALLOW_WRITES). Files: routes/sicon.py, sicon_sync.py.
- Pulse assets = `db.equipment`; CRM = `db.crm*`; audit = `db.sicon_audit_log`;
  config = `db.sicon_config`; observability = integration_logs/bridge/events.
- Admin UI to extend: `frontend/src/pages/SiconIntegrationTab.js`, `SiconServicePanel.js`.

## Next
- Increment B: Equipment→Asset import preview + confidence matching + duplicate
  prevention + conflict queue; Master Admin → Sicon dashboard.
- Increment C: CaseSearch→Service Desk inbound mapping + configurable
  reference-data + customer/site mapping screens. Contract/SLA/appointment/
  engineer stay as INACTIVE extension points (§14/§15) — do NOT guess.
