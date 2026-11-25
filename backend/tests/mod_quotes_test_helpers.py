"""Test-only helpers for MOD quotation HTTP tests: create/delete a TEST_ second MOD site + user, and delete test groups by id."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils.auth import hash_password  # noqa: E402

OTHER_EMAIL = "test_other_modsite@example.test"
OTHER_PW = "TestOther123!"


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def create_other(run: str) -> dict:
    db = _db()
    org_id, user_id = f"TEST_other_site_{run}", f"TEST_other_user_{run}"
    now = datetime.now(timezone.utc).isoformat()
    await db.organizations.insert_one({"id": org_id, "name": f"TEST_Other MOD Site {run}", "account_type": "mod_site", "created_at": now})
    await db.users.insert_one({"id": user_id, "email": f"test_other_{run}@example.test", "full_name": "TEST Other Officer",
                               "organization_id": org_id, "role": "owner", "account_type": "mod_site", "is_mod_user": True,
                               "password": hash_password(OTHER_PW), "must_change_password": False, "created_at": now})
    return {"org_id": org_id, "user_id": user_id, "email": f"test_other_{run}@example.test", "password": OTHER_PW}


async def delete_other(org_id: str, user_id: str):
    db = _db()
    await db.users.delete_one({"id": user_id})
    await db.organizations.delete_one({"id": org_id})


async def delete_groups(gids: list[str]):
    db = _db()
    for gid in gids:
        await db.crm2_quotes.delete_many({"mod_group_id": gid})
        await db.mod_quote_events.delete_many({"group_id": gid})
        await db.mod_quote_authorisations.delete_many({"group_id": gid})
        await db.mod_quote_handovers.delete_many({"group_id": gid})
        await db.crm2_activities.delete_many({"mod_group_id": gid})
        await db.crm2_opportunities.delete_many({"mod_group_id": gid})
        await db.mod_quote_groups.delete_one({"id": gid})


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


if __name__ == "__main__":
    # usage: python mod_quotes_test_helpers.py delete_groups gid1 gid2
    if sys.argv[1] == "delete_groups":
        run(delete_groups(sys.argv[2:]))
        print("deleted", sys.argv[2:])
