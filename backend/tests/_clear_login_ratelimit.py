"""Test helper: clear login rate-limit buckets so the QA browser run can log in."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(REPO + "/backend/.env")
c = MongoClient(os.environ["MONGO_URL"])
col = c[os.environ["DB_NAME"]]["rate_buckets"]
res = col.delete_many({"_id": {"$regex": "^login"}})
print("cleared login buckets:", res.deleted_count)
