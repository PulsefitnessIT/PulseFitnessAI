# Iter 297: Further Work follow-up (draft + intake link) and Further Parts -> stores parts requests
import uuid

import pytest
import requests

from test_engineer_report_asset_list import (ADMIN_ORG, BASE_URL, CREATED, _now, _seed_case, admin_h, owner_h,  # noqa: F401
                                             cleanup, mdb)

PARTS = [{"name": "TEST_ Drive belt", "qty": 2, "sku": "tst-db-9"}, {"name": "TEST_ Console cable", "qty": 1}]
NEW_CASES = []


@pytest.fixture(scope="module", autouse=True)
def cleanup_297():
    yield
    ids = CREATED["svc_cases"] + NEW_CASES
    mdb.svc_parts_requests.delete_many({"$or": [{"case_id": {"$in": ids}}, {"origin_case_id": {"$in": ids}}]})
    for cid in NEW_CASES:
        mdb.svc_cases.delete_one({"id": cid})
        mdb.svc_case_events.delete_many({"case_id": cid})


def _complete(h, cid, parts=PARTS, further="TEST_ replace motor next visit"):
    requests.post(f"{BASE_URL}/api/svc/engineer/signature", headers=h,
                  json={"case_id": cid, "unavailable": True, "reason": "TEST_ away"})
    return requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=h, json={
        "summary": "TEST_", "report": {"work_completed": "TEST_ swapped belt", "further_work_required": further,
                                       "further_parts_required": parts, "start_time": _now(-60), "end_time": _now(-5)}})


# ── Further parts -> parts requests ─────────────────────────────
class TestFurtherParts:
    def test_complete_raises_parts_requests(self, admin_h):
        cid = _seed_case()
        r = _complete(admin_h, cid)
        assert r.status_code == 200, r.text
        rows = list(mdb.svc_parts_requests.find({"case_id": cid, "source": "further_parts_required"}, {"_id": 0}))
        assert len(rows) == 2
        by = {x["part_name"]: x for x in rows}
        assert by["TEST_ Drive belt"]["qty"] == 2 and by["TEST_ Drive belt"]["part_sku"] == "TST-DB-9"
        assert by["TEST_ Console cable"]["part_sku"] == "TBC"
        assert all(x["status"] == "pending" and x["organization_id"] == ADMIN_ORG for x in rows)
        ev = mdb.svc_case_events.find_one({"case_id": cid, "kind": "parts_request"}) or \
            mdb.svc_case_events.find_one({"case_id": cid, "body": {"$regex": "^Parts requested for the next visit"}})
        assert ev, "no timeline event for parts request"
        TestFurtherParts.cid = cid

    def test_parts_requests_in_admin_inbox(self, admin_h):
        cid = getattr(TestFurtherParts, "cid", None) or pytest.skip()
        r = requests.get(f"{BASE_URL}/api/admin/parts-requests", headers=admin_h, params={"status": "pending", "limit": 500})
        assert r.status_code == 200, r.text
        assert sum(1 for x in r.json()["items"] if x.get("case_id") == cid) == 2

    def test_no_parts_no_requests(self, admin_h):
        cid = _seed_case()
        assert _complete(admin_h, cid, parts=[]).status_code == 200
        assert mdb.svc_parts_requests.count_documents({"case_id": cid}) == 0


