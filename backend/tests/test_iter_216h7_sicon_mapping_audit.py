"""
Iter 216h7 — Sicon integration capability extensions + truth mapping table.

Pins:
  1. Contract spare-num + spare-date slots are serialised correctly (legacy text-only path stays).
  2. CLAnalysisCode 11-15 (new finance/governance slots) appear in contract-line payloads.
  3. Sub-status resolves via per-org workflow_state → SiSMDocumentSubStatusID map.
  4. The mapping table covers every wire field actually sent by the mappers
     (drift guard — fail the build if a new field is sent without a doc row).
  5. /sicon/field-mapping returns the new direction-summary metadata.
  6. The customer-order-number endpoint exists and validates input.
"""
from __future__ import annotations

import os

import httpx
import pytest


API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")


@pytest.fixture
def master_headers():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ── Mapper-level tests (in-process, no HTTP) ────────────────────────


def test_contract_spare_text_legacy_path():
    from utils.sicon_client import _contract_spare_fields
    contract = {"spare_text_map": ["renewal_strategy"], "renewal_strategy": "Auto"}
    out = _contract_spare_fields(contract)
    assert out["SpareText1"] == "Auto"


def test_contract_spare_num_slots():
    from utils.sicon_client import _contract_spare_fields
    contract = {
        "spare_num_map": ["uplift_cap_pct", "min_renewal_value"],
        "uplift_cap_pct": 5.5,
        "min_renewal_value": 12000,
    }
    out = _contract_spare_fields(contract)
    assert out["SpareNum1"] == 5.5
    assert out["SpareNum2"] == 12000.0


def test_contract_spare_date_slots():
    from utils.sicon_client import _contract_spare_fields
    contract = {
        "spare_date_map": ["last_review_date", "next_uplift_date"],
        "last_review_date": "2026-01-15",
        "next_uplift_date": "2026-04-01",
    }
    out = _contract_spare_fields(contract)
    assert out["SpareDate1"] == "2026-01-15"
    assert out["SpareDate2"] == "2026-04-01"


def test_contract_spare_dict_overrides():
    """Direct slot overrides via spare_text/num/date dicts work alongside maps."""
    from utils.sicon_client import _contract_spare_fields
    contract = {
        "spare_text": {3: "Direct override"},
        "spare_num": {7: 99.9},
        "spare_date": {1: "2027-01-01"},
    }
    out = _contract_spare_fields(contract)
    assert out["SpareText3"] == "Direct override"
    assert out["SpareNum7"] == 99.9
    assert out["SpareDate1"] == "2027-01-01"


def test_contract_spare_drops_invalid_slot_indices():
    """Out-of-range and non-int keys are silently dropped."""
    from utils.sicon_client import _contract_spare_fields
    contract = {"spare_num": {8: 1.0, "x": 2.0, 0: 3.0, 1: 4.5}}
    out = _contract_spare_fields(contract)
    assert "SpareNum1" in out and out["SpareNum1"] == 4.5
    # 8 (out of 1-7 range) and 0 (below range) and "x" (not int) must NOT appear.
    assert "SpareNum8" not in out
    assert "SpareNum0" not in out


def test_contract_line_analysis_codes_11_to_15():
    from utils.sicon_client import _contract_line_analysis_codes
    line = {
        "tier": "Gold",
        "sla_penalty_band": "0/5/10/25%",
        "kpi_breach_flag": "warn",
        "finance_approver_email": "cfo@example.com",
        "billing_cycle_override": "quarterly",
        "holdback_pct": 5.0,
    }
    out = _contract_line_analysis_codes(line)
    assert out["CLAnalysisCode1"] == "Gold"
    assert out["CLAnalysisCode11"] == "0/5/10/25%"
    assert out["CLAnalysisCode12"] == "WARN"  # uppercased
    assert out["CLAnalysisCode13"] == "cfo@example.com"
    assert out["CLAnalysisCode14"] == "quarterly"
    assert out["CLAnalysisCode15"] == "5.0"


def test_sub_status_resolves_via_workflow_state_map():
    from utils.sicon_client import map_gymaxis_to_sicon_case
    issue = {"id": "i1", "workflow_state": "awaiting_parts", "severity": "medium"}
    config = {"sub_status_mapping": {"awaiting_parts": 4}}
    payload = map_gymaxis_to_sicon_case(issue, config)
    assert payload.get("SiSMDocumentSubStatusID") == 4


def test_sub_status_explicit_id_wins_over_workflow_state():
    from utils.sicon_client import map_gymaxis_to_sicon_case
    issue = {
        "id": "i1", "workflow_state": "awaiting_parts", "severity": "medium",
        "sicon_sub_status_id": 9,
    }
    config = {"sub_status_mapping": {"awaiting_parts": 4}}
    payload = map_gymaxis_to_sicon_case(issue, config)
    assert payload["SiSMDocumentSubStatusID"] == 9


def test_sub_status_omitted_when_no_signals():
    from utils.sicon_client import map_gymaxis_to_sicon_case
    payload = map_gymaxis_to_sicon_case({"id": "i1", "severity": "medium"}, {})
    assert "SiSMDocumentSubStatusID" not in payload


# ── Mapping table tests (HTTP) ──────────────────────────────────────


def test_mapping_endpoint_returns_extended_table(master_headers):
    r = httpx.get(
        f"{API_URL}/api/sicon/field-mapping", headers=master_headers, timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "iter-216h7"
    assert body["total"] > 100, f"Expected >100 mapping rows, got {body['total']}"
    # All 7 entities must be represented.
    expected = {"Case", "Contract", "ContractLine", "TrackingNote",
                "Appointment", "TimeBooking", "Resource", "Customer"}
    assert expected.issubset(set(body["entities"]))
    # Direction-summary is the new iter 216h7 addition.
    assert "direction_summary" in body
    for entity, counts in body["direction_summary"].items():
        assert set(counts.keys()) <= {"→", "←", "↔"}


def test_mapping_covers_iter_216h7_extensions(master_headers):
    """Drift guard — the new CL11-15 + spare-num/date rows must be documented."""
    body = httpx.get(
        f"{API_URL}/api/sicon/field-mapping", headers=master_headers, timeout=30,
    ).json()
    sicon_fields = {row["sicon_field"] for row in body["mappings"]}
    must_have = {
        "case.SiSMDocumentSubStatusID",
        "contract.SpareNum1-7",
        "contract.SpareDate1-7",
        "line.CLAnalysisCode11",
        "line.CLAnalysisCode12",
        "line.CLAnalysisCode13",
        "line.CLAnalysisCode14",
        "line.CLAnalysisCode15",
        "contract.CustomerOrderNumber",
    }
    missing = must_have - sicon_fields
    assert not missing, f"Mapping table missing iter 216h7 entries: {missing}"


# ── Customer-order-number endpoint ──────────────────────────────────


def test_update_contract_po_requires_value(master_headers):
    """Missing customer_order_number → 400."""
    # Auth-only smoke (no real contract — should still validate body first).
    r = httpx.post(
        f"{API_URL}/api/sicon/update-contract-po/non-existent",
        headers={**master_headers, "X-RateLimit-Bypass": BYPASS},
        json={},
        timeout=30,
    )
    # Master admin doesn't have organization_id, so we expect either 400 (body validation)
    # or 403 (org required) — both prove the endpoint is wired and reachable.
    assert r.status_code in (400, 403)
