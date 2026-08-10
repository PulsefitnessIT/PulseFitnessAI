# MFA Break-Glass & Recovery Runbook

`ENFORCE_MASTER_ADMIN_MFA=true` makes TOTP mandatory for the master admin, and the
master admin **cannot self-disable** MFA via the API/UI (returns 403). This runbook
covers recovery so you can never be permanently locked out.

## Layer 1 — Backup codes (self-service, preferred)
- At enrolment the admin receives **10 one-time backup codes**. Any one works in
  place of the authenticator code at the login MFA step.
- When codes run low, the admin can **regenerate** a fresh set in-console:
  `/master-admin?section=my-security` → "Regenerate backup codes" (requires a live
  authenticator code). Endpoint: `POST /api/auth/mfa/backup-codes/regenerate {code}`.
  Regeneration requires a **live TOTP** (a backup code is NOT accepted for this) so a
  single leaked backup code can't mint a new set.
- The console shows a **low-codes warning** when 3 or fewer remain.

## Layer 2 — Operator break-glass (lost device AND lost backup codes)
Run from a trusted operator shell with DB access (`/app/backend`). This is AUDITED
(writes a `mfa_break_glass_reset` security event visible in the Security Alert Centre):

```
PYTHONPATH=/app/backend python scripts/mfa_break_glass.py admin@pulsefitness.com "lost device + codes, verified identity via <method>"
```

Effect: clears the user's `user_mfa` record. Next login forces a fresh enrolment
(new QR + new backup codes) if MFA is still mandatory. No secret is exposed.

## Turning enforcement off (last resort / maintenance)
Set `ENFORCE_MASTER_ADMIN_MFA=false` (or remove) in `backend/.env` and restart backend.
Login then no longer requires MFA for the master admin.

## State checks (POST /api/auth/login)
- `{requires_mfa_enrolment: true}` → enrolled? no; enforcement on → will force enrolment.
- `{requires_mfa: true}` → enrolled; needs a code.
- `{token: ...}` → MFA off (or not required).
