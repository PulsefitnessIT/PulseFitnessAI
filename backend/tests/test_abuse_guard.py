"""Abuse auto-response escalation ladder tests — security §33."""
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
import utils.abuse_guard as ag  # noqa: E402

EMAIL = "abuseqa_actor@test.local"
KEY = f"user:{EMAIL}"


async def _reset():
    await db.abuse_counters.delete_one({"id": KEY})
    await db.security_events.delete_many({"actor_email": EMAIL})


def _user():
    return {"id": "abuseqa_1", "email": EMAIL, "role": "manager"}


class TestAbuseGuard:

    def test_escalates_and_blocks_writes_but_not_reads(self):
        async def run():
            await _reset()
            u = _user()
            # Below throttle: reads + writes still fine.
            for _ in range(ag.T_THROTTLE - 1):
                await ag.record_denial(u, None, reason="probe")
            await ag.check_abuse(u, None, action="read")   # never blocked
            await ag.check_abuse(u, None, action="update")  # not yet suspended

            # Drive past the SUSPEND threshold.
            for _ in range(ag.T_SUSPEND):
                await ag.record_denial(u, None, reason="probe")

            # Reads are still allowed even when suspended.
            await ag.check_abuse(u, None, action="read")
            # Writes are now blocked with 429 + Retry-After.
            with pytest.raises(HTTPException) as ei:
                await ag.check_abuse(u, None, action="delete")
            assert ei.value.status_code == 429
            assert "Retry-After" in (ei.value.headers or {})

            # A critical abuse_detected event was recorded (Alert Centre feed).
            n = await db.security_events.count_documents(
                {"actor_email": EMAIL, "event_type": "abuse_detected"})
            assert n >= 1
            await _reset()
        asyncio.run(run())

    def test_stepup_level_forces_reauth_on_write(self):
        async def run():
            await _reset()
            u = _user()
            # Land squarely in the STEPUP band (>= STEPUP, < SUSPEND).
            for _ in range(ag.T_STEPUP):
                await ag.record_denial(u, None, reason="probe")
            with pytest.raises(HTTPException) as ei:
                await ag.check_abuse(u, None, action="update")
            assert ei.value.status_code == 403
            assert ei.value.detail.get("error") == "step_up_required"
            assert ei.value.detail.get("reason") == "unusual_activity"
            await _reset()
        asyncio.run(run())

    def test_admin_exempt(self):
        async def run():
            await _reset()
            admin = {"id": "a", "email": EMAIL, "is_master_admin": True}
            for _ in range(ag.T_SUSPEND + 5):
                await ag.record_denial(admin, None, reason="probe")
            # Admin writes are never blocked by the abuse guard.
            await ag.check_abuse(admin, None, action="delete")
            await _reset()
        asyncio.run(run())

    def test_disabled_is_noop(self):
        async def run():
            await _reset()
            u = _user()
            for _ in range(ag.T_SUSPEND + 2):
                await ag.record_denial(u, None, reason="probe")
            original = ag.ABUSE_GUARD_ENFORCED
            ag.ABUSE_GUARD_ENFORCED = False
            try:
                await ag.check_abuse(u, None, action="delete")  # no raise
            finally:
                ag.ABUSE_GUARD_ENFORCED = original
                await _reset()
        asyncio.run(run())
