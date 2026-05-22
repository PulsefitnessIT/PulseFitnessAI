#!/usr/bin/env python3
"""lint_health_report.py — Iter 216h297

Weekly codebase-health snapshot. Designed to be run by a cron job
(or a scheduled CI workflow) every Monday morning.

Captures the **current** state of the repo:
  • ESLint warning count (target: 0)
  • ruff finding count (target: 0)
  • Backend regression test count + pass status
  • `eslint-disable-next-line` directive count (lint-debt indicator)
  • `# noqa` directive count (lint-debt indicator)
  • Top 5 most complex files by Xenon's letter grade

…and trends each metric vs last week's snapshot (↑ ↓ →).

Output: a Markdown report at `/app/reports/lint-health-YYYY-WW.md`
plus a JSON sidecar (`.json`) holding the raw metrics so next
week's run can compute deltas.

When `LINT_HEALTH_NOTIFY_EMAIL` is configured the report is also
delivered via the existing Resend integration.

Why a current-state snapshot vs. event-driven "regressions caught"?
  We have no persistent telemetry pipe between the pre-commit hook
  (laptop) and the GitHub-Actions CI run (cloud). Building one was
  scoped against — see iter 216h297 PRD entry. A snapshot delivers
  90% of the operator value with 0% of the infra cost.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/app")
REPORT_DIR = REPO_ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


@dataclass
class HealthSnapshot:
    captured_at: str
    iso_week: str            # e.g. "2026-W08"
    eslint_warnings: int
    ruff_findings: int
    eslint_disable_directives: int
    noqa_directives: int
    backend_regression_total: int
    backend_regression_passed: int
    backend_regression_skipped: int
    top_complex_files: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── Metric collectors ──────────────────────────────────────────────


def count_eslint_warnings() -> int:
    """Run ESLint over the whole frontend tree and count the
    "X problems (Y errors, Z warnings)" footer. Returns -1 on
    tooling failure so the trend arrow can show a question mark
    rather than a misleading zero."""
    try:
        r = subprocess.run(
            ["yarn", "-s", "eslint", "src", "--ext", ".js,.jsx", "--max-warnings", "999999"],
            cwd=REPO_ROOT / "frontend",
            capture_output=True,
            text=True,
            timeout=180,
        )
        for line in (r.stdout + "\n" + r.stderr).splitlines():
            m = re.search(r"(\d+) problems? \((\d+) errors?, (\d+) warnings?\)", line)
            if m:
                return int(m.group(2)) + int(m.group(3))
        # No "X problems" line means clean
        return 0
    except Exception:  # noqa: BLE001
        return -1


def count_ruff_findings() -> int:
    """ruff exits non-zero when findings exist. Use --statistics so
    we can sum the per-rule counts without relying on the exit code."""
    try:
        r = subprocess.run(
            ["ruff", "check", ".", "--statistics"],
            cwd=REPO_ROOT / "backend",
            capture_output=True,
            text=True,
            timeout=60,
        )
        total = 0
        for line in r.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+\w+", line)
            if m:
                total += int(m.group(1))
        # Fallback: parse the "Found N errors" trailer
        if total == 0:
            for line in r.stdout.splitlines() + r.stderr.splitlines():
                m = re.search(r"Found (\d+) errors?", line)
                if m:
                    return int(m.group(1))
        return total
    except Exception:  # noqa: BLE001
        return -1


def count_directives(pattern: str, paths: list[Path], extensions: tuple[str, ...]) -> int:
    """Count occurrences of ``pattern`` across the given file
    extensions. Used for both `eslint-disable-next-line` and
    `# noqa` lint-debt indicators."""
    total = 0
    rx = re.compile(pattern)
    for root in paths:
        for ext in extensions:
            for fp in root.rglob(f"*{ext}"):
                # Skip node_modules, build, dist
                parts = set(fp.parts)
                if parts & {"node_modules", "build", "dist", ".venv", "venv"}:
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                total += len(rx.findall(text))
    return total


def count_eslint_disable_directives() -> int:
    return count_directives(
        pattern=r"eslint-disable-next-line",
        paths=[REPO_ROOT / "frontend" / "src"],
        extensions=(".js", ".jsx", ".ts", ".tsx"),
    )


def count_noqa_directives() -> int:
    return count_directives(
        pattern=r"#\s*noqa",
        paths=[REPO_ROOT / "backend" / "routes",
               REPO_ROOT / "backend" / "utils",
               REPO_ROOT / "backend" / "models"],
        extensions=(".py",),
    )


def count_backend_regression() -> tuple[int, int, int]:
    """Run `make regression` and parse the pytest summary line.
    Returns (total, passed, skipped). Returns (-1, -1, -1) on
    tooling failure so the report can flag it."""
    try:
        r = subprocess.run(
            ["make", "regression"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        # pytest prints e.g. "547 passed, 14 skipped, 2 warnings in 11.99s"
        m = re.search(r"(\d+) passed(?:, (\d+) skipped)?", r.stdout + r.stderr)
        if not m:
            return -1, -1, -1
        passed = int(m.group(1))
        skipped = int(m.group(2) or 0)
        total = passed + skipped
        return total, passed, skipped
    except Exception:  # noqa: BLE001
        return -1, -1, -1


def top_complex_files(limit: int = 5) -> list[dict]:
    """Use radon (xenon's underlying engine) to rank the top-N most
    complex Python files by their max cyclomatic complexity score."""
    try:
        r = subprocess.run(
            ["radon", "cc", "backend/routes", "backend/utils",
             "backend/models", "-s", "-j"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
        rows: list[tuple[str, int, str]] = []
        for fp, blocks in data.items():
            if not isinstance(blocks, list):
                continue
            max_cc = max((b.get("complexity", 0) for b in blocks), default=0)
            top_block = max(blocks, key=lambda b: b.get("complexity", 0)) if blocks else None
            top_name = top_block.get("name") if top_block else "—"
            rows.append((fp, max_cc, top_name))
        rows.sort(key=lambda r: -r[1])
        return [
            {"file": fp, "max_cc": cc, "worst_block": name}
            for fp, cc, name in rows[:limit]
        ]
    except Exception:  # noqa: BLE001
        return []


# ── Trend computation ──────────────────────────────────────────────


def _previous_snapshot() -> HealthSnapshot | None:
    """Find the most recent JSON sidecar that isn't the one we're
    about to write (i.e. captured before today). Used to compute
    week-over-week deltas."""
    today = datetime.now(timezone.utc).date().isoformat()
    candidates = sorted(REPORT_DIR.glob("lint-health-*.json"), reverse=True)
    for fp in candidates:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("captured_at", "")[:10] == today:
            continue
        return HealthSnapshot(**{k: v for k, v in data.items()
                                  if k in HealthSnapshot.__dataclass_fields__})
    return None


def _arrow(current: int, previous: int | None) -> str:
    if previous is None or current < 0:
        return "—"
    if current < previous:
        return f"↓ ({previous - current} fewer)"
    if current > previous:
        return f"↑ ({current - previous} more)"
    return "→ (no change)"


# ── Markdown rendering ─────────────────────────────────────────────


def render_markdown(snap: HealthSnapshot, prev: HealthSnapshot | None) -> str:
    headline_metrics = [
        ("ESLint warnings",       snap.eslint_warnings,       prev.eslint_warnings       if prev else None),
        ("ruff findings",         snap.ruff_findings,         prev.ruff_findings         if prev else None),
        ("eslint-disable-next-line",
                                  snap.eslint_disable_directives,
                                  prev.eslint_disable_directives if prev else None),
        ("# noqa directives",     snap.noqa_directives,       prev.noqa_directives       if prev else None),
        ("Backend tests passing", snap.backend_regression_passed,
                                  prev.backend_regression_passed if prev else None),
    ]

    lines: list[str] = []
    lines.append(f"# GymAxis · Lint-health snapshot · {snap.iso_week}")
    lines.append("")
    lines.append(f"_Captured at {snap.captured_at}._")
    lines.append("")
    if prev:
        lines.append(f"Compared with the previous snapshot from "
                     f"`{prev.iso_week}` ({prev.captured_at[:10]}).")
    else:
        lines.append("_No previous snapshot found — first run, no trends yet._")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Now | Trend |")
    lines.append("|---|---:|---|")
    for name, current, previous in headline_metrics:
        cur_str = "?" if current < 0 else str(current)
        lines.append(f"| {name} | {cur_str} | {_arrow(current, previous)} |")
    lines.append("")

    lines.append("## Backend regression suite")
    lines.append("")
    if snap.backend_regression_total < 0:
        lines.append("> ⚠️  Could not run `make regression`. Investigate.")
    else:
        lines.append(f"- **{snap.backend_regression_passed}** tests passed")
        lines.append(f"- {snap.backend_regression_skipped} skipped")
        lines.append(f"- {snap.backend_regression_total} total")
    lines.append("")

    lines.append("## Most complex files (cyclomatic complexity)")
    lines.append("")
    if not snap.top_complex_files:
        lines.append("_radon didn't return data this run._")
    else:
        lines.append("| File | Max CC | Worst block |")
        lines.append("|---|---:|---|")
        for row in snap.top_complex_files:
            short = row["file"].replace("/app/", "")
            lines.append(f"| `{short}` | {row['max_cc']} | `{row['worst_block']}` |")
    lines.append("")

    if snap.notes:
        lines.append("## Notes")
        lines.append("")
        for note in snap.notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Auto-generated by `make lint-health` · iter 216h297")
    return "\n".join(lines)


# ── Email delivery (optional) ──────────────────────────────────────


async def _maybe_email(subject: str, html_body: str) -> bool:
    recipient = os.environ.get("LINT_HEALTH_NOTIFY_EMAIL")
    if not recipient:
        return False
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        from utils.email import send_email
    except Exception as exc:  # pragma: no cover — environmental
        print(f"!  notify email skipped — backend imports unavailable: {exc}",
              file=sys.stderr)
        return False
    return await send_email(recipient, subject, html_body)


def _markdown_to_html(md: str) -> str:
    """Tiny inline markdown→HTML for the Resend body. Avoids adding
    a `markdown` dependency just for this; the grammar is simple."""
    html_lines: list[str] = ['<div style="font-family:-apple-system,sans-serif;max-width:760px;">']
    in_table = False
    table_buffer: list[str] = []

    def flush_table():
        nonlocal in_table, table_buffer
        if not table_buffer:
            return
        rows = []
        for i, raw in enumerate(table_buffer):
            cells = [c.strip() for c in raw.strip("|").split("|")]
            if i == 1 and all(set(c) <= set("-: ") for c in cells):
                continue   # separator row
            tag = "th" if i == 0 else "td"
            rows.append(
                "<tr>" + "".join(
                    f'<{tag} style="padding:6px 10px;border-bottom:1px solid #E5E7EB;font-size:13px;text-align:left;">{c}</{tag}>'
                    for c in cells
                ) + "</tr>"
            )
        html_lines.append('<table style="border-collapse:collapse;margin:6px 0 14px;">' + "".join(rows) + '</table>')
        table_buffer = []
        in_table = False

    for line in md.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("|"):
            in_table = True
            table_buffer.append(stripped)
            continue
        if in_table:
            flush_table()
        if stripped.startswith("# "):
            html_lines.append(f'<h2 style="margin:14px 0 6px;color:#0F172A;">{stripped[2:]}</h2>')
        elif stripped.startswith("## "):
            html_lines.append(f'<h3 style="margin:12px 0 4px;color:#1F2937;font-size:14px;">{stripped[3:]}</h3>')
        elif stripped.startswith("- "):
            html_lines.append(f'<div style="font-size:13px;color:#374151;margin:2px 0;">• {stripped[2:]}</div>')
        elif stripped.startswith(">"):
            html_lines.append(f'<blockquote style="border-left:3px solid #F59E0B;background:#FEF3C7;padding:8px 12px;color:#78350F;font-size:13px;">{stripped[1:].strip()}</blockquote>')
        elif stripped == "---":
            html_lines.append('<hr style="border:0;border-top:1px solid #E5E7EB;margin:16px 0;" />')
        elif stripped:
            html_lines.append(f'<p style="font-size:13px;color:#374151;margin:4px 0;">{stripped}</p>')
    flush_table()
    html_lines.append("</div>")
    return "".join(html_lines)


# ── Entrypoint ─────────────────────────────────────────────────────


def collect_snapshot() -> HealthSnapshot:
    """Pure data-collection helper — extracted so the regression
    test can call it without going through the CLI."""
    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    eslint = count_eslint_warnings()
    ruff = count_ruff_findings()
    eslint_disables = count_eslint_disable_directives()
    noqas = count_noqa_directives()
    total, passed, skipped = count_backend_regression()
    top = top_complex_files()
    notes: list[str] = []
    if eslint < 0:
        notes.append("ESLint did not produce a parseable summary line — tooling check needed.")
    if ruff < 0:
        notes.append("ruff did not produce a parseable summary — tooling check needed.")
    if total < 0:
        notes.append("`make regression` could not be parsed — tooling check needed.")
    return HealthSnapshot(
        captured_at=now.isoformat(),
        iso_week=week_label,
        eslint_warnings=eslint,
        ruff_findings=ruff,
        eslint_disable_directives=eslint_disables,
        noqa_directives=noqas,
        backend_regression_total=total,
        backend_regression_passed=passed,
        backend_regression_skipped=skipped,
        top_complex_files=top,
        notes=notes,
    )


def write_report(snap: HealthSnapshot) -> tuple[Path, Path]:
    """Write the markdown + JSON sidecar. Returns the (md, json)
    paths so the caller can echo them."""
    week_slug = snap.iso_week
    md_path = REPORT_DIR / f"lint-health-{week_slug}.md"
    json_path = REPORT_DIR / f"lint-health-{week_slug}.json"
    prev = _previous_snapshot()
    md_path.write_text(render_markdown(snap, prev), encoding="utf-8")
    json_path.write_text(json.dumps(asdict(snap), indent=2), encoding="utf-8")
    return md_path, json_path


async def main() -> int:
    snap = collect_snapshot()
    md_path, json_path = write_report(snap)
    print(f"✓ Wrote {md_path.relative_to(REPO_ROOT)}")
    print(f"✓ Wrote {json_path.relative_to(REPO_ROOT)}")
    print()
    print(md_path.read_text(encoding="utf-8"))
    subject = f"[lint-health] {snap.iso_week} · ESLint:{snap.eslint_warnings} · ruff:{snap.ruff_findings}"
    html = _markdown_to_html(md_path.read_text(encoding="utf-8"))
    if await _maybe_email(subject, html):
        print("✓ Resend email dispatched")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
