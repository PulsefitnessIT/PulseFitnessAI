> **📋 Status — Iter 220m (May 26, 2026)** — Partner Engineer Instagram campaign assets generated
>
> The PRD below remains the canonical Marketing roadmap. Recent additions
> stacked on top of the original April 2026 baseline:
>
> ## Partner Engineer Instagram launch campaign (iter 220m)
>
> Full 4-week social campaign for the Partner Engineer soft launch:
>
> * **32 pixel-perfect assets** rendered into `/app/backend/marketing/instagram/`
>   via Playwright (HTML templates → 1080×1080 PNGs at device-scale 2x).
>   – 19 feed posts across 4 weeks (carousels + single tiles + reel covers)
>   – 8 story frames (with poll / slider / link sticker / countdown placement notes)
>   – 5 highlight covers (Apply · Demo · Engineers · Reviews · FAQ)
> * **Brand-locked** — every colour pulled from the same CSS vars the live
>   product uses (`#0055FF` brand blue, `#19CDFF` cyan accent, `#0A0C10`
>   ink). Headlines in Outfit 800/900 (Satoshi-style), body in Inter,
>   stats in JetBrains Mono. Google Fonts loaded at render time so
>   typography is crisp at any zoom.
> * **Regeneratable** — `python3 backend/marketing/generate.py` rebuilds
>   every asset from the HTML templates in ~30s. Editors can change a
>   price, a hashtag, a stat globally in one find/replace.
> * **Ready-to-publish copy** — `/app/backend/marketing/CAPTIONS.md`
>   holds the full 4-week posting schedule with caption + hashtags +
>   suggested UK time slots for every asset.
> * **KPI targets**: 50 verified Partner Engineer applications in 4
>   weeks · ≥45% story completion · ≥12s avg reel watch time.
>
> Operator workflow: hand the `/instagram/` folder + `CAPTIONS.md` to
> the social-media manager. They paste the captions, attach UTM
> `?utm_source=instagram&utm_medium=social&utm_campaign=partner_launch_2026`
> to the bio link, and post on the recommended cadence.
>
> ## Module-intent capture at trial signup (iter 216h227)
> Marketing module landing pages (`/modules/marketing`) now dispatch
> `openTrial('marketing')` so the new operator's primary_module is
> set to `marketing` at signup. The `/activation/me` funnel then
> narrows to JUST marketing-relevant first wins:
>
> 1. `first_brand_discovered` — fires when the brand-discovery flow
>    is applied (`POST /api/marketing/brand-discovery/apply`).
> 2. `first_audience_built` — fires on the first
>    `POST /api/marketing/audiences`.
> 3. `first_campaign_launched` — fires on the first
>    `POST /api/marketing/campaigns/{id}/send` **only when sent>0**
>    (zero-send drafts do NOT count).
>
> All three are wired into the existing route handlers as best-effort
> emit hooks (`try/except`) so a failed activation write never blocks
> the marketing operation.
>
> **Creative Studio mobile fix (iter 216h229)**
> Brand library + category library grids switched from fixed
> `grid-cols-3` to `grid-cols-2 sm:grid-cols-3` so thumbnails get
> full width below the sm breakpoint instead of squashing to ~120px.

---


# GymAxis Marketing Suite — Architecture & PRD

> **Status**: Active — Phase 1 in development (Apr 2026)
> **Owner**: Product
> **Depends on**: GymAxis CRM · Memberships · Stripe Connect · Resend · Gemini Nano Banana · Meta Graph API

A data-driven, AI-powered customer engagement engine for gyms — designed to
**rival Braze** but optimised for fitness operators. Every campaign is
personalised, automated, behaviour-driven, and continuously optimised.

---

## 1. Vision

Marketing in fitness is reactive: someone churns, then you email them. We
build the opposite — **proactive, autonomous growth**:

