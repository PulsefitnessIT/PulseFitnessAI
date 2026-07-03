"""Guard: no BLOCKING calls at module-import scope in route modules.

Why this exists
---------------
A production crash-loop (Jul 2026) was traced to ``routes/admin_analytics.py``
creating a synchronous ``pymongo.MongoClient(MONGO_URL)`` at *module import
time*. On an Atlas ``mongodb+srv://`` URI, pymongo performs a BLOCKING DNS SRV
lookup while constructing the client — which hung app import so uvicorn never
bound :8001 and the pod failed its readiness probe. It passed in preview
because a local ``mongodb://`` URI needs no SRV lookup, so the bug was
invisible until deploy.

This test statically scans every route module for the same class of
anti-pattern (synchronous MongoClient construction and blocking ``requests`` /
``urllib`` / ``time.sleep`` calls executed at import scope) so the regression
can never ship again. Code that legitimately needs such a call at import scope
can opt out with a trailing ``# noqa: import-blocking`` comment.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
# Modules imported during app boot (register_routes + server import chain).
SCAN_DIRS = [
    BACKEND / "routes",
    BACKEND / "route_registry",
    BACKEND / "utils",
    BACKEND / "bootstrap",
]

# Dotted call targets that block the event loop / hang on network I/O.
# NOTE: AsyncIOMotorClient('mongodb+srv://…') ALSO does a blocking DNS SRV
# lookup at construction (motor wraps pymongo's parse_uri) — so constructing
# it at import scope hangs prod boot on Atlas exactly like sync MongoClient.
# The canonical shared client (utils/database.py) defers this via a lazy
# proxy for srv URIs and opts the eager non-srv branch out with the noqa tag.
BLOCKING_CALLS = {
    "MongoClient",              # pymongo — SYNC, does SRV DNS lookup at construction
    "pymongo.MongoClient",
    "AsyncIOMotorClient",       # motor — SYNC SRV DNS lookup at construction
    "motor.motor_asyncio.AsyncIOMotorClient",
    "requests.get", "requests.post", "requests.put", "requests.patch",
    "requests.delete", "requests.head", "requests.request", "requests.Session",
    "urllib.request.urlopen",
    "time.sleep",
}

OPT_OUT = "noqa: import-blocking"


def _dotted_name(node: ast.AST) -> str:
    """Best-effort dotted name for a Call's func (e.g. 'requests.get')."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _iter_import_time_calls(tree: ast.Module):
    """Yield Call nodes that execute at import time.

    Descends into module body and top-level control flow (If/Try/With/For/
    While) — all of which run on import — but NOT into function or class
    bodies, which only run when called.
    """
    def walk(body):
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # not executed at import time
            for node in ast.walk(stmt):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # ast.walk can't be pruned; skip nested def contents by
                    # not yielding from them — handled by the isinstance guard
                    # on the Call's enclosing scope below.
                    pass
                if isinstance(node, ast.Call):
                    yield stmt, node

    # ast.walk over a whole stmt would also dive into nested defs, so instead
    # collect calls while pruning function/class scopes explicitly.
    def collect(node, out):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, ast.Call):
                out.append(child)
            collect(child, out)

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        calls: list[ast.Call] = []
        if isinstance(stmt, ast.Call):
            calls.append(stmt)
        collect(stmt, calls)
        for call in calls:
            yield stmt, call


def _scan_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src, filename=str(path))
    violations: list[str] = []
    for _stmt, call in _iter_import_time_calls(tree):
        name = _dotted_name(call.func)
        if name in BLOCKING_CALLS:
            lineno = getattr(call, "lineno", 0)
            line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if OPT_OUT in line_text:
                continue
            rel = path.relative_to(BACKEND)
            violations.append(f"{rel}:{lineno} — blocking call '{name}(...)' at import scope")
    return violations


def test_no_blocking_calls_at_import_scope():
    all_violations: list[str] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            all_violations.extend(_scan_file(py))

    assert not all_violations, (
        "Blocking call(s) executed at module IMPORT scope in route modules. "
        "These hang app boot on Atlas (SRV DNS / network I/O) and cause k8s "
        "readiness crash-loops. Move them into a function/handler, use the "
        "shared async motor `db` from utils.database, or (if truly required) "
        "append '# noqa: import-blocking'.\n  - " + "\n  - ".join(all_violations)
    )


if __name__ == "__main__":
    import sys
    v: list[str] = []
    for base in SCAN_DIRS:
        if base.exists():
            for py in base.rglob("*.py"):
                v.extend(_scan_file(py))
    if v:
        print("BLOCKING import-scope calls found:")
        for line in v:
            print("  -", line)
        sys.exit(1)
    print("OK — no blocking calls at import scope in route modules.")
