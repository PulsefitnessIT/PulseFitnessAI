#!/usr/bin/env bash
# ============================================================================
# GymAxis AI — Quality Gate
# Runs all code quality checks. Exit code 0 = all pass, non-zero = failures.
# Usage:
#   ./scripts/quality_gate.sh          # Full suite (lint + types + smoke)
#   ./scripts/quality_gate.sh --quick  # Lint only (no smoke test)
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

PASS=0
FAIL=0
WARN=0
QUICK_MODE=false

[[ "${1:-}" == "--quick" ]] && QUICK_MODE=true

section() { echo -e "\n${CYAN}${BOLD}=== $1 ===${NC}"; }
pass()    { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
fail()    { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); }
warn()    { echo -e "  ${YELLOW}WARN${NC} $1"; WARN=$((WARN + 1)); }

# ── 1. Backend Ruff Lint ────────────────────────────────────────────
section "Backend Lint (ruff)"
if cd /app/backend && ruff check . --config pyproject.toml --quiet 2>/dev/null; then
    pass "Zero ruff errors"
else
    RUFF_OUT=$(cd /app/backend && ruff check . --config pyproject.toml 2>&1 || true)
    ERROR_COUNT=$(echo "$RUFF_OUT" | grep -c "error\|E\|F\|W\|B\|SIM\|C90" || echo "?")
    fail "Ruff found issues ($ERROR_COUNT). Run: cd backend && ruff check . --config pyproject.toml"
    echo "$RUFF_OUT" | head -20
fi

# ── 2. Backend Type Hint Coverage ───────────────────────────────────
section "Backend Type Hints"
MISSING_HINTS=0
CHECKED_FILES=0

check_hints() {
    local file=$1
    local basename
    basename=$(basename "$file")
    # Skip test files and __init__
    [[ "$basename" == "__init__.py" || "$basename" == "conftest.py" ]] && return
    [[ "$file" == *"/tests/"* ]] && return

    CHECKED_FILES=$((CHECKED_FILES + 1))

    # Count public async def / def without return type hints
    local missing
    missing=$(grep -nE '^\s*(async )?def [a-z][a-zA-Z_]*\(' "$file" | grep -v '^\s*#' | grep -v '\->' | grep -vc '__' || true)

    if [ "$missing" -gt 0 ]; then
        MISSING_HINTS=$((MISSING_HINTS + missing))
        warn "$basename: $missing functions missing return type hints"
        # Show the offending lines
        grep -nE '^\s*(async )?def [a-z][a-zA-Z_]*\(' "$file" | grep -v '^\s*#' | grep -v '\->' | grep -v '__' | head -5 | while read -r line; do
            echo "       $line"
        done
    fi
}

