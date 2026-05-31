"""Iter 220dx — Engineer "Capture serial on visit 1" auto-task.

Closes the rubbed-off-serial loop end-to-end:

  * Customer flagged ``serial_unknown`` on the Log-a-Fault dialog
    (iter 220dw) → backend stamps ``capture_serial_required=True``
    on the case (iter 220dt).
  * Engineer opens the case → Equipment tab → the new
    ``CaptureSerialCard`` pins at the top with a text input,
    optional photo upload, and a "Mark serial captured" button.
  * Submit posts to ``POST /api/svc/engineer/jobs/{id}/capture-serial``
    → stamps the case with the captured serial + engineer + photo
    id, flips ``capture_serial_required`` off, AND back-fills the
    canonical equipment row when the asset doesn't yet have a
    serial.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _eng():
    return {"id": "eng-1", "organization_id": "org-1",
            "full_name": "Sam Engineer", "email": "e@x.test"}


def _case(extra: dict | None = None):
    base = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "asset_id": "asset-1",
        "assigned_engineer_id": "eng-1",
        "capture_serial_required": True,
        "capture_serial_reason": "rubbed_off",
    }
    base.update(extra or {})
    return base


# ── Backend ───────────────────────────────────────────────────────


def test_capture_serial_409_when_not_required():
    from fastapi import HTTPException
    from routes.svc.engineer_phase3 import capture_serial, CaptureSerialIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=_case({
        "capture_serial_required": False,
    }))

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb):
            try:
                await capture_serial(
                    case_id="case-1",
                    body=CaptureSerialIn(serial="LF-1234"),
                    user=_eng(),
                )
                return None
            except HTTPException as exc:
                return exc.status_code

    assert _run(go()) == 409


def test_capture_serial_stamps_case_and_flips_required_flag():
    from routes.svc.engineer_phase3 import capture_serial, CaptureSerialIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=_case())
    fdb.svc_cases.update_one = AsyncMock()
    fdb.equipment.find_one = AsyncMock(return_value={
        "id": "asset-1", "serial_number": "",  # no serial yet
    })
    fdb.equipment.update_one = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            return await capture_serial(
                case_id="case-1",
                body=CaptureSerialIn(
                    serial="LF-22-12345-A",
                    photo_file_id="file-77",
                ),
                user=_eng(),
            )

    out = _run(go())
    # Case stamped with the captured info + flag flipped off.
    case_set = fdb.svc_cases.update_one.call_args[0][1]["$set"]
    assert case_set["captured_serial"] == "LF-22-12345-A"
    assert case_set["serial_capture_engineer_id"] == "eng-1"
    assert case_set["serial_capture_photo_id"] == "file-77"
    assert case_set["capture_serial_required"] is False
    # Equipment record back-filled.
    assert out["equipment_updated"] is True
    eq_set = fdb.equipment.update_one.call_args[0][1]["$set"]
    assert eq_set["serial_number"] == "LF-22-12345-A"
    assert "serial_captured_at" in eq_set


def test_capture_serial_does_not_overwrite_existing_equipment_serial():
    """If the canonical equipment row already has a serial we trust
    that one — engineer might be capturing a secondary plate. Case
    is still updated; equipment row is left alone."""
    from routes.svc.engineer_phase3 import capture_serial, CaptureSerialIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=_case())
    fdb.svc_cases.update_one = AsyncMock()
    fdb.equipment.find_one = AsyncMock(return_value={
        "id": "asset-1", "serial_number": "EXISTING-001",
    })
    fdb.equipment.update_one = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            return await capture_serial(
                case_id="case-1",
                body=CaptureSerialIn(serial="LF-22-99999-Z"),
                user=_eng(),
            )

    out = _run(go())
    fdb.equipment.update_one.assert_not_called()
    assert out["equipment_updated"] is False
    # Case still gets the captured value.
    case_set = fdb.svc_cases.update_one.call_args[0][1]["$set"]
    assert case_set["captured_serial"] == "LF-22-99999-Z"


def test_capture_serial_skips_equipment_when_no_asset_id():
    """Free-text intake (no `asset_id` on the case) → no equipment
    row to back-fill. The case still stamps cleanly."""
    from routes.svc.engineer_phase3 import capture_serial, CaptureSerialIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=_case({
        "asset_id": "",
    }))
    fdb.svc_cases.update_one = AsyncMock()
    fdb.equipment.find_one = AsyncMock()
    fdb.equipment.update_one = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            return await capture_serial(
                case_id="case-1",
                body=CaptureSerialIn(serial="LF-22-77777-Q"),
                user=_eng(),
            )

    out = _run(go())
    fdb.equipment.find_one.assert_not_called()
    assert out["equipment_updated"] is False


def test_capture_serial_appends_audit_event():
    """Event log must record the capture (kind, serial, photo id,
    equipment-update outcome) so admins can audit who fixed what."""
    from routes.svc.engineer_phase3 import capture_serial, CaptureSerialIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=_case())
    fdb.svc_cases.update_one = AsyncMock()
    fdb.equipment.find_one = AsyncMock(return_value=None)
    appended = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", appended):
            await capture_serial(
                case_id="case-1",
                body=CaptureSerialIn(serial="LF-X", photo_file_id="f1"),
                user=_eng(),
            )

    _run(go())
    assert appended.await_count == 1
    kwargs = appended.await_args.kwargs
    assert kwargs["event_type"] == "serial_captured"
    assert "LF-X" in kwargs["body"]
    assert kwargs["extra"]["kind"] == "serial_captured"
    assert kwargs["extra"]["serial"] == "LF-X"
    assert kwargs["extra"]["photo_file_id"] == "f1"


# ── Frontend ──────────────────────────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_equipment_tab_renders_capture_serial_card_when_required():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Component + its testids.
    assert "function CaptureSerialCard" in src
    assert 'data-testid="capture-serial-card"' in src
    assert 'data-testid="capture-serial-input"' in src
    assert 'data-testid="capture-serial-photo"' in src
    assert 'data-testid="capture-serial-submit"' in src
    assert 'data-testid="capture-serial-reason"' in src
    # Gated on the case flag — card hidden when False/missing.
    assert "job?.capture_serial_required ? (" in src
    # Calls the new backend endpoint.
    assert "/svc/engineer/jobs/${job.id}/capture-serial" in src


def test_capture_serial_card_handles_all_three_reasons():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    for slug, label in (
        ("rubbed_off", "Plate rubbed off / unreadable"),
        ("not_visible", "Plate not visible / behind cladding"),
        ("never_had_one", "Machine has no serial plate"),
    ):
        assert slug in src, f"reason slug {slug} missing"
        assert label in src, f"reason label '{label}' missing"
