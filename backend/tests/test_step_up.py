"""Step-up (fresh re-authentication) tests — security §18."""
import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from utils.database import db  # noqa: E402
from utils.auth import hash_password  # noqa: E402
import utils.step_up as step_up  # noqa: E402

P = "STEPUPQA_"
UID = f"{P}user"
EMAIL = f"{P}user@test.local".lower()


async def _seed():
    await _teardown()
    await db.users.insert_one({
        "id": UID, "email": EMAIL, "role": "owner",
        "password_hash": hash_password("Sup3rSecret!"),
    })


async def _teardown():
    await db.users.delete_many({"id": {"$regex": f"^{P}"}})
    await db.security_step_ups.delete_many({"id": {"$regex": f"^{P.lower()}|test.local"}})
    await db.security_step_ups.delete_one({"id": EMAIL})


class TestStepUp:

    def test_password_challenge_and_freshness(self):
        async def run():
            await _seed()
            user = {"id": UID, "email": EMAIL}
            # Wrong password rejected.
            with pytest.raises(HTTPException) as ei:
                await step_up.verify_step_up_challenge(user, password="nope")
            assert ei.value.status_code == 400
            # Correct password accepted → method 'password'.
            method = await step_up.verify_step_up_challenge(user, password="Sup3rSecret!")
            assert method == "password"
            # Not fresh until recorded.
            assert await step_up.is_step_up_fresh(user) is False
            await step_up.record_step_up(user, method)
            assert await step_up.is_step_up_fresh(user) is True
            await _teardown()
        asyncio.run(run())

    def test_require_step_up_gate(self):
        async def run():
            await _seed()
            user = {"id": UID, "email": EMAIL}
            original = step_up.STEP_UP_ENFORCED
            step_up.STEP_UP_ENFORCED = True
            try:
                # No fresh step-up → 403 with machine-readable payload.
                with pytest.raises(HTTPException) as ei:
                    await step_up.require_step_up(user, action="delete_company")
                assert ei.value.status_code == 403
                assert ei.value.detail.get("error") == "step_up_required"
                assert ei.value.detail.get("action") == "delete_company"
                # After a fresh step-up → passes.
                await step_up.record_step_up(user, "password")
                await step_up.require_step_up(user, action="delete_company")  # no raise
            finally:
                step_up.STEP_UP_ENFORCED = original
                await _teardown()
        asyncio.run(run())

    def test_disabled_by_default_is_noop(self):
        async def run():
            await _seed()
            user = {"id": UID, "email": EMAIL}
            assert step_up.STEP_UP_ENFORCED is False  # default OFF
            # Even with no step-up recorded, the gate is a no-op when disabled.
            await step_up.require_step_up(user, action="delete_company")
            await _teardown()
        asyncio.run(run())

    def test_freshness_expiry(self):
        async def run():
            await _seed()
            user = {"id": UID, "email": EMAIL}
            await step_up.record_step_up(user, "password")
            original_ttl = step_up.STEP_UP_TTL_SECONDS
            step_up.STEP_UP_TTL_SECONDS = 0  # everything is instantly stale
            try:
                assert await step_up.is_step_up_fresh(user) is False
            finally:
                step_up.STEP_UP_TTL_SECONDS = original_ttl
                await _teardown()
        asyncio.run(run())
