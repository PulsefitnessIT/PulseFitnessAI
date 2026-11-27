# Pulse Fitness — Launch sign-off (27 November 2026)

**Final commit:** the latest "Auto-generated changes" commit on `main` after this file. Push it with **Save to GitHub**. The reviewed starting commit was `a62f2c0d`.
**Deployment:** not deployed. No live customer data was imported, no customer invitations were sent, and no payments or Sage/Sicon writes were enabled.

## 1. Security fixes in this round (all covered by tests in `backend/tests/test_release1_signoff.py`)
| Area | Fix |
|---|---|
| One organisation access check | `utils/team_guards.assert_user_may_access` blocks a customer whose organisation is awaiting activation, not activated (`portal_access`) or still importing (`provisioning_state`). It applies to:<br>- main sign-in<br>- every existing session (`_load_user_core`)<br>- token refresh<br>- CRM sign-in and every CRM request<br>- gym-floor device sessions<br><br>A customer set back to awaiting activation loses access within 10 seconds. Pulse administrators and operator organisations are never blocked. |
| CRM can't bypass the platform | Pending second-factor CRM tokens are refused as sessions. CRM tokens now carry the time they were issued (`iat`), so central session revocation applies to them. A CRM token is marked as two-step-verified (`mfa`) only after a real second factor: CRM TOTP, or the person's **own** MFA-verified platform session. If the platform account needs MFA, a CRM password login without CRM 2FA is refused. Disabled, revoked, removed or moved platform users lose CRM access. Revoked or disabled platform sessions can't be exchanged for CRM. |
| Invitation recovery | Acceptance now runs in this order: claim → user → **activate organisation** → consume invitation. Each step can be repeated safely. Recovery works at every stage: the person accepts again, or simply signs in (`complete_interrupted_activation`). In every case the result is one user, one owner, one consumed invitation and the same organisation ID, still on LITE. |
| Purchase routes | One gate (`utils/commercial_gate.py`) now covers **8 routes**: `/payments/checkout`, `/payments/checkout/flex`, `/me/crm-business/checkout`, `/me/module-trials/start`, `/me/upgrade-to-pro`, `/me/module-purchase/checkout`, `/financial-ops/checkout` and `/financial-ops/llm-top-up`. It applies to customers created by the Sage/Sicon import, however they were activated. MOD estates and self-sign-up customers are not affected. In the preview, no imported customer with users or paid products is affected. |
| Test invitation | `INVITATION_TEST_RECIPIENTS` (empty by default) lets one approved Pulse test mailbox receive the real branded email while `INVITATION_EMAILS_LIVE=false`. |

## 2. Test evidence
- New suites (preview, HTTPS):
  - `test_release1_signoff.py`: 17 passed. This covers the access check, CRM, the 4 interruption stages × 2 recovery routes, the purchase gate, the test-mailbox allowlist and the gym floor.
  - The other Release 1 suites (`test_release1_access.py`, `test_release1_gym_floor.py`, `test_release1_iter342.py`, `test_release1_iter343.py`, `test_release1_sicon_sample.py`) pass.
- Wider release-critical run on the preview after all fixes:
  - **184 passed, 0 product failures** across Release A/B identity and onboarding, onboarding consolidation, shared matching, AFS matching, Sicon field-mapping and mapping-audit, customer import Release A, all Release 1 suites, Release C/E and the authorisation matrix.
  - Two Release A/B tests signed in as the master admin with a CRM password. That is now refused by design, because the account needs MFA. Their sign-in helper now gets the CRM session the way the product issues it (an MFA-verified session); the assertions are unchanged.
  - One teardown error came from a MongoDB restart and passed on rerun.
  - `test_sage_sicon_customer_import`: 6/6 passed. The 5,200-row test was not re-run: about 19,000 leftover test organisations in the preview make it take more than 10 minutes. Commit speed (about 7 rows per second on this server) should be checked against the size of the real customer file before the full import.
- Independent test round iteration_344 (forced summary at its time limit):
  - All product checks it ran passed.
  - It found 5 Release 1 tests whose test data had `portal_access="not_activated"`, which is a set-up error. The tester fixed them and they pass.
  - Its code-review points are fixed: CRM MFA now uses only the person's own session, the access-check cache is bounded, and the purchase gate also covers imported customers activated another way. MOD estates are excluded.
- **Equivalent-conditions regression comparison.** Two runs of `make regression` had the same fresh MongoDB and a local backend with the same CI settings:
  - **Previous app commit `ae183314`** (application and tests): 211 failed, 51 errors, 2,378 passed.
  - **Release candidate:** 209 failed, 51 errors, 2,380 passed.
  - **New failures in the candidate: none.** Two failures from the previous commit now pass.
- GitHub Actions (as reported for a62f2c0d): Security Audit, Quality Gate, Zero-Trust and Pre-commit all **PASS**. The Full Backend Regression job **FAILS**, which is pre-existing (see section 3). Ruff and frontend lint/build pass locally on the final code.

