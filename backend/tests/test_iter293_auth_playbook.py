"""Auth playbook checks: bcrypt format, httpOnly cookies, CORS, brute-force lockout."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET") or be.get("RATE_LIMIT_BYPASS_SECRET") or ""
CREDS = {"email": "owner@isodemo.com", "password": "IsoDemo123!"}


# bcrypt hash format in the DB
def test_password_hashes_are_bcrypt_2b():
    mongo_url = os.environ.get("MONGO_URL") or be.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or be.get("DB_NAME")
    if not mongo_url:
        pytest.skip("MONGO_URL unavailable")
    from pymongo import MongoClient
    cli = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    doc = cli[db_name]["users"].find_one({"email": CREDS["email"]}, {"password": 1, "_id": 0})
    cli.close()
    assert doc and doc.get("password"), "user/password not found"
    assert doc["password"].startswith("$2b$"), f"unexpected hash prefix: {doc['password'][:6]}"


# httpOnly session cookies on login
def test_login_sets_httponly_cookies():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS,
               headers={"X-RateLimit-Bypass": BYPASS}, timeout=40)
    assert r.status_code == 200, r.text[:300]
    raw = "; ".join(r.raw.headers.getlist("Set-Cookie")) if hasattr(r.raw, "headers") else ""
    names = [c.name for c in s.cookies]
    assert names, f"no cookies set on login (Set-Cookie: {raw[:200]})"
    assert "HttpOnly" in raw, f"cookies not HttpOnly: {raw[:300]}"
    assert "ga_session" in raw or "ga_refresh" in raw, names


# CORS: credentials allowed for an explicit origin (not wildcard).
# NOTE: the preview edge (Cloudflare/ingress) REWRITES CORS headers to `*` on
# public preflights, so the APP's own policy is asserted on the internal port.
APP_ORIGIN = "http://localhost:8001"


def _preflight(app_base, origin):
    return requests.options(
        f"{app_base}/api/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"}, timeout=15)


def test_cors_allows_credentials_with_explicit_origin():
    origin = BASE_URL
    r = _preflight(APP_ORIGIN, origin)
    allow_origin = r.headers.get("access-control-allow-origin", "")
    allow_creds = r.headers.get("access-control-allow-credentials", "")
    assert allow_origin != "*", "wildcard origin with credentials is invalid"
    assert allow_origin == origin, f"expected echoed origin, got {allow_origin!r}"
    assert allow_creds.lower() == "true", allow_creds


def test_cors_rejects_unknown_origin():
    r = _preflight(APP_ORIGIN, "https://evil.example.com")
    allow_origin = r.headers.get("access-control-allow-origin", "")
    assert allow_origin != "https://evil.example.com", "rogue origin echoed by app CORS"
    assert allow_origin != "*", allow_origin


# brute-force lockout after 5 failures (uses a throwaway email — no real account affected)
def test_brute_force_lockout_after_five_failures():
    email = f"TEST_lockout_{uuid.uuid4().hex[:10]}@example.invalid"
    codes = []
    for _ in range(7):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "WrongPassw0rd!x"},
                          headers={"X-RateLimit-Bypass": BYPASS}, timeout=30)
        codes.append(r.status_code)
    assert 429 in codes, f"no lockout after 7 failures: {codes}"
    assert codes.index(429) >= 5, f"locked out too early: {codes}"
