"""Iter 216h282 — Engineer route consolidation.

Closes Gaps 3 + 7 from the BA audit:

* Gap 3 — TWO application pathways (public + logged-in-wizard) with
  divergent validation. Keep ONE: the public form at
  `/partners/engineers/apply`. The duplicate `PartnerApplyWizard`
  has been deleted entirely (the backend's `_resolve_or_create_partner`
  already de-dupes by email so a logged-in re-application is handled
  by the same endpoint).
* Gap 7 — multiple paths to the same content. Canonical map:

  | Concept                          | Canonical path                 |
  |----------------------------------|--------------------------------|
  | Find an engineer (customer)      | /engineer                      |
  | Engineer partner programme (mkt) | /partners/engineers            |
  | Apply to become a partner        | /partners/engineers/apply      |
  | Authed partner dashboard         | /partner-engineer              |

  Legacy paths are now `<Navigate>` aliases — `/engineers` →
  `/engineer`, `/partner-engineer/apply` → `/partners/engineers/apply`.

This file pins the redirect routes + scans the codebase to catch any
new link that points at the killed wizard path.
"""
from __future__ import annotations

from pathlib import Path

ROUTES_FILE = Path("/app/frontend/src/routes/AppRoutes.js")
WIZARD_FILE = Path("/app/frontend/src/pages/PartnerEngineer/PartnerApplyWizard.js")


def _routes() -> str:
    return ROUTES_FILE.read_text(encoding="utf-8")


def test_partner_engineer_apply_redirects_to_public_canonical():
    """`/partner-engineer/apply` must remain in the route table as a
    Navigate-alias pointing at the canonical public form. External
    bookmarks of the old URL must keep working."""
    txt = _routes()
    assert 'path="/partner-engineer/apply"' in txt
    assert '<Navigate to="/partners/engineers/apply" replace />' in txt


def test_engineers_plural_still_redirects_to_singular():
    """Existing redirect from the BA audit's link-fix iter must stay."""
    txt = _routes()
    assert 'path="/engineers"' in txt
    assert '<Navigate to="/engineer" replace />' in txt


def test_duplicate_wizard_file_deleted():
    """The duplicate logged-in apply wizard file must no longer exist."""
    assert not WIZARD_FILE.exists(), (
        f"{WIZARD_FILE} should have been deleted (Gap 3 from BA audit). "
        "All apply links route through /partners/engineers/apply now."
    )


def test_no_imports_of_deleted_wizard():
    """No JS/JSX file should still import the deleted PartnerApplyWizard."""
    root = Path("/app/frontend/src")
    offenders: list[str] = []
    for js in root.rglob("*.js"):
        text = js.read_text(encoding="utf-8", errors="ignore")
        if "PartnerApplyWizard" in text:
            # Allow comments mentioning the removal in AppRoutes.js
            if js.name == "AppRoutes.js" and "removed" in text.lower():
                continue
            offenders.append(str(js.relative_to(root)))
    assert not offenders, f"Still referencing deleted wizard: {offenders}"


def test_canonical_apply_link_is_the_only_active_target():
    """Inside source files, every active `Link to="/partner-engineer/apply"`
    must have been replaced with the canonical `/partners/engineers/apply`.
    AppRoutes.js itself is allowed to keep the path because the redirect
    lives there."""
    root = Path("/app/frontend/src")
    offenders: list[tuple[str, int]] = []
    for js in root.rglob("*.js"):
        if js.name == "AppRoutes.js":
            continue
        for n, line in enumerate(js.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "/partner-engineer/apply" in line and (' to="' in line or "to: '/partner-engineer/apply'" in line):
                offenders.append((str(js.relative_to(root)), n))
    assert not offenders, f"Still linking to legacy /partner-engineer/apply: {offenders}"