- **Predict** churn 14 days early, fire a reactivation journey before they cancel.
- **Surface** under-capacity Monday-evening classes and propose a promo.
- **Auto-segment** every member by attendance pattern, spend, class
  preference, churn risk — refreshed in real time.
- **AI-generate** the poster, the email, the social caption, the SMS — from a
  one-line brief.
- **Cross-channel** orchestration — email → no open in 24 h → SMS fallback →
  in-app banner on next login.
- **Attribute** every booking, payment, retention event back to the campaign
  that drove it.

---

## 2. Module Architecture

```
                    ┌──────────────────────────────┐
                    │   Marketing Suite Frontend   │
                    │  /marketing  (gym-facing)    │
                    │  /master-admin/marketing     │
                    │     (platform config + KPI)  │
                    └──────────────┬───────────────┘
                                   │
       ┌───────────────┬───────────┴─────────────┬─────────────────┐
       ▼               ▼                         ▼                 ▼
┌───────────────┐ ┌──────────────┐ ┌─────────────────┐ ┌──────────────────┐
│ Segmentation  │ │   Campaign   │ │ Journey Builder │ │ Creative Studio  │
│   Engine      │ │   Builder    │ │   (canvas)      │ │  (AI images)     │
└──────┬────────┘ └──────┬───────┘ └────────┬────────┘ └─────────┬────────┘
       │                 │                  │                    │
       └────────┬────────┴────────┬─────────┴──────────┬─────────┘
                ▼                 ▼                    ▼
       ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
       │ CRM / Members   │ │  Omnichannel     │ │  Insights & AI   │
       │ Integration     │ │  Messenger       │ │  Optimisation    │
       │ (read+write)    │ │  (email/SMS/IM)  │ │                  │
       └─────────────────┘ └──────────────────┘ └──────────────────┘
                ▼                 ▼                    ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  marketing_events  ←  central event bus (Mongo capped col)  │
       └─────────────────────────────────────────────────────────────┘
                ▼
       ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
       │  Stripe Plans   │ │   Reporting +    │ │  Master Admin    │
       │  (gating)       │ │   Attribution    │ │  Analytics       │
       └─────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## 3. Data Model (MongoDB)

### `marketing_audiences`
Saved audience segments with rules. Support both **dynamic** (re-evaluated on
read) and **snapshot** (frozen contact list) modes.

```js
{
  id: uuid, organization_id: uuid, created_by: uuid,
  name: "High spenders – Tottenham",
  type: "dynamic" | "snapshot",
  rules: {                       // mongo-style rule tree
    op: "and",
    conditions: [
      {field: "lifetime_value_gbp", op: ">=", value: 500},
      {field: "site_id", op: "==", value: "tottenham-..."},
      {field: "last_attended_at", op: "<=", value: "30d_ago"}
    ]
  },
  estimated_size: 412,
  computed_at: iso,
  tags: ["retention", "high-value"]
}
```

**Available rule fields** (resolved in `audiences.compute()`):
- `lifetime_value_gbp` · `last_attended_at` · `attendance_30d` · `attendance_90d`
- `class_preference` (`spin` / `hiit` / `pt`) · `churn_risk_score` (0-100)
- `subscription_tier` · `payment_status` (`active` / `failed` / `cancelled`)
- `last_booking_at` · `signup_at` · `tags` (CRM) · `site_id`
- `pt_sessions_used_30d` · `inactive_days` · `referral_count`

### `marketing_campaigns`
```js
{
  id: uuid, organization_id: uuid, created_by: uuid,
  name: "Spin Saturday — capacity push",
  status: "draft" | "scheduled" | "sending" | "sent" | "paused",
  channel: "email" | "sms" | "in_app" | "social",
  audience_id: uuid,             // OR inline audience
  audience_inline: {...},
  content: {
    subject: "...",
    preheader: "...",
    body_html: "...",            // assembled from blocks
    blocks: [{type: "hero"|"text"|"cta"|"image", ...}],
    creative_asset_ids: [uuid],
    cta_url: "https://...",
  },
  schedule: {
    send_at: iso | null,         // null = send now
    timezone: "Europe/London",
    quiet_hours: {start: "21:00", end: "08:00"},
  },
  tracking: {
    utm_source: "gymaxis_marketing", utm_campaign: "spin-sat",
  },
  ai_assist: {
    suggested_send_time: iso,
    suggested_subject_lines: [...],
    confidence: 0.84,
  },
  metrics: {
    sent: 0, delivered: 0, opened: 0, clicked: 0, bounced: 0,
    converted: 0, revenue_gbp: 0,
  },
  created_at: iso, updated_at: iso, sent_at: iso | null,
}
```

### `marketing_messages`
One row per recipient — used for engagement tracking (open / click / convert).
```js
{
  id: uuid, campaign_id: uuid, organization_id: uuid,
  contact_id: uuid, contact_email: "...", contact_phone: "...",
  channel: "email" | "sms" | "in_app",
  resend_message_id: "...",      // when channel=email
  status: "queued" | "sent" | "delivered" | "opened" | "clicked" | "bounced",
  events: [{type, at}],          // open/click trail
  attribution: {                  // bookings/revenue tied to this message
    bookings: [], revenue_gbp: 0,
  },
  sent_at: iso, opened_at: iso, clicked_at: iso,
}
```

### `marketing_journeys`
Visual canvas: nodes + edges. Triggers fire from event bus.
```js
{
  id: uuid, organization_id: uuid, name: "New Member Welcome",
  status: "active" | "paused" | "draft",
  trigger: {
    event: "member_signed_up" | "missed_class" | "failed_payment" | "...",
    filter: {...},               // sub-rules on the event payload
  },
  nodes: [
    {id: "n1", type: "wait", duration_h: 24},
    {id: "n2", type: "send_email", template_id: uuid},
    {id: "n3", type: "branch", condition: "opened", true_next: "n4", false_next: "n5"},
    {id: "n4", type: "send_sms", template_id: uuid},
    {id: "n5", type: "create_offer", offer_type: "percent", value: 20, expires_h: 72},
    {id: "n6", type: "notify_staff", role: "manager", message: "..."},
  ],
  edges: [{from: "trigger", to: "n1"}, {from: "n1", to: "n2"}, ...],
  ai_optimisation: {
    auto_subject_test: true, auto_send_time: true,
  },
  metrics: {entered: 412, completed: 87, converted: 23, revenue_gbp: 5_400},
}
```

### `marketing_creative_assets`
Outputs of the AI Creative Studio.
```js
{
  id: uuid, organization_id: uuid, created_by: uuid,
  type: "poster" | "email_hero" | "social_post" | "logo" | "background",
  prompt: "high-energy spin class promo for saturday morning",
  brand_kit_applied: true,
  source: "gemini_nano_banana" | "user_upload",
  variants: [{url, width, height, model: "gemini-2.5-flash-image", thumb_url}],
  used_by_campaign_ids: [], used_by_post_ids: [],
  created_at: iso,
}
```

### `marketing_brand_kit` (one per org)
```js
{
  organization_id: uuid,
  logo_url: "...", logo_dark_url: "...",
  primary_color: "#0055FF", secondary_color: "#66CCFF", accent_color: "...",
  font_family: "Inter", font_url: "...",
  voice_tone: "energetic"|"premium"|"friendly"|"professional",
  brand_phrases: ["Train · Recover · Win"],
  email_footer_html: "...",
}
```

### `marketing_social_accounts`
OAuth-linked Meta Pages / Instagram Business accounts per org.
```js
{
  id: uuid, organization_id: uuid,
  network: "facebook_page" | "instagram_business",
  meta_page_id: "...",
  meta_user_id: "...",
  ig_business_id: "...",
  access_token_enc: "...",         // encrypted
  token_expires_at: iso,
  page_name: "Pulse Fitness Tottenham",
  status: "active" | "expired" | "revoked",
  connected_by: uuid, connected_at: iso,
}
```

### `marketing_social_posts`
```js
{
  id: uuid, organization_id: uuid, account_id: uuid,
  network: "facebook_page" | "instagram_business",
  caption: "...", media_urls: [...], hashtags: [...],
  scheduled_at: iso, posted_at: iso | null,
  status: "draft" | "scheduled" | "posted" | "failed",
  meta_post_id: "...",
  metrics: {likes, comments, shares, reach},
  ai_generated_caption: bool,
  ai_suggested_hashtags: [...],
}
```

### `marketing_plans` (platform-level, configurable)
```js
{
  id: "basic" | "pro" | "enterprise",
  name: "Pro Marketing",
  monthly_price_gbp: 149,
  annual_price_gbp: 1_490,
  stripe_price_id_monthly: "price_...",
  stripe_price_id_annual: "price_...",
  limits: {
    contacts: 25_000,
    monthly_emails: 250_000,
    monthly_sms: 2_500,
    ai_generations: 500,
    journey_count: 25,
    social_accounts: 5,
  },
  features: {
    audiences: true, campaigns: true, ai_creative_studio: true,
    journeys: true, social_scheduling: true, white_label_social: false,
    dedicated_csm: false, advanced_attribution: true,
  },
  active: true, sort_order: 2,
}
```

### `marketing_subscriptions` (per org)
```js
{
  organization_id: uuid, plan_id: "pro",
  status: "active" | "trial" | "cancelled" | "past_due",
  stripe_subscription_id: "sub_...", stripe_customer_id: "cus_...",
  trial_ends_at: iso, current_period_end: iso,
  usage_this_period: {emails_sent, sms_sent, ai_generations, contacts_count},
  enabled_by: uuid (admin-override-able by GymAxis Master), comp_seats: false,
}
```

### `marketing_events` (event bus — capped collection)
```js
{
  id: uuid, organization_id: uuid, type: "...", at: iso,
  contact_id: uuid | null, payload: {...},
  source: "membership" | "crm" | "stripe" | "marketing" | "manual",
}
```
Indexed `organization_id + at` and `type + at`; consumed by Journey trigger
evaluator (every 60 s) and AI Insights aggregator (nightly).

---

## 4. Segmentation Engine

`POST /api/marketing/audiences/preview` — accepts a rule-tree and returns
`{count, sample_contacts[10]}` without persisting. This is the core of the
audience builder UI — every drag/drop refreshes the count.

`POST /api/marketing/audiences` — saves the rule-tree as a named audience.
Dynamic audiences re-resolve on every campaign send; snapshots freeze the
contact list at save time.

Resolver pipeline:
1. **Field resolvers** map `rule.field` to a Mongo aggregation stage.
2. Each rule is composed via `$and` / `$or` operators on the `crm_contacts`
   collection joined to `members` and `class_attendance`.
3. **Computed fields** (`churn_risk_score`, `attendance_30d`,
   `lifetime_value_gbp`) are pre-aggregated by a nightly job and stored on
   the contact doc — keeps audience preview <200 ms even on 50k members.
4. AI assist endpoint `POST /api/marketing/audiences/ai-suggest` accepts
   plain English ("members at risk of churning") → returns a draft rule-tree.

---

## 5. AI Creative Studio

**Stack**: Emergent LLM Key → `emergentintegrations` lib → Gemini Nano Banana
(image gen) + GPT-4o-mini (caption / brand-voice copy).

### Endpoints
- `POST /marketing/creative/generate` — body `{type, prompt, n: 3}` →
  returns `{asset_id, variants: [{url, ...}]}`. Persists to
  `marketing_creative_assets` and S3-equivalent storage.
- `POST /marketing/creative/upload` — direct image upload (validated via
  `validate_upload`).
- `GET  /marketing/creative` — list with pagination, filterable by type.
- `POST /marketing/creative/{id}/variations` — re-generate variants from
  the same prompt with different style guidance.

### Prompt enhancement (server-side)
Every prompt is augmented with:
1. **Brand kit fragment** — "Brand colours: #0055FF/#66CCFF; logo URL: ...;
   tone: energetic; brand phrase: 'Train · Recover · Win'".
2. **Type-specific framing** — `poster` adds "vertical 4:5, dramatic
   lighting, gym interior with kettlebells visible"; `email_hero` adds
   "horizontal 16:9, light enough for white background email body".
3. **Negative prompt** — "no stock-photo watermarks, no text overlays
   resembling a logo other than the supplied brand mark".

### Brand consistency
- Brand-kit upload lifts colours via `colorthief` and stores them as design
  tokens consumed by the email-block renderer.
- Logo overlay is composited **server-side post-generation** (always same
  position / size) so the AI never has to draw the logo.

---

## 6. Campaign Builder (UX)

3-step wizard plus an advanced expert mode.

1. **Audience** — pick a saved audience, build inline, or paste a CSV.
   Live count updates as rules change.
2. **Content** — block-based editor with templates (welcome, win-back,
   class-promo, PT-upsell). Each block accepts AI assistance:
   - Subject-line generator (5 options ranked by predicted open rate).
   - Body suggester (uses brand voice).
   - Creative asset picker — "generate hero image" inline.
3. **Schedule** — send now, schedule for later, or send to a journey.
   AI suggests optimal send time based on historic open patterns for the
   audience.

Always-visible **AI Assistant sidebar** explains every recommendation and
lets the user one-click accept.

---

## 7. Omnichannel Messenger

`utils/marketing/dispatch.py` — single function `send(message, channel)`.
Channel adapters:

| Channel | Implementation | Phase |
|---------|---------------|-------|
| Email   | Resend SDK (already in codebase) | **Phase 1** |
| SMS     | Twilio SDK (stubbed adapter) | Phase 2 |
| In-app  | `marketing_messages` row picked up by frontend toast on next login | Phase 1 |
| WhatsApp| Twilio Messaging | Phase 3 |

**Cross-channel fallback** — journey node `send_with_fallback` accepts a
primary + secondary channel and a wait time. Email-first → no-open-in-24 h
→ SMS auto-retry.

**Tracking** — every email body has a 1×1 pixel + link rewriter
(`/marketing/track/open/{message_id}` and `/marketing/track/click/{message_id}`).
Pixel returns a 1×1 PNG; link returns a 302 to the original URL after
recording the click event.

---

## 8. Journey Builder (visual canvas)

Frontend uses **React Flow** (already in package.json). Nodes:

- `trigger` (entry, one per journey)
- `wait` (duration)
- `send_email` / `send_sms` / `send_in_app`
- `branch` (condition: opened? clicked? booked?)
- `create_offer` (Stripe coupon) / `tag_contact` / `notify_staff` /
  `assign_crm_task` / `move_to_stage`
- `goal` (defined revenue/conversion target — terminates the path)

Backend runner `utils/marketing/journey_runner.py` executes every 60 s:
1. Pull pending steps from `marketing_journey_runs` (`next_run_at <= now`).
2. Execute action; schedule next step based on edge.
3. Increment journey-level metrics.

AI optimisation — runner records winning subject/body/send-time per step;
once N=200 successful sends accumulate, the runner picks the best variant
for new entrants.

---

## 9. Social Media (Meta Graph)

### OAuth wizard (gym-facing, **/marketing/social/connect**)
Each gym connects **their own Meta Business app + Page** — that's how Meta
actually works (one app per business, not per platform tenant). Wizard:

1. **Step 1 — Choose**: Facebook Page, Instagram Business, or both.
2. **Step 2 — Login**: redirect to Facebook OAuth with scopes
   `pages_show_list pages_manage_posts pages_read_engagement
   instagram_basic instagram_content_publish business_management`.
3. **Step 3 — Pick Page**: list of Pages the user manages → user picks one.
4. **Step 4 — Confirm IG**: if Instagram selected, fetch the IG Business
   account ID linked to that Page.
5. **Step 5 — Test post**: a "Hello from GymAxis Marketing Suite" preview
   post the user must approve before activating.

Tokens encrypted at rest using the same Fernet key used by the
`integration_configs` collection.

### Posting
- `POST /marketing/social/posts` — create draft.
- `POST /marketing/social/posts/{id}/schedule` — set `scheduled_at`.
- Background `social_publisher` runs every 5 min, picks up due posts, calls
  Meta Graph API `/{page-id}/feed` (FB) or `/{ig-user-id}/media` then
  `/media_publish` (IG).
- Metrics polled hourly: likes, comments, shares, reach.

---

## 10. Performance & Attribution

`GET /marketing/campaigns/{id}/report` returns:
- Funnel: sent → delivered → opened → clicked → converted.
- Revenue attributed (any booking/payment within 7 d of click on a
  message in this campaign).
- Retention impact (audience attendance Δ vs control 30 d post-send).
- Cohort breakdown by tier / location / churn-risk segment.

`GET /marketing/dashboard` — org-level rollup (this month: campaigns
sent, audiences active, revenue from marketing, avg open / click rates,
top-performing journey).

`GET /master-admin/marketing/analytics` — platform-wide rollup (all orgs):
total emails sent, MAUs, AI generations, plan distribution, MRR from
marketing add-ons, most-active orgs.

---

## 11. AI Insights (Proactive Engine)

Nightly job `utils/marketing/insights_runner.py` produces tile-style
insights surfaced on `/marketing` home:

- **Capacity** — "Monday 19:00 spin class is 38% under capacity for the
  next 4 weeks. Run a free-class promo to your inactive segment?" → one-click
  CTA spins up a campaign draft.
- **Churn risk** — "12 members have a churn-risk > 70 and haven't been
  contacted in 14 days. Send a personalised win-back?"
- **Trend** — "HIIT bookings up 24% week-on-week. Promote your HIIT bundle
  to your high-spender segment?"
- **Performance review** — "Your last campaign 'Spring Special' had a
  click-rate 38% below your 90-day average. Try our AI subject-line
  optimiser on the next one?"

Insights ranked by `predicted_revenue_uplift_gbp` so operators see the
biggest opportunities first.

---

## 12. Monetisation (Stripe Add-on)

### Tiers (defaults, configurable per platform admin)

| Tier        | £/mo  | Contacts | Emails / mo | AI gens / mo | Social acct | Features |
|-------------|------:|---------:|------------:|-------------:|------------:|----------|
| Basic       |   £49 |    5 000 |      25 000 |            0 |           1 | Audiences + email campaigns |
| Pro         |  £149 |   25 000 |     250 000 |          500 |           5 | + AI Creative + Journeys + SMS |
| Enterprise  |  £399 |  Unlimited |  Unlimited  |        5 000 |     Unlimited | + White-label social + Dedicated CSM |

### Admin configurability
- `/master-admin/marketing/plans` — GymAxis Master + Pulse Master can edit
  tier price, limits, feature flags. Changes hot-reload via `marketing_plans`
  collection (no redeploy needed).
- Trial: every new org gets 14-day free Pro trial on first visit to
  `/marketing`.
- Comp seats: GymAxis Master can flag any org as `comp_seats: true` to
  bypass billing entirely (useful for partners / pilots).

### Gating
- Backend decorator `@requires_plan('pro')` on premium routes.
- Frontend reads `/marketing/me/entitlement` once on load and disables
  locked features with a *"Upgrade to Pro"* CTA modal.

### Stripe wiring
- Reuses the existing **Stripe Connect Standard** integration (same
  platform-fee structure as gym-floor billing).
- New webhooks: `customer.subscription.created/updated/deleted`,
  `invoice.payment_succeeded/failed`. Handler updates
  `marketing_subscriptions.status` + invoices the `usage_this_period`
  counters reset on `current_period_end`.

---

## 13. Master Admin Surface

**Sidebar** → new entry **"Marketing Suite"** under group `tools` with
sub-tabs:

1. **Overview** — platform-wide KPIs (MRR, MAUs, emails sent, top orgs).
2. **Plans** — edit / publish tier definitions.
3. **Subscriptions** — list of active marketing subscriptions, churn,
   comp-seat overrides.
4. **AI Usage** — token spend per org for Gemini / GPT-4o-mini, alertable.
5. **Insights Feed** — what insights the AI is generating across all
   orgs (governance + tuning surface).

Pulse Master Admin sees the same surface but scoped via the existing
`is_pulse_only(user)` filter — so they only see Pulse-visible orgs'
marketing analytics.

---

## 14. Phased Rollout

### Phase 1 (this session — Apr 2026)
- Segmentation engine + audience builder
- Email campaign builder + Resend dispatch
- Performance dashboard
- AI Creative Studio (poster + social_post via Gemini Nano Banana)
- Journey Builder canvas (trigger eval cron, send-email + wait nodes)
- Meta OAuth wizard scaffold + post scheduler skeleton
- Stripe plan gating + Master Admin plans/analytics page
- `marketing_events` bus + nightly Insights aggregator (insight tiles)

### Phase 2 (next)
- SMS via Twilio (when keys provided)
- Branch / offer / staff-notify nodes in Journey Builder
- Conversion attribution (booking / payment within N days of click)
- Retention impact A/B testing
- WhatsApp via Twilio
- TikTok scheduler

### Phase 3 (future)
- Push notifications (web + mobile)
- Multi-armed-bandit subject-line optimiser
- Conversational AI assistant (voice → campaign in 30 s)

---

## 15. Example User Flows

### Flow A — "Promote spin class for Saturday"
1. Operator opens `/marketing` → "Quick start" → "Promote a class".
2. Picks Saturday 09:00 spin from class drop-down (auto-fills audience
   "members who attended spin in last 90d").
3. AI Creative Studio generates 4 poster variants in 8 s.
4. Email campaign auto-drafts with variant 2 as hero.
5. AI suggests Friday 18:30 as send time.
6. Operator clicks **Schedule** — done in 90 s end-to-end.
7. Campaign sends, opens / clicks roll in, attendance Saturday tracked,
   revenue attributed.

### Flow B — "Win back at-risk members"
1. Insights tile: "12 members at risk of churning, no contact in 14 days."
2. One-click "Run win-back journey" → loads pre-built 3-step journey:
   email day 0 → SMS day 3 → 20% offer day 7.
3. AI personalises each step copy per member's last class attended.
4. 4 of 12 reactivate within 7 days, attributed back to Insights tile.

### Flow C — "Connect Instagram and schedule a week of posts"
1. `/marketing/social/connect` → wizard.
2. Operator approves Meta OAuth, picks the Pulse Fitness Tottenham Page.
3. Creative Studio generates 7 posts (one per day) tied to that week's
   class schedule.
4. Scheduler queues all 7 for posting at 11:30 daily.
5. After posting, engagement metrics roll back to the post detail view.

---

## 16. Security & Compliance

- All access tokens (Meta, Twilio) encrypted at rest with the existing
  Fernet key (`integration_configs` shared key).
- GDPR — every contact has `marketing_consent` (email / SMS / push) bit.
  Audience resolver auto-excludes anyone without the relevant consent for
  the campaign's channel.
- Unsubscribe — every email body is rewritten to include a per-message
  unsubscribe link; click flips the consent bit.
- Audit trail — every campaign send / journey activation logged to
  `activity_log` with `actor` / `target` / `at`.

---

*Last updated: 2026-04-25 — Phase 1 in active development.*
