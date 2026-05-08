"""
Orbit4 deep-mapping regression tests (Phases α-δ).
"""
import json

import pytest

from utils.orbit4_client import (
    Orbit4APIError,
    ORBIT4_SUPPORTED_EVENTS,
    map_gymaxis_contract_to_orbit4,
    map_gymaxis_equipment_to_orbit4,
    map_gymaxis_issue_to_orbit4_ticket,
    map_gymaxis_status_to_orbit4_patch,
    map_gymaxis_user_to_orbit4,
    map_orbit4_asset_to_gymaxis,
    map_orbit4_contract_to_gymaxis,
    map_orbit4_ticket_full,
)


# ─── Phase α (inbound) ───────────────────────────────────────────

def _ticket_fixture() -> dict:
    return {
        "id": 4212, "number": "TCK-4212", "type": "fault_repair",
        "description": "Treadmill belt slipping",
        "priority": "high", "problem_type": "belt",
        "status": "in_progress",
        "tags": ["safety", "wear-and-tear"],
        "engineer_deployed_at": "2026-04-22T09:00:00Z",
        "engineer_arrived_at": "2026-04-22T10:15:00Z",
        "closed_at": None,
        "created_at": "2026-04-21T18:00:00Z",
        "metadata": {"integration_id": "iss-uuid-42", "organization_id": "org-pulse"},
        "asset": {
            "id": 777, "brand": "Matrix", "range": "T7XE", "product": "Treadmill",
            "serial_number": "T-987654", "qr_code": "QR-T777",
            "installation_date": "2024-03-15", "warranty_end_date": "2027-03-15",
            "current_spend": 420.0, "max_spend": 1500.0,
            "fitness_product": True, "has_odometer": True,
            "image": "https://cdn.orbit4/img/T7XE.png",
            "metadata": {"origin": "shipment-99"},
        },
        "contract": {
            "id": 555, "number": "CONT-555", "type": "Full Annual",
            "active": True, "start_date": "2026-04-01", "end_date": "2027-03-31",
        },
        "gym_operator": {
            "id": 10, "first_name": "Lee", "last_name": "Somers",
            "email": "lee@pulse.com", "role": "gym_operator",
            "site_name": "Pulse Newcastle",
            "company": {"name": "Pulse Fitness"},
        },
        "service_provider": {"id": 20, "first_name": "Matrix", "last_name": "Service",
                             "email": "service@matrix.com", "role": "service_provider"},
        "engineer": {"id": 42, "first_name": "Jake", "last_name": "Wilson",
                     "email": "jake@matrix.com", "role": "engineer"},
        "ticket_admin": {"id": 30, "first_name": "Emma", "last_name": "King",
                         "email": "emma@pulse.com", "role": "ticket_admin"},
        "caretaker": {"id": 40, "first_name": "Mark", "last_name": "Lee",
                      "email": "mark@pulse.com", "role": "caretaker"},
        "notes": [
            {"user": {"first_name": "Jake", "last_name": "Wilson"},
             "note": "Arrived, diagnosis in progress",
             "created_at": "2026-04-22T10:15:00Z"},
        ],
        "media": [{"id": 900, "url": "https://cdn/img1.jpg",
                   "type": "image", "created_at": "2026-04-22T10:20:00Z"}],
        "documents": [{"id": 901, "url": "https://cdn/report.pdf",
                       "type": "pdf", "created_at": "2026-04-22T10:30:00Z"}],
    }


def test_phase_alpha_ticket_captures_all_key_fields():
    mapped = map_orbit4_ticket_full(_ticket_fixture())
    assert mapped["orbit4_ticket_id"] == "4212"
    assert mapped["orbit4_ticket_number"] == "TCK-4212"
    assert mapped["orbit4_tags"] == ["safety", "wear-and-tear"]
    assert mapped["severity"] == "high"
    assert mapped["source"] == "orbit4"
    assert mapped["orbit4_engineer_deployed_at"] == "2026-04-22T09:00:00Z"
    assert mapped["orbit4_engineer_arrived_at"] == "2026-04-22T10:15:00Z"
    assert mapped["orbit4_closed_at"] is None


