"""Helper for UI testing: seed (upload only, no commit) a fictional mmt_ui_ workbook, or report state / cleanup.
Usage: python tests/mm_ui_seed.py state|seed|cleanup"""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
import sys

sys.path.insert(0, REPO + "/backend")
sys.path.insert(0, REPO + "/backend/tests")
from test_cm_maintenance_master import mdb, _h, _upload, workbook, MM, _cleanup  # noqa: E402

REAL = "e7a84748-9c0d-4415-ba64-d66c621d3dae"


def state():
    u = mdb.crm2_mm_uploads.find_one({"id": REAL}, {"_id": 0, "state": 1, "filename": 1, "summary.counts": 1, "summary.held_mod": 1,
                                                    "summary.totals": 1, "created_at": 1})
    print("REAL:", u)
    print("uploads:", list(mdb.crm2_mm_uploads.find({}, {"_id": 0, "id": 1, "filename": 1, "state": 1, "created_at": 1}).sort("created_at", -1)))
    print("committed real rows:", mdb.crm2_mm_rows.count_documents({"upload_id": REAL, "state": "committed"}))
    print("mm contracts:", mdb.crm2_contracts.count_documents({"mm_record_key": {"$type": "string"}}))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "state":
        state()
    elif cmd == "seed":
        u = _upload("mmt_ui_master.xlsx", workbook(), _h("cm-test-coord"))
        print("seeded", u["id"], u["state"], u["summary"]["counts"])
    elif cmd == "cleanup":
        _cleanup()
        state()
