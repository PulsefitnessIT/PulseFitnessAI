# GymAxis · Complete Stripe Integration & Operations Guide

**Audience:** GymAxis platform owner / operator + engineers maintaining the codebase.
**Scope:** Every Stripe money-flow in GymAxis — both directions — with the exact endpoints, environment variables, Stripe Dashboard configuration, webhooks, test plan and go‑live checklist.
**Last reviewed:** June 2026 · matches the current codebase.

> ℹ️ The Stripe **code is already implemented and wired** in GymAxis. This guide is the operating manual: what to switch on in the Stripe Dashboard, which env vars to set, which webhooks to create, and how to test & go live. You do **not** need to write new code to use any flow described here.

---

## 0. The big picture — two directions of money

GymAxis moves money in **two independent directions**. Keep them separate in your head; they use different Stripe features.

```
 DIRECTION A — GymAxis gets paid (platform billing)
 ┌─────────────┐   £30/£15 app-fee sub      ┌────────────┐
 │  Engineers  │ ─────────────────────────▶ │            │
 └─────────────┘                            │  GymAxis   │
 ┌─────────────┐   module/bundle subs       │ (platform  │
 │    Orgs     │ ─────────────────────────▶ │  account)  │
 └─────────────┘                            └────────────┘
        These use STANDARD Stripe Checkout subscriptions on the PLATFORM account.

 DIRECTION B — Engineers & Orgs get paid by THEIR customers (Stripe Connect)
 ┌──────────────┐  pays card invoice   ┌─────────────┐
 │ Eng customer │ ───────────────────▶ │  Engineer   │  Direct Charge, 0% platform fee
 └──────────────┘                      │ (connected) │
 ┌──────────────┐  pays membership     ┌─────────────┐
 │  Gym member  │ ───────────────────▶ │  Org / gym  │  Connect sub, GymAxis takes 1% fee
 └──────────────┘                      │ (connected) │
                                       └─────────────┘
        These use STRIPE CONNECT — each engineer/gym has their OWN connected account.
```

| | **Direction A — Platform billing** | **Direction B — Connect** |
|---|---|---|
| Who pays | Engineers & Orgs | Their customers (eng customers, gym members) |
| Who receives | **GymAxis** | **Engineer / Org** (GymAxis may take a fee) |
| Stripe feature | Checkout **subscription** on the platform account | **Connect** (Express/Standard connected accounts) |
| Platform fee | n/a (this *is* GymAxis revenue) | Engineers: **0%** · Orgs: **1%** application fee |
| Where the funds land | GymAxis Stripe balance | The engineer's / gym's Stripe balance |

---

## 1. Stripe account model

* **One platform account** = your GymAxis Stripe account. The live key `STRIPE_API_KEY=sk_live_…` is already configured.
* **Many connected accounts** = one per engineer and one per gym/org, created through Connect onboarding. Their id looks like `acct_…` and is stored on our records:
  * Engineer → `partner_engineers.payout.stripe_account_id`
  * Org → `organizations.stripe_account_id`

### Connected-account types we support
| Cohort | Type | How it's created | Charge type |
|---|---|---|---|
| **Engineers** | **Express** | We call `Account.create(type="express")` then a hosted onboarding link | **Direct Charge** (`stripe_account=acct_…`), no application fee |
| **Orgs/gyms** | **Express** (default) | Same Express flow, master-admin initiated | **Destination/Connect subscription** with `application_fee_percent = 1%` |
| **Orgs/gyms** | **Standard** (optional) | Org pastes an existing `acct_…`, or OAuth connect | Same 1% fee |

---

## 2. Prerequisites (one-time, in the Stripe Dashboard)

1. **Log in** to the platform Stripe account that owns `sk_live_…`.
2. **Enable Connect:** Dashboard → **Connect → Get started** → choose **Platform or marketplace**. Complete the platform profile (business details, support email, statement descriptor).
3. **Brand the Express onboarding:** Connect → **Settings → Branding**: upload the GymAxis logo, set the brand colour and your support URL. This is what engineers & gyms see during onboarding (hosted flow).
4. **Confirm capabilities are allowed:** `card_payments`, `transfers` (engineers + orgs) and `bacs_debit_payments` (orgs). These are *requested* in code on each connected account.
5. **(Optional) Standard OAuth connect for orgs:** if you want gyms to link an *existing* Stripe account via OAuth, register an OAuth redirect at Connect → **Settings → Integration/OAuth** and capture the **client id** + redirect URI (env: `STRIPE_CONNECT_CLIENT_ID`, `STRIPE_CONNECT_REDIRECT_URI`).

---

