# Sicon Service WebAPI — Pulse Fitness (consolidated integration pack)

**This folder is the single source of truth for the Sicon Service integration
hand-over.** It replaces the previously scattered locations (see "Consolidated
from" below).

## Contents

| Path | What it is |
|---|---|
| `bruno/` | Importable **Bruno collection** — Platform Auth + the full Service WebAPI plugin, merged so one import authenticates and drives every Service entity. |
| `bruno/environments/` | `Sicon Local` + `Sicon Production` environment templates (baseUrl / companyId / username + **blank** secret `password`). |
| `Sicon-Service-Pulse.bruno.zip` | The same `bruno/` collection zipped, ready to import into Bruno. |
| `FIELD_MAPPING.md` | Sicon Service body field → Pulse field, grouped per entity, with a coverage %. |
| `mapping.csv` | The same mapping as CSV (one row per Sicon field). |
| `_source/service/` | Verbatim Sicon-provided **Service Management WebAPI Plugin** collection (input, do not edit). |
| `_source/platform/` | Verbatim Sicon-provided **WebAPI Platform** host collection + Auth (input, do not edit). |

## Import into Bruno

1. **Bruno → Import Collection** → select `Sicon-Service-Pulse.bruno.zip`
   (or open the `bruno/` folder directly).
2. Pick the **Sicon Local** (or **Sicon Production**) environment; set `baseUrl`
   and `companyId`, and paste the Sicon `password` into the secret var.
3. Run **Auth → Authenticate** — it captures `accessToken` into `BEARER_TOKEN`;
   every Service request inherits it via collection-level bearer auth.
4. Run **Metadata → CaseType/Priority** and **Tracking → TrackingStatus** GetMany —
   these auto-populate `caseTypeId` / `priorityId` / `trackingStatusId` / `statusId`.
5. **Cases → Case → PostOne** auto-captures the new `caseId`; Appointment,
   TrackingNote and Equipment requests then chain off it with **no manual id copying**.

`companyId` is the Sage company (`?companyId=`). Entity ids live as environment
vars and are updated by the post-response capture scripts.

## Code source of truth (runtime)

The wire mapping the platform actually sends is defined in code and must move
together with the mappers:

- **Mapping table:** `backend/routes/sicon_mapping.py` → `GET /api/sicon/field-mapping`
  (Case, Contract, ContractLine, TrackingNote, Appointment, TimeBooking, Resource,
  **Equipment (new 2026-06)**, Metadata, Customer).
- **Mappers / client:** `backend/utils/sicon_client.py`, `sicon_sync.py`,
  `sicon_outbox_worker.py`, `sicon_inbound_worker.py`, `sicon_poller.py`,
  `backend/routes/svc/integrations/`.
- **Drift guard:** `backend/tests/test_iter_216h7_sicon_mapping_audit.py`.

## Regenerate

```bash
cd /app/backend && PYTHONPATH=/app/backend python scripts/gen_bruno_sicon_mapping.py
```

Reads `_source/` + `sicon_mapping.py`, rewrites `bruno/`, `FIELD_MAPPING.md`,
`mapping.csv` and the zip. No credentials are ever written.

## Consolidated from (previous locations)

- `integrations/sicon-bruno/` (old generated pack — removed; referenced a lost `/tmp` source)
- `memory/SICON_FIELD_MAPPING.md` (superseded stub → now points here)
- `memory/INTEGRATION_FIELD_MAPPING.md` §33 (master narrative — retained, cross-referenced)
- `memory/SICON_API_AUDIT_2026-06.md`, `memory/SICON_INTEGRATION_SPEC.md`,
  `memory/PULSE_FITNESS_x_SICON_INTEGRATION_BRIEF.md` (background docs — retained)

## Open questions for Sicon (UNMAPPED in FIELD_MAPPING.md)

Fields flagged `UNMAPPED` are either Sicon-side-only (e.g. `systemType`,
`isEnabled`, `coverType`, `sla`, `faultCode`, `colour`) or nested container
parents whose child fields map individually (`address`, `caseType`, `priority`,
`subLocation`, `contract`, `customer`). Confirm the intended Pulse mapping (or
"not required") for each at the Sicon meeting.
