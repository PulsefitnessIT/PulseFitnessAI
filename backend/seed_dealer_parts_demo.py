"""Seed demo data for Dealer Warranty Parts (Phase 1).

Idempotent: creates a handful of international dealers, imports orders
(auto-calculating spare-parts allowance), builds an allocation per dealer
and walks a couple through the approve → dispatch → receive lifecycle so
the dashboard, stores and stock ledger show real numbers.

Runs against the live backend using the iso-demo owner account.
"""
import os
import sys
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    # fall back to frontend .env
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE = line.strip().split("=", 1)[1]
API = f"{BASE}/api"

EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"

DEALERS = [
    {"name": "Fitline Deutschland", "country": "Germany", "region": "EU-Central", "currency": "EUR", "default_percentage": 2.5, "account_manager": "Sarah Klein"},
    {"name": "IberFit España", "country": "Spain", "region": "EU-South", "currency": "EUR", "default_percentage": 3.0, "account_manager": "Diego Ruiz"},
    {"name": "GulfGym Trading", "country": "UAE", "region": "Middle East", "currency": "USD", "default_percentage": 2.0, "account_manager": "Omar Haddad"},
]

ORDERS = {
    "Fitline Deutschland": {"order_reference": "PO-DE-2041", "order_value": 240000,
        "lines": [{"machine_model": "260G Treadmill", "quantity": 12, "unit_value": 8000},
                  {"machine_model": "500 Series Cross Trainer", "quantity": 24, "unit_value": 6000}]},
    "IberFit España": {"order_reference": "PO-ES-1187", "order_value": 96000,
        "lines": [{"machine_model": "260G Treadmill", "quantity": 6, "unit_value": 8000},
                  {"machine_model": "Rower Pro", "quantity": 16, "unit_value": 3000}]},
    "GulfGym Trading": {"order_reference": "PO-AE-3320", "order_value": 150000,
        "lines": [{"machine_model": "500 Series Cross Trainer", "quantity": 15, "unit_value": 6000},
                  {"machine_model": "260G Treadmill", "quantity": 7, "unit_value": 8571}]},
}

ITEMS = {
    "Fitline Deutschland": [
        {"part_sku": "BELT-260G", "part_name": "Running Belt 260G", "machine_model": "260G Treadmill", "quantity": 6, "unit_value": 120, "reason": "Top warranty part for treadmills in EU-Central"},
        {"part_sku": "CONS-260G", "part_name": "Console PCB 260G", "machine_model": "260G Treadmill", "quantity": 3, "unit_value": 340, "reason": "Recurring early-life console failures"},
        {"part_sku": "ROLL-500", "part_name": "Idler Roller 500", "machine_model": "500 Series Cross Trainer", "quantity": 8, "unit_value": 65, "reason": "Wear item, high usage"},
    ],
    "IberFit España": [
        {"part_sku": "BELT-260G", "part_name": "Running Belt 260G", "machine_model": "260G Treadmill", "quantity": 4, "unit_value": 120, "reason": "Belt requests rising in Spain"},
        {"part_sku": "SEAT-ROW", "part_name": "Rower Seat Assembly", "machine_model": "Rower Pro", "quantity": 5, "unit_value": 45, "reason": "Common consumable"},
    ],
    "GulfGym Trading": [
        {"part_sku": "MOTOR-260G", "part_name": "Drive Motor 260G", "machine_model": "260G Treadmill", "quantity": 2, "unit_value": 480, "reason": "High ambient temp reduces motor life"},
        {"part_sku": "ROLL-500", "part_name": "Idler Roller 500", "machine_model": "500 Series Cross Trainer", "quantity": 6, "unit_value": 65, "reason": "Wear item"},
    ],
}

# How far to walk each dealer's allocation through the lifecycle.
LIFECYCLE = {"Fitline Deutschland": "received", "IberFit España": "dispatched", "GulfGym Trading": "approved"}


def main():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    token = r.json().get("token") or r.json().get("access_token")
    h = {"Authorization": f"Bearer {token}"}

    for d in DEALERS:
        dealer = requests.post(f"{API}/dealer-parts/dealers", json=d, headers=h, timeout=30).json()
        did = dealer["id"]
        od = ORDERS[d["name"]]
        order = requests.post(f"{API}/dealer-parts/orders", json={"dealer_id": did, **od}, headers=h, timeout=30).json()
        alloc = requests.post(f"{API}/dealer-parts/allocations",
                              json={"dealer_id": did, "order_id": order["id"], "items": ITEMS[d["name"]]},
                              headers=h, timeout=30).json()
        aid = alloc["id"]
        stage = LIFECYCLE[d["name"]]
        if stage in ("approved", "dispatched", "received"):
            requests.post(f"{API}/dealer-parts/allocations/{aid}/submit", json={}, headers=h, timeout=30)
            requests.post(f"{API}/dealer-parts/allocations/{aid}/approve", json={}, headers=h, timeout=30)
        if stage in ("dispatched", "received"):
            requests.post(f"{API}/dealer-parts/allocations/{aid}/dispatch", json={}, headers=h, timeout=30)
        if stage == "received":
            requests.post(f"{API}/dealer-parts/allocations/{aid}/receive", json={}, headers=h, timeout=30)
        print(f"seeded {d['name']}: allowance={order['allowance']} alloc={alloc['recommended_value']} stage={stage}")

    dash = requests.get(f"{API}/dealer-parts/dashboard", headers=h, timeout=30).json()
    print("dashboard cards:", dash["cards"])


if __name__ == "__main__":
    sys.exit(main())
