# Email Deliverability Sanity Check — Pre-Pen-Test (May 28, 2026)

> **Status:** Operator runbook. You (the user) execute these DNS checks.
> The platform code is fine — this is purely a configuration audit so
> spam-folder routing doesn't burn live demo requests during the pen-test
> window.
>
> **Domains in scope:**
>
> - `gymaxisai.com` (primary marketing + transactional)
> - `in.gymaxis.com` (planned inbound subdomain for support@/sales@)
>
> If you've added any other From: domains via Resend, add them to the
> list below.

---

## Why this matters

The platform sends transactional email (signup confirmations, password
resets, GDPR receipts, demo-request acknowledgements) via **Resend**. If
your DNS doesn't expose SPF / DKIM / DMARC, recipient mail servers
(Microsoft, Google, etc.) will silently down-rank or quarantine these.
The pen-tester won't see them. Real prospects won't either.

The fix is 5 DNS records and ~10 minutes.

---

## 1 · Pull the current state of the world

Run these from any terminal (Linux / macOS / WSL) **before** changing
anything, so you have a rollback baseline:

```bash
# SPF — should mention "include:resend.com" or similar Resend hostname
dig +short TXT gymaxisai.com | grep -i spf

# DKIM — Resend defaults to selector "resend"
dig +short TXT resend._domainkey.gymaxisai.com

# DMARC
dig +short TXT _dmarc.gymaxisai.com

# MX — check the domain accepts inbound (for return-path bounces)
dig +short MX gymaxisai.com
```

Repeat for `in.gymaxis.com` if you've configured it as a sender.

Save the output. Example "good" baseline:

```
;; SPF
"v=spf1 include:_spf.resend.com ~all"

;; DKIM
"v=DKIM1; k=rsa; p=MIIBIjANBgk…"

;; DMARC
"v=DMARC1; p=quarantine; rua=mailto:dmarc@gymaxisai.com; aspf=r; adkim=r"
```

---

## 2 · What needs to be in place

### 2.1 SPF (required)

One TXT record at the apex (`@`) of each sender domain:

```
gymaxisai.com.   IN  TXT  "v=spf1 include:_spf.resend.com ~all"
```

- **One SPF record per domain only.** Multiple TXT records starting
  with `v=spf1` cause SPF validation to **fail closed** (PermError) —
  recipients will reject your mail outright.
- If you also send via Stripe, Microsoft 365, or Google Workspace from
  the same domain, **merge** their includes into the single SPF record:

```
"v=spf1 include:_spf.resend.com include:spf.protection.outlook.com include:_spf.google.com ~all"
```

- Use `~all` (soft-fail) during onboarding; harden to `-all` only after
  you've watched 7 days of Resend-side reports and confirmed zero
  legitimate sources are missing.

### 2.2 DKIM (required)

Resend gives you 3 DKIM TXT records when you verify a domain in the
**Resend Console → Domains → Add domain** flow. They look like:

```
resend._domainkey                IN  TXT  "v=DKIM1; k=rsa; p=…"
resend2._domainkey               IN  TXT  "v=DKIM1; k=rsa; p=…"
resend3._domainkey               IN  TXT  "v=DKIM1; k=rsa; p=…"
```

Paste these verbatim into your DNS provider. The Resend dashboard will
show a green tick when propagation completes (usually < 1 hour, can
take up to 24 hours).

### 2.3 DMARC (required for enterprise inboxes)

DMARC builds on SPF + DKIM. Until both are passing, leave DMARC at
`p=none` so you don't silently drop legit mail:

```
_dmarc.gymaxisai.com.  IN  TXT  "v=DMARC1; p=none; rua=mailto:dmarc@gymaxisai.com; aspf=r; adkim=r"
```

After 14 days of clean reports (no spoofing, no legitimate mail
quarantined), promote to:

```
"v=DMARC1; p=quarantine; pct=25; rua=mailto:dmarc@gymaxisai.com"
```

