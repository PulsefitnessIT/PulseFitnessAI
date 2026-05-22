"""Iter 216h297 — `make lint-health` weekly snapshot pin.

The script captures a current-state codebase health snapshot,
computes trend arrows vs last week, writes a Markdown report
(committable) + JSON sidecar (powers next week's trends), and
optionally fires a Resend email.

Pins covered
------------
* `count_eslint_warnings` parses the "X problems" footer
* `count_ruff_findings` sums --statistics output, falls back
  to the "Found N errors" trailer
* `count_directives` filters out node_modules / build / venv
* `count_backend_regression` parses the pytest summary line
* `_arrow` renders the right glyph for ↓ / ↑ / →
* `render_markdown` emits the headline metrics table + the
  complexity table + a "no previous snapshot" note on first run
* `_markdown_to_html` survives tables and headings (the email
  body is structured, not a code dump)
* `_previous_snapshot` skips today's own JSON sidecar
* Makefile exposes `lint-health` in `.PHONY` + `make help`
* Script is executable
"""
from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_PATH = Path("/app/scripts/lint_health_report.py")
MAKEFILE = Path("/app/Makefile")


def _load_module():
    spec = importlib.util.spec_from_file_location("lint_health_report", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_health_report"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_module()


@pytest.fixture
def isolated_report_dir(tmp_path, monkeypatch, script):
    """Redirect REPORT_DIR onto a fresh tmp_path so tests can't
    pollute /app/reports/ and don't depend on prior runs."""
    monkeypatch.setattr(script, "REPORT_DIR", tmp_path)
    return tmp_path


# ── ESLint summary parsing ─────────────────────────────────────────


def _stub_subprocess(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a CompletedProcess-like object for monkeypatching."""
    class _CP:
        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode
    return _CP()


def test_count_eslint_warnings_parses_footer(script, monkeypatch):
    fake_out = "src/foo.js\n  1:1  warning  test  rule\n\n4 problems (1 error, 3 warnings)"
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=fake_out))
    assert script.count_eslint_warnings() == 4


def test_count_eslint_warnings_returns_zero_when_clean(script, monkeypatch):
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=""))
    assert script.count_eslint_warnings() == 0


def test_count_eslint_warnings_returns_minus_one_on_failure(script, monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("yarn missing")
    monkeypatch.setattr(script.subprocess, "run", _boom)
    assert script.count_eslint_warnings() == -1


# ── Ruff statistics parsing ────────────────────────────────────────


def test_count_ruff_findings_sums_statistics(script, monkeypatch):
    fake_out = textwrap.dedent("""
       3   F401 unused-import
       2   E702 multiple-statements
       1   SIM117 nested-with
    """).strip()
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=fake_out))
    assert script.count_ruff_findings() == 6


def test_count_ruff_findings_falls_back_to_total_line(script, monkeypatch):
    """When --statistics produces no per-rule lines but the trailer
    says "Found 5 errors", we must still pick up the count."""
    fake_out = "All checks passed!"
    fake_err = "Found 5 errors."
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=fake_out, stderr=fake_err))
    # Note: without per-rule lines the function falls back to the
    # trailer search, returning 5
    assert script.count_ruff_findings() == 5


def test_count_ruff_findings_returns_zero_when_clean(script, monkeypatch):
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout="All checks passed!"))
    assert script.count_ruff_findings() == 0


# ── Directive counter ──────────────────────────────────────────────


def test_count_directives_skips_excluded_dirs(script, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.js").write_text("// eslint-disable-next-line\nconst x = 1;\n")
    nested = src / "node_modules" / "x"
    nested.mkdir(parents=True)
    (nested / "bad.js").write_text("// eslint-disable-next-line\n// eslint-disable-next-line\n")
    n = script.count_directives(
        pattern=r"eslint-disable-next-line",
        paths=[src],
        extensions=(".js",),
    )
    assert n == 1, "node_modules contents must be excluded"


def test_count_directives_finds_multiple_per_file(script, tmp_path):
    (tmp_path / "a.py").write_text("x = 1  # noqa\ny = 2  # noqa: E501\n")
    n = script.count_directives(pattern=r"#\s*noqa", paths=[tmp_path], extensions=(".py",))
    assert n == 2


# ── Backend regression parsing ─────────────────────────────────────


def test_count_backend_regression_parses_pytest_summary(script, monkeypatch):
    fake_out = "===== 547 passed, 14 skipped, 2 warnings in 11.99s ====="
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=fake_out))
    total, passed, skipped = script.count_backend_regression()
    assert (total, passed, skipped) == (561, 547, 14)


def test_count_backend_regression_handles_no_skipped(script, monkeypatch):
    fake_out = "===== 100 passed in 5.0s ====="
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout=fake_out))
    total, passed, skipped = script.count_backend_regression()
    assert (total, passed, skipped) == (100, 100, 0)


def test_count_backend_regression_returns_minus_one_on_unparseable(script, monkeypatch):
    monkeypatch.setattr(script.subprocess, "run",
                        lambda *a, **kw: _stub_subprocess(stdout="garbage"))
    assert script.count_backend_regression() == (-1, -1, -1)


# ── Trend arrow ────────────────────────────────────────────────────


def test_arrow_down_when_current_lower(script):
    assert "↓" in script._arrow(2, 5)
    assert "3 fewer" in script._arrow(2, 5)


def test_arrow_up_when_current_higher(script):
    assert "↑" in script._arrow(7, 5)
    assert "2 more" in script._arrow(7, 5)


def test_arrow_flat_when_unchanged(script):
    assert "→" in script._arrow(5, 5)


def test_arrow_dash_when_no_baseline(script):
    assert script._arrow(5, None) == "—"


def test_arrow_dash_when_metric_unparseable(script):
    """A negative current value (tooling failure) must not invent a fake trend."""
    assert script._arrow(-1, 5) == "—"


# ── Markdown rendering ─────────────────────────────────────────────


def _make_snap(script, **overrides):
    base = dict(
        captured_at="2026-05-22T08:00:00+00:00",
        iso_week="2026-W21",
        eslint_warnings=0,
        ruff_findings=0,
        eslint_disable_directives=162,
        noqa_directives=85,
        backend_regression_total=561,
        backend_regression_passed=547,
        backend_regression_skipped=14,
        top_complex_files=[
            {"file": "/app/backend/utils/churn_signals.py", "max_cc": 69, "worst_block": "detect"},
        ],
        notes=[],
    )
    base.update(overrides)
    return script.HealthSnapshot(**base)


def test_render_markdown_first_run_says_no_previous(script):
    snap = _make_snap(script)
    md = script.render_markdown(snap, prev=None)
    assert "Lint-health snapshot" in md
    assert "2026-W21" in md
    assert "No previous snapshot" in md
    # All 5 headline metrics show up
    assert "ESLint warnings" in md
    assert "ruff findings" in md
    assert "eslint-disable-next-line" in md
    assert "# noqa directives" in md
    assert "Backend tests passing" in md


def test_render_markdown_includes_trend_arrows_with_previous(script):
    snap = _make_snap(script, eslint_warnings=0)
    prev = _make_snap(script, eslint_warnings=3, captured_at="2026-05-15T08:00:00+00:00",
                       iso_week="2026-W20")
    md = script.render_markdown(snap, prev=prev)
    assert "Compared with the previous snapshot" in md
    assert "↓" in md
    assert "3 fewer" in md


def test_render_markdown_renders_complexity_table(script):
    snap = _make_snap(script)
    md = script.render_markdown(snap, prev=None)
    assert "Most complex files" in md
    assert "churn_signals.py" in md
    assert "69" in md


def test_render_markdown_emits_warning_block_on_tooling_failure(script):
    snap = _make_snap(script, backend_regression_total=-1)
    md = script.render_markdown(snap, prev=None)
    assert "Could not run `make regression`" in md


# ── HTML conversion ────────────────────────────────────────────────


def test_markdown_to_html_renders_table(script):
    md = textwrap.dedent("""
    | A | B |
    |---|---|
    | 1 | 2 |
    """).strip()
    html = script._markdown_to_html(md)
    assert "<table" in html
    assert "<th" in html
    assert "<td" in html
    # Separator row must NOT leak as a data row
    assert "---" not in html


def test_markdown_to_html_preserves_headings_and_lists(script):
    md = "# Title\n\n## Section\n\n- bullet one\n- bullet two\n"
    html = script._markdown_to_html(md)
    assert "<h2" in html and "Title" in html
    assert "<h3" in html and "Section" in html
    assert "bullet one" in html


# ── Previous-snapshot lookup ───────────────────────────────────────


def test_previous_snapshot_skips_todays_own_json(isolated_report_dir, script):
    today_path = isolated_report_dir / "lint-health-2026-W21.json"
    today_path.write_text(json.dumps({
        "captured_at": "2026-05-22T08:00:00+00:00", "iso_week": "2026-W21",
        "eslint_warnings": 0, "ruff_findings": 0,
        "eslint_disable_directives": 162, "noqa_directives": 85,
        "backend_regression_total": 561, "backend_regression_passed": 547,
        "backend_regression_skipped": 14, "top_complex_files": [], "notes": [],
    }))
    # Today filter compares the captured_at[:10] to today's date in UTC,
    # so plant a previous-day snapshot to find
    earlier = isolated_report_dir / "lint-health-2026-W20.json"
    earlier.write_text(json.dumps({
        "captured_at": "2026-05-15T08:00:00+00:00", "iso_week": "2026-W20",
        "eslint_warnings": 3, "ruff_findings": 2,
        "eslint_disable_directives": 170, "noqa_directives": 80,
        "backend_regression_total": 554, "backend_regression_passed": 540,
        "backend_regression_skipped": 14, "top_complex_files": [], "notes": [],
    }))
    # Patch today's date so the "skip today's own JSON" branch fires
    fake_today = type("FakeDate", (), {"isoformat": lambda self: "2026-05-22"})()
    with patch("lint_health_report.datetime") as fake_dt:
        fake_dt.now.return_value.date.return_value = fake_today
        prev = script._previous_snapshot()
    assert prev is not None
    assert prev.iso_week == "2026-W20"
    assert prev.eslint_warnings == 3


def test_previous_snapshot_returns_none_when_only_todays_present(isolated_report_dir, script):
    (isolated_report_dir / "lint-health-2026-W21.json").write_text(json.dumps({
        "captured_at": "2026-05-22T08:00:00+00:00", "iso_week": "2026-W21",
        "eslint_warnings": 0, "ruff_findings": 0,
        "eslint_disable_directives": 0, "noqa_directives": 0,
        "backend_regression_total": 0, "backend_regression_passed": 0,
        "backend_regression_skipped": 0, "top_complex_files": [], "notes": [],
    }))
    fake_today = type("FakeDate", (), {"isoformat": lambda self: "2026-05-22"})()
    with patch("lint_health_report.datetime") as fake_dt:
        fake_dt.now.return_value.date.return_value = fake_today
        assert script._previous_snapshot() is None


# ── Makefile + script-level wiring ─────────────────────────────────


def test_makefile_exposes_lint_health_target():
    text = MAKEFILE.read_text(encoding="utf-8")
    phony = next((line for line in text.splitlines() if line.startswith(".PHONY:")), "")
    assert "lint-health" in phony
    assert "scripts/lint_health_report.py" in text


def test_makefile_help_advertises_lint_health():
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "make lint-health" in text


def test_script_is_executable():
    import os
    assert SCRIPT_PATH.is_file()
    assert os.access(SCRIPT_PATH, os.X_OK)
