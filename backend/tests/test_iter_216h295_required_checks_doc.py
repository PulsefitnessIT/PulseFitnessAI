"""Iter 216h295 — `docs/CI_REQUIRED_CHECKS.md` job-name drift pins.

Closes the documentation half of the CI hardening saga. The doc is
a paste-to-PR guide for a teammate to flip "Required" on each CI
job in GitHub branch protection. The risk: a future workflow
rename (or job-name typo in `name:`) silently breaks the doc, and
the teammate ends up unable to find the check in GitHub's
dropdown.

This test parses the two workflow YAMLs and asserts each job's
`name:` value appears verbatim in the doc. If anyone renames a
job, the test fails until the doc is updated.

Pins covered
------------
* The doc file exists at the documented path
* Every `jobs.<id>.name` from `ci.yml` is present verbatim
* Every `jobs.<id>.name` from `quality-gate.yml` is present
  verbatim (including the special-cased `pip-audit` ID-only job)
* The doc explains the "no dropdown until the check has run"
  GitHub gotcha
* The doc references the four hardening iters that produced the
  CI surface so the historical context isn't lost
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

DOC = Path("/app/docs/CI_REQUIRED_CHECKS.md")
CI_YML = Path("/app/.github/workflows/ci.yml")
QG_YML = Path("/app/.github/workflows/quality-gate.yml")


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), f"required-checks doc missing at {DOC}"
    return DOC.read_text(encoding="utf-8")


def _job_display_names(yml_path: Path) -> dict[str, str]:
    """Return ``{job_id: display_name}`` for every job in the workflow.
    Falls back to the job id when no `name:` is set (GitHub's own
    behaviour)."""
    with yml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    jobs = data.get("jobs", {})
    return {jid: (j.get("name") or jid) for jid, j in jobs.items()}


# ── Doc structure ──────────────────────────────────────────────────


def test_required_checks_doc_exists_at_expected_path():
    assert DOC.is_file()
    assert DOC.suffix == ".md"


def test_doc_calls_out_dropdown_first_run_gotcha(doc_text):
    """The single most common "this isn't working" support thread
    on GitHub branch protection — the dropdown stays empty until
    the workflow has run at least once. Doc must mention this."""
    lower = doc_text.lower()
    assert "dropdown" in lower or "search" in lower
    # Specifically must say the check needs to have run at least once
    assert "run" in lower
    assert any(
        phrase in lower
        for phrase in ("at least one pr", "at least once", "no-op commit", "first run", "after it has run")
    ), "doc must explain GitHub's empty-dropdown-until-first-run quirk"


def test_doc_references_hardening_iters(doc_text):
    """The doc lives at the end of a 4-iter chain (h291 → h294).
    Reference at least the boundary iters so the historical
    context survives a search."""
    assert "h291" in doc_text
    assert "h294" in doc_text


def test_doc_links_makefile_and_pre_commit_companion(doc_text):
    """Sister docs that a confused teammate would naturally want
    to read alongside this one."""
    assert "Makefile" in doc_text
    assert "PRE_COMMIT.md" in doc_text


# ── Workflow job-name drift pins ───────────────────────────────────


def test_doc_lists_every_ci_yml_job_name(doc_text):
    names = _job_display_names(CI_YML)
    assert names, "ci.yml has no jobs?"
    for jid, display in names.items():
        assert display in doc_text, (
            f"ci.yml job `{jid}` (display: {display!r}) is not listed in "
            f"the required-checks doc — likely a rename drift"
        )


def test_doc_lists_every_quality_gate_job_name(doc_text):
    names = _job_display_names(QG_YML)
    assert names, "quality-gate.yml has no jobs?"
    for jid, display in names.items():
        assert display in doc_text, (
            f"quality-gate.yml job `{jid}` (display: {display!r}) is not "
            f"listed in the required-checks doc — likely a rename drift"
        )


def test_doc_distinguishes_the_two_source_workflows(doc_text):
    """A maintainer needs to know which file each name comes from
    when debugging a missing check. The doc must reference both
    workflow filenames explicitly."""
    assert "ci.yml" in doc_text
    assert "quality-gate.yml" in doc_text
