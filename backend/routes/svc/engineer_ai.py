"""Iter 216h134 — Engineer App AI Report Assistant.

Voice-to-text dictation for the engineer's Complete tab work summary.

Flow:
  1. Engineer holds the mic button in the PWA, captures a short audio
     blob (webm/opus on most browsers).
  2. Frontend posts the audio multipart to this backend.
  3. We transcribe with OpenAI Whisper via `emergentintegrations`
     (model "whisper-1"), using the Emergent LLM Key.
  4. We rewrite the raw transcript via GPT-5.2 (also via
     emergentintegrations) into a tight, professional UK-English
     service report summary.
  5. Both raw + polished text are returned so the engineer can pick.

Endpoints (gated by `require_engineer_app_access`):
  • POST /api/svc/engineer/ai/transcribe
      Multipart: `audio` (file). Optional `case_id` for usage logging.
      Returns `{ transcript: str, duration_seconds?: float }`.
  • POST /api/svc/engineer/ai/rewrite-summary
      Body: `{ transcript: str, case_id?: str, hint?: str }`.
      Returns `{ summary: str, transcript: str }`.
  • POST /api/svc/engineer/ai/dictate-summary
      Combines both — single round-trip from audio to polished text.

Cost / usage are tracked on the existing `svc_ai_calls` collection
so the master-admin AI Usage panel reflects engineer dictation.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from routes.partners import require_engineer_app_access
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/svc/engineer/ai",
    tags=["Service Ops · Engineer AI Report Assistant"],
    dependencies=[Depends(require_engineer_app_access)],
)


# Models — emergentintegrations strings per playbook
WHISPER_MODEL = "whisper-1"
REWRITE_MODEL = ("openai", "gpt-5.2")  # default per playbook decision rule

MAX_AUDIO_MB = 20  # Whisper limit is 25 MB; cap a bit lower for headroom
ALLOWED_AUDIO_MIME_PREFIXES = ("audio/", "video/webm", "video/mp4")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise HTTPException(503, "AI service not configured (EMERGENT_LLM_KEY missing)")
    return k


async def _log_call(*, organization_id: str | None, kind: str,
                     prompt_chars: int, response_chars: int,
                     latency_ms: int, ok: bool, extra: dict | None = None) -> None:
    try:
        await db.svc_ai_calls.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "kind": kind,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "latency_ms": latency_ms,
            "ok": ok,
            "extra": extra or {},
            "at": _now(),
        })
    except Exception as e:
        logger.warning("ai call log failed: %s", e)


# ──────────────────────────── Whisper ──────────────────────────────


async def _transcribe_audio(file_bytes: bytes, filename: str) -> str:
    """Send the audio buffer to OpenAI Whisper via emergentintegrations.

    Per playbook: `OpenAISpeechToText(api_key=...).transcribe(file=fh,
    model="whisper-1", response_format="json")` and read `.text`.
    """
    from emergentintegrations.llm.openai import OpenAISpeechToText
    stt = OpenAISpeechToText(api_key=_key())
    # Some library versions read the filename to infer mime — keep a
    # well-known extension. We write to a temp file so the library can
    # handle paths/streams identically across versions.
    suffix = "." + (filename.rsplit(".", 1)[-1] if "." in filename else "webm")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.seek(0)
        with open(tmp.name, "rb") as fh:
            try:
                resp = await stt.transcribe(
                    file=fh, model=WHISPER_MODEL,
                    response_format="json", language="en",
                    prompt="Field service engineer dictating a fitness equipment "
                            "repair report. Mentions of belt, motor, console, "
                            "treadmill, lubricant, sensor, drive board, parts SKUs.",
                )
            except Exception as exc:
                logger.warning("[engineer_ai] whisper transcription failed: %s", exc)
                raise HTTPException(502, f"Transcription failed: {exc}")
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise HTTPException(422, "Couldn't pick up any speech — try again in a quieter spot.")
    return text


# ───────────────────────────── Rewrite ─────────────────────────────


REWRITE_SYSTEM_PROMPT = (
    "You are an assistant for a UK fitness-equipment field service engineer. "
    "Rewrite the engineer's spoken work-summary transcript into a concise, "
    "professional report fragment suitable for the customer-facing service "
    "report PDF.\n"
    "Rules:\n"
    "  • UK English spelling (e.g. 'tyre', 'colour', 'litre').\n"
    "  • 60-150 words. Third-person voice — never 'I'.\n"
    "  • Lead with what was diagnosed, then what was repaired/replaced, "
    "then any follow-up advice for the customer.\n"
    "  • Preserve technical terms exactly as the engineer said them "
    "(SKUs, part names, serial numbers) — only fix obvious mistranscriptions.\n"
    "  • If the engineer mentions parts and quantities, list them as "
    "compact 'Replaced: 2 × drive belt (BELT-DRV-001), 1 × motor capacitor' style.\n"
    "  • If there is a follow-up action, end with a single 'Next steps:' line.\n"
    "  • Output the polished text and nothing else — no markdown headers, "
    "no preamble, no closing pleasantries."
)


async def _rewrite_with_gpt(transcript: str, hint: str | None) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    user_text = transcript.strip()
    if hint and hint.strip():
        user_text = f"Context for the visit: {hint.strip()}\n\nTranscript:\n{user_text}"
    chat = LlmChat(
        api_key=_key(),
        session_id=f"engineer-ai-{uuid.uuid4()}",
        system_message=REWRITE_SYSTEM_PROMPT,
    ).with_model(*REWRITE_MODEL)
    try:
        polished = await chat.send_message(UserMessage(text=user_text))
    except Exception as exc:
        logger.warning("[engineer_ai] gpt rewrite failed: %s", exc)
        raise HTTPException(502, f"Rewrite failed: {exc}")
    return (polished or "").strip()


# ──────────────────────────── endpoints ────────────────────────────


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(..., description="Audio file (webm/mp3/wav/m4a, ≤20 MB)"),
    case_id: str | None = Form(default=None),
    user=Depends(get_current_user),
):
    """Whisper transcription only — no polish."""
    if not audio:
        raise HTTPException(400, "audio file required")
    mime = (audio.content_type or "").lower()
    if not any(mime.startswith(p) for p in ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(415, f"Unsupported audio type: {mime or 'unknown'}")
    data = await audio.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_AUDIO_MB:
        raise HTTPException(413, f"Audio too large ({size_mb:.1f} MB > {MAX_AUDIO_MB} MB)")
    start = time.perf_counter()
    text = await _transcribe_audio(data, audio.filename or "audio.webm")
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_call(
        organization_id=user.get("organization_id"),
        kind="engineer_dictation_stt",
        prompt_chars=len(data), response_chars=len(text),
        latency_ms=latency_ms, ok=True,
        extra={"case_id": case_id, "size_mb": round(size_mb, 2)},
    )
    return {"transcript": text}


class RewriteIn(BaseModel):
    transcript: str = Field(..., min_length=2, max_length=8000)
    case_id: str | None = None
    hint: str | None = None


@router.post("/rewrite-summary")
async def rewrite_summary(body: RewriteIn, user=Depends(get_current_user)):
    start = time.perf_counter()
    polished = await _rewrite_with_gpt(body.transcript, body.hint)
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_call(
        organization_id=user.get("organization_id"),
        kind="engineer_dictation_rewrite",
        prompt_chars=len(body.transcript), response_chars=len(polished),
        latency_ms=latency_ms, ok=True,
        extra={"case_id": body.case_id},
    )
    return {"summary": polished, "transcript": body.transcript}


@router.post("/dictate-summary")
async def dictate_summary(
    audio: UploadFile = File(...),
    case_id: str | None = Form(default=None),
    hint: str | None = Form(default=None),
    user=Depends(get_current_user),
):
    """Single round-trip: audio in → polished summary out (+ raw transcript)."""
    mime = (audio.content_type or "").lower()
    if not any(mime.startswith(p) for p in ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(415, f"Unsupported audio type: {mime or 'unknown'}")
    data = await audio.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_AUDIO_MB:
        raise HTTPException(413, f"Audio too large ({size_mb:.1f} MB > {MAX_AUDIO_MB} MB)")
    start = time.perf_counter()
    transcript = await _transcribe_audio(data, audio.filename or "audio.webm")
    polished = await _rewrite_with_gpt(transcript, hint)
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_call(
        organization_id=user.get("organization_id"),
        kind="engineer_dictation_full",
        prompt_chars=len(data), response_chars=len(polished),
        latency_ms=latency_ms, ok=True,
        extra={"case_id": case_id, "transcript_chars": len(transcript),
               "size_mb": round(size_mb, 2)},
    )
    return {"transcript": transcript, "summary": polished}


# Iter 220cw — Voice-to-job. Engineers talk into the mic while
# driving (or one-handed at a customer site); we transcribe with
# Whisper and run the transcript through the existing GPT-5.2
# email-parse extractor so the New Job form auto-fills.
@router.post("/voice-to-job")
async def voice_to_job(
    audio: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Audio in → transcript + parsed job fields out.

    Reuses the proven ``jobs_parse_email`` pipeline (same prompt,
    same JSON schema) so the engineer's spoken brief produces the
    exact same field shape as a pasted customer email.
    """
    mime = (audio.content_type or "").lower()
    if not any(mime.startswith(p) for p in ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(415, f"Unsupported audio type: {mime or 'unknown'}")
    data = await audio.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_AUDIO_MB:
        raise HTTPException(413, f"Audio too large ({size_mb:.1f} MB > {MAX_AUDIO_MB} MB)")
    start = time.perf_counter()
    transcript = await _transcribe_audio(data, audio.filename or "audio.webm")
    if not transcript.strip():
        raise HTTPException(422, "Could not transcribe audio — please try again.")

    # Reuse the email-parse extractor so the field shape matches what
    # the New Job form already knows how to consume.
    from routes.svc.independence import jobs_parse_email, ParseEmailIn
    try:
        # Send a tiny synthesised "email" carrying just the transcript.
        # The extractor is robust enough to find customer / fault / etc.
        parsed_out = await jobs_parse_email(
            body=ParseEmailIn(
                email_body=transcript,
                subject="Voice-to-job (engineer dictation)",
            ),
            user=user,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("[voice-to-job] parse failed: %s", exc)
        # Soft-fail — engineer still gets the transcript, just no parsed fields.
        parsed_out = {"parsed": {}, "raw": ""}

    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_call(
        organization_id=user.get("organization_id"),
        kind="engineer_voice_to_job",
        prompt_chars=len(data), response_chars=len(transcript),
        latency_ms=latency_ms, ok=True,
        extra={"transcript_chars": len(transcript),
               "size_mb": round(size_mb, 2)},
    )
    return {
        "transcript": transcript,
        "parsed": parsed_out.get("parsed") or {},
        "raw": parsed_out.get("raw") or "",
    }


__all__ = ["router"]

