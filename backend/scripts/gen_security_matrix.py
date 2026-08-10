"""Generate the platform API security matrix / inventory (security §36 & §38).

Walks the live FastAPI app, and for every /api route records: path, methods,
whether it is authenticated (an auth dependency is present anywhere in its
dependency tree), the auth callables involved, and whether it mutates state.

Outputs:
  * security_matrix.json         — full API inventory (every endpoint + policy)
  * security_matrix_baseline.json — the curated allow-list of INTENTIONALLY
    public routes. The CI test (tests/test_auth_matrix.py) fails the build if a
    NEW unauthenticated route appears that is not in this baseline.

Run:  cd /app/backend && python scripts/gen_security_matrix.py [--write-baseline]
"""
from __future__ import annotations

import json
import os
import re
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

MATRIX_PATH = os.path.join(BACKEND_DIR, "security_matrix.json")
BASELINE_PATH = os.path.join(BACKEND_DIR, "security_matrix_baseline.json")

# A dependency callable is treated as an auth/identity boundary if its name
# matches any of these. Deliberately broad — a route with ANY of these in its
# dependency tree is considered authenticated.
AUTH_NAME_RE = re.compile(
    r"(get_current_user|get_optional_user|get_crm_user|current_member|"
    r"master_admin|mod_site|supplier.*session|orbit4_admin|ops_role|"
    r"require_[a-z_]+|_require_[a-z_]+|get_[a-z_]*_user|_auth|verify_[a-z_]*token|"
    r"verify_api_key|api_key|require_mfa|require_step_up|dealer_session|engineer_[a-z_]*)",
    re.IGNORECASE,
)

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _collect_auth_callables(dependant, seen=None):
    """Recursively gather the names of every callable in a route's dependency tree."""
    if seen is None:
        seen = set()
    names = set()
    call = getattr(dependant, "call", None)
    if call is not None:
        nm = getattr(call, "__name__", None) or repr(call)
        names.add(nm)
    for sub in getattr(dependant, "dependencies", []) or []:
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        names |= _collect_auth_callables(sub, seen)
    return names


def build_matrix():
    from server import app  # imports the fully-wired app

    entries = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or not path.startswith("/api"):
            continue
        methods = sorted(m for m in methods if m not in ("HEAD", "OPTIONS"))
        if not methods:
            continue
        dep = getattr(route, "dependant", None)
        dep_names = _collect_auth_callables(dep) if dep is not None else set()
        auth_calls = sorted(n for n in dep_names if AUTH_NAME_RE.search(n or ""))
        # get_optional_user allows anonymous access — not a hard boundary.
        hard_auth = [c for c in auth_calls if "optional" not in c.lower()]
        entries.append({
            "path": path,
            "methods": methods,
            "authenticated": bool(hard_auth),
            "auth_dependencies": auth_calls,
            "mutating": any(m in MUTATING for m in methods),
            "endpoint": getattr(getattr(route, "endpoint", None), "__name__", None),
        })
    entries.sort(key=lambda e: e["path"])
    return entries


def unprotected(entries):
    """Routes with NO hard auth dependency (candidate public/gap routes)."""
    return sorted(
        {e["path"] for e in entries if not e["authenticated"]}
    )


if __name__ == "__main__":
    entries = build_matrix()
    with open(MATRIX_PATH, "w") as f:
        json.dump({"count": len(entries), "endpoints": entries}, f, indent=2)
    pub = unprotected(entries)
    print(f"Total /api endpoints: {len(entries)}")
    print(f"Unauthenticated (public/gap candidates): {len(pub)}")
    if "--write-baseline" in sys.argv:
        with open(BASELINE_PATH, "w") as f:
            json.dump({"public_routes": pub}, f, indent=2)
        print(f"Wrote baseline: {BASELINE_PATH} ({len(pub)} public routes)")