## 3. Environment variables (backend/.env)

> Edit `.env` with the file editor only (never `echo`/heredoc), then `sudo supervisorctl restart backend`.

### Core keys
| Var | Status | Purpose |
|---|---|---|
| `STRIPE_API_KEY` | ✅ set (`sk_live_…`) | Secret key used by **all** Stripe calls. Use `sk_test_…` in preview to test safely. |
| `STRIPE_PUBLISHABLE_KEY` | ✅ set (`pk_…`) | Public key (front-end / embedded use). |
| `STRIPE_WEBHOOK_SECRET` | ✅ set | Signing secret for **platform** + Direct-charge webhooks. |
| `STRIPE_CONNECT_WEBHOOK_SECRET` | ⚠️ **not set** (falls back to `STRIPE_WEBHOOK_SECRET`) | Dedicated signing secret for the **Connect** webhook endpoint. Recommended to set. |
| `PUBLIC_ORIGIN` | ⚠️ **not set** | Canonical app origin for Stripe return/refresh links, e.g. `https://gymaxisai.com`. Falls back to `REACT_APP_BACKEND_URL` (the preview URL) if missing — **set this for production.** |
| `STRIPE_CONNECT_CLIENT_ID` | optional | Only for Standard OAuth org connect. |
| `STRIPE_CONNECT_REDIRECT_URI` | optional | Only for Standard OAuth org connect. |

### Platform price IDs (Direction A — GymAxis revenue)
These map GymAxis plans/modules to Stripe Price objects. All already set:

| Var | Plan |
|---|---|
| `STRIPE_PRICE_PARTNER_PLAN_30` | Engineer app-fee £30/mo |
| `STRIPE_PRICE_PARTNER_PLAN_15` | Engineer app-fee £15/mo (5+ active referrals tier) |
| `STRIPE_PRICE_GYMAXIS_PRO` / `_ANNUAL` | GymAxis Pro bundle (all modules) |
| `STRIPE_PRICE_OPERATIONS` / `_ANNUAL` | Operations module |
| `STRIPE_PRICE_MEMBERSHIPS` / `_ANNUAL` | Memberships module |
| `STRIPE_PRICE_CRM` / `_ANNUAL` / `_BUSINESS` | CRM module |
| `STRIPE_PRICE_MARKETING` / `_ANNUAL` | Marketing module |
| `STRIPE_PRICE_SITE_ADDON` / `_ANNUAL` | Extra-site add-on |
| `STRIPE_PRICE_STARTER` / `_PRO` / `_ENTERPRISE` | Legacy tiers |

> **Important:** Price IDs are environment-specific. Live-mode prices (`price_…`) are different objects from test-mode prices. If you test with `sk_test_…`, you must point these vars at **test-mode** price IDs.

---

## 4. DIRECTION A — GymAxis collects from Engineers & Orgs

### A1. Engineer app-fee subscription (£30/mo, or £15 tier)

The engineer trial → subscription pipeline (10-day free trial → feedback form → Stripe) is fully automated. Manual subscription start is also available.

* **Create checkout:** `POST /api/partners/me/subscription/checkout`
  * Auto-selects the price from the partner's `app_fee_tier` (£30 default, £15 at 5+ active referrals, free tier returns a friendly 400).
  * Returns a Stripe Checkout `mode=subscription` URL. Idempotent via an idempotency key.
* **Cancel / resume:** `POST /api/partners/me/subscription/cancel` · `POST /api/partners/me/subscription/resume`
* **Trial pipeline (no card needed to trial):** master-admin starts a trial (`POST /api/partners/{id}/start-trial` or `approve-with-trial`); on day 10 a tokenised feedback form is emailed; **Accept → Stripe checkout**, Decline/no-response → suspend. Worker: `utils/partner_trial_lifecycle.py`.
* **Settled to:** the GymAxis platform balance (this is GymAxis revenue).
* **Webhook handling:** the central platform webhook (`POST /api/webhook/stripe`) receives `checkout.session.completed` and calls `handle_partner_checkout_completed(...)`, which flips the trial to `converted_paid` and activates the subscription. Subscription lifecycle (`customer.subscription.updated/deleted`) keeps status in sync.

### A2. Org module & bundle subscriptions

Orgs buy GymAxis Pro (bundle) or individual modules (Operations / Memberships / CRM / Marketing) — flat monthly subscriptions (catalogue in `routes/payments.py` `PRICING_CATALOG`).

