"""Pulse Fitness 1-pager generator — iteration 216."""
from __future__ import annotations

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_sales_pager_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/sales-pack/sales", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403


def test_sales_pager_returns_pdf(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/sales-pack/sales",
        headers=_h(master_admin_token_session),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("Content-Type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000  # real content, not an error blob


def test_trust_pager_returns_pdf(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/sales-pack/trust",
        headers=_h(master_admin_token_session),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("Content-Type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


def test_generate_all_pagers_auto_captures(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    r = requests.post(
        f"{base}/api/master-admin/sales-pack/generate-all",
        headers=headers,
        json={},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    sales_id = body["sales"]["document_id"]
    trust_id = body["trust"]["document_id"]
    assert sales_id and trust_id
    assert body["sales"]["size_bytes"] > 1000
    assert body["trust"]["size_bytes"] > 1000

    # Library should now contain both, and downloading a captured doc
    # should return the same PDF magic bytes.
    list_r = requests.get(
        f"{base}/api/master-admin/document-library?q=Pulse",
        headers=headers,
        timeout=10,
    )
    titles = [d["title"] for d in list_r.json().get("documents", [])]
    assert any("sales 1-pager" in t for t in titles)
    assert any("trust" in t.lower() for t in titles)
    # Titles must NOT contain the broken &amp; HTML entity.
    assert not any("&amp;" in t for t in titles), titles

    dl = requests.get(
        f"{base}/api/master-admin/document-library/{sales_id}/download",
        headers=headers,
        timeout=15,
    )
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"
