"""Contracts & Renewals backup / restore (BSON, per organisation).

  python scripts/cm_backup.py backup  --org <org_id> --out /app/backups/cm-YYYYMMDD
  python scripts/cm_backup.py restore --src /app/backups/cm-YYYYMMDD --target-db <db>   (never the live DB unless --live)
  python scripts/cm_backup.py verify  --src /app/backups/cm-YYYYMMDD --target-db <db>

Restore only inserts documents that are missing (by _id) — it never deletes or overwrites.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import bson
from pymongo import MongoClient

COLLS = ("crm2_contracts", "crm2_companies", "crm2_contract_changes", "crm2_mm_uploads", "crm2_mm_rows",
         "crm2_afs_service_schedules", "crm2_afs_billing", "crm2_afs_agreements", "crm2_sicon_contract_queue",
         "crm2_mm_cutover", "crm2_activities")
FILES = ("mm_workbooks.files", "mm_workbooks.chunks")


def _db(name=None):
    return MongoClient(os.environ["MONGO_URL"])[name or os.environ["DB_NAME"]]


def backup(org, out):
    db = _db()
    os.makedirs(out, exist_ok=True)
    manifest = {"org": org, "db": os.environ["DB_NAME"], "at": datetime.now(timezone.utc).isoformat(), "counts": {}}
    for c in COLLS:
        docs = list(db[c].find({"organization_id": org}))
        with open(os.path.join(out, f"{c}.bson"), "wb") as f:
            for d in docs:
                f.write(bson.encode(d))
        manifest["counts"][c] = len(docs)
    files = list(db["mm_workbooks.files"].find({"metadata.organization_id": org}))
    chunks = list(db["mm_workbooks.chunks"].find({"files_id": {"$in": [f["_id"] for f in files]}}))
    for name, docs in (("mm_workbooks.files", files), ("mm_workbooks.chunks", chunks)):
        with open(os.path.join(out, f"{name}.bson"), "wb") as f:
            for d in docs:
                f.write(bson.encode(d))
        manifest["counts"][name] = len(docs)
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    return manifest


def _read(src, name):
    p = os.path.join(src, f"{name}.bson")
    return bson.decode_all(open(p, "rb").read()) if os.path.exists(p) else []


def restore(src, target, live=False):
    if target == os.environ["DB_NAME"] and not live:
        sys.exit("Refusing to restore into the live database without --live")
    db, added = _db(target), {}
    for name in COLLS + FILES:
        n = 0
        for d in _read(src, name):
            if not db[name].find_one({"_id": d["_id"]}, {"_id": 1}):
                db[name].insert_one(d)
                n += 1
        added[name] = n
    return added


def verify(src, target):
    m = json.load(open(os.path.join(src, "manifest.json")))
    db = _db(target)
    out = {}
    for name, n in m["counts"].items():
        ids = [d["_id"] for d in _read(src, name)]
        out[name] = {"backup": n, "present": db[name].count_documents({"_id": {"$in": ids}}) if ids else 0}
    return {"ok": all(v["backup"] == v["present"] for v in out.values()), "collections": out}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backup", "restore", "verify"])
    ap.add_argument("--org")
    ap.add_argument("--out")
    ap.add_argument("--src")
    ap.add_argument("--target-db")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    if a.cmd == "backup":
        print(json.dumps(backup(a.org, a.out), indent=1))
    elif a.cmd == "restore":
        print(json.dumps(restore(a.src, a.target_db, a.live), indent=1))
    else:
        print(json.dumps(verify(a.src, a.target_db), indent=1))
