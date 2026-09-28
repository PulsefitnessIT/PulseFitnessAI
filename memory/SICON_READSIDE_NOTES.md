# Sicon READ-side integration (Sicon → Pulse) — implementation notes

Spec: customer's "PulseFitness-Sicon.zip / FINAL PROVEN READ-SIDE" (2026-09-24).
Live Sicon (`http://localhost:51080`, companyId=2) is only reachable on the
customer network, so everything here is built + unit-tested offline (httpx
MockTransport). The customer runs the live acceptance tests on their side.

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
