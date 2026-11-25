#!/usr/bin/env bash
# Reproducible backend install for CI.
# emergentintegrations is served from Emergent's public package index (no credentials) and pins
# openai==1.99.9, while the app pins openai==2.24.0 (the version the running platform uses).
# Install the app's pinned set first, then emergentintegrations without re-resolving its deps —
# the same state as the working Emergent environment.
set -euo pipefail
cd "$(dirname "$0")/.."
EI_INDEX="https://d33sy5i8bnduwe.cloudfront.net/simple/"
grep -v '^emergentintegrations==' requirements.txt > /tmp/requirements-ci.txt
pip install -r /tmp/requirements-ci.txt
pip install --no-deps --extra-index-url "$EI_INDEX" "$(grep '^emergentintegrations==' requirements.txt)"
python -c "import emergentintegrations, openai, fastapi; print('backend deps ok', openai.__version__)"
