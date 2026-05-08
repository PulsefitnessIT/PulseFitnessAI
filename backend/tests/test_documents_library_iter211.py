"""Documents library — list / upload / download / delete + per-org scoping.

Iteration 211 — wires up the Documents sub-tab inside OrgBillingPanel and the
top-level Master Admin → Support → Documents view. Auto-capture of invoice
PDFs is exercised indirectly: list returns whatever has been generated.
"""
from __future__ import annotations

import io
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_documents_list_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/document-library", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403


def test_documents_list_returns_payload(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/document-library", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "documents" in body and isinstance(body["documents"], list)
    assert "categories" in body
    assert "invoice" in body["categories"]
    # Storage blob should never be returned in the list payload.
    for d in body["documents"]:
        assert "storage" not in d
        assert "has_body" in d


def test_documents_upload_download_delete_roundtrip(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)

    # Upload
    files = {"file": ("test-contract.txt", io.BytesIO(b"hello contract body"), "text/plain")}
    data = {
        "title": "Iteration 211 — pytest contract",
        "category": "contract",
        "scope": "platform",
        "tags": "pytest, iter211",
    }
    r = requests.post(
        f"{base}/api/master-admin/document-library",
        headers=headers,
        files=files,
        data=data,
        timeout=10,
    )
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    doc_id = doc["id"]
    assert doc["title"].startswith("Iteration 211")
    assert doc["category"] == "contract"
    assert doc["source"] == "upload"
    assert "pytest" in doc["tags"]

    # Download
    r2 = requests.get(
        f"{base}/api/master-admin/document-library/{doc_id}/download",
        headers=headers,
        timeout=10,
    )
    assert r2.status_code == 200
    assert r2.content == b"hello contract body"
    assert r2.headers.get("Content-Type", "").startswith("text/plain")

    # Search filter — title contains
    r3 = requests.get(
        f"{base}/api/master-admin/document-library?q=Iteration%20211",
        headers=headers,
        timeout=10,
    )
    assert r3.status_code == 200
    assert any(d["id"] == doc_id for d in r3.json()["documents"])

    # Category filter
    r4 = requests.get(
        f"{base}/api/master-admin/document-library?category=contract",
        headers=headers,
        timeout=10,
    )
    assert r4.status_code == 200
    assert any(d["id"] == doc_id for d in r4.json()["documents"])

    # Delete
    r5 = requests.delete(
        f"{base}/api/master-admin/document-library/{doc_id}",
        headers=headers,
        timeout=10,
    )
    assert r5.status_code == 200
    assert r5.json()["deleted"] is True

    # Confirm gone
    r6 = requests.get(
        f"{base}/api/master-admin/document-library/{doc_id}/download",
        headers=headers,
        timeout=10,
    )
    assert r6.status_code == 404


def test_documents_org_scope_filtering(master_admin_token_session):
    """Per-org scoping must isolate uploads to the targeted organization."""
    base = _test_backend_url()
    headers = _h(master_admin_token_session)

    # Pick a real org id. Tottenham Green is guaranteed by conftest.
    from tests.conftest import TOTTENHAM_GREEN_ORG_ID
    org_id = TOTTENHAM_GREEN_ORG_ID

    files = {"file": ("dpa.txt", io.BytesIO(b"dpa body"), "text/plain")}
    data = {
        "title": "Iteration 211 — org-scoped DPA",
        "category": "dpa",
        "scope": "org",
        "organization_id": org_id,
        "tags": "iter211, scoped",
    }
    r = requests.post(
        f"{base}/api/master-admin/document-library",
        headers=headers,
        files=files,
        data=data,
        timeout=10,
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["document"]["id"]

    try:
        # Filter by org — must include this doc.
        r2 = requests.get(
            f"{base}/api/master-admin/document-library?organization_id={org_id}",
            headers=headers,
            timeout=10,
        )
        assert r2.status_code == 200
        assert any(d["id"] == doc_id for d in r2.json()["documents"])

        # Platform-only scope — must NOT include this doc.
        r3 = requests.get(
            f"{base}/api/master-admin/document-library?scope=platform",
            headers=headers,
            timeout=10,
        )
        assert r3.status_code == 200
        assert not any(d["id"] == doc_id for d in r3.json()["documents"])
    finally:
        requests.delete(
            f"{base}/api/master-admin/document-library/{doc_id}",
            headers=headers,
            timeout=10,
        )


def test_documents_upload_rejects_org_scope_without_org_id(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    files = {"file": ("x.txt", io.BytesIO(b"x"), "text/plain")}
    data = {"title": "bad", "category": "other", "scope": "org"}
    r = requests.post(
        f"{base}/api/master-admin/document-library",
        headers=headers,
        files=files,
        data=data,
        timeout=10,
    )
    assert r.status_code == 400


def test_documents_upload_rejects_empty_file(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    data = {"title": "empty", "category": "other", "scope": "platform"}
    r = requests.post(
        f"{base}/api/master-admin/document-library",
        headers=headers,
        files=files,
        data=data,
        timeout=10,
    )
    assert r.status_code == 400
