"""Auto-carved package (god-file split). Re-exports router(s) + symbols."""
from ._shared import *  # noqa: F401,F403
from ._shared import router, engineer_router
from . import planner  # noqa: F401  (registers routes)
from . import engineer_views  # noqa: F401  (registers routes)

# Restore original static-before-dynamic route precedence lost when splitting.
router.routes.sort(key=lambda _r: 1 if "{" in getattr(_r, "path", "") else 0)
engineer_router.routes.sort(key=lambda _r: 1 if "{" in getattr(_r, "path", "") else 0)
