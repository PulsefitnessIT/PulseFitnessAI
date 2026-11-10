# MOD jobs on the Pulse Service Desk: visibility, job file, provider mirror, take-over
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CASE = "TEST_DESK_case"
TOK = "TEST_DESK_tok"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def op():
    return _login("craig.henshall@pulsefitness.com", "PulseMOD123!")


@pytest.fixture(scope="module")
def nonop():
    return _login("owner@isodemo.com", "IsoDemo123!")


# --- List visibility ---
class TestListVisibility:
    def test_operator_sees_mod(self, op):
        r = op.get(f"{BASE_URL}/api/svc/cases", params={"limit": 200})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] > 0
        mods = [c for c in d["cases"] if c.get("organization_id") == "bfpo-mod-org"]
        assert mods and all(c.get("is_mod") for c in mods)

    def test_mod_only_and_hide(self, op):
        a = op.get(f"{BASE_URL}/api/svc/cases", params={"mod": "1", "limit": 200}).json()
        assert a["total"] > 0 and all(c["organization_id"] == "bfpo-mod-org" for c in a["cases"])
        h = op.get(f"{BASE_URL}/api/svc/cases", params={"mod": "0", "limit": 200}).json()
        assert all(c["organization_id"] != "bfpo-mod-org" for c in h["cases"])
        allc = op.get(f"{BASE_URL}/api/svc/cases", params={"limit": 1}).json()
        assert allc["total"] == a["total"] + h["total"]

    def test_search_mod_ref(self, op):
        d = op.get(f"{BASE_URL}/api/svc/cases", params={"search": "MOD-TEST-1"}).json()
        assert any(c["id"] == CASE for c in d["cases"])

    def test_nonop_no_mod(self, nonop):
        r = nonop.get(f"{BASE_URL}/api/svc/cases", params={"limit": 200})
        assert r.status_code == 200, r.text
        assert all(c.get("organization_id") != "bfpo-mod-org" for c in r.json()["cases"])
        r1 = nonop.get(f"{BASE_URL}/api/svc/cases", params={"mod": "1", "limit": 200}).json()
        assert all(c.get("organization_id") != "bfpo-mod-org" for c in r1["cases"])


# --- Desk summary / queue ---
class TestDesk:
    def test_summary(self, op):
        r = op.get(f"{BASE_URL}/api/svc/desk/summary")
        assert r.status_code == 200, r.text
        print("summary", str(r.json())[:400])

    def test_queue_includes_mod(self, op):
        r = op.get(f"{BASE_URL}/api/svc/desk/queue")
        assert r.status_code == 200, r.text
        txt = r.text
        assert "bfpo-mod-org" in txt or "MOD" in txt


# --- Per-case reads ---
class TestCaseReads:
    def test_get_case(self, op):
        r = op.get(f"{BASE_URL}/api/svc/cases/{CASE}")
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["is_mod"] is True
        assert "external_provider" in c and "desk_read_only" in c
        assert "_id" not in c

    @pytest.mark.parametrize("path", ["events", "lifecycle", "crm-context", "tracking-link",
                                      "service-report.pdf", "job-file"])
    def test_subresources(self, op, nonop, path):
        r = op.get(f"{BASE_URL}/api/svc/cases/{CASE}/{path}")
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        r2 = nonop.get(f"{BASE_URL}/api/svc/cases/{CASE}/{path}")
        if path == "events" and r2.status_code == 200:  # org-scoped list: must be empty
            assert r2.json()["events"] == []
        else:
            assert r2.status_code in (403, 404), f"nonop {path}: {r2.status_code}"

    def test_comms_log(self, op, nonop):
        r = op.get(f"{BASE_URL}/api/svc/comms/log", params={"case_id": CASE})
        assert r.status_code == 200, r.text
        r2 = nonop.get(f"{BASE_URL}/api/svc/comms/log", params={"case_id": CASE})
        print("nonop comms", r2.status_code, r2.text[:200])
        assert r2.status_code in (403, 404) or not r2.json().get("items") and not r2.json().get("logs")

    def test_nonop_get_case_404(self, nonop):
        assert nonop.get(f"{BASE_URL}/api/svc/cases/{CASE}").status_code == 404

    def test_job_file_shape(self, op):
        d = op.get(f"{BASE_URL}/api/svc/cases/{CASE}/job-file").json()
        for k in ("logged", "provider", "work", "documents", "commercial"):
            assert k in d
        assert d["logged"]["ticket_ref"]
        assert isinstance(d["logged"]["photos"], list)
        assert {"active", "cases", "messages"} <= set(d["provider"])
        assert {"quotes", "purchase_orders", "customer_po_number"} <= set(d["commercial"])
        assert all("token" not in s for s in d["provider"]["cases"])


# --- Provider mirror then take-over (order matters) ---
class TestProviderFlow:
    def test_1_provider_update_mirrors(self, op):
        r = requests.post(f"{BASE_URL}/api/supplier/case/{TOK}/update", json={
            "status": "engineer_scheduled", "engineer_name": "TEST_Eng Bob",
            "estimated_arrival": "2026-02-01T10:00", "notes": "TEST_note mirror"}, timeout=30)
        assert r.status_code == 200, r.text
        c = op.get(f"{BASE_URL}/api/svc/cases/{CASE}").json()
        assert c.get("provider_status") == "engineer_scheduled"
        ev = [e for e in c["events"] if e.get("type") == "provider_update"]
        assert ev and any("TEST_Eng Bob" in (e.get("body") or "") for e in ev)
        assert c["desk_read_only"] is True and c["external_provider"]

    def test_2_put_blocked(self, op):
        r = op.put(f"{BASE_URL}/api/svc/cases/{CASE}", json={"priority": "p2"})
        assert r.status_code == 409, r.text

    def test_3_transition_blocked_while_provider(self, op):
        # read-only should cover state changes too
        r = op.post(f"{BASE_URL}/api/svc/cases/{CASE}/transition", json={"to": "triaged", "reason": "TEST"})
        print("transition while provider active:", r.status_code, r.text[:200])
        assert r.status_code in (400, 409, 403)

    def test_4_take_over(self, op):
        r = op.post(f"{BASE_URL}/api/svc/cases/{CASE}/take-over", json={"reason": "TEST_takeover"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        c = op.get(f"{BASE_URL}/api/svc/cases/{CASE}").json()
        assert c["desk_read_only"] is False and c["external_provider"] is None
        assert any(e.get("type") == "provider_taken_over" for e in c["events"])

    def test_5_put_ok_after(self, op):
        r = op.put(f"{BASE_URL}/api/svc/cases/{CASE}", json={"priority": "p3"})
        assert r.status_code == 200, r.text
        assert r.json()["priority"] == "p3"

    def test_6_take_over_again_400(self, op):
        assert op.post(f"{BASE_URL}/api/svc/cases/{CASE}/take-over", json={}).status_code == 400

    def test_7_nonop_take_over_404(self, nonop):
        assert nonop.post(f"{BASE_URL}/api/svc/cases/{CASE}/take-over", json={}).status_code == 404

    def test_8_provider_update_after_takeover(self, op):
        r = requests.post(f"{BASE_URL}/api/supplier/case/{TOK}/update", json={
            "status": "in_progress", "notes": "TEST_after takeover"}, timeout=30)
        print("provider update after take-over:", r.status_code, r.text[:200])
        assert r.status_code in (400, 403, 409, 410), "provider can still update a taken-over job"
