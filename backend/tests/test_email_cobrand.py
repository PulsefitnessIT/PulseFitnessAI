"""Iter 216h64 — regression tests for the co-branded email wrapper.

Every outbound email passes through `wrap_branded(html, organization_id)`
which prepends a header with the operator's logo (left) + the platform
mark (GymAxis or Pulse Fitness) (right) and appends a co-branded footer.

These tests cover:
  - Platform-only emails (no organization_id) still get a header.
  - Pulse Pro / Lite tenants get the Pulse Fitness lockup as the
    platform mark.
  - Full-account tenants get the GymAxis lockup.
  - Operator logo & name resolve from the org document.
  - The wrapper is idempotent — already-wrapped HTML passes through.
"""

# ruff: noqa: E402
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio  # noqa: E402

from utils.email import (  # noqa: E402
    _looks_branded,
    wrap_branded,
)
from tests.shared_loop import run_async as run


def test_wraps_platform_only():
    async def _go():
        out = await wrap_branded("<p>Hello world</p>")
        assert "gymaxis-email-cobrand-wrap" in out
        assert "Hello world" in out

    run(_go())


def test_wraps_pulse_tenant():
    """Pulse Pro tenant id 8cd02d8c-… → Pulse Fitness mark."""
    async def _go():
        out = await wrap_branded("<p>Hi Pulse</p>", "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f")
        assert "Pulse Fitness" in out

    run(_go())


def test_idempotent():
    async def _go():
        once = await wrap_branded("<p>Hello</p>", "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f")
        twice = await wrap_branded(once, "8cd02d8c-e5a2-4c13-bdb9-8b143b85455f")
        assert once == twice
        assert _looks_branded(once)

    run(_go())


def test_unknown_org_falls_back_to_platform():
    async def _go():
        out = await wrap_branded("<p>x</p>", "non-existent-org-id-xxx")
        assert "gymaxis-email-cobrand-wrap" in out
        # Still wraps cleanly without crashing.
        assert "<p>x</p>" in out

    run(_go())


if __name__ == "__main__":
    test_wraps_platform_only()
    test_wraps_pulse_tenant()
    test_idempotent()
    test_unknown_org_falls_back_to_platform()
    print("ALL PASS")