## 3. Release exception register (the 260 failing or erroring regression tests)
None of these were introduced by Release 1. All of them also fail on the previous commit under the same conditions.
| Category | Approx. tests | Example | Risk for launch |
|---|---|---|---|
| Seeded demo accounts missing or locked in a fresh database | ~80 | `pulse.admin.test@…: Invalid credentials`, `Account temporarily locked` | **Low.** The test can't sign in; it doesn't show broken features. Coverage for sign-in, permissions and access comes from the Release 1 suites. Fix later: seed fixtures for CI. |
| Integration credentials not present in CI (object storage, AI) | ~30 | `500 Internal server error` ← `objstore storage/init 400` | **Low.** These features work in the preview with the platform key. Production must have the storage key (section 5). |
| Old assertions on frontend source text | ~60 | expected `data-testid`, copy text or component names that changed later | **Low** (cosmetic). Refresh in a clean-up release. |
| Test harness defects | ~25 | `MagicMock can't be used in 'await'`, `StopIteration`, `KeyError 'dispatched'` | **Low.** These are problems in the tests themselves. |
| Session-cookie tests over plain `http://` | ~10 | `iter232_active_sessions` | **Low.** They pass on the HTTPS preview. |
| Missing locale files | 4 | `i18n/locales/en.json` not found | **Low.** |
| **Security configuration decision** | 1 | `test_password_reset_ttl_default_is_15_minutes`: the code default is **7 days** (10080 min, set earlier on purpose) | **Medium.** A password-reset link stays valid for 7 days. **Recommendation:** set `PASSWORD_RESET_TTL_MINUTES=60` in production. This is your decision. |
| Status-code wording | 1 | `enforce_master_admin_mfa` returns 403, the test expects 401 | **Low.** Access is still refused. |

Release-critical areas (sign-in, permissions, customer import, Sage/Sicon isolation, entitlements) are covered by passing suites. SmartQuote, Contract OS, Service Desk and MOD failures are all in the categories above. None shows a broken workflow; most are sign-in fixtures.

## 4. Settings confirmed (preview, `GET /api/build-info` with an admin token)
- The preview reports `commit` a62f2c0d (updates on the next restart).
- All five switches are false: `SICON_ALLOW_WRITES`, `SAGE_ALLOW_WRITES`, `SICON_NIGHTLY_SYNC_ENABLED`, `INVITATION_EMAILS_LIVE`, `IMPORTED_CUSTOMER_PURCHASES_ENABLED`.
- **Production is not verified from here.** After deploying, Pulse IT must check `/api/build-info` and confirm:
  - The commit matches.
  - All five switches are false.
  - **`FRONTEND_URL` = the production portal address.** In the preview it is the preview address, and invitation links are built from it.
  - Production MongoDB settings, `RESEND_API_KEY` and the storage key are set, and no preview values are used.
- Before deploying, run this production check: list organisations blocked by the new rule that have users. In the preview the answer is 0.

## 5. Backup, migration and rollback
- **No production backup has been taken by me**, because I have no access to production. Pulse IT must run `mongodump` on production, restore it into a separate database, and compare document counts. The procedure is in `RELEASE_1_REPORT.md` §6 and `LIVE_ACCEPTANCE_SAGE_SICON.md` §0.
- **Legacy invitation migration:** **dry run only** (`POST /api/master-admin/legacy-invites/migrate {}`). Do **not** apply until you approve how the replacement invitations are delivered.
- No destructive migrations. Indexes are created automatically on first use. Rollback: redeploy the previous commit through Emergent. Release 1 only adds collections and fields, so no data rollback is needed.

## 6. GO / NO-GO
| Decision | Status | Basis |
|---|---|---|
| Internal production deployment | **GO**, after the production backup, restore check and settings check (§4–5) | All P0 fixes tested; no new regressions under the same conditions |
| Sage account spreadsheet import | **GO for the 5–10 customer pilot** | Customer import and Release A suites pass; LITE only, no users, no emails |
| Sicon contact spreadsheet import | **GO for the pilot** | Same suites |
| Full account and contact database import | **NO-GO** until the pilot is signed off | Your instruction |
| Live Sage retrieval | **NO-GO** until the supervised live check | Not reachable from development |
| Live Sicon equipment retrieval | **NO-GO** until the supervised live check (use the isolated database first; apply only to `sample_org_ids`) | Sample isolation tested with simulated Sicon data only |
| Customer activation pilot | **NO-GO** until one real test email is approved | Set `INVITATION_TEST_RECIPIENTS` to your test mailbox, test, then clear it |
| Manager and staff access | **GO** | Release 1 access and iteration 342/343 suites |
| Gym-floor access | **GO** | Gym-floor suites, including blocking organisations not yet activated |
| Paid product purchasing | **NO-GO** | No genuine Stripe test-mode lifecycle yet (the preview key can't use Subscription APIs) |
| Full commercial rollout | **NO-GO** | Release D and the real Stripe lifecycle are outstanding |

## 7. Still mandatory after launch (not done)
- Matching machines without serial numbers while keeping counts right.
- Shared maintenance contract identity.
- Service-history reconciliation.
- Safe Undo for older imports.
- Delegated staff access outside Master Admin.
- Shared CRM and operational sites.
- Shared CRM, Memberships and Marketing person identity.
- Central user identity and multi-organisation access.
- Prospect-to-member conversion.
- Unified communication preferences.
- Reliable cross-module updates.
- A genuine Stripe lifecycle test.

The platform must not be described as fully integrated until these pass acceptance.

**Notes for the release notes:**
- After deploying, CRM sessions of people with two-step verification will be signed out once, because older CRM tokens have no MFA marker. They simply open CRM again from the portal.
- The preview database holds about 19,600 leftover "TEST Large …" organisations from earlier test runs. They are being rolled back by import job; this doesn't affect production.
