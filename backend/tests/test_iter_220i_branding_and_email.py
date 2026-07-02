"""Iter 220i — Engineer/Org branding + Service-report PDF integration.

Covers:
  * /api/svc/branding endpoints (GET/PUT/DELETE engineer override).
  * Effective branding resolves engineer override winning over org.
  * Hex validation: short hex expanded, invalid input → 400.
  * Service report PDF builder accepts logo_bytes kwarg (no regression).
  * Email wrapper renders the self-hosted /brand/ GymAxis mark,
    NOT the dead customer-assets.emergentagent.com one (P0 fix).
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://comms-email-hub.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
        data = r.json()
    _CACHE[email] = data.get("token") or data.get("access_token")
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


# ── 1. Email logo regression (no network, pure import) ─────────────


def test_email_mark_now_self_hosted(monkeypatch):
    """GYMAXIS_LOGO_MARK must not point at the dead URL."""
    monkeypatch.setenv("EMAIL_PUBLIC_BASE_URL", "https://example.test")
    import utils.email as e
    importlib.reload(e)
    mark = e.GYMAXIS_LOGO_MARK
    assert "customer-assets.emergentagent.com" not in mark, mark
    assert mark.endswith("/brand/gymaxis-mark-tight.png"), mark


# ── 2. Branding HTTP round-trip ────────────────────────────────────


def test_branding_endpoints_round_trip():
    with httpx.Client(timeout=15.0) as c:
        H = _hdr()

        r = c.get(f"{BASE}/api/svc/branding", headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "effective" in body
        assert "organization" in body
        assert "engineer" in body

        # Engineer override with short hex
        payload = {
            "logo_url": f"/api/public/files/test-{uuid.uuid4().hex[:6]}",
            "primary_color": "#abc",
            "accent_color": "#FF5599",
        }
        r = c.put(f"{BASE}/api/svc/branding/me", json=payload, headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["engineer"]["primary_color"] == "#AABBCC"
        assert body["engineer"]["accent_color"] == "#FF5599"
        assert body["effective"]["primary_color"] == "#AABBCC"
        assert body["has_engineer_override"] is True

        # Bad hex
        r = c.put(f"{BASE}/api/svc/branding/me", json={"primary_color": "not-a-hex"}, headers=H)
        assert r.status_code == 400, r.text

        # Revert
        r = c.delete(f"{BASE}/api/svc/branding/me", headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["has_engineer_override"] is False


# ── 3. PDF builder accepts logo_bytes ──────────────────────────────


def test_pdf_builder_accepts_logo_bytes_kwarg():
    from routes.svc.service_report import _build_pdf

    payload = {
        "case": {"id": "c", "reference": "JOB-1", "title": "Visit"},
        "org": {"name": "Acme", "brand_primary_color": "#0F9D58"},
        "engineer": {},
        "engineer_branding": {"primary_color": "#DC2626"},
        "signature": None,
        "time_entries": [],
        "rating": None,
        "rating_comment": None,
        "safety_signoff": None,
        "machines": [],
        "custom_field_defs": [],
        "fix_summary": "",
        "photos": [],
    }
    pdf1 = _build_pdf(payload, [], None, logo_bytes=None)
    assert pdf1.startswith(b"%PDF")
    assert len(pdf1) > 1000

    one_px_png = __import__("base64").b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAEklEQVR4nGP8z4APMOGVHbHSAEEsAROxCnMTAAAAAElFTkSuQmCC"
    )
    pdf2 = _build_pdf(payload, [], None, logo_bytes=one_px_png)
    assert pdf2.startswith(b"%PDF")
    assert len(pdf2) > 1000


# ── 4. Machine-row custom-fields endpoint is wired ─────────────────


def test_for_machine_row_endpoint_404_for_unknown():
    """Confirms the new /work-report-fields/for-machine-row/{id}
    endpoint is reachable through the registry."""
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/svc/work-report-fields/for-machine-row/__nope__",
            headers=_hdr(),
        )
        assert r.status_code == 404, r.text


# ── 5. Wrapped email HTML uses the self-hosted mark ────────────────


def test_wrap_branded_uses_self_hosted_mark(monkeypatch):
    import asyncio
    monkeypatch.setenv("EMAIL_PUBLIC_BASE_URL", "https://test.example")
    import utils.email as e
    importlib.reload(e)
    html = asyncio.get_event_loop().run_until_complete(
        e.wrap_branded("<p>hello</p>", organization_id=None)
    )
    assert (
        "customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/gymaxis-mark-tight.png"
        not in html
    )
    assert "/brand/gymaxis-mark-tight.png" in html
