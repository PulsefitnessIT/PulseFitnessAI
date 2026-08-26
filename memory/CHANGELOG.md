# CHANGELOG

## 2026-06 — 4 bug fixes: job-role chips, Forgot Password, archive layout, operator-portal context

- **Bug 1 (Job roles)** `LiteDashboard/staffing/HRTab.js`: built-in role chips in the "Manage job roles" modal are now clickable buttons (`job-roles-builtin-{role}`) that populate the "Add a role" input. VERIFIED by testing_agent (owner@isodemo.com, 9/9 chips).
- **Bug 2 (Forgot Password)** root causes fixed & VERIFIED:
  - `utils/security.py`: split the single 3/15min limiter into `rate_limit_password_reset` (requests, key `resetreq:`, 5/15min) and NEW `rate_limit_password_reset_submit` (submissions, key `resetsubmit:`, 15/15min). `routes/auth.py` reset-password now uses the submit limiter. Previously a user who requested a link then mistyped their new password 2-3× got locked out (429).
  - `pages/ResetPasswordPage.js`: live password-requirements checklist (12+/upper/lower/digit/symbol, `reset-password-rules`) mirroring backend policy; client-side validation before POST; minLength 12 on both fields; added `CaptchaWidget` to the request form (was missing the captcha token → would 400 in prod if captcha enabled).
- **Bug 3 (Archive layout)** `MasterAdmin/AdminOrganizations.js`: org-user row no longer collapses the name/email into a vertical one-letter column when extra buttons appear (archived). Name column reserves `sm:w-60 flex-shrink-0` + `truncate`; actions use `sm:flex-1` and wrap. NOTE: verified by code only — live master-admin UI check blocked by TOTP MFA.
- **Bug 4 (Pulse Fitness Portal)** `routes/auth.py` `/auth/refresh` + `utils/auth.py`: refresh now PRESERVES the `act_org` (and `imp_grants`) JWT claim via `extra_claims`. Previously the frontend's on-load/15-min refresh minted a token without `act_org`, silently reverting a master admin out of the operator company (Pulse Fitness Ltd) back to their home org within seconds — cause of "portal shows no data" and "reverts to Head Office after visiting CRM". VERIFIED by curl: refreshed act_org token still returns the 6 Pulse Fitness Ltd staff. Live master-admin UI check blocked by MFA.


## 2026-06 — MOD Tender pack (LSL/DC/0223) finalised in-place

Edited all 6 `.docx` responses in place (templates, images, headers/footers, tables preserved) against Red Team reviews + Sheen/Director comments. Then a tender-writer QA pass drove a final correction round.

### Final correction round (tender-writer QA)
- **Figures embedded**: user-supplied corrected process maps for 2.2A (UK) and 2.3A (overseas) swapped into `word/media/image3.png` in each docx, with drawing extents adjusted to the new aspect ratios (no distortion).
- **All `[PULSE INPUT]` removed** across all 6 docs, populated with confirmed data:
  - Contract **LSL/DC/0186** (1 Apr 2023–31 Mar 2027); original value **£4,000,000**; delivered **£966,886.64** (UK £851,241.43; UK 2yr-to-30Jun2026 £719,479.54); overseas £115,645.30 (£84,549.87 2yr); **127 contract sites (9 overseas)** within **226-site** estate.
  - Overseas: **100%** ack within 48h and 100% scheduled within 5 working days; Type C **9/9** accepted. Canada = direct UK Type C. Gibraltar: Sean Coakley removed → Jimmy Connors.
  - UK 48/72 historic split confirmed unavailable → handled transparently (no fabricated stat).
- **2.1**: QP149 caption → Issue 02, 1 Nov 2025; UKAS/ISO 9001 assurance paragraph reinstated; MI wording → "agreed contract reporting route".
- **2.2B**: contract identified with values/sites; HMS testimonials no longer over-claimed as priority sites; KPI historic positions stated honestly.
- **2.3A/2.3B**: courier 3–10 days; portal caption transparency; 2.3B reframed as contract, Cyprus/Jersey/Norway reconciled.

**Deliverables** (`/app/tender_deliverables/`): `FINAL_Submission_Edited/` (6 docs), `MOD2026_Submission_EDITED.zip`, `Figure_Build_Specs.docx`, `Figure_Handover_Brief.docx`, `Pulse_Input_Required_Register.docx` (all resolved), `Score_Review.docx`.

**Estimated score after this pass: ~96–100/100** (from ~76). 2.2B carries a residual risk (unprovable historic 48/72 split, handled transparently).
