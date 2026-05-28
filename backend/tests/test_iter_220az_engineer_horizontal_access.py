"""Iter 220az — F-29 / F-33 close-out · Engineer-app horizontal access.

Confirms every engineer-app cross-engineer access path returns 404
(NOT 403) so an attacker can't enumerate resource IDs by status code.

Pre-fix: status_code=403 with detail "Not your quote" / "Not your
invoice" / "Not assigned to this job" / "Cannot edit another engineer's
personal preset". Post-fix: status_code=404 with the same generic
"not found" detail used for non-existent rows.

The 11 surfaces patched:

  1. engineer_quotes._get_quote_or_404
  2. engineer_invoices._get_invoice_or_404  (similar path)
  3. engineer_invoices.create_invoice_from_quote (quote ownership)
  4. engineer_invoice_payments._get_invoice
  5. engineer.engineer_job_detail
  6. engineer.engineer_close_case (the second occurrence)
  7. safety (assigned_engineer_id gate)
  8. diary.set_case_schedule
  9. service_report (the assigned_engineer_id gate)
 10. per_machine_reports.update_personal_preset
 11. per_machine_reports.archive_personal_preset
 12. engineer_phase3._require_case_visible_to_engineer

Source-level checks (no DB / no FastAPI app boot) so the regression
suite stays fast + deterministic.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "routes" / "svc"


def _grep_403_lines_with_owned_check(text: str) -> list[str]:
    """Return every line that pairs a 403 status with an engineer-ownership
    rejection message."""
    needles = [
        "Not your",
        "Not assigned to this job",
        "Cannot edit another",
        "Cannot archive another",
    ]
    return [
        line for line in text.splitlines()
        if "HTTPException(403" in line and any(n in line for n in needles)
    ]


def test_no_403_for_engineer_ownership_mismatch():
    """F-29 / F-33 — the entire engineer-app must NOT return 403 when an
    engineer accesses another engineer's resource. Cross-engineer rows
    must look identical to non-existent rows (404)."""
    offenders: list[str] = []
    for p in sorted(ROOT.glob("*.py")):
        text = p.read_text(encoding="utf-8")
        for line in _grep_403_lines_with_owned_check(text):
            offenders.append(f"{p.relative_to(ROOT.parent.parent)}: {line.strip()}")
    assert not offenders, (
        "F-29 / F-33 regression — cross-engineer 403 leak reintroduced:\n  "
        + "\n  ".join(offenders)
    )


def test_engineer_quotes_returns_404_on_cross_engineer():
    """Spot-check the canonical `_get_quote_or_404` path: must compare
    against ``user.get("id")`` and raise a 404 (not 403) when mismatched."""
    text = (ROOT / "engineer_quotes.py").read_text(encoding="utf-8")
    # The fix must include both the ownership check AND a master-admin escape.
    assert re.search(
        r'quote\.get\("engineer_id"\) != user\.get\("id"\).*not user\.get\("is_master_admin"\)',
        text, flags=re.DOTALL,
    ), "engineer_quotes._get_quote_or_404 missing master-admin bypass"
    assert 'raise HTTPException(404, "Quote not found")' in text


def test_engineer_invoices_returns_404_on_cross_engineer():
    text = (ROOT / "engineer_invoices.py").read_text(encoding="utf-8")
    # Both the get-invoice gate AND the create-invoice-from-quote gate
    # must now raise 404.
    assert text.count('raise HTTPException(404, "Invoice not found")') >= 2
    assert 'raise HTTPException(404, "Quote not found")' in text


def test_engineer_invoice_payments_returns_404_on_cross_engineer():
    text = (ROOT / "engineer_invoice_payments.py").read_text(encoding="utf-8")
    assert 'raise HTTPException(404, "Invoice not found")' in text
    # Should appear twice now: missing-row 404 + cross-engineer 404.
    assert text.count('raise HTTPException(404, "Invoice not found")') >= 2


def test_case_assignment_gates_return_404():
    """Every `assigned_engineer_id != user["id"]` gate across the
    engineer-app must now produce a 404 ("Job not found" / "Case not found"
    / "Preset not found") — never a 403."""
    files_to_check = (
        "engineer.py",
        "safety.py",
        "diary.py",
        "service_report.py",
        "engineer_phase3.py",
    )
    for fname in files_to_check:
        text = (ROOT / fname).read_text(encoding="utf-8")
        # Find every `assigned_engineer_id != user["id"]` line and the
        # next HTTPException reference. Must be 404, not 403.
        for m in re.finditer(
            r"assigned_engineer_id.*?!=.*?user\[.id.\].*?HTTPException\((\d+)",
            text, flags=re.DOTALL,
        ):
            assert m.group(1) == "404", (
                f"{fname}: assigned_engineer_id gate still raises {m.group(1)} — "
                f"must be 404 for F-29 / F-33 close-out"
            )


def test_per_machine_preset_gates_return_404():
    text = (ROOT / "per_machine_reports.py").read_text(encoding="utf-8")
    # Both the update + archive ownership gates must raise 404.
    # Use a tight regex (no DOTALL) so we match each guard individually.
    matches = re.findall(
        r'engineer_id"\) != user\.get\("id"\)[\s\S]{0,200}?HTTPException\((\d+)',
        text,
    )
    assert len(matches) >= 2, f"expected 2 personal-preset gates, found {len(matches)}"
    for code in matches:
        assert code == "404", (
            f"per_machine_reports personal-preset gate still raises {code} "
            "— must be 404"
        )


# ── Smoke: assert_engineer_owns helper still does the right thing.


def test_assert_engineer_owns_still_404s():
    """W6 helper must still be the canonical pattern — regression-lock it
    in case a future refactor changes the status code."""
    from fastapi import HTTPException
    from utils.audit_log import assert_engineer_owns
    try:
        assert_engineer_owns("eng-1", "eng-2", label="Foo")
        assert False
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "Foo" in exc.detail
