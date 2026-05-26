> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> Memberships blueprint below unchanged. New activation events
> exposed for Memberships trials:
>
> - `first_member_added` — `POST /api/memberships/members`
> - `first_booking_taken` — `POST /api/memberships/bookings`
> - `first_invoice_generated` — `POST /api/memberships/invoices`
> - `first_class_scheduled` — `POST /api/memberships/class-templates`
>
> All wired into the matching route handlers as best-effort emit
> hooks. When a prospect signs up via `/modules/memberships`,
> `primary_module='memberships'` is set at register-time and the
> First Wins funnel narrows to ONLY these events (no equipment / no
> CRM / no marketing milestones).
>
> The `connect_stripe` step in the Setup Checklist remains visible
> for memberships trials (memberships is one of the modules that
> needs payment collection on day one).

---


# GymAxis Memberships — Architecture & Build Blueprint

> Member lifecycle + revenue + retention platform. Not a timetable. Not a
> billing page. **One operating layer** that turns members → bookings →
> revenue → CRM intelligence → retention actions.

## Guiding principles

1. **Every action connects to the member record.** A booking is not a row in
   a table; it is a datapoint on a person's retention trajectory.
2. **CRM is the relationship layer; Memberships is the commercial layer.** No
   duplicated ownership — see §4.
3. **Mobile-first everything.** The member portal is the product most users
   will touch; the operator console is secondary UX.
4. **Multi-site from day 1.** Umbrella memberships, site-scoped classes,
   branch rollups in every query.

## 1 · Primary entities

```
organization              # existing — gym operator / multi-site group
  └─ mod_root_id / parent_id for umbrella grouping

site                      # NEW — a physical location
  - organization_id, name, address, timezone, brand_colour
  - access_rules (key fob, QR, both)

member                    # NEW — the person; separate from `users`
  - email (unique), password_hash (argon2/bcrypt)
  - first_name, last_name, phone, dob, emergency_contact
  - site_id (home site), organization_id (group)
  - tags[], notes (operator-only), waivers[]
  - status: active|frozen|cancelled|lapsed
  - account_type: "member" (distinct from user "gym_owner"/"mod_site" etc)
  - created_at, last_seen_at, lifetime_value_gbp, no_show_count

membership_plan           # NEW — a sellable product
  - id, organization_id, name, description, colour
  - kind: recurring | fixed_term | class_pack | payg
  - price_pence, currency (GBP default), billing_cycle (monthly|annual|oneoff)
  - upfront_fee_pence (joining fee)
  - included_classes (unlimited | N_per_week | credits)
  - credits_count (for class_pack)
  - duration_days (fixed_term only)
  - freeze_allowed, freeze_max_days, cancel_notice_days
  - site_scope: "all_sites" | [site_id,...]  (umbrella vs site-locked)
  - stripe_price_id (Phase 1b)
  - active, display_order

member_membership         # NEW — an instance of a plan held by a member
  - id, member_id, plan_id, organization_id
  - status: active|frozen|cancelled|expired|pending_payment
  - start_date, end_date (null for rolling)
  - billing_status: current|past_due|cancelled_future
  - credits_remaining (packs only), credits_used
  - stripe_subscription_id (Phase 1b)
  - gocardless_mandate_id (Phase 2)
  - frozen_from, frozen_until, cancel_effective_date
  - joined_at, last_billed_at, next_billing_at
  - audit_log[]: {at, actor_id, action, payload}

class_template            # NEW — the recurring pattern
  - id, organization_id, site_id, name, description, category
  - instructor_user_id, room_name, colour
  - duration_min, capacity
  - recurs: {by: "weekly", days: [1,3,5], start_time: "07:00"}
  - booking_opens_hours_before (default 168 = 1 week)
  - cancellation_cutoff_hours_before (default 12)
  - waitlist_enabled, max_waitlist
  - credits_to_book (default 1 from member's pack; 0 if unlimited)
  - required_tag (gate access — e.g. "MOD" or "VIP")
  - access_plans: [plan_id,...] (null = all plans allowed)

class_occurrence          # NEW — materialised instance on a specific date
  - id, template_id, organization_id, site_id
  - starts_at, ends_at, instructor_user_id, room_name
  - capacity, bookings_count, waitlist_count, attended_count, no_show_count
  - status: scheduled|cancelled (operator cancelled)
  - generated_from: template_id
  - (Occurrences auto-generated 8 weeks ahead by a nightly job.)

booking                   # NEW — a member's hold on a class
  - id, occurrence_id, member_id, organization_id, site_id
  - status: booked|waitlist|attended|no_show|cancelled|late_cancel
  - booked_at, cancelled_at, checked_in_at, promoted_from_waitlist_at
  - credits_charged (0 if unlimited)
  - payment_ref (for drop-in)
  - channel: member_portal|operator|api|kiosk

member_session            # NEW — member portal JWT tracking
  - id, member_id, issued_at, last_seen_at, user_agent, revoked

member_ledger             # NEW — financial movements per member
  - id, member_id, organization_id
  - type: charge|refund|credit|voucher|adjustment
  - amount_pence, currency, description
  - stripe_payment_intent_id?, stripe_invoice_id?
  - created_at, created_by (operator or "system")

qr_rotation_secret        # NEW — TOTP secret per member for check-in QR
  - member_id (unique), secret_b32, created_at, rotated_at
```

## 2 · Capacity + waitlist engine

