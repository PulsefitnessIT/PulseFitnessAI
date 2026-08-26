"""Seed a delivered TEST quote for the FE Customer-Register-Handover test.

Creates a CPQ v2 quote for the seeded linked company HANDOVER-TEST-CO
(iso-demo-org -> tenant org 'handover-test-portal'), raises a PO and receives
2 units with serials so the handover panel shows 0/2 pending.

Usage:  python tests/_seed_fe_handover_quote.py            # seed
        python tests/_seed_fe_handover_quote.py --cleanup  # remove TEST data
"""
import os
import sys

import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
_be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
V2 = f"{BASE}/api/crm/v2"
EMAIL, PASSWORD = "owner@isodemo.com", "IsoDemo123!"
NOTE = "TEST_fe_customer_handover"


def _db():
    from pymongo import MongoClient
    mc = MongoClient(_be["MONGO_URL"])
    return mc, mc[_be["DB_NAME"]]


def cleanup():
    mc, db = _db()
    qids = [q["id"] for q in db.crm2_quotes.find({"notes": NOTE}, {"id": 1})]
    for qid in qids:
        db.crm2_quotes.delete_many({"id": qid})
        db.purchase_orders.delete_many({"quote_id": qid})
        db.equipment.delete_many({"quote_id": qid})
        db.crm2_invoices.delete_many({"quote_id": qid})
        db.issues.delete_many({"quote_id": qid})
        db.svc_cases.delete_many({"quote_id": qid})
    mc.close()
    print(f"cleaned {len(qids)} TEST quote(s): {qids}")


def seed():
    s = requests.Session()
    r = s.post(f"{BASE}/api/crm/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})

    r = s.post(f"{V2}/quotes", json={
        "notes": NOTE, "vat_rate": 0,
        "company_id": "HANDOVER-TEST-CO", "company_name": "Handover Test Gym",
        "lines": [{"description": "Spin Bike", "line_type": "sale", "quantity": 2,
                   "unit_price": 1500, "cost_price": 900, "manufacturer": "Pulse",
                   "model": "SB-1", "discount": 0}],
    }, timeout=60)
    r.raise_for_status()
    q = r.json().get("quote") or r.json()
    qid = q["id"]

    r = s.post(f"{V2}/quotes/{qid}/purchase-orders", json={"supplier_name": "ACME", "vat_rate": 0}, timeout=60)
    r.raise_for_status()
    po = r.json()["purchase_order"]
    line_id = next(i["line_id"] for i in po["items"] if i["is_equipment"])
    r = s.post(f"{V2}/quotes/{qid}/purchase-orders/{po['id']}/receive",
               json={"items": [{"line_id": line_id, "received_qty": 2, "serials": ["SPIN-1", "SPIN-2"]}]}, timeout=60)
    r.raise_for_status()

    r = s.get(f"{V2}/quotes/{qid}/handover", timeout=60)
    print("QUOTE_ID=", qid)
    print("QUOTE_NUMBER=", q.get("quote_number"))
    print("customer_portal=", r.json()["customer_portal"])


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        seed()