* **Pricing config (public):** `GET /api/payments/pricing` · `GET /api/payments/config` (includes `stripe_configured`).
* **Create checkout:** `POST /api/payments/checkout` (body: `plan="bundle"|"module"`, `module_id` for module). Also `POST /api/payments/checkout/flex`.
  * In-app module upsell (CRM business mode) uses `POST /api/me/crm-business/checkout` (price `STRIPE_PRICE_CRM_BUSINESS`), status `GET /api/me/crm-business/checkout/{session_id}/status`.
* **Status poll:** `GET /api/payments/status/{session_id}`.
* **Trial conversion:** if the org is on a trial, the session is tagged with `trial_org_id` / `trial_convert` metadata so the webhook converts the trial on payment.
* **Settled to:** GymAxis platform balance.
* **Webhook:** `POST /api/webhook/stripe` → `checkout.session.completed` activates the subscription/modules; subscription + invoice events drive renewals/dunning.

---

## 5. DIRECTION B — Engineers & Orgs collect from their customers (Connect)

### B1. Engineers → their customers (Direct Charges, **0% platform fee**)

Invoices an engineer raises settle into **their own** Stripe balance. GymAxis takes no cut (the £30/mo sub already covers it).

**Onboarding (engineer connects their Stripe):**
* Entry point (UI): Engineer App → **Account Settings → Payouts** (`EngineerPayouts.js`).
* `POST /api/svc/engineer/stripe/connect/onboarding` → creates an **Express** account if missing (`country=GB`, `business_type=individual`, capabilities `card_payments`+`transfers`) and returns a single-use hosted **AccountLink** (`type=account_onboarding`, expires ~5 min).
* `GET /api/svc/engineer/stripe/connect/status?refresh=true` → connection + capability flags (`charges_enabled`, `payouts_enabled`, `details_submitted`, `requirements_currently_due`).
* `POST /api/svc/engineer/stripe/connect/login-link` → Express Dashboard login link.
* Stored at `partner_engineers.payout.stripe_account_id` + cached flags in `payout.stripe_connect`.

**Taking a card payment on an invoice:**
* `POST /api/svc/engineer/invoices/{invoice_id}/payment-link` → creates a Checkout `mode=payment` session **on the engineer's connected account** (`stripe_account=acct_…` → Direct Charge). Returns `{url, session_id, shortcode}`.
* Guard rails: returns **412** `engineer_not_connected` (no account) or `onboarding_incomplete` (`charges_enabled=false`) so the UI nudges the engineer to finish onboarding.
* On success the customer lands on `/{PUBLIC_ORIGIN}/i/{shortcode}/paid`; a receipt email is sent via Resend; the invoice flips to `paid`.

### B2. Orgs/gyms → their members (Connect subscriptions, **1% platform fee**)

Membership payments settle into the **gym's** Stripe balance; GymAxis takes a **1% application fee** (floored at 50p).

**Onboarding (org connects its Stripe):**
* Entry point (UI): Master Admin → **Stripe Connect** (`AdminStripeConnect.js`), per org.
* `GET /api/stripe-connect/orgs/{org}/status` → onboarding state + `platform_fee_percent`.
* `POST /api/stripe-connect/orgs/{org}/onboarding-link` → create/reuse **Express** account + hosted AccountLink.
* `POST /api/stripe-connect/orgs/{org}/link-existing` → link an existing **Standard** account by pasting `acct_…`.
* `POST /api/stripe-connect/orgs/{org}/dashboard-link` → Express dashboard login.
* `DELETE /api/stripe-connect/orgs/{org}/disconnect` → clear the connection.
* Stored at `organizations.stripe_account_id` (+ `stripe_account_type`).

**Member pays (public join flow):**
* `POST /api/public/signup/{slug}/checkout` → Checkout `mode=subscription` **on the gym's connected account** with `subscription_data.application_fee_percent = 1%` (recurring plan + optional joining fee). Records a row in `payment_transactions`.
* `GET /api/payments/status/...` style polling on the success redirect; the webhook finalises member creation.
* Other membership billing (autopay, credit packs, class invoices, billing portal) lives under `routes/memberships_payments.py` and `routes/memberships/*`.

---

## 6. Webhooks — complete reference

GymAxis exposes several webhook endpoints. **Two distinctions matter in the Stripe Dashboard:**
* **"Events on your account"** = platform events (Direction A, and platform-side records).
* **"Events on Connected accounts"** = events that happen on a connected account (Direction B — onboarding status + Direct/Connect charges).

