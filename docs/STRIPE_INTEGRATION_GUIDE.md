# GymAxis · Complete Stripe Setup Guide (from absolute zero)

**Who this is for:** anyone — no Stripe or coding knowledge assumed.
**What it does:** takes you from "I have nothing" to "engineers, gyms, and GymAxis are all taking payments", one click at a time.
**Rule of thumb:** do **everything in Test mode first** (Part 8). Only switch to Live once a test run works (Part 9).
**Last reviewed:** June 2026 · matches the current GymAxis code.

> 💡 The payment **code is already built into GymAxis.** You are not coding anything. You are (1) creating a Stripe account, (2) copying a few keys/IDs into one settings file, and (3) clicking some buttons in the Stripe website. That's the whole job.

---

## How to use this guide
- Work **top to bottom**. Don't skip.
- Every box like `STRIPE_API_KEY` is a setting name — you'll copy/paste values into it in Part 3.
- ✅ Tick each checkbox as you go.
- If a Stripe menu name looks slightly different from what's written here, look for the closest match — Stripe occasionally renames menus, but the location is the same.

---

## PART 0 — Understand what you're switching on (5-minute read)

### 0.1 The two money directions, in plain English
GymAxis handles money going **two different ways**:

**Direction A — money coming TO GymAxis (your income):**
- Engineers pay GymAxis **£30/month** (or £15 on a discount tier) to use the app.
- Gyms/organisations pay GymAxis monthly for modules (Operations, Memberships, CRM, Marketing).

**Direction B — money your users collect FROM their own customers:**
- An **engineer** sends an invoice to *their* customer; the customer pays by card; the money goes into **the engineer's** bank (GymAxis takes **0%**).
- A **gym** sells a membership to a member; the member pays; the money goes into **the gym's** bank, and GymAxis automatically keeps a **1%** fee.

Stripe handles both. Direction B uses a Stripe feature called **Connect**, which lets each engineer/gym have their own mini Stripe account "underneath" yours.

### 0.2 Plain-English glossary (keep this handy)
| Term | What it means |
|---|---|
| **Platform account** | *Your* main Stripe account (GymAxis). Everything sits under it. |
| **Connected account** | A sub-account for one engineer or one gym, created when they "Connect Stripe". Has an id like `acct_1A2b...`. |
| **Express** | The easy type of connected account — Stripe hosts the sign-up form; the engineer/gym just fills in details. We use this. |
| **Standard** | A connected account where the gym already has their own full Stripe account and links it. Optional. |
| **Direct Charge** | A payment taken straight on a connected account (engineer invoices use this; GymAxis takes nothing). |
| **Application fee** | The slice GymAxis keeps from a connected-account payment (gyms = 1%). |
| **API key** | A password GymAxis uses to talk to Stripe. Two kinds: **Publishable** (public, `pk_...`) and **Secret** (private, `sk_...`). |
| **Test mode vs Live mode** | Stripe has a practice world (Test) and the real world (Live). Each has its **own** keys, products and webhooks. There's a toggle at the top of the Stripe Dashboard. |
| **Product / Price** | In Stripe you create a "Product" (e.g. "Operations module") and a "Price" (e.g. £29/month). The Price has an id like `price_1A2b...` that GymAxis needs. |
| **Webhook** | A way for Stripe to ping GymAxis the instant something happens ("this invoice was paid"), so GymAxis updates itself automatically. |
| **Signing secret** | A password (`whsec_...`) that proves a webhook ping really came from Stripe. |

### 0.3 Test mode first — always
At the **top of the Stripe Dashboard** there is a **Test mode** toggle (often an orange switch).
- **ON (Test mode)** = practice. Fake cards, no real money. **Start here.**
- **OFF (Live mode)** = real money.
Everything you set up in Test mode (keys, products, webhooks) must be **re-done in Live mode** later (Part 9). That's normal.

### 0.4 "I think I need to start again" — read this
Good news: **starting again is safe.** You are mostly re-copying values into one settings file and re-clicking Dashboard buttons. To start clean:
1. Decide Test vs Live (start Test).
2. Work through Parts 1–8 in order.
3. If old/half-finished connected accounts exist from a previous attempt, you can ignore them — they don't block new ones. (Don't delete live gym/engineer accounts that already took real money without checking with them.)
4. The only thing you can truly "break" is pasting a wrong key/secret into the settings file — and that's instantly fixable by pasting the right one and restarting (Part 3).

