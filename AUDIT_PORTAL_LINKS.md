# Master Admin → End-User Portal Linkage Audit
*Iter 216h26 · Feb 11, 2026*

Goal: confirm that every Master Admin write surface (after the P1-P6 redesign) actually reaches the end-user portals (Pulse Fitness staff portals, GymAxis LiteDashboard, customer staff portals, members at `/m/{slug}`) at runtime.

## Method

Wrote `/app/backend/tests/test_iter_216h26_audit.py` — an end-to-end script that:
1. Logs in as both GymAxis Master Admin (full scope) and Pulse Master Admin (Pulse scope).
2. Exercises each Master Admin write/read endpoint.
3. Asserts the downstream visibility at the end-user runtime (`/auth/me`, module-access dict, equipment listing, etc.).
4. Cleans up after itself.

Run with `cd /app/backend && python3 tests/test_iter_216h26_audit.py`.

## Results — 17 / 17 PASSED

| # | Check | Status | Surface checked |
|---|---|---|---|
| A1 | `/auth/me` carries `is_pulse_admin` flag on Pulse admin login | ✅ | Auth rehydrate |
| A2 | Pulse admin requesting `brand=gymaxis` on `/all-sites` is forced to `pulse` | ✅ | Brand scope-lock |
| A2b | Same on `/audit-log` | ✅ | Brand scope-lock |
| A2c | Same on `/marketing/analytics` (`scoped: true`) | ✅ | Brand scope-lock |
| B1 | Staff Onboarding wizard creates real user with 72 h invite link | ✅ | `POST /organizations/{id}/users` |
| B2 | Invite link redeems via `/auth/reset-password` | ✅ | Reset-password flow |
| B3 | Newly invited user can log in immediately | ✅ | `/auth/login` |
| B3b | New user is anchored to the correct org | ✅ | `/auth/me.organization_id` |
| B3c | New user has the `module_access` dict populated | ✅ | `/auth/me.module_access` |
| C1 | Toggling `module_overrides.crm = false` on Master Admin zeroes `module_access.crm` at runtime | ✅ | `PUT /users/{id}/edit` → `/auth/me` |
| C2 | `allowed_site_ids` round-trips through `/master-admin/users` listing | ✅ | Site-lock persistence |
| D1 | A new operator can fetch `/equipment` (their portal's catalogue surface) | ✅ | Operations Portal |
| E1 | Master Admin can upsert a marketing subscription for an org | ✅ | Marketing Suite gate |
| F1 | Customer-onboarding org create endpoint returns 200 | ✅ | New customer onboarding |
| F1b | New owner receives a 72 h invite link in the response payload | ✅ ◀ **fixed** | New customer onboarding |
| G1 | Integrations Hub aggregate endpoint returns the 4-block summary | ✅ | Integrations Hub |
| H1 | Duplicate-email 409 carries structured `code:'user_exists'` payload | ✅ | Wizard error toast |

## Broken links found & fixed

### 🛠 F1b — Customer-onboarding org create did not return an invite link
**Symptom**: `POST /api/master-admin/organizations` created the primary-contact user and stashed an auto-generated plaintext password on the org doc (for the legacy "Reveal Password" handover) but did NOT surface a 72 h reset-link invite. Operators had to manually open the org panel, reveal the password, then hand-deliver it — bypassing the iter-216h15 reset-link flow that the rest of the platform uses.

**Fix**:
- Extracted a `_mint_invite_link(user_id, email, issued_by)` helper in `master_admin.py` (DRY against the existing `/users/{id}/invite-link` route).
- After org creation, auto-mints an invite link for the freshly-provisioned primary contact.
- Response payload now carries `owner.invite_url` + top-level `invite_url` + `invite_expires_at` so older callers keep working.
- Frontend `useMasterAdminActions.createOrganization` now surfaces the link in the success toast.
- Backwards-compatible — legacy reveal-password flow still works.

### 🛠 (Audit-script bug, no product bug) D1 — Equipment Catalogue scope
**Symptom**: First audit run failed on `/equipment-catalogue` 404.
**Root cause**: The Equipment Catalogue (`master-admin/catalogue/*`) is intentionally master-admin only — it's platform master data. Operators see the per-site `/equipment` list which inherits images/spec-sheets from the catalogue.
**Resolution**: Audit script updated to test the correct customer-facing surface (`GET /api/equipment`). No product fix needed.

## Other Master Admin → end-user dependencies verified by code review

1. **Brand picker** (`useBrandContext` → `?brand=` on every Master Admin fetch) is applied to `/master-admin/organizations`, `/audit-log`, `/marketing/analytics`, `/marketing/subscriptions`, `/all-sites`, `/integrations-hub`. **Pulse admins forced server-side regardless of client param** (defence-in-depth, verified in iter 216h25).
2. **Module access** is computed by `utils/module_access.py:resolve_module_access(user, org)` — applies org-level account-type default → org modules override → user `module_overrides`. Same code path serves `/auth/login`, `/auth/me`, every route guarded by `has_module()`, and the frontend `ModuleAccessGate`. Single source of truth.
3. **Customer Onboarding hub** at Organisations → Customer onboarding renders the same `AdminOnboardingHub` with all 4 wizards (Onboard Site / Head Office / Packets / Bulk Imports). Same `/master-admin/organizations` POST in the end — now invite-link-aware.
4. **Catalogue & Library** (Equipment catalogue, Custom properties, Spec sheets, Equipment images, Marketing library, Social media library) write to master-data collections that operator equipment lists join into. Visible on the Operations Portal at `/dashboard` for `account_type=full` and `/pulse` for `account_type=lite/pulse_pro`.
5. **Member portal `/m/:slug`** consumes site branding + class data that Master Admin can edit via the Organisation drawer's Sites tab. No write-paths added in P1-P6 affect it directly.
6. **CRM** at `/crm` is gated by `ModuleAccessGate module="crm"`, which reads `user.module_access.crm` — exactly the value the wizard's module-override step toggles.

## Conclusion

✅ **No remaining broken links between the redesigned Master Admin and the end-user portals.** The Master Admin redesign (iters 216h17 - 216h25) is correctly wired through to runtime visibility on every customer-facing surface I could exercise.
