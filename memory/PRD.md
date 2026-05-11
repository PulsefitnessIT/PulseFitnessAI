## Iter 216h13 — Short equipment-row display + backfill endpoint (Feb 11, 2026)

**Operator-reported (with screenshots)**: imported equipment rows were rendering the full 200-char Pulse marketing line ("Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, Apple/Samsung Watch Connectivity, Content Mirroring & Wireless Charging in Sand Black…") as BOTH the equipment `name` AND `model`, blowing the row layout out of the page. Operator demanded the row match the manual-add format: `Treadmill (cardio)` · `Pulse Fitness · 260G · 12345`.

### What shipped (backend)
- **`_EXTRACTION_TEMPLATE` schema gained `equipment_name`** (SHORT subtype noun) **and `description`** (FULL marketing line).
- **`_short_equipment_name(eq)`**: Picks AI-extracted name when ≤ 40 chars; heuristic keyword fallback (treadmill/stepmill/upright cycle/recumbent cycle/cross-trainer/rower/smith machine/lat pulldown/leg press/etc.).
- **`_short_model_code(eq)`**: Prefers `stock_item_code`. Refuses any "model" > 24 chars or > 2 spaces.
- **`_build_equipment_doc`**: Now produces clean rows. `name = short subtype`, `model = short stock code`, `description = full marketing line`, `notes = "Imported from invoice {n} · {description}"`.
- **Wizard preview** + **Sicon CSV row** + **`/parse-invoice` response** all use the same helpers → wizard preview matches what gets created on confirm.

### Backfill endpoint for legacy data
- **`POST /api/master-admin/equipment/backfill-short-display`** (master-admin gated):
  - Body: `{organization_id?, site_name?, supplier_name?, dry_run?}` — also accepts `?dry_run=true|false` query param.
  - Only touches rows with `import_id` set OR notes starting with "Imported from invoice" (manual-add rows are untouched).
  - Skips rows already in the short shape (idempotent — second run returns 0 updates).
  - Returns `{dry_run, total_candidates, equipment_to_update, equipment_updated, orgs, preview[≤200]}`.
- **UI**: New card in **Master Admin → Data Backfills** titled "Short equipment-row display (iter 216h13)" with Preview + Apply buttons. Reuses the existing dry-run-first pattern.

### Verified live (preview)
- Seeded 4 rows (3 legacy long + 1 control short manual-add).
- Dry-run preview returned `equipment_to_update: 3` with the exact before→after split (StepMill / 200H-AAF, Upright Cycle / 240G-AAV, Treadmill / 210T-BBC).
- Commit applied 3 updates; control row untouched.
- Re-running commit returned `equipment_updated: 0` — idempotent.
- New backfill card visible in MA → Data Backfills with Preview + Apply buttons.

### Regression — 19/19 passing across two new test files
- `test_iter_216h13_short_equipment_display.py` (13/13): helper unit tests.
- `test_iter_216h13_backfill_short_display.py` (6/6): API tests — dry-run preview, commit, skips already-short rows, idempotency, master-admin gate, site-name filter.

### Cost reassurance
Operator was concerned $17.44 was per-invoice. Clarified via support_agent: 1 credit = $0.20 USD, so 20 credits = $4. Their $17.44 is cumulative spend across every AI feature since signup (≈ 87 credits worth). A single Carshalton-sized extraction costs ~$0.10–0.20 (Claude Haiku 4.5). Add balance via Profile → Universal Key; auto-recharge available.

### ⚠ Action required
1. Top up Universal Key.
2. Redeploy preview → production.
3. On production: **Master Admin → Data Backfills → "Short equipment-row display" → Preview → Apply** to clean up the existing Carshalton rows (no need to delete + re-import; preserves equipment IDs, fault history, QR codes).
4. New invoice imports going forward will already use the short shape.

---


## Iter 216h12 — Carshalton invoice import: truncation + missing fields + supplier auto-matching (Feb 11, 2026)

**Production bugs reported**: User uploaded the Carshalton Invoice PDF (Pulse Fitness → South Thames College, £421,804.01 gross, 88 line items across 20 pages). Operators complained that the import "missing details and supplier matching".

### Root cause investigation
- **Missing details**: `_build_extraction_prompt` was truncating PDF text at `pdf_text[:12000]` — but the Carshalton PDF extracts to **24,090 chars**. The AI only saw ~28 of the 88 line items, plus none of the totals (NET £351,503.34 / VAT £70,300.67 / GROSS £421,804.01), bank details (HSBC sort 40-28-56, acct 40023205), customer reference (00000512 for payment), supplier VAT (785413509) or company number (4354059) — all of which sit in the second half of the document.
- **Supplier matching**: The extracted `supplier_name` was just a raw string. `db.suppliers` already had Pulse Fitness in the org directory but the import never tried to link to it, so every import created an orphan/duplicate supplier reference.

