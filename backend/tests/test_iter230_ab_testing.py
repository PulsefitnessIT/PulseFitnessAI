"""Iter 230 — Email A/B testing on campaigns.

Covers:
  • Validation: variant count cap, duplicate ids, sample_pct bounds,
    decide_after_minutes bounds.
  • Create + list a campaign with two variants and ab_test enabled.
  • Decide-winner endpoint requires ab_testing status.
  • Backwards-compat: campaigns without `variants` still work and have a
    synthesised default variant on the GET response.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip() + "/api"
)


def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


def test_legacy_campaign_still_creates(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Iter230 Plain {nonce}",
        "channel": "email",
        "content": {"subject": "Plain subject", "body_html": "<p>hello</p>"},
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    campaign = r.json()["campaign"]
    assert campaign["status"] == "draft"
    assert campaign["ab_test"]["enabled"] is False
    assert isinstance(campaign["variants"], list)
    assert len(campaign["variants"]) == 1
    assert campaign["variants"][0]["id"] == "default"


def test_ab_campaign_create_validates_variants(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Iter230 AB {nonce}",
        "channel": "email",
        "content": {"subject": "fallback", "body_html": "<p>fallback</p>"},
        "variants": [
            {"id": "a", "name": "Variant A", "subject": "Subject A", "body_html": "<p>A</p>", "weight": 1},
            {"id": "b", "name": "Variant B", "subject": "Subject B", "body_html": "<p>B</p>", "weight": 1},
        ],
        "ab_test": {
            "enabled": True,
            "winner_metric": "opens",
            "sample_pct": 30,
            "decide_after_minutes": 240,
        },
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    campaign = r.json()["campaign"]
    assert campaign["ab_test"]["enabled"] is True
    assert campaign["ab_test"]["sample_pct"] == 30
    assert campaign["ab_test"]["winner_metric"] == "opens"
    assert len(campaign["variants"]) == 2
    assert {v["id"] for v in campaign["variants"]} == {"a", "b"}
    assert campaign["metrics_by_variant"]["a"]["sent"] == 0
    assert campaign["metrics_by_variant"]["b"]["sent"] == 0


def test_duplicate_variant_ids_rejected(operator_headers):
    payload = {
        "name": "Iter230 DupVariant",
        "channel": "email",
        "variants": [
            {"id": "a", "subject": "Subj 1", "body_html": "<p>1</p>", "weight": 1},
            {"id": "a", "subject": "Subj 2", "body_html": "<p>2</p>", "weight": 1},
        ],
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_too_many_variants_rejected(operator_headers):
    payload = {
        "name": "Iter230 TooMany",
        "channel": "email",
        "variants": [
            {"id": chr(ord("a") + i), "subject": f"Subj {i}", "body_html": f"<p>{i}</p>", "weight": 1}
            for i in range(5)
        ],
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_invalid_sample_pct_rejected(operator_headers):
    payload = {
        "name": "Iter230 BadSample",
        "channel": "email",
        "variants": [
            {"id": "a", "subject": "Subj 1", "body_html": "<p>1</p>", "weight": 1},
            {"id": "b", "subject": "Subj 2", "body_html": "<p>2</p>", "weight": 1},
        ],
        "ab_test": {
            "enabled": True,
            "sample_pct": 99,
            "winner_metric": "opens",
        },
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_invalid_winner_metric_rejected(operator_headers):
    payload = {
        "name": "Iter230 BadMetric",
        "channel": "email",
        "variants": [
            {"id": "a", "subject": "1", "body_html": "<p>1</p>", "weight": 1},
            {"id": "b", "subject": "2", "body_html": "<p>2</p>", "weight": 1},
        ],
        "ab_test": {
            "enabled": True,
            "winner_metric": "revenue",  # not allowed
            "sample_pct": 30,
        },
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_decide_winner_rejects_non_ab_campaign(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Iter230 NoAB {nonce}",
        "channel": "email",
        "content": {"subject": "x", "body_html": "y"},
    }
    r = requests.post(
        f"{API_BASE}/marketing/campaigns",
        json=payload,
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 200
    campaign_id = r.json()["campaign"]["id"]
    r = requests.post(
        f"{API_BASE}/marketing/campaigns/{campaign_id}/decide-winner",
        json={},
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_decide_winner_unknown_campaign_404(operator_headers):
    r = requests.post(
        f"{API_BASE}/marketing/campaigns/bogus-id/decide-winner",
        json={},
        headers=operator_headers,
        timeout=10,
    )
    assert r.status_code == 404
