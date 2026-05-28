# Flip the Production Env Flags — Step-by-Step

**Who:** You (admin/owner of the GymAxis Emergent deployment)
**When:** Before the pen-tester starts work
**How long:** 10 minutes
**Pre-requisite:** Latest deploy is live in prod (it is — code is on `main`)

---

## What this does

You're turning on six security gates that are coded into the platform but
default-OFF so dev/test environments don't have to set up TOTP, CRM rosters,
and ClamAV just to run the test suite. Once on, prod enforces:

* MFA required for master-admin endpoints
* Email sends only to known recipients (same-org / CRM contact / partner)
* Field-level Fernet encryption for stored integration secrets
* SSRF guard rejects metadata-server / IMDS lookups

Three of these are mandatory. Two depend on a ClamAV side-car you don't have
yet (and can skip for this engagement). One is an explicit denylist string
you'll paste verbatim.

---

## Step 1 — Generate the Fernet key (do this first, locally on your laptop)

Open a terminal (Mac/Linux) or PowerShell (Windows) and run:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> No Python? Use this online-equivalent (one-time, doesn't leave your laptop):
> https://fernetkeygen.com → click "Generate Key" → copy the result.

You'll get something like:
```
fG3Hb-_NbjL8sR... (44 characters ending in `=`)
```

**Copy this string somewhere safe** — a password manager entry called
`GymAxis · MFA_ENCRYPTION_KEY · 2026-Q2`. You'll paste it into the env
editor in step 3, and you'll need it again later for rotations.

⚠️  **Don't lose this.** If you lose it after enrolling MFA on your master
admin account, you'll have to disable MFA in the database and start over.

---

## Step 2 — Open the Emergent deploy environment editor

1. Log into your Emergent dashboard
2. Open the GymAxis project
3. Click the **Deploy** tab (top nav)
4. Click **Environment Variables** in the side panel
5. You'll see a list of existing vars: `MONGO_URL`, `JWT_SECRET`,
   `RESEND_API_KEY`, etc. Don't touch any of these.

---

## Step 3 — Add the env vars

Click **"Add variable"** and add each of these one at a time. Copy the
**Name** and **Value** columns exactly — including capitalisation.

| # | Name                                  | Value                                                | Notes                                                         |
|---|---------------------------------------|------------------------------------------------------|---------------------------------------------------------------|
| 1 | `ENFORCE_MASTER_ADMIN_MFA`            | `true`                                               | Mandatory.                                                    |
| 2 | `ENFORCE_EMAIL_RECIPIENT_VALIDATION`  | `true`                                               | Mandatory.                                                    |
| 3 | `MFA_ENCRYPTION_KEY`                  | _paste the key from Step 1_                          | Mandatory.                                                    |
| 4 | `SSRF_EXTRA_DENYLIST_HOSTS`           | `metadata.google.internal,metadata,169.254.169.254`  | Mandatory. Paste exactly — comma-separated, no spaces.        |
| 5 | `STRICT_AV_MODE`                      | `false`                                              | **Leave as `false`** — flip to `true` only after ClamAV ships.|
| 6 | `CLAMAV_HOST`                         | _leave blank / don't add_                            | Skip until ClamAV side-car is deployed (separate task).       |

After saving each one, the dashboard usually shows a green "Saved" tick.

---

## Step 4 — Trigger a redeploy

Same Deploy tab → click **"Redeploy"** (or "Restart" — whichever button is
labelled to push the new env vars into the running container).

Wait until the dashboard shows **"Deployment healthy"** (~30–60 seconds).

---

## Step 5 — Verify (2 minutes)

Open `https://app.gymaxisai.com` in a private/incognito browser and:

### Check 1 — Health endpoint still responds
Visit `https://app.gymaxisai.com/api/health`
**Expected:** `{"status":"ok"}` — exactly that, nothing more.
If you see version info or a stack trace, something else changed; ping me.

### Check 2 — Login still works for a regular user
Use any non-master-admin account you know the password for. Log in → should
land on the dashboard normally. Master-admin MFA enforcement doesn't affect
regular operator logins.

### Check 3 — Master admin login behaviour
Log in as `admin@gymaxisai.com` with your normal password.

**If you've already enrolled TOTP** on this account: you'll be prompted for
your 6-digit code as usual → enter it → land in the admin console normally.

**If you've NEVER set up TOTP**: you'll be prompted to enrol it on first
login after this flag is on. Scan the QR with Google Authenticator / 1Password
/ Authy → save the backup codes → enter your first 6-digit code → done.

> ⚠️ **Important**: Save the backup codes in your password manager. If
> you lose your phone before the engagement starts, those backup codes are
> the only way back in without a Mongo intervention.

### Check 4 — Confirm MFA is being enforced
After logging in successfully, leave the tab open. Open a **new private window**
and try to hit a master-admin endpoint directly:
`https://app.gymaxisai.com/api/master-admin/users`
**Expected:** `{"detail":"Not authenticated"}` (no cookie) — that's correct.

---

## Step 6 — Tell me you're done

Reply with "env flags flipped" (or any confirmation) and I'll:
1. Mark `Iter 220ay+ · env-flag rollout` as complete in the PRD
2. Hand the pen-tester the brief from `PEN_TEST_ONBOARDING.md`

---

## If something goes wrong

| Symptom                                                  | Most likely cause                              | Fix                                                                        |
|----------------------------------------------------------|------------------------------------------------|----------------------------------------------------------------------------|
| `/api/health` returns 502/503 after redeploy             | Container failed to start                      | Check the deploy logs for `MFA_ENCRYPTION_KEY` errors — most likely the key was malformed. Re-paste it (it should be 44 chars ending in `=`). |
| All login attempts return "Internal server error"        | `MFA_ENCRYPTION_KEY` malformed → MFA module won't load | Same fix — regenerate via Step 1, re-paste, redeploy.                      |
| Master admin can log in but immediately gets 401 on every page | TOTP not enrolled on `admin@gymaxisai.com` yet | Log out, log in again — enrolment screen should appear. If it doesn't, set `ENFORCE_MASTER_ADMIN_MFA=false`, enrol via Settings → Security → MFA, then flip back to `true`. |
| Customers complain emails aren't arriving                | A non-CRM recipient (e.g. a new lead not yet in `crm2_contacts`) is being blocked | This is the gate doing its job. Either add the recipient to `crm2_contacts` first, or temporarily set `ENFORCE_EMAIL_RECIPIENT_VALIDATION=false` for the affected send, debug, and flip back. |

**Rollback button:** if anything goes sideways, set the three mandatory
flags to `false` and redeploy. Backwards-compat is preserved — all existing
sessions and stored secrets keep working with the gates off.

---

_Last updated: 2026-05-28_