def test_phase_alpha_ticket_parties_hydrated():
    mapped = map_orbit4_ticket_full(_ticket_fixture())
    assert mapped["orbit4_gym_operator"]["name"] == "Lee Somers"
    assert mapped["orbit4_gym_operator"]["company_name"] == "Pulse Fitness"
    assert mapped["orbit4_engineer"]["email"] == "jake@matrix.com"
    assert mapped["orbit4_caretaker"]["name"] == "Mark Lee"
    assert mapped["orbit4_ticket_admin"]["role"] == "ticket_admin"


def test_phase_alpha_ticket_asset_and_contract():
    mapped = map_orbit4_ticket_full(_ticket_fixture())
    assert mapped["orbit4_contract"]["id"] == 555
    assert mapped["orbit4_contract"]["active"] is True
    assert mapped["orbit4_asset_id"] == 777
    assert mapped["machine_type"] == "Treadmill"
    assert mapped["warranty_expiry"] == "2027-03-15"
    assert mapped["orbit4_max_spend"] == 1500.0
    assert mapped["orbit4_has_odometer"] is True


def test_phase_alpha_ticket_media_and_notes_flattened():
    mapped = map_orbit4_ticket_full(_ticket_fixture())
    assert len(mapped["orbit4_attachments"]) == 2
    urls = [a["url"] for a in mapped["orbit4_attachments"]]
    assert "https://cdn/img1.jpg" in urls
    assert "https://cdn/report.pdf" in urls
    assert mapped["orbit4_notes"][0]["message"].startswith("Arrived")
    assert mapped["orbit4_notes"][0]["by"] == "Jake Wilson"


def test_phase_alpha_asset_inbound_mapper():
    mapped = map_orbit4_asset_to_gymaxis(_ticket_fixture()["asset"])
    assert mapped["orbit4_asset_id"] == 777
    assert mapped["manufacturer"] == "Matrix"
    assert mapped["model"] == "T7XE"
    assert mapped["install_date"] == "2024-03-15"
    assert mapped["orbit4_image_url"].endswith("T7XE.png")


def test_phase_alpha_contract_inbound_mapper():
    mapped = map_orbit4_contract_to_gymaxis({
        "id": 99, "number": "C-99", "type": "Platinum", "active": True,
        "start_date": "2026-01-01", "end_date": "2027-01-01",
        "gym_operator": {"first_name": "Lee", "last_name": "S", "email": "l@p.com", "role": "gym_operator"},
        "service_provider": {"first_name": "M", "last_name": "S", "email": "m@s.com", "role": "service_provider"},
        "metadata": {"integration_id": "c-uuid"},
    })
    assert mapped["orbit4_contract_id"] == 99
    assert mapped["active"] is True
    assert mapped["orbit4_gym_operator"]["email"] == "l@p.com"
    assert mapped["orbit4_metadata"]["integration_id"] == "c-uuid"


# ─── Phase γ (outbound equipment + contract) ─────────────────────

def _equipment_fixture() -> dict:
    return {
        "id": "eq-uuid-1", "organization_id": "org-pulse",
        "serial_number": "T-987654", "manufacturer": "Matrix",
        "model": "T7XE", "equipment_type": "Treadmill",
        "install_date": "2024-03-15T00:00:00Z",
        "manufacture_date": "2024-01-01",
        "warranty_expiry": "2027-03-15",
        "deprecation_date": "2031-03-15",
        "qr_code": "QR-T777",
    }


def test_phase_gamma_equipment_outbound_shape():
    payload = map_gymaxis_equipment_to_orbit4(_equipment_fixture(), user_id=10)
    assert payload["qr_code"] == "QR-T777"
    assert payload["brand"] == "Matrix"
    assert payload["range"] == "T7XE"
    assert payload["product"] == "Treadmill"
    assert payload["installation_date"] == "2024-03-15"
    assert payload["warranty_end_date"] == "2027-03-15"
    assert payload["user_id"] == 10
    meta = json.loads(payload["metadata"])
    assert meta["integration_id"] == "eq-uuid-1"
    assert meta["organization_id"] == "org-pulse"


