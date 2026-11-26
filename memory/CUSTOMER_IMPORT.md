# Sage & Sicon Customer Import — Handover (P0)

## Where
Master Admin → Organisations → Onboarding → Customers → **Sage & Sicon Customer Import**
(`/master-admin?section=onboarding`, then the sub-tab with `data-testid="onboarding-subtab-sage-import"`).
API: `/api/master-admin/customer-import/*`. Only Pulse Fitness admins can use it. Service Desk users are refused (403).

## Code
- `backend/utils/sage_sicon_import.py`: reads the file, detects the format and row types, builds and validates records, classifies each field, and matches contacts.
- `backend/routes/customer_account_import.py`: import jobs, preview, decisions, approval, batch commit, reconciliation report, undo log and rollback, review queues, overview.
- `backend/routes/onboarding_import.py`: legacy importer fixes. Files over 5,000 rows are now rejected (413) instead of silently cut short. No user or password is created automatically. No welcome emails are sent. Customers are matched by account number first.
- `backend/utils/file_validation.py`: legacy XLS files are now recognised correctly (fixed by the testing agent).
- Frontend: `frontend/src/pages/MasterAdmin/CustomerImport/{SageSiconImport,ImportJobPanel,ImportRowsTable,ReviewQueues}.js`, plus the new tab in `AdminOnboardingHub.js`. Uploads reuse the resumable chunked uploader (up to 50 MB).
- Tests: `backend/tests/test_sage_sicon_customer_import.py` (acceptance tests A–D, edge cases, a 5,200-row import) and `test_sage_sicon_import_independent.py`.

## Formats
- Legacy XLS (read with xlrd, including number formats so leading zeros survive).
- XLSX (read with openpyxl, using number_format).
- CSV in UTF-8, UTF-8 with BOM, or cp1252.
- The file type is detected from its contents, not just its name.
- Limit: 50,000 records per file. Larger files are rejected with a message, never cut short.

## Template and example handling
**Sage**
- The header row is found automatically (it is the row containing AccountNumber and AccountName).
- A leading "Field in template:" column is ignored.
- Rows labelled Description / Format / Field length / Pre-requisites / Mandatory/Optional / Can Create / Can Update / Name in application / Database/field name are treated as **metadata**.
- "Examples:" and the rows that follow it, up to the first blank row, are treated as **examples**.
- Any rows after that gap are marked **uncertain**. The admin must tick Include for each one.
- In production-style files, a row that matches a Sage sample on account number *and* name together is marked **suspected example** and excluded until the admin includes it. Account numbers are never blacklisted on their own.

**Sicon**
- The MetaDataDescription column decides the row type: Description / Mandatory / Default Value / Max Length / Comments are metadata, and "Sample Data" rows are examples.
- Rows where that column is blank or the column is missing are treated as genuine data.

## Sage field mapping (115 fields)
**Shown on the customer organisation**
| Sage field | Stored as |
|---|---|
| AccountName | name |
| ShortName | short_name |
| CurrencyISOCode | currency (no default is invented) |
| CountryCode | sage_country_code |
| AddressLine1–4 | address_line1–4 |
| City | city |
| County | county |
| Country | country / address_country_code (kept separate from CountryCode) |
| PostCode | postcode |
| MainWebsite | website |
| MainTelephone* | phone, plus phone_parts with the original source pieces |
| MainFax* | fax_parts |

**Source references (stored on the organisation)**
- AccountNumber → customer_account_number, sage_customer_number and sage_account_refs[], plus a unique entry in `customer_account_refs` keyed by (system, company, ref).
- AssociatedOfficeType → sage_office_type.
- AssociatedHeadOfficeAccountNum → sage_head_office_ref.
- ActiveStatus, AccountIsOnHold and AccountOpened → internal record `sage_status` only.

**Business contact (Sage primary contact)**
- Contact* fields → a `crm2_contacts` record in the Pulse Fitness Ltd internal CRM, linked by `linked_organization_id`.
- The record keeps the structured phone, mobile and fax pieces and the source fingerprint.
- It is never a login. Marketing permission is set to `not_obtained`.

**Staff-only internal record (`customer_account_internal`, never returned by customer APIs)**
- Finance: AccountBalance, CreditLimit, TaxCode, TaxRegistrationNumber, FinanceCharge, DefaultNominal*.
- Terms and discounts: EarlySettlement*, PaymentTermsInDays, SYSPaymentTermsBasis, UseConsolidatedBilling, invoice discounts, SendCopyStatementToBranch.
- Order and transaction history: ValueOfCurrentOrdersInSOP, DateOfLastTransaction, DateFinanceChargeLastRun, SYSAccountType, DefaultOrderPriority.
- Credit: TradingTerms, CreditReference, CreditBureau, CreditPosition, TermsAgreed, credit review dates, ApplicationDate, DateReceived.
- Notes: Memo.
- **AnalysisName/Value 1–20**, stored as {index, name, value} pairs. Analysis values never grant access or products.

**Not stored**
- SYSExchangeRateType, MonthsToKeepTransactionsFor, EuroAccountNumberCopiedFromTo, DateEuroAccountCopied.

