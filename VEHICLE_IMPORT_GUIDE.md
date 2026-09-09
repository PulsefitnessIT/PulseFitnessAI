# Company Vehicle Import — Procedure & Data Guide

Bulk-load your fleet into the Pulse Staff Portal without re-keying. Drivers are
matched to existing staff accounts, so people are never duplicated.

## Where
Staffing console → **Vehicles** tab → **Import from engineers** button →
**Bulk import from spreadsheet (CSV)** panel.

## Procedure
1. Click **Download CSV template** (`vehicle-import-template.csv`).
2. Fill in one row per vehicle (see columns below). Keep the header row.
3. Save as **CSV (UTF‑8)**.
4. Click **Upload CSV**. You'll get a summary: created, skipped (duplicate reg
   already in the register), and any rows whose driver email didn't match a staff
   account.
5. Fix any flagged rows and re-upload — existing registrations are skipped, so
   re-uploading is safe.

## Columns (capture ALL available information)
| Column | Required | Notes |
|---|---|---|
| `reg_no` | ✅ | Number plate, e.g. `AB12 CDE`. Stored uppercase. Duplicates are skipped. |
| `make_model` | – | e.g. `Ford Transit Custom` |
| `vehicle_type` | – | One of `car`, `electric_car`, `van`, `electric_van`, `lorry`. Default `car`. Sets which weekly checklist the driver completes. |
| `provider` | – | Supplier / lease company / garage, e.g. `Vanarama`. (This is a **supplier**, not a check type.) |
| `odometer` | – | Current mileage |
| `driver_names` | – | **Who the vehicle is assigned to** — one or more staff **names**, e.g. `Alex Rivera;Sam Patel`. Matched to your staff register (case-insensitive). Separate multiple with `;` (or `,`). The **first** name becomes the primary driver. |
| `driver_emails` | – | Alternative way to assign drivers — matched to staff by **email**. Use this *or* `driver_names` (or both); names and emails are combined and de-duplicated. |
| `next_service` | – | Date `YYYY-MM-DD` (or `DD/MM/YYYY`) |
| `mot_due` | – | Date — feeds the compliance dashboard's expiry list |
| `tax_status` | – | e.g. `Taxed` / `SORN` / a due date |
| `insurance_expiry` | – | Date |
| `mileage_due` | – | Next service mileage |
| `service_ref` | – | Provider/garage reference |
| `notes` | – | Free text (e.g. equipment fitted) |

## Matching & rules
- **Drivers (who the car is assigned to)**: put the person's **name** in `driver_names`
  and/or their **email** in `driver_emails`. Both are matched to your `staff_members`
  register (case-insensitive); the first driver becomes the primary. Anything that
  doesn't match an existing staff member is listed as a row error and left unassigned.
- **Duplicates**: a reg already active in the register is skipped (never overwritten).
- **Engineer sync**: the primary driver's registration is pushed to their Service
  Desk engineer profile automatically.
- **Vehicle type drives the checklist** — car/van get the standard checks, electric
  types add the EV section, lorry adds tachograph/load-security/coupling checks.

## After import
Vehicles appear in the **Fleet register**; assigned drivers immediately see the
weekly check in their Staff Portal, and the **Overview** dashboard starts tracking
completion, defects and upcoming MOT/tax/insurance dates.
