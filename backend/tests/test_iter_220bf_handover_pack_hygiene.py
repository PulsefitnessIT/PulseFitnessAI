"""Iter 220bf — Pen-test handover pack documentation hygiene.

Source-level regression locks for the final pre-pen-test doc tidy:

* The 4 handover docs (PEN_TEST_SCOPE, PEN_TEST_READINESS_CHECKLIST,
  RESIDUAL_RISK_SUMMARY, TESTER_HANDOVER_CHECKLIST) all exist.
* No raw plaintext credentials in any SECURITY_AUDIT/*.md handover
  doc — the only allowed mentions of weak passwords are in
  `RISK_REGISTER.md` where the F-30 row documents the detection
  list intentionally.
* No `<your-domain>` / `<your-phone>` / `+44 (0) 0000 000000` /
  `INSERT HERE` style placeholders remain anywhere in
  `SECURITY_AUDIT/` or `LEGAL/`.
* The readiness checklist contains the post-pen-test process + the
  internal approval statement.
* The residual-risk summary uses the A/B/C/D structure with the
  explicit "Open risks: None" wording.
"""
from __future__ import annotations

import pathlib
import re


REPO = pathlib.Path(__file__).resolve().parent.parent.parent  # /app
SECURITY = REPO / "memory" / "SECURITY_AUDIT"
LEGAL = REPO / "memory" / "LEGAL"

HANDOVER_DOCS = [
    SECURITY / "PEN_TEST_SCOPE.md",
    SECURITY / "PEN_TEST_READINESS_CHECKLIST.md",
    SECURITY / "RESIDUAL_RISK_SUMMARY.md",
    SECURITY / "TESTER_HANDOVER_CHECKLIST.md",
    SECURITY / "PEN_TEST_ONBOARDING.md",
    SECURITY / "PEN_TEST_FINDINGS.md",
    SECURITY / "DEPLOY_RUNBOOK_PENTEST.md",
    SECURITY / "SECURITY_AUDIT_PASS_1.md",
]


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def test_all_handover_docs_exist():
    for p in HANDOVER_DOCS:
        assert p.exists(), f"missing handover doc {p}"


def test_no_placeholder_strings_in_security_or_legal():
    """No bracket-style placeholders anywhere."""
    needles = [
        r"<your-domain>",
        r"<your-name>",
        r"<your-phone>",
        r"<phone>",
        r"<email>",
        r"INSERT HERE",
        r"\+44 \(0\) 0000 000000",
        r"<your-internal-share>",
    ]
    rx = re.compile("|".join(needles))
    hits: list[str] = []
    for p in list(SECURITY.glob("*.md")) + list(LEGAL.glob("*.md")):
        body = _read(p)
        for ln, line in enumerate(body.splitlines(), start=1):
            if rx.search(line):
                hits.append(f"{p.name}:{ln}: {line[:120]}")
    assert not hits, "placeholders remain in docs:\n" + "\n".join(hits[:20])


def test_no_plaintext_credentials_in_handover_docs():
    """The pen-test handover pack must not contain raw passwords.

    Allowed: the F-30 row in RISK_REGISTER.md (it documents the
    detection list by intent), and the utils/secrets_audit.py
    detection module itself.
    """
    weak = ("MasterAdmin123!", "Test123!", "PentestOwner!2026",
            "PentestMgr!2026", "PentestStaff!2026", "PentestMfa!2026")
    hits: list[str] = []
    for p in HANDOVER_DOCS:
        body = _read(p)
        for ln, line in enumerate(body.splitlines(), start=1):
            for needle in weak:
                if needle in line:
                    # The F-30 row in the risk register documents that
                    # these strings are intentionally on a detection
                    # list — that's the only allowed mention.
                    if p.name == "RISK_REGISTER.md" and "F-30" in line:
                        continue
                    hits.append(f"{p.name}:{ln}: {needle} in {line[:80]}")
    assert not hits, \
        "plaintext credentials found in handover docs:\n" + "\n".join(hits[:20])


