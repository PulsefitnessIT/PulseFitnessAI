# MOD Quotations — runbook (25 Nov 2026)

**Where:** MOD Operations (`/bfpo`) → Quotations. Roles: MOD Sales = MOD Operations access; `users.mod_quote_role` = `manager` (approve, exceptions, verify authorisations, handover set-up, validity), `pricing_admin` (Schedule of Rates), `pricing_admin_manager` (both).

1. **Schedule of Rates** (pricing admin): upload the Schedule B workbook → review issues (duplicate Sage codes, Schedule B vs printed SER conflicts) → Approve with effective date. Only the imported service type of each row becomes verified; Type A approval never verifies Type B. New price lists never change already-published PDFs.
2. **New quotation:** customer/site → equipment (register, Excel/CSV, manual) → options A / B / A-B Mix (A/B per row) → review → Generate (drafts). Quantity 0 rows are listed as "not quoted"; negative/non-numeric quantities are rejected; unmapped or POA items block generation.
3. **Approval** (manager): every priced line on an unverified rate (including the Type B call-out) needs a structured exception (line, reason, original = quoted rate, valid until). Otherwise approval and publication are refused.
4. **Publish** to MODService: immutable PDF + checksum + pricing snapshot; validity from the provisional 30-day setting (Settings → validity, manager; mark "approved commercially" when Commercial confirms).
5. **Notify:** re-type recipient; attachments only if ticked. Sends nothing unless `MOD_QUOTE_NOTIFY_LIVE=true` (dry-run recorded in history otherwise).
6. **Customer** views/compares/downloads (PDF/ZIP) and submits authorisation (PO, officer, date, evidence). Expired or superseded versions cannot be authorised; staff can extend validity (reason recorded) or revise.
7. **Verify & accept** (manager) → handover queue → **Set up service records** with commencement date: Type A → active annual contract with *proposed* visit; Type B → one-off record (no annual obligation). Idempotent; no bookings, invoices or Sicon writes.
8. **CRM:** company → MOD Quotations tab (read-only) with "View in MOD Operations".
Originals (Schedule B, QT9410–QT9412 renders) are in object storage under `restricted/` — not in Git.
