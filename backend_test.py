#!/usr/bin/env python3
"""
Pulse Fitness AI - Backend Smoke Test
White-label rebrand verification after GymAxis → Pulse Fitness conversion
"""
import requests
import sys
import json
from datetime import datetime

class PulseFitnessAPITester:
    def __init__(self, base_url="https://fitness-ai-migrate.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user_id = None
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

    def test_health_endpoint(self):
        """Test GET /api/health - must return 200"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                self.log_test(
                    "Health Endpoint", 
                    True, 
                    f"Status: {response.status_code}, Response: {data}",
                    data
                )
            else:
                self.log_test(
                    "Health Endpoint", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200, Response: {response.text}"
                )
            return success
        except Exception as e:
            self.log_test("Health Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_master_admin_login(self):
        """Test POST /api/auth/login with master admin credentials"""
        try:
            data = {
                "email": self.master_admin_email,
                "password": self.master_admin_password
            }
            
            response = requests.post(
                f"{self.api_url}/auth/login", 
                json=data, 
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self.token = result.get('token')
                user = result.get('user', {})
                self.user_id = user.get('id')
                
                # Verify we got a valid token
                if self.token and self.user_id:
                    self.log_test(
                        "Master Admin Login", 
                        True, 
                        f"Token received, User ID: {self.user_id}, Email: {user.get('email')}, Is Master Admin: {user.get('is_master_admin')}",
                        {"user_id": self.user_id, "is_master_admin": user.get('is_master_admin')}
                    )
                    return True
                else:
                    self.log_test(
                        "Master Admin Login", 
                        False, 
                        f"Login succeeded but missing token or user_id. Response: {result}"
                    )
                    return False
            else:
                self.log_test(
                    "Master Admin Login", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200, Response: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test("Master Admin Login", False, f"Exception: {str(e)}")
            return False

    def test_auth_me_endpoint(self):
        """Test GET /api/auth/me - authenticated read endpoint"""
        if not self.token:
            self.log_test("Auth Me Endpoint", False, "No token available (login failed)")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(
                f"{self.api_url}/auth/me", 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                user_data = response.json()
                self.log_test(
                    "Auth Me Endpoint", 
                    True, 
                    f"Status: 200, User: {user_data.get('email')}, Role: {user_data.get('role')}",
                    {"email": user_data.get('email'), "role": user_data.get('role')}
                )
                return True
            else:
                self.log_test(
                    "Auth Me Endpoint", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200, Response: {response.text}"
                )
                return False
            
        except Exception as e:
            self.log_test("Auth Me Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_master_admin_endpoint(self):
        """Test a master-admin specific endpoint"""
        if not self.token:
            self.log_test("Master Admin Endpoint", False, "No token available (login failed)")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            # Try to access master admin organizations list
            response = requests.get(
                f"{self.api_url}/master-admin/organizations", 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                orgs = data.get('organizations', [])
                self.log_test(
                    "Master Admin Organizations Endpoint", 
                    True, 
                    f"Status: 200, Organizations count: {len(orgs)}",
                    {"org_count": len(orgs)}
                )
                return True
            else:
                self.log_test(
                    "Master Admin Organizations Endpoint", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200, Response: {response.text}"
                )
                return False
            
        except Exception as e:
            self.log_test("Master Admin Organizations Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_organization_endpoint(self):
        """Test organization endpoint - representative authenticated read"""
        if not self.token:
            self.log_test("Organization Endpoint", False, "No token available (login failed)")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            # Try to access organization data
            response = requests.get(
                f"{self.api_url}/organization", 
                headers=headers, 
                timeout=30
            )
            
            # Accept 200 or 404 as success - we're checking for 500 errors
            if response.status_code in [200, 404]:
                if response.status_code == 200:
                    data = response.json()
                    org_name = data.get('name', '')
                    self.log_test(
                        "Organization Endpoint", 
                        True, 
                        f"Status: 200, Organization: {org_name}",
                        {"org_name": org_name}
                    )
                else:
                    self.log_test(
                        "Organization Endpoint", 
                        True, 
                        f"Status: 404 (no organization - acceptable)"
                    )
                return True
            else:
                self.log_test(
                    "Organization Endpoint", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200 or 404, Response: {response.text}"
                )
                return False
            
        except Exception as e:
            self.log_test("Organization Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_memberships_list_endpoint(self):
        """Test Memberships list endpoint - representative authenticated read"""
        if not self.token:
            self.log_test("Memberships List Endpoint", False, "No token available (login failed)")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            # Try to access memberships list
            response = requests.get(
                f"{self.api_url}/memberships/members", 
                headers=headers, 
                timeout=30
            )
            
            # Accept 200 or 404 as success - we're checking for 500 errors
            if response.status_code in [200, 404]:
                if response.status_code == 200:
                    data = response.json()
                    members = data.get('members', [])
                    self.log_test(
                        "Memberships Members Endpoint", 
                        True, 
                        f"Status: 200, Members count: {len(members)}",
                        {"member_count": len(members)}
                    )
                else:
                    self.log_test(
                        "Memberships Members Endpoint", 
                        True, 
                        f"Status: 404 (no members - acceptable for clean DB)"
                    )
                return True
            else:
                self.log_test(
                    "Memberships Members Endpoint", 
                    False, 
                    f"Status: {response.status_code}, Expected: 200 or 404, Response: {response.text}"
                )
                return False
            
        except Exception as e:
            self.log_test("Memberships Members Endpoint", False, f"Exception: {str(e)}")
            return False

    def run_smoke_tests(self):
        """Run focused smoke tests for white-label rebrand verification"""
        print("=" * 80)
        print("🔍 Pulse Fitness AI - Backend Smoke Test")
        print("   White-label rebrand verification (GymAxis → Pulse Fitness)")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 80)
        print()
        
        # Priority 1: Health check
        print("📋 Test 1: Health Endpoint")
        if not self.test_health_endpoint():
            print("\n❌ CRITICAL: Health endpoint failed - backend may not be running")
        print()
        
        # Priority 2: Master Admin Login
        print("📋 Test 2: Master Admin Login")
        if not self.test_master_admin_login():
            print("\n❌ CRITICAL: Master admin login failed - database seed may have failed")
            print("   This is the primary regression to confirm after DB reset")
        print()
        
        # Priority 3: Authenticated read endpoints
        print("📋 Test 3: Current User Endpoint (/api/auth/me)")
        self.test_auth_me_endpoint()
        print()
        
        print("📋 Test 4: Master Admin Endpoint")
        self.test_master_admin_endpoint()
        print()
        
        print("📋 Test 5: Organization Endpoint")
        self.test_organization_endpoint()
        print()
        
        print("📋 Test 6: Memberships List Endpoint")
        self.test_memberships_list_endpoint()
        print()
        
        # Print summary
        print("=" * 80)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run} passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("✅ All smoke tests PASSED")
        else:
            print(f"❌ {self.tests_run - self.tests_passed} test(s) FAILED")
        print("=" * 80)
        
        return self.tests_passed == self.tests_run

def main():
    tester = PulseFitnessAPITester()
    success = tester.run_smoke_tests()
    
    # Save detailed results
    results_file = '/app/backend_test_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'test_type': 'smoke_test_white_label_rebrand',
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
