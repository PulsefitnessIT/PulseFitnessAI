"""Production safety guard for demo/test seed scripts.

Root problem this prevents: demo/test data accidentally landing in the
PRODUCTION database (e.g. a seed script run against a prod MONGO_URL, or a
migration carrying dev data across).

Policy (fail-safe): a seed script may only write when EITHER
  • the target MongoDB is LOCAL (preview/dev uses mongodb://localhost:27017), OR
  • an explicit override env var ALLOW_DEMO_SEED is truthy (a deliberate,
    documented escape hatch).
Otherwise it hard-exits BEFORE any connection/write happens.

Stdlib-only so every seed script can import it regardless of how it connects.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

# Hostnames we treat as a local (non-production) database.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", ""}


def _mongo_host() -> str:
    uri = os.environ.get("MONGO_URL", "")
    try:
        # urlparse handles mongodb:// and mongodb+srv:// forms.
        return (urlparse(uri).hostname or "").lower()
    except Exception:
        return ""


def is_local_database() -> bool:
    """True when MONGO_URL points at a local dev/preview database."""
    return _mongo_host() in _LOCAL_HOSTS


def _override_enabled() -> bool:
    return os.environ.get("ALLOW_DEMO_SEED", "").strip().lower() in ("1", "true", "yes", "on")


def assert_seeding_allowed(script_name: str = "seed script") -> None:
    """Abort (SystemExit) if this looks like a production database.

    Call this at the very top of a seed/test script, before connecting.
    """
    if is_local_database() or _override_enabled():
        return
    host = _mongo_host() or "<unknown>"
    raise SystemExit(
        f"[seed-guard] Refusing to run '{os.path.basename(str(script_name))}': "
        f"the target database host '{host}' is not local — this looks like PRODUCTION. "
        f"Demo/test seed scripts must never populate production. "
        f"If this is genuinely intended, re-run with ALLOW_DEMO_SEED=1."
    )
