"""Backend tests for Operations > Faults > Request a Part feature.

Covers: meta, equipment-search, coverage, create/get/update, attachments
(object storage), AI part identify, submit + supplier card + service desk,
public supplier card lifecycle (acknowledge/quote/invoice/allocate/despatch/complete),
exploded drawings CRUD.
"""
import io
import os
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"No token in login: {data}"
    return tok


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# Meta -------------------------------------------------------------------
def test_meta(headers):
    r = requests.get(f"{BASE_URL}/api/parts-requests/meta", headers=headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert len(d["statuses"]) == 9
    assert d["default_supplier_email"] == "parts@pulsefitness.com"


# Equipment search -------------------------------------------------------
def test_equipment_search(headers):
    r = requests.get(f"{BASE_URL}/api/parts-requests/equipment-search",
                     params={"q": "Life"}, headers=headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("equipment"), list)


# Coverage ---------------------------------------------------------------
def test_coverage_iso_tm_001(headers):
    r = requests.get(f"{BASE_URL}/api/parts-requests/coverage",
                     params={"serial_number": "ISO-TM-001"}, headers=headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "cover_type" in d and "coverage_status" in d


# Create + Get -----------------------------------------------------------
@pytest.fixture(scope="module")
def created_request(headers):
    payload = {
        "supplier_email": "test-supplier@example.com",
        "supplier_name": "Test Supplier",
        "notes": "TEST_ automated parts request",
        "machines": [{
            "serial_number": "ISO-TM-001",
            "machine_name": "Treadmill A",
            "manufacturer": "Life Fitness",
            "model": "T5",
            "equipment_type": "Treadmill",
            "parts": [{"part_name": "Belt", "part_number": "LF-BELT-001", "qty": 2, "notes": "worn"}],
        }],
    }
    r = requests.post(f"{BASE_URL}/api/parts-requests", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    d = r.json()
    assert d["status"] == "draft"
    assert d["reference"].startswith("PR-")
    assert len(d["machines"]) == 1
    assert d["machines"][0]["cover_type"] in ("chargeable", "contract", "warranty")
    assert d["machines"][0]["coverage_status"]
    return d


def test_get_request(headers, created_request):
    rid = created_request["id"]
    r = requests.get(f"{BASE_URL}/api/parts-requests/{rid}", headers=headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == rid
    assert isinstance(d["events"], list)
    assert any(e["action"] == "created" for e in d["events"])


# Attachment upload/download --------------------------------------------
@pytest.fixture(scope="module")
def attachment(headers, created_request):
    rid = created_request["id"]
    # 1x1 PNG
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    r = requests.post(
        f"{BASE_URL}/api/parts-requests/{rid}/attachments?machine_index=0",
        files=files, headers=headers, timeout=60,
    )
    assert r.status_code == 200, f"attachment upload failed: {r.status_code} {r.text}"
    d = r.json()
    assert "id" in d
    assert "storage_path" not in d
    assert "data_b64" not in d
    return d


def test_attachment_download(headers, created_request, attachment):
    rid = created_request["id"]
    aid = attachment["id"]
    r = requests.get(f"{BASE_URL}/api/parts-requests/{rid}/attachments/{aid}/download",
                     headers=headers, timeout=30)
    assert r.status_code == 200
    assert len(r.content) > 0


# AI identify ------------------------------------------------------------
def test_ai_identify_endpoint_responds(headers, created_request, attachment):
    rid = created_request["id"]
    aid = attachment["id"]
    r = requests.post(f"{BASE_URL}/api/parts-requests/{rid}/ai-identify",
                      json={"attachment_id": aid, "machine_type": "Treadmill",
                            "manufacturer": "Life Fitness", "model": "T5"},
                      headers=headers, timeout=120)
    assert r.status_code == 200, f"ai-identify failed: {r.status_code} {r.text}"
    d = r.json()
    assert "available" in d  # true or false both acceptable


# Submit -----------------------------------------------------------------
@pytest.fixture(scope="module")
def submitted_request(headers, created_request):
    rid = created_request["id"]
    r = requests.post(f"{BASE_URL}/api/parts-requests/{rid}/submit",
                      json={"send_to_service_desk": True}, headers=headers, timeout=60)
    assert r.status_code == 200, f"submit failed: {r.status_code} {r.text}"
    d = r.json()
    assert d["status"] == "submitted"
    assert "email_sent" in d
    assert d["supplier_card_url"]
    assert d.get("service_desk", {}).get("created") is True
    token = d["supplier_card_url"].rsplit("/", 1)[-1]
    return {"request_id": rid, "token": token, "url": d["supplier_card_url"]}


# Public supplier card (no auth) ----------------------------------------
def test_public_card_no_auth(submitted_request):
    tok = submitted_request["token"]
    r = requests.get(f"{BASE_URL}/api/parts-card/{tok}", timeout=30)
    assert r.status_code == 200, f"public card failed: {r.status_code} {r.text}"
    d = r.json()
    assert d["reference"]
    assert isinstance(d["machines"], list) and len(d["machines"]) >= 1
    assert "cover_label" in d["machines"][0]
    assert isinstance(d["events"], list)


def test_public_card_attachment_no_auth(submitted_request, attachment):
    tok = submitted_request["token"]
    aid = attachment["id"]
    r = requests.get(f"{BASE_URL}/api/parts-card/{tok}/attachments/{aid}", timeout=30)
    assert r.status_code == 200
    assert len(r.content) > 0


# Supplier lifecycle actions --------------------------------------------
def test_supplier_lifecycle(headers, submitted_request):
    tok = submitted_request["token"]
    rid = submitted_request["request_id"]
    seq = [
        ("acknowledge", {}, "acknowledged"),
        ("quote", {"amount": 250, "currency": "GBP", "note": "quote note"}, "quoted"),
        ("invoice", {"amount": 250, "invoice_number": "INV-TEST-1"}, "invoiced"),
        ("allocate", {}, "allocated"),
        ("despatch", {"carrier": "DHL", "tracking": "TRK123", "eta": "2026-01-15"}, "despatched"),
        ("complete", {}, "completed"),
    ]
    for action, extra, expected_status in seq:
        body = {"action": action, **extra}
        r = requests.post(f"{BASE_URL}/api/parts-card/{tok}/update", json=body, timeout=30)
        assert r.status_code == 200, f"{action} failed: {r.status_code} {r.text}"
        d = r.json()
        assert d["status"] == expected_status, f"expected {expected_status}, got {d}"

    # Verify operator view has quote/invoice/despatch populated + supplier events
    r = requests.get(f"{BASE_URL}/api/parts-requests/{rid}", headers=headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "completed"
    assert d.get("quote", {}).get("amount") == 250
    assert d.get("invoice", {}).get("invoice_number") == "INV-TEST-1"
    assert d.get("despatch", {}).get("carrier") == "DHL"
    supplier_actions = [e["action"] for e in d["events"] if e.get("actor_role") == "supplier"]
    for a in ["acknowledge", "quote", "invoice", "allocate", "despatch", "complete"]:
        assert a in supplier_actions, f"missing supplier event {a}"


# Exploded drawings ------------------------------------------------------
def test_exploded_drawings_crud(headers):
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )
    files = {"file": ("drawing.png", io.BytesIO(png), "image/png")}
    # NOTE: endpoint accepts these as QUERY params (not Form fields) — minor design issue
    params = {"manufacturer": "Life Fitness", "model": "T5",
              "title": "TEST_ T5 Belt Drawing", "equipment_type": "Treadmill"}
    r = requests.post(f"{BASE_URL}/api/exploded-drawings", files=files, params=params,
                      headers=headers, timeout=60)
    assert r.status_code == 200, f"drawing upload failed: {r.status_code} {r.text}"
    d = r.json()
    did = d["id"]

    r = requests.get(f"{BASE_URL}/api/exploded-drawings",
                     params={"manufacturer": "Life Fitness"}, headers=headers, timeout=30)
    assert r.status_code == 200
    drawings = r.json()["drawings"]
    assert any(x["id"] == did for x in drawings)

    r = requests.get(f"{BASE_URL}/api/exploded-drawings/{did}/file",
                     headers=headers, timeout=30)
    assert r.status_code == 200
    assert len(r.content) > 0

    requests.delete(f"{BASE_URL}/api/exploded-drawings/{did}", headers=headers, timeout=30)
