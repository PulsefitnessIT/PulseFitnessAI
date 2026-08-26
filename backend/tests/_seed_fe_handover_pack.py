"""Seed / cleanup a TEST quote with GRN equipment for the FE Handover-Pack test."""
import os
import sys

import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
_be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
V2 = f"{BASE}/api/crm/v2"
EMAIL, PASSWORD = "owner@isodemo.com", "IsoDemo123!"
NOTE = "TEST_fe_handover_pack_jul2026"


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
    print(f"cleaned {len(qids)}: {qids}")


def seed():
    s = requests.Session()
    r = s.post(f"{BASE}/api/crm/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})

    r = s.post(f"{V2}/quotes", json={
        "notes": NOTE, "vat_rate": 0, "company_name": "TEST_FE Handover Co",
        "lines": [{"description": "TEST_Rower R5", "line_type": "sale", "quantity": 2,
                   "unit_price": 1800, "cost_price": 1100, "manufacturer": "Pulse",
                   "model": "R5", "discount": 0, "warranty_tier": "extended_3yr"}],
    }, timeout=60)
    r.raise_for_status()
    q = r.json().get("quote") or r.json()
    qid = q["id"]

    ful = s.get(f"{V2}/quotes/{qid}/fulfilment", timeout=60).json()
    line_id = ful["procurable_lines"][0]["line_id"]
    po = s.post(f"{V2}/quotes/{qid}/purchase-orders", json={"supplier_name": "TEST_Pulse Supplier"}, timeout=60).json()
    po_id = (po.get("purchase_order") or po).get("id")
    rr = s.post(f"{V2}/quotes/{qid}/purchase-orders/{po_id}/receive",
                json={"items": [{"line_id": line_id, "received_qty": 2,
                                 "serials": ["TEST-FE-1", "TEST-FE-2"]}]}, timeout=90)
    rr.raise_for_status()
    print(f"QUOTE_ID={qid}")
    print(f"QUOTE_NUMBER={q.get('quote_number')}")


if __name__ == "__main__":
    cleanup() if "--cleanup" in sys.argv else seed()
