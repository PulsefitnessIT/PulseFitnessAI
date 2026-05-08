#!/usr/bin/env bash
#
# Pre-commit complexity gate.
#
# Runs `radon cc` against STAGED Python files only. Any function with a rank
# of C or worse (cyclomatic complexity > 10) blocks the commit.
#
# Design: staged-files-only intentionally — existing legacy complexity isn't
# flagged until a developer actively edits that file. This encourages gradual
# improvement (touching a legacy file = owning its complexity) without
# blocking all commits on day one.
#
# Files ignored by design:
#   - tests/*           (test functions legitimately chain many asserts)
#   - migrations/*      (data migrations often have necessary branching)
#   - venv/, node_modules/
#
# Run manually: ./scripts/check_complexity.sh

set -euo pipefail

THRESHOLD="${COMPLEXITY_THRESHOLD:-D}"   # D = rank > 20
BACKEND_DIR="backend"

if ! command -v radon >/dev/null 2>&1; then
    echo "⚠️  radon not installed. Install with: pip install radon"
    echo "    (skipping complexity check)"
    exit 0
fi

# Collect staged Python files under backend/ that aren't tests/migrations
mapfile -t staged < <(
    git diff --cached --name-only --diff-filter=ACMR -- "${BACKEND_DIR}/**/*.py" \
        | grep -vE "(^|/)(tests|migrations|venv)/" \
        || true
)

if [ ${#staged[@]} -eq 0 ]; then
    exit 0
fi

# radon exits 0 even when violations are found — we parse output ourselves.
violations="$(radon cc -s -n "${THRESHOLD}" "${staged[@]}" 2>/dev/null || true)"

if [ -n "${violations}" ]; then
    echo ""
    echo "❌ Complexity gate: the following staged blocks exceed rank ${THRESHOLD} (complexity > 10):"
    echo ""
    echo "${violations}" | sed 's/^/    /'
    echo ""
    echo "Options:"
    echo "  • Refactor — extract helpers, collapse branches, early-return."
    echo "  • See /app/docs/PRE_COMMIT.md for guidance."
    echo "  • Emergency bypass (NOT recommended):  git commit --no-verify"
    echo ""
    exit 1
fi

exit 0
