"""Iter 216h294 — `make pre-deploy` now depends on `make lint`.

The old `pre-deploy` target dropped straight into the shell script,
which in turn only linted files **changed in HEAD**. A stale
warning in a file the deployer didn't touch would slip through to
production. After h294 the Makefile-level dependency runs strict
ruff + ESLint over the whole tree first, then hands off.

Pins covered
------------
* `pre-deploy` target lists `lint` as a prerequisite
* `lint` target itself still chains all three sub-linters
* `make pre-deploy` aborts when ESLint or ruff is dirty
* `pre-deploy` is still in `.PHONY` (didn't get accidentally
  promoted to a file target)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

MAKEFILE = Path("/app/Makefile")


def _read() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


# ── Static Makefile pins ───────────────────────────────────────────


def test_pre_deploy_target_depends_on_lint():
    """The single most important pin — without this the deployer
    can ship lint-dirty code straight to production."""
    text = _read()
    # Match `pre-deploy:` followed by prerequisites — must list `lint`
    m = re.search(r"^pre-deploy:\s*(.*)$", text, re.MULTILINE)
    assert m, "pre-deploy target not found in Makefile"
    prereqs = m.group(1).split()
    assert "lint" in prereqs, f"pre-deploy is missing `lint` prerequisite (got: {prereqs!r})"


def test_lint_target_chains_all_three_linters():
    """make lint must still cover integrations + backend + frontend.
    Without this, depending on `lint` would be theatre."""
    text = _read()
    m = re.search(r"^lint:\s*(.*)$", text, re.MULTILINE)
    assert m, "lint target not found in Makefile"
    sub_linters = m.group(1).split()
    assert "lint-integrations" in sub_linters
    assert "lint-backend" in sub_linters
    assert "lint-frontend" in sub_linters


def test_pre_deploy_remains_phony():
    """If a `pre-deploy` file ever appears at the repo root, Make
    would skip the target. Pin it to .PHONY."""
    text = _read()
    phony_lines = [
        line for line in text.splitlines() if line.startswith(".PHONY:")
    ]
    assert phony_lines, ".PHONY declaration missing"
    joined = " ".join(phony_lines)
    assert "pre-deploy" in joined


def test_lint_backend_target_has_no_swallow():
    """Defence-in-depth: even with the dependency, a `|| true`
    on ruff would let dirty backends through. Pin we never
    re-introduce the swallow."""
    text = _read()
    m = re.search(r"^lint-backend:\s*\n([^\n]+)\n", text, re.MULTILINE)
    assert m, "lint-backend target body not found"
    body = m.group(1)
    assert "|| true" not in body, f"ruff swallow detected in lint-backend: {body!r}"


def test_lint_frontend_target_has_no_swallow():
    text = _read()
    m = re.search(r"^lint-frontend:\s*\n([^\n]+)\n", text, re.MULTILINE)
    assert m, "lint-frontend target body not found"
    body = m.group(1)
    assert "|| true" not in body, f"ESLint swallow detected in lint-frontend: {body!r}"


# ── Behaviour test — make actually wires the dependency ────────────


def test_make_dry_run_lists_lint_before_pre_deploy():
    """Run make in dry-run mode (`-n`) so we don't actually deploy.
    The dependency means make MUST mention the lint targets in the
    invocation order — `lint-backend` and `lint-frontend` must
    appear in the output."""
    result = subprocess.run(
        ["make", "-n", "pre-deploy"],
        cwd="/app",
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Combined stdout+stderr for inspection
    out = result.stdout + result.stderr
    # Even in dry-run mode, prerequisites are walked
    assert "ruff check" in out or "lint-backend" in out, (
        f"`make -n pre-deploy` did not walk lint-backend prerequisite. Output:\n{out}"
    )
    assert "eslint" in out.lower() or "lint-frontend" in out.lower(), (
        f"`make -n pre-deploy` did not walk lint-frontend prerequisite. Output:\n{out}"
    )
    # And the deploy script comes AFTER the linters — verify ordering
    deploy_idx = out.find("pre-deploy.sh")
    eslint_idx = out.lower().find("eslint")
    if deploy_idx > -1 and eslint_idx > -1:
        assert eslint_idx < deploy_idx, (
            "ESLint must run before pre-deploy.sh — make is invoking them in the wrong order"
        )