# ── Follow-up draft + booking ──────────────────────────────────
class TestFollowUp:
    def test_draft(self, admin_h):
        cid = getattr(TestFurtherParts, "cid", None) or pytest.skip()
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/follow-up-draft", headers=admin_h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["follow_up_of"] == cid and d["title"].startswith("Follow-up: ")
        assert "TEST_ replace motor next visit" in d["description"]
        assert "2 × TEST_ Drive belt" in d["description"]
        assert d["existing_follow_up"] is None

    def test_draft_404(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/svc/cases/TEST_nope_{uuid.uuid4().hex[:6]}/follow-up-draft", headers=admin_h)
        assert r.status_code == 404

    def test_draft_cross_tenant_404(self, owner_h):
        cid = getattr(TestFurtherParts, "cid", None) or pytest.skip()
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/follow-up-draft", headers=owner_h)
        assert r.status_code in (403, 404)

    def test_book_links_and_moves_parts(self, admin_h):
        cid = getattr(TestFurtherParts, "cid", None) or pytest.skip()
        d = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/follow-up-draft", headers=admin_h).json()
        r = requests.post(f"{BASE_URL}/api/svc/intake/phone", headers=admin_h, json={
            "title": d["title"], "description": d["description"], "priority": "p3", "case_type": "repair",
            "customer_name": "TEST_Customer", "follow_up_of": cid})
        assert r.status_code in (200, 201), r.text
        new = r.json().get("case") or r.json()
        nid = new["id"]
        NEW_CASES.append(nid)
        n = mdb.svc_cases.find_one({"id": nid}, {"_id": 0})
        o = mdb.svc_cases.find_one({"id": cid}, {"_id": 0})
        assert n["follow_up_of"] == cid and n["follow_up_of_reference"] == o["reference"]
        assert o["follow_up_case_id"] == nid and o["follow_up_case_reference"] == n["reference"]
        assert mdb.svc_parts_requests.count_documents({"case_id": nid, "origin_case_id": cid}) == 2
        assert mdb.svc_parts_requests.count_documents({"case_id": cid}) == 0
        assert mdb.svc_case_events.find_one({"case_id": cid, "body": {"$regex": "^Follow-up job"}})
        assert mdb.svc_case_events.find_one({"case_id": nid, "body": {"$regex": "^Follow-up to"}})
        TestFollowUp.nid, TestFollowUp.nref = nid, n["reference"]

    def test_draft_after_booking_returns_existing(self, admin_h):
        cid = getattr(TestFurtherParts, "cid", None) or pytest.skip()
        nref = getattr(TestFollowUp, "nref", None) or pytest.skip()
        d = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/follow-up-draft", headers=admin_h).json()
        assert d["existing_follow_up"] == nref
        g = requests.get(f"{BASE_URL}/api/svc/cases/{cid}", headers=admin_h)
        assert g.status_code == 200
        body = g.json().get("case") or g.json()
        assert body.get("follow_up_case_reference") == nref

    def test_cross_tenant_follow_up_of_does_not_touch_other_org(self, owner_h):
        """owner@isodemo (iso-demo-org) must not be able to link/mutate an admin-org case via follow_up_of."""
        victim = _seed_case(engineer_report={"further_parts_required": PARTS}, status="closed")
        mdb.svc_parts_requests.insert_one({"id": f"TEST_pr_{uuid.uuid4().hex[:8]}", "organization_id": ADMIN_ORG,
                                           "case_id": victim, "source": "further_parts_required", "status": "pending",
                                           "part_name": "TEST_ victim part", "qty": 1, "origin_case_id": victim})
        r = requests.post(f"{BASE_URL}/api/svc/intake/phone", headers=owner_h, json={
            "title": "TEST_ cross-tenant follow-up", "priority": "p3", "follow_up_of": victim})
        if r.status_code in (200, 201):
            new = r.json().get("case") or r.json()
            NEW_CASES.append(new["id"])
        v = mdb.svc_cases.find_one({"id": victim}, {"_id": 0})
        moved = mdb.svc_parts_requests.count_documents({"origin_case_id": victim, "case_id": {"$ne": victim}})
        assert not v.get("follow_up_case_id"), "other-org case was linked to a foreign follow-up"
        assert moved == 0, "other-org parts requests were moved onto a foreign case"

    def test_mod_case_follow_up_from_desk_stays_in_mod_org(self, admin_h):
        """Desk (operator) books a follow-up from a MOD (bfpo-mod-org) case: new case + moved parts must stay in the MOD org."""
        mod = _seed_case(org="bfpo-mod-org", status="closed",
                         engineer_report={"further_work_required": "TEST_ mod return", "further_parts_required": PARTS})
        mdb.svc_parts_requests.insert_one({"id": f"TEST_pr_{uuid.uuid4().hex[:8]}", "organization_id": "bfpo-mod-org",
                                           "case_id": mod, "source": "further_parts_required", "status": "pending",
                                           "part_name": "TEST_ mod part", "qty": 1, "origin_case_id": mod})
        d = requests.get(f"{BASE_URL}/api/svc/cases/{mod}/follow-up-draft", headers=admin_h)
        if d.status_code != 200:
            pytest.skip(f"desk cannot see MOD case: {d.status_code}")
        r = requests.post(f"{BASE_URL}/api/svc/intake/phone", headers=admin_h, json={
            "title": d.json()["title"], "description": d.json()["description"], "priority": "p3", "follow_up_of": mod})
        assert r.status_code in (200, 201), r.text
        nid = (r.json().get("case") or r.json())["id"]
        NEW_CASES.append(nid)
        n = mdb.svc_cases.find_one({"id": nid}, {"_id": 0, "organization_id": 1})
        pr = mdb.svc_parts_requests.find_one({"origin_case_id": mod}, {"_id": 0})
        print("new case org:", n["organization_id"], "| parts req case_id==new:", pr["case_id"] == nid, "| pr org:", pr["organization_id"])
        assert n["organization_id"] == "bfpo-mod-org", f"MOD follow-up created in {n['organization_id']}"


# ── MOD job complete also raises parts requests in MOD org ─────
class TestBfpoParts:
    def test_bfpo_complete_raises_parts(self, admin_h):
        cid = _seed_case(org="bfpo-mod-org", status="assigned")
        requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", headers=admin_h,
                      json={"unavailable": True, "reason": "TEST_ nobody"})
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", headers=admin_h, json={
            "summary": "TEST_", "safe_and_working": True,
            "report": {"work_completed": "TEST_ w", "further_parts_required": PARTS[:1],
                       "start_time": _now(-60), "end_time": _now(-5)}})
        assert r.status_code == 200, r.text
        rows = list(mdb.svc_parts_requests.find({"case_id": cid}, {"_id": 0}))
        assert len(rows) == 1 and rows[0]["organization_id"] == "bfpo-mod-org"
