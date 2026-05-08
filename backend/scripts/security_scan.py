#!/usr/bin/env python3
"""
Local security scanner — wraps Bandit (SAST) + pip-audit (CVEs) so engineers
can run one command before merging. Designed to be CI-friendly: exit code
is non-zero if either tool finds a high-severity issue.

Usage:
    python scripts/security_scan.py [--strict]

``--strict`` also fails on medium-severity findings.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return 127, f"tool not installed: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def scan_bandit(strict: bool) -> int:
    print("=== Bandit (SAST) ===")
    threshold = "-lll" if not strict else "-ll"  # -lll = HIGH only, -ll = MED+HIGH
    rc, out = run(["bandit", "-r", str(BACKEND), "-c", str(BACKEND / ".bandit.yml"), threshold])
    print(out)
    return rc


def scan_pip_audit() -> int:
    print("=== pip-audit (CVE scan) ===")
    rc, out = run(["pip-audit", "--strict"])
    print(out)
    return rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail on MED findings too")
    args = parser.parse_args()

    rc1 = scan_bandit(args.strict)
    rc2 = scan_pip_audit()

    final = max(rc1, rc2)
    if final == 0:
        print("✅ Security scan passed")
    else:
        print(f"❌ Security scan failed with rc={final}")
    return final


if __name__ == "__main__":
    sys.exit(main())
