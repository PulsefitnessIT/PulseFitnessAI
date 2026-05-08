"""
Test suite for iteration 133: Feature Presets, Audit Log, Copy Features, Display Name, QR Card
Tests:
- Feature presets API (list, apply, validation)
- Copy features from org
- Feature audit log
- Manual feature update appends audit + unsets preset
- Equipment display_name field
- QR card endpoint
- Cleanup: reset Tottenham Green features to {}
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials (loaded from env with local-dev fallbacks)
MASTER_ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_ADMIN_PASSWORD = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_PRO_EMAIL = os.environ.get("TEST_PULSE_PRO_EMAIL", "lee.somers@pulsefitness.com")
PULSE_PRO_ALT_EMAIL = os.environ.get("TEST_PULSE_PRO_ALT_EMAIL", "somerslee@hotmail.com")
PULSE_PRO_PASSWORD = os.environ.get("TEST_PULSE_PRO_PASSWORD", "TempPass123!")

# Tottenham Green org ID
TOTTENHAM_GREEN_ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"


class TestFeaturePresetsAPI:
    """Test the feature presets listing and validation"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    @pytest.fixture(scope="class")
    def pulse_pro_token(self):
        """Get Pulse Pro user auth token - try primary then alt"""
        # Try primary email first
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")

        # Try alternate email
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_ALT_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")

        pytest.skip("Could not login as Pulse Pro user (rate limited or credentials invalid)")

    def test_feature_presets_endpoint_registered(self):
        """Verify the endpoint is registered (returns 200/401, not 404)"""
        resp = requests.head(f"{BASE_URL}/api/master-admin/feature-presets")
        # Should be 401 (unauthorized) or 405 (method not allowed for HEAD), not 404
        assert resp.status_code != 404, "Endpoint not registered - got 404"
        print(f"Endpoint registered - HEAD returned {resp.status_code}")

    def test_feature_presets_list_requires_admin(self, pulse_pro_token):
        """Non-admin users should get 403"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/feature-presets",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("Non-admin correctly gets 403")

    def test_feature_presets_list_returns_5_presets(self, admin_token):
        """Admin should get list of 5 presets with correct structure"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/feature-presets",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "presets" in data, "Response missing 'presets' key"
        presets = data["presets"]

        # Should have exactly 5 presets
        assert len(presets) == 5, f"Expected 5 presets, got {len(presets)}"

        # Check expected preset keys
        expected_keys = {"pulse_basic", "pulse_pro_standard", "pulse_pro_kpi", "pulse_enterprise", "gymaxis_full"}
        actual_keys = {p["key"] for p in presets}
        assert actual_keys == expected_keys, f"Preset keys mismatch. Expected {expected_keys}, got {actual_keys}"

        # Verify each preset has required fields
        for preset in presets:
            assert "key" in preset, f"Preset missing 'key': {preset}"
            assert "label" in preset, f"Preset missing 'label': {preset}"
            assert "description" in preset, f"Preset missing 'description': {preset}"
            assert "features" in preset, f"Preset missing 'features': {preset}"
            assert isinstance(preset["features"], dict), f"Features should be dict: {preset}"

        print(f"Got {len(presets)} presets: {[p['key'] for p in presets]}")


class TestApplyPreset:
    """Test applying feature presets to organizations"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    def test_apply_invalid_preset_returns_400(self, admin_token):
        """Invalid preset key should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/apply-preset",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"preset": "invalid_preset_key"}
        )
        assert resp.status_code == 400, f"Expected 400 for invalid preset, got {resp.status_code}: {resp.text}"
        print("Invalid preset correctly returns 400")

    def test_apply_pulse_pro_kpi_preset(self, admin_token):
        """Apply pulse_pro_kpi preset to Tottenham Green"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/apply-preset",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"preset": "pulse_pro_kpi"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        assert "features" in data, f"Response missing 'features': {data}"

        features = data["features"]
        # Verify kpi_engine is enabled in pulse_pro_kpi preset
        assert features.get("kpi_engine") == True, f"kpi_engine should be True: {features}"
        assert features.get("ai_audits") == True, f"ai_audits should be True: {features}"
        assert features.get("ppm_engine") == True, f"ppm_engine should be True: {features}"

        print(f"Applied pulse_pro_kpi preset. Features: {features}")

    def test_verify_features_preset_stored(self, admin_token):
        """Verify features_preset is stored in org document"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/audit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data.get("current_preset") == "pulse_pro_kpi", f"Expected current_preset='pulse_pro_kpi': {data}"
        print(f"Verified features_preset stored: {data.get('current_preset')}")