| # | Endpoint (prepend your domain, e.g. `https://gymaxisai.com`) | Dashboard mode | Events to select | Signing secret | Purpose |
|---|---|---|---|---|---|
| 1 | `/api/webhook/stripe` | **Your account** | `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed` | `STRIPE_WEBHOOK_SECRET` | Direction A: engineer app-fee + org module subscriptions, trial conversion, renewals/dunning |
| 2 | `/api/webhooks/stripe/connect` | **Connected accounts** | `account.updated`, `account.application.deauthorized` | `STRIPE_CONNECT_WEBHOOK_SECRET` | Engineer Connect onboarding status |
| 3 | `/api/webhooks/stripe/engineer-invoices` | **Connected accounts** | `checkout.session.completed` | `STRIPE_WEBHOOK_SECRET` | Engineer invoice paid (Direct Charge) |
| 4 | `/api/webhooks/stripe-connect` | **Connected accounts** | `account.updated` | `STRIPE_CONNECT_WEBHOOK_SECRET` | Org Connect onboarding status |
| 5 | `/api/webhooks/stripe-checkout` | **Connected accounts** | `checkout.session.completed` | `STRIPE_WEBHOOK_SECRET` | Member signup finalisation (gym connected account) |
| 6 | `/api/memberships/webhook/stripe` | **Connected accounts** | `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted` | `STRIPE_WEBHOOK_SECRET` | Membership billing lifecycle (current/past_due/cancelled) |

Notes:
* All handlers verify the Stripe signature and are **idempotent** at the event-id layer (`utils/stripe_idempotency.mark_event_processed`) — Stripe retries are safe.
* Endpoints 3/5/6 receive Direct/Connect charge events; they route internally by `metadata.tenant` / `metadata` so unrelated events are ignored.
* **Minimum viable set** to go live: create **#1 (your account)**, **#2 + #3 (connected, engineers)**, and **#4 + #5 + #6 (connected, orgs/members)**. You may consolidate multiple connected-account *event types* per endpoint URL, but each URL above is a distinct handler path, so create them as listed.

---

## 7. Dashboard configuration — step by step

