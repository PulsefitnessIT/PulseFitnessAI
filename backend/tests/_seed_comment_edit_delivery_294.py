# Iter 294 seed/cleanup: gym comment edit/delete + merged Notified card/delivery-status.
# Usage: python _seed_comment_edit_delivery_294.py seed|clean|send
# seed/clean: direct DB rows only (no emails). send: ONE real email to TEST_RECIPIENT_EMAIL
# and stores its message_id on the TEST MOD issue's pulse recipient.
import os, sys, asyncio, json
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BK)
load_dotenv(os.path.join(BK, ".env"))
from utils.auth import hash_password

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PW = "TestCmt294#2026"
NOW = datetime.now(timezone.utc)
iso = lambda d: d.isoformat()

MOD_ORG = "TEST_294_modorg"
GYM_ORG = "TEST_294_gymorg"
OTHER_ORG = "TEST_294_otherorg"
USERS = {
    "TEST_294_owner": (MOD_ORG, "mod_site", "owner", None),
    "TEST_294_other": (MOD_ORG, "mod_site", "owner", None),
    "TEST_294_locked": (MOD_ORG, "mod_site", "staff", ["TEST_294_siteB"]),
    "TEST_294_gymowner": (GYM_ORG, "gym", "owner", None),
    "TEST_294_outsider": (OTHER_ORG, "gym", "owner", None),
}
ISSUES = ["TEST_294_i_mod", "TEST_294_i_gym"]
CASES = ["TEST_294_case_mod", "TEST_294_case_gym"]


def email_of(uid):
    return f"{uid.lower()}@example.test"


def seed():
    clean()
    for oid, at in [(MOD_ORG, "mod_site"), (GYM_ORG, "gym"), (OTHER_ORG, "gym")]:
        db.organizations.insert_one({"id": oid, "name": f"TEST_ 294 {at}", "account_type": at, "created_at": iso(NOW)})
    for uid, (oid, at, role, allowed) in USERS.items():
        d = {"id": uid, "email": email_of(uid), "full_name": f"{uid} Name", "password": hash_password(PW),
             "role": role, "organization_id": oid, "active": True, "account_type": at,
             "must_change_password": False, "password_changed_at": iso(NOW), "created_at": iso(NOW)}
        if allowed:
            d["allowed_site_ids"] = allowed
        db.users.insert_one(d)
    db.equipment.insert_one({"id": "TEST_294_eq", "organization_id": MOD_ORG, "serial_number": "TST294SER",
                             "name": "Treadmill", "manufacturer": "Technogym", "model": "SKILLMILL",
                             "equipment_type": "Treadmill", "created_at": iso(NOW)})
    db.issues.insert_one({
        "id": "TEST_294_i_mod", "organization_id": MOD_ORG, "site_id": "TEST_294_siteA", "status": "open",
        "severity": "medium", "created_at": iso(NOW), "issue_description": "TEST_ 294 belt slipping",
        "serial_number": "TST294SER", "machine_type": "Treadmill", "manufacturer": "Technogym", "model": "SKILLMILL",
        "notified_recipients": [
            {"role": "pulse", "name": "Pulse Ops", "email": "pulse294@example.test", "at": iso(NOW), "delivered": True},
            {"role": "overseas", "name": "Overseas SP", "email": "sp294@example.test", "at": iso(NOW), "delivered": False},
            {"role": "supplier", "name": "Nonsense Supplier", "email": "sup294@example.test", "at": iso(NOW),
             "delivered": True, "message_id": "00000000-0000-0000-0000-000000000294"},
        ],
    })
    db.issues.insert_one({
        "id": "TEST_294_i_gym", "organization_id": GYM_ORG, "status": "open", "severity": "medium",
        "created_at": iso(NOW), "issue_description": "TEST_ 294 gym fault", "serial_number": "TST294GYM",
        "machine_type": "Bike", "auto_dispatched_supplier_name": "Inda Fitness",
        "auto_dispatched_supplier_email": "inda294@example.test", "auto_dispatched_at": iso(NOW),
        "auto_dispatch_delivered_to": ["inda294@example.test"],
    })
    for cid, iid, sname, semail in [("TEST_294_case_mod", "TEST_294_i_mod", "Nonsense Supplier", "sup294@example.test"),
                                    ("TEST_294_case_gym", "TEST_294_i_gym", "Inda Fitness", "inda294@example.test")]:
        db.supplier_cases.insert_one({"id": cid, "issue_id": iid, "token": f"{cid}_tok", "supplier_name": sname,
                                      "supplier_email": semail, "current_status": "open", "created_at": iso(NOW)})
    m = lambda mins: iso(NOW - timedelta(minutes=mins))
    C = "TEST_294_case_mod"
    rows = [
        ("own_edit", "gym", "TEST_294_owner", 2, {}),
        ("own_del", "gym", "TEST_294_owner", 2, {}),
        ("own_ui_edit", "gym", "TEST_294_owner", 1, {}),
        ("own_ui_del", "gym", "TEST_294_owner", 1, {}),
        ("own_old", "gym", "TEST_294_owner", 20, {}),
        ("other", "gym", "TEST_294_other", 2, {}),
        ("supplier", "supplier", None, 2, {}),
        ("legacy", "gym", None, 2, {}),
        ("deleted", "gym", "TEST_294_owner", 2, {"deleted_at": m(1)}),
    ]
    for suf, role, author, mins, extra in rows:
        d = {"id": f"TEST_294_c_{suf}", "case_id": C, "author_name": f"TEST {suf}", "author_role": role,
             "message": f"TEST_ msg {suf}", "attachments": [], "created_at": m(mins), **extra}
        if author:
            d["author_user_id"] = author
        db.supplier_case_comments.insert_one(d)
    print("seeded")


def clean():
    db.users.delete_many({"id": {"$in": list(USERS)}})
    db.organizations.delete_many({"id": {"$in": [MOD_ORG, GYM_ORG, OTHER_ORG]}})
    db.equipment.delete_many({"id": "TEST_294_eq"})
    db.issues.delete_many({"id": {"$in": ISSUES}})
    db.supplier_cases.delete_many({"id": {"$in": CASES}})
    db.supplier_case_comments.delete_many({"case_id": {"$in": CASES}})
    print("cleaned; left:", db.issues.count_documents({"id": {"$in": ISSUES}}),
          db.supplier_case_comments.count_documents({"case_id": {"$in": CASES}}))


def send():
    from utils.email import send_email
    out = {}
    ok = asyncio.run(send_email(to=os.environ["TEST_RECIPIENT_EMAIL"], subject="Delivery tick check",
                                html="<p>t</p>", kind="system.ops_alert", category="mod", result_out=out))
    mid = out.get("message_id")
    ev = db.email_send_events.find_one({"resend_id": mid}, {"_id": 0, "resend_id": 1, "status": 1}) if mid else None
    print(json.dumps({"ok": ok, "has_message_id": bool(mid), "event_row_has_resend_id": bool(ev and ev.get("resend_id")),
                      "event_status": (ev or {}).get("status")}))
    if mid:
        db.issues.update_one({"id": "TEST_294_i_mod", "notified_recipients.role": "pulse"},
                             {"$set": {"notified_recipients.$.message_id": mid}})


if __name__ == "__main__":
    {"seed": seed, "clean": clean, "send": send}[sys.argv[1]]()
