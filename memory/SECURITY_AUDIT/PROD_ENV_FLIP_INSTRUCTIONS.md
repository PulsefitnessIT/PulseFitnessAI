# Flipping the Pen-Test Security Flags — Updated Instructions

**Replaces the previous version.** The Emergent platform doesn't expose
an "Add variable" dashboard — env vars live in `/app/backend/.env` and
the agent (me) writes them. There's also no preview-vs-prod env
separation on Emergent native deploys: the deployed pod uses the same
`.env` as the preview. That means flipping these flags affects the
preview test suite too.

The cleanest workflow is a **one-button shell script** that toggles
the 3 enforcement flags ON for the pen-test window and OFF afterwards.

---

## Current state

Already set by me, permanently (these don't break tests):

| Var                          | Value                                              |
|------------------------------|----------------------------------------------------|
| `MFA_ENCRYPTION_KEY`         | _server-generated Fernet key, 44 chars_            |
| `SSRF_EXTRA_DENYLIST_HOSTS`  | `metadata.google.internal,metadata,169.254.169.254`|

OFF by default (would break the test suite if left on):

| Var                                  | Default | Flip via                                              |
|--------------------------------------|---------|-------------------------------------------------------|
| `ENFORCE_MASTER_ADMIN_MFA`           | off     | toggle script (below)                                 |
| `ENFORCE_EMAIL_RECIPIENT_VALIDATION` | off     | toggle script (below)                                 |
| `STRICT_AV_MODE`                     | off     | toggle script (auto-stays-off without ClamAV)         |

---

## Pen-test day workflow

### Before kick-off (5 minutes)

Tell me **"flip pen-test flags ON"** in chat. I'll run:

```bash
bash /app/scripts/toggle_pentest_flags.sh on
```

This sets the 3 enforcement flags to `true` in `.env`, restarts the
backend, and confirms the gates are live. I'll then run a verification
curl loop and paste the results so you have a dated proof-of-state to
attach to the pen-test brief.

> **Trade-off**: while the flags are ON, ~9 tests in the regression
> suite will fail (they don't pre-arrange MFA / known-recipient
> context). That's fine for the engagement window because we're not
> shipping code during it.

### Master admin login (one-time, 2 minutes)

Once the flags are on:

1. Open `https://app.gymaxisai.com` in a private/incognito browser.
2. Log in as `admin@gymaxisai.com` with your normal password.
3. If you've never set up TOTP, you'll be prompted to enrol it:
   - Scan the QR code with Google Authenticator / 1Password / Authy.
   - **Save the backup codes** in your password manager.
   - Enter your first 6-digit code → done.
4. From now on every master-admin login requires the 6-digit code.

### During the engagement

Pen-tester works against `https://app.gymaxisai.com` with the credentials
from `PEN_TEST_ONBOARDING.md`. Findings land in `PEN_TEST_FINDINGS.md`.

### After the engagement (1 minute)

Tell me **"flip pen-test flags OFF"** in chat. I'll run:

```bash
bash /app/scripts/toggle_pentest_flags.sh off
```

Flags clear from `.env`, backend restarts, regression suite is green again,
dev cycle resumes.

---

## Status check anytime

Tell me **"check pen-test flag status"**:

```bash
bash /app/scripts/toggle_pentest_flags.sh status
```

Returns:
```
[toggle] current state:
  ENFORCE_MASTER_ADMIN_MFA                 <not set / off>
  ENFORCE_EMAIL_RECIPIENT_VALIDATION       <not set / off>
  STRICT_AV_MODE                           <not set / off>
```

---

## Why we can't just leave them ON permanently

Emergent's deploy model uses one `.env` file for both the preview pod
(where the test suite runs) and the deployed pod. So:

- **Flags ON in `.env`** → prod-style enforcement, but 9 tests fail
- **Flags OFF in `.env`** → tests pass, but the gates aren't active

The toggle script gives us prod-style enforcement on demand, without
permanently breaking the dev workflow. If the Emergent platform later
exposes a deploy-time env-var injection mechanism (so the deployed pod
sees `flags=true` while the preview pod sees `flags=false`), we'll
switch to that and retire the toggle. For now, this is the cleanest
practical pattern.

---

## ClamAV side-car (still ops-team work)

`STRICT_AV_MODE` stays `false` even when you flip the other two on,
because flipping it to `true` without a reachable ClamAV daemon would
503 every upload. Once the side-car is deployed (k8s YAML in
`DEPLOY_RUNBOOK_PENTEST.md` §3) and `CLAMAV_HOST` is set, the toggle
script automatically flips `STRICT_AV_MODE` to `true` too.

Until then, the static-signature scan (EICAR + shell-in-image) remains
the active AV layer. That's documented in
`PEN_TEST_ONBOARDING.md` §5 as accepted residual risk.

---

_Last updated: 2026-05-28 · supersedes the v1 instructions._
