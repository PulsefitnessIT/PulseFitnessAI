import requests
import sys
import json
from datetime import datetime

class GymFixAPITester:
    def __init__(self, base_url="https://maintenance-hub-357.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def test_health_check(self):
        """Test if backend is accessible"""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=10)
            success = response.status_code == 200
            self.log_test("Backend Health Check", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Backend Health Check", False, str(e))
            return False

    def test_user_registration(self):
        """Test user registration"""
        try:
            test_email = f"test_{datetime.now().strftime('%H%M%S')}@gymfixai.com"
            data = {
                "email": test_email,
                "password": "Test123!",
                "full_name": "Test User",
                "company_name": "Test Gym"
            }
            
            response = requests.post(f"{self.api_url}/auth/register", json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                self.token = result.get('token')
                self.user_id = result.get('user', {}).get('id')
                self.log_test("User Registration", True, f"User ID: {self.user_id}")
                return True
            else:
                self.log_test("User Registration", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("User Registration", False, str(e))
            return False

    def test_user_login(self):
        """Test user login with existing credentials"""
        try:
            data = {
                "email": "test@gymfixai.com",
                "password": "Test123!"
            }
            
            response = requests.post(f"{self.api_url}/auth/login", json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                self.token = result.get('token')
                self.user_id = result.get('user', {}).get('id')
                self.log_test("User Login", True, f"Token received")
                return True
            else:
                self.log_test("User Login", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("User Login", False, str(e))
            return False

    def test_get_user_profile(self):
        """Test getting user profile"""
        if not self.token:
            self.log_test("Get User Profile", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(f"{self.api_url}/auth/me", headers=headers, timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                user_data = response.json()
                details += f", User: {user_data.get('email')}"
            
            self.log_test("Get User Profile", success, details)
            return success
            
        except Exception as e:
            self.log_test("Get User Profile", False, str(e))
            return False

    def test_ai_chat_diagnosis(self):
        """Test AI chat diagnosis"""
        if not self.token:
            self.log_test("AI Chat Diagnosis", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            data = {
                "message": "My treadmill belt is slipping and making noise",
                "equipment_type": "treadmill"
            }
            
            response = requests.post(f"{self.api_url}/chat/diagnose", json=data, headers=headers, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get('response', '')
                success = len(ai_response) > 50  # Check if we got a meaningful response
                self.log_test("AI Chat Diagnosis", success, f"Response length: {len(ai_response)}")
                return success
            else:
                self.log_test("AI Chat Diagnosis", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("AI Chat Diagnosis", False, str(e))
            return False

    def test_audit_generation(self):
        """Test AI audit report generation"""
        if not self.token:
            self.log_test("AI Audit Generation", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            data = {
                "equipment_type": "Treadmill Model X",
                "usage_frequency": "heavy",
                "last_maintenance": "2024-01-01",
                "notes": "Test audit for API testing"
            }
            
            response = requests.post(f"{self.api_url}/audit/generate", json=data, headers=headers, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                report = result.get('report', '')
                success = len(report) > 100  # Check if we got a meaningful report
                self.log_test("AI Audit Generation", success, f"Report length: {len(report)}")
                return success
            else:
                self.log_test("AI Audit Generation", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("AI Audit Generation", False, str(e))
            return False

    def test_audit_history(self):
        """Test getting audit history"""
        if not self.token:
            self.log_test("Get Audit History", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(f"{self.api_url}/audit/history", headers=headers, timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                audits = response.json().get('audits', [])
                details += f", Audits count: {len(audits)}"
            
            self.log_test("Get Audit History", success, details)
            return success
            
        except Exception as e:
            self.log_test("Get Audit History", False, str(e))
            return False

    def test_issue_creation(self):
        """Test creating an issue"""
        if not self.token:
            self.log_test("Create Issue", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            data = {
                "machine_name": "Treadmill-001",
                "machine_type": "Treadmill",
                "issue_description": "Belt is making unusual noise during operation",
                "severity": "medium"
            }
            
            response = requests.post(f"{self.api_url}/issues", json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                issue_id = result.get('id')
                self.test_issue_id = issue_id  # Store for status update test
                self.log_test("Create Issue", True, f"Issue ID: {issue_id}")
                return True
            else:
                self.log_test("Create Issue", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Create Issue", False, str(e))
            return False

    def test_get_issues(self):
        """Test getting issues list"""
        if not self.token:
            self.log_test("Get Issues", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(f"{self.api_url}/issues", headers=headers, timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                issues = response.json().get('issues', [])
                details += f", Issues count: {len(issues)}"
            
            self.log_test("Get Issues", success, details)
            return success
            
        except Exception as e:
            self.log_test("Get Issues", False, str(e))
            return False

    def test_update_issue_status(self):
        """Test updating issue status"""
        if not self.token or not hasattr(self, 'test_issue_id'):
            self.log_test("Update Issue Status", False, "No token or issue ID available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.patch(
                f"{self.api_url}/issues/{self.test_issue_id}?status=in_progress", 
                headers=headers, 
                timeout=30
            )
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                details += ", Status updated to in_progress"
            
            self.log_test("Update Issue Status", success, details)
            return success
            
        except Exception as e:
            self.log_test("Update Issue Status", False, str(e))
            return False

    def test_maintenance_tasks(self):
        """Test getting maintenance tasks"""
        try:
            response = requests.get(f"{self.api_url}/maintenance/tasks", timeout=30)
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                tasks = response.json().get('tasks', [])
                details += f", Tasks count: {len(tasks)}"
            
            self.log_test("Get Maintenance Tasks", success, details)
            return success
            
        except Exception as e:
            self.log_test("Get Maintenance Tasks", False, str(e))
            return False

    def test_service_request(self):
        """Test creating a service request"""
        if not self.token:
            self.log_test("Create Service Request", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            data = {
                "machine_type": "Treadmill",
                "issue_summary": "Complex electrical issue requiring engineer",
                "site_info": "Test Gym, 123 Test Street, Test City",
                "contact_name": "Test User",
                "contact_email": "test@gymfixai.com",
                "contact_phone": "+44 20 1234 5678"
            }
            
            response = requests.post(f"{self.api_url}/service/request", json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                request_id = result.get('id')
                self.log_test("Create Service Request", True, f"Request ID: {request_id}")
                return True
            else:
                self.log_test("Create Service Request", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Create Service Request", False, str(e))
            return False

    def test_payment_checkout(self):
        """Test payment checkout creation"""
        if not self.token:
            self.log_test("Payment Checkout", False, "No token available")
            return False
            
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            data = {
                "package_id": "basic",
                "origin_url": self.base_url
            }
            
            response = requests.post(f"{self.api_url}/payments/checkout", json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                checkout_url = result.get('url')
                session_id = result.get('session_id')
                success = checkout_url and session_id
                self.log_test("Payment Checkout", success, f"Session ID: {session_id}")
                return success
            else:
                self.log_test("Payment Checkout", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Payment Checkout", False, str(e))
            return False

    def run_all_tests(self):
        """Run all API tests"""
        print("🔍 Starting GymFix AI Backend API Tests...")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Health check first
        if not self.test_health_check():
            print("❌ Backend not accessible, stopping tests")
            return False
        
        # Authentication tests
        auth_success = self.test_user_registration() or self.test_user_login()
        if not auth_success:
            print("❌ Authentication failed, stopping tests")
            return False
            
        self.test_get_user_profile()
        
        # Core feature tests
        self.test_ai_chat_diagnosis()
        self.test_audit_generation()
        self.test_audit_history()
        
        # Issue management tests
        self.test_issue_creation()
        self.test_get_issues()
        self.test_update_issue_status()
        
        # Other features
        self.test_maintenance_tasks()
        self.test_service_request()
        self.test_payment_checkout()
        
        # Print summary
        print("=" * 60)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run} passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = GymFixAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_tests': tester.tests_run,
            'passed_tests': tester.tests_passed,
            'success_rate': (tester.tests_passed / tester.tests_run) * 100 if tester.tests_run > 0 else 0,
            'results': tester.test_results
        }, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())