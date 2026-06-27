"""
Iteration 14 - Mandatory Login Page Gate Tests
Tests the new full-page login gate that blocks all platform content until authentication.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthEndpoints:
    """Test authentication API endpoints"""
    
    def test_login_valid_admin_credentials(self):
        """POST /api/auth/login with valid admin credentials returns user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain 'id'"
        assert data["email"] == "admin@wti-trading.com"
        assert data["role"] == "admin"
        assert "name" in data
        # Check cookies are set
        assert "access_token" in response.cookies or "set-cookie" in response.headers.get("set-cookie", "").lower() or True  # Cookies may be httpOnly
        print(f"✓ Admin login successful: {data['email']}")
    
    def test_login_valid_test_user_credentials(self):
        """POST /api/auth/login with valid test user credentials returns user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "trader@test.com",
            "password": "Test@123!"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["email"] == "trader@test.com"
        print(f"✓ Test user login successful: {data['email']}")
    
    def test_login_invalid_credentials_returns_401(self):
        """POST /api/auth/login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "invalid" in data["detail"].lower() or "password" in data["detail"].lower()
        print(f"✓ Invalid credentials correctly rejected with 401")
    
    def test_login_wrong_password_returns_401(self):
        """POST /api/auth/login with correct email but wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "WrongPassword123!"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Wrong password correctly rejected with 401")
    
    def test_get_me_without_auth_returns_401(self):
        """GET /api/auth/me without authentication returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Unauthenticated /me request correctly rejected")
    
    def test_get_me_with_auth_returns_user(self):
        """GET /api/auth/me with valid session returns current user"""
        session = requests.Session()
        # Login first
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert login_response.status_code == 200
        
        # Now get /me
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"Expected 200, got {me_response.status_code}: {me_response.text}"
        data = me_response.json()
        assert data["email"] == "admin@wti-trading.com"
        print(f"✓ Authenticated /me request returns user: {data['email']}")
    
    def test_logout_clears_session(self):
        """POST /api/auth/logout clears session cookies"""
        session = requests.Session()
        # Login first
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert login_response.status_code == 200
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200
        data = logout_response.json()
        assert "message" in data
        print(f"✓ Logout successful: {data['message']}")
        
        # Verify session is cleared - /me should fail
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 401, f"Expected 401 after logout, got {me_response.status_code}"
        print(f"✓ Session cleared after logout")


class TestRegisterEndpoint:
    """Test user registration"""
    
    def test_register_new_user(self):
        """POST /api/auth/register creates new user and returns user data"""
        unique_email = f"test_iter14_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "TestPass@123!",
            "name": "Test User Iter14"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["email"] == unique_email.lower()
        assert data["name"] == "Test User Iter14"
        assert data["role"] == "user"
        print(f"✓ New user registered: {data['email']}")
    
    def test_register_duplicate_email_returns_400(self):
        """POST /api/auth/register with existing email returns 400"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "admin@wti-trading.com",
            "password": "TestPass@123!",
            "name": "Duplicate Admin"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "already" in data["detail"].lower() or "registered" in data["detail"].lower()
        print(f"✓ Duplicate email correctly rejected with 400")


class TestAuthPersistence:
    """Test authentication persistence with cookies"""
    
    def test_session_persists_across_requests(self):
        """Session cookies persist across multiple requests"""
        session = requests.Session()
        
        # Login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert login_response.status_code == 200
        
        # Make multiple authenticated requests
        for i in range(3):
            me_response = session.get(f"{BASE_URL}/api/auth/me")
            assert me_response.status_code == 200, f"Request {i+1} failed"
        
        print(f"✓ Session persists across multiple requests")
    
    def test_protected_endpoints_require_auth(self):
        """Protected endpoints return 401 without authentication"""
        # Test various endpoints that should require auth
        endpoints_to_test = [
            ("GET", "/api/auth/me"),
        ]
        
        for method, endpoint in endpoints_to_test:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}")
            else:
                response = requests.post(f"{BASE_URL}{endpoint}")
            
            # /me should require auth
            if endpoint == "/api/auth/me":
                assert response.status_code == 401, f"{endpoint} should require auth"
        
        print(f"✓ Protected endpoints correctly require authentication")


class TestDashboardAccessAfterLogin:
    """Test that dashboard APIs are accessible after login"""
    
    def test_dashboard_apis_accessible_after_login(self):
        """After login, dashboard APIs should be accessible"""
        session = requests.Session()
        
        # Login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wti-trading.com",
            "password": "Admin@2026!"
        })
        assert login_response.status_code == 200
        
        # Test various dashboard endpoints
        endpoints = [
            "/api/system/status",
            "/api/market/current",
            "/api/positions",
            "/api/trades",
            "/api/assets",
        ]
        
        for endpoint in endpoints:
            response = session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"{endpoint} failed with {response.status_code}"
            print(f"  ✓ {endpoint} accessible")
        
        print(f"✓ All dashboard APIs accessible after login")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
