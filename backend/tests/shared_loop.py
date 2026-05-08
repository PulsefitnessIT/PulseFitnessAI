"""Single source of truth for the shared session asyncio loop used by
backend pytest fixtures.

Why this module exists
----------------------
``conftest.py`` was being imported twice — once as ``conftest`` (the
plugin pytest auto-discovers) and once as ``tests.conftest`` (the
explicit import some test files use to share helpers like
``run_async``). Each import created its own ``_SHARED_LOOP``, so
fixtures running via the auto-discovered copy bound Motor to one loop
while tests calling ``run_async`` on the explicit copy ran on another
— producing the long-standing "Task got Future attached to a
different loop" failures in `test_security_hardening.py` and friends.

Putting the loop in its own module guarantees a single canonical
import path (``tests.shared_loop``), so all callers share the same
loop regardless of how they discovered the helper.
"""

from __future__ import annotations

import asyncio as _asyncio


_SHARED_LOOP = _asyncio.new_event_loop()
# Make it the process-wide default so Motor's lazy
# ``asyncio.get_event_loop()`` discovery binds to the same loop our
# fixtures + ``run_async`` helpers drive.
_asyncio.set_event_loop(_SHARED_LOOP)


def run_async(coro):
    """Run *coro* on the shared session loop. Imported by both
    ``conftest.py`` and individual test modules."""
    return _SHARED_LOOP.run_until_complete(coro)


__all__ = ["_SHARED_LOOP", "run_async"]
