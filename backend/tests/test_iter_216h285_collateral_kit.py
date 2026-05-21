"""Iter 216h285 — Referral collateral kit (Gap 6).

Closes Gap 6 from the BA audit: engineers had a raw URL but no
professional collateral to share. The new endpoint returns one of
three branded assets generated in-memory from the partner's name +
referral code:

* ``qr-poster``   — A4 portrait PNG with a large QR code (for printing).
* ``social-card`` — 1200×630 PNG (Instagram, LinkedIn, link previews).
* ``pdf-pitch``   — single-page A4 PDF the engineer can email to a gym.

These tests pin:
* Pure generator returns valid PNG / PDF bytes
* Each output embeds the referral code visually (we don't crack
  the rendered glyphs, but file size sanity-checks the QR-payload
  branch by comparing different codes produce different bytes)
* Unknown kind raises
* Endpoint enforces approved status + valid kind
* Non-partners get a clean 404
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.partner_collateral import (
    COLLATERAL_KINDS,
    generate,
    generate_pdf_pitch,
    generate_qr_poster,
    generate_social_card,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user():
    return {"id": "u-jane", "organization_id": "gymaxis-ai-admin"}


# ── Generator output sanity ───────────────────────────────────────


def test_qr_poster_returns_valid_png_bytes():
    data = generate_qr_poster("Jane Doe", "GYM-JANE", "https://gymaxisai.com/signup?ref=GYM-JANE")
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert 50_000 < len(data) < 500_000  # A4@150 DPI PNG sanity range


def test_social_card_returns_valid_png_bytes():
    data = generate_social_card("Tom S", "GYM-TOM", "https://gymaxisai.com/signup?ref=GYM-TOM")
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert 20_000 < len(data) < 300_000


def test_pdf_pitch_returns_valid_pdf_bytes():
    data = generate_pdf_pitch("Sue R", "GYM-SUE", "https://gymaxisai.com/signup?ref=GYM-SUE")
    assert data.startswith(b"%PDF-")
    assert b"%%EOF" in data[-32:]
    assert 5_000 < len(data) < 200_000


def test_different_codes_produce_different_outputs():
    """Sanity check the personalisation actually fires — QR encodes the
    URL, so two different codes must produce two different files."""
    a = generate_qr_poster("Jane", "AAA", "https://gymaxisai.com/signup?ref=AAA")
    b = generate_qr_poster("Jane", "BBB", "https://gymaxisai.com/signup?ref=BBB")
    assert a != b


def test_generate_dispatches_to_correct_kind():
    for kind in COLLATERAL_KINDS:
        data, mime, filename = generate(kind, "Jane", "GYM-X", "https://x.io/?ref=GYM-X")
        assert data
        if kind == "pdf-pitch":
            assert mime == "application/pdf"
            assert filename.endswith(".pdf")
        else:
            assert mime == "image/png"
            assert filename.endswith(".png")


def test_generate_rejects_unknown_kind():
    with pytest.raises(ValueError) as exc:
        generate("hologram", "Jane", "GYM-X", "https://x.io/")
    assert "Unknown collateral kind" in str(exc.value)


# ── Endpoint behaviour ────────────────────────────────────────────


def test_endpoint_returns_attachment_response_with_filename():
    from routes.partners import get_my_collateral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane", "status": "approved",
        "referral_code": "GYM-JANE", "full_name": "Jane Doe",
    })
    with patch("routes.partners.db", fake_db):
        resp = _run(get_my_collateral("qr-poster", user=_user()))
    assert resp.status_code == 200
    assert resp.media_type == "image/png"
    assert 'filename="gymaxis-qr-poster-GYM-JANE.png"' in resp.headers["content-disposition"]
    assert len(resp.body) > 1000
    assert resp.headers["cache-control"].startswith("private")


def test_endpoint_rejects_unknown_kind():
    from routes.partners import get_my_collateral
    with pytest.raises(Exception) as exc:
        _run(get_my_collateral("dancing-bear", user=_user()))
    assert "Unknown collateral kind" in str(exc.value.detail)


def test_endpoint_blocks_non_approved_partner():
    from routes.partners import get_my_collateral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane", "status": "pending",
        "referral_code": "X", "full_name": "Jane",
    })
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(get_my_collateral("pdf-pitch", user=_user()))
    assert "Approved partners only" in str(exc.value.detail)


def test_endpoint_404s_for_non_partner():
    from routes.partners import get_my_collateral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(get_my_collateral("pdf-pitch", user=_user()))
    assert "apply first" in str(exc.value.detail)


def test_collateral_kinds_constant_is_stable():
    """If we ever extend the kinds, the front-end button strip needs
    to know. Pin the current 3 so a renaming breaks the test and
    forces a coordinated update."""
    assert tuple(COLLATERAL_KINDS) == ("qr-poster", "social-card", "pdf-pitch")
