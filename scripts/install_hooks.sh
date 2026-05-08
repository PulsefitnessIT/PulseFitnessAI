#!/usr/bin/env bash
# ============================================================================
# Install GymAxis AI git hooks
# Usage: ./scripts/install_hooks.sh
# ============================================================================
set -e

HOOK_DIR="/app/.git/hooks"
SOURCE_DIR="/app/.githooks"

if [ ! -d "$HOOK_DIR" ]; then
    echo "Error: .git/hooks directory not found. Are you in the repo root?"
    exit 1
fi

# Copy pre-commit hook
cp "$SOURCE_DIR/pre-commit" "$HOOK_DIR/pre-commit"
chmod +x "$HOOK_DIR/pre-commit"

echo "Git hooks installed successfully."
echo "  - pre-commit: ruff + ESLint + secrets scan"
echo ""
echo "To skip hooks on a commit: git commit --no-verify"
echo "To run full quality gate:  ./scripts/quality_gate.sh"
