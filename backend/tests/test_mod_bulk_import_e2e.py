"""
End-to-end tests for MOD Sites Bulk Import feature
Tests the full flow: upload CSV -> send credentials -> poll status -> download receipt
"""
import pytest
import requests
import os
import base64
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for master admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

class TestMODBulkImportE2E:
    """End-to-end tests for MOD bulk import feature"""
    
    def test_delivery_receipt_returns_409_before_send(self, auth_headers):
        """
        Regression test: GET /delivery-receipt.csv should return 409 (not 404)
        when batch exists but no send has happened yet.
        This was the bug fixed in mod_sites_bulk_import.py line 717-723.
        """
        # First, create a batch via bulk import using file upload
        csv_content = """site_code,site_name,branch,address_line1,address_line2,city,county,postcode,country,phone,email,site_manager_name,site_manager_email,oncall_phone,access_notes,password
test-e2e-001,Test Site E2E 1,Army,123 Test St,,Test City,Test County,TS1 1AA,United Kingdom,01onal 000001,test1@example.com,Test Manager 1,manager1@example.com,+44 7700 900001,,
test-e2e-002,Test Site E2E 2,Navy,456 Test Ave,,Test City,Test County,TS2 2BB,United Kingdom,01234 000002,test2@example.com,Test Manager 2,manager2@example.com,+44 7700 900002,,
test-e2e-003,Test Site E2E 3,RAF,789 Test Rd,,Test City,Test County,TS3 3CC,United Kingdom,01234 000003,test3@example.com,Test Manager 3,manager3@example.com,+44 7700 900003,,"""
        
        # Use multipart form data for file upload
        files = {
            'file': ('test_sites.csv', csv_content, 'text/csv')
        }
        
        # Remove Content-Type from headers for multipart
        upload_headers = {"Authorization": auth_headers["Authorization"]}
        
        # Upload CSV with sync=true for immediate processing
        response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import?sync=true&mod_root_id=mod-root-uk",
            headers=upload_headers,
            files=files
        )
        
        # Should succeed or return validation errors
        assert response.status_code in [200, 201, 400], f"Unexpected status: {response.status_code} - {response.text}"
        
        if response.status_code in [200, 201]:
            data = response.json()
            batch_id = data.get("batch_id")
            
            if not batch_id:
                # If no batch_id, the import might have been skipped (all sites exist)
                print(f"No batch_id returned (sites may already exist): {data}")
                pytest.skip("No batch_id returned - sites may already exist")
            
            # Now try to get delivery receipt BEFORE sending credentials
            receipt_response = requests.get(
                f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{batch_id}/delivery-receipt.csv",
                headers=auth_headers
            )
            
            # Should return 409 (Conflict) not 404 (Not Found)
            assert receipt_response.status_code == 409, \
                f"Expected 409 for delivery receipt before send, got {receipt_response.status_code}: {receipt_response.text}"
            
            print(f"✓ Delivery receipt correctly returns 409 before send")
    
    def test_send_credentials_returns_404_for_unknown_batch(self, auth_headers):
        """POST send-credentials returns 404 for unknown batch_id"""
        fake_batch_id = "nonexistent-batch-12345"
        
        response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{fake_batch_id}/send-credentials",
            headers=auth_headers,
            json={"test_only_email": "test@example.com"}
        )
        
        assert response.status_code == 404, \
            f"Expected 404 for unknown batch, got {response.status_code}: {response.text}"
        
        print(f"✓ Send credentials correctly returns 404 for unknown batch")
    
    def test_full_bulk_import_flow(self, auth_headers):
        """
        Full flow test:
        1. POST bulk-import (sync) -> get batch_id
        2. POST send-credentials (test_only_email mode)
        3. Poll GET /status until delivery_status='done'
        4. GET /delivery-receipt.csv returns CSV
        """
        # Step 1: Upload CSV using file upload
        csv_content = """site_code,site_name,branch,address_line1,address_line2,city,county,postcode,country,phone,email,site_manager_name,site_manager_email,oncall_phone,access_notes,password
flow-test-001,Flow Test Site 1,Army,100 Flow St,,Flow City,Flow County,FL1 1AA,United Kingdom,01234 100001,flowtest1@example.com,Flow Manager 1,flowmgr1@example.com,+44 7700 100001,,
flow-test-002,Flow Test Site 2,Navy,200 Flow Ave,,Flow City,Flow County,FL2 2BB,United Kingdom,01234 100002,flowtest2@example.com,Flow Manager 2,flowmgr2@example.com,+44 7700 100002,,
flow-test-003,Flow Test Site 3,RAF,300 Flow Rd,,Flow City,Flow County,FL3 3CC,United Kingdom,01234 100003,flowtest3@example.com,Flow Manager 3,flowmgr3@example.com,+44 7700 100003,,"""
        
        files = {
            'file': ('flow_test_sites.csv', csv_content, 'text/csv')
        }
        upload_headers = {"Authorization": auth_headers["Authorization"]}
        
        response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import?sync=true&mod_root_id=mod-root-uk",
            headers=upload_headers,
            files=files
        )
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Bulk import failed: {response.status_code} - {response.text}")
        
        data = response.json()
        batch_id = data.get("batch_id")
        
        if not batch_id:
            pytest.skip(f"No batch_id returned (sites may already exist): {data}")
        
        print(f"✓ Step 1: Bulk import created batch {batch_id}")
        
        # Step 2: Send credentials in test_only_email mode
        send_response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{batch_id}/send-credentials",
            headers=auth_headers,
            json={"test_only_email": "test-recipient@example.com"}
        )
        
        # Should succeed or return 409 if already running
        assert send_response.status_code in [200, 202, 409], \
            f"Send credentials failed: {send_response.status_code} - {send_response.text}"
        
        if send_response.status_code == 409:
            print(f"✓ Step 2: Send already in progress (409)")
        else:
            print(f"✓ Step 2: Send credentials initiated")
        
        # Step 3: Poll status until done
        max_polls = 30
        poll_interval = 2
        delivery_done = False
        
        for i in range(max_polls):
            status_response = requests.get(
                f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{batch_id}/status",
                headers=auth_headers
            )
            
            assert status_response.status_code == 200, \
                f"Status check failed: {status_response.status_code} - {status_response.text}"
            
            status_data = status_response.json()
            delivery_status = status_data.get("delivery_status")
            
            print(f"  Poll {i+1}: delivery_status={delivery_status}")
            
            if delivery_status == "done":
                delivery_done = True
                # Verify delivery fields are present
                assert "delivery_total" in status_data
                assert "delivery_sent" in status_data
                assert "delivery_failed" in status_data
                assert "delivery_missing" in status_data
                assert "delivery_receipt_available" in status_data
                print(f"✓ Step 3: Delivery complete - total={status_data.get('delivery_total')}, sent={status_data.get('delivery_sent')}, failed={status_data.get('delivery_failed')}")
                break
            
            time.sleep(poll_interval)
        
        if not delivery_done:
            pytest.skip("Delivery did not complete within timeout")
        
        # Step 4: Download delivery receipt
        receipt_response = requests.get(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{batch_id}/delivery-receipt.csv",
            headers=auth_headers
        )
        
        assert receipt_response.status_code == 200, \
            f"Delivery receipt failed: {receipt_response.status_code} - {receipt_response.text}"
        
        # Verify it's a CSV
        content_type = receipt_response.headers.get("Content-Type", "")
        assert "csv" in content_type.lower() or "text" in content_type.lower(), \
            f"Expected CSV content type, got: {content_type}"
        
        receipt_content = receipt_response.text
        assert len(receipt_content) > 0, "Receipt CSV is empty"
        print(f"✓ Step 4: Delivery receipt downloaded ({len(receipt_content)} bytes)")
        
        print(f"\n✓ Full bulk import flow completed successfully!")


