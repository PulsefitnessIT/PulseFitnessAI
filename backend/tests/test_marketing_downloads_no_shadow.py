"""Regression: the marketing downloads router must NOT register a greedy
`/marketing/{slug}` catch-all, which previously shadowed the marketing app
routes (`/marketing/campaigns`, `/audiences`, `/templates`) and 404-ed them
platform-wide. It must instead expose one explicit route per whitelisted slug.
"""
from routes.marketing_downloads import router, DOWNLOADS


def _paths():
    return {r.path for r in router.routes}


def test_no_greedy_slug_catch_all():
    # A path param route like "/marketing/{slug}" would shadow sibling exact paths.
    assert not any("{" in p for p in _paths()), _paths()


def test_each_whitelisted_slug_has_explicit_route():
    paths = _paths()
    for slug in DOWNLOADS:
        assert f"/marketing/{slug}" in paths, f"missing explicit route for {slug}"
