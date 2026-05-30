"""Iter 220cw — Voice-to-job endpoint.

Pins ``POST /api/svc/engineer/ai/voice-to-job``:

* Validates the audio mime + size (same gate as `/transcribe` and
  `/dictate-summary`).
* Whisper-transcribes via the existing helper (mocked here).
* Hands the transcript to the existing GPT-5.2 email-parse extractor
  (mocked here) so the field shape matches what the New Job form
  already knows how to consume.
* Returns ``{transcript, parsed, raw}`` — what the
  ``VoiceToJobButton`` stashes in sessionStorage.
"""
from __future__ import annotations

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1"):
    return {"id": uid, "organization_id": org, "email": "e@x"}


def _audio_upload(content_type="audio/webm", body: bytes = b"\x00" * 2048):
    """Build a FastAPI UploadFile carrying fake audio bytes."""
    bio = BytesIO(body)
    return UploadFile(
        file=bio, filename="dictation.webm",
        headers={"content-type": content_type},
    )


def test_voice_to_job_returns_transcript_and_parsed_fields():
    """Happy path: whisper returns a sentence, the parser pulls out
    customer + fault + priority."""
    transcript = (
        "Treadmill four at Acme Gym belt slipping, customer Sarah on "
        "07700 900123, priority P2 please."
    )
    parsed_fields = {
        "customer_name": "Sarah",
        "customer_phone": "07700 900123",
        "site_name": "Acme Gym",
        "title": "Treadmill 4 belt slipping",
        "description": "Treadmill 4 belt slipping; customer Sarah; priority P2.",
        "priority": "P2",
    }

    async def run():
        with patch(
            "routes.svc.engineer_ai._transcribe_audio",
            AsyncMock(return_value=transcript),
        ), patch(
            "routes.svc.engineer_ai._log_call", AsyncMock(),
        ), patch(
            "routes.svc.independence.jobs_parse_email",
            AsyncMock(return_value={"parsed": parsed_fields, "raw": "…"}),
        ):
            from routes.svc.engineer_ai import voice_to_job
            return await voice_to_job(audio=_audio_upload(), user=_user())

    out = _run(run())
    assert out["transcript"] == transcript
    assert out["parsed"]["customer_name"] == "Sarah"
    assert out["parsed"]["priority"] == "P2"
    assert out["parsed"]["site_name"] == "Acme Gym"
    assert "raw" in out  # transparency for debugging


def test_voice_to_job_rejects_unsupported_mime():
    async def run():
        from routes.svc.engineer_ai import voice_to_job
        try:
            await voice_to_job(
                audio=_audio_upload(content_type="application/pdf"),
                user=_user(),
            )
            pytest.fail("should have raised")
        except HTTPException as exc:
            assert exc.status_code == 415

    _run(run())


def test_voice_to_job_rejects_oversized_audio():
    """26 MB > 20 MB cap → 413."""
    big = b"\x00" * (26 * 1024 * 1024)

    async def run():
        from routes.svc.engineer_ai import voice_to_job
        try:
            await voice_to_job(
                audio=_audio_upload(body=big),
                user=_user(),
            )
            pytest.fail("should have raised")
        except HTTPException as exc:
            assert exc.status_code == 413

    _run(run())


def test_voice_to_job_422s_on_empty_transcript():
    """Whisper returned silence → 422 with a clear retry hint."""

    async def run():
        with patch(
            "routes.svc.engineer_ai._transcribe_audio",
            AsyncMock(return_value=""),
        ), patch(
            "routes.svc.engineer_ai._log_call", AsyncMock(),
        ):
            from routes.svc.engineer_ai import voice_to_job
            try:
                await voice_to_job(audio=_audio_upload(), user=_user())
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 422

    _run(run())


def test_voice_to_job_soft_fails_on_parse_error():
    """If the GPT extractor itself raises, we still return the
    transcript so the engineer doesn't lose their dictation."""

    async def run():
        with patch(
            "routes.svc.engineer_ai._transcribe_audio",
            AsyncMock(return_value="something useful happened"),
        ), patch(
            "routes.svc.engineer_ai._log_call", AsyncMock(),
        ), patch(
            "routes.svc.independence.jobs_parse_email",
            AsyncMock(side_effect=RuntimeError("LLM down")),
        ):
            from routes.svc.engineer_ai import voice_to_job
            return await voice_to_job(audio=_audio_upload(), user=_user())

    out = _run(run())
    assert out["transcript"] == "something useful happened"
    assert out["parsed"] == {}
    assert out["raw"] == ""


def test_voice_to_job_endpoint_is_registered():
    """Path-on-router contract guard so a refactor that renames it
    breaks loud."""
    from routes.svc.engineer_ai import router
    paths = [
        (r.path, sorted(r.methods))
        for r in router.routes if hasattr(r, "path")
    ]
    assert any(
        p.endswith("/voice-to-job") and "POST" in m for p, m in paths
    ), "POST /svc/engineer/ai/voice-to-job must be registered."
