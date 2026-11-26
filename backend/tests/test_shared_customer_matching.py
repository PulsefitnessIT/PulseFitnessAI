"""Sicon sync + Aftersales estate onboarding use the shared customer identity (same matching as Sage imports)."""
import asyncio
import uuid

from utils.database import db


def test_sicon_and_afs_use_shared_identity():
    asyncio.run(_run())


async def _run():
    from utils import customer_identity as CI
    from utils import sicon_onboarding as SO
    from routes import crm_afs_onboarding as AFS

    tag = uuid.uuid4().hex[:6].upper()
    op = f"TSTOP-{tag}"
    ref_a, ref_b = f"SHA{tag}", f"SHB{tag}"
    created = []
    try:
        # A: Sage-imported org that already has an internal CRM mirror.
        org_a, _ = await CI.provision_customer_org({"name": f"Shared Alpha {tag} Gym"}, source="test", actor="t", ref=ref_a,
                                                   confirmed_new=True)
        org_b, _ = await CI.provision_customer_org({"name": f"Zebra Bravo {tag} Leisure"}, source="test", actor="t", ref=ref_b,
                                                   confirmed_new=True)
        created += [org_a, org_b]
        mirror = str(uuid.uuid4())
        await db.crm2_companies.insert_one({"id": mirror, "organization_id": op, "name": "Alpha mirror",
                                            "linked_organization_id": org_a, "account_number": ref_a})

        cls = await SO.classify_customer(op, None, ref_a, "Completely different name")
        assert cls["bucket"] == "matched" and cls["pulse_id"] == mirror, cls

        # B: org exists but no CRM mirror -> Sicon creates one CRM company, linked to the org (no new org).
        n_orgs = await db.organizations.count_documents({})
        res = await SO.sync_customer(op, None, ref_b, "Bravo from Sicon", True, "run-test")
        assert res["bucket"] == "new"
        doc = await db.crm2_companies.find_one({"id": res["pulse_id"]}, {"_id": 0})
        assert doc["linked_organization_id"] == org_b and doc["account_number"] == ref_b
        assert await db.organizations.count_documents({}) == n_orgs
        # re-run is idempotent: matches the same CRM company
        res2 = await SO.sync_customer(op, None, ref_b, "Bravo from Sicon", True, "run-test")
        assert res2["bucket"] == "matched" and res2["pulse_id"] == res["pulse_id"]

        # C: Aftersales candidates include customer organisations from the shared identity service.
        await db.crm2_companies.delete_many({"organization_id": op, "linked_organization_id": org_b})
        cands = await AFS._customer_candidates(op, f"Zebra Bravo {tag} Leisure")
        assert any(c["id"] == f"org:{org_b}" and c.get("kind") == "organisation" for c in cands), cands
        # orgs already represented by a CRM candidate are not listed twice
        cands_a = await AFS._customer_candidates(op, "Alpha mirror")
        assert not any(c["id"] == f"org:{org_a}" for c in cands_a)
    finally:
        await db.crm2_companies.delete_many({"organization_id": op})
        await db.customer_account_refs.delete_many({"ref": {"$in": [ref_a, ref_b]}})
        await db.organizations.delete_many({"id": {"$in": created}})
        await db.onboarding_audit_events.delete_many({"org_id": {"$in": created}})
