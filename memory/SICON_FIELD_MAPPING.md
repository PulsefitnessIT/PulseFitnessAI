# Sicon / Sage 200 integration — field mapping & readiness (June 2026)

## Honest headline
Today the platform maps ONLY ONE thing: an active maintenance contract → a Sage 200
**Sales Order** payload (utils/finance_sync.py, outbox crm2_afs_finance_sync). It is
env-driven and queues under `awaiting_credentials`. Service and CRM entities are NOT
mapped. "Perfect, works-on-switch-on" cannot be guaranteed until the customer's Sage
Business Partner confirms the version-specific Sicon WebAPI schema and we validate
against a Sage sandbox. Below is exactly what maps, what's missing, and the plan.

## The three Sicon/Sage domains vs our readiness
1. Sicon Contracts (recurring billing / deferred income / renewals / RPI)
   - Best architectural target for our maintenance contracts (NOT a raw SOP order —
     Business Partner to decide: post Sales Order per invoice vs. create a Sicon Contract).
   - Readiness: ~80% conceptually mappable. Gaps below.
2. Sicon Service (jobs / call management / engineers / van stock / equipment / PPM)
   - Readiness: 0% — no adapter today. Our service/ops data (equipment, faults, PPM,
     vehicle checks) lives in separate modules and is not wired to Sicon Service.
3. Sage 200 core CRM / customers (customers, contacts, opportunities)
   - Readiness: ~40% — we send customer name/email/derived reference, but NOT the real
     Sage customer account number, contacts, or opportunity/pipeline sync.

## Field mapping matrix — CONTRACT → Sicon (current + required)
| Our field (crm2_contracts / _companies / _afs_billing) | Sicon/Sage target | Status | Gap / action |
|---|---|---|---|
| company.legal_name/name | Customer.CustomerName | mapped | ok |
| _customer_reference(company) (derived) | Customer.CustomerAccountNumber (SLCustomerAccountNumber) | RISK | Sage needs the REAL account ref, not a derived one. Must store sage_customer_ref on each company. |
| company billing email | Customer.Email | mapped | ok |
| company address/postcode | Customer address lines | MISSING | not currently sent |
| contract.contract_number | Contract.Reference / Order.CustomerDocumentNo | mapped | ok |
| contract.contract_type/tier | Contract line / SOP line description | partial | confirm Sicon "Contract Type" code list |
| contract.start_date / end_date | Contract.StartDate / EndDate | mapped | confirm date format (ISO vs DD/MM/YYYY) |
| contract.term_years | Contract term / renewal cycle | mapped | ok |
| contract.annual_value | line UnitPrice / Contract annual value (ex-VAT) | mapped | confirm ex-VAT vs inc-VAT expectation |
| contract.billing_frequency | Contract billing cycle | mapped | map our values → Sicon cycle codes |
| invoice line description | SOPOrderLine.LineDescription | mapped | ok |
| cfg nominal_code (env, default 4000) | SOPOrderLine.NominalCode | RISK | must match customer chart of accounts |
| cfg tax_code (env, default 1) | SOPOrderLine.TaxCode | RISK | must match customer VAT codes |
| — (none) | Analysis codes / project code / cost centre | MISSING | many Sage setups mandate analysis codes |
| — (none) | Deferred income schedule | MISSING | Sicon Contracts handles this; confirm if required |
| contract.rpi_last_review / RPI uplift | Contract price escalation | MISSING | RPI changes not pushed as contract amendments |
| contract.id | Order.ExternalReference / idempotency key | mapped | ok (dedupe by contract) |

## Field mapping matrix — CRM → Sage (not built)
| Our field | Sage target | Status |
|---|---|---|
| crm2_companies (customer master) | Sage Customer / CRM Company | not synced (create/update) |
| contacts | Sage CRM Contact | not synced |
| crm2_afs_quotes / opportunities | Sage CRM Opportunity/Quote | not synced |

## Field mapping matrix — SERVICE → Sicon Service (not built)
| Our data | Sicon Service target | Status |
|---|---|---|
| equipment / assets | Sicon Service Equipment | not synced |
| faults / call-outs | Sicon Service Case/Job | not synced |
| PPM / planned maintenance | Sicon Service PPM schedule | not synced |
| engineer time/parts | Service job costs / van stock | not synced |

## Why "switch on and it just works" is not safe yet
- Sicon WebAPI schema is VERSION-SPECIFIC; Swagger is disabled by default. Exact field
  names, mandatory fields, and code lists come from the customer's Sage Business Partner.
- No live credentials and no sandbox to validate against.
- Sage rejects orders without a real customer account number + valid nominal/tax/analysis
  codes matching THEIR configuration. Our defaults (nominal 4000, tax 1) are placeholders.
- Contract vs Sales-Order target is a finance-process decision only the customer can make.

## Path to a confident go-live
1. Mapping/adapter layer per domain (Contracts, Service, CRM) + a shared field dictionary.
2. DRY-RUN / pre-flight validator: build every payload, validate required fields & code
   lists, output a report — WITHOUT posting. Works today with zero credentials.
3. Business Partner confirms schema + temporarily enables WebAPI Swagger so we auto-verify
   endpoints and field names.
4. Capture sage_customer_ref (+ nominal/tax/analysis codes) on each company/contract.
5. Validate against a Sage SANDBOX company end-to-end before pointing at live.
6. Reconciliation report: what we sent vs what Sage accepted/rejected, with retry.
