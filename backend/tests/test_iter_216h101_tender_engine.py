"""Tender Engine v2 regression tests (iter 216h101).

Validates:
  * Document text extraction utilities (pypdf / docx / xlsx).
  * Retrieval ranking.
  * Pulse bid library seed idempotency.
  * Suggest-snippets endpoint.
  * Tender submission + pitch deck PDF generation (smoke — valid PDF
    header bytes + non-trivial size).
"""
from __future__ import annotations

import io
import os

import requests

from tests.conftest import _test_backend_url

API = _test_backend_url() + "/api"

CRM_EMAIL = os.environ.get("TEST_CRM_USER", "craig.henshall@pulsefitness.com")
CRM_PASSWORD = os.environ.get("TEST_CRM_PASSWORD", "Test123!")


def _crm_login() -> str:
    """CRM has its own auth at /crm/auth/login."""
    r = requests.post(
        f"{API}/crm/auth/login",
        json={"email": CRM_EMAIL, "password": CRM_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    return body.get("token") or body.get("access_token")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _hg(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Document extractor utils (pure functions) ─────────────────────────


def test_chunk_text_window_and_overlap():
    from utils.document_extractor import chunk_text
    text = "abc " * 1000  # ~4000 chars
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) >= 4
    # Each chunk respects cap.
    assert all(len(c) <= 1000 for c in chunks)


def test_retrieve_relevant_ranks_keyword_matches():
    from utils.document_extractor import retrieve_relevant
    cands = [
        {"text": "Cats and dogs are common pets in the UK."},
        {"text": "The mitochondrion is the powerhouse of the cell."},
        {"text": "Health and safety RAMS govern site visits for engineers."},
        {"text": "Sustainability targets aligned to SBTi reduction plan."},
    ]
    top = retrieve_relevant("health and safety RAMS engineer", cands, top_k=2)
    assert top, "retrieval returned no results"
    assert top[0]["text"].startswith("Health and safety RAMS")


def test_extract_text_returns_empty_for_unknown_format():
    from utils.document_extractor import extract_text
    assert extract_text("foo.xyz", "application/octet-stream", b"random") == ""
    assert extract_text("foo.txt", "text/plain", b"hello world") == "hello world"


# ── PDF exporters (build_*_pdf shouldn't crash and produces valid PDFs) ──


def test_submission_pdf_smoke():
    from utils.tender_pdf_exporter import build_submission_pdf
    pdf = build_submission_pdf(
        {"title": "Smoke ITT", "type": "ITT", "issuer": "QA Co", "deadline": "2026-06-30"},
        [
            {"order": 1, "category": "health_safety", "text": "How do you manage RAMS?", "response": "We do X, Y and Z.", "word_limit": 500, "weighting": 10},
        ],
        {"company_name": "Pulse Fitness", "primary_color": "#19CDFF"},
    )
    assert pdf.startswith(b"%PDF-"), "submission PDF header missing"
    assert len(pdf) > 1500


def test_pitch_pdf_smoke():
    from utils.tender_pdf_exporter import build_pitch_deck_pdf
    pdf = build_pitch_deck_pdf(
        {"title": "Smoke Pitch", "issuer": "QA Co"},
        {"company_name": "Pulse Fitness", "primary_color": "#19CDFF"},
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 3000, "pitch deck unexpectedly small"


# ── End-to-end via the CRM API ───────────────────────────────────────


def test_pulse_bid_library_seed_is_idempotent():
    token = _crm_login()
    r1 = requests.post(f"{API}/crm/v2/knowledge-base/seed-pulse-defaults", headers=_h(token), timeout=20)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{API}/crm/v2/knowledge-base/seed-pulse-defaults", headers=_h(token), timeout=20)
    assert r2.status_code == 200, r2.text
    # Re-run skips everything that was just seeded.
    assert r2.json()["seeded"] == 0 and r2.json()["skipped"] >= r1.json()["seeded"]


def test_tender_create_question_suggest_snippets_export():
    token = _crm_login()
    # Ensure KB is populated for retrieval to have material.
    requests.post(f"{API}/crm/v2/knowledge-base/seed-pulse-defaults", headers=_h(token), timeout=20)

    create = requests.post(
        f"{API}/crm/v2/tenders",
        headers=_h(token),
        json={"title": "QA Smoke ITT", "type": "ITT", "issuer": "QA", "deadline": "2026-12-31"},
        timeout=15,
    )
    assert create.status_code == 200, create.text
    tid = create.json()["id"]

    q = requests.post(
        f"{API}/crm/v2/tenders/{tid}/questions",
        headers=_h(token),
        json={"text": "Describe ISO 9001 quality management implementation across multi-site contracts.", "category": "compliance", "word_limit": 400, "order": 1},
        timeout=15,
    )
    assert q.status_code == 200, q.text
    qid = q.json()["id"]

    sugg = requests.post(
        f"{API}/crm/v2/tenders/{tid}/questions/{qid}/ai/suggest-snippets",
        headers=_h(token),
        timeout=20,
    )
    assert sugg.status_code == 200, sugg.text
    suggestions = sugg.json().get("suggestions", [])
    assert len(suggestions) >= 1, "expected at least one KB suggestion from the seeded library"
    # The top result should be the ISO 9001 entry given the question.
    titles = " ".join([s["title"] for s in suggestions])
    assert "ISO 9001" in titles

    # Export PDFs
    sub_r = requests.get(f"{API}/crm/v2/tenders/{tid}/export/submission", headers=_hg(token), timeout=30)
    assert sub_r.status_code == 200, sub_r.text
    assert sub_r.content.startswith(b"%PDF-")
    assert int(sub_r.headers.get("content-length", len(sub_r.content))) > 1500

    pitch_r = requests.get(f"{API}/crm/v2/tenders/{tid}/export/pitch", headers=_hg(token), timeout=30)
    assert pitch_r.status_code == 200, pitch_r.text
    assert pitch_r.content.startswith(b"%PDF-")
    assert int(pitch_r.headers.get("content-length", len(pitch_r.content))) > 3000


def test_parse_from_doc_rejects_image_only_pdf():
    token = _crm_login()
    create = requests.post(
        f"{API}/crm/v2/tenders",
        headers=_h(token),
        json={"title": "QA Parse-from-doc ITT", "type": "ITT", "issuer": "QA"},
        timeout=15,
    )
    tid = create.json()["id"]
    # Synthesize a "doc" with empty extracted_text by uploading a binary file
    # whose text-extraction yields no characters (a 1KB PNG-like payload).
    files = {"file": ("scan.bin", io.BytesIO(b"\x00" * 1024), "application/octet-stream")}
    up = requests.post(f"{API}/crm/v2/tenders/{tid}/documents", headers=_hg(token), files=files, data={"category": "rfp"}, timeout=20)
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]
    r = requests.post(
        f"{API}/crm/v2/tenders/{tid}/ai/parse-from-doc",
        headers=_h(token),
        json={"doc_id": doc_id},
        timeout=20,
    )
    assert r.status_code == 422
    assert "scanned" in r.json().get("detail", "").lower() or "image" in r.json().get("detail", "").lower()
