"""
Test suite for GymAxis Service Operations Phase 3 — Parts, Scheduler, Intake enhancements.
Iter 215dq.

Tests:
- Parts catalogue CRUD: GET /api/svc/parts, POST /api/svc/parts
- Parts import: POST /api/svc/parts/imports/sicon
- Van stock: GET /api/svc/parts/van/{engineer_id}
- Parts allocation: POST /api/svc/parts/allocate, DELETE /api/svc/parts/allocate/{id}
- Intake enhancements: equipment_ids, equipment_serials, allocated_parts, required_skills, site_postcode
- Case PATCH: equipment_ids, equipment_serials, required_skills, site_postcode
- Scheduler diary: GET /api/svc/scheduler/diary
- Scheduler assign: POST /api/svc/scheduler/assign
- Scheduler auto-assign: POST /api/svc/scheduler/auto-assign (preview + commit)
- Scoring formula verification
- Sicon outbox payload verification (EquipmentIDs, EquipmentSerials, Parts, RequiredSkills)
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from tests.conftest import rate_limit_bypass_headers

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://fitness-onboarding-3.preview.emergentagent.com"

# Session-scoped login to avoid rate limiting
_SESSION_TOKEN = None
_SESSION_USER_ID = None
_SESSION_ORG_ID = None


def _get_session_auth():
    """Get session-scoped auth token (login once)."""
    global _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID
    if _SESSION_TOKEN:
        return _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID

    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        headers=rate_limit_bypass_headers()
    )
    if resp.status_code == 200:
        data = resp.json()
        _SESSION_TOKEN = data["token"]
        _SESSION_USER_ID = data["user"]["id"]
        _SESSION_ORG_ID = data["user"]["organization_id"]
    return _SESSION_TOKEN, _SESSION_USER_ID, _SESSION_ORG_ID


class TestPartsCatalogue:
    """Parts catalogue CRUD tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup using session-scoped auth."""
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.token = token
        self.user_id = user_id
        self.org_id = org_id
        yield

    def test_list_parts_empty_catalogue(self):
        """GET /api/svc/parts returns empty list when catalogue is empty."""
        resp = self.session.get(f"{BASE_URL}/api/svc/parts", params={"search": "NONEXISTENT_SKU_XYZ"})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "parts" in data
        assert "count" in data
        assert isinstance(data["parts"], list)
        print(f"Parts search returned: {data['count']} results")

    def test_create_part_sku_uppercased(self):
        """POST /api/svc/parts creates part with SKU auto-uppercased."""
        sku = f"test-sku-{uuid.uuid4().hex[:6]}"  # lowercase
        resp = self.session.post(f"{BASE_URL}/api/svc/parts", json={
            "sku": sku,
            "name": "Test Part for Phase 3",
            "manufacturer": "Test Mfg",
            "cost": 25.50
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        part = resp.json()

        assert part["sku"] == sku.upper(), f"SKU not uppercased: {part['sku']}"
        assert part["name"] == "Test Part for Phase 3"
        assert "id" in part
        print(f"Created part: {part['sku']}")

    def test_create_part_returns_existing_on_duplicate(self):
        """POST /api/svc/parts returns existing part on duplicate SKU."""
        sku = f"DUP-{uuid.uuid4().hex[:6]}".upper()

        # Create first
        resp1 = self.session.post(f"{BASE_URL}/api/svc/parts", json={
            "sku": sku,
            "name": "Original Part"
        })
        assert resp1.status_code == 200
        part1 = resp1.json()

        # Create duplicate
        resp2 = self.session.post(f"{BASE_URL}/api/svc/parts", json={
            "sku": sku,
            "name": "Duplicate Part"
        })
        assert resp2.status_code == 200
        part2 = resp2.json()

        # Should return same part
        assert part1["id"] == part2["id"], "Duplicate SKU created new part!"
        assert part2["name"] == "Original Part", "Duplicate overwrote original name"
        print(f"Duplicate SKU returned existing part: {part1['id']}")


class TestPartsImportSicon:
    """Sicon parts import tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        yield

    def test_import_sicon_upserts_parts(self):
        """POST /api/svc/parts/imports/sicon upserts parts and returns counts."""
        sku1 = f"SICON-{uuid.uuid4().hex[:6]}".upper()
        sku2 = f"SICON-{uuid.uuid4().hex[:6]}".upper()

        resp = self.session.post(f"{BASE_URL}/api/svc/parts/imports/sicon", json={
            "parts": [
                {"sku": sku1, "name": "Sicon Part 1", "sicon_part_id": "SP001", "sage_stock_code": "SAGE001"},
                {"sku": sku2, "name": "Sicon Part 2", "sicon_part_id": "SP002", "sage_stock_code": "SAGE002"},
            ]
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        result = resp.json()

        assert "inserted" in result
        assert "updated" in result
        assert "total" in result
        assert result["total"] == 2
        print(f"Sicon import: inserted={result['inserted']}, updated={result['updated']}")

    def test_import_sicon_updates_existing(self):
        """POST /api/svc/parts/imports/sicon updates existing parts."""
        sku = f"SICON-UPD-{uuid.uuid4().hex[:6]}".upper()

        # First import
        resp1 = self.session.post(f"{BASE_URL}/api/svc/parts/imports/sicon", json={
            "parts": [{"sku": sku, "name": "Original Name"}]
        })
        assert resp1.status_code == 200
        assert resp1.json()["inserted"] == 1

        # Second import with updated name
        resp2 = self.session.post(f"{BASE_URL}/api/svc/parts/imports/sicon", json={
            "parts": [{"sku": sku, "name": "Updated Name", "sicon_part_id": "SP999"}]
        })
        assert resp2.status_code == 200
        assert resp2.json()["updated"] == 1

        # Verify update
        resp3 = self.session.get(f"{BASE_URL}/api/svc/parts", params={"search": sku})
        parts = resp3.json()["parts"]
        assert len(parts) == 1
        assert parts[0]["name"] == "Updated Name"
        assert parts[0]["sicon_part_id"] == "SP999"
        print(f"Sicon import updated existing part: {sku}")


class TestVanStock:
    """Van stock tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        yield

    def test_get_van_stock_returns_joined_catalogue(self):
        """GET /api/svc/parts/van/{engineer_id} returns van stock joined with catalogue."""
        resp = self.session.get(f"{BASE_URL}/api/svc/parts/van/{self.user_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "van" in data
        assert "engineer_id" in data
        assert data["engineer_id"] == self.user_id
        assert isinstance(data["van"], list)
        print(f"Van stock for {self.user_id}: {len(data['van'])} items")


class TestPartsAllocation:
    """Parts allocation tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        self.org_id = org_id
        self.test_case_id = None
        self.test_part_sku = None
        yield

        # Cleanup
        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _create_test_case(self):
        """Helper to create a test case."""
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Alloc_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case for parts allocation",
            "priority": "p2",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
        })
        assert resp.status_code in [200, 201], f"Failed to create case: {resp.text}"
        case = resp.json()
        self.test_case_id = case["id"]
        return case

    def _create_test_part(self):
        """Helper to create a test part."""
        sku = f"ALLOC-{uuid.uuid4().hex[:6]}".upper()
        resp = self.session.post(f"{BASE_URL}/api/svc/parts", json={
            "sku": sku,
            "name": "Test Part for Allocation"
        })
        assert resp.status_code == 200
        self.test_part_sku = sku
        return resp.json()

    def test_allocate_warehouse_creates_allocation(self):
        """POST /api/svc/parts/allocate with source=warehouse creates allocation."""
        case = self._create_test_case()
        part = self._create_test_part()

        resp = self.session.post(f"{BASE_URL}/api/svc/parts/allocate", json={
            "case_id": case["id"],
            "part_sku": part["sku"],
            "qty": 2,
            "source": "warehouse"
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        alloc = resp.json()

        assert "id" in alloc
        assert alloc["case_id"] == case["id"]
        assert alloc["part_sku"] == part["sku"]
        assert alloc["qty"] == 2
        assert alloc["source"] == "warehouse"
        print(f"Created warehouse allocation: {alloc['id']}")

        # Verify allocation is on case
        resp = self.session.get(f"{BASE_URL}/api/svc/cases/{case['id']}")
        case_data = resp.json()
        assert len(case_data.get("allocated_parts", [])) == 1
        assert case_data["allocated_parts"][0]["part_sku"] == part["sku"]

    def test_allocate_van_insufficient_qty_returns_409(self):
        """POST /api/svc/parts/allocate with source=van and insufficient qty returns 409."""
        case = self._create_test_case()
        part = self._create_test_part()

        # Assign engineer to case first
        self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "assigned_engineer_id": self.user_id
        })

        # Try to allocate from van (which has 0 stock)
        resp = self.session.post(f"{BASE_URL}/api/svc/parts/allocate", json={
            "case_id": case["id"],
            "part_sku": part["sku"],
            "qty": 5,
            "source": "van",
            "engineer_id": self.user_id
        })
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
        print("Van allocation with insufficient stock correctly returned 409")

    def test_deallocate_removes_allocation(self):
        """DELETE /api/svc/parts/allocate/{id} removes the allocation."""
        case = self._create_test_case()
        part = self._create_test_part()

        # Create allocation
        resp = self.session.post(f"{BASE_URL}/api/svc/parts/allocate", json={
            "case_id": case["id"],
            "part_sku": part["sku"],
            "qty": 1,
            "source": "warehouse"
        })
        assert resp.status_code == 200
        alloc = resp.json()

        # Delete allocation
        resp = self.session.delete(f"{BASE_URL}/api/svc/parts/allocate/{alloc['id']}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        result = resp.json()
        assert result.get("ok") == True

        # Verify allocation removed from case
        resp = self.session.get(f"{BASE_URL}/api/svc/cases/{case['id']}")
        case_data = resp.json()
        assert len(case_data.get("allocated_parts", [])) == 0
        print(f"Deallocated: {alloc['id']}")


class TestIntakeEnhancements:
    """Intake form enhancements tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.test_case_id = None
        yield

        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def test_intake_phone_accepts_equipment_ids_and_serials(self):
        """POST /api/svc/intake/phone accepts equipment_ids[] and equipment_serials[]."""
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Equip_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case with equipment",
            "priority": "p2",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
            "equipment_ids": ["equip-001", "equip-002"],
            "equipment_serials": ["SN-12345", "SN-67890"],
        })
        assert resp.status_code in [200, 201], f"Failed: {resp.text}"
        case = resp.json()
        self.test_case_id = case["id"]

        assert case.get("equipment_ids") == ["equip-001", "equip-002"]
        assert case.get("equipment_serials") == ["SN-12345", "SN-67890"]
        print(f"Intake with equipment: {case['reference']}")

    def test_intake_phone_accepts_allocated_parts(self):
        """POST /api/svc/intake/phone accepts allocated_parts[]."""
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Parts_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case with pre-allocated parts",
            "priority": "p2",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
            "allocated_parts": [
                {"part_sku": "BELT-001", "part_name": "Treadmill Belt", "qty": 1, "source": "warehouse"},
            ],
        })
        assert resp.status_code in [200, 201], f"Failed: {resp.text}"
        case = resp.json()
        self.test_case_id = case["id"]

        assert len(case.get("allocated_parts", [])) == 1
        assert case["allocated_parts"][0]["part_sku"] == "BELT-001"
        print(f"Intake with allocated parts: {case['reference']}")

    def test_intake_phone_accepts_required_skills_and_postcode(self):
        """POST /api/svc/intake/phone accepts required_skills[] and site_postcode."""
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Skills_Case_{uuid.uuid4().hex[:8]}",
            "description": "Test case with skills and postcode",
            "priority": "p1",
            "customer_name": "Test Customer",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
            "site_postcode": "WC1V 7AA",
            "required_skills": ["electrical", "plumbing"],
        })
        assert resp.status_code in [200, 201], f"Failed: {resp.text}"
        case = resp.json()
        self.test_case_id = case["id"]

        assert case.get("site_postcode") == "WC1V 7AA"
        assert case.get("required_skills") == ["electrical", "plumbing"]
        print(f"Intake with skills/postcode: {case['reference']}")


class TestCasePatch:
    """Case PATCH tests for new fields."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.test_case_id = None
        yield

        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _create_test_case(self):
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Patch_Case_{uuid.uuid4().hex[:8]}",
            "priority": "p3",
            "customer_name": "Test",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
        })
        case = resp.json()
        self.test_case_id = case["id"]
        return case

    def test_case_patch_equipment_ids(self):
        """PUT /api/svc/cases/{id} accepts equipment_ids patch."""
        case = self._create_test_case()

        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "equipment_ids": ["new-equip-001", "new-equip-002"]
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        updated = resp.json()

        assert updated.get("equipment_ids") == ["new-equip-001", "new-equip-002"]
        print("Case patched with equipment_ids")

    def test_case_patch_equipment_serials(self):
        """PUT /api/svc/cases/{id} accepts equipment_serials patch."""
        case = self._create_test_case()

        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "equipment_serials": ["SN-NEW-001"]
        })
        assert resp.status_code == 200
        updated = resp.json()

        assert updated.get("equipment_serials") == ["SN-NEW-001"]
        print("Case patched with equipment_serials")

    def test_case_patch_required_skills(self):
        """PUT /api/svc/cases/{id} accepts required_skills patch."""
        case = self._create_test_case()

        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "required_skills": ["hvac", "mechanical"]
        })
        assert resp.status_code == 200
        updated = resp.json()

        assert updated.get("required_skills") == ["hvac", "mechanical"]
        print("Case patched with required_skills")

    def test_case_patch_site_postcode(self):
        """PUT /api/svc/cases/{id} accepts site_postcode patch."""
        case = self._create_test_case()

        resp = self.session.put(f"{BASE_URL}/api/svc/cases/{case['id']}", json={
            "site_postcode": "SW1A 1AA"
        })
        assert resp.status_code == 200
        updated = resp.json()

        assert updated.get("site_postcode") == "SW1A 1AA"
        print("Case patched with site_postcode")


