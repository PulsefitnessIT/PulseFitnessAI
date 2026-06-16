# Sicon Integration — Specs & Mapping Reference

This folder is the canonical reference for the Sicon (Sage 200 add-on) integration
used by Pulse Fitness. The official Swagger specs are committed below so the mapper code
is always traceable to a known schema version (R260200c, April 2026).

## Specs

| File | Origin | Build |
|------|--------|-------|
| `Service.R260200c.json`   | Sicon Service WebAPI (cases, appointments, tracking notes, equipment refs) | R260200c |
| `Contracts.R260200c.json` | Sicon Contract Management WebAPI (contract headers, contract lines, billing, delivery addresses) | R260200c |

If Sicon ships a new build, drop the new Swagger JSON here under its own version
suffix (e.g. `Service.R260201a.json`) and update this README — never overwrite
in place; the diff between builds is what tells us which mapper changes are needed.

## Where the mapping lives

All Pulse Fitness → Sicon payload construction is centralised in
`backend/utils/sicon_client.py`. Key mappers and the spec object they target:

| Mapper                                | Sicon object (Spec)                | Spec file |
|---------------------------------------|------------------------------------|-----------|
| `map_gymaxis_to_sicon_case()`         | `Case` / `CreateCaseRequest`       | Service   |
| `_apply_location()`                   | `Case.Location*`                   | Service   |
| `_build_contact_fields()`             | `Case.Contact*` + customer refs    | Service   |
| `_build_assignment_fields()`          | `Case` team / contract assignment  | Service   |
| `_build_analysis_fields()` (1-8)      | `Case.AnalysisField1-8`            | Service   |
| `_build_extended_analysis_fields()`   | `Case.AnalysisField9-20`           | Service   |
| `_build_sub_location()`               | `Case.SubLocation` (`SiconSubLocation`) | Service |
| `_build_equipments_array()`           | `Case.Equipments[]` + `EquipmentIDs[]` | Service |
| `build_tracking_note_payload()`       | `AddTrackingNoteRequest`           | Service   |
| `map_gymaxis_contract_to_sicon()`     | `CreateUpdateContractRequest`      | Contracts |
| `map_gymaxis_contract_line_to_sicon()`| `ContractLine`                     | Contracts |
| `_contract_line_dates_and_price()`    | `ContractLine` price/date block    | Contracts |
| `_contract_line_renewal()`            | `ContractLine` renewal block       | Contracts |
| `_contract_line_billing()`            | `ContractLine` billing block       | Contracts |
| `_contract_line_discounts()`          | `ContractLine` Discount1-3         | Contracts |
| `_contract_line_supplier()`           | `ContractLine` supplier block      | Contracts |
| `_contract_line_analysis_codes()`     | `ContractLine.CLAnalysisCode1-150` | Contracts |

## Coverage audit (Apr 25 2026 — R260200c)

✅ Fully covered (every field in the spec has a mapper input):
- `Case` — Description, Summary, CallDate, Priority, all Location*, all Contact*,
  Equipments[], EquipmentIDs[], SubLocation, AssignedToSageUserID, InternalTeamID,
  ExternalTeamID, SiconContractID, SiconContractLineID, SiconCRMPersonID,
  SiconCRMCompanyID, AnalysisField1-20, SiSMDocumentSubStatusID, CaseNumber.
- `ContractLine` — every required field plus 90% of optional fields including
  the SLA-mapped CLAnalysisCode1-10 reservations (see `_contract_line_analysis_codes`).
- `CreateUpdateContractRequest` — all 7 SpareText / 7 SpareNumber / 7 SpareDateTime
  slots reachable via `spare_text_map` config.

🟡 Available but not yet used (low priority):
- `SiconAppointment` — full payload supported via `build_tracking_note_payload`'s
  `sicon_appointment_id` link, but we don't currently *create* appointments from
  Pulse Fitness. If we ship engineer dispatch this is the next mapper to add.
- `TimeBookingRequest` — engineer time entries; same caveat as appointments.

## When to edit `sicon_client.py`

1. Sicon publishes a new build — drop the new spec under a new version suffix.
2. `diff` it against the previous version (e.g. `diff Service.R260200c.json
   Service.R260201a.json`).
3. For every changed/added field on a payload we send, update the matching
   mapper. Add a one-line comment naming the spec file + version.
4. Bump the docstring at the top of `sicon_client.py` (`R260200c` constant)
   and run `pytest tests/test_sicon_mappers.py -v`.

Never construct Sicon payloads by hand outside `sicon_client.py` — the mapper
guarantees field-name parity with the spec, and downstream code (retry queue,
audit log, error surfaces) depends on that contract.
