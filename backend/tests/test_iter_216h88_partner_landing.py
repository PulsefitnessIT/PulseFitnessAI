"""Iter 216h88 — Engineer Partner public marketing landing page.

Verifies the two new public routes serve and the public route to apply
remains intact. Frontend-only feature so this is a thin sanity test —
the route is auth-free and renders client-side.
"""
from __future__ import annotations

import os

import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://allocation-wizard-ai.preview.emergentagent.com"
).rstrip("/")


class TestPublicMarketingRoutes:
    def test_partners_engineers_route_returns_html(self):
        r = requests.get(f"{BASE_URL}/partners/engineers", timeout=15, allow_redirects=True)
        assert r.status_code == 200, r.text[:300]
        body = r.text.lower()
        # Index.html shell — react-router will mount the actual content client-side.
        assert "<!doctype html>" in body or "<html" in body

    def test_root_marketing_route_returns_html(self):
        r = requests.get(f"{BASE_URL}/", timeout=15, allow_redirects=True)
        assert r.status_code == 200
        body = r.text.lower()
        assert "<!doctype html>" in body or "<html" in body
