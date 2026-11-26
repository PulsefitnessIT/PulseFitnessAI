"""Retest of iteration_334 fixes: CRM /me home_organization_id (auth loop), create-new keeps prevCompany,
org pick reuses exact-name unlinked CRM company, non-operator LITE orgs stamped created_by_org_id + ineligible."""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_afs_shared_customer_matching_api import (  # noqa: E402,F401
    API, BASE_URL, CREATED, MDB, OP, TAG, H, _cleanup, _commit, _import, _mk_crm, _mk_org, _status)

ADMIN = {"email": "admin@pulsefitness.com", "password": "C2s9yJ3YAhydB4d34-Bykg"}
ISO_CREDS = {"email": "owner@isodemo.com", "password": "IsoDemo123!"}


def _main_me(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200 and r.json().get("token"), r.text
    me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}, timeout=30)
    assert me.status_code == 200, me.text
    j = me.json()
    return (j.get("user") or j).get("organization_id")


def _crm_me(creds):
    r = requests.post(f"{BASE_URL}/api/crm/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    me = requests.get(f"{BASE_URL}/api/crm/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}, timeout=30)
    assert me.status_code == 200, me.text
    return me.json()


@pytest.fixture(scope="module")
def ISO():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login", json=ISO_CREDS, timeout=30)
    if r.status_code != 200:
        pytest.skip("iso login failed")
    return {"Authorization": f"Bearer {r.json()['token']}"}


# CRM /me home_organization_id (fix for master-admin crm_token loop)
class TestCrmMeHomeOrg:
    def test_master_admin_home_org_matches_main(self):
        main_org = _main_me(ADMIN)
        me = _crm_me(ADMIN)
        assert me["organization_id"] == OP, me
        assert me["home_organization_id"] == main_org, (me.get("home_organization_id"), main_org)

    def test_tenant_home_org_equals_org(self):
        main_org = _main_me(ISO_CREDS)
        me = _crm_me(ISO_CREDS)
        assert me["organization_id"] == main_org
        assert me["home_organization_id"] == main_org


# Create new after CRM-company 409 keeps the CRM company (no duplicate CRM record)
class TestCreateNewKeepsCrm:
    def test_create_new_with_prev_company(self, H):
        name = f"TEST_{TAG} Platypus Gym"
        org = _mk_org(name)
        crm = _mk_crm(name)
        iid = _import(H, name)
        r = _commit(H, iid, company_id=crm)
        assert r.status_code == 409, r.text
        assert any(c["id"] == f"org:{org}" for c in r.json()["detail"]["candidates"])
        assert MDB.crm2_companies.find_one({"id": crm}).get("linked_organization_id") in (None, "")
        r2 = _commit(H, iid, company_id=crm, create_new_customer=True)
        assert r2.status_code == 200, r2.text
        c = r2.json()["committed"]
        CREATED["orgs"].append(c["customer_org_id"])
        assert c["crm_company_id"] == crm
        assert c["customer_org_id"] != org
        assert MDB.crm2_companies.find_one({"id": crm})["linked_organization_id"] == c["customer_org_id"]
        assert MDB.crm2_companies.count_documents({"organization_id": OP, "name": name}) == 1
        assert MDB.sites.count_documents({"organization_id": org}) == 0


# Picking org candidate links the exact-name unlinked CRM company
class TestOrgPickReusesCrm:
    def test_org_only_links_unlinked_exact_crm(self, H):
        name = f"TEST_{TAG} Pangolin Fitness"
        org = _mk_org(name)
        crm = _mk_crm(name)
        iid = _import(H, name)
        r = _commit(H, iid, company_id=f"org:{org}")
        assert r.status_code == 200, r.text
        c = r.json()["committed"]
        assert c["customer_org_id"] == org
        assert c["crm_company_id"] == crm
        assert MDB.crm2_companies.find_one({"id": crm})["linked_organization_id"] == org
        assert MDB.crm2_companies.count_documents({"organization_id": OP, "name": name}) == 1

    def test_ineligible_org_leaves_crm_unlinked(self, H):
        name = f"TEST_{TAG} Narwhal Club"
        org = _mk_org(name, account_type="full")
        crm = _mk_crm(name)
        iid = _import(H, name)
        assert _commit(H, iid, customer_org_id=org).status_code == 404
        assert MDB.crm2_companies.find_one({"id": crm}).get("linked_organization_id") in (None, "")
        assert _status(iid) not in ("committing", "committed")

    def test_already_committed_leaves_no_link(self, H):
        name = f"TEST_{TAG} Ibis Leisure"
        org = _mk_org(name)
        crm = _mk_crm(name)
        iid = _import(H, name)
        MDB.crm2_afs_onboarding.update_one({"id": iid}, {"$set": {"status": "committing"}})
        assert _commit(H, iid, company_id=crm, customer_org_id=org).status_code == 409
        assert MDB.crm2_companies.find_one({"id": crm}).get("linked_organization_id") in (None, "")
        MDB.crm2_afs_onboarding.update_one({"id": iid}, {"$set": {"status": "ready"}})


# Non-operator LITE orgs are stamped + not eligible for the Pulse operator
class TestNonOperatorOrgStamp:
    def test_iso_created_org_ineligible_for_operator(self, H, ISO):
        name = f"TEST_{TAG} Iso Owned Marmot"
        iid = _import(ISO, name)
        r = _commit(ISO, iid, create_new_customer=True)
        assert r.status_code == 200, r.text
        new = r.json()["committed"]["customer_org_id"]
        CREATED["orgs"].append(new)
        o = MDB.organizations.find_one({"id": new})
        iso_org = MDB.crm2_afs_onboarding.find_one({"id": iid})["organization_id"]
        assert o.get("created_by_org_id") == iso_org, o.get("created_by_org_id")
        iid2 = _import(H, name)
        rc = requests.get(f"{API}/{iid2}/reconcile", headers=H, timeout=30).json()
        assert f"org:{new}" not in [c["id"] for c in rc["candidates"]]
        assert _commit(H, iid2, customer_org_id=new).status_code == 404
        assert MDB.sites.count_documents({"organization_id": new}) == 1

    def test_operator_created_org_not_stamped_foreign(self, H):
        name = f"TEST_{TAG} Operator Fresh Heron"
        iid = _import(H, name)
        r = _commit(H, iid, create_new_customer=True)
        assert r.status_code == 200, r.text
        new = r.json()["committed"]["customer_org_id"]
        CREATED["orgs"].append(new)
        assert MDB.organizations.find_one({"id": new}).get("created_by_org_id") in (None, "", OP)