def test_phase_gamma_equipment_fallback_qr():
    payload = map_gymaxis_equipment_to_orbit4({"id": "abc12345678", "serial_number": "S"})
    assert payload["qr_code"] == "GA-abc12345"


def test_phase_gamma_contract_outbound_shape():
    payload = map_gymaxis_contract_to_orbit4(
        {"id": "c1", "contract_number": "C-100", "organization_id": "org-pulse",
         "start_date": "2026-04-01T00:00:00Z", "end_date": "2027-03-31T00:00:00Z",
         "status": "active", "contract_type": "Platinum"},
        gym_operator_id=10, service_provider_id=20,
    )
    assert payload["number"] == "C-100"
    assert payload["gym_operator_id"] == 10
    assert payload["service_provider_id"] == 20
    assert payload["type"] == "Platinum"
    assert payload["active"] is True
    assert payload["start_date"] == "2026-04-01"
    assert payload["end_date"] == "2027-03-31"


def test_phase_gamma_user_outbound_language_clamp():
    payload = map_gymaxis_user_to_orbit4(
        {"id": "u1", "full_name": "Lee Somers", "email": "lee@pulse.com",
         "language": "klingon", "organization_id": "org-pulse"},
        role="gym_operator", site_name="Pulse Newcastle",
    )
    assert payload["language"] == "en"
    assert payload["first_name"] == "Lee"
    assert payload["last_name"] == "Somers"
    assert payload["site_name"] == "Pulse Newcastle"
    assert payload["role"] == "gym_operator"


# ─── Phase δ (outbound ticket) ───────────────────────────────────

def test_phase_delta_ticket_payload():
    issue = {
        "id": "iss-1", "organization_id": "org-pulse",
        "issue_description": "Belt slipping badly",
        "severity": "safety_critical",
        "fault_code": "BEL-01", "fault_tags": ["urgent", "cardio"],
        "supplier_case_token": "sup-token",
        "sicon_case_id": 12345,
    }
    payload = map_gymaxis_issue_to_orbit4_ticket(
        issue, asset_id=777, gym_operator_id=10, service_provider_id=20,
        problem_type="BEL-01",
    )
    assert payload["priority"] == "critical"
    assert payload["problem_type"] == "BEL-01"
    assert payload["tags"] == ["urgent", "cardio"]
    assert payload["asset_id"] == 777
    assert payload["gym_operator_id"] == 10
    meta = json.loads(payload["metadata"])
    assert meta["sicon_case_id"] == 12345


def test_phase_delta_status_patch_lifecycle():
    open_patch = map_gymaxis_status_to_orbit4_patch("in_progress")
    assert open_patch == {"status": "in_progress"}

    close_patch = map_gymaxis_status_to_orbit4_patch("resolved", resolution="Belt replaced")
    assert close_patch["status"] == "closed"
    assert close_patch["resolution"] == "Belt replaced"
    assert "closed_at" in close_patch

    unknown = map_gymaxis_status_to_orbit4_patch("bogus_status")
    assert unknown == {"status": "open"}


def test_phase_delta_severity_unknown_defaults_normal():
    payload = map_gymaxis_issue_to_orbit4_ticket({"issue_description": "x", "severity": "wat"})
    assert payload["priority"] == "normal"


# ─── Event catalogue ─────────────────────────────────────────────

def test_supported_events_superset_of_webhooks():
    expected = {"ticket.created", "ticket.updated", "ticket.closed",
                "asset.created", "asset.updated", "asset.moved",
                "note.created", "media.created",
                "user.created", "user.updated"}
    assert expected.issubset(ORBIT4_SUPPORTED_EVENTS)


# ─── Error class surface ─────────────────────────────────────────

def test_orbit4_api_error_is_exception():
    with pytest.raises(Orbit4APIError):
        raise Orbit4APIError("boom")
