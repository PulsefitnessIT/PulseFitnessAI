"""Seed a staff account for frontend UI testing. Prints creds+reset token."""
import os, uuid, requests, sys
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip().strip('"')
MURL = os.environ["MONGO_URL"]; DBN = os.environ["DB_NAME"]

tag = f"ui_{uuid.uuid4().hex[:6]}"
email = f"test_ui_{tag}@example.com".lower()
pwd = "UIPass123!"

tok = requests.post(f"{BASE}/api/auth/login", json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}).json()["token"]
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
r = requests.post(f"{BASE}/api/staff-onboarding/cases",
    json={"legal_first_name":"Uitest","surname":"User","personal_email":email,"position":"Instructor"}, headers=h).json()
case_id, staff_id = r["id"], r["staff_id"]
inv = requests.post(f"{BASE}/api/staff-onboarding/cases/{case_id}/invite", json={"expiry_days":7}, headers=h).json()
invite_token = inv["invite_token"]
requests.post(f"{BASE}/api/new-starter/accept-invite", json={"token":invite_token,"password":pwd})

print(f"EMAIL={email}")
print(f"PASSWORD={pwd}")
print(f"CASE_ID={case_id}")
print(f"STAFF_ID={staff_id}")
print(f"INVITE_TOKEN={invite_token}")
print(f"BASE={BASE}")
