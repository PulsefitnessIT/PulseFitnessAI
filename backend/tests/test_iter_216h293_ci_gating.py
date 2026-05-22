"""Iter 216h293 — CI workflow gates pinned.

The team has now cleaned every ESLint warning AND every ruff issue
locally (iters 216h289 + 216h292). The pre-commit hook enforces
this on developer laptops (iter 216h291). This test pins the
remaining piece — the GitHub-Actions CI workflow — so a future
edit can't quietly weaken the strict gate or downgrade the backend
test surface.

Pins covered
------------
* `ci.yml` ESLint step uses `--max-warnings 0` (NOT 99999)
* `ci.yml` backend-tests job runs `make regression` (NOT a single
  hand-picked test file)
* `quality-gate.yml` ESLint step still uses `--max-warnings 0`
* `quality-gate.yml` ruff step still runs (no `|| true` swallow)
* Both workflows fire on `pull_request` so checks gate the merge
"""
from __future__ import annotations

from pathlib import Path

import pytest

CI_YML = Path("/app/.github/workflows/ci.yml")
QG_YML = Path("/app/.github/workflows/quality-gate.yml")


@pytest.fixture(scope="module")
def ci_text() -> str:
    assert CI_YML.exists(), f"CI workflow missing at {CI_YML}"
    return CI_YML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def qg_text() -> str:
    assert QG_YML.exists(), f"quality-gate workflow missing at {QG_YML}"
    return QG_YML.read_text(encoding="utf-8")


# ── ci.yml ─────────────────────────────────────────────────────────


def test_ci_eslint_step_uses_strict_zero_warnings(ci_text):
    """The most important pin — `--max-warnings 99999` is literally
    the gate disabled. `--max-warnings 0` matches the local
    `make lint-frontend` target."""
    assert "--max-warnings 0" in ci_text
    assert "--max-warnings 99999" not in ci_text


def test_ci_backend_tests_job_runs_make_regression(ci_text):
    """Was a single hand-picked test file pre-h293; now runs the
    curated 511-test regression suite. Catches `--no-verify`
    commits that the pre-commit hook missed."""
    assert "make regression" in ci_text
    # The old single-file invocation must not survive
    assert "tests/test_xss_and_brand_urls.py -v" not in ci_text


def test_ci_runs_on_pull_request(ci_text):
    """The whole point — CI must gate PR merges, not just push events."""
    # YAML "pull_request:" key
    assert "pull_request:" in ci_text


def test_ci_runs_ruff(ci_text):
    """Ruff still runs and its `|| true` swallow was never present
    here — the local Makefile target is the one we tightened."""
    assert "ruff check backend" in ci_text


def test_ci_runs_secrets_scan(ci_text):
    """Defense in depth — gitleaks-style grep against AWS / Stripe /
    Twilio key prefixes."""
    assert "Detect hardcoded secrets" in ci_text
    assert "sk_live_" in ci_text
    assert "AKIA" in ci_text


# ── quality-gate.yml ───────────────────────────────────────────────


def test_quality_gate_eslint_uses_strict_zero(qg_text):
    """The sister workflow had the strict gate already — verify it
    didn't drift."""
    assert "--max-warnings 0" in qg_text


def test_quality_gate_ruff_step_has_no_swallow(qg_text):
    """`ruff check .` followed by `|| true` would silently let CI
    pass on a regression. Pin that we never add the swallow."""
    # Find the ruff line and verify nothing follows it on the same line
    for line in qg_text.splitlines():
        if "ruff check" in line and not line.strip().startswith("#"):
            assert "|| true" not in line, f"ruff swallow detected: {line!r}"


def test_quality_gate_runs_pytest_regression_dir(qg_text):
    """The h211 trust-recovery suite must keep gating PRs."""
    assert "tests/regression" in qg_text


def test_quality_gate_runs_on_pull_request(qg_text):
    assert "pull_request:" in qg_text


# ── Drift cross-check ──────────────────────────────────────────────


def test_workflows_pin_consistent_ruff_version(ci_text, qg_text):
    """Pinning ruff at different majors across workflows has caused
    mysterious "passes locally / fails in CI" before. Lock the
    pin here so a Dependabot PR can't drift one but not the other."""
    import re
    versions_ci = set(re.findall(r"ruff==([\d.]+)", ci_text))
    versions_qg = set(re.findall(r"ruff==([\d.]+)", qg_text))
    assert versions_ci, "ci.yml does not pin a ruff version"
    assert versions_qg, "quality-gate.yml does not pin a ruff version"
    assert versions_ci == versions_qg, (
        f"ruff version drift: ci.yml={versions_ci}, quality-gate.yml={versions_qg}"
    )
