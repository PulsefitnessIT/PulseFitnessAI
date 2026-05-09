#!/usr/bin/env bash
# Backend security + lint baseline check.
# Run from repo root or backend dir. Exits non-zero if any new High/Medium
# bandit issue or any ruff error is introduced.
#
# Usage:
#   bash backend/scripts/security-scan.sh
#
# Baseline (last verified):
#   bandit:  0 High, 0 Medium, 94 Low (all `try/except/pass` patterns,
#            reviewed and considered intentional in storage paths).
#   ruff:    All checks passed.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> ruff (style + bug-bear + complexity)"
ruff check .

echo
echo "==> bandit (security)"
# -ll filters Low severity, so we only fail on Medium+ regressions.
bandit -c pyproject.toml -r . -ll

echo
echo "All security + lint checks passed."
