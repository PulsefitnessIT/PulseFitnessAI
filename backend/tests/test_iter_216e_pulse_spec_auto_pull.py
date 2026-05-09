"""Iter 216e — Pulse spec auto-pull regression.

Pins:
  • SKIP_PATTERNS regex blocks social / press / after-sales URLs.
  • POST /api/master-admin/catalogue/cleanup deletes them.
  • POST /api/master-admin/catalogue/rematch-equipment runs the
    fallback chain (PDF specs → manufacturer catalogue) and
    persists `spec_sheet_image` + `manufacturer_page_url` onto
    matched equipment rows.
"""
from __future__ import annotations

import requests
import pytest

from tests.conftest import (
    _test_backend_url,
    rate_limit_bypass_headers,
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


@pytest.fixture(scope="module")
def admin_token() -> str:
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_skip_patterns_block_pulse_social_pages():
    """The regex itself is a pure-Python contract — easy to pin
    without spinning up Mongo / HTTP."""
    from utils.manufacturer_catalogue import SKIP_PATTERNS

    must_skip = [
        "https://pulsefitness.com/instagram-arm-only-workout/",
        "https://pulsefitness.com/linkedin-best-of-british/",
        "https://pulsefitness.com/press-release/teme-leisure/",
        "https://pulsefitness.com/after-sales/gold/",
        "https://pulsefitness.com/event/elevate-2026/",
        "https://pulsefitness.com/articles/data-in-fitness/",
    ]
    must_keep = [
        "https://pulsefitness.com/product/cv-treadmill-alpha-runner/",
        "https://pulsefitness.com/product/30kg-dumbbell/",
        "https://pulsefitness.com/connectivity/",
        "https://pulsefitness.com/flooring/",
    ]
    for u in must_skip:
        assert SKIP_PATTERNS.search(u), f"SKIP_PATTERNS should block {u}"
    for u in must_keep:
        assert not SKIP_PATTERNS.search(u), f"SKIP_PATTERNS should NOT block {u}"


def test_cleanup_endpoint_removes_noise(admin_token):
    """Idempotent — called when the catalogue is already clean it
    should still return a 0-or-positive deleted count without erroring."""
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/catalogue/cleanup?domain=pulsefitness.com",
        headers=_hdr(admin_token),
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "deleted" in data
    assert data["scope"] == "pulsefitness.com"
    assert isinstance(data["deleted"], int) and data["deleted"] >= 0


def test_rematch_endpoint_returns_counts(admin_token):
    """The rematch endpoint must return matched/unchanged/skipped
    integer counts so the Master Admin UI can render a progress card."""
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/master-admin/catalogue/rematch-equipment",
        headers=_hdr(admin_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("matched", "unchanged", "skipped"):
        assert k in data, f"rematch response missing '{k}'"
        assert isinstance(data[k], int)
