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
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_pending_partner_for_user(email: str | None, user_id: str | None) -> bool:
    """Best-effort claim + partner-engineer flagging. Returns True iff this
    user is a partner engineer (a partner_engineers row is linked to them).
    Never raises — auth must not fail because of a partner-side hiccup.

    Iter 220ea·32 — also stamps ``users.is_partner_engineer = True`` so the
    frontend routes them to the Engineer App on login instead of the
    Operations dashboard (partner engineers have no org → account_type
    resolved to 'full' → they were dumped on /dashboard)."""
    if not email or not user_id:
        return False
    try:
        from utils.database import db
        email_rx = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        # 1. Link any still-pending placeholder rows for this email.
        await db.partner_engineers.update_many(
            {
                "email": email_rx,
                "user_id": {"$regex": "^pending:"},
            },
            {"$set": {"user_id": user_id, "updated_at": _now()}},
        )
        # 2. Is this user a partner engineer? (row linked by id OR email)
        linked = await db.partner_engineers.find_one(
            {"$or": [
                {"user_id": user_id},
                {"email": email_rx},
            ]},
            {"_id": 0, "id": 1},
        )
        if linked:
            # Idempotent flag so login/me payloads route correctly.
            await db.users.update_one(
                {"id": user_id, "is_partner_engineer": {"$ne": True}},
                {"$set": {"is_partner_engineer": True}},
            )
            logger.info("[partners] flagged user=%s as partner engineer (%s)", user_id, email)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] claim_pending_partner_for_user failed: %s", exc)
    return False
