"""Test helper: print access-related fields of fictional cm.* / vc.driver test users (read-only)."""
import os, json
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
F = ["id", "email", "role", "organization_id", "crm_workspace_role", "crm_override_from_workspace", "module_overrides",
     "mod_quote_role", "crm_workspace_extra_permissions", "department"]
for u in db.users.find({"email": {"$regex": r"^(cm\.|vc\.driver).*@pulsefitness\.test$"}}, {"_id": 0}):
    st = db.staff_members.find_one({"$or": [{"user_id": u["id"]}, {"email": u["email"]}]}, {"_id": 0, "id": 1, "primary_role": 1, "department": 1, "status": 1})
    print(json.dumps({**{k: u.get(k) for k in F}, "staff": st}, default=str))