## Sicon field mapping
| Sicon field | Stored as |
|---|---|
| CustomerCode | Links to Sage AccountNumber |
| Salutation, FirstName, MiddleName, LastName | Name fields |
| Telephone / Mobile / Fax (country code, area code, number) | Structured phones, plus a display number when it can be read reliably |
| Email | Email, if valid. An invalid email is kept as the source value but not used. |
| Website | website |
| ContactRole | job_title / role |
| IsDefault* and ContactRolePreferred | sicon_preferences (shown for information only; they never mean consent or login permission) |

## Required fields
**Sage**
- AccountNumber is required, up to 8 characters.
- AccountName is required, up to 60 characters.
- Other limits: ShortName 8, PostCode 10, Country and CountryCode 2, head office account 8, ContactEmail 227.
- If CurrencyISOCode is given it must be 3 letters. A missing currency does not block import.
- Values over a limit are reported as invalid and never truncated.
- Missing contact details or email never block a customer.

**Sicon**
- CustomerCode is required, up to 8 characters.
- Each contact needs at least a name, email or phone.

## Duplicate prevention
**Organisations**
- Matched only by account number, against the unique `customer_account_refs` index plus the organisation fields and site invoice/Sicon references, scoped by Sage company code.
- An account number that matches several organisations is held as ambiguous.
- Organisations with the same name are shown only as a warning and are never merged.
- Account numbers are case-folded strings with leading zeros kept.
- A duplicate source row with identical content is skipped. Duplicates with different content block approval.

**Contacts**
- Matched within one customer only, using the source fingerprint (an identical row means no change), then the name together with a personal email or phone.
- Generic mailboxes (info@, reception@, accounts@ and so on) are never used to merge people.
- Same name with a different personal email, or same email with a different name, is held as ambiguous. The admin can choose "Create as new contact".

**CRM company**
- Matched by `linked_organization_id`, then by account number. Never by name.

## Head office and branch handling (updated: Release A)
- A Sage head office / branch link is an *accounting* relationship. It is not proof of ownership or access.
- By default, every branch is imported as its **own customer**, with `head_office_link_status=proposed`.
- Admins verify or reject links in bulk in the Review Centre ("Unverified branch relationship", via `POST /customer-import/branch-links`). Verifying records the link only: there is no merge and no shared access.
- An admin can still choose "Merge into head office — I have verified it" on a row before approval.
- Circular or self-referencing links block approval.

## Statuses
- Hidden accounts (ActiveStatus=1) are excluded by default. The admin can include them.
- On-hold accounts are imported and flagged.
- These Sage statuses are stored separately from platform status and never change subscriptions or logins.

## LITE provisioning
A new organisation gets:
- `enabled_modules=["operations"]`, `modules.operations.tier="lite"`, `subscription_tier="free"`, `account_type="lite"`
- `onboarding_status="pending_activation"`, `portal_access="not_activated"`

There are no users, no passwords, no invitations and no emails. Existing organisations keep their modules and subscriptions; the import only fills blank fields. A changed value is applied only when the admin ticks "Apply changes", and the previous value is saved first.

## How to import customer accounts
1. Open the tab and pick **Sage Customer Accounts**.
2. Optionally enter the Sage company code, if more than one Sage company is used.
3. Upload the export.
4. Check the detection card: worksheet, header row, fields and row counts.
5. Review outcomes using the category filter.
6. Resolve red categories by excluding rows or changing the relationship choice.
7. Tick Include for any hidden or uncertain rows that should be imported.
8. Click **Approve import**. The data is re-checked against the live database and a snapshot is locked.
9. Click **Run import** and watch progress.
10. Download the **Reconciliation report**.
11. Confirm or reject the **Proposed sites**.

## How to import contacts
Pick **Sicon Customer Contacts**, then upload, review, approve and run, as above.
- Contacts whose customer is not on the platform yet are staged and grouped by CustomerCode ("Contacts awaiting a Sage account").
- They are linked automatically when that Sage account is imported.

## How to correct failed records
- Fix the record in Sage, re-export and re-import. Records that already imported are recognised and left unchanged.
- Rows that failed during commit can be retried with **Retry failed records**. Successful rows are never repeated.
- Rows held for a decision stay listed in the report with the action required.

## Backup and recovery
- Every change an import makes is written to `customer_import_undo`, and overwritten organisation values to `customer_import_preimages`.
- **Undo import** reverses everything in reverse order:
  - Deletes contacts, CRM companies, internal records, proposed sites and references the import created.
  - Pulls added references and restores earlier values.
  - Removes organisations it created, but only while they have no users and no paid products. Removed documents are archived to `customer_import_rollback_archive`.
- Before a live import, take a database backup through the platform's normal backup.

## Plaintext password remediation
`POST /api/master-admin/customer-import/security/initial-passwords?apply=true` removes stored `primary_contact_initial_password` values. Users' real passwords are unaffected; hand over access with the secure set-password link instead. Run it first with `apply=false` to see the count.

## Release A additions (Nov 2026)
- **Undo preview:** `GET /jobs/{id}/undo-preview` checks what depends on each customer before undoing.
- **Value restore:** a pre-import value is restored only if the field still holds what the import wrote.
- **Change after approval:** if records change after approval, Run sends the import back for review (409).
- **Proposed sites:** Confirm / Link to existing / Reject. A site at the same postcode triggers a prompt.
- **Inactive customers:** company-code sign-up is refused for imported customers that are not yet activated.
- **Passwords:** Reveal password and emailing credentials are retired.
- Full architecture and remaining gaps: `memory/PLATFORM_DATA_ARCHITECTURE.md`.
