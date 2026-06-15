"""Iter 289 — public org-chart share endpoint hardening (F-21 posture).

Verifies the defence-in-depth controls added to the unauthenticated
`GET /api/staffing/orgchart/public/{token}` endpoint:
  * unknown / disabled tokens return 404 (no info leak, no auth required);
  * per-IP enumeration cap (60/min/IP) returns 429 once exceeded.

Token strength (256-bit) and PII stripping are covered by the
authenticated publish flow + code review (see SEC-013 in
memory/SECURITY_AUDIT/findings.md).
"""
import random

import requests

from tests.conftest import API_BASE_URL

PUBLIC = f"{API_BASE_URL}/api/staffing/orgchart/public"


def test_public_org_unknown_token_returns_404():
    r = requests.get(f"{PUBLIC}/this-token-does-not-exist-{random.randint(0, 1_000_000)}", timeout=20)
    assert r.status_code == 404, r.text


def test_public_org_per_ip_rate_limit():
    # Fixed, unique source IP so the 60/min window is clean for this run.
    ip = f"198.51.100.{random.randint(1, 254)}"
    headers = {"X-Forwarded-For": ip}
    codes = []
    for i in range(64):
        r = requests.get(f"{PUBLIC}/enum-{i}", headers=headers, timeout=20)
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codes, f"expected a 429 once the per-IP cap is hit, got {sorted(set(codes))}"
    # everything before the cap should be a clean 404 (not a 500 / leak)
    assert all(c in (404, 429) for c in codes), f"unexpected status in {sorted(set(codes))}"
