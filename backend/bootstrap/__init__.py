"""Bootstrap package — long-running ``startup`` work split off ``server.py``.

Iter 220dy (Feb 2026): `/app/backend/server.py` had grown past 1000
lines, with the bulk being one-shot startup seeding + index
creation. These functions are stateless, depend only on
``utils.database.db``, and don't reference the FastAPI ``app`` or
``api_router`` instances — so they extract cleanly into a
dedicated package, leaving ``server.py`` to do what it should:
wire middleware, mount routers, and orchestrate startup.

Two modules:

* ``bootstrap.seed`` — ``seed_master_admin`` and ``seed_services``
  (which seeds CRM, integrations, picklists, memberships and
  Pulse tenant mirror).
* ``bootstrap.indexes`` — ``create_indexes`` builds every
  collection's index family in one place so additions land in a
  single audit-friendly file.

The public API is the three coroutines re-exported below; the
``startup`` handler in ``server.py`` calls them in dependency
order.
"""
from .indexes import create_indexes
from .seed import seed_master_admin, seed_services

__all__ = ["create_indexes", "seed_master_admin", "seed_services"]
