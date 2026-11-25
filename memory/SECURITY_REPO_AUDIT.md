# Repository information audit — 2026-11-25 (public repo PulsefitnessIT/PulseFitnessAI)

## Removed from the working tree (and from version control going forward)
| Item | Why sensitive | Action | Original kept at |
|---|---|---|---|
| `backend/tests/fixtures/mod_quotes/schedule_b_sor.xlsx` | Full MOD Schedule B contract pricing (LSLDC0223) | Deleted; replaced by synthetic generator `backend/tests/mod_quote_fixtures.py` (same layout; only the 9 historical-test categories + call-out carry their historical values) | Object storage `restricted/mod_quote_originals/schedule_b_sor.xlsx` |
| `backend/tests/fixtures/mod_quotes/reference_{A,B,AB}.png` | Renders of real issued quotations QT9410–QT9412 (HMNB Clyde) | Deleted | `restricted/mod_quote_originals/` |
| `test_reports/mm_tmp/real_mm.xlsx` (7.7 MB) | Real multi-customer Maintenance Master workbook | Deleted | `restricted/maintenance_master/real_mm_test_copy.xlsx` |
| `test_reports/mm_tmp/mmt_ui.xlsx`, `rebuild_probe.py` | Derived test artefacts | Deleted | — |
| `.lintfix/` | Local lint tooling and failure lists | Deleted | — |
| `memory/test_credentials_bfpo.md` | Passwords for 4 preview accounts (`*@bfpo.pulsefitness.test`) | Untracked (`git rm --cached`) and git-ignored; file kept locally for the agents | local only |

`.gitignore` now blocks `backend/tests/fixtures/mod_quotes/`, `test_reports/mm_tmp/`, `memory/test_credentials_bfpo.md`, `.lintfix/` (`memory/test_credentials.md` was already ignored).

## Secret scan
Pattern scan of all tracked files (Stripe `sk_live_`, OpenAI `sk-`, AWS `AKIA`, Resend `re_`, GitHub `ghp_`, Slack `xox`, private keys): **no live keys found** (one false positive: a function name in a test). Tests with "credential" in the name use synthetic values.

## Still in Git history (requires management approval — not done)
The files above remain retrievable from earlier commits (from `f6973d3b` and earlier). Removing them needs a history rewrite (`git filter-repo --path <file> --invert-paths`), a force-push to `main`, re-cloning by all contributors, and a GitHub support request to purge cached views/forks. Recommended only after approval because it rewrites every commit SHA.

## Rotation plan (preview test accounts)
The four `*.pulsefitness.test` BFPO accounts and the accounts in `memory/test_credentials.md` exist only in the preview database. If any were ever created in production: disable them or reset their passwords in Master Admin → Users. No production credential was found in the repository.

## Other tracked business files to review (not removed — runtime dependencies)
`backend/seed_data/pulse_price_list.xlsx` and `backend/scripts/data/contract_quoting.xlsx` are loaded by seed/pricing code. Confirm with Commercial whether these are publishable; if not, move them to object storage and load at runtime.
