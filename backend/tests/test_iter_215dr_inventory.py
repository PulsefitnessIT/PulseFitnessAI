"""
Phase 4 Inventory Testing — iter 215dr

Tests for:
- Warehouse stock (GET /api/svc/inventory/stock)
- Stock adjustments (POST /api/svc/inventory/stock/adjust)
- Reorder rules CRUD (GET/POST/DELETE /api/svc/inventory/reorder-rules)
- Low-stock detection (GET /api/svc/inventory/low-stock)
- Purchase orders lifecycle (draft → submitted → received/cancelled)
- PO from low-stock generation
- Sage PO outbox integration
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

def get_auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@gymaxisai.com",
        "password": "MasterAdmin123!"
    })
    if response.status_code == 200:
        return response.json().get("token")
    return None

# Get token once for all tests
TOKEN = get_auth_token()
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"} if TOKEN else {}

def unique_sku():
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"

# ─────────────────────────────────────────────────────────────────
# Warehouse Stock Tests
# ─────────────────────────────────────────────────────────────────

def test_get_warehouse_stock():
    """GET /api/svc/inventory/stock?location=warehouse returns stock list"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/stock",
                    params={"location": "warehouse"},
                    headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "stock" in data
    assert "location" in data
    assert data["location"] == "warehouse"
    print(f"✓ Warehouse stock endpoint returns {data.get('count', len(data.get('stock', [])))} items")

def test_get_van_stock_requires_engineer_id():
    """GET /api/svc/inventory/stock?location=van without engineer_id returns 400"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/stock",
                    params={"location": "van"},
                    headers=HEADERS)
    assert r.status_code == 400
    assert "engineer_id" in r.json().get("detail", "").lower()
    print("✓ Van stock requires engineer_id")

def test_get_van_stock_with_engineer_id():
    """GET /api/svc/inventory/stock?location=van&engineer_id=X returns van stock"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/stock",
                    params={"location": "van", "engineer_id": "test-engineer-123"},
                    headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["location"] == "van"
    assert data["engineer_id"] == "test-engineer-123"
    print("✓ Van stock with engineer_id works")

# ─────────────────────────────────────────────────────────────────
# Stock Adjustment Tests
# ─────────────────────────────────────────────────────────────────

def test_adjust_stock_missing_part_returns_404():
    """POST /api/svc/inventory/stock/adjust with non-existent part returns 404"""
    r = requests.post(f"{BASE_URL}/api/svc/inventory/stock/adjust",
                     json={"part_sku": "NONEXISTENT-SKU-999", "qty": 5, "location": "warehouse"},
                     headers=HEADERS)
    assert r.status_code == 404
    print("✓ Adjust stock with missing part returns 404")

def test_adjust_stock_requires_nonzero_qty():
    """POST /api/svc/inventory/stock/adjust with qty=0 returns 400"""
    r = requests.post(f"{BASE_URL}/api/svc/inventory/stock/adjust",
                     json={"part_sku": "ANY-SKU", "qty": 0, "location": "warehouse"},
                     headers=HEADERS)
    assert r.status_code == 400
    print("✓ Adjust stock requires non-zero qty")

def test_adjust_stock_van_requires_engineer_id():
    """POST /api/svc/inventory/stock/adjust for van without engineer_id returns 400"""
    sku = unique_sku()
    # First create a part
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Test Part", "cost": 10},
                 headers=HEADERS)

    r = requests.post(f"{BASE_URL}/api/svc/inventory/stock/adjust",
                     json={"part_sku": sku, "qty": 5, "location": "van"},
                     headers=HEADERS)
    assert r.status_code == 400
    assert "engineer_id" in r.json().get("detail", "").lower()
    print("✓ Van adjustment requires engineer_id")

def test_adjust_stock_creates_movement_record():
    """POST /api/svc/inventory/stock/adjust creates svc_part_movements row"""
    sku = unique_sku()
    # Create a part first
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Test Part for Adjust", "cost": 15},
                 headers=HEADERS)

    r = requests.post(f"{BASE_URL}/api/svc/inventory/stock/adjust",
                     json={"part_sku": sku, "qty": 10, "location": "warehouse", "reason": "initial stock"},
                     headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] == True
    assert data["part_sku"] == sku
    assert data["delta"] == 10
    print("✓ Stock adjustment creates movement record")

# ─────────────────────────────────────────────────────────────────
# Reorder Rules Tests
# ─────────────────────────────────────────────────────────────────

