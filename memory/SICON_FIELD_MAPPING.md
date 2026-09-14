# ⚠️ SUPERSEDED — see the authoritative mapping doc

This file was an early, NARROW view based only on the legacy aftersales billing
path (utils/finance_sync.py → Sage Sales Order). It does NOT represent the full,
live Sicon Service integration.

THE AUTHORITATIVE, COMPLETE MAPPING IS:
  /app/memory/INTEGRATION_FIELD_MAPPING.md  (1,180+ lines)
  → Section 33: "SICON ↔ GYMAXIS — COMPLETE FIELD-CAPTURE & CONNECTION PACK
    (Pulse Fitness Portal · Sicon partner meeting hand-over)"

Live in-app source of truth:
  • Backend table:  backend/routes/sicon_mapping.py  → GET /api/sicon/field-mapping
    (207 field rows: Case 65, ContractLine 62, Resource 25, Appointment 23,
     Contract 14, TrackingNote 11, TimeBooking 5, Customer 2)
  • Coverage:       backend/utils/integration_mapping_coverage.py
    (Sicon 113 fields 100% annotated · Sage 70 100% · both 33 100%)
  • Master Admin UI: frontend/src/pages/MasterAdmin/SiconMappingPanel.js + SiconHealthPanel.js
  • Workers/client: utils/sicon_client.py, sicon_sync.py, sicon_outbox_worker.py,
    sicon_inbound_worker.py, sicon_poller.py, routes/svc/integrations/
