"""Iter 220bo — guard rail against double `/api/api/` URL bugs in
frontend panels.

Background: In Iter 220bl the SocialAutopilotPanel destructured
`const { API } = useAuth()` where `API` already includes `/api`. The
fetch URLs then prefixed `/api/marketing/...` themselves, producing
`/api/api/marketing/...` which 404'd in production and rendered as
"Not Found" in the panel body.

This test sweeps the entire React source tree looking for any literal
that would produce a double-prefix URL when concatenated. It's a fast
regex check — no Node/Jest dependency required.

Add new panels to the whitelist only if you are 100% sure they don't
contribute to a runtime fetch (e.g. comments, doc strings).
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_frontend_src_dir_exists():
    assert FRONTEND_SRC.is_dir(), f"frontend src missing at {FRONTEND_SRC}"


def _scan_files():
    """Yield (path, line_no, line) for any source file that uses the
    convention `${API}/api/...` AND also reads `API` from `useAuth()`.

    The combination is the smell — either pattern alone is fine; both
    together produce `/api/api/...`.
    """
    offenders: list[tuple[str, int, str]] = []
    for p in FRONTEND_SRC.rglob("*.js"):
        text = p.read_text(encoding="utf-8", errors="replace")
        uses_useauth_api = re.search(r"\bconst\s*\{\s*API\s*\}\s*=\s*useAuth\(", text)
        if not uses_useauth_api:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # Skip JSDoc / block / line comments — false positives.
            if stripped.startswith(("*", "//", "/*")):
                continue
            if re.search(r"\$\{API\}/api/", line):
                offenders.append((str(p.relative_to(FRONTEND_SRC.parent.parent)), i, stripped))
    return offenders


def test_no_double_api_prefix_combination():
    offenders = _scan_files()
    assert not offenders, (
        "Double `/api/api/` prefix risk — these files read API from "
        "useAuth() (which already ends with `/api`) AND also prefix "
        "`/api/` in the URL literal. Either remove the leading `/api/` "
        "or switch to `const API = process.env.REACT_APP_BACKEND_URL`.\n"
        + "\n".join(f"  {p}:{ln}  {src}" for p, ln, src in offenders)
    )


def test_social_autopilot_panel_uses_env_url_directly():
    """Lock the SocialAutopilotPanel fix in place so a future refactor
    cannot silently re-introduce the bug."""
    panel = (FRONTEND_SRC / "pages" / "MasterAdmin" / "SocialAutopilotPanel.js").read_text()
    assert "const API = process.env.REACT_APP_BACKEND_URL" in panel, (
        "SocialAutopilotPanel.js must define API as "
        "process.env.REACT_APP_BACKEND_URL (no trailing /api) — see "
        "Iter 220bo for context."
    )
    assert "import { useAuth }" not in panel and "from '@/App'" not in panel, (
        "SocialAutopilotPanel.js must NOT import useAuth from @/App — "
        "see Iter 220bo for context."
    )
    assert "const { API } = useAuth(" not in panel, (
        "SocialAutopilotPanel.js must NOT destructure API from useAuth()."
    )
    assert "/api/api/" not in panel, (
        "SocialAutopilotPanel.js contains a literal `/api/api/` — bug "
        "regression."
    )
