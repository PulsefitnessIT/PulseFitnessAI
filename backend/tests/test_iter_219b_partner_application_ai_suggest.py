"""Iter 219b — AI decision helper for partner applications.

Pins the contract of POST /api/partners/applications/{id}/ai-suggest:
  • 200 with a structured suggestion block (decision/level/confidence
    /headline/reasons/red_flags/coverage_value) when the LLM is up.
  • Same shape from the deterministic fallback when the LLM is down,
    so the FE never has to special-case missing fields.
  • 403 for non master-admin callers.
  • 404 for unknown application id.

Also unit-tests the pure `_fallback()` helper for the three deterministic
branches (reject / needs_info / approve) plus the `verified_partner`
seniority promotion rule.
"""
from __future__ import annotations

import io
import os
import sys
import uuid

import httpx
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.partner_application_ai import _fallback, _coerce, _summarise_roster


BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://maintenance-hub-357.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _login(email: str, password: str) -> str:
    key = f"login::{email}"
    if _CACHE.get(key):
        return _CACHE[key]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
        )
        r.raise_for_status()
    _CACHE[key] = r.json()["token"]
    return _CACHE[key]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


def _non_admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('engineer.smoke@gymaxisai.com', 'EngTest123!')}"}


@pytest.fixture()
def fresh_application_id() -> str:
    cv_bytes = b"%PDF-1.4\nFake CV body for iter 219b tests.\n%%EOF"
    files = {"cv_file": ("cv.pdf", io.BytesIO(cv_bytes), "application/pdf")}
    email = f"iter219b-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "AI Suggest Test Engineer",
        "email": email,
        "phone": "07123456789",
        "service_postcode": "SW1A 1AA",
        "travel_radius_km": "50",
        "brands_supported": "Life Fitness,Technogym",
        "skills": "cardio,strength",
        "qualifications": "C&G Level 3,IPAF",
        "years_experience": "8",
        "has_insurance": "true",
        "insurance_provider": "Hiscox",
        "insurance_expires_at": "2026-12-31",
        "terms_accepted": "true",
        "cover_letter": "8 years of service experience across UK gyms.",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{BASE}/api/partners/public-apply", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()["application_id"]


# ──────────────────────── Endpoint contract ────────────────────────


def test_ai_suggest_returns_structured_payload(fresh_application_id: str):
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{fresh_application_id}/ai-suggest",
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["application_id"] == fresh_application_id
    s = body["suggestion"]
    assert s["decision"] in {"approve", "reject", "needs_info"}
    assert s["level"] in {"engineer_partner", "verified_partner", "strategic_partner"}
    assert 0.0 <= float(s["confidence"]) <= 1.0
    assert isinstance(s["headline"], str) and s["headline"]
    assert isinstance(s["reasons"], list)
    assert isinstance(s["red_flags"], list)
    assert "roster_summary" in s
    assert s["roster_summary"]["total_active_partners"] >= 0


def test_ai_suggest_404_for_unknown_application():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/missing-{uuid.uuid4().hex[:8]}/ai-suggest",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


def test_ai_suggest_403_for_non_admin(fresh_application_id: str):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{fresh_application_id}/ai-suggest",
            headers=_non_admin_headers(),
        )
    assert r.status_code == 403


# ──────────────────── Pure helper unit tests ───────────────────────


def test_fallback_rejects_completely_blank_application():
    out = _fallback({
        "has_insurance": False,
        "attachments": [],
        "qualifications": [],
        "brands_supported": [],
        "cover_letter": "",
        "years_experience": "0",
    })
    assert out["decision"] == "reject"
    assert any("insurance" in r.lower() for r in out["red_flags"])
    assert out["model"] == "deterministic-fallback"


def test_fallback_needs_info_when_partial():
    out = _fallback({
        "has_insurance": False,
        "attachments": [{"id": "a"}],
        "qualifications": ["IPAF"],
        "brands_supported": ["Life Fitness"],
        "cover_letter": "Some context.",
        "years_experience": "3",
    })
    # missing insurance triggers a red flag → needs_info path
    assert out["decision"] == "needs_info"


def test_fallback_promotes_to_verified_partner_when_seasoned():
    out = _fallback({
        "has_insurance": True,
        "attachments": [{"id": "a"}, {"id": "b"}],
        "qualifications": ["IPAF", "IOSH"],
        "brands_supported": ["Life Fitness", "Technogym"],
        "cover_letter": "Senior engineer.",
        "years_experience": "10",
    })
    assert out["decision"] == "approve"
    assert out["level"] == "verified_partner"


def test_coerce_clamps_out_of_range_confidence():
    out = _coerce({
        "decision": "approve",
        "level": "engineer_partner",
        "confidence": 9.0,
        "headline": "h",
        "reasons": ["r1", "r2"],
        "red_flags": [],
        "coverage_value": "ok",
    })
    assert out["confidence"] == 1.0


def test_coerce_falls_back_on_unknown_decision():
    out = _coerce({"decision": "fire-them", "level": "engineer_partner", "confidence": 0.5})
    assert out["decision"] == "needs_info"


def test_summarise_roster_buckets_brands_and_postcodes():
    snap = _summarise_roster([
        {"brands_supported": ["Life Fitness", "Technogym"], "service_postcode": "SW1A 1AA"},
        {"brands_supported": ["Life Fitness"], "service_postcode": "SW1B 2BB"},
        {"brands_supported": ["Matrix"], "service_postcode": "LS1 1AB"},
    ])
    brand_map = {b["brand"]: b["partners"] for b in snap["brand_coverage"]}
    assert brand_map["Life Fitness"] == 2
    assert brand_map["Technogym"] == 1
    assert brand_map["Matrix"] == 1
    pc_map = {p["area"]: p["partners"] for p in snap["postcode_coverage"]}
    assert pc_map["SW1A"] == 1
    assert pc_map["SW1B"] == 1
    assert pc_map["LS1"] == 1
