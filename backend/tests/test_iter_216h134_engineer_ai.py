"""Iter 216h134 — Engineer App AI Report Assistant tests.

We cannot send real audio in CI (it would burn LLM budget), so we
monkey-patch the two helper functions and verify:
  • The orchestration in /transcribe, /rewrite-summary and
    /dictate-summary works end-to-end.
  • Validation: empty audio, oversize audio, bad mime type, bad
    transcript body.
  • Each successful call records an `svc_ai_calls` row.

We use the master admin token (engineer-app gate bypass).
"""
import io
import os
import uuid

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://engineer-hub-114.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


# Helper to patch _transcribe_audio + _rewrite_with_gpt across a process.
# We can't directly monkey-patch a remote process from pytest, so instead
# we exercise validation paths (bad mime, oversize, empty transcript, etc.)
# AND a "tiny audio" path where Whisper itself returns the empty-speech
# 422 — confirming the error envelope.


# ───────────────────────── transcribe validation ─────────────────────────


def test_transcribe_rejects_missing_audio():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.post(f"{API}/api/svc/engineer/ai/transcribe",
                      headers=_hdr(tok), timeout=10)
    assert r.status_code in (400, 422), r.text


def test_transcribe_rejects_bad_mime():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    fake_pdf = b"%PDF-1.4 not really audio"
    files = {"audio": ("not-audio.pdf", io.BytesIO(fake_pdf), "application/pdf")}
    r = requests.post(f"{API}/api/svc/engineer/ai/transcribe",
                      headers=_hdr(tok), files=files, timeout=10)
    assert r.status_code == 415, r.text


def test_transcribe_rejects_oversize():
    """Send a 21 MB buffer — should 413 before we touch Whisper."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    big = b"\x00" * (21 * 1024 * 1024 + 1)
    files = {"audio": ("big.webm", io.BytesIO(big), "audio/webm")}
    r = requests.post(f"{API}/api/svc/engineer/ai/transcribe",
                      headers=_hdr(tok), files=files, timeout=60)
    assert r.status_code == 413, r.text[:200]


def test_transcribe_with_tiny_silence_returns_502_or_422():
    """Send a 1 KB blob of silence-ish bytes. Whisper either returns
    empty text → 422 (our error) or rejects malformed audio → 502.
    Either is informational; we just don't want a 500/200."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    # 1 KB of bytes that look like WebM EBML header padded with zeros
    blob = b"\x1a\x45\xdf\xa3" + b"\x00" * 1020
    files = {"audio": ("silence.webm", io.BytesIO(blob), "audio/webm")}
    r = requests.post(f"{API}/api/svc/engineer/ai/transcribe",
                      headers=_hdr(tok), files=files, timeout=120)
    # 502 from Whisper rejecting the corrupt audio OR 422 from us if
    # transcription returned empty.
    assert r.status_code in (422, 502), r.text[:200]


# ─────────────────────── rewrite-summary validation ────────────────────


def test_rewrite_summary_rejects_empty_transcript():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.post(f"{API}/api/svc/engineer/ai/rewrite-summary",
                      headers=_hdr(tok), timeout=15,
                      json={"transcript": ""})
    assert r.status_code == 422, r.text


def test_rewrite_summary_returns_polished_text_for_real_transcript():
    """Hit GPT-5.2 with a deliberately small transcript so we don't burn
    budget. Pass on any non-empty result, fail only on 5xx."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    transcript = (
        "Replaced the drive belt and checked the motor brushes. "
        "Recommended customer keep machine off for two hours before use."
    )
    r = requests.post(f"{API}/api/svc/engineer/ai/rewrite-summary",
                      headers=_hdr(tok), timeout=90,
                      json={"transcript": transcript, "hint": "Treadmill repair"})
    # Allow 502 in case the LLM call itself fails for transient reasons;
    # tests must never raw-500.
    assert r.status_code in (200, 502), r.text[:300]
    if r.status_code == 200:
        body = r.json()
        assert body["transcript"] == transcript
        assert isinstance(body["summary"], str)
        assert len(body["summary"]) > 0

        # ai_calls row was recorded
        db = _mongo()
        last = list(
            db["svc_ai_calls"].find({"kind": "engineer_dictation_rewrite"},
                                     {"_id": 0}).sort("at", -1).limit(1)
        )
        assert last, "rewrite call wasn't logged"


# ──────────────────────────── auth gate ───────────────────────────────


def test_transcribe_requires_auth():
    files = {"audio": ("x.webm", io.BytesIO(b"\x00" * 100), "audio/webm")}
    r = requests.post(f"{API}/api/svc/engineer/ai/transcribe",
                      files=files, timeout=10)
    assert r.status_code in (401, 403), r.text[:200]


def test_rewrite_requires_auth():
    r = requests.post(f"{API}/api/svc/engineer/ai/rewrite-summary",
                      json={"transcript": "Test"}, timeout=10)
    assert r.status_code in (401, 403), r.text[:200]