def test_residual_risk_summary_structure():
    body = _read(SECURITY / "RESIDUAL_RISK_SUMMARY.md")
    # Required A/B/C/D sections.
    for heading in (
        "## A · Fixed and verified",
        "## B · Implemented but awaiting external verification",
        "## C · Accepted limitations",
        "## D · Open risks",
    ):
        assert heading in body, f"missing section {heading!r}"
    # Explicit "no open risks" statement.
    assert "None currently identified before external test" in body, \
        "open-risks statement missing or worded differently"
    # All 33 findings closed claim.
    assert "All **33**" in body or "All 33" in body, \
        "summary must state the 33-findings-closed headline"


def test_residual_risk_summary_lists_accepted_limitations():
    body = _read(SECURITY / "RESIDUAL_RISK_SUMMARY.md")
    # Each of the 6 documented limitations must be present.
    for needle in (
        "C-1 · `/api/health/deep`",
        "C-2 · Public sub-processor list",
        "C-3 · Engineer App offline cache",
        "C-4 · Shared preview + production environment values",
        "C-5 · Twilio SMS mocked",
        "C-6 · Credential-blocked integrations",
    ):
        assert needle in body, f"residual summary missing limitation: {needle!r}"


def test_residual_risk_summary_lists_implemented_awaiting_verification_areas():
    body = _read(SECURITY / "RESIDUAL_RISK_SUMMARY.md")
    for needle in (
        "AI prompt injection",
        "AI excessive agency",
        "AI output sanitisation",
        "AI token-budget caps",
        "Public widget brute-force",
        "Engineer App horizontal access",
        "DOM-XSS in PDF / email rendering",
        "Multi-tenant isolation edge cases",
    ):
        assert needle in body, f"§B missing area: {needle!r}"


def test_tester_handover_checklist_has_required_sections():
    body = _read(SECURITY / "TESTER_HANDOVER_CHECKLIST.md")
    for section in (
        "## 1 · URLs",
        "## 2 · Test window",
        "## 3 · Credential delivery",
        "## 4 · Communication channels",
        "## 5 · Out-of-scope",
        "## 6 · Safe testing rules",
        "## 7 · No live customer data confirmation",
        "## 8 · Reporting format",
        "## 9 · Emergency stop / escalation",
        "## 10 · Retest process",
    ):
        assert section in body, f"tester checklist missing {section!r}"
    # Must explicitly confirm no live data.
    assert "No real GymAxis or Pulse Fitness customer data" in body
    # Must reference 1Password for credential delivery (not inline).
    assert "1Password" in body


def test_readiness_checklist_has_approval_and_post_pentest():
    body = _read(SECURITY / "PEN_TEST_READINESS_CHECKLIST.md")
    assert "## G · Post-pen-test process" in body, "missing §G post-pen-test process"
    assert "## H · Internal approval statement" in body, "missing §H approval statement"
    assert "F-34" in body, "post-pen-test process must reference F-34+ logging"
    assert "Approval date" in body, "approval statement must include a date"
    assert "Craig Henshall" in body, "approval owner must be named"
    # Severity-tied fix targets (Critical/High/Medium/Low).
    for sev in ("Critical", "High", "Medium", "Low"):
        assert sev in body, f"§G missing severity tier {sev}"


def test_pen_test_scope_no_tbc_or_placeholder_phone():
    body = _read(SECURITY / "PEN_TEST_SCOPE.md")
    # The previous placeholder phone and TBC string must be gone.
    assert "+44 (0) 0000 000000" not in body
    # "TBC" appears in some legitimate "next scheduled" contexts; what
    # we want gone is the standalone "| TBC |" cell in the limitations
    # table.
    assert "| TBC |" not in body, "TBC table cell must be replaced with concrete guidance"
    # Version bumped.
    assert "Version 1.2" in body, "PEN_TEST_SCOPE.md version must be ≥ 1.2 (Iter 220bf)"


def test_pen_test_onboarding_credentials_redacted():
    body = _read(SECURITY / "PEN_TEST_ONBOARDING.md")
    # No inline password column.
    assert "| Password" not in body, "credential column must be removed from PEN_TEST_ONBOARDING"
    # Must call out 1Password as the delivery method.
    assert "1Password" in body, "onboarding must explain credential delivery via 1Password"


def test_deploy_runbook_no_inline_pentest_password():
    body = _read(SECURITY / "DEPLOY_RUNBOOK_PENTEST.md")
    # The PentestOwner!2026 inline string must be gone.
    assert "PentestOwner!2026" not in body
    # The previous internal-share placeholder must be gone.
    assert "<your-internal-share>" not in body
