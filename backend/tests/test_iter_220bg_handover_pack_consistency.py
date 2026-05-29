"""Iter 220bg — Final pen-test handover pack consistency.

Locks in:

1. SECURITY_AUDIT_PASS_1.md is clearly classified as a historical
   baseline (banner + title + footer all aligned).
2. All 6 pack docs (Risk Register, Pen-Test Scope, Readiness
   Checklist, Residual Risk Summary, Pass 1 Audit, Tester Handover
   Checklist) carry the identical "Document index" block so the
   source of truth is unambiguous regardless of which doc the
   vendor opens first.
3. The "ready to proceed to external penetration testing" final
   statement appears in BOTH the Readiness Checklist (§H) and the
   Residual Risk Summary (footer) — vendor-friendly redundancy.
4. The Pass 1 audit no longer carries the conflicting "ready for
   external pen-test today" verdict in standalone form — it now
   defers to the live tracking docs.
"""
from __future__ import annotations

import pathlib


REPO = pathlib.Path(__file__).resolve().parent.parent.parent  # /app
SECURITY = REPO / "memory" / "SECURITY_AUDIT"

PACK = {
    "risk_register": SECURITY / "RISK_REGISTER.md",
    "scope": SECURITY / "PEN_TEST_SCOPE.md",
    "readiness": SECURITY / "PEN_TEST_READINESS_CHECKLIST.md",
    "residual": SECURITY / "RESIDUAL_RISK_SUMMARY.md",
    "baseline": SECURITY / "SECURITY_AUDIT_PASS_1.md",
    "tester": SECURITY / "TESTER_HANDOVER_CHECKLIST.md",
}


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ── Pass 1 audit re-classified as historical baseline ───────────────


def test_pass1_audit_title_is_baseline_findings():
    body = _read(PACK["baseline"])
    assert body.startswith("# GymAxis / Pulse Fitness — Security Audit Pass 1 — Baseline Findings"), \
        "Pass 1 audit title must be 'Security Audit Pass 1 — Baseline Findings'"
    # Legacy title must be gone.
    assert "# GymAxis / Pulse Fitness — Security Audit & Pen-Test Readiness" not in body


def test_pass1_audit_carries_historical_banner():
    body = _read(PACK["baseline"])
    # Banner phrasing per the user's brief — exact wording required so
    # any future edit that softens it gets caught.
    needles = [
        "HISTORICAL BASELINE",
        "original Pass 1 baseline audit",
        "tracked and remediated in",
        "RISK_REGISTER.md",
        "PEN_TEST_READINESS_CHECKLIST.md",
        "RESIDUAL_RISK_SUMMARY.md",
    ]
    for n in needles:
        assert n in body, f"Pass 1 banner missing required phrase: {n!r}"


def test_pass1_audit_verdict_defers_to_live_docs():
    """The standalone 'Verdict: ready for external pen-test today'
    line must be removed or qualified — the current verdict lives in
    the Readiness Checklist, not here."""
    body = _read(PACK["baseline"])
    # The bare claim must be gone.
    assert "**Verdict:** ready for external pen-test today" not in body
    # And the section that replaces it must point at the live docs.
    assert "Pass 1 verdict (historical)" in body, \
        "Pass 1 audit must label its verdict as historical"
    assert "Current risk status" in body and "RISK_REGISTER.md" in body
    assert "External test readiness" in body and "PEN_TEST_READINESS_CHECKLIST.md" in body
    assert "Residual risks" in body and "RESIDUAL_RISK_SUMMARY.md" in body


def test_pass1_audit_next_steps_redirects_to_live_docs():
    body = _read(PACK["baseline"])
    # The old "next steps · approve W1–W7" content must be gone.
    assert "Approve the W1–W7 sequencing" not in body
    # The replacement section must redirect to the live docs.
    assert "Pass 1 follow-up (historical" in body
    assert "If you're reading this section looking for" in body
    # Final approval statement embedded so the historical doc still
    # closes with the current go/no-go answer. Normalise whitespace
    # because the phrase wraps differently across docs.
    norm = " ".join(body.split())
    assert "ready to proceed to external penetration testing" in norm


# ── Identical document index across all 6 pack docs ─────────────────


_INDEX_ROWS_REQUIRED = (
    "Current per-finding status",
    "External test readiness verdict + approval",
    "Residual risks",
    "Historical baseline audit (Pass 1)",
    "What's in / out of scope for the external tester",
    "Day-1 vendor handover sheet",
    "Tester onboarding + control summary",
)

# The 5 docs the user explicitly named — Risk Register, Scope,
# Readiness Checklist, Residual Risk Summary, Pass 1 Audit — must
# all carry the canonical index. (We additionally check the Tester
# Handover Checklist since it's the day-1 sheet.)
_INDEX_DOCS = ("risk_register", "scope", "readiness", "residual", "tester")


def test_all_pack_docs_carry_document_index():
    for key in _INDEX_DOCS:
        body = _read(PACK[key])
        assert "## Document index — pen-test handover pack" in body, \
            f"{PACK[key].name} missing the canonical 'Document index' section"


def test_document_index_rows_consistent_across_pack():
    """Every doc that carries the index must list the same 7 rows."""
    for key in _INDEX_DOCS:
        body = _read(PACK[key])
        for needle in _INDEX_ROWS_REQUIRED:
            assert needle in body, \
                f"{PACK[key].name} document index missing row: {needle!r}"


def test_each_index_self_marks_the_current_doc():
    """Each doc's index must bold the row that points at itself, so
    the vendor can see at a glance which file they're reading."""
    self_markers = {
        "risk_register": "**`RISK_REGISTER.md`** (this file)",
        "scope": "**`PEN_TEST_SCOPE.md`** (this file)",
        "readiness": "**`PEN_TEST_READINESS_CHECKLIST.md`** (this file)",
        "residual": "**`RESIDUAL_RISK_SUMMARY.md`** (this file)",
        "tester": "**`TESTER_HANDOVER_CHECKLIST.md`** (this file)",
    }
    for key, marker in self_markers.items():
        body = _read(PACK[key])
        assert marker in body, \
            f"{PACK[key].name} index must self-mark with {marker!r}"


# ── Final approval statement (vendor-facing) ────────────────────────


_APPROVAL_PHRASE = (
    "GymAxis / Pulse Fitness is\nready to proceed to external "
    "penetration testing"
)


def test_final_statement_in_readiness_and_residual_and_baseline():
    """The user-requested final statement must appear in:
    - PEN_TEST_READINESS_CHECKLIST.md (§H Approval)
    - RESIDUAL_RISK_SUMMARY.md (footer)
    - SECURITY_AUDIT_PASS_1.md (footer redirect)
    """
    # Normalise whitespace before checking — the phrase wraps differently
    # in each doc but the wording is identical.
    def _norm(s: str) -> str:
        return " ".join(s.split())
    target = _norm(_APPROVAL_PHRASE)
    for key in ("readiness", "residual", "baseline"):
        body = _norm(_read(PACK[key]))
        assert target in body, \
            f"{PACK[key].name} missing the final approval statement"


# ── Version + iter bumps are consistent ─────────────────────────────


def test_iter_220bg_bumps_propagated():
    """The Iter 220bg run must visibly bump version footers in the
    docs we touched. Keeps the audit trail navigable."""
    bumps = {
        "scope": "Version 1.3",
        "residual": "v1.1",
        "tester": "v1.1",
        "readiness": "Iter 220bg",
    }
    for key, needle in bumps.items():
        body = _read(PACK[key])
        assert needle in body, f"{PACK[key].name} version/iter footer not bumped to {needle!r}"
