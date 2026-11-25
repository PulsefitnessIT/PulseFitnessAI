"""UI-test setup helper: create + publish a TEST_ MOD quotation group via API (Clyde rows). Usage: python mod_quotes_ui_setup.py [publish|state|revise GID]"""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(REPO + "/frontend/.env")
load_dotenv(REPO + "/backend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MQ = f"{API}/mod-ops/quotes"
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
sys.path.insert(0, os.path.dirname(__file__))
from test_mod_quotes_http import ROWS, CUSTOMER  # noqa: E402


def login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{API}/auth/login", json=body, headers=BYPASS, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def publish_flow(m, gid, quotes):
    m.post(f"{MQ}/groups/{gid}/submit").raise_for_status()
    m.post(f"{MQ}/groups/{gid}/approve", json={"approve": True, "commercial_exception_reason": "TEST exception reason for UI test"}).raise_for_status()
    r = m.post(f"{MQ}/groups/{gid}/publish", json={"quote_ids": [q["id"] for q in quotes]})
    r.raise_for_status()


if __name__ == "__main__":
    m = login("modsales.manager@pulsedemo.test", "ModSales123!")
    cmd = sys.argv[1]
    if cmd == "publish":
        r = m.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["AB", "B", "A"], "notes": "TEST_ui"})
        r.raise_for_status()
        g = r.json()
        publish_flow(m, g["id"], g["quotes"])
        print(json.dumps({"gid": g["id"], "quotes": {q["mod_quote_type"]: [q["id"], q["quote_number"], q["total"]] for q in g["quotes"]}}))
    elif cmd == "draft":
        r = m.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A"], "notes": "TEST_ui_draft"})
        print(r.json()["id"])
    elif cmd == "state":
        gid = sys.argv[2]
        g = m.get(f"{MQ}/groups/{gid}").json()
        print(json.dumps({"status": g["status"], "rev": g["revision"], "order": [q["mod_quote_type"] for q in g["quotes"]],
                          "qstatus": {q["mod_quote_type"]: q["status"] for q in g["quotes"]},
                          "events": [(e["kind"], e.get("detail")) for e in g["events"]]}, default=str))
    elif cmd == "cust":
        c = login("modsite.officer@army.mod.test", "ModSite123!", "mod")
        d = c.get(f"{API}/mod/site/quotes").json()
        print(json.dumps({"legacy": [(q["quote_number"], q.get("status"), q.get("mod_group_id")) for q in d["quotes"]][:30],
                          "groups": [(g["id"], g["status"], [q["mod_quote_type"] + ":" + q["status"] for q in g["quotes"]]) for g in d["groups"]]}))
