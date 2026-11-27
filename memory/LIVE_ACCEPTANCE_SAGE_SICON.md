# Pulse Fitness: supervised read-only live acceptance (Sage 200 + Sicon)

This procedure is for Pulse Fitness IT, with a Pulse admin present. Everything here is **read-only**.

Throughout:
- Keep `SICON_ALLOW_WRITES` and `SAGE_ALLOW_WRITES` unset or `false`.
- Keep `SICON_NIGHTLY_SYNC_ENABLED` unset.
- Nothing has been live-verified from the development environment: these servers are not reachable from it.

## 0. Before you start
0. Confirm the deployed commit (`GET /api/build-info` → `commit`) matches the approved release commit.
   - Confirm `flags` shows `SICON_ALLOW_WRITES`, `SAGE_ALLOW_WRITES`, `SICON_NIGHTLY_SYNC_ENABLED`, `INVITATION_EMAILS_LIVE` and `IMPORTED_CUSTOMER_PURCHASES_ENABLED` all **false**.
1. Take a database backup and keep it until sign-off:
   - Back up with `mongodump --uri "$MONGO_URL" --db "$DB_NAME" --gzip --out backup-YYYYMMDD`.
   - Prove the backup restores on a separate restore host:
     `mongorestore --gzip --nsFrom "$DB_NAME.*" --nsTo "restore_check.*" backup-YYYYMMDD`.
   - Compare document counts for `organizations`, `users`, `equipment`, `sites`, `customer_account_refs` and `sicon_external_links`.
2. Confirm the environment:
   - `SICON_SAGE_COMPANY="Pulse Fitness"`.
   - The Sicon connection (Master Admin → Integrations → Sicon) shows the **base URL and companyId** of the live installation.
   - The Sage 200 connection (CRM → Settings → Sage) shows **company name = Pulse Fitness**, plus site and company ids.
3. Write down the verified identifiers:
   - Sicon base URL host.
   - Sicon companyId.
   - Sage site id.
   - Sage company id and name.

   Links are stored as `<sicon host>#<companyId>`. The Sage company comes from the connection, never from a typed label.

## 1. Authentication
| Test | Expected |
|---|---|
| Sicon: Integrations → Sicon → Test connection | Platform Authenticate succeeds and a bearer token is issued (token never shown) |
| Sage: CRM → Settings → Sage → Test | 200 from `/customers?$top=1` |
| Customer CRM admin opens Sage settings | 403 (Sage is Pulse-only) |

## 2. Small customer sample (5–10 approved accounts)
1. Export those accounts from Sage, using the Customer Accounts template.
2. Upload the file in Onboarding → Import Centre → Customer Accounts. The company should be prefilled as "Pulse Fitness".
3. Approve and run the import. Record the permanent org ids of the sample.

## 3. Customer retrieval and pagination (Sage 200)
1. Run CRM → Settings → Sage → Pull. This creates an Import Centre job; **do not approve yet**.
2. Check the job's record count equals the Sage customer count. Every `$skip` page is fetched, and the pull fails loudly above 50,000.
3. Open the job rows: every sample account must show **Existing organisation** with the same org id as step 2, and no duplicates.
4. Discard the job, unless it is intentionally used for the full import later.

## 4. Existing link migration (dry run)
1. Call `GET /api/master-admin/customer-import/sicon-links/migration`.
2. Record `to_scope` and `needs_review`.
3. Only after sign-off, run `POST .../migration/apply`.

## 5. Sicon equipment (preview only)
1. Go to Integrations → Sicon onboarding → **Preview** (never Import on the first pass).
2. Check the run card:
   - **Retrieved:** records and pages per resource. Equipment records must equal the Sicon totalRecords.
   - **Status:** `partial` is expected, because contracts are listed as missing (no confirmed contract read API).
   - **Sage company:** PULSE FITNESS. **Sicon company:** `<host>#<id>`.
3. Prove the preview made no changes: the counts of `equipment`, `sites` and `organizations` are identical before and after.
4. Review Centre:
   - "Held Sicon equipment (customer not imported)" groups the equipment whose customer isn't on the platform.
   - "Proposed operational site" (source: Sicon sub-location) lists unknown locations.

## 6. Sample apply (only for the sample customers)
1. **Never apply a full-estate preview on the live database.** Restrict the apply to the approved sample:
   `POST /api/sicon/read/onboarding/{preview_run_id}/apply` with body `{"sample_org_ids": ["<org id 1>", "..."]}`.
   The org ids are the ones recorded in step 2.
   - Equipment, cases, customers and sites belonging to any other customer are skipped. They are not created and not queued.
   - The run card shows `outside_sample.skipped`.
   - Alternatively, run the apply in an isolated acceptance database restored from the step-0 backup.
2. Import the approved preview once; a second Import of the same preview is refused.
3. Check:
   - Equipment sits under the sample customers, not the Pulse organisation.
   - Spreadsheet assets with the same reliable serial gained `sicon_equipment_id`, with no new asset.
   - Placeholder serials (N/A, unknown) were not matched.
4. Confirm or link each proposed site. The equipment at that location joins the site. Re-run the preview and apply: no new sites, proposals or assets appear.

## 7. Contracts
- Confirm with Sicon whether the installed Contract Management plugin exposes any **GET** resource. Contracts.R260200c has POST endpoints only.
- Until confirmed, contracts come from the Maintenance Contracts spreadsheet.

## 8. Sign-off record
Record:
- Identifiers (step 0).
- Counts per step.
- Screenshots of the run card and Review Centre.
- Any differences found.

Unattended (nightly) sync stays disabled until this record is signed.
