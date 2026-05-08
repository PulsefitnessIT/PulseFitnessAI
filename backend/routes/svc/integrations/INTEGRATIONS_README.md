# Service Operations · External Integrations — Code-Side Wiring Guide

**Iter 215dy · Feb 2026**

> Counterpart to `/app/memory/INTEGRATION_FIELD_MAPPING.md`. That file is the
> **data contract**; this file is the **code map**. Read both together when
> picking up Sicon / Sage work.
>
> The **single most important rule**: every external write goes through an
> *outbox* collection first. The system runs in **dry-run** mode until
> credentials are configured, at which point the relevant worker drains
> the outbox to the live API. **No code path bypasses the outbox.** This is
> what lets us ship the integration before the keys arrive.

---

## Files in this folder

```
routes/svc/integrations/
├── __init__.py
├── sicon_sync.py        # Outbox push helpers for Sicon (case, event, time, signature, attachment)
├── sage_invoice.py      # Outbox push helpers for Sage SLInvoice
└── INTEGRATIONS_README.md   ← you are here
```

Supporting files outside this folder:

- `routes/sicon.py` — legacy Sicon routes (settings, manual sync, queue admin). **Stays as-is** during the contract-winning phase.
- `routes/sicon_mapping.py` — read-only field mapping endpoint backing the admin UI tooltips.
- `routes/crm_sage200.py` — Sage 200 customer config + customer sync routes.
- `utils/sicon_client.py`, `sicon_common.py`, `sicon_poller.py`, `sicon_sync.py` — Sicon HTTP client + bidirectional poll.
- `models/schemas.py` — shared Pydantic models (some carry `sicon:` / `sage:` annotations on Field descriptions).

---

## The dry-run → live switch

Both integrations have the **same** state model and the same switch logic:

```
config.enabled = false   →   outbox accumulates rows, status="pending", no HTTP
config.enabled = true    →   worker drains outbox every 30s
```

| System | Config endpoint | Storage | Worker |
|---|---|---|---|
| Sicon | `PUT /api/sicon/config` | `sicon_configs` collection (encrypted) | `utils/sicon_sync.run_worker()` (Phase 8 A — TODO) |
| Sage 200 | `POST /api/crm/sage200/config` | `sage_configs` collection (encrypted) | `utils/sage_invoice.run_worker()` (Phase 8 B — TODO) |

The workers are *not yet implemented* — that's the Phase 8 work. The
*outboxes* are already accumulating real rows so the moment the worker
ships + credentials land, every queued row gets pushed.

---

## Outbox collections

| Collection | Owner | Drain target | Status enum |
|---|---|---|---|
| `svc_sicon_outbox` | `routes/svc/integrations/sicon_sync.py::_enqueue` | Sicon REST endpoints (per kind) | `pending → in_flight → succeeded \| failed (retry ≤ 5) → dead_letter` |
| `svc_sage_invoice_outbox` | `routes/svc/integrations/sage_invoice.py::_enqueue` | Sage `POST /SLInvoice` | `pending → ready → submitted → posted \| failed` |
| `svc_sicon_inbox` | `utils/sicon_poller.py` | merge into `svc_cases` / `svc_case_events` | per row |

Idempotency: outbox rows are upserted on `(organization_id, kind, our_reference)`
so retries / replays are safe.

---

## Where the push helpers are called from

| Helper | Call sites | Trigger |
|---|---|---|
| `sicon_sync.push_case` | `routes/svc/intake.py`, `routes/svc/cases.py` (transition), `routes/svc/scheduler.py` (×2), `routes/svc/engineer.py` (closes) | every case create / state-change |
| `sicon_sync.push_event` | (TODO) `routes/svc/cases.py` after note added | **MISSING — add in Phase 8 A** |
| `sicon_sync.push_time_entry` | `routes/svc/engineer.py` (start + stop) | engineer time-tracking |
| `sicon_sync.push_signature` | `routes/svc/engineer.py` (sign-off) | customer sign-off |
| `sicon_sync.push_attachment` | `routes/svc/engineer.py` (photo upload) | engineer photo |
| `sicon_sync.push_part_movement` | (TODO) `routes/svc/parts.py`, `routes/svc/scheduler.py` | **MISSING — add in Phase 8 A** |
| `sage_invoice.push_quote` | (TODO) `routes/svc/billing.py` on `finalise` | **MISSING — add in Phase 8 B** |

---

## Adding a new field to a `svc_*` collection

1. Add it to the Pydantic model in `models/schemas.py` (or the relevant `routes/svc/*.py` model class).
2. Add an inline `Field(description="sicon: <SiconField> · sage: <SageField>")` or `Field(description="gymaxis_only: <reason>")`.
3. Add a row in the matching section of `/app/memory/INTEGRATION_FIELD_MAPPING.md` (or `SVC_FIELD_MAPPING.md` for sections 2-18).
4. Update `_to_sicon_*` / `_to_sage_*` payload builder if `bidirectional` or outbound.
5. Run `python /app/backend/scripts/check_integration_mapping.py` — it must exit 0.

---

## Demo-readiness checklist (when credentials arrive)

When the customer / dev provides Sicon and/or Sage keys, the steps are:

```bash
# 1. Sicon — per-org via UI (Admin Console → Integrations → Sicon)
#    OR drop master-admin defaults in /app/backend/.env:
SICON_BASE_URL=https://customer.sicon-cloud.com/api
SICON_USERNAME=svc.account
SICON_PASSWORD=•••••
# (then `sudo supervisorctl restart backend`)

# 2. Sage — per-org via UI (CRM Settings → Sage 200)
#    OR drop master-admin defaults in /app/backend/.env:
SAGE_CLIENT_ID=•••
SAGE_CLIENT_SECRET=•••
SAGE_SITE_ID=•••
SAGE_COMPANY_ID=•••
SAGE_TIER=standard

# 3. Verify (no outbox bypass — these still go through the same rails):
curl -X POST $REACT_APP_BACKEND_URL/api/sicon/test-connection -H "Authorization: Bearer $TOKEN"
curl -X GET  $REACT_APP_BACKEND_URL/api/crm/sage200/customers -H "Authorization: Bearer $TOKEN"

# 4. Drain any pending outbox rows (Phase 8 worker — once shipped):
curl -X POST $REACT_APP_BACKEND_URL/api/integrations/sicon/drain-now -H "Authorization: Bearer $TOKEN"
curl -X POST $REACT_APP_BACKEND_URL/api/integrations/sage/drain-now  -H "Authorization: Bearer $TOKEN"
```

The `/integrations` admin console (Phase 8 D) surfaces all of this in the UI
including the live outbox health, last-success timestamp, and drift alarms.

---

## Phase 8 sub-deliverables (from updated PRD iter 215dy)

| Phase | Workstream | Status |
|---|---|---|
| 8 A | Sicon outbox worker + missing push_event / push_part_movement wiring | 🔜 |
| 8 B | Sage SLInvoice end-to-end (push_quote → outbox → worker → `posted` state) | 🔜 |
| 8 C | Mapping completeness audit + CI lint | ✅ this iter (215dy) |
| 8 D | `/integrations` admin console — live outbox health, lineage viewer | 🔜 |

Original "Phase 8 — Sicon decommission" plan is **deferred indefinitely**
per customer requirement (we keep Sicon, deepen the link, and prove Sage
in parallel before any decommission).
