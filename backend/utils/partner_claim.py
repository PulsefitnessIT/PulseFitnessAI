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
        # 1. Find every partner_engineers row that belongs to this email.
        #    The dashboard (`_get_partner_by_user`) resolves the row by
        #    `user_id` ONLY, so the row's `user_id` MUST point at the
        #    logged-in user or the engineer gets flagged-as-partner (via the
        #    email match below) yet lands on an empty "Become a Partner
        #    Engineer / Apply now" screen. This happens when the row's
        #    `user_id` is the `pending:<id>` placeholder OR a stale/dead id
        #    (e.g. the engineer's original account was removed and they
        #    re-registered with the same email). Self-heal by relinking the
        #    row to the current user.
        rows = await db.partner_engineers.find(
            {"email": email_rx},
            {"_id": 0, "id": 1, "user_id": 1, "status": 1, "created_at": 1},
        ).to_list(length=50)
        if not rows:
            return False
        # Already correctly linked to this user? Then nothing to relink.
        if not any(r.get("user_id") == user_id for r in rows):
            # Pick the best row to own this user: approved first, then newest.
            def _rank(r):
                return (1 if r.get("status") == "approved" else 0, r.get("created_at") or "")
            target = sorted(rows, key=_rank, reverse=True)[0]
            try:
                await db.partner_engineers.update_one(
                    {"id": target["id"]},
                    {"$set": {"user_id": user_id, "updated_at": _now()}},
                )
                logger.info("[partners] relinked partner row %s → user=%s (%s)",
                            target["id"], user_id, email)
            except Exception as relink_exc:  # noqa: BLE001
                # Unique index on user_id — another row already owns this id,
                # which means the user is already linked. Safe to ignore.
                logger.warning("[partners] relink skipped for %s: %s", email, relink_exc)
        # 2. Idempotent flag so login/me payloads route correctly.
        await db.users.update_one(
            {"id": user_id, "is_partner_engineer": {"$ne": True}},
            {"$set": {"is_partner_engineer": True}},
        )
        logger.info("[partners] flagged user=%s as partner engineer (%s)", user_id, email)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] claim_pending_partner_for_user failed: %s", exc)
    return False
