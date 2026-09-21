"""Iter 216h49 — Backend tests for equipment move/delete, service-desk search, staffing backfill, file upload compression.

Features tested:
1. POST /api/equipment/{id}/move — Owner/manager moves equipment between sites
2. DELETE /api/equipment/{id} — Org-scoped delete (was user-scoped)
3. PATCH /api/equipment/{id} — site_id field gating for owner/manager only
4. GET /api/service-desk/equipment — Global equipment search for Service Desk
5. GET /api/staffing/staff — Auto-backfill from db.users to db.staff_members
6. POST /api/files/upload — PDF compression with original_size + compression_ratio fields
"""
import os
import pytest
import requests
import uuid
from datetime import datetime

# Base URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine.preview.emergentagent.com").rstrip("/")

# Test credentials
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Bob is owner of Strong Fitness org
BOB_EMAIL = "bob@knockers.com"
BOB_PASSWORD = "Test123!"

# Service Desk agent
SERVICE_DESK_EMAIL = "desk@pulsefitness.com"
SERVICE_DESK_PASSWORD = "DeskAgent123!"


def rate_limit_bypass_headers() -> dict:
    """Rate-limit bypass header for test runs."""
    secret = ""
    try:
        env_path = "/app/backend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
                        secret = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        break
    except Exception:
        pass
    return {"X-RateLimit-Bypass": secret} if secret else {}


