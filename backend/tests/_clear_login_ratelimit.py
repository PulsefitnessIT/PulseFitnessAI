"""Test helper: clear login rate-limit buckets so the QA browser run can log in."""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
c = MongoClient(os.environ["MONGO_URL"])
col = c[os.environ["DB_NAME"]]["rate_buckets"]
res = col.delete_many({"_id": {"$regex": "^login"}})
print("cleared login buckets:", res.deleted_count)