```
book(occurrence, member):
  if occurrence.status != "scheduled": reject
  if now < occurrence.starts_at - template.booking_opens_hours_before * 3600: reject("too early")
  if member has another booking overlapping: reject("conflict")
  if member has active membership that doesn't cover this class: reject("plan_not_allowed")
  if credits_needed > 0 and member.credits_remaining < needed: reject("no_credits")

  if occurrence.bookings_count < occurrence.capacity:
    create booking(status="booked"), decrement credits
  elif template.waitlist_enabled and occurrence.waitlist_count < template.max_waitlist:
    create booking(status="waitlist"), DO NOT decrement credits yet
  else:
    reject("full")

cancel(booking):
  if now < occurrence.starts_at - template.cancellation_cutoff_hours_before * 3600:
    refund credits, status="cancelled"
    promote_waitlist(occurrence)
  else:
    status="late_cancel", credits NOT refunded, no_show_count += 1

promote_waitlist(occurrence):
  while occurrence.bookings_count < occurrence.capacity and waitlist exists:
    oldest_waitlist.status = "booked"
    decrement credits for that member
    send_promotion_email(that_member)

check_in(booking):
  if booking.status not in ("booked",): reject
  if now < occurrence.starts_at - 30min: reject("too early")
  if now > occurrence.ends_at + 15min: reject("too late")
  booking.status = "attended", booking.checked_in_at = now
```

## 3 · QR check-in (rotating TOTP)

Each member has a TOTP secret (32 bytes base32). Member portal shows:

```
qr payload = {
  "v": 1,
  "m": <member_id>,
  "o": <org_id>,
  "t": <unix_seconds>,
  "c": <6-digit TOTP code, rotates every 30s, generated from member.secret_b32>
}
```

QR kiosk reads, backend verifies code via `pyotp.TOTP(secret).verify(code)`.

## 4 · CRM ↔ Memberships source-of-truth

| Domain                     | Owner          | Read-only in other |
| --                          | --             | --                 |
| Member personal data       | Memberships   | CRM (syncs as contact) |
| Membership plan + status   | Memberships   | CRM (reads status for lead scoring) |
| Payment status             | Memberships   | CRM (reads as opportunity signal) |
| Attendance / retention risk | Memberships   | CRM (feeds churn scoring) |
| Lead origin / campaign     | CRM           | Memberships (reads at signup) |
| Account owner              | CRM           | Memberships (shows on profile) |
| Site / organization tree   | Shared        | both write          |

Sync is outbound event-driven from Memberships → CRM (see `outbox` pattern in
Phase 2). No two-way conflicts because no shared writes.

## 5 · Phased roadmap

### Phase 1a — **SHIPPED THIS SESSION**

* Core data model (all collections above)
* Members CRUD + separate auth (login, register, JWT)
* Membership plans CRUD
* Assign/freeze/cancel membership workflows
* Class templates + occurrence materialisation
* Booking/cancel + waitlist auto-promotion
* QR rotating-TOTP check-in
* Operator console (dashboard + members + classes + timetable)
* Member portal (browse/book/cancel, QR pass, profile)
* Seeded demo studio (`Pulse Studio · Leeds`)

### Phase 1b — **next session**

* Stripe Subscriptions (create, webhook, pause/resume/cancel, proration)
* Member ledger rendering + failed-payment retry flow
* Class pack credit purchases
* Email receipts + reminders (Resend)
* Operator-initiated sell membership/pack UI

### Phase 2

* GoCardless Direct Debit
* PT / 1-to-1 appointments with staff calendars
* SMS reminders (Twilio)
* Retention analytics + AI churn scoring
* CRM sync outbox
* Instructor portal (check-off, attendance marking)
* Reports export

### Phase 3

* Mobile PWA shell
* Corporate wellness
* Multi-site transfer / family linking
* Advanced AI (class scheduling optimiser, waitlist→new-class detector)

## 6 · Routes (Phase 1a)

```
# Operator-facing (require authenticated gym operator)
GET    /api/memberships/plans                      # list
POST   /api/memberships/plans                      # create
PATCH  /api/memberships/plans/{id}                 # update
DELETE /api/memberships/plans/{id}                 # archive

GET    /api/memberships/members                    # list + filter + search
POST   /api/memberships/members                    # operator-create
GET    /api/memberships/members/{id}               # full profile
PATCH  /api/memberships/members/{id}
POST   /api/memberships/members/{id}/assign-plan
POST   /api/memberships/members/{id}/freeze
POST   /api/memberships/members/{id}/cancel
GET    /api/memberships/members/{id}/timeline

GET    /api/memberships/classes/templates
POST   /api/memberships/classes/templates
PATCH  /api/memberships/classes/templates/{id}
DELETE /api/memberships/classes/templates/{id}

GET    /api/memberships/timetable?site=&from=&to=  # occurrences + bookings_count
POST   /api/memberships/classes/{occ_id}/cancel    # operator cancel

GET    /api/memberships/dashboard                   # operator KPIs

POST   /api/memberships/checkin/verify             # kiosk — scan QR
GET    /api/memberships/occurrences/{id}/roster    # front desk

# Member-facing (require authenticated member)
POST   /api/member-auth/register
POST   /api/member-auth/login
GET    /api/member-auth/me
POST   /api/member-auth/logout

GET    /api/member/timetable?from=&to=
POST   /api/member/bookings                        # body {occurrence_id}
DELETE /api/member/bookings/{id}
GET    /api/member/bookings                        # my upcoming + past
GET    /api/member/qr                              # rotating TOTP code
GET    /api/member/profile
PATCH  /api/member/profile
```