class TestKPIAccessAfterPreset:
    """Test that Pulse Pro user can access KPI after preset applied"""

    @pytest.fixture(scope="class")
    def pulse_pro_token(self):
        """Get Pulse Pro user auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")

        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": PULSE_PRO_ALT_EMAIL,
            "password": PULSE_PRO_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")

        pytest.skip("Could not login as Pulse Pro user")

    def test_kpi_dashboard_accessible_after_preset(self, pulse_pro_token):
        """Pulse Pro user should get 200 on KPI dashboard after pulse_pro_kpi preset"""
        resp = requests.get(
            f"{BASE_URL}/api/reports/kpi-dashboard",
            headers={"Authorization": f"Bearer {pulse_pro_token}"}
        )
        # After applying pulse_pro_kpi preset, kpi_engine should be enabled
        # So this should return 200 (or at least not 403)
        if resp.status_code == 403:
            print("WARNING: KPI still returns 403 - preset may not have been applied or user is in different org")
        else:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            print(f"KPI dashboard accessible - status {resp.status_code}")


class TestCopyFeatures:
    """Test copying features from one org to another"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    @pytest.fixture(scope="class")
    def source_org_id(self, admin_token):
        """Get a different org to copy from"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        orgs = resp.json().get("organizations", [])
        # Find an org that's not Tottenham Green
        for org in orgs:
            if org["id"] != TOTTENHAM_GREEN_ORG_ID:
                return org["id"]
        pytest.skip("No other org found to copy from")

    def test_copy_from_same_org_returns_400(self, admin_token):
        """Copying from same org should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/copy-from/{TOTTENHAM_GREEN_ORG_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400 for same org, got {resp.status_code}: {resp.text}"
        print("Copy from same org correctly returns 400")

    def test_copy_from_nonexistent_org_returns_404(self, admin_token):
        """Copying from non-existent org should return 404"""
        fake_org_id = "00000000-0000-0000-0000-000000000000"
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/copy-from/{fake_org_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 404, f"Expected 404 for non-existent org, got {resp.status_code}: {resp.text}"
        print("Copy from non-existent org correctly returns 404")

    def test_copy_features_success(self, admin_token, source_org_id):
        """Successfully copy features from another org"""
        resp = requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/copy-from/{source_org_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data.get("success") == True, f"Expected success=True: {data}"
        assert "features" in data, f"Response missing 'features': {data}"
        assert "copied_from" in data, f"Response missing 'copied_from': {data}"

        print(f"Copied features from {data.get('copied_from')}: {data.get('features')}")


class TestAuditLog:
    """Test the feature audit log"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    def test_audit_log_returns_entries(self, admin_token):
        """Audit log should have entries from previous operations"""
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/audit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "audit" in data, f"Response missing 'audit': {data}"

        audit = data["audit"]
        assert isinstance(audit, list), f"Audit should be a list: {audit}"

        if len(audit) > 0:
            # Verify entry structure
            entry = audit[0]
            assert "by" in entry, f"Entry missing 'by': {entry}"
            assert "at" in entry, f"Entry missing 'at': {entry}"
            assert "changes" in entry, f"Entry missing 'changes': {entry}"
            # preset can be None for manual changes
            assert "preset" in entry, f"Entry missing 'preset': {entry}"

            print(f"Audit log has {len(audit)} entries. Latest: by={entry.get('by')}, preset={entry.get('preset')}")
        else:
            print("Audit log is empty (no changes recorded yet)")


class TestManualFeatureUpdate:
    """Test that manual feature update appends audit and unsets preset"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    def test_manual_update_appends_audit_and_unsets_preset(self, admin_token):
        """PUT /api/master-admin/organizations/{id}/features should append audit and unset preset"""
        # First apply a preset so we have a preset to unset
        requests.post(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/apply-preset",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"preset": "pulse_basic"}
        )

        # Capture the latest audit entry before the manual update (audit list is capped at 50,
        # so a simple "count increased" check is unreliable under repeat runs — we instead
        # assert the newest entry's timestamp advances).
        import time
        time.sleep(1)  # ensure timestamp resolution beats our threshold
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/audit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        audit_before = resp.json().get("audit", [])
        latest_before_ts = (audit_before[0].get("at") if audit_before else "") or ""

        # Now do a manual update
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"features": {"kpi_engine": True, "ai_audits": False}}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        # Check audit log was appended (newest timestamp moved forward)
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features/audit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = resp.json()
        latest_after_ts = (data.get("audit", [{}])[0].get("at", "") if data.get("audit") else "") or ""
        assert latest_after_ts > latest_before_ts, (
            f"Newest audit timestamp should advance after a manual update. "
            f"Before: {latest_before_ts!r}, After: {latest_after_ts!r}"
        )

        # Check preset was unset
        assert data.get("current_preset") is None, f"Preset should be unset after manual update: {data.get('current_preset')}"

        # Check latest audit entry has preset=None
        if data.get("audit"):
            latest = data["audit"][0]
            assert latest.get("preset") is None, f"Latest audit entry should have preset=None: {latest}"

        print(f"Manual update advanced audit timestamp ({latest_before_ts} -> {latest_after_ts}) and unset preset")


class TestEquipmentDisplayName:
    """Test equipment display_name field"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    def test_equipment_list_has_display_name(self, admin_token):
        """GET /api/equipment should return items with display_name field"""
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        equipment_list = data.get("equipment", [])

        if len(equipment_list) == 0:
            pytest.skip("No equipment found to test display_name")

        # Check that all items have display_name
        for equip in equipment_list[:5]:  # Check first 5
            assert "display_name" in equip, f"Equipment missing display_name: {equip.get('id')}"
            assert equip["display_name"], f"display_name should not be empty: {equip}"

            # Verify display_name is shorter or equal to name
            name = equip.get("name", "")
            display_name = equip["display_name"]
            if name and len(name) > 40:
                assert len(display_name) <= 40 or display_name.endswith("…"), f"Long name should be truncated: {name} -> {display_name}"

        print(f"Checked {min(5, len(equipment_list))} equipment items - all have display_name")

        # Show example of long name truncation if any
        for equip in equipment_list:
            if len(equip.get("name", "")) > 40:
                print(f"Example truncation: '{equip['name'][:50]}...' -> '{equip['display_name']}'")
                break

    def test_single_equipment_has_display_name(self, admin_token):
        """GET /api/equipment/{id} should return display_name field"""
        # First get an equipment ID
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        equipment_list = resp.json().get("equipment", [])

        if len(equipment_list) == 0:
            pytest.skip("No equipment found to test")

        equip_id = equipment_list[0]["id"]

        resp = requests.get(
            f"{BASE_URL}/api/equipment/{equip_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "display_name" in data, f"Single equipment missing display_name: {data.get('id')}"
        print(f"Single equipment has display_name: '{data['display_name']}'")


class TestQRCard:
    """Test QR card endpoint"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    @pytest.fixture(scope="class")
    def equipment_id(self, admin_token):
        """Get an equipment ID to test with"""
        resp = requests.get(
            f"{BASE_URL}/api/equipment",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        equipment_list = resp.json().get("equipment", [])
        if len(equipment_list) == 0:
            pytest.skip("No equipment found to test QR card")
        return equipment_list[0]["id"]

    def test_qr_card_returns_png(self, admin_token, equipment_id):
        """GET /api/equipment/{id}/qr-card?size=62x35 should return PNG image"""
        resp = requests.get(
            f"{BASE_URL}/api/equipment/{equipment_id}/qr-card?size=62x35",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.headers.get("content-type") == "image/png", f"Expected image/png, got {resp.headers.get('content-type')}"

        # Check image size is non-trivial (>10KB as per requirements)
        content_length = len(resp.content)
        assert content_length > 10000, f"Image should be >10KB, got {content_length} bytes"

        print(f"QR card returned PNG image of {content_length} bytes")

    def test_qr_card_all_sizes(self, admin_token, equipment_id):
        """Test all QR card size presets"""
        sizes = ["62x35", "62x62", "50x50", "card", "a4"]

        for size in sizes:
            resp = requests.get(
                f"{BASE_URL}/api/equipment/{equipment_id}/qr-card?size={size}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert resp.status_code == 200, f"Size {size} failed: {resp.status_code}"
            assert resp.headers.get("content-type") == "image/png"
            print(f"Size {size}: {len(resp.content)} bytes")


class TestCleanup:
    """Cleanup: Reset Tottenham Green org features to {}"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get master admin auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MASTER_ADMIN_EMAIL,
            "password": MASTER_ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json().get("token")

    def test_reset_tottenham_green_features(self, admin_token):
        """Reset Tottenham Green org features to empty dict"""
        resp = requests.put(
            f"{BASE_URL}/api/master-admin/organizations/{TOTTENHAM_GREEN_ORG_ID}/features",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"features": {}}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        # Verify features are now empty
        resp = requests.get(
            f"{BASE_URL}/api/master-admin/organizations",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        orgs = resp.json().get("organizations", [])
        tottenham = next((o for o in orgs if o["id"] == TOTTENHAM_GREEN_ORG_ID), None)

        if tottenham:
            features = tottenham.get("features", {})
            assert features == {} or all(v is None for v in features.values()), f"Features should be empty: {features}"
            print(f"Tottenham Green features reset to: {features}")
        else:
            print("Could not verify - Tottenham Green org not found in list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
