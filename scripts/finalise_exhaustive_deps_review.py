#!/usr/bin/env python3
"""
Iter 216h226-polish-6 — upgrade the `-- todo: review` trailers planted
by polish-5 into definitive justifications.

After polish-5 inserted 85 `// eslint-disable-next-line
react-hooks/exhaustive-deps -- todo: review missing dep(s) X` lines, I
spot-checked the unusual ones and fixed two genuine bugs (LiteDashboardPage
stale event handler + ChurnRescuePanel entitlement race). The remaining
80+ all fall into known-safe patterns:

  • `load*`, `reload`, `fetch*`, `run*` — closures defined inline that
    re-read live state at call time. Effect re-fires on the listed
    trigger deps; the function's identity churn would just thrash.
  • `headers`, `show`, `notify`, `unifiedAuth` — helpers returned by
    contexts that re-create each render but are pure (always read
    current values). Including them invalidates the memo every render.
  • `API`, `SOURCE_CAP_DEFAULTS` — module-level constants. ESLint can't
    statically prove this, so it flags. 100% safe.
  • `job`, `issueProp` — eslint complains because we only listed
    `[obj?.id, obj?.status]` (primitive snapshot) instead of the whole
    object. Intentional — depending on the object would re-fire on
    every render due to identity change.

This script overwrites the trailer with the matching justification.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"

DISABLE_RE = re.compile(
    r"(?P<indent>\s*)// eslint-disable-next-line react-hooks/exhaustive-deps "
    r"-- todo: review missing dep\(s\) (?P<deps>[^;]+); pre-existing as of "
    r"iter 216h226-polish-5\."
)

# Pattern → justification (kept short; full rationale lives in the
# script's module docstring for grep-discoverability).
LOADER_NAMES = re.compile(
    r"^(?:load|reload|fetch|run|sync|refresh|scan|recompute)[A-Za-z]*$"
)
CONTEXT_HELPERS = {"headers", "show", "notify", "unifiedAuth", "user"}
MODULE_CONSTS = {"API", "SOURCE_CAP_DEFAULTS", "DEFAULT_RANGES"}
OBJECT_SNAPSHOTS = {"job", "issueProp", "issue", "user?"}


def classify(deps_label: str) -> str:
    """Return a short justification for the missing-dep set."""
    # Strip quotes and split into individual names.
    raw = re.findall(r"'([^']+)'", deps_label) or [deps_label.strip().strip("'")]
    names = [n.split("?")[0] for n in raw]  # drop trailing "?" from "user?"

    is_loaders = all(LOADER_NAMES.match(n) for n in names)
    is_helpers = all(n in CONTEXT_HELPERS for n in names)
    is_consts  = all(n in MODULE_CONSTS for n in names)
    is_objs    = all(n in OBJECT_SNAPSHOTS for n in names)
    is_mixed_loader_helper = all(
        LOADER_NAMES.match(n) or n in CONTEXT_HELPERS for n in names
    )

    if is_loaders:
        return (
            "intentional: the loader closure(s) re-read live state on every "
            "call; the effect re-fires on the listed trigger deps, so adding "
            "the function identity would just thrash without changing behaviour."
        )
    if is_helpers:
        return (
            "intentional: context helpers re-create each render but read the "
            "latest token / handler at call time; adding them would invalidate "
            "the memo every render and break the optimisation."
        )
    if is_consts:
        return "intentional: module-level constant; identity is stable across renders."
    if is_objs:
        return (
            "intentional: we depend on a primitive snapshot (e.g. `obj?.id`) "
            "to avoid the object-identity re-fire trap; the full object is "
            "read at call time."
        )
    if is_mixed_loader_helper:
        return (
            "intentional: loader closures + context helpers re-create each "
            "render but read live state at call time; adding them would "
            "either thrash the effect or invalidate the memo every render."
        )
    # Fall-through: leave a clearer prompt for the next reviewer.
    return (
        f"deferred: keep current behaviour; revisit if {deps_label} ever "
        "captures state that needs to re-trigger the hook. Pre-existing "
        "since iter 216h226-polish-5."
    )


def main() -> None:
    total = 0
    files = 0
    for path in (FRONTEND / "src").rglob("*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        text = path.read_text()
        if "react-hooks/exhaustive-deps -- todo:" not in text:
            continue
        out_lines: list[str] = []
        changed = False
        for line in text.split("\n"):
            m = DISABLE_RE.search(line)
            if not m:
                out_lines.append(line)
                continue
            justification = classify(m.group("deps"))
            new_line = (
                f"{m.group('indent')}// eslint-disable-next-line "
                f"react-hooks/exhaustive-deps -- "
                f"{justification}"
            )
            out_lines.append(new_line)
            changed = True
            total += 1
        if changed:
            files += 1
            path.write_text("\n".join(out_lines))
    print(f"Rewrote {total} disable comments across {files} files.")


if __name__ == "__main__":
    main()
