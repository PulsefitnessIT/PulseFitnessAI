# Snapshot / restore MOD Test Site supplier state (usage: python _mod_site_snapshot.py save|restore)
import pickle, os, sys
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
P = "/tmp/mod_site_snap.pkl"
if sys.argv[1] == "save":
    snap = {"org": db.organizations.find_one({"id": SITE}, {"_id": 0}),
            "eq": list(db.equipment.find({"organization_id": SITE}, {"_id": 0})),
            "sup": list(db.suppliers.find({"organization_id": SITE}, {"_id": 0}))}
    pickle.dump(snap, open(P, "wb"))
    print("saved", len(snap["eq"]), len(snap["sup"]), snap["org"].get("service_supplier_id"))
else:
    snap = pickle.load(open(P, "rb"))
    db.organizations.replace_one({"id": SITE}, snap["org"])
    db.equipment.delete_many({"organization_id": SITE}); db.equipment.insert_many(snap["eq"])
    db.suppliers.delete_many({"organization_id": SITE})
    if snap["sup"]: db.suppliers.insert_many(snap["sup"])
    print("restored")