> ✅ Tick when you understand the two directions and that you'll start in **Test mode**: ☐

---

## PART 1 — Create and activate your Stripe account

> Skip Step 1.1/1.2 if you already have a Stripe account and just sign in.

1.1 ☐ Go to **https://stripe.com** → **Sign up**. Enter email, name, password.
1.2 ☐ Confirm your email (click the link Stripe sends).
1.3 ☐ Sign in to the **Dashboard** (https://dashboard.stripe.com).
1.4 ☐ **Activate the account** (needed for Live mode; Test mode works immediately): Dashboard → click **Activate** / **Complete your profile** and fill in:
   - Business type & details (sole trader / limited company etc.)
   - Your business address
   - **Bank account** where GymAxis's own income (Direction A) will be paid out.
1.5 ☐ Set your **public business name / statement descriptor** (what shows on customers' card statements): Settings → **Business → Public details**.

> You can do everything that follows in **Test mode** before activation is fully approved.

---

## PART 2 — Get your API keys (Test mode)

2.1 ☐ Make sure the **Test mode** toggle (top of the Dashboard) is **ON**.
2.2 ☐ Go to **Developers → API keys** (left sidebar; or the "Developers" link top-right → API keys).
2.3 ☐ You'll see two keys:
   - **Publishable key** — starts `pk_test_...` → click to copy. This is `STRIPE_PUBLISHABLE_KEY`.
   - **Secret key** — starts `sk_test_...` → click **Reveal**, then copy. This is `STRIPE_API_KEY`.
2.4 ☐ Paste both somewhere safe for a moment (you'll put them in GymAxis in Part 3).

> 🔒 The **secret key is a master password.** Never email it, never put it in a screenshot, never commit it to code. Treat it like your bank PIN.

---

## PART 3 — Put the keys into GymAxis (the settings file)

GymAxis reads all its secrets from one file: **`/app/backend/.env`**.

3.1 ☐ Open `/app/backend/.env` (ask your developer/agent to open it, or use the file editor — **do not** use copy-paste-in-terminal tricks, they can corrupt the file).
3.2 ☐ Find or add these lines (one per line, no spaces around `=`, no quotes):
```
STRIPE_API_KEY=sk_test_your_secret_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_publishable_key_here
PUBLIC_ORIGIN=https://gymaxisai.com
```
   - `PUBLIC_ORIGIN` is your app's web address. It tells Stripe where to send people back after they pay. For testing on preview you can use your preview URL; for production use `https://gymaxisai.com`.
3.3 ☐ Save the file.
3.4 ☐ Restart the backend so it reads the new values. Command (your developer/agent runs this):
```
sudo supervisorctl restart backend
```
3.5 ☐ Verify: open `https://YOUR-APP/api/payments/config` in a browser (or ask your dev). You want to see `"stripe_configured": true`.

> ℹ️ Other Stripe secrets (`STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_WEBHOOK_SECRET`, price IDs) go in this same file. You'll add them in Parts 5 and 6.

> ✅ Keys are in and `stripe_configured: true`: ☐

---

## PART 4 — Turn on Stripe Connect (so engineers & gyms can connect)

This is the switch that makes Direction B possible.

4.1 ☐ In the Dashboard (Test mode ON), go to **Connect**. If you've never used it: click **Get started** / **Enable Connect**.
4.2 ☐ When asked what you're building, choose **Platform or marketplace**.
4.3 ☐ Fill in the **platform profile**: business name, support email, your website (`https://gymaxisai.com`), and a short description (e.g. "Field service & membership software for gyms").
4.4 ☐ **Brand the sign-up screen** engineers/gyms will see: Connect → **Settings** → **Branding** (sometimes under "Express"): upload the **GymAxis logo**, set a brand colour, and the support URL.
4.5 ☐ (Optional, only if some gyms want to link an *existing* full Stripe account by login): note your **Connect client id** under Connect → **Settings → Integration/OAuth**, and set `STRIPE_CONNECT_CLIENT_ID` + `STRIPE_CONNECT_REDIRECT_URI` in `.env`. Most setups can skip this and use Express only.

> If you skip Connect, engineers/gyms get an error like "Stripe Connect not enabled" when they try to connect. So don't skip it.

> ✅ Connect enabled + branded: ☐

---

## PART 5 — Create your Products & Prices (Direction A — GymAxis's plans)

These are the plans engineers/gyms pay **GymAxis** for. For each one you create a Product + monthly Price in Stripe, copy the **Price id** (`price_...`), and paste it into the matching setting in `.env`.

### 5.1 How to create one Price (do this for each row below)
a. ☐ Dashboard (Test mode ON) → **Product catalogue** → **Add product** (sometimes "Products → + Add product").
b. ☐ Name it (e.g. "GymAxis Operations module").
c. ☐ Under **Pricing**: choose **Recurring**, **Monthly**, enter the amount (e.g. £29.00), currency **GBP**.
d. ☐ **Save**.
e. ☐ Open the product, find the **Price** you just made, and copy its **API ID** — it looks like `price_1A2bC3...`.
f. ☐ Paste it into the matching setting in `.env` (table below).
g. ☐ (Optional) add a second **yearly** price for the `_ANNUAL` settings.

### 5.2 Which Price goes in which setting
| GymAxis plan | Suggested price | `.env` setting |
|---|---|---|
| Engineer app fee (standard) | £30 / mo | `STRIPE_PRICE_PARTNER_PLAN_30` |
| Engineer app fee (discount tier) | £15 / mo | `STRIPE_PRICE_PARTNER_PLAN_15` |
| GymAxis Pro (all modules bundle) | your price | `STRIPE_PRICE_GYMAXIS_PRO` (+ `_ANNUAL`) |
| Operations module | £29 / mo | `STRIPE_PRICE_OPERATIONS` (+ `_ANNUAL`) |
| Memberships module | £49 / mo | `STRIPE_PRICE_MEMBERSHIPS` (+ `_ANNUAL`) |
| CRM module | £49 / mo | `STRIPE_PRICE_CRM` (+ `_ANNUAL`), `STRIPE_PRICE_CRM_BUSINESS` |
| Marketing module | £59 / mo | `STRIPE_PRICE_MARKETING` (+ `_ANNUAL`) |
| Extra-site add-on | your price | `STRIPE_PRICE_SITE_ADDON` (+ `_ANNUAL`) |

5.3 ☐ After pasting all the price IDs, **save `.env`** and **restart backend** (`sudo supervisorctl restart backend`).

> ⚠️ **Test vs Live prices are different objects.** The `price_...` ids you copy in Test mode will NOT work in Live mode. In Part 9 you'll create them again in Live mode and swap the values.
> ⚠️ If you only care about Direction B (engineers/gyms taking customer payments) right now, you can set just the engineer app-fee prices and come back to the rest later.

---

## PART 6 — Create your Webhooks (so GymAxis updates itself automatically)

A webhook is Stripe phoning GymAxis when something happens. GymAxis needs **six** of them. Each has: a **URL**, a **mode** (very important: "Your account" vs "Connected accounts"), a list of **events**, and a **signing secret** you copy back into `.env`.

> The single most common mistake: choosing the wrong **mode**. Use the table's "Mode" column exactly.

### 6.1 How to create one webhook (repeat for all six)
a. ☐ Dashboard (Test mode ON) → **Developers → Webhooks** → **Add endpoint** (or "+ Add destination").
b. ☐ **Endpoint URL:** type your domain + the path from the table, e.g. `https://gymaxisai.com/api/webhook/stripe`.
c. ☐ **Mode / "Listen to":** choose **Events on your account** OR **Events on Connected accounts** exactly as the table says.
d. ☐ **Select events:** click "Select events" and tick the exact events listed.
e. ☐ **Add endpoint** to save.
f. ☐ Open the new endpoint → find **Signing secret** → **Reveal** → copy the `whsec_...` value.
g. ☐ Paste it into the `.env` setting named in the table's last column.

### 6.2 The six webhooks
| # | Endpoint URL (use your domain) | Mode (pick exactly) | Tick these events | Paste secret into |
|---|---|---|---|---|
| 1 | `…/api/webhook/stripe` | **Events on your account** | `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed` | `STRIPE_WEBHOOK_SECRET` |
| 2 | `…/api/webhooks/stripe/connect` | **Events on Connected accounts** | `account.updated`, `account.application.deauthorized` | `STRIPE_CONNECT_WEBHOOK_SECRET` |
| 3 | `…/api/webhooks/stripe/engineer-invoices` | **Events on Connected accounts** | `checkout.session.completed` | `STRIPE_WEBHOOK_SECRET` |
| 4 | `…/api/webhooks/stripe-connect` | **Events on Connected accounts** | `account.updated` | `STRIPE_CONNECT_WEBHOOK_SECRET` |
| 5 | `…/api/webhooks/stripe-checkout` | **Events on Connected accounts** | `checkout.session.completed` | `STRIPE_WEBHOOK_SECRET` |
| 6 | `…/api/memberships/webhook/stripe` | **Events on Connected accounts** | `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted` | `STRIPE_WEBHOOK_SECRET` |

What each one is for (plain English):
- **#1** GymAxis's own income — engineer subs + gym module subs, trial conversions, renewals.
- **#2** tells GymAxis when an **engineer** finishes connecting Stripe (or disconnects).
- **#3** tells GymAxis when an **engineer's invoice** was paid.
- **#4** tells GymAxis when a **gym** finishes connecting Stripe.
- **#5** finishes a **member's** sign-up after they pay.
- **#6** keeps **membership** billing status correct (paid / overdue / cancelled).

6.3 ☐ Note: webhook **#1, #3, #5, #6** all use `STRIPE_WEBHOOK_SECRET`. If those secrets differ per endpoint in your Dashboard, that's fine — Stripe sometimes shows the *same* account-level secret. If GymAxis later logs "Invalid signature", it means the secret in `.env` doesn't match that endpoint; re-copy it.
6.4 ☐ After pasting all secrets, **save `.env`** and **restart backend**.

> ✅ All six webhooks created with the **correct mode** + secrets in `.env`: ☐

---

## PART 7 — Final settings check

7.1 ☐ Open `/app/backend/.env` and confirm these exist with real values:
```
STRIPE_API_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CONNECT_WEBHOOK_SECRET=whsec_...   ← from webhook #2 / #4
PUBLIC_ORIGIN=https://gymaxisai.com
STRIPE_PRICE_PARTNER_PLAN_30=price_...
(...other price IDs you created...)
```
7.2 ☐ Save → `sudo supervisorctl restart backend`.
7.3 ☐ Visit `…/api/payments/config` → expect `"stripe_configured": true`.

---

## PART 8 — Test everything (Test mode) before going live

You'll now pretend to be each kind of user. Use Stripe's fake details:
- **Test card:** `4242 4242 4242 4242`, any future expiry (e.g. 12/34), any 3-digit CVC, any postcode.
- **Test bank (UK payout):** sort code `10-88-00`, account `00012345`.
- **Express identity:** any name/address, ID number `000000000`, any date of birth.

Run these in order. After each, check **Developers → Events** (and the webhook's **Recent deliveries**) shows a green/2xx response.

8.1 ☐ **Engineer connects Stripe:** sign in as a test engineer → Engineer App → menu → **Account Settings → Payouts** → **Connect Stripe** → complete the hosted form with test details → you're returned to GymAxis → status shows **"ready / charges enabled"**. *(Fires webhook #2.)*
8.2 ☐ **Engineer takes a customer card payment:** create an invoice → **Take card payment** / payment link → pay with `4242…` → invoice flips to **Paid**, a receipt email is sent. *(Fires webhook #3.)*
8.3 ☐ **Gym connects Stripe:** Master Admin → **Stripe Connect** → pick an org → **Start onboarding** → complete → status **ready**. *(Fires webhook #4.)*
8.4 ☐ **Member joins & pays a gym:** open the public join page `…/m/{gym-slug}/join` → pick a plan → pay with `4242…` → member is created; in your platform balance you should see a **1% application fee**. *(Fires webhooks #5/#6.)*
8.5 ☐ **Engineer pays GymAxis (app fee):** start a trial for the engineer → accept → Stripe checkout → pay `4242…` → engineer shows **subscribed**. *(Fires webhook #1.)*
8.6 ☐ **Gym pays GymAxis (module):** as a gym admin, buy a module → pay `4242…` → module unlocks. *(Fires webhook #1.)*

If any step fails, jump to Part 11 (Troubleshooting). **Do not go live until 8.1–8.4 pass at minimum.**

> ✅ Test runs pass: ☐

---

## PART 9 — Go live (switch to real money)

Live mode is a **separate world** — you repeat the key parts with the toggle OFF.

9.1 ☐ Make sure your account is **fully activated** (Part 1.4 approved).
9.2 ☐ Turn the **Test mode toggle OFF** (you're now in **Live**).
9.3 ☐ **Get live keys:** Developers → API keys → copy `pk_live_...` and `sk_live_...`. Put them in `.env`:
```
STRIPE_API_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
```
9.4 ☐ **Enable Connect in Live** (if it asks again) + re-check branding.
9.5 ☐ **Re-create Products/Prices in Live** (Part 5) and paste the new **live** `price_...` ids into `.env`.
9.6 ☐ **Re-create all six Webhooks in Live** (Part 6) and paste the new **live** signing secrets into `.env` (`STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_WEBHOOK_SECRET`).
9.7 ☐ Set `PUBLIC_ORIGIN=https://gymaxisai.com`.
9.8 ☐ Save `.env` → `sudo supervisorctl restart backend` → check `…/api/payments/config` → `stripe_configured: true`.
9.9 ☐ Do **one tiny real test**: a £1 engineer invoice paid with a real card, and a £1 membership, then refund them. Confirm money moved and the 1% fee appeared.

> 🔁 Anything created in Test mode (keys, prices, webhooks) does **not** carry over to Live. Re-doing them in Live is expected.

> ✅ Live keys, prices, webhooks all set + one real test done: ☐

---

## PART 10 — What each address means (reference)

You don't type these by hand (GymAxis does), but here's what your users click:

| Who | Where in the app | What happens |
|---|---|---|
| Engineer | Engineer App → menu → **Account Settings → Payouts → Connect Stripe** | Creates their Express account, opens Stripe's hosted form |
| Engineer | An invoice → **Take card payment** | Customer pays; money to the engineer (0% fee) |
| Gym admin (you) | Master Admin → **Stripe Connect** | Onboard a gym's Express account (or link existing) |
| Member | Public **`/m/{gym}/join`** | Buys a membership; money to the gym (GymAxis keeps 1%) |
| Engineer | Trial → feedback → **Accept** | Starts their £30/mo GymAxis subscription |
| Gym admin | In-app **upgrade / buy module** | Starts a GymAxis module subscription |

---

## PART 11 — Troubleshooting (symptom → cause → fix)

| You see… | It means… | Do this |
|---|---|---|
| "Stripe Connect not enabled" / `503 stripe_connect_not_enabled` | You didn't switch on Connect | Part 4 — enable Connect |
| Engineer can't take card payment; "connect your Stripe" / `412 engineer_not_connected` | Engineer hasn't connected yet | Engineer does Part 8.1; status must show "charges enabled" |
| "Finish onboarding" / `412 onboarding_incomplete` | Engineer started but didn't finish the Stripe form | Engineer reopens Connect and completes all required fields |
| After paying, the user lands on the **wrong/preview** site | `PUBLIC_ORIGIN` not set | Set `PUBLIC_ORIGIN=https://gymaxisai.com`, restart backend |
| Webhook shows red / "Invalid signature" (400) | Wrong signing secret, or wrong **mode** for that webhook | Re-copy the endpoint's signing secret into the right `.env` setting; confirm "Connected accounts" vs "Your account" matches Part 6 |
| Invoice paid but GymAxis still says unpaid | Webhook #3 missing or wrong mode | Create #3 as **Connected accounts**, event `checkout.session.completed` |
| Member paid but no 1% fee in your balance | Fee not applied (often a Standard-account quirk) | Use Express onboarding; confirm the gym account allows application fees |
| "Link expired" on the Stripe form | Onboarding links are single-use, ~5 min | Click Connect again to get a fresh link (the app does this automatically) |
| `stripe_configured: false` | Keys missing/typo in `.env`, or backend not restarted | Re-check Part 3; restart backend |
| Prices/checkout fail after going live | Still using **test** price IDs | Re-create prices in **Live** and swap the ids (Part 9.5) |

---

## PART 12 — Safety rules (don't skip)
1. ☐ Never share or screenshot a **secret key** (`sk_...`) or **signing secret** (`whsec_...`).
2. ☐ Keep all secrets only in `/app/backend/.env` — never in code, chat, or email.
3. ☐ Use **test keys in preview** and **live keys only in production**, so testing never moves real money.
4. ☐ Delete leftover backup files that may contain old secrets (`backend/.env.bak`, `backend/.env.live.bak`).
5. ☐ If you ever think a secret leaked: in Stripe → Developers → API keys / Webhooks → **roll/regenerate**, paste the new value into `.env`, restart backend.

---

## Appendix A — Master list of `.env` settings
```
# Core
STRIPE_API_KEY=                 # secret key  (sk_test_... then sk_live_...)
STRIPE_PUBLISHABLE_KEY=         # public key  (pk_test_... then pk_live_...)
PUBLIC_ORIGIN=https://gymaxisai.com
# Webhook signing secrets
STRIPE_WEBHOOK_SECRET=          # from webhooks #1/#3/#5/#6
STRIPE_CONNECT_WEBHOOK_SECRET=  # from webhooks #2/#4
# (optional) link existing gym Stripe accounts via login
STRIPE_CONNECT_CLIENT_ID=
STRIPE_CONNECT_REDIRECT_URI=
# Direction-A plan prices (price_...)
STRIPE_PRICE_PARTNER_PLAN_30=
STRIPE_PRICE_PARTNER_PLAN_15=
STRIPE_PRICE_GYMAXIS_PRO=
STRIPE_PRICE_GYMAXIS_PRO_ANNUAL=
STRIPE_PRICE_OPERATIONS=
STRIPE_PRICE_OPERATIONS_ANNUAL=
STRIPE_PRICE_MEMBERSHIPS=
STRIPE_PRICE_MEMBERSHIPS_ANNUAL=
STRIPE_PRICE_CRM=
STRIPE_PRICE_CRM_ANNUAL=
STRIPE_PRICE_CRM_BUSINESS=
STRIPE_PRICE_MARKETING=
STRIPE_PRICE_MARKETING_ANNUAL=
STRIPE_PRICE_SITE_ADDON=
STRIPE_PRICE_SITE_ADDON_ANNUAL=
```

## Appendix B — Webhook master table (copy when creating them)
| # | Path | Mode | Events |
|---|---|---|---|
| 1 | `/api/webhook/stripe` | Your account | checkout.session.completed, customer.subscription.updated, customer.subscription.deleted, invoice.paid, invoice.payment_failed |
| 2 | `/api/webhooks/stripe/connect` | Connected accounts | account.updated, account.application.deauthorized |
| 3 | `/api/webhooks/stripe/engineer-invoices` | Connected accounts | checkout.session.completed |
| 4 | `/api/webhooks/stripe-connect` | Connected accounts | account.updated |
| 5 | `/api/webhooks/stripe-checkout` | Connected accounts | checkout.session.completed |
| 6 | `/api/memberships/webhook/stripe` | Connected accounts | checkout.session.completed, invoice.paid, invoice.payment_failed, customer.subscription.deleted |

## Appendix C — Developer endpoint reference (for your engineer, not the Dashboard)
- Engineer Connect: `POST /api/svc/engineer/stripe/connect/onboarding` · `GET …/status` · `POST …/login-link` · `POST …/refresh`
- Engineer invoice payment: `POST /api/svc/engineer/invoices/{id}/payment-link`
- Org Connect: `GET/POST /api/stripe-connect/orgs/{org}/status|onboarding-link|link-existing|dashboard-link` · `DELETE …/disconnect`
- Member signup checkout: `POST /api/public/signup/{slug}/checkout`
- Engineer app-fee subscription: `POST /api/partners/me/subscription/checkout|cancel|resume`
- Org module/bundle subscription: `GET /api/payments/pricing|config` · `POST /api/payments/checkout|checkout/flex` · `GET /api/payments/status/{id}`

---

### One-page "did I finish?" checklist
- ☐ Stripe account created & (for live) activated with a bank account
- ☐ Test keys in `.env`, `stripe_configured: true`
- ☐ Connect enabled + branded
- ☐ Products/Prices created, price IDs in `.env`
- ☐ All 6 webhooks created with the correct **mode**, secrets in `.env`
- ☐ Test-mode runs 8.1–8.6 pass
- ☐ Repeated keys/prices/webhooks in **Live**, one real £1 test passed
- ☐ Backups with secrets deleted; secrets only in `.env`
