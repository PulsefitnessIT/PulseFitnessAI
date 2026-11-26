"""Retest of iteration_333 fixes: operator-only org matching, company_id+customer_org_id link, billing validation
before writes, account_ref multi-hit 409, copy/match labels. Reuses helpers + cleanup from the base suite."""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_afs_shared_customer_matching_api import (  # noqa: E402,F401
    API, BASE_URL, CREATED, MDB, OP, TAG, H, _cleanup, _commit, _import, _mk_crm, _mk_org, _n_orgs, _status)


@pytest.fixture(scope="module")
def ISO():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login", json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"iso CRM login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cands(h, iid):
    r = requests.get(f"{API}/{iid}/reconcile", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["candidates"]


# (1) cross-tenant isolation
class TestTenantIsolation:
    def test_non_operator_sees_no_org_candidates(self, ISO):
        org = _mk_org(f"TEST_{TAG} Isolated Lemur")
        iid = _import(ISO, f"TEST_{TAG} Isolated Lemur")
        ids = [c["id"] for c in _cands(ISO, iid)]
        assert not any(i.startswith("org:") for i in ids), ids
        assert f"org:{org}" not in ids

    def test_non_operator_cannot_link_org(self, ISO):
        org = _mk_org(f"TEST_{TAG} Isolated Gecko")
        iid = _import(ISO, f"TEST_{TAG} Isolated Gecko")
        for body in ({"company_id": f"org:{org}"}, {"customer_org_id": org}):
            r = _commit(ISO, iid, **body)
            assert r.status_code == 404, (body, r.status_code, r.text)
        assert _status(iid) not in ("committing", "committed")
        assert MDB.sites.count_documents({"organization_id": org}) == 0

    def test_non_operator_account_ref_does_not_autolink(self, ISO):
        ref = f"TREF{TAG}ISO"
        org = _mk_org(f"TEST_{TAG} Ref Owl", ref=ref)
        iid = _import(ISO, f"TEST_{TAG} Unrelated Iso Customer")
        r = _commit(ISO, iid, account_ref=ref, create_new_customer=True)
        assert r.status_code == 200, r.text
        new = r.json()["committed"]["customer_org_id"]
        CREATED["orgs"].append(new)
        assert new != org
        assert MDB.users.count_documents({"organization_id": new}) == 0

    @pytest.mark.parametrize("atype", ["full", "service_provider", "mod_site", None])
    def test_operator_ineligible_org_types(self, H, atype):
        org = _mk_org(f"TEST_{TAG} Ineligible {atype} Tapir", account_type=atype)
        iid = _import(H, f"TEST_{TAG} Ineligible {atype} Tapir")
        assert f"org:{org}" not in [c["id"] for c in _cands(H, iid)]
        assert _commit(H, iid, customer_org_id=org).status_code == 404

    def test_operator_platform_admin_and_operator_orgs_rejected(self, H):
        admin_org = (MDB.users.find_one({"is_master_admin": True}, {"organization_id": 1}) or {}).get("organization_id")
        iid = _import(H, f"TEST_{TAG} Guard Admin")
        assert _commit(H, iid, customer_org_id=OP).status_code == 404
        if admin_org:
            assert _commit(H, iid, customer_org_id=admin_org).status_code == 404

    def test_mirrored_non_lite_org_eligible(self, H):
        org = _mk_org(f"TEST_{TAG} Mirrored Bison", account_type="gym")
        crm = _mk_crm(f"TEST_{TAG} Mirrored Bison CRM", linked_organization_id=org)
        iid = _import(H, f"TEST_{TAG} Mirrored Bison CRM")
        r = _commit(H, iid, customer_org_id=org)
        assert r.status_code == 200, r.text
        assert r.json()["committed"]["crm_company_id"] == crm


# (2) company_id + customer_org_id together
class TestCompanyPlusOrg:
    def test_409_then_retry_with_both_links_same_crm(self, H):
        org = _mk_org(f"TEST_{TAG} Wombat Club")
        crm = _mk_crm(f"TEST_{TAG} Wombat Club")
        iid = _import(H, f"TEST_{TAG} Wombat Club")
        r = _commit(H, iid, company_id=crm)
        assert r.status_code == 409, r.text
        assert any(c["id"] == f"org:{org}" for c in r.json()["detail"]["candidates"])
        r2 = _commit(H, iid, company_id=crm, customer_org_id=org)
        assert r2.status_code == 200, r2.text
        com = r2.json()["committed"]
        assert com["crm_company_id"] == crm and com["customer_org_id"] == org
        assert MDB.crm2_companies.find_one({"id": crm})["linked_organization_id"] == org
        assert MDB.crm2_companies.count_documents({"organization_id": OP, "name": f"TEST_{TAG} Wombat Club"}) == 1

    def test_crm_linked_to_other_org_409(self, H):
        a = _mk_org(f"TEST_{TAG} Otter A")
        b = _mk_org(f"TEST_{TAG} Otter B")
        crm = _mk_crm(f"TEST_{TAG} Otter A", linked_organization_id=a)
        iid = _import(H, f"TEST_{TAG} Otter A")
        r = _commit(H, iid, company_id=crm, customer_org_id=b)
        assert r.status_code == 409, r.text
        assert MDB.crm2_companies.find_one({"id": crm})["linked_organization_id"] == a
        assert _status(iid) not in ("committing", "committed")


# (3) billing_frequency validated before writes
class TestBillingValidation:
    def test_invalid_freq_with_both_ids_no_writes(self, H):
        org = _mk_org(f"TEST_{TAG} Freq Heron")
        crm = _mk_crm(f"TEST_{TAG} Freq Heron")
        iid = _import(H, f"TEST_{TAG} Freq Heron")
        r = _commit(H, iid, company_id=crm, customer_org_id=org, billing_frequency="fortnightly")
        assert r.status_code == 400
        assert not MDB.crm2_companies.find_one({"id": crm}).get("linked_organization_id")
        assert MDB.sites.count_documents({"organization_id": org}) == 0

    def test_invalid_freq_create_new_no_org(self, H):
        iid = _import(H, f"TEST_{TAG} Freq Newbie Zzq")
        n = _n_orgs()
        r = _commit(H, iid, create_new_customer=True, billing_frequency="weekly")
        assert r.status_code == 400
        assert _n_orgs() == n


# (4) account_ref -> >1 org
class TestAccountRefMulti:
    def test_multi_hit_409_candidates(self, H):
        ref = f"TREF{TAG}M"
        a = _mk_org(f"TEST_{TAG} Multi Ref One", ref=ref)
        b = _mk_org(f"TEST_{TAG} Multi Ref Two")
        MDB.organizations.update_one({"id": b}, {"$set": {"customer_account_number": ref}})  # 2nd hit via org field
        iid = _import(H, f"TEST_{TAG} Multi Ref Whatever")
        n = _n_orgs()
        r = _commit(H, iid, account_ref=ref)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "customer_match_required"
        ids = {c["id"] for c in d["candidates"]}
        assert {f"org:{a}", f"org:{b}"} <= ids
        assert _n_orgs() == n and _status(iid) not in ("committing", "committed")


# (5) copy + exact match label
class TestCopy:
    def test_exact_org_match_and_message(self, H):
        org = _mk_org(f"TEST_{TAG} Exact Puffin")
        iid = _import(H, f"TEST_{TAG} Exact Puffin")
        c = [x for x in _cands(H, iid) if x["id"] == f"org:{org}"]
        assert c and c[0]["match"] == "exact"
        r = _commit(H, iid)
        assert r.status_code == 409
        assert "Link the existing customer" in r.json()["detail"]["message"]
