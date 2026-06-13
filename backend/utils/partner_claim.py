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



async def backfill_partner_relink(dry_run: bool = False) -> dict:
    """One-pass proactive fix for the iter-272 stale-link bug.

    Relinks every ``partner_engineers`` row whose ``user_id`` is a
    ``pending:<id>`` placeholder OR a dead/stale id, to the real user that
    owns the row's email — so engineers who haven't signed in yet are
    unstuck without waiting for the lazy sign-in self-heal. Idempotent and
    conservative: it only relinks when (a) a user exists for the row's
    email and (b) the row isn't already correctly linked AND its current
    ``user_id`` is a placeholder or doesn't point at any real user (never
    steals a row from another live account). Also stamps the owning user
    ``is_partner_engineer=True`` so routing + dashboard agree.

    Returns a stats dict. ``dry_run=True`` reports without writing.
    """
    from utils.database import db
    stats = {
        "scanned": 0, "relinked": 0, "flagged": 0,
        "skipped_no_user": 0, "skipped_already_linked": 0,
        "skipped_other_user": 0, "errors": 0,
    }

    rows = await db.partner_engineers.find(
        {}, {"_id": 0, "id": 1, "email": 1, "user_id": 1},
    ).to_list(length=None)
    stats["scanned"] = len(rows)
    if not rows:
        return stats

    # Build lowercased email -> user_id map + the set of all real user ids.
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1}).to_list(length=None)
    email_to_uid: dict[str, str] = {}
    all_user_ids: set[str] = set()
    for u in users:
        uid = u.get("id")
        if uid:
            all_user_ids.add(uid)
        em = (u.get("email") or "").strip().lower()
        if em and uid and em not in email_to_uid:
            email_to_uid[em] = uid

    for r in rows:
        try:
            em = (r.get("email") or "").strip().lower()
            cur_uid = r.get("user_id") or ""
            target_uid = email_to_uid.get(em)
            if not em or not target_uid:
                stats["skipped_no_user"] += 1
                continue
            if cur_uid == target_uid:
                # Already linked — just ensure the routing flag is set.
                if not dry_run:
                    res = await db.users.update_one(
                        {"id": target_uid, "is_partner_engineer": {"$ne": True}},
                        {"$set": {"is_partner_engineer": True}},
                    )
                    if res.modified_count:
                        stats["flagged"] += 1
                stats["skipped_already_linked"] += 1
                continue
            # Only relink placeholders or rows whose user_id is dead/unknown.
            is_relinkable = cur_uid.startswith("pending:") or cur_uid not in all_user_ids
            if not is_relinkable:
                # Current id points at a real (different) user — don't steal it.
                stats["skipped_other_user"] += 1
                continue
            if not dry_run:
                try:
                    await db.partner_engineers.update_one(
                        {"id": r["id"]},
                        {"$set": {"user_id": target_uid, "updated_at": _now()}},
                    )
                except Exception as relink_exc:  # noqa: BLE001
                    # Unique index — target already owns a row. Skip safely.
                    logger.warning("[partners] backfill relink skipped %s: %s", r["id"], relink_exc)
                    stats["errors"] += 1
                    continue
                res = await db.users.update_one(
                    {"id": target_uid, "is_partner_engineer": {"$ne": True}},
                    {"$set": {"is_partner_engineer": True}},
                )
                if res.modified_count:
                    stats["flagged"] += 1
            stats["relinked"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[partners] backfill row failed (%s): %s", r.get("id"), exc)
            stats["errors"] += 1
    return stats


async def run_partner_relink_migration_once() -> None:
    """Marker-guarded startup migration so production auto-heals stranded
    engineers on the next redeploy (the user can't run scripts on prod).
    Runs the backfill exactly once per database; cheap no-op thereafter."""
    from utils.database import db
    marker = "partner_relink_backfill_v1"
    try:
        already = await db.migrations.find_one({"_id": marker})
        if already:
            return
        stats = await backfill_partner_relink(dry_run=False)
        await db.migrations.update_one(
            {"_id": marker},
            {"$set": {"_id": marker, "ran_at": _now(), "stats": stats}},
            upsert=True,
        )
        logger.info("[partners] relink backfill migration complete: %s", stats)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partners] relink backfill migration failed: %s", exc)