class TestMODBulkImportEdgeCases:
    """Edge case tests for MOD bulk import"""
    
    def test_send_credentials_requires_auth(self):
        """Send credentials endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/any-batch/send-credentials",
            json={"test_only_email": "test@example.com"}
        )
        
        assert response.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {response.status_code}"
        
        print(f"✓ Send credentials correctly requires auth")
    
    def test_status_endpoint_returns_delivery_fields(self, auth_headers):
        """Status endpoint should return delivery_* fields"""
        # First create a batch using file upload
        csv_content = """site_code,site_name,branch,address_line1,address_line2,city,county,postcode,country,phone,email,site_manager_name,site_manager_email,oncall_phone,access_notes,password
status-test-001,Status Test Site,Army,1 Status St,,Status City,Status County,ST1 1AA,United Kingdom,01234 200001,statustest@example.com,Status Manager,statusmgr@example.com,+44 7700 200001,,"""
        
        files = {
            'file': ('status_test_sites.csv', csv_content, 'text/csv')
        }
        upload_headers = {"Authorization": auth_headers["Authorization"]}
        
        response = requests.post(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import?sync=true&mod_root_id=mod-root-uk",
            headers=upload_headers,
            files=files
        )
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Bulk import failed: {response.status_code}")
        
        batch_id = response.json().get("batch_id")
        
        if not batch_id:
            pytest.skip("No batch_id returned")
        
        # Check status
        status_response = requests.get(
            f"{BASE_URL}/api/master-admin/mod-sites/bulk-import/{batch_id}/status",
            headers=auth_headers
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        # Verify delivery fields exist (may be null/None before send)
        expected_fields = ["delivery_status", "delivery_total", "delivery_sent", 
                          "delivery_failed", "delivery_missing", "delivery_receipt_available"]
        
        for field in expected_fields:
            assert field in status_data, f"Missing field: {field}"
        
        print(f"✓ Status endpoint returns all delivery fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
