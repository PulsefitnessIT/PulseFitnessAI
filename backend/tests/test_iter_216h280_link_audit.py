"""Iter 216h280 — Dead-link audit + redirects.

User asked for a link audit ("First wins — audit and ensure every
link is directed to where it is intended to"). Crawl + static
analysis found 5 dead links:

* `/forgot-password`     — used by EngineerLanding, no route
* `/legal/privacy`       — used by EngineerLanding, no route
                           (real route is `/privacy`)
* `/legal/terms`         — used by EngineerLanding, no route
                           (real route is `/terms`)
* `/svc/engineer/parts`  — used by EngineerHomeV2 quick-action, no
                           route (parts live inside jobs)
* `/api-docs`            — has a route, but the Kubernetes ingress
                           prefix-matches `/api*` to the backend so
                           the React app never loaded. Renamed to
                           `/developers`; legacy alias redirects.

This test guards the redirect routes by parsing AppRoutes.js — keeps
us honest if someone removes them. Pure file-system check so we don't
need a running React app.
"""
from __future__ import annotations

from pathlib import Path

ROUTES_FILE = Path("/app/frontend/src/routes/AppRoutes.js")


def _routes_text() -> str:
    return ROUTES_FILE.read_text(encoding="utf-8")


def test_legacy_legal_paths_redirect_to_canonical():
    """`/legal/privacy` and `/legal/terms` must remain Navigate-aliases
    to their canonical `/privacy` and `/terms` routes."""
    txt = _routes_text()
    assert 'path="/legal/privacy"' in txt
    assert 'path="/legal/terms"' in txt
    assert '<Navigate to="/privacy" replace />' in txt
    assert '<Navigate to="/terms" replace />' in txt


def test_legacy_forgot_password_redirects_to_reset():
    """The "Forgot password?" link in EngineerLanding always used
    `/forgot-password`. Keep that path alive as a redirect."""
    txt = _routes_text()
    assert 'path="/forgot-password"' in txt
    assert '<Navigate to="/reset-password" replace />' in txt


def test_legacy_engineer_parts_redirects_to_jobs():
    """`/svc/engineer/parts` redirects to the jobs list (parts are
    managed inline on each job)."""
    txt = _routes_text()
    assert 'path="/svc/engineer/parts"' in txt
    assert '<Navigate to="/svc/engineer/jobs" replace />' in txt


def test_developers_route_replaces_api_docs():
    """`/api-docs` collided with the Kubernetes `/api*` ingress rule.
    Confirm the developer-docs page is now at `/developers` and the
    legacy `/api-docs` path is a Navigate-alias (in case anyone
    bookmarks it from outside the app)."""
    txt = _routes_text()
    assert 'path="/developers"' in txt
    assert 'element={<ApiDocsPage />}' in txt.replace(" ", "").replace("\n", "") or 'element={<ApiDocsPage/>}' in txt.replace(" ", "")
    # legacy alias preserved
    assert 'path="/api-docs"' in txt
    assert '<Navigate to="/developers" replace />' in txt


def test_no_remaining_links_to_known_dead_paths():
    """No JS/JSX file outside AppRoutes should still link to the dead
    paths. AppRoutes itself is allowed because that's where the
    redirects live."""
    root = Path("/app/frontend/src")
    offenders: list[tuple[str, str]] = []
    DEAD_TARGETS = [
        '"/legal/privacy"', "'/legal/privacy'",
        '"/legal/terms"', "'/legal/terms'",
    ]
    for js in root.rglob("*.js"):
        if js.name == "AppRoutes.js":
            continue
        text = js.read_text(encoding="utf-8", errors="ignore")
        for target in DEAD_TARGETS:
            if target in text:
                offenders.append((str(js.relative_to(root)), target))
    assert not offenders, f"Still-linking to dead paths: {offenders}"


def test_footer_links_to_developers_not_api_docs():
    """Footer's developer-docs link must use the new `/developers`
    path so the K8s ingress doesn't intercept it as a backend route."""
    footer = Path("/app/frontend/src/components/shared/Footer.js").read_text(encoding="utf-8")
    assert 'to="/developers"' in footer
    # The legacy path must not be linked from anywhere — only
    # registered as a Navigate alias inside AppRoutes.
    assert 'to="/api-docs"' not in footer
