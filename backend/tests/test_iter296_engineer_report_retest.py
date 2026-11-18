# Retest of iteration_295 fixes: end==start rejected, desk single-site includes site_id '' equipment, PPM signature only after PDF build
import uuid

import pytest
import requests

from test_engineer_report_asset_list import (BASE_URL, CREATED, SIG_PNG, _now, _seed_case, admin_h, owner_h,  # noqa: F401
                                             cleanup, mdb)


def _same_report():
    t = _now(-30)
    return {"work_completed": "TEST_ same", "start_time": t, "end_time": t}


# ── end_time == start_time rejected ──────────────────────────────
class TestEqualTimes:
    def test_svc_equal_times_400(self, admin_h):
        cid = _seed_case()
        requests.post(f"{BASE_URL}/api/svc/engineer/signature", headers=admin_h,
                      json={"case_id": cid, "unavailable": True, "reason": "TEST_ away"})
        r = requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_", "report": _same_report()})
        assert r.status_code == 400
        assert "End time must be after the start time" in r.text
        assert not (mdb.svc_cases.find_one({"id": cid}) or {}).get("engineer_report")

    def test_bfpo_job_equal_times_400(self, admin_h):
        cid = _seed_case(org="bfpo-mod-org", status="assigned")
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", headers=admin_h,
                      json={"unavailable": True, "reason": "TEST_ nobody"})
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_", "safe_and_working": True, "report": _same_report()})
        assert r.status_code == 400 and "End time must be after" in r.text

    def test_ppm_equal_times_400_no_signature(self, admin_h):
        sid = f"TEST_ppm_{uuid.uuid4().hex[:8]}"
        mdb.bfpo_ppm_services.insert_one({"id": sid, "organization_id": "bfpo-mod-org", "reference": "TEST-PPM-EQ",
                                          "site_id": "TEST_site", "site_name": "TEST_ Site", "status": "in_progress",
                                          "due_date": _now()[:10], "created_at": _now()})
        CREATED["bfpo_ppm_services"].append(sid)
        r = requests.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", headers=admin_h,
                          json={"notes": "TEST_", "report": _same_report(),
                                "signoff": {"signed_by_name": "TEST_ S", "image_data": SIG_PNG}})
        assert r.status_code == 400
        assert mdb.svc_signatures.count_documents({"ppm_service_id": sid}) == 0

    def test_one_minute_ok(self, admin_h):
        cid = _seed_case()
        requests.post(f"{BASE_URL}/api/svc/engineer/signature", headers=admin_h,
                      json={"case_id": cid, "unavailable": True, "reason": "TEST_ away"})
        r = requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_", "report": {"work_completed": "TEST_ ok",
                                                                "start_time": _now(-2), "end_time": _now(-1)}})
        assert r.status_code == 200, r.text


# ── PPM signature persisted once, after PDF build ────────────────
class TestPpmSignatureOrder:
    def test_single_signature_on_success_and_retry_blocked(self, admin_h):
        sid = f"TEST_ppm_{uuid.uuid4().hex[:8]}"
        mdb.bfpo_ppm_services.insert_one({"id": sid, "organization_id": "bfpo-mod-org", "reference": "TEST-PPM-SIG",
                                          "site_id": "TEST_site", "site_name": "TEST_ Site", "status": "in_progress",
                                          "due_date": _now()[:10], "created_at": _now()})
        CREATED["bfpo_ppm_services"].append(sid)
        body = {"notes": "TEST_", "report": {"work_completed": "TEST_ w", "start_time": _now(-60), "end_time": _now(-5)},
                "signoff": {"signed_by_name": "TEST_ PPM Sig", "image_data": SIG_PNG}}
        r = requests.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", headers=admin_h, json=body)
        assert r.status_code == 200, r.text
        assert mdb.svc_signatures.count_documents({"ppm_service_id": sid}) == 1
        again = requests.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", headers=admin_h, json=body)
        assert again.status_code == 400
        assert mdb.svc_signatures.count_documents({"ppm_service_id": sid}) == 1
        g = requests.get(f"{BASE_URL}/api/bfpo/ppm/services/{sid}", headers=admin_h)
        assert g.status_code == 200
        TestPpmSignatureOrder.svc = g.json()
        assert g.json()["engineer_report"]["work_completed"] == "TEST_ w"

    def test_ppm_service_get_exposes_signoff(self):
        svc = getattr(TestPpmSignatureOrder, "svc", None) or pytest.skip("no svc")
        # UI renders EngineerReportView on completed PPM; without a signoff field it says 'No customer signature captured.'
        assert any(k in svc for k in ("signoff", "signature")), f"no signoff key in GET service: {sorted(svc.keys())}"


# ── Desk equipment single site includes site_id '' ──────────────
class TestDeskBlankSite:
    def test_blank_site_equipment_in_single_site(self, owner_h):
        eid = f"TEST_eq_{uuid.uuid4().hex[:8]}"
        mdb.equipment.insert_one({"id": eid, "organization_id": "iso-demo-org", "site_id": "",
                                  "name": "TEST_ Blank site bike", "status": "operational"})
        CREATED["equipment"].append(eid)
        for site in ("iso-demo-site-a", "iso-demo-site-b", "all"):
            r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment",
                             params={"organization_id": "iso-demo-org", "site_id": site}, headers=owner_h)
            assert r.status_code == 200
            ids = [e["id"] for e in r.json()["equipment"]]
            assert eid in ids, f"blank-site equipment missing from {site}"

    def test_single_site_excludes_other_site(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment",
                         params={"organization_id": "iso-demo-org", "site_id": "iso-demo-site-a"}, headers=owner_h)
        assert "iso-demo-site-b" not in {e.get("site_id") for e in r.json()["equipment"]}