1. **Enable Connect** + brand the Express flow (see §2).
2. **Create the platform webhook (#1):** Developers → Webhooks → **Add endpoint** → *Events on your account* → URL `https://gymaxisai.com/api/webhook/stripe` → select the Direction-A events → copy the signing secret into `STRIPE_WEBHOOK_SECRET` (already set; update if you rotate).
3. **Create the engineer Connect webhook (#2):** Add endpoint → **Events on Connected accounts** → URL `…/api/webhooks/stripe/connect` → events `account.updated`, `account.application.deauthorized` → copy secret into `STRIPE_CONNECT_WEBHOOK_SECRET`.
4. **Create the engineer-invoice webhook (#3):** Add endpoint → **Connected accounts** → URL `…/api/webhooks/stripe/engineer-invoices` → event `checkout.session.completed`.
5. **Create the org webhooks (#4, #5, #6):** as per the table, all **Connected accounts** mode.
6. **Set `PUBLIC_ORIGIN`** = `https://gymaxisai.com` in `backend/.env`.
7. **Restart backend:** `sudo supervisorctl restart backend`.
8. **Verify config:** `GET /api/payments/config` should report `stripe_configured: true`.

---

## 8. Testing the whole thing (test mode)

> Connect calls (`Account.create`, `AccountLink`) are **real** Stripe API calls — they are **not** covered by the Emergent Checkout proxy. To rehearse safely, set `STRIPE_API_KEY=sk_test_…` (your own test key) + test-mode price IDs in **preview**, then restart backend.

### Test data
* **Card:** `4242 4242 4242 4242`, any future expiry, any CVC, any postcode.
* **Express identity (GB):** date of birth any, ID number `000000000`, address any UK address.
* **Test bank (GB payout):** sort code `10-88-00`, account `00012345`.

### End-to-end rehearsals
1. **Engineer onboarding:** Engineer App → Payouts → Connect Stripe → complete hosted onboarding with test data → return to app → `status` flips `charges_enabled=true`. (Webhook #2 fires `account.updated`.)
2. **Engineer takes a payment:** raise an invoice → "Take card payment" → pay with `4242…` on the hosted page → invoice flips to **paid**, receipt email sent. (Webhook #3 fires `checkout.session.completed`.)
3. **Org onboarding:** Master Admin → Stripe Connect → Start onboarding → complete → status ready. (Webhook #4.)
4. **Member joins & pays:** public `/m/{slug}/join` → pick a plan → pay `4242…` → subscription created on the gym account with a 1% application fee; member provisioned. (Webhooks #5/#6.)
5. **Engineer app-fee sub:** start trial → fast-forward feedback → Accept → Stripe checkout → pay → partner `converted_paid`. (Webhook #1.)
6. **Org module sub:** `/api/payments/checkout` (bundle/module) → pay → module unlocked. (Webhook #1.)

Use **Developers → Events** + **Webhooks → (endpoint) → recent deliveries** to confirm 2xx responses. Re-send an event to confirm idempotency (no double-processing).

---

## 9. Fees, payouts, refunds & reconciliation

* **GymAxis revenue (Direction A):** lands in the GymAxis balance; pays out per your platform payout schedule.
* **Engineer funds (B1):** land in the engineer's connected balance — GymAxis takes **nothing**. Engineers manage payouts in their Express dashboard (login link in-app).
* **Gym funds (B2):** land in the gym's connected balance; GymAxis's **1%** application fee is swept to the platform balance automatically per transaction.
* **Refunds:** issue Direct/Connect refunds from the **connected account** (or via API with `stripe_account=acct_…`). Platform-subscription refunds are issued from the platform account.
* **Reconciliation:** every Direction-B charge stores the connected `account` id on our record (`stripe_account_id`) + a `payment_transactions` row for member signups, so you can reconcile by account.

---

## 10. Go-live checklist

- [ ] Connect enabled + Express branding done (logo, colour, support URL).
- [ ] `STRIPE_API_KEY` = live key (already set). `PUBLIC_ORIGIN=https://gymaxisai.com` set.
- [ ] All **live-mode** price IDs set in `.env` (not test-mode ids).
- [ ] Webhooks #1–#6 created in **live** mode with correct event sets + modes.
- [ ] `STRIPE_CONNECT_WEBHOOK_SECRET` set to the live Connect endpoint secret.
- [ ] `GET /api/payments/config` → `stripe_configured: true`.
- [ ] One real (small) engineer onboarding + £1 invoice payment verified end-to-end.
- [ ] One real org onboarding + £1 member payment verified (1% fee observed in platform balance).
- [ ] Backend restarted after the final `.env` edit.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `503 stripe_connect_not_enabled` on engineer onboarding | Connect not switched on for the platform account | Enable Connect (§2.2) |
| `412 engineer_not_connected` / `onboarding_incomplete` when taking a card payment | Engineer hasn't connected / finished Express onboarding | Engineer completes Payouts → Connect Stripe; check `status` shows `charges_enabled=true` |
| Onboarding returns user to the **preview** URL | `PUBLIC_ORIGIN` unset → falls back to `REACT_APP_BACKEND_URL` | Set `PUBLIC_ORIGIN=https://gymaxisai.com`, restart backend |
| Webhook deliveries show **400 Invalid signature** | Wrong signing secret for that endpoint, or Connect events sent to a "your account" endpoint | Match the secret + the **Connected accounts** vs **Your account** mode to the table in §6 |
| Invoice not flipping to paid | Webhook #3 missing / wrong mode | Create #3 as **Connected accounts**, event `checkout.session.completed` |
| Member subscription created but no 1% fee | Org linked but `application_fee_percent` not applied (e.g. Standard account quirk) | Confirm the gym's account supports application fees; re-check `subscription_data` on the session |
| "AccountLink expired" | AccountLinks are single-use, ~5-min TTL | Request a fresh link (the UI does this automatically on retry) |

---

## 12. Security & operational notes

* **Never** take payment amounts from the front-end — all amounts are computed server-side (already enforced).
* **Never** commit keys; all secrets live in `backend/.env` only. (Action item: purge `backend/.env.bak` / `.env.live.bak`.)
* All webhook handlers verify signatures and de-duplicate by Stripe event id.
* Keep a **separate test key in preview** and the live key only in production to avoid running real onboarding/charges while testing.
* Rotate `STRIPE_WEBHOOK_SECRET` / `STRIPE_CONNECT_WEBHOOK_SECRET` if a leak is suspected; update `.env` and restart backend.

---

### Appendix — endpoint quick reference

**Engineer Connect:** `POST /api/svc/engineer/stripe/connect/onboarding` · `GET …/status` · `POST …/login-link` · `POST …/refresh`
**Engineer invoices:** `POST /api/svc/engineer/invoices/{id}/payment-link` · public receipt `GET /api/svc/engineer/public/invoice/{shortcode}/receipt`
**Org Connect:** `GET/POST /api/stripe-connect/orgs/{org}/status|onboarding-link|link-existing|dashboard-link` · `DELETE …/disconnect`
**Member signup:** `POST /api/public/signup/{slug}/checkout`
**Engineer app-fee sub:** `POST /api/partners/me/subscription/checkout|cancel|resume`
**Org platform sub:** `GET /api/payments/pricing|config` · `POST /api/payments/checkout|checkout/flex` · `GET /api/payments/status/{id}`
**Webhooks:** see §6.
