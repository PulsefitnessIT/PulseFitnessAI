"""Operator BREAK-GLASS: reset MFA for a locked-out account (AUDITED).

Use only when a user (e.g. the master admin, who cannot self-disable) has lost
both their authenticator AND their backup codes. Clears their MFA enrolment so
the next login starts fresh (forced re-enrolment if MFA is still mandatory).
Writes a `mfa_break_glass_reset` security event so the action is never silent.

Usage (from /app/backend):
    PYTHONPATH=/app/backend python scripts/mfa_break_glass.py <email> "<reason>"
"""
import asyncio
import sys

from utils.database import db
from utils.security_events import log_security_event, SEV_WARNING


async def main(email: str, reason: str) -> None:
    email = email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "email": 1})
    if not user:
        print(f"No user found with email: {email}")
        return
    uid = user["id"]
    res = await db.user_mfa.delete_many({"user_id": uid})
    await log_security_event(
        "mfa_break_glass_reset",
        user={"id": "operator-cli", "email": "operator:mfa_break_glass", "role": "operator"},
        severity=SEV_WARNING,
        action="mfa_reset",
        result="reset",
        resource_type="user",
        resource_id=email,
        detail=f"Break-glass MFA reset for {email} — reason: {reason}",
        extra={"records_cleared": res.deleted_count},
    )
    print(f"MFA reset for {email} ({res.deleted_count} record(s) cleared).")
    print("Next login will force a fresh enrolment (if MFA is still mandatory).")
    print("Audited as security event: mfa_break_glass_reset.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: PYTHONPATH=/app/backend python scripts/mfa_break_glass.py <email> "<reason>"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
