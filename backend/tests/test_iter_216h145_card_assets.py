"""Iter 216h145 — Supplier-card QR (SVG) + printable PDF tests."""
import os
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://fitness-onboarding-3.preview.emergentagent.com").rstrip("/")


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def tok():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")["token"]


def test_card_svg_returns_svg(tok):
    r = requests.get(f"{API}/api/svc/engineer/intake-card.svg",
                     headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("image/svg+xml")
    body = r.content
    assert body.startswith(b"<?xml") or body.startswith(b"<svg")
    assert b"<svg" in body
    assert len(body) > 200  # not an empty stub


def test_card_pdf_returns_pdf(tok):
    r = requests.get(f"{API}/api/svc/engineer/intake-card.pdf",
                     headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "") == "application/pdf"
    # PDF magic
    assert r.content[:4] == b"%PDF"
    # Reasonable size for a single A6 page
    assert 2000 < len(r.content) < 200000
    # filename hint
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()
    assert ".pdf" in cd.lower()


def test_card_svg_requires_auth():
    r = requests.get(f"{API}/api/svc/engineer/intake-card.svg", timeout=10)
    assert r.status_code in (401, 403)


def test_card_pdf_requires_auth():
    r = requests.get(f"{API}/api/svc/engineer/intake-card.pdf", timeout=10)
    assert r.status_code in (401, 403)
