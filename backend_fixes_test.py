#!/usr/bin/env python3
"""
Pulse Fitness AI - Backend Fixes Verification Test
Tests three specific fixes:
1. AUTH COOKIE SameSite=None & Secure attributes
2. MASTER ADMIN AUDIT LOG reading from audit_logs collection
3. MASTER ADMIN password persistence with MASTER_ADMIN_RESET_ON_BOOT=0
"""
import requests
import sys
import json
from datetime import datetime

class BackendFixesTester:
    def __init__(self, base_url="https://admin-portal-fix-37.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.session_cookie = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Master admin credentials from test_credentials.md
        self.master_admin_email = "admin@pulsefitness.com"
        self.master_admin_password = "MasterAdmin123!"

    def log_test(self, name, success, details="", response_data=None):
        """Log test result with detailed information"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
            if details:
                print(f"   {details}")
        else:
            print(f"❌ {name}")
            if details:
                print(f"   ERROR: {details}")
        
        result = {
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        if response_data:
            result["response_data"] = response_data
        
        self.test_results.append(result)
        return success

    def test_auth_cookie_samesite(self):
        """
        FIX 1: Test that POST /api/auth/login returns Set-Cookie with SameSite=None and Secure
        This fix allows the session cookie to work inside the Emergent App Preview iframe
        """
        print("\n" + "="*80)
        print("🔐 FIX 1: AUTH COOKIE SameSite=None & Secure")
        print("="*80)
        
        try:
            data = {
                "email": self.master_admin_email,
                "password": self.master_admin_password
            }
            
            # Use a session to capture cookies
            session = requests.Session()
            response = session.post(
                f"{self.api_url}/auth/login", 
                json=data, 
                timeout=30
            )
            
            # Check response status
            if response.status_code != 200:
                return self.log_test(
                    "Login Response Status", 
                    False, 
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
            
            self.log_test("Login Response Status", True, "Status: 200 OK")
            
            # Extract token from response body
            result = response.json()
            self.token = result.get('token')
            user = result.get('user', {})
            
            if not self.token:
                return self.log_test(
                    "Token in Response Body", 
                    False, 
                    "No token in response body"
                )
            
            self.log_test(
                "Token in Response Body", 
                True, 
                f"Token received, User: {user.get('email')}, is_master_admin: {user.get('is_master_admin')}"
            )
            
            # Check Set-Cookie header
            set_cookie_headers = response.headers.get('Set-Cookie', '')
            if not set_cookie_headers:
                # Try getting from raw headers (multiple Set-Cookie headers)
                set_cookie_headers = response.raw.headers.get_all('Set-Cookie') or []
                if isinstance(set_cookie_headers, list):
                    set_cookie_headers = '; '.join(set_cookie_headers)
            
            print(f"\n📋 Set-Cookie Header(s):")
            print(f"   {set_cookie_headers}")
            
            # Look for ga_session cookie
            ga_session_found = False
            has_samesite_none = False
            has_secure = False
            
            if 'ga_session=' in set_cookie_headers:
                ga_session_found = True
                cookie_parts = set_cookie_headers.lower()
                
                # Check for SameSite=None
                if 'samesite=none' in cookie_parts:
                    has_samesite_none = True
                
                # Check for Secure
                if 'secure' in cookie_parts:
                    has_secure = True
            
            # Verify ga_session cookie exists
            if not ga_session_found:
                return self.log_test(
                    "ga_session Cookie Present", 
                    False, 
                    "ga_session cookie not found in Set-Cookie header"
                )
            
            self.log_test("ga_session Cookie Present", True, "ga_session cookie found")
            
            # Verify SameSite=None
            if not has_samesite_none:
                return self.log_test(
                    "SameSite=None Attribute", 
                    False, 
                    "SameSite=None not found in ga_session cookie. This is required for iframe embedding."
                )
            
            self.log_test(
                "SameSite=None Attribute", 
                True, 
                "✓ SameSite=None present (allows cross-site cookie in iframe)"
            )
            
            # Verify Secure
            if not has_secure:
                return self.log_test(
                    "Secure Attribute", 
                    False, 
                    "Secure attribute not found. Required when SameSite=None."
                )
            
            self.log_test(
                "Secure Attribute", 
                True, 
                "✓ Secure attribute present (required with SameSite=None)"
            )
            
            # Test authenticated call using the cookie
            print("\n📋 Testing authenticated call with cookie...")
            auth_response = session.get(f"{self.api_url}/auth/me", timeout=30)
            
            if auth_response.status_code != 200:
                return self.log_test(
                    "Authenticated Call with Cookie", 
                    False, 
                    f"GET /api/auth/me failed with status {auth_response.status_code}"
                )
            
            me_data = auth_response.json()
            self.log_test(
                "Authenticated Call with Cookie", 
                True, 
                f"✓ GET /api/auth/me succeeded using cookie. User: {me_data.get('email')}"
            )
            
            print("\n✅ FIX 1 VERIFIED: Auth cookie has SameSite=None and Secure attributes")
            return True
            
        except Exception as e:
            return self.log_test("Auth Cookie SameSite Test", False, f"Exception: {str(e)}")

    def test_master_admin_audit_log(self):
        """
        FIX 2: Test that GET /api/master-admin/audit-log returns events from audit_logs collection
        Previously it read from empty login_events collection and returned nothing
        """
        print("\n" + "="*80)
        print("📊 FIX 2: MASTER ADMIN AUDIT LOG (audit_logs collection)")
        print("="*80)
        
        if not self.token:
            return self.log_test(
                "Master Admin Audit Log", 
                False, 
                "No token available (login test must run first)"
            )
        
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            
            # Call the audit log endpoint with default parameters
            response = requests.get(
                f"{self.api_url}/master-admin/audit-log",
                headers=headers,
                params={"since_days": 7},  # Default window
                timeout=30
            )
            
            if response.status_code != 200:
                return self.log_test(
                    "Audit Log Endpoint Status", 
                    False, 
                    f"Expected 200, got {response.status_code}: {response.text}"
                )
            
            self.log_test("Audit Log Endpoint Status", True, "Status: 200 OK")
            
            data = response.json()
            events = data.get('events', [])
            count = data.get('count', 0)
            
            print(f"\n📋 Audit Log Response:")
            print(f"   Total events: {count}")
            print(f"   Since: {data.get('since', 'N/A')}")
            
            # The bug was "no details passing through" - verify we have events with details
            if count == 0:
                return self.log_test(
                    "Audit Log Has Events", 
                    False, 
                    "No events returned. Expected at least login events from audit_logs collection."
                )
            
            self.log_test(
                "Audit Log Has Events", 
                True, 
                f"✓ {count} event(s) returned"
            )
            
            # Find a login event with details
            login_event_found = False
            event_with_details = None
            
            for event in events:
                if event.get('kind') in ['login', 'login_failed']:
                    login_event_found = True
                    if event.get('actor_email') and event.get('timestamp') and event.get('summary'):
                        event_with_details = event
                        break
            
            if not login_event_found:
                return self.log_test(
                    "Login Event Present", 
                    False, 
                    "No login/login_failed events found in audit log"
                )
            
            self.log_test("Login Event Present", True, "✓ Login event(s) found")
            
            if not event_with_details:
                return self.log_test(
                    "Event Has Required Fields", 
                    False, 
                    "Login events missing required fields (actor_email, timestamp, summary)"
                )
            
            # Verify the event has all required fields
            actor_email = event_with_details.get('actor_email', '')
            timestamp = event_with_details.get('timestamp', '')
            summary = event_with_details.get('summary', '')
            details = event_with_details.get('details', {})
            
            print(f"\n📋 Sample Event:")
            print(f"   Kind: {event_with_details.get('kind')}")
            print(f"   Actor Email: {actor_email}")
            print(f"   Timestamp: {timestamp}")
            print(f"   Summary: {summary}")
            print(f"   Details: {json.dumps(details, indent=6)}")
            
            # Verify actor_email is not empty
            if not actor_email or actor_email == "":
                return self.log_test(
                    "Event Has actor_email", 
                    False, 
                    "actor_email is empty or missing"
                )
            
            self.log_test(
                "Event Has actor_email", 
                True, 
                f"✓ actor_email present: {actor_email}"
            )
            
            # Verify timestamp
            if not timestamp:
                return self.log_test(
                    "Event Has timestamp", 
                    False, 
                    "timestamp is missing"
                )
            
            self.log_test("Event Has timestamp", True, f"✓ timestamp present: {timestamp}")
            
            # Verify summary
            if not summary:
                return self.log_test(
                    "Event Has summary", 
                    False, 
                    "summary is missing"
                )
            
            self.log_test("Event Has summary", True, f"✓ summary present: {summary}")
            
            # Verify details object exists (can be empty, but should be present)
            if details is None:
                return self.log_test(
                    "Event Has details Object", 
                    False, 
                    "details object is None"
                )
            
            # Check if details has meaningful content (e.g., ip address)
            has_ip = 'ip' in details and details['ip']
            details_info = f"✓ details object present"
            if has_ip:
                details_info += f" with IP: {details['ip']}"
            
            self.log_test("Event Has details Object", True, details_info)
            
            print("\n✅ FIX 2 VERIFIED: Audit log returns events from audit_logs collection with complete details")
            return True
            
        except Exception as e:
            return self.log_test("Master Admin Audit Log Test", False, f"Exception: {str(e)}")

    def test_master_admin_password_persistence(self):
        """
        FIX 3: Test that MASTER_ADMIN_RESET_ON_BOOT=0 is set and master admin login still works
        This ensures the password persists across restarts and is not reset on every boot
        """
        print("\n" + "="*80)
        print("🔑 FIX 3: MASTER ADMIN PASSWORD PERSISTENCE (RESET_ON_BOOT=0)")
        print("="*80)
        
        try:
            # Read the .env file to verify MASTER_ADMIN_RESET_ON_BOOT=0
            env_file_path = '/app/backend/.env'
            try:
                with open(env_file_path, 'r') as f:
                    env_content = f.read()
                
                # Check for MASTER_ADMIN_RESET_ON_BOOT setting
                reset_on_boot_found = False
                reset_on_boot_value = None
                
                for line in env_content.split('\n'):
                    if line.strip().startswith('MASTER_ADMIN_RESET_ON_BOOT'):
                        reset_on_boot_found = True
                        # Extract value
                        if '=' in line:
                            reset_on_boot_value = line.split('=', 1)[1].strip()
                        break
                
                if not reset_on_boot_found:
                    return self.log_test(
                        "MASTER_ADMIN_RESET_ON_BOOT Setting", 
                        False, 
                        "MASTER_ADMIN_RESET_ON_BOOT not found in backend/.env"
                    )
                
                print(f"\n📋 Environment Configuration:")
                print(f"   MASTER_ADMIN_RESET_ON_BOOT={reset_on_boot_value}")
                
                if reset_on_boot_value != "0":
                    return self.log_test(
                        "MASTER_ADMIN_RESET_ON_BOOT=0", 
                        False, 
                        f"Expected MASTER_ADMIN_RESET_ON_BOOT=0, got {reset_on_boot_value}"
                    )
                
                self.log_test(
                    "MASTER_ADMIN_RESET_ON_BOOT=0", 
                    True, 
                    "✓ MASTER_ADMIN_RESET_ON_BOOT is set to 0 (password will persist)"
                )
                
            except FileNotFoundError:
                return self.log_test(
                    "Read .env File", 
                    False, 
                    f"Could not read {env_file_path}"
                )
            
            # Test that login still works with the configured password
            print(f"\n📋 Testing login with configured password...")
            data = {
                "email": self.master_admin_email,
                "password": self.master_admin_password
            }
            
            response = requests.post(
                f"{self.api_url}/auth/login", 
                json=data, 
                timeout=30
            )
            
            if response.status_code != 200:
                return self.log_test(
                    "Master Admin Login Still Works", 
                    False, 
                    f"Login failed with status {response.status_code}. Password may have been reset."
                )
            
            result = response.json()
            user = result.get('user', {})
            
            self.log_test(
                "Master Admin Login Still Works", 
                True, 
                f"✓ Login successful with {self.master_admin_email} / {self.master_admin_password}"
            )
            
            # Verify it's still the master admin
            if not user.get('is_master_admin'):
                return self.log_test(
                    "User is Master Admin", 
                    False, 
                    "User logged in but is_master_admin is False"
                )
            
            self.log_test(
                "User is Master Admin", 
                True, 
                f"✓ is_master_admin=True, email={user.get('email')}"
            )
            
            print("\n✅ FIX 3 VERIFIED: MASTER_ADMIN_RESET_ON_BOOT=0 and password persists (MasterAdmin123!)")
            return True
            
        except Exception as e:
            return self.log_test("Master Admin Password Persistence Test", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all three fix verification tests"""
        print("=" * 80)
        print("🔍 Pulse Fitness AI - Backend Fixes Verification")
        print("   Testing three specific fixes:")
        print("   1. AUTH COOKIE SameSite=None & Secure")
        print("   2. MASTER ADMIN AUDIT LOG (audit_logs collection)")
        print("   3. MASTER ADMIN PASSWORD PERSISTENCE (RESET_ON_BOOT=0)")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 80)
        
        # Run all three tests
        fix1_passed = self.test_auth_cookie_samesite()
        fix2_passed = self.test_master_admin_audit_log()
        fix3_passed = self.test_master_admin_password_persistence()
        
        # Print summary
        print("\n" + "=" * 80)
        print("📊 FINAL SUMMARY")
        print("=" * 80)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"Success rate: {success_rate:.1f}%")
        print()
        
        print("Fix Status:")
        print(f"  {'✅' if fix1_passed else '❌'} FIX 1: AUTH COOKIE SameSite=None & Secure")
        print(f"  {'✅' if fix2_passed else '❌'} FIX 2: MASTER ADMIN AUDIT LOG")
        print(f"  {'✅' if fix3_passed else '❌'} FIX 3: MASTER ADMIN PASSWORD PERSISTENCE")
        print()
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL FIXES VERIFIED - All tests PASSED")
        else:
            print(f"❌ SOME FIXES FAILED - {self.tests_run - self.tests_passed} test(s) failed")
        print("=" * 80)
        
        return self.tests_passed == self.tests_run

def main():
    tester = BackendFixesTester()
    success = tester.run_all_tests()
    
    # Save detailed results
    results_file = '/app/backend_fixes_test_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'test_type': 'backend_fixes_verification',
            'timestamp': datetime.now().isoformat(),
            'total_tests': tester.tests_run,
            'passed_tests': tester.tests_passed,
            'failed_tests': tester.tests_run - tester.tests_passed,
            'success_rate': (tester.tests_passed / tester.tests_run) * 100 if tester.tests_run > 0 else 0,
            'results': tester.test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
