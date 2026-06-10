> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> Recovery procedure below remains current. Updated production
> URLs since the doc was written:
>
> - Production: `https://gymaxisai.com`
> - Preview: `https://seo-fix-preview-4.preview.emergentagent.com`
>
> The `admin@gymaxisai.com` master-admin credentials in
> `memory/test_credentials.md` are valid for both environments.
> Account lockout is now in-memory (`utils/security.py:_locked_accounts`)
> so a backend restart clears it — see iter 216h231 collateral note.

---


# Master Admin Recovery on Production

If you ever can't sign in as `admin@gymaxisai.com` on the deployed app
(e.g. fresh deploy, stale DB, lost password), this is the lifeline.

## How it works

A single endpoint at `POST /api/auth/admin-recovery` that:

- Refuses every request with **HTTP 404** when the env var
  `ADMIN_RECOVERY_TOKEN` is **not set** (default state — secure).
- When `ADMIN_RECOVERY_TOKEN` is set, accepts JSON `{recovery_token, email, password}`.
  - Wrong token → HTTP 403 with a timing delay (slows brute force).
  - Correct token → upserts the master admin user with the email/password
    you provide, clears any lockout, sets `is_master_admin=True`,
    `active=True`, `must_change_password=false`, `temp_password_expires_at=null`.
- After use, **rotate or unset** `ADMIN_RECOVERY_TOKEN` to disable recovery again.

## One-time prod setup

1. Pick a strong random token, e.g. via:
   ```bash
   openssl rand -hex 32
   ```
2. In your **deployed** Emergent app's Environment settings, add:
   ```
   ADMIN_RECOVERY_TOKEN=<the-token-from-step-1>
   ```
3. Click **Save** / **Restart** so the backend picks up the new env var.

## Recover the master admin

```bash
DEPLOYED_URL="https://your-deployed-app.example.com"
TOKEN="<your ADMIN_RECOVERY_TOKEN value>"

curl -X POST "$DEPLOYED_URL/api/auth/admin-recovery" \
  -H "Content-Type: application/json" \
  -d "{
    \"recovery_token\": \"$TOKEN\",
    \"email\": \"admin@gymaxisai.com\",
    \"password\": \"MasterAdmin123!\"
  }"
```

Expected response:
```json
{"success":true,"email":"admin@gymaxisai.com","message":"Master admin password reset. Please sign in."}
```

Now sign in via either the GymAxis homepage or Pulse homepage.

## After you're back in

**Important:** rotate or remove `ADMIN_RECOVERY_TOKEN` from your deployed
env vars (or set it to an empty string) so the endpoint goes back to
returning 404.

## Why the seed alone isn't always enough

`_seed_master_admin` runs at backend startup and self-heals the master admin
on every boot. But if:

- The startup hook ran into an unhandled error elsewhere before reaching
  the seed, OR
- The deployed DB is on a different cluster than expected, OR
- The deploy didn't actually rebuild the backend container,

…the seed may not have repaired the user record. The recovery endpoint is
a no-rebuild lifeline that doesn't depend on container restart.

## Pulse Pro test user `lee.somers@pulsefitness.com`

This user is **NOT auto-seeded** on prod. It only exists in the dev DB.
On prod, register a fresh org via the normal sign-up flow with whatever
email you want, then promote them to master admin from the Master Admin
console if needed.