### What shipped
- **`equipment_import.py` — `_PDF_TEXT_MAX_CHARS = 40_000`** (was 12 000). Haiku-4.5 has a 200 K-token input window so 10 K extra tokens is well within budget; latency impact is ~+5-10 s for the largest invoices.
- **`_EXTRACTION_TEMPLATE` schema extended** with `supplier_vat_number`, `supplier_company_number`, `customer_name`, `customer_reference`, `due_date`, `payment_terms`, `bank_details` (bank_name, account_name, account_number, sort_code), and `totals` (net, vat, gross).
- **`_normalise_supplier_name(name)`** — collapses "Pulse Fitness Limited", "PULSE FITNESS LTD.", "Pulse Fitness", "pulse-fitness ltd" all to the same key for fuzzy match.
- **`match_supplier(org_id, supplier_name, vat_number)`** — 3-tier match priority: (1) exact case-insensitive, (2) VAT number, (3) normalised name. Returns the matched supplier doc (no `_id`) or None. Tenant-scoped to `organization_id`.
- **`/api/equipment-import/parse-invoice`** + **`/api/master-admin/invoice/parse-for-wizard`** — both endpoints now surface `matched_supplier`, `matched_supplier_id`, plus the new invoice metadata fields (totals, bank, customer ref, due-date, payment terms) in their response.

