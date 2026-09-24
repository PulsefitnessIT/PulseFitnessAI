import asyncio
from datetime import datetime, timezone, timedelta
from utils.database import db
from utils.auth import hash_password

EMAIL = "honey.test@pulsefitness.com"
TEMP = "TempPass123!"


async def main():
    res = await db.users.update_one(
        {"email": EMAIL},
        {"$set": {
            "password": hash_password(TEMP),
            "must_change_password": True,
            "temp_password_expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "active": True,
            "locked_until": None,
            "failed_login_attempts": 0,
        }},
    )
    print("matched", res.matched_count, "modified", res.modified_count)
    u = await db.users.find_one({"email": EMAIL})
    print("must_change_password", u.get("must_change_password"), "expires", u.get("temp_password_expires_at"))


asyncio.run(main())
