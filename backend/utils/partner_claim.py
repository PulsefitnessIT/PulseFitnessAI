"""Iter 219e — Auto-claim helper for stranded partner_engineers rows.

When an engineer applies via `/partners/public-apply` they don't yet
have a user account. Master Admin approves them → a `partner_engineers`
row is created with `user_id="pending:<partner_id>"` (unique placeholder
to dodge the unique-index collision on null `user_id`).

The engineer then registers / logs in with the same email. Before this
iter, nothing linked the two: `_get_partner_by_user(user["id"])` would
return None forever and the engineer would be locked out of every
partner UI. We discovered this with 37 of 40 approved partners stuck
in this state.

`claim_pending_partner_for_user` is called from `/auth/register` and
`/auth/login` (idempotent, best-effort, never blocks auth). It also
runs proactively against the existing 37 stranded rows via a tiny
backfill script in iter 219e migrations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_pending_partner_for_user(email: str | None, user_id: str | None) -> bool:
    """Best-effort claim. Returns True iff we relinked at least one
    partner_engineers row to this user. Never raises — auth must
    not fail because of a partner-side hiccup."""
    if not email or not user_id:
        return False
    try:
        # Import here so the auth router doesn't pull the whole
        # partner-engineers surface on cold start.
        from utils.database import db
        # Match any row that:
        #   • shares the email (case-insensitive — Mongo collation
        #     not used to keep the index hits cheap; lowercased
        #     copies sit beside the original)
        #   • is still in the pending-claim placeholder state
        result = await db.partner_engineers.update_many(
            {
                "email": {"$regex": f"^{email}$", "$options": "i"},
                "user_id": {"$regex": "^pending:"},
            },
            {"$set": {"user_id": user_id, "updated_at": _now()}},
        )
        if result.modified_count:
            logger.info(
                "[partners] claimed %d pending partner_engineer row(s) for user=%s (%s)",
                result.modified_count, user_id, email,
            )
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] claim_pending_partner_for_user failed: %s", exc)
    return False