### Regression — `test_iter_216h12_carshalton_supplier_match.py` (13/13 passing)
- Truncation cap is pinned at ≥ 24 000 (locks the bug surface — refactors can't silently re-shrink).
- Prompt schema regression: explicitly asserts every new field key is present in the prompt.
- `_normalise_supplier_name` covers 4 shape variants + empty/None.
- `match_supplier` covers exact, case-insensitive, normalised, VAT-number, no-match, wrong-org, missing-args.

### ⚠ Action required (BLOCKED on Emergent LLM budget top-up)
- The Emergent LLM key budget is **exhausted** (`Current cost: $17.44 / Max: $17.40`). End-to-end live extraction can't be verified against the Carshalton PDF until you top up via **Profile → Universal Key → Add Balance** (or enable auto top-up). Once topped up, re-run the import on production — the changes are deterministic and the unit tests pin every contract surface, so the live run should succeed.
- After re-running on production, you'll see: full 88-line extraction (not 60), populated totals/bank/customer-ref fields, and a `matched_supplier_id` so the operator can one-click "Link to existing Pulse Fitness".

---

## Iter 216h11 — Spec Sheet dropdown crash + bulk delete + image graceful degradation (Feb 11, 2026)

**Production bugs reported**: (a) Master Admin → Image Catalogue → Spec Sheets dropdown was crashing the entire page (React error "Objects are not valid as a React child"). (b) Spec Sheet hero images were rendering as blank/broken-image icons. (c) User requested a "bulk select + delete" workflow.

### What shipped
- **`AdminSpecSheets.js` — `safeRenderValue()` helper**: Recursively coerces any JSON value (including nested objects like `{value, unit}`, `{min, max}`, generic `{key:value}`) into a compact human-readable string. Wraps every `key_specs` cell + `description` so the AI extractor can never crash the route again.
- **`AdminSpecSheets.js` — `<SpecImage>` component**: Adds `onError → "No image" placeholder` fallback for the public `/api/spec-sheets/image/{id}` endpoint. When the underlying S3/storage object is missing the user sees a friendly placeholder instead of a broken-image icon.
- **`AdminSpecSheets.js` — `<ExpandedDetail>` component**: Extracted to its own component with a defensive try/catch render guard (`spec-expand-error-{id}` test-id) so any future malformed payload can't take down the whole panel.
- **Bulk select + delete**:
  - Per-row checkbox (`spec-select-{id}`).
  - "Select all (N)" / "Clear selection" toggle (`spec-select-all`).
  - Sticky black bulk-action bar at top with row count + red "Delete N selected" button (`spec-bulk-bar`, `spec-bulk-delete`).
  - Loops `DELETE /api/spec-sheets/{id}` per selected id, shows mixed-success toast (`X deleted · Y failed`) and refreshes the grid.
- **PDF preview fallback**: iframe `onError` switches to a small "PDF preview unavailable" card so a missing storage object doesn't leave an empty panel.

### Verified live (preview)
- Seeded 2 test spec sheets (one with object-shaped `key_specs` — the exact crash vector) — page renders all of `flywheel weight: 22 kg`, `resistance: 1–24`, `dimensions: length: 120cm; width: 55cm; height: 115cm` plus the object-shaped description `short: …; long: …` without crashing.
- "Select all (2)" → black bulk bar visible → "Delete 2 selected" red button rendered → "Clear selection" dismisses bar.
- Missing `hero_image_url` shows placeholder icon (no broken-image).
- 0 captured `pageerror`s during the flow.

### Regression — `test_iter_216h11_spec_sheet_render_safety.py` (4/4 passing)
1. `test_list_returns_raw_object_key_specs` — backend round-trips object-shaped values unchanged (bug surface stays observable).
2. `test_delete_spec_sheet_hard_deletes_row` — single DELETE wipes a seeded row (powers bulk loop).
3. `test_delete_missing_spec_sheet_returns_404` — graceful 404 on already-deleted ids.
4. `test_image_endpoint_is_public_and_404s_cleanly` — endpoint returns 404 (not 401) when no image is stored so `<SpecImage>` placeholder triggers correctly.

### ⚠ Action required
Lives in **preview** only — **redeploy** to push to gymaxisai.com. If the production images stay blank after deploying, the underlying S3/storage objects are missing — re-upload affected spec sheets.

---


## Iter 216h10 — Fix for "0 records wiped" on production purge (Feb 10, 2026)

**Production bug reported**: user clicked "Remove everywhere" on Craig Henshall, toast showed "0 record(s) wiped" but the row remained. Root cause: my iter-216h8 purge endpoint only deleted from `db.users`, but the "Already added" check in `master_admin.py::add_user_to_organization` also looks at `db.crm_users` — so a stale row in `crm_users` was blocking re-onboarding without being touched by the purge.

### What shipped
- **Backend**: extended both `hard_purge_pulse_admin` (by id) AND `hard_purge_user_by_email` to ALSO delete from `db.crm_users`. Audit-log queries extended to find crm_users matches too, with `_collection: "crm_users"` annotation so the audit trail makes it obvious where rows came from.
- **Frontend `GlobalUsersPanel.js`**: fixed misleading toast — when the email regex matches 0 rows, the toast now shows a **warning** (not success) with actionable hint, AND automatically falls back to a hard-delete by user_id (auto-archives first since hard-delete is archive-gated). Fallback emits its own success toast indicating it was used. Success toast also now mentions CRM rows wiped when applicable.

### Why the fallback path matters
If the stored email has a hidden character, weird whitespace, or unexpected format, the email-regex match returns 0 — but we still have the user_id from the row that was clicked. Falling back to id-based delete catches this edge case without operator intervention.

### Regression — `test_iter_216h8_user_purge.py` extended to 5 tests (was 4)
- New `test_purge_by_email_also_wipes_crm_users` seeds a crm_users row and verifies the purge endpoint deletes it. **All 5 pass.**

---

## Iter 216h9 — Global Users panel + leaver workflow (Feb 10, 2026)
(See CHANGELOG history — fully shipped, 109 users panel with archive/delete + remove-everywhere, 4-pill status filter, master-admin auto-protected.)

---

## Prioritised backlog (P0/P1/P2)

### P0 — Currently in-progress
- None — iter 216h11 just landed.

### P1 — Reported bugs (next)
- **Carshalton invoice import**: missing details + supplier matching. **BLOCKED** awaiting user to upload an example PDF/image so the LLM extraction prompt can be tuned.
- **Head Office site not selectable for owners**: site-selector should show "All sites | Head Office | Site A | Site B" for multi-site orgs.
- **RAM usage metric on Trust & Reliability dashboard**: build via `psutil` per-pod gauge backend → existing T&R UI tile. Helps user decide on package upgrade.
- **"Jump to this user" link** in error toast when an existing user is re-added on the org drawer.

### P1 — Integration work
- Sage 200 / Sicon ledger posting on payment, CRM lead conversion, custom domains (`join.{gym-domain}.com`).

### P2 — Blocked / Parked
- Sicon and Sage 200 LIVE connection cutover (waiting on creds).
- Sentry DSN for production observability (Parked).
- Twilio SMS real integration (Parked).

---

## Critical operator notes
- User tests on **production** (gymaxisai.com). Agent only sees **preview**. Remind them to hit "Deploy" after each fix lands.
- Recent deploy failure was a "pod not found" infra error — fix is to re-hit Deploy (NOT a code issue).
- Master Admin credentials: `admin@gymaxisai.com` / `MasterAdmin123!` (always preserved).
- Preview DB has been wiped — only the master admin + Tottenham Green Leisure Centre data remain (since iter 215bs).
