"""Iter 220ea·33 — Legacy report import (Engineer App).

Engineers bulk-import historic PDF/CSV/XLSX service reports → Gemini 3
extracts the machines + per-machine custom fields → review/edit → a
branded PDF is generated and saved against the customer.

These tests cover the deterministic parts (customer upsert, report save,
branded PDF build) live, plus source-level guards for the frontend
wizard + entry points. The AI extraction step itself is exercised
separately (live LLM) and is not asserted here to keep the suite
hermetic.
"""
from __future__ import annotations

import os
import pathlib
import uuid

import requests

from conftest import rate_limit_bypass_headers

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://service-ops-hub-6.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
ADMIN_PW = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")

FRONT = pathlib.Path("/app/frontend/src/pages/ServiceOps/Engineer")


def _token() -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
        headers=rate_limit_bypass_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ─── Live backend: customer → save report → branded PDF ──────────────

def test_legacy_customer_save_report_and_pdf():
    tok = _token()
    h = _auth(tok)
    tag = f"PYTEST_Legacy_{uuid.uuid4().hex[:8]}"

    # Create a customer.
    rc = requests.post(f"{BASE}/api/svc/legacy/customers", json={"name": tag, "site_name": "QA Hall"}, headers=h, timeout=30)
    assert rc.status_code == 200, rc.text
    cust = rc.json()["customer"]
    cid = cust["id"]
    assert cust["name"] == tag

    # Search finds it.
    rs = requests.get(f"{BASE}/api/svc/legacy/customers/search", params={"q": tag}, headers=h, timeout=30)
    assert rs.status_code == 200
    assert any(c["id"] == cid for c in rs.json()["customers"])

    # Save a report with two machines + custom fields.
    payload = {
        "customer_id": cid,
        "visits": [{
            "service_date": "2025-09-14",
            "job_number": "QA-1001",
            "summary": "Quarterly PPM",
            "machines": [
                {"name": "RowErg 3", "model": "Concept2 D", "serial": "RE-1", "status": "Serviced",
                 "work_done": "Chain lubed", "custom_fields": [{"label": "Drag Factor", "value": "118"}]},
                {"name": "Treadmill 7", "status": "Needs repair",
                 "custom_fields": [{"label": "Belt wear", "value": "40%"}]},
            ],
        }],
    }
    rr = requests.post(f"{BASE}/api/svc/legacy/reports", json=payload, headers=h, timeout=30)
    assert rr.status_code == 200, rr.text
    rep = rr.json()["report"]
    rid = rep["id"]
    assert rep["machine_count"] == 2
    assert rep["visit_count"] == 1

    # It lists.
    rl = requests.get(f"{BASE}/api/svc/legacy/reports", headers=h, timeout=30)
    assert rl.status_code == 200
    assert any(x["id"] == rid for x in rl.json()["reports"])

    # Branded PDF is a real PDF.
    rp = requests.get(f"{BASE}/api/svc/legacy/reports/{rid}/pdf", headers=h, timeout=60)
    assert rp.status_code == 200
    assert rp.headers.get("content-type", "").startswith("application/pdf")
    assert rp.content[:4] == b"%PDF"

    # Cleanup.
    rd = requests.delete(f"{BASE}/api/svc/legacy/reports/{rid}", headers=h, timeout=30)
    assert rd.status_code == 200
    # Remove the QA customer directly via a fresh save-guard delete is not
    # exposed; the report is gone, and the uniquely-tagged customer is
    # harmless, but tidy it through the DB if reachable.


def test_legacy_endpoints_require_auth():
    r = requests.get(f"{BASE}/api/svc/legacy/customers/search", timeout=30)
    assert r.status_code in (401, 403)


def test_legacy_save_rejects_empty_visits():
    tok = _token()
    r = requests.post(
        f"{BASE}/api/svc/legacy/reports",
        json={"customer": {"name": "QA NoVisits"}, "visits": []},
        headers=_auth(tok), timeout=30,
    )
    assert r.status_code == 400


# ─── PDF builder unit (no network) ──────────────────────────────────

def test_build_legacy_pdf_unit():
    from utils.legacy_report_pdf import build_legacy_pdf
    report = {
        "customer": {"name": "Unit Gym", "site_name": "Hall"},
        "visits": [{
            "service_date": "2025-01-02", "job_number": "U-1", "summary": "x",
            "machines": [{"name": "Bike", "model": "M", "status": "Pass",
                          "custom_fields": [{"label": "Firmware", "value": "v1"}]}],
        }],
    }
    pdf = build_legacy_pdf(report, {"company_name": "Acme", "primary_color": "#2563EB"}, None)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 800


# ─── Frontend wiring guards ─────────────────────────────────────────

def test_wizard_component_exists_with_steps():
    src = (FRONT / "EngineerLegacyImport.js").read_text()
    for tid in (
        "engineer-legacy-import", "legacy-stepper", "legacy-step-customer",
        "legacy-step-upload", "legacy-step-review", "legacy-step-done",
        "legacy-cust-mode-search", "legacy-cust-mode-new", "legacy-upload-input",
        "legacy-save", "legacy-done-view-pdf",
    ):
        assert f'data-testid="{tid}"' in src, f"missing {tid}"
    # PDF open is popup-blocker hardened (pre-open the tab).
    assert "window.open('', '_blank')" in src


def test_route_registered():
    src = pathlib.Path("/app/frontend/src/routes/AppRoutes.js").read_text()
    assert "EngineerLegacyImport" in src
    assert "/svc/engineer/legacy-import" in src


def test_home_tile_dismissible_and_imports_present():
    src = (FRONT / "EngineerHomeV2.js").read_text()
    # Regression guard: the icons used by the tile MUST be imported.
    import re
    imports = re.search(r"from 'lucide-react'", src)
    assert imports is not None
    assert "Wand2" in src and "X," in src.split("from 'lucide-react'")[0]
    assert 'data-testid="engineer-home-legacy-tile"' in src
    assert 'data-testid="engineer-home-legacy-hide"' in src
    assert "gx_engineer_legacy_tile_hidden" in src


def test_settings_entry_present():
    src = (FRONT / "EngineerAccountSettings.js").read_text()
    assert 'testid="engineer-settings-legacy-import-row"' in src
    assert "/svc/engineer/legacy-import" in src
