"""Iter 220bh — Final consistency: regression count, "33 findings"
phrasing, and removal of "opportunistic" rollout wording.

Locks in:

1. **No stale absolute regression counts** in any pack doc.
   We allow the canonical "1,300+ tests" fuzzy phrasing only —
   bare numbers like "1253", "1290", "1301", "1312", "1321"
   would drift the moment we add or remove a test.
2. **"33 findings" wording standardised** to a single canonical
   phrasing — "33 risk-register findings (F-01 → F-33)" — across
   the whole security pack. Old variants ("33 findings, all closed",
   "all 33 actionable findings", "33/33 findings", "27 of 33") must
   be gone.
3. **"Opportunistic" rollout language removed** — pen-testers read
   it as non-committal. Every previous occurrence is replaced with
   either concrete cadence ("scheduled into the next backlog
   review") or concrete state ("foundation deployed; gaps will be
   filed as F-34+").
"""
from __future__ import annotations

import pathlib
import re


REPO = pathlib.Path(__file__).resolve().parent.parent.parent  # /app
SECURITY = REPO / "memory" / "SECURITY_AUDIT"

PACK = sorted(SECURITY.glob("*.md"))


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ── 1) Regression count consistency ────────────────────────────────


_BARE_COUNT_RX = re.compile(r"\b(?:12\d\d|13\d\d|14\d\d)\s+(?:tests?\s+)?pass(?:ed|ing)\b")


def test_no_stale_absolute_regression_counts():
    hits: list[str] = []
    for p in PACK:
        body = _read(p)
        for ln, line in enumerate(body.splitlines(), start=1):
            if _BARE_COUNT_RX.search(line):
                hits.append(f"{p.name}:{ln}: {line.strip()[:120]}")
    assert not hits, (
        "Stale absolute regression counts found in security pack — "
        "use the canonical '1,300+ tests passing' fuzzy phrasing "
        "instead (number drifts every iter):\n"
        + "\n".join(hits[:10])
    )


def test_canonical_regression_phrasing_present():
    """At least one pack doc must carry the canonical
    "1,300+ tests" phrasing so the vendor sees a steady-state
    signal."""
    norm_hits = sum(
        1 for p in PACK if "1,300+" in _read(p)
    )
    assert norm_hits >= 1, \
        "no canonical '1,300+' regression-count phrasing in the pack"


# ── 2) "33 findings" wording consistency ───────────────────────────


_FORBIDDEN_FINDING_PHRASES = (
    "27 of 33",
    "33/33 findings",
    "33 actionable findings",
    "33 findings, all closed",
    "33 findings ranked",
    "33 findings, ranked",
    "33 known findings",
)


def test_no_legacy_finding_count_phrasings():
    """Drift hunt — any of the old phrasings means a doc didn't
    pick up the canonical wording."""
    hits: list[str] = []
    for p in PACK:
        body = _read(p)
        for ln, line in enumerate(body.splitlines(), start=1):
            for needle in _FORBIDDEN_FINDING_PHRASES:
                if needle in line:
                    hits.append(f"{p.name}:{ln}: {needle!r} in {line.strip()[:80]}")
    assert not hits, (
        "Legacy 33-findings phrasing still present:\n"
        + "\n".join(hits[:10])
    )


def test_canonical_finding_phrasing_used_everywhere():
    """The canonical phrasing — "33 risk-register findings (F-01 →
    F-33)" — must appear in every pack doc that mentions the
    finding count. We allow the abbreviated "all 33" / "33 risk-
    register findings" as long as the F-01 → F-33 anchor is there
    elsewhere in the same doc.
    """
    canonical = "33 risk-register findings (F-01 → F-33)"
    docs_mentioning_count = [
        p for p in PACK
        if "33" in _read(p) and "F-" in _read(p)
    ]
    assert docs_mentioning_count, "no pack doc mentions the finding count"
    bad = [p.name for p in docs_mentioning_count if canonical not in _read(p)]
    # The TESTER_HANDOVER_CHECKLIST + PEN_TEST_FINDINGS docs talk
    # about the engagement, not the finding count. They are
    # exempt — they don't need to mention the canonical phrasing.
    bad = [
        n for n in bad
        if n not in {"TESTER_HANDOVER_CHECKLIST.md",
                     "PEN_TEST_FINDINGS.md",
                     "DEPLOY_RUNBOOK_PENTEST.md",
                     "OPS_RUNBOOK.md",
                     "PROD_ENV_FLIP_INSTRUCTIONS.md"}
    ]
    assert not bad, (
        "Pack docs missing canonical finding phrasing "
        f"({canonical!r}): {bad}"
    )


# ── 3) "opportunistic" wording removed ─────────────────────────────


def test_no_opportunistic_wording_anywhere_in_security_pack():
    hits: list[str] = []
    for p in PACK:
        body = _read(p)
        for ln, line in enumerate(body.splitlines(), start=1):
            if "opportunistic" in line.lower():
                hits.append(f"{p.name}:{ln}: {line.strip()[:120]}")
    assert not hits, (
        "'opportunistic' wording still present in security pack — "
        "pen-testers read it as non-committal. Replace with concrete "
        "cadence or 'gaps will be filed as F-34+' language:\n"
        + "\n".join(hits[:10])
    )


def test_concrete_rollout_language_replaces_opportunistic():
    """For each of F-18, F-20, F-33 (the previously "opportunistic"
    rollouts) the Risk Register row must now state the concrete
    rollout policy + the F-34+ filing rule."""
    risk = _read(SECURITY / "RISK_REGISTER.md")
    for fid in ("F-18", "F-20", "F-33"):
        row_match = re.search(
            r"\|\s*" + fid + r"\s*\|.*?\|\s*\n",
            risk,
            re.DOTALL,
        )
        assert row_match, f"could not locate {fid} row in RISK_REGISTER.md"
        row = row_match.group(0)
        assert "F-34" in row, \
            f"{fid} row must reference 'gaps will be filed as F-34+' policy"


def test_low_severity_cadence_is_concrete_not_opportunistic():
    """The Low severity definition in the Risk Register + the Low
    fix-target row in §G of the Readiness Checklist must both be
    concrete cadence-statements, not the old "opportunistic" word."""
    risk = _read(SECURITY / "RISK_REGISTER.md")
    readiness = _read(SECURITY / "PEN_TEST_READINESS_CHECKLIST.md")
    assert "Scheduled into the next security-backlog grooming review" in risk
    assert "Scheduled into the next security-backlog grooming review" in readiness