Then after another 14 days:

```
"v=DMARC1; p=reject; rua=mailto:dmarc@gymaxisai.com"
```

`p=reject` is the gold standard. Microsoft 365 inbound and most banks
won't even open mail from a domain at `p=none`.

### 2.4 Return-Path / Bounce processing (optional but recommended)

Set up a custom Return-Path domain (`bounces.gymaxisai.com` CNAME to
Resend's bounce subdomain) so bounce processing happens under your
brand. Resend dashboard guides you through this.

### 2.5 MTA-STS / TLS-RPT (defence-in-depth)

For enterprise prospects who run their own DMARC checks:

```
mta-sts.gymaxisai.com.  IN  TXT  "v=STSv1; id=2026052801;"
_smtp._tls.gymaxisai.com. IN  TXT  "v=TLSRPTv1; rua=mailto:tlsrpt@gymaxisai.com"
```

Plus serve `mta-sts.txt` over HTTPS at `https://mta-sts.gymaxisai.com/.well-known/mta-sts.txt`:

```
version: STSv1
mode: enforce
mx: feedback-smtp.eu-west-1.amazonses.com     # whichever MX Resend tells you
max_age: 86400
```

This is **bonus** — pen-testers tick a box, prospects feel safer. Not
mandatory for pen-test pass.

---

## 3 · Sender-side checks (run these once DNS is in)

```bash
# Free online checker — gives a clean PDF you can hand to procurement
open https://www.mail-tester.com/

# Send a test message:
#   1. From the Resend dashboard → Send test email → paste the address shown by mail-tester
#   2. Refresh mail-tester — target score = 9.5 / 10 or higher
```

Specific signals to verify on mail-tester:

| Check | Expected |
|---|---|
| SPF | PASS, includes Resend |
| DKIM | PASS, signature validates |
| DMARC | PASS, p=quarantine or reject |
| Reverse DNS | matches sending IP |
| Not on Spamhaus / Barracuda | clean |
| List-Unsubscribe header (marketing only) | present |

---

## 4 · Per-feature smoke tests on preview

Once DNS is in, do a final smoke pass against the preview env to make
sure no transactional flow is being silently dropped:

```bash
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)

# 1. Public demo-request (sales inbox notification)
curl -s -X POST "$API/api/public/demo-request" \
  -H "Content-Type: application/json" \
  -d '{"name":"Deliverability Smoke","email":"deliverability+smoke@example.com","company":"Smoke Co","site_count":1,"message":"test"}'

# 2. Password reset (auth flow)
curl -s -X POST "$API/api/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@gymaxisai.com"}'
```

Both should return HTTP 200. Resend dashboard should show the
corresponding events in **Logs → Activity** within 10 seconds. Green
delivery status against the actual inbox = pass.

---

## 5 · Rollback

If anything breaks customer mail flow:

1. Restore the SPF / DMARC TXT records from your **§1 baseline**.
2. DNS propagation: 15 minutes – 1 hour.
3. Confirm with `dig` again before sending another batch.

Don't keep `p=reject` on if you don't trust the SPF/DKIM alignment yet
— flip back to `p=none` while you debug.

---

## 6 · Sign-off checklist

Tick before you tell the pen-tester you're ready:

- [ ] `dig +short TXT gymaxisai.com` returns exactly one SPF record.
- [ ] All three Resend DKIM selectors resolve.
- [ ] `_dmarc.gymaxisai.com` is at least at `p=quarantine`.
- [ ] mail-tester.com scores ≥ 9.5/10 for a Resend-sent test.
- [ ] Preview-env smoke (`§4`) lands cleanly in an inbox you control.
- [ ] In Resend dashboard → Domains, the `gymaxisai.com` row is fully
      green ("Verified · DKIM · SPF · Return-path").

---

*This runbook is operator work — code-side delivery is already wired
through `utils/email.send_email`. Last reviewed Iter 220ba (May 28, 2026).*