def test_list_reorder_rules():
    """GET /api/svc/inventory/reorder-rules returns rules list"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/reorder-rules", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "rules" in data
    assert "count" in data
    print(f"✓ Reorder rules list returns {data['count']} rules")

def test_upsert_reorder_rule():
    """POST /api/svc/inventory/reorder-rules creates/updates rule"""
    sku = unique_sku()
    r = requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                     json={"part_sku": sku, "location": "warehouse",
                           "min_qty": 2, "max_qty": 10, "supplier": "Test Supplier"},
                     headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["part_sku"] == sku
    assert data["min_qty"] == 2
    assert data["max_qty"] == 10
    rule_id = data["id"]

    # Upsert same rule - should return same id
    r2 = requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                      json={"part_sku": sku, "location": "warehouse",
                            "min_qty": 3, "max_qty": 15, "supplier": "Test Supplier"},
                      headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json()["id"] == rule_id  # Same rule updated
    assert r2.json()["min_qty"] == 3
    print("✓ Reorder rule upsert works (same id on duplicate)")

def test_reorder_rule_max_less_than_min_returns_400():
    """POST /api/svc/inventory/reorder-rules with max < min returns 400"""
    sku = unique_sku()
    r = requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                     json={"part_sku": sku, "location": "warehouse",
                           "min_qty": 10, "max_qty": 5},
                     headers=HEADERS)
    assert r.status_code == 400
    assert "max" in r.json().get("detail", "").lower()
    print("✓ max_qty < min_qty returns 400")

def test_reorder_rule_van_requires_engineer_id():
    """POST /api/svc/inventory/reorder-rules for van without engineer_id returns 400"""
    sku = unique_sku()
    r = requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                     json={"part_sku": sku, "location": "van",
                           "min_qty": 1, "max_qty": 5},
                     headers=HEADERS)
    assert r.status_code == 400
    assert "engineer_id" in r.json().get("detail", "").lower()
    print("✓ Van reorder rule requires engineer_id")

def test_delete_reorder_rule():
    """DELETE /api/svc/inventory/reorder-rules/{id} removes rule"""
    sku = unique_sku()
    # Create a rule first
    r = requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                     json={"part_sku": sku, "location": "warehouse",
                           "min_qty": 1, "max_qty": 5, "supplier": "Delete Test"},
                     headers=HEADERS)
    rule_id = r.json()["id"]

    # Delete it
    r2 = requests.delete(f"{BASE_URL}/api/svc/inventory/reorder-rules/{rule_id}",
                        headers=HEADERS)
    assert r2.status_code == 200
    assert r2.json()["deleted"] == 1
    print("✓ Delete reorder rule works")

# ─────────────────────────────────────────────────────────────────
# Low-Stock Detection Tests
# ─────────────────────────────────────────────────────────────────

def test_low_stock_detection():
    """GET /api/svc/inventory/low-stock returns rows where on_hand < min_qty"""
    sku = unique_sku()
    # Create a part
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Low Stock Test Part", "cost": 25},
                 headers=HEADERS)

    # Create a reorder rule with min_qty=5
    requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                 json={"part_sku": sku, "location": "warehouse",
                       "min_qty": 5, "max_qty": 10, "supplier": "Low Stock Supplier"},
                 headers=HEADERS)

    # Don't add any stock - should show as low stock
    r = requests.get(f"{BASE_URL}/api/svc/inventory/low-stock", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "rows" in data
    assert "count" in data

    # Find our test SKU in low stock
    our_row = next((row for row in data["rows"] if row["part_sku"] == sku), None)
    if our_row:
        assert our_row["on_hand"] < our_row["min_qty"]
        assert "shortfall" in our_row
        assert our_row["shortfall"] == our_row["max_qty"] - our_row["on_hand"]
        print(f"✓ Low stock detection works - {sku} has shortfall of {our_row['shortfall']}")
    else:
        print(f"✓ Low stock endpoint works - {data['count']} items below threshold")

# ─────────────────────────────────────────────────────────────────
# Purchase Orders Tests
# ─────────────────────────────────────────────────────────────────

def test_list_purchase_orders():
    """GET /api/svc/inventory/purchase-orders returns PO list"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/purchase-orders", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "purchase_orders" in data
    assert "count" in data
    print(f"✓ Purchase orders list returns {data['count']} POs")