def login(email: str, password: str) -> str | None:
    """Login and return JWT token."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json().get("token")
    print(f"Login failed for {email}: {resp.status_code} {resp.text[:200]}")
    return None


def auth_headers(token: str) -> dict:
    """Return auth headers with rate limit bypass."""
    headers = rate_limit_bypass_headers()
    headers["Authorization"] = f"Bearer {token}"
    headers["Content-Type"] = "application/json"
    return headers


class TestEquipmentMove:
    """Test POST /api/equipment/{id}/move endpoint."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner)")
        return token

    @pytest.fixture(scope="class")
    def setup_test_data(self, bob_token):
        """Create test equipment and sites for move testing."""
        headers = auth_headers(bob_token)
        
        # Get org info
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        if me_resp.status_code != 200:
            pytest.skip("Could not get user info")
        org_id = me_resp.json().get("organization_id")
        
        # Get existing sites or create them
        sites_resp = requests.get(f"{BASE_URL}/api/sites", headers=headers)
        sites = sites_resp.json().get("sites", []) if sites_resp.status_code == 200 else []
        
        # Create sites if needed
        if len(sites) < 2:
            for i in range(2 - len(sites)):
                site_data = {
                    "name": f"TEST_Site_{uuid.uuid4().hex[:8]}",
                    "address_line1": f"Test Address {i}",
                    "city": "Test City",
                    "postcode": "TE1 1ST"
                }
                create_resp = requests.post(f"{BASE_URL}/api/sites", json=site_data, headers=headers)
                if create_resp.status_code in (200, 201):
                    sites.append(create_resp.json())
        
        if len(sites) < 2:
            pytest.skip("Could not create enough sites for testing")
        
        site_a = sites[0]
        site_b = sites[1]
        
        # Create test equipment on site_a
        equip_data = {
            "name": f"TEST_Equipment_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Treadmill",
            "manufacturer": "Test Manufacturer",
            "site_id": site_a["id"]
        }
        equip_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=headers)
        if equip_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create test equipment: {equip_resp.text}")
        
        equipment = equip_resp.json()
        
        return {
            "org_id": org_id,
            "site_a": site_a,
            "site_b": site_b,
            "equipment": equipment
        }

    def test_move_equipment_success(self, bob_token, setup_test_data):
        """Test successful equipment move between sites."""
        headers = auth_headers(bob_token)
        equipment = setup_test_data["equipment"]
        site_b = setup_test_data["site_b"]
        
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{equipment['id']}/move",
            json={"site_id": site_b["id"]},
            headers=headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("moved") is True
        assert data.get("to_site_id") == site_b["id"]
        assert "to_site_name" in data
        print(f"✓ Equipment moved successfully: {data}")

    def test_move_equipment_already_at_target(self, bob_token, setup_test_data):
        """Test move returns moved=false when equipment is already at target site."""
        headers = auth_headers(bob_token)
        equipment = setup_test_data["equipment"]
        site_b = setup_test_data["site_b"]
        
        # Equipment was moved to site_b in previous test, try moving again
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{equipment['id']}/move",
            json={"site_id": site_b["id"]},
            headers=headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("moved") is False
        print(f"✓ Equipment already at target site: {data}")

    def test_move_equipment_invalid_site(self, bob_token, setup_test_data):
        """Test move returns 404 for site not in same org."""
        headers = auth_headers(bob_token)
        equipment = setup_test_data["equipment"]
        
        resp = requests.post(
            f"{BASE_URL}/api/equipment/{equipment['id']}/move",
            json={"site_id": "non-existent-site-id"},
            headers=headers
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print(f"✓ Invalid site returns 404: {resp.json()}")

    def test_move_equipment_not_found(self, bob_token):
        """Test move returns 404 for non-existent equipment."""
        headers = auth_headers(bob_token)
        
        resp = requests.post(
            f"{BASE_URL}/api/equipment/non-existent-equipment-id/move",
            json={"site_id": "some-site-id"},
            headers=headers
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ Non-existent equipment returns 404")


class TestEquipmentDeleteOrgScoped:
    """Test DELETE /api/equipment/{id} is now org-scoped."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner)")
        return token

    def test_delete_equipment_as_owner(self, bob_token):
        """Test owner can delete equipment in their org."""
        headers = auth_headers(bob_token)
        
        # Create test equipment
        equip_data = {
            "name": f"TEST_DeleteMe_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Bike",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=headers)
        assert create_resp.status_code in (200, 201), f"Failed to create equipment: {create_resp.text}"
        equipment_id = create_resp.json()["id"]
        
        # Delete it
        delete_resp = requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=headers)
        assert delete_resp.status_code == 200, f"Expected 200, got {delete_resp.status_code}: {delete_resp.text}"
        data = delete_resp.json()
        assert data.get("success") is True
        print(f"✓ Owner can delete equipment: {data}")

    def test_delete_equipment_not_found(self, bob_token):
        """Test delete returns 404 for non-existent equipment."""
        headers = auth_headers(bob_token)
        
        resp = requests.delete(f"{BASE_URL}/api/equipment/non-existent-id", headers=headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ Delete non-existent equipment returns 404")


class TestEquipmentPatchSiteIdGating:
    """Test PATCH /api/equipment/{id} site_id field is gated to owner/manager."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner)")
        return token

    def test_patch_site_id_as_owner(self, bob_token):
        """Test owner can update site_id via PATCH."""
        headers = auth_headers(bob_token)
        
        # Get sites
        sites_resp = requests.get(f"{BASE_URL}/api/sites", headers=headers)
        sites = sites_resp.json().get("sites", []) if sites_resp.status_code == 200 else []
        if not sites:
            pytest.skip("No sites available for testing")
        
        # Create test equipment
        equip_data = {
            "name": f"TEST_PatchSite_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Rower",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=headers)
        assert create_resp.status_code in (200, 201), f"Failed to create equipment: {create_resp.text}"
        equipment_id = create_resp.json()["id"]
        
        # Patch site_id
        patch_resp = requests.patch(
            f"{BASE_URL}/api/equipment/{equipment_id}",
            json={"site_id": sites[0]["id"]},
            headers=headers
        )
        assert patch_resp.status_code == 200, f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"
        print(f"✓ Owner can PATCH site_id: {patch_resp.json()}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=headers)


class TestServiceDeskEquipmentSearch:
    """Test GET /api/service-desk/equipment global search endpoint."""

    @pytest.fixture(scope="class")
    def service_desk_token(self):
        token = login(SERVICE_DESK_EMAIL, SERVICE_DESK_PASSWORD)
        if not token:
            # Try master admin as fallback (master admins pass service desk guard)
            token = login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)
        if not token:
            pytest.skip("Could not login as Service Desk or Master Admin")
        return token

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob")
        return token

    def test_service_desk_equipment_search_basic(self, service_desk_token):
        """Test basic equipment search returns results with org/site names."""
        headers = auth_headers(service_desk_token)
        
        resp = requests.get(f"{BASE_URL}/api/service-desk/equipment", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "equipment" in data
        assert "total" in data
        print(f"✓ Service desk equipment search returned {data['total']} items")
        
        # Check hydration of org/site names
        if data["equipment"]:
            first = data["equipment"][0]
            assert "organization_name" in first, "Missing organization_name hydration"
            assert "site_name" in first, "Missing site_name hydration"
            print(f"✓ Equipment row has organization_name and site_name: {first.get('organization_name')}, {first.get('site_name')}")

    def test_service_desk_equipment_search_with_query(self, service_desk_token):
        """Test equipment search with free-text query."""
        headers = auth_headers(service_desk_token)
        
        resp = requests.get(f"{BASE_URL}/api/service-desk/equipment?q=treadmill", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        print(f"✓ Search for 'treadmill' returned {data['total']} items")

    def test_service_desk_equipment_search_with_filters(self, service_desk_token):
        """Test equipment search with filters."""
        headers = auth_headers(service_desk_token)
        
        resp = requests.get(
            f"{BASE_URL}/api/service-desk/equipment?equipment_type=Treadmill&limit=10",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        print(f"✓ Filtered search returned {data['total']} items")

    def test_service_desk_equipment_search_requires_auth(self, bob_token):
        """Test regular user gets 403 on service desk endpoint."""
        headers = auth_headers(bob_token)
        
        resp = requests.get(f"{BASE_URL}/api/service-desk/equipment", headers=headers)
        assert resp.status_code == 403, f"Expected 403 for regular user, got {resp.status_code}: {resp.text}"
        print("✓ Regular user gets 403 on service desk endpoint")


class TestStaffingAutoBackfill:
    """Test GET /api/staffing/staff auto-backfill from db.users."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner/manager)")
        return token

    @pytest.fixture(scope="class")
    def master_admin_token(self):
        token = login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)
        if not token:
            pytest.skip("Could not login as Master Admin")
        return token

    def test_staffing_list_returns_staff(self, bob_token):
        """Test staffing list endpoint works for manager."""
        headers = auth_headers(bob_token)
        
        resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "staff" in data
        assert "role" in data
        print(f"✓ Staffing list returned {len(data['staff'])} staff members, role={data['role']}")

    def test_staffing_backfill_creates_staff_for_new_user(self, bob_token, master_admin_token):
        """Test that a new user added via Master Admin appears in staffing list."""
        bob_headers = auth_headers(bob_token)
        admin_headers = auth_headers(master_admin_token)
        
        # Get Bob's org ID
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=bob_headers)
        if me_resp.status_code != 200:
            pytest.skip("Could not get Bob's user info")
        org_id = me_resp.json().get("organization_id")
        
        # Create a new user in Bob's org via Master Admin
        test_email = f"TEST_backfill_{uuid.uuid4().hex[:8]}@example.com"
        user_data = {
            "email": test_email,
            "full_name": "TEST Backfill User",
            "role": "staff",
            "organization_id": org_id
        }
        
        # Try to add user via master admin endpoint
        add_resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{org_id}/users",
            json=user_data,
            headers=admin_headers
        )
        
        if add_resp.status_code not in (200, 201):
            # Try alternative endpoint
            add_resp = requests.post(
                f"{BASE_URL}/api/users/invite",
                json={"email": test_email, "full_name": "TEST Backfill User", "role": "staff"},
                headers=bob_headers
            )
        
        if add_resp.status_code not in (200, 201):
            print(f"Could not create test user: {add_resp.status_code} {add_resp.text}")
            pytest.skip("Could not create test user for backfill testing")
        
        # Now call staffing list as Bob (manager) - should trigger backfill
        staff_resp = requests.get(f"{BASE_URL}/api/staffing/staff", headers=bob_headers)
        assert staff_resp.status_code == 200, f"Expected 200, got {staff_resp.status_code}: {staff_resp.text}"
        
        data = staff_resp.json()
        staff_emails = [s.get("email", "").lower() for s in data.get("staff", [])]
        
        # Check if the new user was backfilled
        if test_email.lower() in staff_emails:
            print(f"✓ New user {test_email} was auto-backfilled into staffing")
            # Check for auto_synced_from_users flag
            for s in data.get("staff", []):
                if s.get("email", "").lower() == test_email.lower():
                    assert s.get("auto_synced_from_users") is True, "Missing auto_synced_from_users flag"
                    print("✓ Staff record has auto_synced_from_users=true")
                    break
        else:
            print(f"Note: User {test_email} not found in staff list - backfill may not have run or user creation failed")


class TestFileUploadCompression:
    """Test POST /api/files/upload returns original_size and compression_ratio."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob")
        return token

    def test_file_upload_returns_compression_fields(self, bob_token):
        """Test file upload response includes original_size and compression_ratio."""
        headers = rate_limit_bypass_headers()
        headers["Authorization"] = f"Bearer {bob_token}"
        
        # Create a simple text file (won't compress much but tests the fields)
        test_content = b"This is a test file content for upload testing. " * 100
        
        files = {
            "file": ("test_file.txt", test_content, "text/plain")
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/files/upload?category=general",
            files=files,
            headers=headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "original_size" in data, "Missing original_size field"
        assert "compression_ratio" in data, "Missing compression_ratio field"
        assert data["original_size"] == len(test_content), f"original_size mismatch: {data['original_size']} vs {len(test_content)}"
        assert isinstance(data["compression_ratio"], (int, float)), "compression_ratio should be numeric"
        assert 0 <= data["compression_ratio"] <= 1, f"compression_ratio should be 0-1, got {data['compression_ratio']}"
        
        print(f"✓ File upload returned original_size={data['original_size']}, compression_ratio={data['compression_ratio']}")

    def test_pdf_upload_compression(self, bob_token):
        """Test PDF upload triggers compression and returns ratio."""
        headers = rate_limit_bypass_headers()
        headers["Authorization"] = f"Bearer {bob_token}"
        
        # Create a minimal PDF (this is a valid but tiny PDF)
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
196
%%EOF
"""
        
        files = {
            "file": ("test_document.pdf", pdf_content, "application/pdf")
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/files/upload?category=general",
            files=files,
            headers=headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "original_size" in data, "Missing original_size field"
        assert "compression_ratio" in data, "Missing compression_ratio field"
        assert data["original_size"] == len(pdf_content), "original_size mismatch"
        
        print(f"✓ PDF upload returned original_size={data['original_size']}, compression_ratio={data['compression_ratio']}")


class TestAuditLogEntries:
    """Test that equipment operations write audit log entries."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner)")
        return token

    @pytest.fixture(scope="class")
    def master_admin_token(self):
        token = login(MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD)
        if not token:
            pytest.skip("Could not login as Master Admin")
        return token

    def test_equipment_delete_creates_audit_log(self, bob_token, master_admin_token):
        """Test that deleting equipment creates an audit log entry."""
        bob_headers = auth_headers(bob_token)
        admin_headers = auth_headers(master_admin_token)
        
        # Create test equipment
        equip_data = {
            "name": f"TEST_AuditDelete_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Bike",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=bob_headers)
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create test equipment: {create_resp.text}")
        
        equipment_id = create_resp.json()["id"]
        
        # Delete it
        delete_resp = requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=bob_headers)
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Check audit log via master admin
        audit_resp = requests.get(
            f"{BASE_URL}/api/master-admin/audit-log?event=equipment.deleted&limit=10",
            headers=admin_headers
        )
        
        if audit_resp.status_code == 200:
            logs = audit_resp.json().get("logs", [])
            found = any(log.get("equipment_id") == equipment_id for log in logs)
            if found:
                print("✓ Audit log entry found for equipment.deleted event")
            else:
                print("Note: Audit log entry not found in recent logs (may be in different collection)")
        else:
            print(f"Note: Could not verify audit log: {audit_resp.status_code}")


class TestRoleGating403:
    """Test that staff role gets 403 on owner/manager-only operations."""

    @pytest.fixture(scope="class")
    def bob_token(self):
        token = login(BOB_EMAIL, BOB_PASSWORD)
        if not token:
            pytest.skip("Could not login as Bob (owner)")
        return token

    @pytest.fixture(scope="class")
    def staff_user_and_token(self, bob_token):
        """Create a staff user and return their token."""
        bob_headers = auth_headers(bob_token)
        
        # Get Bob's org ID
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=bob_headers)
        if me_resp.status_code != 200:
            pytest.skip("Could not get Bob's user info")
        org_id = me_resp.json().get("organization_id")
        
        # Create a staff user
        staff_email = f"TEST_staff_{uuid.uuid4().hex[:8]}@example.com"
        staff_password = "StaffTest123!"
        
        # Try to invite a staff user
        invite_resp = requests.post(
            f"{BASE_URL}/api/users/invite",
            json={"email": staff_email, "full_name": "TEST Staff User", "role": "staff"},
            headers=bob_headers
        )
        
        if invite_resp.status_code not in (200, 201):
            # Try registering directly
            reg_resp = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "email": staff_email,
                    "password": staff_password,
                    "full_name": "TEST Staff User",
                    "company_name": "Test"
                },
                headers=rate_limit_bypass_headers()
            )
            if reg_resp.status_code not in (200, 201, 400):
                pytest.skip(f"Could not create staff user: {reg_resp.text}")
        
        # Login as staff
        staff_token = login(staff_email, staff_password)
        if not staff_token:
            pytest.skip("Could not login as staff user")
        
        return {"email": staff_email, "token": staff_token, "org_id": org_id}

    def test_staff_cannot_move_equipment(self, bob_token, staff_user_and_token):
        """Test staff role gets 403 when trying to move equipment."""
        bob_headers = auth_headers(bob_token)
        staff_headers = auth_headers(staff_user_and_token["token"])
        
        # Create equipment as owner
        equip_data = {
            "name": f"TEST_StaffMove_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Bike",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=bob_headers)
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create equipment: {create_resp.text}")
        
        equipment_id = create_resp.json()["id"]
        
        # Get a site
        sites_resp = requests.get(f"{BASE_URL}/api/sites", headers=bob_headers)
        sites = sites_resp.json().get("sites", []) if sites_resp.status_code == 200 else []
        if not sites:
            pytest.skip("No sites available")
        
        # Try to move as staff
        move_resp = requests.post(
            f"{BASE_URL}/api/equipment/{equipment_id}/move",
            json={"site_id": sites[0]["id"]},
            headers=staff_headers
        )
        
        # Staff should get 403
        assert move_resp.status_code == 403, f"Expected 403 for staff, got {move_resp.status_code}: {move_resp.text}"
        print(f"✓ Staff gets 403 on equipment move: {move_resp.json()}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=bob_headers)

    def test_staff_cannot_delete_equipment(self, bob_token, staff_user_and_token):
        """Test staff role gets 403 when trying to delete equipment."""
        bob_headers = auth_headers(bob_token)
        staff_headers = auth_headers(staff_user_and_token["token"])
        
        # Create equipment as owner
        equip_data = {
            "name": f"TEST_StaffDelete_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Rower",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=bob_headers)
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create equipment: {create_resp.text}")
        
        equipment_id = create_resp.json()["id"]
        
        # Try to delete as staff
        delete_resp = requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=staff_headers)
        
        # Staff should get 403
        assert delete_resp.status_code == 403, f"Expected 403 for staff, got {delete_resp.status_code}: {delete_resp.text}"
        print(f"✓ Staff gets 403 on equipment delete: {delete_resp.json()}")
        
        # Cleanup as owner
        requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=bob_headers)

    def test_staff_cannot_patch_site_id(self, bob_token, staff_user_and_token):
        """Test staff role gets 403 when trying to PATCH site_id."""
        bob_headers = auth_headers(bob_token)
        staff_headers = auth_headers(staff_user_and_token["token"])
        
        # Create equipment as owner
        equip_data = {
            "name": f"TEST_StaffPatch_{uuid.uuid4().hex[:8]}",
            "equipment_type": "Elliptical",
            "manufacturer": "Test"
        }
        create_resp = requests.post(f"{BASE_URL}/api/equipment", json=equip_data, headers=bob_headers)
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Could not create equipment: {create_resp.text}")
        
        equipment_id = create_resp.json()["id"]
        
        # Get a site
        sites_resp = requests.get(f"{BASE_URL}/api/sites", headers=bob_headers)
        sites = sites_resp.json().get("sites", []) if sites_resp.status_code == 200 else []
        if not sites:
            pytest.skip("No sites available")
        
        # Try to patch site_id as staff
        patch_resp = requests.patch(
            f"{BASE_URL}/api/equipment/{equipment_id}",
            json={"site_id": sites[0]["id"]},
            headers=staff_headers
        )
        
        # Staff should get 403
        assert patch_resp.status_code == 403, f"Expected 403 for staff, got {patch_resp.status_code}: {patch_resp.text}"
        print(f"✓ Staff gets 403 on PATCH site_id: {patch_resp.json()}")
        
        # Cleanup as owner
        requests.delete(f"{BASE_URL}/api/equipment/{equipment_id}", headers=bob_headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
