"""Schedule B boot bootstrap: cross-replica lock + repair of a split (duplicate) version from the same file."""
import asyncio

import pytest

from utils.database import db
from utils import mod_schedule_b_bootstrap as boot


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clean():
    yield
    _run(db.mod_sor_price_lists.delete_many({"version": "TEST-DUP-VERSION"}))
    _run(db.mod_sor_rate_card.delete_many({"id": "TEST-dup-row"}))
    _run(db.mod_bootstrap_locks.delete_many({"_id": boot.LOCK_ID}))


def test_only_one_replica_runs_bootstrap():
    async def both():
        return await asyncio.gather(boot._take_lock(), boot._take_lock())
    got = _run(both())
    assert sorted(got) == [False, True]


def test_concurrent_ensure_does_not_create_second_version():
    before = _run(db.mod_sor_price_lists.count_documents({"sha256": boot.SHA256}))

    async def both():
        return await asyncio.gather(boot.ensure_year4_schedule_b(), boot.ensure_year4_schedule_b())
    _run(both())
    assert _run(db.mod_sor_price_lists.count_documents({"sha256": boot.SHA256})) == before
    assert _run(db.mod_sor_price_lists.count_documents({"status": "live"})) == 1


def test_repair_repoints_rows_from_duplicate_version():
    live = _run(db.mod_sor_price_lists.find_one({"sha256": boot.SHA256, "status": "live"}, {"_id": 0, "version": 1}))
    if not live:
        pytest.skip("approved Year 4 list is not live in this database")
    _run(db.mod_sor_price_lists.insert_one({"id": "TEST-dup", "version": "TEST-DUP-VERSION", "sha256": boot.SHA256, "status": "superseded"}))
    _run(db.mod_sor_rate_card.insert_one({"id": "TEST-dup-row", "label": "TEST row", "price_list_version": "TEST-DUP-VERSION"}))
    assert _run(boot.repair_split_versions()) == 1
    row = _run(db.mod_sor_rate_card.find_one({"id": "TEST-dup-row"}))
    assert row["price_list_version"] == live["version"] and row["repointed_from"] == ["TEST-DUP-VERSION"]
    dup = _run(db.mod_sor_price_lists.find_one({"id": "TEST-dup"}))
    assert dup["status"] == "duplicate_superseded" and dup["duplicate_of"] == live["version"]
    assert _run(boot.repair_split_versions()) == 0
