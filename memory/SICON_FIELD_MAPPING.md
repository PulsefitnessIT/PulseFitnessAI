# ⚠️ SUPERSEDED — see the consolidated Sicon integration pack

This file was an early, NARROW view based only on the legacy aftersales billing
path (utils/finance_sync.py → Sage Sales Order). It does NOT represent the full,
live Sicon Service integration.

## ✅ SINGLE SOURCE OF TRUTH (consolidated 2026-06)

**`/app/integrations/sicon/`** — the one location for the Sicon Service hand-over:
  • `bruno/` + `Sicon-Service-Pulse.bruno.zip` — importable Bruno collection
    (Platform Auth + full Service WebAPI plugin, auto-chaining entity ids).
  • `FIELD_MAPPING.md` + `mapping.csv` — Sicon Service field → Pulse field, per entity.
  • `_source/` — the verbatim Sicon-provided collections.
  • `README.md` — import steps + open questions for Sicon.

## Runtime code source of truth

  • Backend table:  backend/routes/sicon_mapping.py  → GET /api/sicon/field-mapping
    (237 rows: Case 65, ContractLine 62, Resource 25, Appointment 23, Equipment 24,
     Contract 14, TrackingNote 11, Metadata 6, TimeBooking 5, Customer 2)
  • Coverage:       backend/utils/integration_mapping_coverage.py
  • Master Admin UI: frontend/src/pages/MasterAdmin/SiconMappingPanel.js + SiconHealthPanel.js
  • Workers/client: utils/sicon_client.py, sicon_sync.py, sicon_outbox_worker.py,
    sicon_inbound_worker.py, sicon_poller.py, routes/svc/integrations/

## Master narrative (retained)

  /app/memory/INTEGRATION_FIELD_MAPPING.md  §33 — full field-capture & connection pack.
