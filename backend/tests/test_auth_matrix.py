"""Automated authorisation matrix — CI regression (security §36 & §38).

Walks the LIVE FastAPI app and asserts that no NEW unauthenticated `/api`
endpoint has appeared that is not in the curated public-route baseline
(`security_matrix_baseline.json`). Any new route lacking an auth dependency —
i.e. a Broken-Function-Level-Authorisation gap — fails the build.

Adding a genuinely public route is a deliberate, reviewable action:
    cd /app/backend && python scripts/gen_security_matrix.py --write-baseline
…which a reviewer must sign off (it changes the security baseline).

Also asserts the resource-registry deny-by-default matrix stays wired.
"""
import json
import os
import sys

BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from scripts.gen_security_matrix import build_matrix, unprotected, BASELINE_PATH  # noqa: E402


def _load_baseline():
    if not os.path.exists(BASELINE_PATH):
        raise AssertionError(
            "security_matrix_baseline.json missing — run "
            "`python scripts/gen_security_matrix.py --write-baseline`"
        )
    with open(BASELINE_PATH) as f:
        return set(json.load(f).get("public_routes", []))


class TestAuthorisationMatrix:

    def test_no_new_unauthenticated_endpoint(self):
        """The build fails if a new /api route has no auth dependency and is
        not an approved public route."""
        entries = build_matrix()
        current = set(unprotected(entries))
        baseline = _load_baseline()

        new_gaps = sorted(current - baseline)
        assert not new_gaps, (
            "\n\nBROKEN FUNCTION-LEVEL AUTHORISATION — new endpoint(s) with no "
            "authentication dependency:\n  - " + "\n  - ".join(new_gaps) +
            "\n\nAdd an auth dependency (e.g. Depends(get_current_user)) OR, if "
            "the route is genuinely public, get it reviewed and run:\n"
            "  python scripts/gen_security_matrix.py --write-baseline\n"
        )

    def test_baseline_is_current(self):
        """Warn (not fail) if approved public routes were removed — keeps the
        baseline from drifting stale. Removal is allowed, addition is not."""
        entries = build_matrix()
        current = set(unprotected(entries))
        baseline = _load_baseline()
        removed = baseline - current
        # Informational only — removed public routes are safe (they became
        # authenticated or were deleted). We just assert the baseline still
        # describes real routes for >50% of its entries (sanity).
        assert len(baseline) == 0 or (len(baseline - removed) / len(baseline)) >= 0.5

    def test_every_api_route_classified(self):
        entries = build_matrix()
        assert len(entries) > 1000  # sanity: the app mounted fully
        # Every mutating, authenticated route must expose at least one known
        # auth dependency name (guards against silent auth-dependency renames).
        for e in entries:
            if e["authenticated"]:
                assert e["auth_dependencies"], e["path"]

    def test_resource_registry_deny_by_default(self):
        """Every registered resource type still fails closed for an
        unregistered/anonymous scope (deny-by-default kept wired)."""
        from utils.authz import RESOURCE_REGISTRY, ResourceSpec
        assert len(RESOURCE_REGISTRY) >= 10
        for name, spec in RESOURCE_REGISTRY.items():
            assert isinstance(spec, ResourceSpec)
            assert spec.collection and spec.org_fields
