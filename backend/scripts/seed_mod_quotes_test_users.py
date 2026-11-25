"""Seed MOD quotation test accounts (idempotent): a Pulse MOD Sales Manager/Pricing admin and a MOD site customer."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils.auth import hash_password  # noqa: E402

OPERATOR_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
MOD_SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
USERS = [
    {"email": "modsales.manager@pulsedemo.test", "password": "ModSales123!", "full_name": "MOD Sales Manager (test)",
     "organization_id": OPERATOR_ORG, "role": "manager", "account_type": "pulse_pro",
     "module_overrides": {"mod_operations": True}, "mod_quote_role": "pricing_admin_manager"},
    {"email": "modsales.rep@pulsedemo.test", "password": "ModSales123!", "full_name": "MOD Sales (test)",
     "organization_id": OPERATOR_ORG, "role": "staff", "account_type": "pulse_pro",
     "module_overrides": {"mod_operations": True}, "mod_quote_role": ""},
    {"email": "modsite.officer@army.mod.test", "password": "ModSite123!", "full_name": "Site Officer (test)",
     "organization_id": MOD_SITE, "role": "owner", "account_type": "mod_site", "is_mod_user": True},
]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    for u in USERS:
        doc = {k: v for k, v in u.items() if k != "password"}
        doc.update({"password": hash_password(u["password"]), "password_updated_at": now, "must_change_password": False})
        await db.users.update_one({"email": u["email"]}, {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}}, upsert=True)
        print("seeded", u["email"])


if __name__ == "__main__":
    asyncio.run(main())
