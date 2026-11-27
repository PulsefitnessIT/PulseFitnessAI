"""Atomic once-only claims for scheduled emails (stops duplicate sends across workers and overlapping senders)."""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from utils.database import db

_IDX = False


async def claim(key: str, **meta) -> bool:
    global _IDX
    if not _IDX:
        await db.email_send_claims.create_index("key", unique=True)
        _IDX = True
    try:
        await db.email_send_claims.insert_one({"key": key, "claimed_at": datetime.now(timezone.utc).isoformat(), **meta})
        return True
    except DuplicateKeyError:
        return False


async def release(key: str) -> None:
    await db.email_send_claims.delete_one({"key": key})


def trial_ending_key(org_id: str, ends_at) -> str:
    """One 'your trial is ending' email per organisation per trial end date, whichever sender gets there first."""
    return f"trial_ending:{org_id}:{str(ends_at)[:10]}"
