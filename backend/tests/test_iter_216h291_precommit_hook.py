"""Iter 216h291 — pre-commit hook ESLint gate.

Pins the contents of the team's git pre-commit hook so a future
edit can't quietly drop the strict 0-warning gate or stop running
ESLint against staged JS/JSX. The hook itself is shell, so this
test runs as a static-string check against the file at:
``/app/.githooks/pre-commit`` plus the Makefile install target.
"""
from __future__ import annotations

from pathlib import Path

import pytest


HOOK_PATH = Path("/app/.githooks/pre-commit")
INSTALL_SCRIPT = Path("/app/scripts/install_hooks.sh")
MAKEFILE = Path("/app/Makefile")


@pytest.fixture(scope="module")
def hook_text() -> str:
    assert HOOK_PATH.exists(), f"pre-commit hook missing at {HOOK_PATH}"
    return HOOK_PATH.read_text(encoding="utf-8")


# ── Hook script content ────────────────────────────────────────────


def test_hook_script_is_executable():
    import os
    assert HOOK_PATH.is_file()
    mode = HOOK_PATH.stat().st_mode
    assert mode & 0o100, f"pre-commit hook is not executable (mode={oct(mode)})"
    assert os.access(HOOK_PATH, os.X_OK)


def test_hook_calls_eslint_with_max_warnings_zero(hook_text):
    """The single most important pin — without `--max-warnings 0` the
    hook would silently allow dark-mode-leakage warnings through."""
    assert "--max-warnings 0" in hook_text
    assert "eslint" in hook_text.lower()


def test_hook_lints_staged_js_jsx_only(hook_text):
    """Speed pin — the hook must filter to staged JS/JSX, not the
    whole `frontend/src` tree, otherwise developers will start
    using `--no-verify` to dodge the slowdown."""
    # Uses `git diff --cached --name-only` to get the staged set
    assert "git diff --cached --name-only" in hook_text
    # Filters down to JS/JSX in the frontend tree
    assert "frontend/src/" in hook_text
    assert "\\.(js|jsx)$" in hook_text


def test_hook_skips_cleanly_when_no_js_changes(hook_text):
    """If the commit only touches backend / docs / config, the JS
    section should print 'skipped' and not invoke ESLint at all."""
    assert "skipped" in hook_text.lower()
    # The skip branch must come BEFORE any ESLint invocation in the JS section
    skip_idx = hook_text.lower().find("skipped")
    eslint_idx = hook_text.find("yarn -s eslint")
    assert 0 < skip_idx < eslint_idx, "skip branch must short-circuit before ESLint runs"


def test_hook_failure_increments_errors_counter(hook_text):
    """Any ESLint failure must increment ERRORS so the final exit
    code is non-zero. Otherwise the gate is theatre."""
    # Find the JS lint block, then verify the failure branch increments ERRORS
    block_start = hook_text.find("Frontend lint (staged JS/JSX")
    assert block_start > -1
    # Look at the next 25 lines from there
    block = hook_text[block_start:block_start + 1200]
    assert "ERRORS=$((ERRORS + 1))" in block


def test_hook_still_runs_backend_ruff_and_secrets_scan(hook_text):
    """We tightened the ESLint section but mustn't regress the other
    checks the hook already enforced."""
    assert "ruff check" in hook_text
    assert "Secrets scan" in hook_text


def test_hook_documents_no_verify_escape_hatch(hook_text):
    """In an emergency the developer has to know how to bypass."""
    assert "--no-verify" in hook_text


# ── Install script + Makefile wiring ───────────────────────────────


def test_install_script_exists_and_targets_pre_commit():
    assert INSTALL_SCRIPT.exists(), f"installer missing at {INSTALL_SCRIPT}"
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "pre-commit" in text
    assert ".git/hooks" in text


def test_makefile_exposes_install_hooks_target():
    text = MAKEFILE.read_text(encoding="utf-8")
    # Listed in .PHONY
    assert "install-hooks" in text.split("\n", 1)[0] or "install-hooks" in text
    # Target body invokes the installer script
    assert "scripts/install_hooks.sh" in text


def test_makefile_help_advertises_install_hooks():
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "make install-hooks" in text
