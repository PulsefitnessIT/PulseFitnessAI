# Pulse Fitness — Release 1 report (internal production release candidate)

Date: 27 November 2026. The starting commit was `3516aa6a97a1413feecaee96d2ceda35a2e8a3d1` (GitHub main). The final commit is the latest "Auto-generated changes" commit on main after this report; use **Save to GitHub** to push it.

## 1. P0 defects corrected
| # | Defect | Fix |
|---|---|---|
| 3 | A company code let anyone join an ACTIVE customer as staff | `_resolve_org_and_role` now refuses every company-code join, for active and inactive customers, including legacy invites (403). New-organisation sign-up is unchanged. The sign-up form no longer has a code field, and the "share this code" text is removed (Settings, Pulse Settings, Account → Team). |
| 3 | Legacy `invites` could bypass verification | `POST /api/master-admin/legacy-invites/migrate` (dry run by default, optional `organization_id`) reissues them as secure invitations. Roles are capped at manager/staff. Rows are marked `migrated` or `retired`, never deleted, and each row reports its errors. |
| 4 | Staff permissions were inconsistent (`auth.py` **and** the Account → Team screen in `account.py`) | One rule set, `utils/team_guards.py`. Nobody can change their own access. Managers can only manage staff inside their own sites and can never grant all-site access. Site IDs must belong to the organisation. A role or site change ends the person's sessions. Becoming a manager forces MFA enrolment. The owner role moves only through `POST /api/organization/ownership/transfer`, which needs the owner's password and a new owner who already uses MFA. Account → Team "invite" now creates a secure invitation (no temporary passwords, no direct accounts). |
| 6 | Disabled accounts kept their existing sessions | `_load_user_core` rejects `active:false`, `is_active:false` and `status:"disabled"` on every request. Login does the same. |
| 6 | Members of a customer still awaiting activation could sign in | Login returns 403 until the owner accepts the activation invitation. |
| 7 | Legacy all-sites gym-floor logins bypassed the new site rules | In a multi-site organisation, an older login is refused and its sessions end. With one site, it is bound to that site. A site-restricted manager can no longer delete another site's handover notes. |
| 11 | The owner already had a login in another organisation | No duplicate person is created. The customer is flagged `activation_review_required` and shown as "Activation review" in Customer Activation. |
| 11 | Interrupted invitation acceptance | An acceptance stuck for over 5 minutes can be retried, and it completes with one user. |
| 10 | A supervised Sicon apply couldn't be limited to the approved sample | `POST /api/sicon/read/onboarding/{run_id}/apply` takes `{sample_org_ids: [...]}`. Customers outside the sample are not touched and nothing is queued for them. |
| 13 | Imported customers could buy before a real Stripe test | `_imported_purchase_gate`: imported or activated-by-invitation customers get 403 on checkout until `IMPORTED_CUSTOMER_PURCHASES_ENABLED=true`. Self-sign-up journeys are unchanged. |
| – | Trial reminder retries | A failed reminder is retried at most 3 times; previously it retried every 5 minutes for ever. |

## 2. Test results (actual)
- Independent test round iteration_342 found 5 real defects (side-door Team endpoints, sign-in before activation, the disabled status, handover delete scope, legacy-invite 403). All 5 are fixed. Its 9 tests (`tests/test_release1_iter342.py`) now pass.
- Release-critical suites (run against the preview after the fixes): 155 passed (see section 9).
- **Zero-trust authorisation gate** (`test_auth_matrix`, `test_security_authz_matrix`, `test_step_up`, `test_abuse_guard`): 26/26. This was run both against the preview and in a CI-like run (fresh MongoDB, local backend). The only original failure was the two new public invitation endpoints. They are genuinely public: token-authenticated, rate-limited and scanner-safe. They were reviewed and added to `security_matrix_baseline.json`, and nothing else changed in the baseline.
- **Ruff 0.15.10:** `All checks passed`. The one error was E731 in `tests/test_release_ab_iter338.py`.
- **Frontend production build:** `yarn build` succeeded (Done in 166 s). ESLint shows 0 warnings on every file changed.

## 3. GitHub Actions
| Workflow job | Before | Now (local reproduction) |
|---|---|---|
| Security Audit | PASS | unchanged |
| Frontend ESLint + build | PASS | PASS |
| Python Quality Gate (ruff) | FAIL (E731) | PASS |
| Pre-commit (ruff) | FAIL (E731) | PASS |
| Zero-Trust Authorisation Gate | FAIL (2 public routes not in baseline) | PASS (26/26) |
| Backend Regression Suite (`make regression`, about 2,600 tests) | FAIL | **still FAIL; not caused by this release** (see below) |

The GitHub logs need a sign-in, so the failures were reproduced locally.
- Against the preview, `make regression` gave 2,441 passed, 161 failed and 41 errors.
- **Baseline proof:** every one of those 202 failing tests also fails when the test code of commit `ae183314` (before Release C/E) runs. No new failures were introduced. The causes are:
  - Source-text assertions on frontend files that were later changed (stale expectations).
  - Seeded demo accounts locked or rate-limited in the shared preview (`Account temporarily locked`, 429).
  - `MagicMock` objects that can't be awaited in older unit tests.
  - Missing locale files.
- A CI-like run (fresh database, `http://127.0.0.1`) adds about 60 failures that pass on the HTTPS preview. They are session-cookie tests (Secure cookies are not sent over plain http), plus tests that expect seeded data.
- Recommendation: a separate clean-up release to refresh those stale assertions. No assertion was weakened in this release.
- Two assertions were updated because the founder changed the policy, not to manufacture a pass:
  - `test_customer_import_release_a::test_company_code_signup_block_and_regression`: an active organisation's code is now refused.
  - `test_gym_floor.py`: a multi-site organisation must pick a site.
