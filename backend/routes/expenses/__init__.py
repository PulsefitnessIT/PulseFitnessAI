"""Pulse Fitness Expenses subsystem (iter 278).

Assembles the single shared ``router`` (defined in ``common``) by importing
each module so its endpoints attach. Import order matters: the settings and
reports modules register their *static* paths (``/config``, ``/dashboard``,
``/reports``…) BEFORE ``core`` registers the dynamic ``/{expense_id}`` route,
so the literal paths are not swallowed by the path-param matcher.
"""
from .common import router  # noqa: F401  (router defined here)
from . import settings  # noqa: F401,E402  (static config + settings paths)
from . import reports   # noqa: F401,E402  (static dashboard/reports/export paths)
from . import core      # noqa: F401,E402  (capture + dynamic /{expense_id})

__all__ = ["router"]
