# Maintenance Master bridge — coordinator & manager runbook

Where: CRM → Contract Management → **Contracts & Renewals** → *Maintenance Master* panel.

## 1. Upload the approved workbook (coordinator or manager)
1. Click **Upload workbook** and choose the approved `.xlsx` (any size up to 200 MB — sent in 2 MB pieces).
2. The original is stored unchanged (GridFS `mm_workbooks`) with its SHA-256, filename, uploader and time.
3. A preview builds in ~30–40 s for the 12 Nov 2026 Master (12.5k rows across 15 sheets).

## 2. Review the reconciliation preview
- Per-sheet totals: rows, active / expired / future / uncertain, contract amount £, stated annual £.
- Classifications: New contract · Matched — unchanged · Matched — differences · Duplicate / overlap ·
  Missing information · Requires review · MOD (held).
- Download the **Reconciliation report** and **Exception report** (Excel) and the **Original workbook** at any time.
- For *Requires review* rows choose the right existing customer (**Use …** shows the account ref) or **New customer**.
- MOD rows are previewed only — MOD Operations keeps ownership.

## 3. Commit (Aftersales manager / admin only)
- Tick **Create unmatched customers** only if new customer records should be created; otherwise those rows are held.
- **Approve & commit** shows the counts and asks for confirmation. Commits are resumable: if interrupted,
  press **Retry / continue commit** — rows already committed are skipped (unique Master record key), nothing duplicates.
- Commit never creates PPM visits, billing schedules, invoices, emails or Sicon writes. Existing CRM contracts
  are linked, never overwritten; differences are recorded for review.

## 3b. Resolve exceptions (coordinators)
- Tick **Unresolved only**, then filter by issue / coordinator / customer. Click a row: see why it was flagged and the original cells.
- Enter a confirmed value (e.g. the contract number from the signed agreement) + **why**, then **Save correction**. The workbook cell is never changed; the row is re-checked.
- Duplicates: **Not a duplicate — keep** or **Do not import this row** (reason required). Find the right CRM customer with the search box.
- Rows still missing information are never imported — they stay in this queue. Export **Unresolved items** to share the list.

## 4. Daily work
- Search/filter the imported contracts, open one to edit permitted fields with a reason; every save records
  contract ID, Master reference, field, old → new, user, time and approval reference. Two people editing at once:
  the second save is refused until they reload.
- Notes, missing-information filter, Sicon state per contract.
- **Current data (Excel)** = all imported contracts + full change history.
- **Updated Master workbook** = the original file, same sheets/layout, edited cells updated, new app contracts appended
  to *Maintenance Database*, plus a *Pulse Fitness Pro changes* sheet listing every edit (fields with no workbook column
  are listed there only).

## 4b. Today view & invoice preview
- **Today** cards at the top: expiring, renewals, missing information, approvals, service visits, follow-ups, import exceptions,
  billing to verify, Sicon pending. Pick your name to see only your contracts; click an item to open it.
- **Finance tab → Maintenance invoice run — preview**: choose the month, review warnings, export. Nothing is invoiced or posted.
  Monthly/quarterly contracts need a *Confirmed instalment amount* on the contract before they are proposed.

## 5. Later workbooks
Upload as before. Rows match by Master Record ID (e.g. `MAIN-00003`). Unedited fields update from the workbook; any field
a coordinator edited in the app is **kept** and flagged as a conflict. Identical files are flagged.

## 6. Sicon (deferred)
`SICON_ALLOW_WRITES` stays `false`. Managers can **Approve for Sicon queue** (held record, nothing sent) and run an
identity reconciliation (`POST …/maintenance-master/sicon-reconcile`, preview by default). Write-back later uses
`POST /api/Contract/CreateUpdateContract` and `POST /api/ContractLine/PostContractLine` only after the API family,
Sage mapping, existing-contract and line reconciliation are confirmed and approved — never as an automatic bulk sync.

## 7. Cutover & recovery
- After the whole workbook is committed and reviewed, a manager records cutover (`POST …/maintenance-master/cutover`):
  Contract Management becomes the editable system of record; the workbook stays as evidence/fallback.
- Recovery: every upload's original file is downloadable; `crm2_contract_changes` holds the full field history;
  the Current-data export is a point-in-time backup. MongoDB backups follow the platform backup policy.

## 8. Backup / restore commands
```
cd /app/backend && set -a && . ./.env && set +a
python scripts/cm_backup.py backup  --org <org_id> --out /app/backups/cm-$(date +%Y%m%d)
python scripts/cm_backup.py restore --src /app/backups/cm-YYYYMMDD --target-db <scratch_db>
python scripts/cm_backup.py verify  --src /app/backups/cm-YYYYMMDD --target-db <scratch_db>
```
Restore inserts only missing documents and refuses the live database unless `--live` is given.

## First day — Mandy & Claire
1. Open CRM → Contract Management → Contracts & Renewals. Choose your name in **Today**.
2. Work the red/amber cards top-left first: expiring contracts, follow-ups, service visits.
3. To change a contract: search it, click it, edit, write the reason, **Save** (wait for "Saved · revision N").
4. Spend time in **Unresolved only** fixing missing contract numbers/dates with a reason — never guess.
5. Use **Current data (Excel)** or **Updated Master workbook** whenever someone needs the spreadsheet.
