# Iter 295 seed/cleanup: MOD fault-wizard photo back-fill (attachment_urls -> attachments)
# Usage: python _seed_fault_photos_295.py seed|clean   (no emails sent; DB rows + 2 stored TEST_ objects)
import os, sys, io, json
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
load_dotenv(os.path.join(BK, ".env"))
from utils.auth import hash_password

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PW = "TestPhoto295#2026"
NOW = datetime.now(timezone.utc).isoformat()
MOD_ORG = "TEST_295_modorg"
OTHER_ORG = "TEST_295_otherorg"
USERS = {"TEST_295_siteuser": (MOD_ORG, "mod_site", "owner"),
         "TEST_295_outsider": (OTHER_ORG, "mod_site", "owner")}
ISSUES = ["TEST_295_i_photos", "TEST_295_i_dupe", "TEST_295_i_gym"]
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".seed_295.json")


def _img(color, fmt="WEBP"):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(b, fmt)
    return b.getvalue()


def seed():
    clean()
    from utils.database import put_object, APP_NAME
    paths = []
    for i, c in enumerate([(200, 30, 30), (30, 160, 60)]):
        p = f"{APP_NAME}/mod-attachments/{MOD_ORG}/TEST_295_photo{i + 1}.webp"
        put_object(p, _img(c), "image/webp")
        paths.append(p)
    for oid in (MOD_ORG, OTHER_ORG):
        db.organizations.insert_one({"id": oid, "name": f"TEST_ 295 {oid}", "account_type": "mod_site", "created_at": NOW})
    db.organizations.insert_one({"id": "TEST_295_gymorg", "name": "TEST_ 295 gym", "account_type": "gym", "created_at": NOW})
    for uid, (oid, at, role) in USERS.items():
        db.users.insert_one({"id": uid, "email": f"{uid.lower()}@example.test", "full_name": f"{uid} Name",
                             "password": hash_password(PW), "role": role, "organization_id": oid, "active": True,
                             "account_type": at, "must_change_password": False, "password_changed_at": NOW,
                             "created_at": NOW})
    db.users.insert_one({"id": "TEST_295_gymowner", "email": "test_295_gymowner@example.test", "full_name": "TEST gym",
                         "password": hash_password(PW), "role": "owner", "organization_id": "TEST_295_gymorg",
                         "active": True, "account_type": "gym", "must_change_password": False,
                         "password_changed_at": NOW, "created_at": NOW})
    upload = {"id": "TEST_295_att_jobsheet", "filename": "TEST_job_sheet.pdf", "content_type": "application/pdf",
              "download_url": "https://example.com/TEST_job_sheet.pdf", "uploaded_by": "Engineer", "uploaded_at": NOW}
    base = {"organization_id": MOD_ORG, "status": "open", "severity": "medium", "created_at": NOW,
            "serial_number": "TST295SER", "machine_type": "Treadmill", "manufacturer": "Technogym",
            "model": "SKILLMILL", "created_by_name": "TEST Site User"}
    db.issues.insert_one({**base, "id": "TEST_295_i_photos", "issue_description": "TEST_ 295 belt slipping with photos",
                          "attachment_urls": paths, "attachments": [upload]})
    db.issues.insert_one({**base, "id": "TEST_295_i_dupe", "issue_description": "TEST_ 295 dupe",
                          "attachment_urls": paths,
                          "attachments": [{"id": "TEST_295_att_existing", "filename": "already merged",
                                           "storage_path": paths[0], "content_type": "image/webp"}]})
    db.issues.insert_one({"id": "TEST_295_i_gym", "organization_id": "TEST_295_gymorg", "status": "open",
                          "severity": "medium", "created_at": NOW, "issue_description": "TEST_ 295 gym",
                          "serial_number": "TST295GYM", "auto_dispatched_supplier_name": "Inda Fitness",
                          "auto_dispatched_supplier_email": "inda295@example.test", "auto_dispatched_at": NOW,
                          "auto_dispatch_delivered_to": ["inda295@example.test"]})
    json.dump({"paths": paths}, open(STATE, "w"))
    print("seeded")


def comments():
    db.supplier_cases.delete_many({"id": "TEST_295_case"})
    db.supplier_case_comments.delete_many({"case_id": "TEST_295_case"})
    db.supplier_cases.insert_one({"id": "TEST_295_case", "issue_id": "TEST_295_i_photos", "token": "TEST_295_case_tok",
                                  "supplier_name": "TEST Sup", "supplier_email": "test_295_sup@example.test",
                                  "current_status": "open", "created_at": NOW})
    for s in ("edit", "del"):
        db.supplier_case_comments.insert_one({"id": f"TEST_295_c_{s}", "case_id": "TEST_295_case",
                                              "author_name": "TEST_295_siteuser Name", "author_role": "gym",
                                              "author_user_id": "TEST_295_siteuser", "message": f"TEST_ msg {s}",
                                              "attachments": [], "created_at": datetime.now(timezone.utc).isoformat()})
    print("comments seeded")


def clean():
    db.email_send_events.delete_many({"to": {"$in": ["TEST_295_r@example.test", "test_295_sup@example.test"]}})
    db.supplier_cases.delete_many({"id": "TEST_295_case"})
    db.supplier_case_comments.delete_many({"case_id": "TEST_295_case"})
    db.users.delete_many({"id": {"$in": list(USERS) + ["TEST_295_gymowner"]}})
    db.organizations.delete_many({"id": {"$in": [MOD_ORG, OTHER_ORG, "TEST_295_gymorg"]}})
    db.issues.delete_many({"id": {"$in": ISSUES + ["TEST_295_i_deliv"]}})
    print("cleaned; left:", db.issues.count_documents({"id": {"$in": ISSUES}}))


if __name__ == "__main__":
    {"seed": seed, "clean": clean, "comments": comments}[sys.argv[1]]()
