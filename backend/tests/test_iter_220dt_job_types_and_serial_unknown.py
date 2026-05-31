"""Iter 220dt — Job-type taxonomy + serial-unknown + Summary cleanup.

Operator feedback (Feb 2026):

  1. **Remove "I'm on site" from the Engineer Summary** — the Time
     tab already owns starting the on-site timer.
  2. **Allocate-to-me time should be Hours + Minutes dropdowns**
     instead of a free-form number input.
  3. **Job types** — customers + service desk + engineer all want
     to pick a job type (Repair / PPM / Install / Inspection /
     Callout / Audit) so reporting + auto-loaded custom fields
     can branch on it. Engineer Summary shows the chosen type as
     a chip.
  4. **Serial unknown escape hatch** — some machines have rubbed-
     off serials. Intake stamps a ``capture_serial_required``
     flag on the case so the engineer raises a "capture on visit
     1" task rather than blocking customer intake.
  5. **Custom fields** move to Account Settings — covered by
     220ds's removal from Complete; future iter binds them to
     job_type + equipment.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")
BACKEND = Path("/app/backend")


def _read_fe(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def _read_be(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


# ── 1 · I'm-on-site removed from Summary ───────────────────────────


def test_summary_no_longer_has_im_on_site_button():
    src = _read_fe("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The CTA button + resume button testids are gone.
    assert 'data-testid="jaag-arrive"' not in src
    assert 'data-testid="jaag-resume"' not in src
    # The literal "I'm on site" CTA text is gone (only comments
    # mentioning the historical button may remain).
    assert ">\n              <LogIn size={14} /> I'm on site" not in src
    # Passive "On site — timer running" badge stays (informative,
    # not a competing control).
    assert 'data-testid="jaag-on-site-now"' in src


# ── 2 · Claim modal switches to Hours + Minutes dropdowns ─────────


def test_claim_modal_uses_hours_minutes_dropdowns():
    src = _read_fe("pages/ServiceOps/Engineer/EngineerQueue.js")
    # New hour + minute selects.
    assert 'data-testid="claim-hours-input"' in src
    assert 'data-testid="claim-minutes-input"' in src
    assert "{ length: 11 }" in src  # 0–10 hours
    # Total preview chip pinned.
    assert 'data-testid="claim-total-minutes"' in src
    # Old free-form numeric input is gone (we kept the testid so
    # auto-tests still find a "minutes" field, but it's the select
    # now). The submission floor stays at 15 minutes.
    assert "totalMins < 15" in src
    assert "Math.max(15, Math.min(600, totalMins))" in src


# ── 3 · Job-type chip on Engineer Summary ────────────────────────


def test_engineer_summary_renders_case_type_chip():
    src = _read_fe("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="jaag-case-type"' in src
    # Friendly label map + helper exist.
    assert "CASE_TYPE_LABELS" in src
    assert "function labelForCaseType" in src
    assert "ppm: 'PPM Service'" in src
    assert "install: 'Installation'" in src


def test_service_desk_intake_form_offers_extended_job_types():
    src = _read_fe("pages/ServiceOps/ServiceDeskIntakeForm.js")
    # The friendly "Job type" label replaces the older "Case type".
    assert 'label="Job type"' in src
    # New options are pinned.
    assert '<option value="inspection">' in src
    assert '<option value="callout">' in src
    assert '<option value="audit">' in src
    assert "Preventative Maintenance Service" in src


# ── 4 · Backend accepts the extended taxonomy ────────────────────


def test_intake_allows_extended_case_types():
    src = _read_be("routes/svc/intake.py")
    # The whitelist now includes the new slugs.
    assert (
        '{"repair", "ppm", "install", "inspection", "callout", "audit"}'
        in src
    )


def test_intake_persists_capture_serial_required_flag():
    src = _read_be("routes/svc/intake.py")
    # Both fields land on the canonical svc_case doc.
    assert '"capture_serial_required": bool(payload.get("capture_serial_required")' in src
    assert '"capture_serial_reason"' in src


def test_issue_create_schema_carries_case_type_and_serial_unknown():
    src = _read_be("models/schemas.py")
    assert 'case_type: Optional[str] = "repair"' in src
    assert "serial_unknown: Optional[bool] = False" in src
    assert "serial_unknown_reason: Optional[str] = None" in src


def test_issue_to_svc_case_mirror_propagates_case_type_and_serial_flag():
    src = _read_be("routes/issues.py")
    # The mirror payload picks the slug up off the issue doc.
    assert '"case_type": issue_doc.get("case_type") or "repair"' in src
    # And carries the capture-serial flag onto the svc_case so the
    # engineer's app can render the follow-up task.
    assert '"capture_serial_required": bool(issue_doc.get("serial_unknown"))' in src
    # source_meta keeps a serial-unknown audit trail.
    assert '"serial_unknown": bool(issue_doc.get("serial_unknown"))' in src


def test_build_issue_doc_persists_case_type():
    src = _read_be("routes/issues.py")
    assert '"case_type": (getattr(issue, "case_type", None) or "repair")' in src
    assert '"serial_unknown": bool(getattr(issue, "serial_unknown", False))' in src