- Still failing and unrelated:
  - `test_sicon_bruno_artifacts` (2 tests): the Bruno collection files are unchanged since September.
  - `test_gym_floor::test_add_staff_as_manager`: this also fails at the baseline commit.

## 4. Safety switches (backend `.env`, all `false`)
`SICON_ALLOW_WRITES`, `SAGE_ALLOW_WRITES`, `SICON_NIGHTLY_SYNC_ENABLED`, `INVITATION_EMAILS_LIVE`, `IMPORTED_CUSTOMER_PURCHASES_ENABLED`. All five are reported by `GET /api/build-info` → `flags`. The production deployment must set the same values as secrets.

## 5. Database migration requirements
- New collections are created on first use with their indexes:
  - `secure_invitations`: unique `token_hash`, plus one pending invite per person per organisation.
  - `email_send_claims`: unique `key`.
  - `commercial_events`.
- Run once after deploying, as a Pulse admin: `POST /api/master-admin/legacy-invites/migrate {}` (dry run). Review the plan, then repeat with `{"apply": true}`. The preview currently has 0 legacy invites.
- No other schema changes. The Sicon link company scope migration from Release A/B is unchanged (dry run, then apply, as documented).

## 6. Backup and restore
- **Backup:** `mongodump --uri "$MONGO_URL" --db "$DB_NAME" --gzip --out backup-YYYYMMDD`. The preview dump completed at 291 MB.
- **Restore check:** restore into a separate database with `mongorestore --gzip --nsFrom "$DB_NAME.*" --nsTo "restore_check.*" backup-YYYYMMDD`, then compare document counts for `organizations`, `users`, `equipment`, `sites`, `customer_account_refs`, `sicon_external_links` and `secure_invitations`.
- Do this on the production host or a dedicated restore host, not on the live app server. A full restore on the busy preview database server caused a MongoDB restart. A smaller restore check is recorded in section 9.

## 7. READY / NOT READY
| Area | Decision | Evidence or blocker |
|---|---|---|
| Internal production deployment | **READY**, subject to the backup and the switch values in section 4 | P0 fixes and tests above. Ruff, authorisation gate and build pass. The full regression suite fails only on failures shown to predate this release. |
| Live Sage customer spreadsheet imports | **READY** (sample first) | Customer-import, shared-matching and Release A/B suites pass. Every new customer gets LITE only, with no invitations and no passwords. |
| Live Sicon contact spreadsheet imports | **READY** (sample first) | Same suites. |
| Live Sage API retrieval | **NOT READY** until the supervised live check | Not reachable from development. The read-only guard is on. |
| Live Sicon equipment retrieval | **NOT READY** until the supervised live check | Not reachable from development. The sample-restricted apply is now available. |
| Maintenance contract imports | **Spreadsheet only** | No confirmed Sicon contract GET resource. Shared contract identity (Release B) is not finished. |
| Customer activation | **READY for a pilot only, invitations not live** | All activation tests pass. A real branded email has not been sent and approved (section 8). |
| Manager and staff access | **READY** | Direct API tests in `test_release1_access.py` and the iteration_342 tests. |
| Gym-floor access | **READY** | `test_release1_gym_floor.py` and the iteration_342 gym-floor checks. |
| Paid product purchasing (imported customers) | **NOT READY** (blocked by the gate) | A genuine Stripe test-mode lifecycle can't be run here (section 8). |
| Complete cross-module data integration (Release D) | **NOT READY** | Not started. Kept off for new customers. |
| Full commercial rollout | **NOT READY** | Depends on Release D and a real Stripe lifecycle. |

## 8. Items that need Pulse Fitness
- **Invitation email:** emails are held; nothing was sent.
  - To approve the single test send, set `INVITATION_EMAILS_LIVE=true` in the preview only.
  - Create one owner invitation to a Pulse test mailbox.
  - Check the sender, the production portal URL (`FRONTEND_URL`), the branding, and that the link works once and leads to MFA set-up.
  - Then switch it back to false. Pilot sending needs separate approval.
- **Stripe:** the preview's Stripe key is the platform proxy key, which can't call Stripe's Subscription APIs (`Invalid API Key` on `Account.retrieve`).
  - A real test-mode lifecycle needs Pulse's own Stripe test account in a staging deployment: upgrade, cancel at period end, withdraw cancellation, expiry, re-subscribe, duplicate webhook and failed payment.
  - The lifecycle logic is covered by handler-level tests (`test_release_ce.py`).
- **Existing managers:** managers created before this release are not forced onto MFA. Only new or promoted managers are. Decide whether to require MFA for all managers.
- **Release B and D work outstanding:**
  - Quantity-preserving matching for machines without serial numbers.
  - Shared contract identity.
  - Service-history reconciliation.
  - Safe Undo for older imports.
  - Shared person and site identities across CRM, Memberships and Marketing.
  - Prospect-to-member flow.
  - Unified email opt-outs.
  - A queue for cross-module updates.

## 9. Restore check result
See section 6 for the procedure. Result: a subset restore of the 7 key collections matched exactly (organizations 692, users 272, equipment 508, sites 115, customer_account_refs 10, sicon_external_links 166, secure_invitations 3). Details are in memory/CHANGELOG.md.

Release-critical suites after the fixes: 155 passed, plus 1 teardown error caused by a MongoDB restart, which passed on rerun (11/11).

The suites were: authorisation gate, Release 1, iteration 342, Release C/E, customer import (Release A, Sage/Sicon), AFS shared matching, estate scale, shared matching, Release A/B identity/338/339, onboarding consolidation, and the Sicon field-mapping and mapping-audit tests.