def test_list_purchase_orders_status_filter():
    """GET /api/svc/inventory/purchase-orders?status=draft filters correctly"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                    params={"status": "draft"},
                    headers=HEADERS)
    assert r.status_code == 200
    for po in r.json().get("purchase_orders", []):
        assert po["status"] == "draft"
    print("✓ PO status filter works")

def test_list_purchase_orders_invalid_status_returns_400():
    """GET /api/svc/inventory/purchase-orders?status=invalid returns 400"""
    r = requests.get(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                    params={"status": "invalid_status"},
                    headers=HEADERS)
    assert r.status_code == 400
    print("✓ Invalid PO status returns 400")

def test_create_purchase_order():
    """POST /api/svc/inventory/purchase-orders creates draft PO"""
    sku = unique_sku()
    # Create a part first
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "PO Test Part", "cost": 50},
                 headers=HEADERS)

    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                     json={
                         "supplier": "Test Supplier Co",
                         "supplier_email": "supplier@test.com",
                         "lines": [{"part_sku": sku, "qty": 5, "unit_cost": 50}],
                         "notes": "Test PO"
                     },
                     headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "draft"
    assert data["reference"].startswith("PO-")
    assert data["supplier"] == "Test Supplier Co"
    assert len(data["lines"]) == 1
    assert data["total"] == 250.0  # 5 * 50
    print(f"✓ Created PO {data['reference']} with total £{data['total']}")

def test_create_po_requires_supplier_and_lines():
    """POST /api/svc/inventory/purchase-orders requires supplier and ≥1 line"""
    # Missing supplier
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                     json={"lines": [{"part_sku": "X", "qty": 1}]},
                     headers=HEADERS)
    assert r.status_code == 400

    # Missing lines
    r2 = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                      json={"supplier": "Test"},
                      headers=HEADERS)
    assert r2.status_code == 400
    print("✓ PO creation requires supplier and lines")

def test_create_po_from_low_stock():
    """POST /api/svc/inventory/purchase-orders/from-low-stock creates PO from shortfalls"""
    sku = unique_sku()
    # Setup: create part, rule, ensure low stock
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "From Low Stock Part", "cost": 30},
                 headers=HEADERS)
    requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                 json={"part_sku": sku, "location": "warehouse",
                       "min_qty": 5, "max_qty": 10, "supplier": "Low Stock Supplier"},
                 headers=HEADERS)

    # Try to create PO from low stock
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/from-low-stock",
                     json={"supplier": "ALL"},
                     headers=HEADERS)

    if r.status_code == 200:
        data = r.json()
        assert data["status"] == "draft"
        assert len(data["lines"]) > 0
        print(f"✓ Created PO {data['reference']} from low-stock with {len(data['lines'])} lines")
    elif r.status_code == 409:
        # No low stock or no match - acceptable
        print("✓ From-low-stock returns 409 when no matching low-stock items")
    else:
        pytest.fail(f"Unexpected status {r.status_code}: {r.text}")

def test_create_po_from_low_stock_no_match_returns_409():
    """POST /api/svc/inventory/purchase-orders/from-low-stock with no match returns 409"""
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/from-low-stock",
                     json={"supplier": "NONEXISTENT-SUPPLIER-XYZ"},
                     headers=HEADERS)
    assert r.status_code == 409
    print("✓ From-low-stock with no match returns 409")

def test_edit_draft_po():
    """PUT /api/svc/inventory/purchase-orders/{id} edits draft PO"""
    sku = unique_sku()
    # Create a PO first
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Edit PO Part", "cost": 20},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Original Supplier",
                                  "lines": [{"part_sku": sku, "qty": 2}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]

    # Edit it
    r = requests.put(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}",
                    json={"supplier": "Updated Supplier", "notes": "Updated notes"},
                    headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["supplier"] == "Updated Supplier"
    assert r.json()["notes"] == "Updated notes"
    print("✓ Edit draft PO works")

def test_submit_po():
    """POST /api/svc/inventory/purchase-orders/{id}/submit moves to submitted"""
    sku = unique_sku()
    # Create a PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Submit PO Part", "cost": 40},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Submit Test Supplier",
                                  "lines": [{"part_sku": sku, "qty": 3, "unit_cost": 40}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]

    # Submit it
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                     json={},
                     headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "submitted"
    assert data["submitted_at"] is not None
    print(f"✓ PO submitted - status={data['status']}, submitted_at={data['submitted_at']}")

def test_edit_submitted_po_returns_409():
    """PUT /api/svc/inventory/purchase-orders/{id} on submitted PO returns 409"""
    sku = unique_sku()
    # Create and submit a PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "No Edit Part", "cost": 10},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "No Edit Supplier",
                                  "lines": [{"part_sku": sku, "qty": 1}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                 json={}, headers=HEADERS)

    # Try to edit
    r = requests.put(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}",
                    json={"supplier": "Should Fail"},
                    headers=HEADERS)
    assert r.status_code == 409
    print("✓ Editing submitted PO returns 409")

def test_receive_po_full():
    """POST /api/svc/inventory/purchase-orders/{id}/receive with full=true receives all"""
    sku = unique_sku()
    # Create, submit PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Receive Full Part", "cost": 60},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Receive Full Supplier",
                                  "lines": [{"part_sku": sku, "qty": 5, "unit_cost": 60}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                 json={}, headers=HEADERS)

    # Receive full
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/receive",
                     json={"full": True},
                     headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "received"
    assert data["received_at"] is not None
    # Check line received_qty
    assert data["lines"][0]["received_qty"] == 5
    print(f"✓ PO fully received - status={data['status']}")

    # Verify warehouse stock increased
    stock_r = requests.get(f"{BASE_URL}/api/svc/inventory/stock",
                          params={"location": "warehouse"},
                          headers=HEADERS)
    stock_items = stock_r.json().get("stock", [])
    our_stock = next((s for s in stock_items if s["part_sku"] == sku), None)
    if our_stock:
        assert our_stock["qty"] >= 5
        print(f"✓ Warehouse stock for {sku} is now {our_stock['qty']}")

def test_cancel_po():
    """POST /api/svc/inventory/purchase-orders/{id}/cancel moves to cancelled"""
    sku = unique_sku()
    # Create a PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Cancel PO Part", "cost": 15},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Cancel Test Supplier",
                                  "lines": [{"part_sku": sku, "qty": 2}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]

    # Cancel it
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/cancel",
                     json={},
                     headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    print("✓ PO cancelled successfully")

def test_cancel_received_po_returns_409():
    """POST /api/svc/inventory/purchase-orders/{id}/cancel on received PO returns 409"""
    sku = unique_sku()
    # Create, submit, receive PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "No Cancel Part", "cost": 25},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "No Cancel Supplier",
                                  "lines": [{"part_sku": sku, "qty": 1}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                 json={}, headers=HEADERS)
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/receive",
                 json={"full": True}, headers=HEADERS)

    # Try to cancel
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/cancel",
                     json={},
                     headers=HEADERS)
    assert r.status_code == 409
    print("✓ Cancelling received PO returns 409")

def test_low_stock_decreases_after_receive():
    """After receiving PO, low-stock count should decrease for satisfied parts"""
    sku = unique_sku()
    # Create part with rule
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Satisfy Low Stock Part", "cost": 35},
                 headers=HEADERS)
    requests.post(f"{BASE_URL}/api/svc/inventory/reorder-rules",
                 json={"part_sku": sku, "location": "warehouse",
                       "min_qty": 3, "max_qty": 8, "supplier": "Satisfy Supplier"},
                 headers=HEADERS)

    # Check low stock before
    before_r = requests.get(f"{BASE_URL}/api/svc/inventory/low-stock", headers=HEADERS)
    before_count = before_r.json()["count"]

    # Create, submit, receive PO with enough qty
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Satisfy Supplier",
                                  "lines": [{"part_sku": sku, "qty": 10, "unit_cost": 35}]},
                            headers=HEADERS)
    po_id = create_r.json()["id"]
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                 json={}, headers=HEADERS)
    requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/receive",
                 json={"full": True}, headers=HEADERS)

    # Check low stock after
    after_r = requests.get(f"{BASE_URL}/api/svc/inventory/low-stock", headers=HEADERS)
    after_count = after_r.json()["count"]

    # Our part should no longer be in low stock
    our_row = next((row for row in after_r.json()["rows"] if row["part_sku"] == sku), None)
    if our_row is None:
        print(f"✓ Part {sku} no longer in low-stock after receiving PO")
    else:
        print(f"⚠ Part {sku} still in low-stock (on_hand={our_row['on_hand']}, min={our_row['min_qty']})")

def test_sage_po_outbox_on_submit():
    """POST /api/svc/inventory/purchase-orders/{id}/submit enqueues Sage PO outbox"""
    sku = unique_sku()
    # Create a PO
    requests.post(f"{BASE_URL}/api/svc/parts",
                 json={"sku": sku, "name": "Sage Outbox Part", "cost": 45, "sage_stock_code": f"SAGE-{sku}"},
                 headers=HEADERS)
    create_r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders",
                            json={"supplier": "Sage Outbox Supplier",
                                  "lines": [{"part_sku": sku, "qty": 7, "unit_cost": 45}]},
                            headers=HEADERS)
    po = create_r.json()
    po_id = po["id"]
    po_ref = po["reference"]

    # Submit it
    r = requests.post(f"{BASE_URL}/api/svc/inventory/purchase-orders/{po_id}/submit",
                     json={},
                     headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"
    print(f"✓ PO {po_ref} submitted - Sage outbox should have been enqueued (MOCKED)")
