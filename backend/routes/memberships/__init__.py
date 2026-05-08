"""GymAxis Memberships routes — package aggregator (Pass 2 split).

Each section of the legacy 1813-line `routes/memberships.py` is now a
focused submodule. This `__init__.py` is the single public entry-point:
it constructs ONE master `router` mounting all sub-routers and re-exports
every helper that the rest of the codebase already imports from
`routes.memberships`.

External imports remain backwards-compatible:
  • `from routes.memberships import router`
  • `from routes.memberships import _require_operator_org`
  • `from routes.memberships import _require_current_member`
  • `from routes.memberships import ensure_memberships_indexes`
  • `from routes.memberships import members_freeze, members_cancel`  (assistant.py)
  • `from routes.memberships import _promote_from_waitlist`
  • `from routes.memberships import _public_member, _now_iso, _gen_referral_code`
  • `from routes.memberships import _load_member, _member_token, pwd_ctx, logger`

Submodule layout:
    helpers.py        — shared utilities (auth, time, model helpers)
    member_misc.py    — referrals / streak / social-pulse
    member_auth.py    — register / login / me
    plans.py          — operator plan CRUD
    booking_rules.py  — per-gym booking rule overrides
    members.py        — operator member CRUD + bulk import + freeze/cancel
    classes.py        — class templates + materialiser
    timetable.py      — operator timetable + cancel + roster
    dashboard.py      — operator dashboard
    bookings.py       — member booking + cancel + swap + waitlist promotion
    qr_checkin.py     — rotating-TOTP pass + operator verify
    indexes.py        — startup index ensure
"""
from fastapi import APIRouter

from routes.memberships import (
    booking_rules,
    bookings,
    classes,
    dashboard,
    family_autopay,
    indexes,
    instructors,
    member_auth,
    member_misc,
    members,
    plans,
    qr_checkin,
    studio,
    studio_billing,
    studio_extras,
    studio_polish,
    timetable,
    wallet,
)

# Helper / utility re-exports (used by sibling routers + server.py + assistant.py)
from routes.memberships.helpers import (  # noqa: F401
    _gen_referral_code,
    _load_member,
    _member_token,
    _now_iso,
    _public_member,
    _require_current_member,
    _require_operator_org,
    _uuid,
    logger,
    pwd_ctx,
)
from routes.memberships.bookings import _promote_from_waitlist  # noqa: F401
from routes.memberships.classes import _materialise_occurrences  # noqa: F401
from routes.memberships.indexes import ensure_memberships_indexes  # noqa: F401
from routes.memberships.members import members_cancel, members_freeze  # noqa: F401


# Single master router — everything mounts here.
router = APIRouter(tags=["memberships"])
for sub in (
    member_misc,
    member_auth,
    plans,
    booking_rules,
    members,
    classes,
    timetable,
    dashboard,
    bookings,
    qr_checkin,
    studio,
    studio_extras,
    studio_polish,
    studio_billing,
    instructors,
    family_autopay,
    wallet,
):
    router.include_router(sub.router)


__all__ = [
    "router",
    "_require_operator_org",
    "_require_current_member",
    "_load_member",
    "_member_token",
    "_now_iso",
    "_uuid",
    "_public_member",
    "_gen_referral_code",
    "_promote_from_waitlist",
    "ensure_memberships_indexes",
    "members_freeze",
    "members_cancel",
    "logger",
    "pwd_ctx",
]