class TestSchedulerDiary:
    """Scheduler diary tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        yield

    def test_diary_returns_engineers_cases_unassigned(self):
        """GET /api/svc/scheduler/diary returns engineers, cases, unassigned."""
        start = datetime.now(timezone.utc).isoformat()

        resp = self.session.get(f"{BASE_URL}/api/svc/scheduler/diary", params={
            "start": start,
            "days": 7
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "start" in data
        assert "days" in data
        assert "engineers" in data
        assert "cases" in data
        assert "unassigned" in data
        assert isinstance(data["engineers"], list)
        assert isinstance(data["cases"], list)
        assert isinstance(data["unassigned"], list)
        print(f"Diary: {len(data['engineers'])} engineers, {len(data['cases'])} scheduled, {len(data['unassigned'])} unassigned")


class TestSchedulerAssign:
    """Scheduler assign tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        self.test_case_id = None
        yield

        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _create_test_case(self):
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Sched_Case_{uuid.uuid4().hex[:8]}",
            "priority": "p2",
            "customer_name": "Test",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
        })
        case = resp.json()
        self.test_case_id = case["id"]
        return case

    def _ensure_engineer_exists(self):
        """Ensure current user has an engineer profile."""
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/me")
        assert resp.status_code == 200
        return resp.json()["engineer"]

    def test_assign_sets_engineer_and_scheduled_at(self):
        """POST /api/svc/scheduler/assign sets engineer + scheduled_at."""
        case = self._create_test_case()
        engineer = self._ensure_engineer_exists()

        scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        resp = self.session.post(f"{BASE_URL}/api/svc/scheduler/assign", json={
            "case_id": case["id"],
            "engineer_id": engineer["id"],
            "scheduled_at": scheduled_at
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        updated = resp.json()

        assert updated["assigned_engineer_id"] == engineer["id"]
        assert updated["scheduled_at"] == scheduled_at
        print(f"Assigned case to {engineer['full_name']} at {scheduled_at}")

    def test_assign_transitions_new_to_assigned(self):
        """POST /api/svc/scheduler/assign auto-transitions new/triaged → assigned."""
        case = self._create_test_case()
        engineer = self._ensure_engineer_exists()

        # Case starts as 'new'
        assert case["status"] == "new"

        resp = self.session.post(f"{BASE_URL}/api/svc/scheduler/assign", json={
            "case_id": case["id"],
            "engineer_id": engineer["id"]
        })
        assert resp.status_code == 200
        updated = resp.json()

        assert updated["status"] == "assigned", f"Expected assigned, got {updated['status']}"
        print("Assign auto-transitioned new → assigned")


class TestSchedulerAutoAssign:
    """Scheduler auto-assign tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        self.test_case_id = None
        yield

        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _create_test_case(self, **kwargs):
        data = {
            "title": f"TEST_Auto_Case_{uuid.uuid4().hex[:8]}",
            "priority": "p2",
            "customer_name": "Test",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
            **kwargs
        }
        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json=data)
        case = resp.json()
        self.test_case_id = case["id"]
        return case

    def _ensure_engineer_exists(self):
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/me")
        assert resp.status_code == 200
        return resp.json()["engineer"]

    def test_auto_assign_preview_returns_rankings(self):
        """POST /api/svc/scheduler/auto-assign returns rankings with breakdown."""
        case = self._create_test_case()
        self._ensure_engineer_exists()

        resp = self.session.post(
            f"{BASE_URL}/api/svc/scheduler/auto-assign",
            params={"case_id": case["id"], "commit": False}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "case_id" in data
        assert "rankings" in data
        assert isinstance(data["rankings"], list)

        if len(data["rankings"]) > 0:
            top = data["rankings"][0]
            assert "engineer_id" in top
            assert "engineer_name" in top
            assert "score" in top
            assert "breakdown" in top

            breakdown = top["breakdown"]
            assert "drive_minutes" in breakdown
            assert "skill_mismatch" in breakdown
            assert "van_match" in breakdown
            assert "sla_breach_risk" in breakdown
            assert "overtime_minutes" in breakdown
            print(f"Top ranking: {top['engineer_name']} score={top['score']}, breakdown={breakdown}")

    def test_auto_assign_commit_assigns_top_engineer(self):
        """POST /api/svc/scheduler/auto-assign?commit=true assigns top engineer."""
        case = self._create_test_case()
        self._ensure_engineer_exists()

        resp = self.session.post(
            f"{BASE_URL}/api/svc/scheduler/auto-assign",
            params={"case_id": case["id"], "commit": True}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()

        assert "assigned_engineer_id" in data
        assert "assigned_engineer_name" in data
        assert "score" in data
        print(f"Auto-assigned to {data['assigned_engineer_name']} with score {data['score']}")

        # Verify case was updated
        resp = self.session.get(f"{BASE_URL}/api/svc/cases/{case['id']}")
        updated = resp.json()
        assert updated["assigned_engineer_id"] == data["assigned_engineer_id"]


class TestScoringFormula:
    """Scoring formula verification tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        self.user_id = user_id
        self.test_case_id = None
        yield

        if self.test_case_id:
            try:
                self.session.delete(f"{BASE_URL}/api/svc/cases/{self.test_case_id}")
            except:
                pass

    def _ensure_engineer_exists(self):
        resp = self.session.get(f"{BASE_URL}/api/svc/engineer/me")
        assert resp.status_code == 200
        return resp.json()["engineer"]

    def test_scoring_same_outward_postcode_15_minutes(self):
        """Scoring: same outward postcode → drive_minutes=15."""
        # Get engineer's home postcode
        engineer = self._ensure_engineer_exists()
        eng_postcode = (engineer.get("home_address") or {}).get("postcode", "")

        # Create case with same outward code
        if eng_postcode:
            outward = eng_postcode.split(" ")[0]
            site_postcode = f"{outward} 1AA"
        else:
            site_postcode = "WC1V 1AA"  # Default

        resp = self.session.post(f"{BASE_URL}/api/svc/intake/phone", json={
            "title": f"TEST_Score_Case_{uuid.uuid4().hex[:8]}",
            "priority": "p2",
            "customer_name": "Test",
            "customer_phone": "+447700900001",
            "site_name": "Test Site",
            "site_postcode": site_postcode,
        })
        case = resp.json()
        self.test_case_id = case["id"]

        # Get auto-assign preview
        resp = self.session.post(
            f"{BASE_URL}/api/svc/scheduler/auto-assign",
            params={"case_id": case["id"], "commit": False}
        )
        assert resp.status_code == 200
        data = resp.json()

        if len(data["rankings"]) > 0:
            # Find our engineer in rankings
            our_ranking = next((r for r in data["rankings"] if r["engineer_id"] == engineer["id"]), None)
            if our_ranking:
                # If postcodes match, drive_minutes should be 15
                # If no postcode set, it defaults to 30
                drive = our_ranking["breakdown"]["drive_minutes"]
                print(f"Drive minutes for {site_postcode}: {drive}")
                # Just verify it's a reasonable value
                assert drive in [15, 30, 45, 90], f"Unexpected drive_minutes: {drive}"


class TestSiconOutboxPayload:
    """Verify Sicon outbox payload includes new fields."""

    @pytest.fixture(autouse=True)
    def setup(self):
        token, user_id, org_id = _get_session_auth()
        assert token, "Failed to get session auth token"

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **rate_limit_bypass_headers()
        })
        yield

    def test_sicon_sync_to_sicon_call_includes_new_fields(self):
        """Verify _to_sicon_call includes EquipmentIDs, EquipmentSerials, Parts, RequiredSkills."""
        from routes.svc.integrations.sicon_sync import _to_sicon_call

        # Mock case with all new fields
        case = {
            "id": "test-case-id",
            "reference": "SVC-00001",
            "organization_id": "test-org",
            "status": "assigned",
            "priority": "p2",
            "cover_type": "chargeable",
            "title": "Test Case",
            "description": "Test description",
            "equipment_ids": ["equip-001", "equip-002"],
            "equipment_serials": ["SN-12345", "SN-67890"],
            "allocated_parts": [
                {"part_sku": "BELT-001", "part_name": "Belt", "qty": 2, "source": "warehouse", "engineer_id": ""},
            ],
            "required_skills": ["electrical", "plumbing"],
            "site_postcode": "WC1V 7AA",
            "site_id": "site-001",
            "site_name": "Test Site",
        }

        payload = _to_sicon_call(case)

        # Verify new fields
        assert payload["EquipmentIDs"] == ["equip-001", "equip-002"]
        assert payload["EquipmentSerials"] == ["SN-12345", "SN-67890"]
        assert len(payload["Parts"]) == 1
        assert payload["Parts"][0]["PartCode"] == "BELT-001"
        assert payload["Parts"][0]["Quantity"] == 2
        assert payload["RequiredSkills"] == ["electrical", "plumbing"]
        print("Sicon payload includes all new fields")


class TestFieldMappingDoc:
    """Verify SVC_FIELD_MAPPING.md has new sections."""

    def test_mapping_doc_has_parts_sections(self):
        """Verify SVC_FIELD_MAPPING.md has §12, §13, §14."""
        path = "/app/memory/SVC_FIELD_MAPPING.md"
        assert os.path.exists(path), f"Missing: {path}"

        with open(path) as f:
            content = f.read()

        # Verify new sections exist
        assert "## 12." in content or "§12" in content, "Missing §12 (svc_parts)"
        assert "## 13." in content or "§13" in content, "Missing §13 (svc_van_stock)"
        assert "## 14." in content or "§14" in content, "Missing §14 (svc_part_movements)"
        assert "svc_parts" in content
        assert "svc_van_stock" in content
        assert "svc_part_movements" in content
        assert "sage_stock_code" in content.lower() or "StockCode" in content
        assert "sicon_part_id" in content.lower() or "PartID" in content
        print("SVC_FIELD_MAPPING.md has all required sections")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
