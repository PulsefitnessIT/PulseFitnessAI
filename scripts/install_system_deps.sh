#!/usr/bin/env bash
# System-level dependencies required by the GymAxis backend.
# Run this once per container (idempotent). The preview environment may
# spin up fresh containers that lack these — run this from anywhere with
# root to restore the platform to a healthy state.
#
# Usage:
#   bash /app/scripts/install_system_deps.sh
#
# Dependencies:
#   libmagic1 — required by python-magic for upload MIME detection
#               (/api/health/deep reports file_validation=down without it).
#   mongodb-mongosh — optional; used only by a handful of integration tests
#                     (we silently skip if absent).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must be run as root (use sudo)." >&2
    exit 1
fi

echo "[deps] Installing libmagic1…"
apt-get update -qq
apt-get install -y --no-install-recommends libmagic1
ldconfig

echo "[deps] Verifying libmagic from Python…"
python3 -c "import magic; print('  libmagic →', magic.from_buffer(b'%PDF-1.4\\n'))"

echo "[deps] Done."