# Check high-traffic files
for f in /app/backend/server.py /app/backend/utils/*.py /app/backend/routes/*.py; do
    [ -f "$f" ] && check_hints "$f"
done

if [ "$MISSING_HINTS" -eq 0 ]; then
    pass "All $CHECKED_FILES files have return type hints on public functions"
else
    warn "$MISSING_HINTS functions across $CHECKED_FILES files missing return types"
fi

# ── 3. Backend Hardcoded Secrets Check ──────────────────────────────
section "Hardcoded Secrets Scan"
SECRET_PATTERNS='password\s*=\s*["\x27][^"\x27]{4,}|api_key\s*=\s*["\x27]sk-|secret\s*=\s*["\x27][^"\x27]{8,}'
SECRETS_FOUND=0

for f in /app/backend/routes/*.py /app/backend/utils/*.py /app/backend/server.py; do
    [ -f "$f" ] || continue
    matches=$(grep -inE "$SECRET_PATTERNS" "$f" | grep -v 'environ\|os\.\|getenv\|\.get(' | grep -vc '^\s*#' || true)
    if [ "$matches" -gt 0 ]; then
        SECRETS_FOUND=$((SECRETS_FOUND + matches))
        fail "$(basename "$f"): $matches potential hardcoded secrets"
        grep -inE "$SECRET_PATTERNS" "$f" | grep -v 'environ\|os\.\|getenv\|\.get(' | grep -v '^\s*#' | head -3
    fi
done

if [ "$SECRETS_FOUND" -eq 0 ]; then
    pass "No hardcoded secrets detected"
fi

# ── 4. Frontend ESLint ──────────────────────────────────────────────
section "Frontend Lint (ESLint)"
cd /app/frontend
if npx eslint src/ --quiet 2>/dev/null; then
    pass "Zero ESLint errors"
else
    ESLINT_OUT=$(npx eslint src/ 2>&1 || true)
    ERROR_COUNT=$(echo "$ESLINT_OUT" | grep -c "error" || echo "?")
    WARN_COUNT=$(echo "$ESLINT_OUT" | grep -c "warning" || echo "0")
    if [ "$ERROR_COUNT" -gt 0 ] 2>/dev/null; then
        fail "ESLint found $ERROR_COUNT errors, $WARN_COUNT warnings"
    else
        warn "ESLint: $WARN_COUNT warnings (0 errors)"
    fi
    echo "$ESLINT_OUT" | tail -10
fi
cd /app

# ── 5. Unused Imports (Backend) ─────────────────────────────────────
section "Unused Imports (Backend)"
UNUSED=$(cd /app/backend && ruff check . --config pyproject.toml --select F401 --quiet 2>&1 || true)
if [ -z "$UNUSED" ]; then
    pass "No unused imports"
else
    UNUSED_COUNT=$(echo "$UNUSED" | wc -l)
    fail "$UNUSED_COUNT unused imports found"
    echo "$UNUSED" | head -10
fi

# ── 6. API Smoke Test ──────────────────────────────────────────────
if [ "$QUICK_MODE" = false ]; then
    section "API Smoke Test"
    API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)

    smoke_test() {
        local method=$1 url=$2 label=$3 data=${4:-}
        local status
        if [ -n "$data" ]; then
            status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" -H "Content-Type: application/json" -d "$data" --max-time 10 2>/dev/null || echo "000")
        else
            status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" -H "Authorization: Bearer $TOKEN" --max-time 10 2>/dev/null || echo "000")
        fi
        if [ "$status" = "200" ]; then
            pass "$label ($status)"
        else
            fail "$label (HTTP $status)"
        fi
    }

    # Login to get token
    LOGIN_RESP=$(curl -s -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" \
        -d "{\"email\":\"admin@gymaxisai.com\",\"password\":\"MasterAdmin123!\"}" --max-time 10 2>/dev/null || echo "{}")
    TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")

    if [ -z "$TOKEN" ]; then
        fail "Could not authenticate — skipping endpoint tests"
    else
        pass "Authentication successful"
        smoke_test GET "$API_URL/api/auth/me" "/auth/me"
        smoke_test GET "$API_URL/api/equipment" "/equipment"
        smoke_test GET "$API_URL/api/issues" "/issues"
        smoke_test GET "$API_URL/api/capex/defaults" "/capex/defaults"
        smoke_test GET "$API_URL/api/organization" "/organization"
        smoke_test GET "$API_URL/api/organization/staff" "/organization/staff"
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD} Quality Gate Results${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  ${GREEN}PASS: $PASS${NC}"
[ "$WARN" -gt 0 ] && echo -e "  ${YELLOW}WARN: $WARN${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}FAIL: $FAIL${NC}"
echo -e "${BOLD}============================================${NC}"

if [ "$FAIL" -gt 0 ]; then
    echo -e "\n${RED}${BOLD}Quality gate FAILED — $FAIL check(s) need attention${NC}"
    exit 1
else
    echo -e "\n${GREEN}${BOLD}Quality gate PASSED${NC}"
    exit 0
fi
