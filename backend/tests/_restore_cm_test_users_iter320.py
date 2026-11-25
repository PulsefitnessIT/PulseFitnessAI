"""Test helper: restore fictional cm.* test users to pre-iter-320 snapshot (only touches cm-test-fin / cm-test-none fields)."""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
print(db.users.update_one({"id": "cm-test-fin"}, {"$set": {"crm_workspace_extra_permissions": None}}).modified_count)
print(db.users.update_one({"id": "cm-test-none"}, {"$unset": {"module_overrides.mod_operations": ""},
                                                   "$set": {"crm_workspace_role": None, "mod_quote_role": None,
                                                            "crm_override_from_workspace": False,
                                                            "module_overrides.crm": False}}).modified_count)
